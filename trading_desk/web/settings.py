"""Reads and writes the desk's settings from the browser.

Two files are involved and they are deliberately different:

``desk.config.json``  ordinary settings. Safe to read back, safe to show.
``.env``              wallet keys. Written, never read back to the browser —
                      the API reports only *whether* a key is set, never its
                      value, so an open dashboard tab cannot leak the wallet.

Risk is exposed to the UI as three presets rather than sixteen numbers,
because someone who does not want to think about ``risk_per_trade_pct``
should not have to, and a wrong guess at that number is expensive.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Optional

from ..config import DeskConfig
from ..execution.signers import EVM_KEY_ENV, SOLANA_KEY_ENV
from ..models import Chain

# Each preset is a complete, coherent risk stance. The labels are honest:
# "bold" is not "better", it is a larger bet with a correspondingly larger
# chance of ending the account, and the UI says so.
PRESETS: dict[str, dict[str, Any]] = {
    "cautious": {
        "label": "Cautious",
        "blurb": "Small bets, tight stops, fewer coins at once. Slowest, survives longest.",
        "risk": {"risk_per_trade_pct": 0.01, "max_concurrent_positions": 3,
                 "max_positions_per_chain": 2, "daily_loss_limit_pct": 0.15},
        "strategy": {"stop_loss_pct": 0.25, "min_entry_score": 0.60},
    },
    "normal": {
        "label": "Normal",
        "blurb": "The shipped defaults. Still above the mathematically optimal bet size.",
        "risk": {"risk_per_trade_pct": 0.02, "max_concurrent_positions": 4,
                 "max_positions_per_chain": 2, "daily_loss_limit_pct": 0.25},
        "strategy": {"stop_loss_pct": 0.30, "min_entry_score": 0.55},
    },
    "bold": {
        "label": "Bold",
        "blurb": "Bigger bets. Faster either way — and far more likely to end at zero.",
        "risk": {"risk_per_trade_pct": 0.04, "max_concurrent_positions": 5,
                 "max_positions_per_chain": 3, "daily_loss_limit_pct": 0.35},
        "strategy": {"stop_loss_pct": 0.35, "min_entry_score": 0.50},
    },
}

CHAIN_LABELS = {
    Chain.SOLANA.value: "Solana",
    Chain.BNB.value: "BNB Chain",
    Chain.ROBINHOOD.value: "Robinhood Chain",
}

# Changing these mid-flight would leave the running desk inconsistent with its
# own book, so they are written to disk and applied on the next start.
RESTART_REQUIRED = ("mode", "chains", "starting_capital_usd")


def detect_preset(cfg: DeskConfig) -> Optional[str]:
    for name, preset in PRESETS.items():
        if (
            abs(cfg.risk.risk_per_trade_pct - preset["risk"]["risk_per_trade_pct"]) < 1e-9
            and abs(cfg.strategy.stop_loss_pct - preset["strategy"]["stop_loss_pct"]) < 1e-9
        ):
            return name
    return None


def read_settings(cfg: DeskConfig, config_path: Path, env_path: Path) -> dict:
    """Current settings for the browser. Never includes key material."""
    return {
        "mode": cfg.execution.mode,
        "armed": cfg.execution.allow_live_trading,
        "starting_capital_usd": cfg.starting_capital_usd,
        "target_usd": cfg.target_usd,
        "chains": [c.value for c in cfg.chains],
        "available_chains": [
            {"id": value, "label": label} for value, label in CHAIN_LABELS.items()
        ],
        "preset": detect_preset(cfg),
        "presets": [
            {"id": name, "label": p["label"], "blurb": p["blurb"],
             "risk_pct": p["risk"]["risk_per_trade_pct"],
             "stop_pct": p["strategy"]["stop_loss_pct"]}
            for name, p in PRESETS.items()
        ],
        "risk_per_trade_pct": cfg.risk.risk_per_trade_pct,
        "stop_loss_pct": cfg.strategy.stop_loss_pct,
        "poll_interval_seconds": cfg.poll_interval_seconds,
        # Presence only. The values never cross this boundary.
        "keys": {
            "solana": bool(os.environ.get(SOLANA_KEY_ENV)),
            "evm": bool(os.environ.get(EVM_KEY_ENV)),
        },
        "config_path": str(config_path),
        "env_path": str(env_path),
    }


def _validate(payload: dict) -> list[str]:
    problems: list[str] = []

    preset = payload.get("preset")
    if preset is not None and preset not in PRESETS:
        problems.append(f"unknown risk preset {preset!r}")

    mode = payload.get("mode")
    if mode is not None and mode not in ("paper", "live"):
        problems.append("mode must be 'paper' or 'live'")

    if "starting_capital_usd" in payload:
        try:
            if float(payload["starting_capital_usd"]) <= 0:
                problems.append("starting money must be more than zero")
        except (TypeError, ValueError):
            problems.append("starting money must be a number")

    chains = payload.get("chains")
    if chains is not None:
        if not isinstance(chains, list) or not chains:
            problems.append("pick at least one chain")
        else:
            unknown = [c for c in chains if c not in CHAIN_LABELS]
            if unknown:
                problems.append(f"unknown chain(s): {', '.join(map(str, unknown))}")

    for field, chain in (("solana_key", "solana"), ("evm_key", "evm")):
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            problems.append(f"{field} must be text")
            continue
        kind, message = classify_secret(value, chain)
        # Anything that is not a usable key is refused here, before _write_keys
        # touches the disk. A seed phrase written to .env "just to see if it
        # works" is already a leaked seed phrase.
        if kind not in ("ok", "empty"):
            problems.append(message)
    return problems


def write_settings(
    payload: dict,
    cfg: DeskConfig,
    config_path: Path,
    env_path: Path,
    desk=None,
) -> dict:
    """Apply settings: to the running desk where safe, to disk always."""
    problems = _validate(payload)
    if problems:
        return {"ok": False, "problems": problems}

    stored = _load_json(config_path)
    needs_restart: list[str] = []

    preset = payload.get("preset")
    if preset:
        chosen = PRESETS[preset]
        stored.setdefault("risk", {}).update(chosen["risk"])
        stored.setdefault("strategy", {}).update(chosen["strategy"])
        # Numbers only — safe to apply to the live desk immediately.
        for key, value in chosen["risk"].items():
            setattr(cfg.risk, key, value)
        for key, value in chosen["strategy"].items():
            setattr(cfg.strategy, key, value)

    if "mode" in payload and payload["mode"] != cfg.execution.mode:
        stored.setdefault("execution", {})["mode"] = payload["mode"]
        if payload["mode"] == "paper" and desk is not None:
            # Live -> paper is the safe direction and needs no restart: swap the
            # executor for the simulated one right now. Requiring a restart to
            # get *out* of a broken live setup is how someone stays stuck.
            from ..execution.paper import PaperExecutor

            cfg.execution.mode = "paper"
            desk.executor = PaperExecutor(cfg)
            desk.paused = False
        else:
            # paper -> live builds a signer from the environment at startup, so
            # that direction genuinely has to wait for a restart.
            needs_restart.append("mode")

    if payload.get("mode") == "live":
        # Arming the second switch is what the operator is asking for by
        # choosing live here; --arm is still required to broadcast.
        stored.setdefault("execution", {})["allow_live_trading"] = True
    elif payload.get("mode") == "paper":
        # Clear it on the way back too. Leaving it set means the next accidental
        # flip to live is armed again without anyone choosing that.
        stored.setdefault("execution", {})["allow_live_trading"] = False
        cfg.execution.allow_live_trading = False

    account_reset = False
    if "starting_capital_usd" in payload:
        amount = float(payload["starting_capital_usd"])
        if amount != cfg.starting_capital_usd:
            stored["starting_capital_usd"] = amount
            cfg.starting_capital_usd = amount
            if desk is not None and _is_simulated(cfg, desk):
                # Apply it for real. Writing the number to a file while the
                # journal's saved balance keeps winning is how this setting came
                # to look broken: it changed nothing, restart or not.
                desk.reset_account(amount)
                account_reset = True
            else:
                needs_restart.append("starting_capital_usd")

    if payload.get("chains"):
        chains = list(dict.fromkeys(payload["chains"]))
        if chains != [c.value for c in cfg.chains]:
            stored["chains"] = chains
            needs_restart.append("chains")

    _write_json(config_path, stored)

    key_written = _write_keys(payload, env_path)
    if key_written:
        needs_restart.append("wallet keys")

    return {
        "ok": True,
        "needs_restart": sorted(set(needs_restart)),
        "applied_now": bool(preset) or account_reset,
        "account_reset": account_reset,
    }


def _write_keys(payload: dict, env_path: Path) -> bool:
    """Write wallet keys to .env, replacing any previous value.

    An empty string clears a key. The file is written 0600 because it is, in
    effect, the wallet itself.
    """
    updates: dict[str, str] = {}
    for field, env_name in (("solana_key", SOLANA_KEY_ENV), ("evm_key", EVM_KEY_ENV)):
        if field in payload and payload[field] is not None:
            updates[env_name] = str(payload[field]).strip()
    if not updates:
        return False

    existing: dict[str, str] = {}
    if env_path.exists():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                existing[key.strip()] = value.strip()
    existing.update(updates)

    lines = ["# Wallet keys. Anyone with this file can spend the money.",
             "# Never share it, never commit it, never paste it anywhere."]
    for key, value in existing.items():
        if value:
            lines.append(f"{key}={value}")
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    env_path.write_text("\n".join(lines) + "\n")
    if platform.system() != "Windows":
        try:
            env_path.chmod(0o600)
        except OSError:
            pass
    return True


def _is_simulated(cfg: DeskConfig, desk) -> bool:
    """Whether this desk's trades are pretend, so its account can be reset.

    Judged from the executor actually in use rather than the config string: the
    two disagree while a mode change is pending, and what decides whether real
    money is involved is what would execute an order, not what a file says. An
    unarmed live executor has never placed one either.
    """
    from ..execution.live import LiveExecutor

    executor = getattr(desk, "executor", None)
    if not isinstance(executor, LiveExecutor):
        return True
    try:
        return bool(executor.preflight())
    except Exception:  # noqa: BLE001 - if we cannot tell, assume it is real
        return False


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


# Recognising what someone pasted, so the wrong secret is refused before it is
# written anywhere. The dangerous case is a seed phrase: it is the master key to
# every account a wallet will ever derive, so it must never reach disk — and
# somebody who does not know the difference will reach for it first, because it
# is the thing their wallet app showed them when they set it up.
_MNEMONIC_LENGTHS = (12, 15, 18, 21, 24)
_HEX = set("0123456789abcdefABCDEF")
_BASE58 = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def classify_secret(value: str, chain: str) -> tuple[str, str]:
    """Say what a pasted string is. Returns (kind, message).

    ``kind`` is "ok" when it looks like a usable private key for that chain, and
    otherwise names what was pasted so the message can be specific. Never echoes
    the value — an error that quotes a seed phrase has leaked it into the logs.
    """
    text = (value or "").strip()
    if not text:
        return "empty", ""

    words = text.split()
    if len(words) > 1:
        if len(words) in _MNEMONIC_LENGTHS and all(w.isalpha() for w in words):
            return "mnemonic", (
                f"That looks like a {len(words)}-word seed phrase. Never put a seed "
                "phrase into any app — it controls every account in your wallet, "
                "forever. This needs the private key of one single account instead."
            )
        return "phrase", (
            "That looks like several words rather than a key. If it is a seed "
            "phrase, do not paste it anywhere — export one account's private key."
        )

    body = text[2:] if text.lower().startswith("0x") else text

    if chain == "evm":
        if len(body) == 40 and set(body) <= _HEX:
            return "address", (
                "That is your wallet address, which is public and cannot sign "
                "anything. The desk needs that account's private key — a longer "
                "string, 64 characters after the 0x."
            )
        if len(body) == 64 and set(body) <= _HEX:
            return "ok", ""
        return "unknown", (
            "That does not look like a BNB Chain private key. Expected 64 "
            f"characters of 0-9 and a-f, usually written after 0x — this was "
            f"{len(body)} characters."
        )

    # Solana: either a base58 secret (64 bytes) or the keygen JSON byte array.
    if text.startswith("["):
        try:
            numbers = json.loads(text)
        except json.JSONDecodeError:
            return "unknown", "That looks like a JSON array but could not be read."
        if isinstance(numbers, list) and len(numbers) in (64, 65):
            return "ok", ""
        return "unknown", (
            "A Solana key file is an array of 64 numbers; this had "
            f"{len(numbers) if isinstance(numbers, list) else 'a different shape'}."
        )
    if set(text) <= _BASE58:
        if len(text) >= 80:
            return "ok", ""
        if 32 <= len(text) <= 45:
            return "address", (
                "That is your Solana wallet address, which is public and cannot "
                "sign anything. The desk needs the account's private key, which is "
                "roughly twice as long."
            )
    return "unknown", (
        "That does not look like a Solana private key. Export the private key "
        "from your wallet — it is a long string, or a file of 64 numbers."
    )

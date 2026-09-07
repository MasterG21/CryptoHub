"""Config loading, environment overrides and validation."""
import json
import os
import tempfile

import pytest

from trading_desk.config import DeskConfig, load_config, validate_config
from trading_desk.models import Chain


def write_config(payload) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(payload, handle)
    handle.close()
    return handle.name


def test_defaults_are_valid():
    assert validate_config(DeskConfig()) == []


def test_sections_load_from_a_file():
    path = write_config(
        {
            "starting_capital_usd": 500,
            "chains": ["solana", "bsc"],
            "risk": {"risk_per_trade_pct": 0.01, "max_concurrent_positions": 8},
            "strategy": {"stop_loss_pct": 0.25},
        }
    )
    cfg, warnings = load_config(path)

    assert warnings == []
    assert cfg.starting_capital_usd == 500
    assert cfg.chains == (Chain.SOLANA, Chain.BNB)
    assert cfg.risk.risk_per_trade_pct == 0.01
    assert cfg.risk.max_concurrent_positions == 8
    assert cfg.strategy.stop_loss_pct == 0.25
    os.unlink(path)


def test_a_misspelled_risk_key_warns_rather_than_silently_using_the_default():
    """Silently ignoring 'risk_per_trade' would trade at 2% while you think 0.5%."""
    path = write_config({"risk": {"risk_per_trade": 0.005}})
    cfg, warnings = load_config(path)

    assert any("risk_per_trade" in w for w in warnings)
    assert cfg.risk.risk_per_trade_pct == DeskConfig().risk.risk_per_trade_pct
    os.unlink(path)


def test_scale_out_lists_become_tuples():
    path = write_config({"strategy": {"scale_out_levels": [2, 5], "scale_out_fractions": [0.5, 0.3]}})
    cfg, _ = load_config(path)

    assert cfg.strategy.scale_out_levels == (2, 5)
    assert validate_config(cfg) == []
    os.unlink(path)


def test_environment_overrides_the_file(monkeypatch):
    path = write_config({"risk": {"risk_per_trade_pct": 0.01}})
    monkeypatch.setenv("DESK_RISK_PER_TRADE", "0.03")
    monkeypatch.setenv("DESK_CHAINS", "solana")
    cfg, warnings = load_config(path)

    assert cfg.risk.risk_per_trade_pct == 0.03
    assert cfg.chains == (Chain.SOLANA,)
    assert warnings == []
    os.unlink(path)


def test_a_bad_environment_value_warns_and_keeps_the_default(monkeypatch):
    monkeypatch.setenv("DESK_RISK_PER_TRADE", "aggressive")
    cfg, warnings = load_config()

    assert any("not a valid float" in w for w in warnings)
    assert cfg.risk.risk_per_trade_pct == DeskConfig().risk.risk_per_trade_pct


def test_an_unknown_chain_warns():
    path = write_config({"chains": ["solana", "dogechain"]})
    _, warnings = load_config(path)
    assert any("bad chain" in w for w in warnings)
    os.unlink(path)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda c: setattr(c.risk, "risk_per_trade_pct", 1.5), "risk_per_trade_pct"),
        (lambda c: setattr(c.risk, "max_pool_impact_pct", 0), "max_pool_impact_pct"),
        (lambda c: setattr(c.strategy, "stop_loss_pct", 1.2), "stop_loss_pct"),
        (lambda c: setattr(c.strategy, "trail_arm_multiple", 0.9), "trail_arm_multiple"),
        (lambda c: setattr(c.execution, "mode", "yolo"), "mode"),
        (lambda c: setattr(c, "target_usd", 50), "target_usd"),
        (lambda c: setattr(c, "chains", ()), "chain"),
    ],
)
def test_invalid_settings_are_reported(mutate, expected):
    cfg = DeskConfig()
    mutate(cfg)
    problems = validate_config(cfg)
    assert any(expected in p for p in problems)


def test_scale_out_fractions_cannot_exceed_the_position():
    cfg = DeskConfig()
    cfg.strategy.scale_out_fractions = (0.6, 0.6)
    cfg.strategy.scale_out_levels = (2.0, 4.0)
    assert any("more than the whole position" in p for p in validate_config(cfg))


def test_scale_out_levels_must_ascend():
    cfg = DeskConfig()
    cfg.strategy.scale_out_levels = (4.0, 2.0)
    cfg.strategy.scale_out_fractions = (0.3, 0.3)
    assert any("ascending" in p for p in validate_config(cfg))


def test_ladder_lengths_must_match():
    cfg = DeskConfig()
    cfg.strategy.scale_out_levels = (2.0,)
    cfg.strategy.scale_out_fractions = (0.3, 0.3)
    assert any("same length" in p for p in validate_config(cfg))


def test_gas_lookup_falls_back_for_an_unconfigured_chain():
    cfg = DeskConfig()
    assert cfg.gas_for(Chain.BNB) == 0.35
    cfg.execution.gas_usd = {}
    assert cfg.gas_for(Chain.BNB) == 0.10

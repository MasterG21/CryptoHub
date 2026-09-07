"""Produce everything BscScan needs to verify the deployed source.

Verification is not cosmetic. An unverified contract is the single
largest deduction any rug screener applies, and it is the first thing a
careful buyer checks — so a launch is not finished until this is done.

Two paths, and the first always runs:

  1. A bundle written to disk: the exact solc standard-JSON input, the
     ABI-encoded constructor arguments, and the compiler settings. Paste
     these into the explorer's verification form and it will match,
     because they are the same bytes the launcher compiled and deployed.
  2. If BSCSCAN_API_KEY is set, an automatic submission. It is attempted
     after the bundle is written, so a failure there costs you nothing.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from compile import (  # noqa: E402
    EVM_VERSION, OPTIMIZER_ENABLED, OPTIMIZER_RUNS, SOLC_VERSION, compile_contracts,
)

# solc reports its own long version; the explorer wants that exact string.
SOLC_LONG = f"v{SOLC_VERSION}+commit.e11b9ed9"


def encode_constructor_args(abi: list, args: list) -> str:
    """ABI-encode constructor arguments, hex without the 0x prefix."""
    from eth_abi import encode

    ctor = next((f for f in abi if f.get("type") == "constructor"), None)
    if ctor is None or not ctor.get("inputs"):
        return ""
    types = [i["type"] for i in ctor["inputs"]]
    return encode(types, args).hex()


def write_verification_bundle(deployment: dict, out_dir: str,
                              node_modules: str | None = None) -> str:
    """Write one folder per deployed contract with everything needed."""
    payload = compile_contracts(node_modules)
    artifacts, solc_input = payload["contracts"], payload["input"]

    bundle_dir = os.path.join(out_dir, "verification")
    os.makedirs(bundle_dir, exist_ok=True)

    index = []
    for name, info in deployment["contracts"].items():
        art = artifacts[name]
        args_hex = encode_constructor_args(art["abi"], info["constructor_args"])

        contract_dir = os.path.join(bundle_dir, name)
        os.makedirs(contract_dir, exist_ok=True)

        with open(os.path.join(contract_dir, "standard-input.json"), "w") as fh:
            json.dump(solc_input, fh, indent=1)
        with open(os.path.join(contract_dir, "constructor-args.txt"), "w") as fh:
            fh.write(args_hex)

        entry = {
            "contract": name,
            "address": info["address"],
            "contract_path": f"{art['file']}:{name}",
            "compiler": SOLC_LONG,
            "optimizer": OPTIMIZER_ENABLED,
            "runs": OPTIMIZER_RUNS,
            "evm_version": EVM_VERSION,
            "constructor_args": args_hex,
            "license": "MIT",
        }
        with open(os.path.join(contract_dir, "settings.json"), "w") as fh:
            json.dump(entry, fh, indent=2)
        index.append(entry)

    with open(os.path.join(bundle_dir, "README.txt"), "w") as fh:
        fh.write(_instructions(deployment, index))
    return bundle_dir


def _instructions(deployment: dict, index: list) -> str:
    lines = [
        "Verifying the deployed contracts",
        "=" * 34,
        "",
        "On the explorer choose:",
        "  Verify and Publish -> Solidity (Standard-Json-Input)",
        "",
        "Then for each contract below, upload standard-input.json, select the",
        "compiler version, and paste the constructor arguments.",
        "",
        "Use these settings exactly. They are the ones the bytecode was built",
        "with, and verification fails on any mismatch.",
        "",
    ]
    for e in index:
        lines += [
            f"{e['contract']}",
            f"  address            {e['address']}",
            f"  contract to select {e['contract_path']}",
            f"  compiler           {e['compiler']}",
            f"  optimizer          {'Yes' if e['optimizer'] else 'No'}, {e['runs']} runs",
            f"  evm version        {e['evm_version']}",
            f"  license            {e['license']}",
            f"  constructor args   {e['constructor_args'] or '(none)'}",
            "",
        ]
    return "\n".join(lines)


def submit_to_explorer(deployment: dict, out_dir: str, api_url: str, api_key: str,
                       chain_id: int) -> list[tuple[str, str]]:
    """Best-effort automatic verification. Returns (contract, message) pairs."""
    import requests

    results = []
    bundle_dir = os.path.join(out_dir, "verification")
    for name in deployment["contracts"]:
        contract_dir = os.path.join(bundle_dir, name)
        with open(os.path.join(contract_dir, "settings.json")) as fh:
            settings = json.load(fh)
        with open(os.path.join(contract_dir, "standard-input.json")) as fh:
            source = fh.read()

        data = {
            "chainid": str(chain_id),
            "module": "contract",
            "action": "verifysourcecode",
            "apikey": api_key,
            "codeformat": "solidity-standard-json-input",
            "sourceCode": source,
            "contractaddress": settings["address"],
            "contractname": settings["contract_path"],
            "compilerversion": settings["compiler"],
            "constructorArguements": settings["constructor_args"],
        }
        try:
            resp = requests.post(api_url, data=data, timeout=60)
            body = resp.json()
            ok = str(body.get("status")) == "1"
            results.append((name, f"{'submitted' if ok else 'rejected'}: {body.get('result')}"))
        except Exception as exc:
            results.append((name, f"could not submit ({exc}) — use the bundle by hand"))
    return results

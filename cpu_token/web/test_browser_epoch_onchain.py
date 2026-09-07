"""End-to-end: an epoch built by the browser code, claimed on a real EVM.

The cross-check against Python proves the two agree. This proves the thing
that actually matters — that a root produced by epoch-builder.html is one
the deployed contract accepts, and that the proofs it writes let holders
collect. It runs the page's own JavaScript through node, then deploys the
real contracts to an in-process EVM and claims against them.

    NODE_MODULES=$PWD/node_modules python cpu_token/web/test_browser_epoch_onchain.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from compile import compile_contracts  # noqa: E402
from web3 import EthereumTesterProvider, Web3  # noqa: E402

WEB_DIR = os.path.dirname(os.path.abspath(__file__))

BUILD_JS = r"""
const fs=require("fs"), path=require("path"), vm=require("vm");
const html=fs.readFileSync(path.join(process.env.WEB_DIR,"epoch-builder.html"),"utf8");
const sandbox={module:{exports:{}},console,TextEncoder};
sandbox.window=undefined; vm.createContext(sandbox);
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],sandbox);
const B=sandbox.module.exports;
const input=JSON.parse(fs.readFileSync(process.env.INPUT,"utf8"));
const split=B.computeSplit(input.holders,BigInt(input.total),input.excluded,0);
const tree=B.buildClaims(split.payouts.map(p=>[p[0],p[1]]));
fs.writeFileSync(process.env.OUT,JSON.stringify({
  merkle_root:tree.root, allocated:split.allocated.toString(), claims:tree.claims}));
"""

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS  {name}")
    except Exception as exc:
        FAILED.append(name)
        print(f"  FAIL  {name}: {exc}")


def build_in_browser_code(holders, total, excluded):
    with tempfile.TemporaryDirectory() as td:
        js, inp, out = (os.path.join(td, n) for n in ("b.js", "in.json", "out.json"))
        with open(js, "w") as fh:
            fh.write(BUILD_JS)
        with open(inp, "w") as fh:
            json.dump({"holders": holders, "total": str(total), "excluded": excluded}, fh)
        subprocess.run(["node", js], check=True,
                       env={**os.environ, "WEB_DIR": WEB_DIR, "INPUT": inp, "OUT": out})
        with open(out) as fh:
            return json.load(fh)


def main() -> int:
    art = compile_contracts(os.environ.get("NODE_MODULES"))["contracts"]
    w3 = Web3(EthereumTesterProvider())
    owner = w3.eth.accounts[0]
    w3.eth.default_account = owner
    alice, bob, carol = w3.eth.accounts[1:4]

    holders = [[alice, str(700 * 10**18)], [bob, str(200 * 10**18)],
               [carol, str(100 * 10**18)],
               ["0x000000000000000000000000000000000000dEaD", str(10**24)]]
    pool = "0x00000000000000000000000000000000000000Aa"
    holders.append([pool, str(500 * 10**18)])

    total = 1000 * 10**18
    print("\nBuilding the epoch with epoch-builder.html's own code...")
    epoch = build_in_browser_code(holders, total, [pool])
    print(f"  root      {epoch['merkle_root']}")
    print(f"  allocated {epoch['allocated']}")
    print(f"  claims    {len(epoch['claims'])}")

    def deploy(name, *args):
        c = w3.eth.contract(abi=art[name]["abi"], bytecode=art[name]["bin"])
        tx = c.constructor(*args).transact()
        addr = w3.eth.wait_for_transaction_receipt(tx).contractAddress
        return w3.eth.contract(address=addr, abi=art[name]["abi"])

    print("\nDeploying and claiming against a real EVM:")
    cpu = deploy("ComputingPower", owner)
    reward = deploy("MockERC20", "Reward", "RWD", 10**26)
    dist = deploy("MerkleRewardDistributor", reward.address, cpu.address, owner)

    allocated = int(epoch["allocated"])
    check("pool and burn were excluded by the browser code",
          lambda: _assert(len(epoch["claims"]) == 3))
    check("browser allocation never exceeds the pot", lambda: _assert(allocated <= total))

    reward.functions.approve(dist.address, allocated).transact()
    reward.functions.approve(dist.address, allocated).call()
    dist.functions.openEpoch(
        bytes.fromhex(epoch["merkle_root"][2:]), allocated, 30 * 24 * 3600
    ).transact()
    check("contract accepted the browser-built root",
          lambda: _assert(dist.functions.epochCount().call() == 1))

    def claim(rec):
        return dist.functions.claim(
            0, rec["index"], rec["account"], int(rec["amount"]),
            [bytes.fromhex(p[2:]) for p in rec["proof"]],
        ).transact()

    for rec in epoch["claims"]:
        before = reward.functions.balanceOf(rec["account"]).call()
        claim(rec)
        after = reward.functions.balanceOf(rec["account"]).call()
        check(f"proof verified and paid {rec['account'][:10]}…",
              lambda b=before, a=after, r=rec: _assert(a - b == int(r["amount"])))

    check("every allocated token was claimed",
          lambda: _assert(dist.functions.unclaimed(0).call() == 0))

    def forged():
        rec = dict(epoch["claims"][0])
        dist.functions.claim(
            0, rec["index"], rec["account"], int(rec["amount"]) + 1,
            [bytes.fromhex(p[2:]) for p in rec["proof"]],
        ).transact()
    check("a tampered amount is still rejected", lambda: _reverts(forged))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


def _assert(c):
    assert c


def _reverts(fn):
    try:
        fn()
    except Exception:
        return
    raise AssertionError("expected a revert")


if __name__ == "__main__":
    raise SystemExit(main())

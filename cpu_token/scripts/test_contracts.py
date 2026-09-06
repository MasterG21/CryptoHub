"""Deploys the contracts to an in-process EVM and exercises the reward flow.

Run: python cpu_token/scripts/test_contracts.py
Needs: pip install "web3[tester]" ; npm install solc @openzeppelin/contracts
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from web3 import EthereumTesterProvider, Web3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from merkle import build_claims, leaf_hash  # noqa: E402

CONTRACTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "contracts")
NODE_MODULES = os.environ.get("NODE_MODULES", os.path.join(os.getcwd(), "node_modules"))

COMPILE_JS = r"""
const fs=require('fs'),path=require('path'),solc=require(process.env.NODE_MODULES+'/solc');
const SRC=process.env.CONTRACTS, NM=process.env.NODE_MODULES;
const sources={};
(function walk(d,pre){for(const f of fs.readdirSync(d)){const p=path.join(d,f);
 if(fs.statSync(p).isDirectory())walk(p,pre+f+'/');
 else if(f.endsWith('.sol'))sources[pre+f]={content:fs.readFileSync(p,'utf8')};}})(SRC,'');
const findImport=p=>{const f=path.join(NM,p);
 return fs.existsSync(f)?{contents:fs.readFileSync(f,'utf8')}:{error:'not found '+p};};
const out=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources,settings:{
 optimizer:{enabled:true,runs:200},
 outputSelection:{'*':{'*':['abi','evm.bytecode.object']}}}}),{import:findImport}));
const errs=(out.errors||[]).filter(e=>e.severity==='error');
if(errs.length){errs.forEach(e=>console.error(e.formattedMessage));process.exit(1);}
const flat={};
for(const f of Object.keys(out.contracts))for(const[n,c]of Object.entries(out.contracts[f]))
 flat[n]={abi:c.abi,bin:c.evm.bytecode.object};
fs.writeFileSync(process.env.OUT,JSON.stringify(flat));
"""

PASSED, FAILED = [], []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS  {name}")
    except Exception as exc:
        FAILED.append((name, exc))
        print(f"  FAIL  {name}: {exc}")


def compile_all():
    with tempfile.TemporaryDirectory() as td:
        js, out = os.path.join(td, "c.js"), os.path.join(td, "out.json")
        open(js, "w").write(COMPILE_JS)
        env = {**os.environ, "CONTRACTS": CONTRACTS, "NODE_MODULES": NODE_MODULES, "OUT": out}
        subprocess.run(["node", js], check=True, env=env)
        return json.load(open(out))


def main():
    art = compile_all()
    w3 = Web3(EthereumTesterProvider())
    owner, alice, bob, carol = w3.eth.accounts[:4]
    w3.eth.default_account = owner

    def deploy(name, *args):
        c = w3.eth.contract(abi=art[name]["abi"], bytecode=art[name]["bin"])
        tx = c.constructor(*args).transact()
        addr = w3.eth.wait_for_transaction_receipt(tx).contractAddress
        return w3.eth.contract(address=addr, abi=art[name]["abi"])

    def reverts(fn, label=""):
        try:
            fn()
        except Exception:
            return
        raise AssertionError(f"expected revert but call succeeded {label}")

    print("\nDeploying...")
    cpu = deploy("ComputingPower", owner)
    reward = deploy("MockERC20", "Mock Reward", "MOCK", 10**24)
    dist = deploy("MerkleRewardDistributor", reward.address, cpu.address, owner)
    print(f"  CPU         {cpu.address}")
    print(f"  reward      {reward.address}")
    print(f"  distributor {dist.address}")

    print("\nToken:")
    check("total supply is 1e9 CPU", lambda: _eq(cpu.functions.totalSupply().call(), 10**27))
    check("supply all to treasury",
          lambda: _eq(cpu.functions.balanceOf(owner).call(), 10**27))
    check("symbol is CPU", lambda: _eq(cpu.functions.symbol().call(), "CPU"))
    check("no mint function in ABI",
          lambda: _assert(not any(f.get("name") == "mint" for f in art["ComputingPower"]["abi"])))
    check("no owner function in ABI",
          lambda: _assert(not any(f.get("name") in ("owner", "transferOwnership")
                                  for f in art["ComputingPower"]["abi"])))
    check("no pause/blacklist/fee in ABI", lambda: _assert(
        not any(any(k in (f.get("name") or "").lower()
                    for k in ("pause", "blacklist", "setfee", "settax", "maxtx", "maxwallet"))
                for f in art["ComputingPower"]["abi"])))

    # --- reward epoch ---
    print("\nReward epoch:")
    payouts = [(alice, 600 * 10**18), (bob, 300 * 10**18), (carol, 100 * 10**18)]
    total = sum(a for _, a in payouts)
    root, claims = build_claims(payouts)

    reward.functions.approve(dist.address, total).transact()
    dist.functions.openEpoch(root, total, 30 * 24 * 3600).transact()

    check("epoch opened and funded", lambda: _eq(
        reward.functions.balanceOf(dist.address).call(), total))
    check("epoch count is 1", lambda: _eq(dist.functions.epochCount().call(), 1))

    def claim(i, sender=None):
        c = claims[i]
        return dist.functions.claim(
            0, c["index"], c["account"], int(c["amount"]),
            [bytes.fromhex(p[2:]) for p in c["proof"]],
        ).transact({"from": sender or owner})

    claim(0)
    check("alice received her share",
          lambda: _eq(reward.functions.balanceOf(alice).call(), 600 * 10**18))
    check("double claim reverts", lambda: reverts(lambda: claim(0)))
    check("isClaimed reflects the claim",
          lambda: _assert(dist.functions.isClaimed(0, 0).call()))
    check("unclaimed remainder tracked",
          lambda: _eq(dist.functions.unclaimed(0).call(), 400 * 10**18))

    check("third party may claim on bob's behalf, funds go to bob",
          lambda: (claim(1, sender=carol),
                   _eq(reward.functions.balanceOf(bob).call(), 300 * 10**18)))

    # forged claim: real proof, inflated amount
    def forged():
        c = claims[2]
        dist.functions.claim(
            0, c["index"], c["account"], int(c["amount"]) * 10,
            [bytes.fromhex(p[2:]) for p in c["proof"]],
        ).transact()
    check("inflated amount reverts (bad proof)", lambda: reverts(forged))

    def wrong_account():
        c = claims[2]
        dist.functions.claim(
            0, c["index"], alice, int(c["amount"]),
            [bytes.fromhex(p[2:]) for p in c["proof"]],
        ).transact()
    check("redirecting a leaf to another account reverts", lambda: reverts(wrong_account))

    check("sweep before deadline reverts",
          lambda: reverts(lambda: dist.functions.sweepUnclaimed(0, owner).transact()))
    check("claim window under 30 days reverts", lambda: reverts(
        lambda: dist.functions.openEpoch(root, 1, 3600).transact()))
    check("unknown epoch reverts", lambda: reverts(lambda: dist.functions.unclaimed(99).call()))

    # --- over-allocation guard: a root promising more than was funded ---
    print("\nOver-allocation guard:")
    big = [(alice, 10**24), (bob, 10**24)]
    bad_root, bad_claims = build_claims(big)
    reward.functions.approve(dist.address, 10**18).transact()
    dist.functions.openEpoch(bad_root, 10**18, 30 * 24 * 3600).transact()

    def over():
        c = bad_claims[0]
        dist.functions.claim(
            1, c["index"], c["account"], int(c["amount"]),
            [bytes.fromhex(p[2:]) for p in c["proof"]],
        ).transact()
    check("claim exceeding the epoch's funding reverts", lambda: reverts(over))
    check("epoch 0 balance untouched by epoch 1's bad root",
          lambda: _eq(dist.functions.unclaimed(0).call(), 100 * 10**18))

    # --- sweep after deadline ---
    print("\nSweep after deadline:")
    w3.provider.ethereum_tester.time_travel(w3.eth.get_block("latest")["timestamp"] + 31 * 24 * 3600)
    w3.provider.ethereum_tester.mine_block()
    before = reward.functions.balanceOf(owner).call()
    dist.functions.sweepUnclaimed(0, owner).transact()
    check("sweep returns exactly the unclaimed remainder",
          lambda: _eq(reward.functions.balanceOf(owner).call() - before, 100 * 10**18))
    check("double sweep reverts",
          lambda: reverts(lambda: dist.functions.sweepUnclaimed(0, owner).transact()))
    check("carol can no longer claim after the deadline", lambda: reverts(lambda: claim(2)))

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


def _eq(a, b):
    assert a == b, f"{a!r} != {b!r}"


def _assert(cond):
    assert cond


if __name__ == "__main__":
    raise SystemExit(main())

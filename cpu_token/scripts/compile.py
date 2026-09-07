"""Compile the contracts by shelling out to the npm solc build.

Kept in one place so the test suite and the launcher compile with byte
identical settings. That matters more than it looks: BscScan verifies
source by recompiling it and comparing bytecode, so if the launcher and
the verifier disagree about the optimizer, verification silently fails
after the token is already live.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

CPU_TOKEN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS_DIR = os.path.join(CPU_TOKEN_DIR, "contracts")

# The exact settings BscScan must be told about at verification time.
SOLC_VERSION = "0.8.24"
OPTIMIZER_ENABLED = True
OPTIMIZER_RUNS = 200
EVM_VERSION = "paris"

_COMPILE_JS = r"""
const fs=require('fs'),path=require('path');
const solc=require(process.env.NODE_MODULES+'/solc');
const SRC=process.env.CONTRACTS, NM=process.env.NODE_MODULES;
const sources={};
(function walk(d,pre){for(const f of fs.readdirSync(d)){const p=path.join(d,f);
 if(fs.statSync(p).isDirectory())walk(p,pre+f+'/');
 else if(f.endsWith('.sol'))sources[pre+f]={content:fs.readFileSync(p,'utf8')};}})(SRC,'');
const findImport=p=>{const f=path.join(NM,p);
 return fs.existsSync(f)?{contents:fs.readFileSync(f,'utf8')}:{error:'not found '+p};};
const input={language:'Solidity',sources,settings:{
 optimizer:{enabled:process.env.OPT==='1',runs:parseInt(process.env.RUNS,10)},
 evmVersion:process.env.EVM,
 outputSelection:{'*':{'*':['abi','evm.bytecode.object','evm.deployedBytecode.object']}}}};
const out=JSON.parse(solc.compile(JSON.stringify(input),{import:findImport}));
const errs=(out.errors||[]).filter(e=>e.severity==='error');
if(errs.length){errs.forEach(e=>console.error(e.formattedMessage));process.exit(1);}
const flat={};
for(const f of Object.keys(out.contracts||{}))
 for(const[n,c]of Object.entries(out.contracts[f]))
  flat[n]={abi:c.abi,bin:c.evm.bytecode.object,
           deployed:c.evm.deployedBytecode.object,file:f};
fs.writeFileSync(process.env.OUT,JSON.stringify({contracts:flat,input}));
"""


class CompileError(RuntimeError):
    pass


def find_node_modules(explicit: str | None = None) -> str:
    """Locate node_modules holding solc, checking the usual places."""
    candidates = [
        explicit,
        os.environ.get("NODE_MODULES"),
        os.path.join(os.getcwd(), "node_modules"),
        os.path.join(CPU_TOKEN_DIR, "node_modules"),
        os.path.join(os.path.dirname(CPU_TOKEN_DIR), "node_modules"),
    ]
    for c in candidates:
        if c and os.path.isdir(os.path.join(c, "solc")):
            return c
    raise CompileError(
        "Could not find solc. Run this from a directory where you have run:\n"
        f"  npm install solc@{SOLC_VERSION} @openzeppelin/contracts@5.0.2\n"
        "or set NODE_MODULES to the folder containing them."
    )


def compile_contracts(node_modules: str | None = None) -> dict:
    """Return {name: {abi, bin, deployed, file}} plus the solc input JSON."""
    if shutil.which("node") is None:
        raise CompileError("node is not installed, and solc runs on it.")
    nm = find_node_modules(node_modules)

    with tempfile.TemporaryDirectory() as td:
        js_path = os.path.join(td, "compile.js")
        out_path = os.path.join(td, "out.json")
        with open(js_path, "w") as fh:
            fh.write(_COMPILE_JS)
        env = {
            **os.environ,
            "CONTRACTS": CONTRACTS_DIR,
            "NODE_MODULES": nm,
            "OUT": out_path,
            "OPT": "1" if OPTIMIZER_ENABLED else "0",
            "RUNS": str(OPTIMIZER_RUNS),
            "EVM": EVM_VERSION,
        }
        proc = subprocess.run(["node", js_path], env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            raise CompileError(f"solc failed:\n{proc.stderr or proc.stdout}")
        with open(out_path) as fh:
            payload = json.load(fh)

    return payload

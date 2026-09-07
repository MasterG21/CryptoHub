/**
 * Proves the flattened contracts are safe to paste.
 *
 * Two things must hold, and neither is obvious by eye: each flattened file
 * compiles with no import resolver at all (so it is genuinely
 * self-contained), and its bytecode is identical to the original's once
 * the trailing CBOR metadata — which encodes a hash of the source and so
 * legitimately differs — is stripped. If those hold, pasting the flattened
 * file into Remix deploys exactly the contract in this repo.
 *
 *   NODE_MODULES=$PWD/node_modules node cpu_token/scripts/check_flattened.js
 */
const fs=require('fs'), path=require('path'), solc=require((process.env.NODE_MODULES || (__dirname+'/../../node_modules'))+'/solc');
const NM=process.env.NODE_MODULES || (__dirname+'/../../node_modules');
const SRC=path.join(__dirname,'..','contracts');
const findImport=p=>{const f=path.join(NM,p);
  return fs.existsSync(f)?{contents:fs.readFileSync(f,'utf8')}:{error:'nf '+p};};
const settings={optimizer:{enabled:true,runs:200},evmVersion:'paris',
  outputSelection:{'*':{'*':['evm.deployedBytecode.object']}}};

function build(sources, resolve){
  const out=JSON.parse(solc.compile(JSON.stringify({language:'Solidity',sources,settings}),
    resolve?{import:findImport}:undefined));
  const errs=(out.errors||[]).filter(e=>e.severity==='error');
  if(errs.length){errs.forEach(e=>console.error(e.formattedMessage));process.exit(1);}
  const warns=(out.errors||[]).filter(e=>e.severity==='warning');
  return {out, warns};
}

// strip the trailing CBOR metadata, which encodes the source hash and so
// legitimately differs between the original and the flattened file
const strip=h=>{const i=h.lastIndexOf('a264697066735822'); return i<0?h:h.slice(0,i);};

const orig={}; for(const f of fs.readdirSync(SRC)) if(f.endsWith('.sol'))
  orig[f]={content:fs.readFileSync(path.join(SRC,f),'utf8')};
const a=build(orig,true);

const FLAT=SRC+'/flattened';
let allOk=true;
for(const name of fs.readdirSync(FLAT)){
  const src={}; src[name]={content:fs.readFileSync(path.join(FLAT,name),'utf8')};
  const b=build(src,false);          // no import resolver: proves it is self-contained
  const key=name.replace('.sol','');
  const A=strip(a.out.contracts[name][key].evm.deployedBytecode.object);
  const B=strip(b.out.contracts[name][key].evm.deployedBytecode.object);
  const ok=A===B;
  allOk=allOk&&ok;
  console.log(`  ${ok?'PASS':'FAIL'}  ${key}: flattened bytecode ${ok?'identical to':'DIFFERS from'} the original (${A.length/2} bytes)`);
  const w=b.warns.filter(x=>!/SPDX|pragma/i.test(x.message));
  if(w.length) w.forEach(x=>console.log('        WARN '+x.formattedMessage.split('\n')[0]));
}
console.log(allOk?'\nFlattened contracts compile standalone and match.':'\nMISMATCH');
process.exit(allOk?0:1);

/**
 * Cross-checks epoch-builder.html against the Python implementation.
 *
 * The builder reimplements keccak-256, EIP-55 checksumming and the Merkle
 * tree in the browser. The Python versions are what the contract suite
 * exercises against a real EVM, so agreeing with them is what makes a root
 * built here safe to publish on-chain. A root that differs by one byte pays
 * nobody, and cannot be corrected once published.
 *
 *   python cpu_token/web/make_builder_vectors.py > /tmp/bv.json
 *   node cpu_token/web/test_epoch_builder.js /tmp/bv.json
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const vectorPath = process.argv[2];
if (!vectorPath) {
  console.error("usage: node test_epoch_builder.js <vectors.json>");
  process.exit(2);
}

// Load the encoder out of the shipped page, not a copy of it.
const html = fs.readFileSync(path.join(__dirname, "epoch-builder.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const sandbox = { module: { exports: {} }, console, TextEncoder, URL, Blob };
sandbox.window = undefined;
vm.createContext(sandbox);
vm.runInContext(script, sandbox);
const B = sandbox.module.exports;

const V = JSON.parse(fs.readFileSync(vectorPath, "utf8"));
let pass = 0, fail = 0;
const check = (name, ok, extra) => {
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "\n        " + extra}`);
  ok ? pass++ : fail++;
};

console.log("\nkeccak-256 vs eth_utils.keccak:");
for (const c of V.keccak) {
  const got = B.toHex(B.keccak256(B.fromHex(c.hex)));
  check(`${c.hex.length / 2} bytes`, got === c.expected, `exp ${c.expected}\n        got ${got}`);
}

console.log("\nEIP-55 checksum vs eth_utils.to_checksum_address:");
let csOk = 0;
for (const c of V.checksum) {
  if (B.checksumAddress(c.input) === c.expected) csOk++;
  else check(`checksum ${c.input}`, false, `exp ${c.expected}`);
}
check(`${csOk}/${V.checksum.length} addresses checksum identically`, csOk === V.checksum.length, "");

console.log("\nEpoch splits and Merkle roots vs the Python builder:");
for (const e of V.epochs) {
  const split = B.computeSplit(e.holders, BigInt(e.total), e.excluded, 0);
  const tree = B.buildClaims(split.payouts.map((p) => [p[0], p[1]]));

  const label = `${e.expected_claims.length} holder(s)`;
  check(`${label}: root matches`, tree.root === e.expected_root,
    `exp ${e.expected_root}\n        got ${tree.root}`);
  check(`${label}: allocated matches`, split.allocated.toString() === e.expected_allocated,
    `exp ${e.expected_allocated}\n        got ${split.allocated}`);
  check(`${label}: claim count matches`, tree.claims.length === e.expected_claims.length,
    `exp ${e.expected_claims.length}, got ${tree.claims.length}`);

  let same = true, why = "";
  for (let i = 0; i < e.expected_claims.length; i++) {
    const a = tree.claims[i], b = e.expected_claims[i];
    if (!a) { same = false; why = `missing claim ${i}`; break; }
    if (a.index !== b.index) { same = false; why = `index ${i}: ${a.index} vs ${b.index}`; break; }
    if (a.account !== b.account) { same = false; why = `account ${i}: ${a.account} vs ${b.account}`; break; }
    if (a.amount !== b.amount) { same = false; why = `amount ${i}: ${a.amount} vs ${b.amount}`; break; }
    if (JSON.stringify(a.proof) !== JSON.stringify(b.proof)) {
      same = false; why = `proof ${i} differs`; break;
    }
  }
  check(`${label}: every claim and proof identical`, same, why);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

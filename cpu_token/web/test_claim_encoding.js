/**
 * Verifies claim.html's hand-rolled ABI encoding against reference vectors
 * produced by Python's eth_abi.
 *
 * The page encodes calldata itself rather than pulling in a library, so this
 * is what stands in for trusting one. A mismatch here means a holder's claim
 * would revert, or worse, encode different arguments than it displays.
 *
 *   python cpu_token/web/make_vectors.py > /tmp/vectors.json
 *   node cpu_token/web/test_claim_encoding.js /tmp/vectors.json
 */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const vectorPath = process.argv[2];
if (!vectorPath) {
  console.error("usage: node test_claim_encoding.js <vectors.json>");
  process.exit(2);
}

// Pull the encoder out of the page itself, so this tests the shipped code
// rather than a copy that can drift away from it.
const html = fs.readFileSync(path.join(__dirname, "claim.html"), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const sandbox = { module: { exports: {} }, console };
sandbox.window = undefined;
vm.createContext(sandbox);
vm.runInContext(script, sandbox);
const { encodeClaim, encodeIsClaimed } = sandbox.module.exports;

const vectors = JSON.parse(fs.readFileSync(vectorPath, "utf8"));
let pass = 0, fail = 0;

for (const v of vectors.claim) {
  const got = encodeClaim(v.epochId, v.index, v.account, v.amount, v.proof);
  const ok = got.toLowerCase() === v.expected.toLowerCase();
  console.log(`  ${ok ? "PASS" : "FAIL"}  claim, ${v.proof.length} proof node(s)`);
  if (!ok) { console.log(`        expected ${v.expected}\n        got      ${got}`); fail++; }
  else pass++;
}

const iv = vectors.isClaimed;
const gotIs = encodeIsClaimed(iv.epochId, iv.index);
const okIs = gotIs.toLowerCase() === iv.expected.toLowerCase();
console.log(`  ${okIs ? "PASS" : "FAIL"}  isClaimed`);
okIs ? pass++ : fail++;

// Malformed input must throw rather than silently encode something wrong.
const rejects = [
  ["short address", () => encodeClaim(0, 0, "0x1234", 1, [])],
  ["bad proof node", () => encodeClaim(0, 0, "0x" + "11".repeat(20), 1, ["0xdead"])],
  ["oversized uint", () => encodeClaim(0, 0, "0x" + "11".repeat(20), 2n ** 256n, [])],
];
for (const [name, fn] of rejects) {
  let threw = false;
  try { fn(); } catch (e) { threw = true; }
  console.log(`  ${threw ? "PASS" : "FAIL"}  rejects ${name}`);
  threw ? pass++ : fail++;
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);

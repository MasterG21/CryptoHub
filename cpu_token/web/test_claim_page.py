"""Drives claim.html in Chromium against a mock wallet and a real epoch file.

Holders use this page to move real money, so the checks that matter most
are that the transaction goes to the distributor, and that the encoded
recipient and amount are the holder's own — not the sender's, and not
whatever the page happens to be displaying.

    pip install playwright && playwright install chromium
    python cpu_token/web/test_claim_page.py
"""
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))
from merkle import build_claims
from playwright.sync_api import sync_playwright

ALICE = "0x1111111111111111111111111111111111111111"
BOB   = "0x2222222222222222222222222222222222222222"
CAROL = "0x3333333333333333333333333333333333333333"
DIST  = "0x4444444444444444444444444444444444444444"

root, claims = build_claims([(ALICE, 600 * 10**18), (BOB, 300 * 10**18)])
epoch = {
    "generated_at": "2026-09-07T12:00:00+00:00",
    "merkle_root": "0x" + root.hex(), "holder_count": 2,
    "epoch_id": 3, "distributor": DIST,
    "reward_token": "0xcdf2f3e0fa43c47a6662a91c9e4a7c5f69762699",
    "reward_symbol": "MUB", "reward_decimals": 18,
    "claims": claims,
}

WALLET = """
window.__sent = [];
window.__calls = [];
window.ethereum = {
  request: async function(req){
    if(req.method === "eth_requestAccounts") return [window.__account];
    if(req.method === "eth_chainId") return window.__chainId;
    if(req.method === "wallet_switchEthereumChain"){ window.__chainId = "0x38"; return null; }
    if(req.method === "eth_call"){ window.__calls.push(req.params[0]); return window.__claimed; }
    if(req.method === "eth_sendTransaction"){ window.__sent.push(req.params[0]); return "0x" + "ab".repeat(32); }
    throw new Error("unexpected " + req.method);
  }
};
"""

results = []
def check(name, cond, extra=""):
    results.append((name, cond))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{'' if cond else ' :: ' + str(extra)}")

with sync_playwright() as pw:
    launch_opts = {"executable_path": os.environ["CHROMIUM"]} if os.environ.get("CHROMIUM") else {}
    b = pw.chromium.launch(**launch_opts)

    def open_page(account, chain="0x38", claimed="0x"+"0"*64):
        pg = b.new_page(viewport={"width":390,"height":844})
        pg.add_init_script(WALLET)
        pg.add_init_script(f'window.__account={json.dumps(account)};'
                           f'window.__chainId={json.dumps(chain)};'
                           f'window.__claimed={json.dumps(claimed)};')
        pg.route("**/epoch.json", lambda r: r.fulfill(
            status=200, content_type="application/json", body=json.dumps(epoch)))
        pg.goto("file://" + os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "claim.html"))
        pg.wait_for_timeout(500)
        return pg

    # --- eligible holder claims ---
    pg = open_page(ALICE)
    check("epoch loads and card shows", pg.is_visible("#epochCard"))
    check("distributor shown", DIST[:8].lower() in pg.inner_text("#e-dist").lower(),
          pg.inner_text("#e-dist"))
    pg.click("#connect"); pg.wait_for_timeout(500)
    check("amount formatted from base units", pg.inner_text("#amount") == "600",
          pg.inner_text("#amount"))
    check("reward symbol shown", pg.inner_text("#sym") == "MUB", pg.inner_text("#sym"))
    check("status ready", "ready" in pg.inner_text("#status"), pg.inner_text("#status"))
    check("isClaimed was read", len(pg.evaluate("window.__calls")) == 1)

    pg.click("#claim"); pg.wait_for_timeout(500)
    sent = pg.evaluate("window.__sent")
    check("exactly one transaction sent", len(sent) == 1)
    if sent:
        tx = sent[0]
        check("tx goes to the distributor", tx["to"].lower() == DIST.lower(), tx["to"])
        check("tx from the connected account", tx["from"].lower() == ALICE.lower())
        check("calldata uses the claim selector", tx["data"].startswith("0x5d4df3bf"),
              tx["data"][:12])
        # The encoded account must be Alice, not whoever sent it.
        encoded_account = tx["data"][10 + 128 : 10 + 192]
        check("encoded recipient is the holder",
              encoded_account.endswith(ALICE[2:].lower()), encoded_account)
        encoded_amount = int(tx["data"][10 + 192 : 10 + 256], 16)
        check("encoded amount matches the epoch file", encoded_amount == 600 * 10**18,
              encoded_amount)
    check("success message shown", "Claim sent" in pg.inner_text("#msg"), pg.inner_text("#msg"))
    pg.close()

    # --- address not in the snapshot ---
    pg = open_page(CAROL)
    pg.click("#connect"); pg.wait_for_timeout(500)
    check("unlisted address shows zero", pg.inner_text("#amount") == "0")
    check("unlisted address gets an explanation",
          "isn't in this epoch" in pg.inner_text("#msg"), pg.inner_text("#msg"))
    check("no claim button for unlisted address", not pg.is_visible("#claim"))
    check("nothing sent for unlisted address", pg.evaluate("window.__sent") == [])
    pg.close()

    # --- already claimed ---
    pg = open_page(BOB, claimed="0x" + "0"*63 + "1")
    pg.click("#connect"); pg.wait_for_timeout(500)
    check("already-claimed detected", "already claimed" in pg.inner_text("#status"),
          pg.inner_text("#status"))
    check("no claim button when already claimed", not pg.is_visible("#claim"))
    pg.close()

    # --- wrong network ---
    pg = open_page(ALICE, chain="0x1")
    pg.click("#connect"); pg.wait_for_timeout(500)
    check("wrong network offers a switch", pg.is_visible("#switch"))
    check("wrong network sends nothing", pg.evaluate("window.__sent") == [])
    pg.click("#switch"); pg.wait_for_timeout(500)
    check("after switching, claim becomes available", pg.is_visible("#claim"))
    pg.screenshot(path="/tmp/claude-0/-home-user-CryptoHub/191f7ea0-d965-5371-bc1e-83a132180b07/scratchpad/claim.png", full_page=True)
    pg.close()
    b.close()

failed = [n for n, ok in results if not ok]
print(f"\n{len(results)-len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)

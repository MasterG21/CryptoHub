"""Drives epoch-builder.html in a browser: guards, then a real build.

The cross-check suites prove the arithmetic. This proves the form around
it — that a missing exclusion or a too-short claim window is refused
before anything is built, and that a fractional reward amount does not go
through a float on its way to base units.

    python cpu_token/web/test_epoch_builder_ui.py
"""
import os

from playwright.sync_api import sync_playwright
R=[]
def ck(n,c,e=""):
    R.append((n,c)); print(f"  {'PASS' if c else 'FAIL'}  {n}{'' if c else ' :: '+str(e)}")
A=lambda n: "0x"+f"{n:040x}"
with sync_playwright() as pw:
    b=pw.chromium.launch(**({"executable_path":os.environ["CHROMIUM"]}
                         if os.environ.get("CHROMIUM") else {}))
    pg=b.new_page(viewport={"width":700,"height":950})
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("file://" + os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "epoch-builder.html"))
    pg.wait_for_timeout(300)

    # guard: no exclusions
    pg.fill("#token", A(1)); pg.fill("#dist", A(2)); pg.fill("#amount","50")
    pg.fill("#holders", f"{A(10)},1000000000000000000")
    pg.click("#build"); pg.wait_for_timeout(300)
    ck("refuses to build with no exclusions", "exclusions" in pg.inner_text("#msg"), pg.inner_text("#msg"))

    # guard: short claim window
    pg.fill("#exclude", A(99)); pg.fill("#days","10")
    pg.click("#build"); pg.wait_for_timeout(300)
    ck("rejects a claim window under 30 days", "30 days" in pg.inner_text("#msg"), pg.inner_text("#msg"))
    pg.fill("#days","60")

    # guard: malformed holder line
    pg.fill("#holders", "not-an-address,123")
    pg.click("#build"); pg.wait_for_timeout(300)
    ck("rejects a malformed holder line", "isn't 'address,balance'" in pg.inner_text("#msg"), pg.inner_text("#msg"))

    # real build
    pg.fill("#holders", "\n".join([f"{A(10)},700000000000000000000",
                                   f"{A(11)},200000000000000000000",
                                   f"{A(12)},100000000000000000000",
                                   f"{A(99)},500000000000000000000"]))
    pg.click("#build"); pg.wait_for_timeout(800)
    ck("results appear", pg.is_visible("#results"))
    ck("excluded address is not paid", pg.inner_text("#r-count")=="3", pg.inner_text("#r-count"))
    root=pg.inner_text("#o-root")
    ck("root is a 32-byte hex value", root.startswith("0x") and len(root)==66, root)
    ck("allocated equals the full 50 tokens",
       pg.inner_text("#o-amount")=="50000000000000000000", pg.inner_text("#o-amount"))
    ck("claim window in seconds", pg.inner_text("#o-window")=="5184000", pg.inner_text("#o-window"))
    ck("epoch json carries the claims", '"claims"' in pg.inner_text("#o-json"))
    ck("largest payout listed first", "35" in pg.inner_text("#top"), pg.inner_text("#top")[:80])
    ck("no page errors", not errs, errs)

    # decimal amount
    pg.fill("#amount","12.5"); pg.click("#build"); pg.wait_for_timeout(600)
    ck("fractional amounts parse without float error",
       pg.inner_text("#o-amount")=="12500000000000000000", pg.inner_text("#o-amount"))
    b.close()
f=[n for n,c in R if not c]
print(f"\n{len(R)-len(f)} passed, {len(f)} failed")
raise SystemExit(1 if f else 0)

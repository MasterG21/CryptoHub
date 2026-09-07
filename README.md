# CryptoHub

Two tools that work together:

- **`trading_desk`** — an autonomous memecoin trading desk for Solana, BNB Chain and
  Robinhood Chain. Paper trading by default.
- **`robinhood_meme_scan`** — the contract-level rug-risk screen the desk uses as its
  safety gate on Robinhood Chain, also usable on its own.

---

## trading_desk

An autonomous desk that discovers new memecoin pools, screens them for traps, scores
what is left for momentum, sizes positions against a stop, and manages exits — on a
loop, unattended.

**It runs in paper mode by default and that is the only mode wired end to end.** Live
order submission needs a signer you write and inject yourself; see
[Going live](#going-live).

### Start here: what the target actually costs

If you point this at $100 with a $1,000,000 target, run `plan` before anything else.
It does the arithmetic rather than the marketing:

```bash
python -m trading_desk plan
```

With the shipped defaults and the shipped assumed trade distribution, it reports:

| | |
|---|---|
| Required return | 10,000x |
| Configured risk per trade | 2.00% |
| Growth-optimal risk (full Kelly) | 0.33% |
| Expected log growth per trade | **negative** |
| Monte Carlo: reached $1M | ~0% |
| Monte Carlo: account dies | ~97% |

Three findings drive that, and none of them are a bug:

1. **Positive expectancy is not enough.** The default distribution has a genuinely
   positive edge (+0.028R per trade) and still compounds *downward* at 2% risk,
   because equity grows at `E[ln(1 + f·R)]`, not at the arithmetic mean. Bet past the
   growth-optimal fraction and you lose growth and gain ruin at the same time.
2. **A $100 account cannot bet small enough.** Risking 0.33% across a 30% stop is a
   $1 position — under the minimum that gas makes worth placing. You would need about
   $451 of equity before the smallest tradeable position stops being an overbet.
3. **Below $75 the desk cannot trade at all.** At 2% risk and a 30% stop, a $5
   minimum position needs $75 of equity behind it. A $100 account therefore has 25%
   of drawdown before it is finished — not because it went to zero, but because it
   can no longer place a valid order. Most simulated runs end exactly there.

`plan` also prints a tail-sensitivity table, because one unknowable number decides the
whole thing: how big the rare runner is. At a 10R best case the strategy is negative
at any size; at 25R and up it turns positive. Nobody knows that number in advance,
which is the honest summary of this trade.

None of this stops the desk from running. It is here so the numbers are visible before
real money is, rather than after.

### Usage

```bash
pip install -r requirements.txt

python -m trading_desk plan                      # the math above
python -m trading_desk doctor                    # config + connectivity check
python -m trading_desk scan                      # one screening pass, no trading
python -m trading_desk run --ticks 20            # the loop, paper mode
python -m trading_desk status                    # portfolio and performance
python -m trading_desk panic                     # flatten every position now
```

Configuration is a JSON file (see `desk.config.example.json`), with environment
overrides for the things you change often:

```bash
python -m trading_desk -c desk.config.example.json run
DESK_RISK_PER_TRADE=0.01 DESK_CHAINS=solana python -m trading_desk run
```

A misspelled config key is reported rather than silently ignored — quietly falling back
to a 2% default when you wrote `risk_per_trade` instead of `risk_per_trade_pct` is the
kind of typo that costs an account.

### How a tick works

Every poll interval, in this order:

1. **Refresh** quotes for open positions. A stale mark is a broken stop.
2. **Exit** anything that has hit a rule — this runs *before* entries and *even while
   halted*, because a circuit breaker must never trap the desk in a losing position.
3. **Check the kill switches** (daily loss limit, losing streak, equity floor). If one
   has tripped, the tick ends here and nothing new is opened.
4. **Discover** candidates, run the safety gate, score the survivors.
5. **Size and enter** the best of them, up to capacity.
6. **Snapshot** equity and persist everything to SQLite.

A failure in one chain, one feed or one token cannot stop the others; failures are
collected and reported, not swallowed.

### The safety gate

Runs before any scoring, and is the harshest layer in the system. Its job is not to
find winners — it is to refuse tokens whose structure means you may not be able to sell
at all:

- pool depth below a floor, or unknown
- **unknown is not OK** — a missing liquidity number is a fact the desk could not
  establish, and it does not put money behind those
- pools too new (still in the launch-sniping window) or too old (the move is over)
- market cap resting on a sliver of real float
- volume far beyond what the pool's depth can support (wash trading)
- **sell starvation** — near-100% buys with almost no sells, the honeypot signature of
  a token whose sells revert
- on Robinhood Chain, the full `robinhood_meme_scan` contract screen, gated on score

### Sizing and exits

Position size is the **smallest** of four independent caps: the risk budget
(equity × risk% ÷ stop distance), a per-position cap, available cash net of reserve,
and a cap on order size versus pool depth. That last one usually binds, and it is the
one that matters — on a thin pool you are not a price taker, you are the price.

Exits, in order of urgency: liquidity drain (the only condition where exiting may stop
being *possible*), hard stop, trailing stop once the trade has earned one, a scale-out
ladder that moves the stop to breakeven after the first tranche, momentum death, and a
time stop for capital that is not working. After any full close, a cooldown blocks
re-entering the same token — without it a stop-out and a re-buy land in the same tick,
because the momentum fields still look strong the instant after a token drops through
its stop.

### What is real and what is modelled

**Paper fills charge every real cost.** Price impact is derived from the constant-product
invariant using the pool's own depth (buying `d` dollars from a pool with `Q` on the
quote side fills at `spot × (1 + d/Q)`), plus DEX fee, plus chain gas. Buys and sells
are asymmetric because the maths is. `--failure-rate` simulates transactions that never
land. This is deliberately pessimistic: a paper result that ignores impact is the main
reason memecoin strategies look profitable and are not.

Concentrated-liquidity pools are deeper than this model near spot and much shallower
outside the active range, so treat the numbers as a well-founded approximation rather
than a quote.

### Chain coverage

| Chain | Source | Price | Depth | Volume / txn counts | Momentum |
|---|---|---|---|---|---|
| Solana | DexScreener | ✅ | ✅ | ✅ | from the feed |
| BNB Chain | DexScreener | ✅ | ✅ | ✅ | from the feed |
| Robinhood Chain | Blockscout + RPC | via V3 `slot0` | pool reserves | ❌ none published | **observed locally** |

Robinhood Chain is new enough that no aggregator publishes rolling windows for it, so
the desk records what it sees on each poll and derives the windows itself. Two
consequences: it needs `--v3-factory`, `--weth` and `--native-usd` before it can price
anything at all (and skips the chain loudly otherwise, rather than guessing), and a
token there is not tradeable until the desk has watched it long enough to measure a
real change. Volume and buy/sell counts stay `None` rather than being invented, and the
safety gate falls back to observed price movement as its proof that trades are happening.

### Going live

Live trading is fully wired: routing through Jupiter on Solana and a 0x-compatible
endpoint on BNB Chain, and signing through `trading_desk/execution/signers.py`
(`SolanaSigner`, `EvmSigner`, `MultiChainSigner`).

**None of this code has ever run against a mainnet RPC.** It was written in an
environment with no route to any chain, aggregator or explorer. It is careful and
unit-tested where testable; that is not the same as proven. Treat your first live
session as a test with real money.

#### Deployment

Run it on your own machine — not on a laptop that sleeps, and not in an ephemeral
container. A VPS or a always-on box.

```bash
git clone https://github.com/MasterG21/CryptoHub.git && cd CryptoHub
pip install -r requirements.txt -r requirements-live.txt

# 1. Prove the plumbing works with no money involved.
python -m trading_desk doctor
python -m trading_desk scan                 # do real pairs come back?
python -m trading_desk run --ticks 60       # paper, ~1 hour

# 2. Keys, from the environment only. Never in a file, never committed.
export DESK_SOLANA_PRIVATE_KEY='...'        # base58, or a JSON byte array
export DESK_EVM_PRIVATE_KEY='0x...'

# 3. Live, but not armed: builds and simulates real orders, broadcasts nothing.
python -m trading_desk -c desk.config.json run --live

# 4. Armed. Real, irreversible transactions.
python -m trading_desk -c desk.config.json run --live --arm --max-order-usd 10
```

Step 3 is not optional. It exercises the whole live path — routing, decimals,
allowances, simulation — against the real chain, and the only thing it does not do is
broadcast. If anything is going to be wrong, it is wrong there, for free.

#### The switches

Four independent things must all be true before a transaction is broadcast, so that no
single typo can turn a simulation into real orders:

| | |
|---|---|
| `execution.mode = "live"` | config file, or `--live` |
| `execution.allow_live_trading = true` | **config file only** — no CLI flag exists |
| A key in the environment | `DESK_SOLANA_PRIVATE_KEY` / `DESK_EVM_PRIVATE_KEY` |
| `--arm` | otherwise every order is simulated and dropped |

`python -m trading_desk doctor` lists whichever are still missing. Without all four,
orders raise `LiveTradingUnavailable`, loudly, with nothing sent.

#### What the signers do for you

- **Simulate before sending.** A transaction that reverts in simulation is never
  broadcast — on Solana via `simulateTransaction`, on EVM via `eth_call`.
- **Cap order size independently.** `--max-order-usd` is enforced inside the signer,
  below the desk's own risk layer, so an upstream bug cannot produce a large order.
- **Approve exactly, on sells only.** An EVM sell needs an ERC-20 allowance for the
  router first — skipping it leaves a position that cannot be exited. The approval is
  written for the exact amount, never unlimited: an infinite approval left sitting on a
  memecoin router is a standing invitation to drain the wallet later.
- **Resolve decimals on-chain.** Order sizes convert to raw integer units, and a wrong
  decimals value misprices an order by powers of ten. There is no default — an order
  whose decimals cannot be read is refused.
- **Keep keys out of everything.** Environment only. Redacted from every repr; error
  messages never quote key material.

#### Use a burner wallet

Fund it with only what the desk is allowed to lose. It holds hot keys on a running
server, it approves arbitrary memecoin contracts, and it is driven by code that has
never been tested against a live chain. Do not point it at a wallet holding anything
you care about.

### Persistence

Everything lands in SQLite: every fill, every closed trade, an equity point per tick,
the open book, the risk counters and the re-entry cooldown. The desk can die mid-session
and come back holding the same positions and the same daily loss counter — a bot that
forgets it is down 20% today because it was restarted has no daily loss limit at all.

### Tests

```bash
python -m pytest tests/
```

221 tests, no network: the feeds are replaced at their seams with canned responses
shaped like the real APIs. That includes end-to-end ticks of the desk — entries, stops,
scale-outs, halts, restarts, feed outages — and the signer rails: caps, key redaction,
approval handling, and the guarantee that a dry run broadcasts nothing.

### Honest limitations

- **The live path has never executed a real trade**, and the broadcast step cannot be
  unit-tested. Everything around it is: caps, key handling, approvals, and that a dry
  run sends nothing. Run unarmed against the real chain first — see
  [Going live](#going-live).
- **The client code has never met the real APIs.** This environment cannot reach
  DexScreener, Blockscout or any RPC, so field handling is written defensively
  (degrade to "unknown" rather than guess) but is unverified against live responses.
  Run `scan` against the real network before trusting it.
- **The assumed trade distribution is an assumption**, not a measurement. Replace it
  with your own realised results via `TradeDistribution.from_trades` once the desk has
  traded enough to have them.
- **The safety gate screens structure, not intent.** It can tell you a contract *can*
  be used against holders. It cannot tell you a token will go up, and a token can pass
  every check here and still go to zero.
- **Autonomous memecoin trading is a way to lose money quickly and automatically.**
  This is software, not investment advice.

---

## robinhood_meme_scan

A CLI heuristic health-check for ERC-20 meme coins on [Robinhood Chain](https://chain.robinhood.com)
(an Arbitrum Orbit L2 settling to Ethereum). Given a token contract address, it pulls data from
Blockscout (Robinhood Chain's explorer) and, optionally, directly from the chain via RPC, then
scores the token against a set of rug-risk patterns.

**This is a heuristic screen, not a security audit.** A high score does not mean a token is safe,
and this is not investment advice — always verify anything material yourself before acting on it.

### Setup

```bash
pip install -r requirements.txt
```

### Usage

One address gives a detailed report:

```bash
python -m robinhood_meme_scan 0xTokenContractAddress
```

Several addresses give a table ranked by score, best first — this is the useful mode when
triaging a launchpad listing:

```bash
python -m robinhood_meme_scan 0xAaa... 0xBbb... 0xCcc...

# or from a file, one address per line ('#' comments allowed)
python -m robinhood_meme_scan -f addresses.txt

# machine-readable
python -m robinhood_meme_scan -f addresses.txt --json
```

One address failing (not a token, typo, unreachable) does not sink the batch — it is
reported separately under "Could not screen".

By default this checks:
- Whether the contract source is verified on Blockscout, and (if verified) scans for `mint`,
  `blacklist`, `pause`, and similar privileged functions
- Holder count and concentration (top holder / top 10 holders, as a % of supply)
- Contract age
- Whether `owner()` has been renounced (for `Ownable` contracts)
- The deployer wallet, and how many other tokens it has launched — a long tail of prior
  launches is the serial-launcher pattern. Disable with `--no-deployer-check` (saves two
  API calls per token).

### What this does and does not tell you

It screens for whether a contract **can be used against holders** — mint functions, admin
levers, supply concentrated in one wallet, missing liquidity. Those are verifiable facts.

It says nothing about whether a token's price will go up. Memecoin returns are driven by
attention and reflexivity, which are not readable from a contract. A token can pass every
check here and still go to zero. Use it to eliminate traps, not to pick winners.

Liquidity-pool verification (does a Uniswap V3 pool for `token/WETH` actually exist and hold
tokens) is **off by default**, because it needs the Uniswap V3 factory and WETH addresses for
Robinhood Chain, and guessing those wrong would silently produce a false "no liquidity" result —
worse than not checking. Once you've confirmed them on Blockscout, enable it with:

```bash
python -m robinhood_meme_scan 0xTokenContractAddress \
  --v3-factory 0xFactoryAddress \
  --weth 0xWrappedEthAddress
```

### Options

| Flag | Default | Purpose |
|---|---|---|
| `--rpc-url` | `https://rpc.mainnet.chain.robinhood.com` | Robinhood Chain JSON-RPC endpoint |
| `--explorer-api` | `https://robinhoodchain.blockscout.com/api/v2` | Blockscout v2 API base |
| `--v3-factory` | none (check skipped) | Uniswap V3 factory address on this chain |
| `--weth` | none (check skipped) | Wrapped ETH token address on this chain |
| `-f`, `--addresses-file` | none | File of addresses, one per line |
| `--json` | off | Emit JSON instead of a table |
| `--no-deployer-check` | off | Skip the deployer / serial-launcher lookup |

### Tests

The scoring logic is unit-tested with mocked data (no network needed):

```bash
python -m pytest tests/
```

The Blockscout/RPC client code itself talks to live endpoints and wasn't exercised against the
real network while writing it — this development environment's outbound network policy blocks
`robinhoodchain.blockscout.com` and `rpc.mainnet.chain.robinhood.com`. Field names in Blockscout's
v2 API can vary slightly by deployment, so the client code degrades to "unknown" rather than
guessing when an expected field is missing — but run it against a real token before trusting it
end to end.

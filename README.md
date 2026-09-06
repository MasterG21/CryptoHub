# CryptoHub

## robinhood_meme_scan

A CLI heuristic health-check for meme coins on [Robinhood Chain](https://chain.robinhood.com)
(an Arbitrum Orbit L2 settling to Ethereum) and on [BNB Smart Chain](https://www.bnbchain.org).
Given a token contract address, it pulls data from Blockscout and, optionally, directly from the
chain via RPC, then scores the token against a set of rug-risk patterns.

**This is a heuristic screen, not a security audit.** A high score does not mean a token is safe,
and this is not investment advice — always verify anything material yourself before acting on it.

### Setup

```bash
pip install -r requirements.txt
```

### Chains

Pick a chain with `--chain`; everything else (explorer, RPC, DEX factory, fee tiers) follows
from the preset. Robinhood Chain stays the default, so existing invocations are unchanged.

```bash
python -m robinhood_meme_scan --list-chains          # show the presets
python -m robinhood_meme_scan --chain bsc 0xToken    # 'bnb' and 'binance' also work
```

| Chain | `--chain` | Explorer | Liquidity check |
|---|---|---|---|
| Robinhood Chain | `robinhood` (default) | `robinhoodchain.blockscout.com` | off — factory address unconfirmed |
| BNB Smart Chain | `bsc` / `bnb` / `binance` | `bnb.blockscout.com` | PancakeSwap V3 vs WBNB |

Any preset value can be overridden per-run with `--explorer-api`, `--rpc-url`, `--v3-factory`,
`--quote-token`, or `--fee-tiers` — useful for a chain with no preset yet, or a private RPC.

Note that PancakeSwap V3's fee tiers (0.01% / 0.05% / **0.25%** / 1%) differ from Uniswap V3's
(0.01% / 0.05% / **0.3%** / 1%). Probing Uniswap's tiers on BSC would miss most real pools and
report them as having no liquidity, so each chain carries its own tier list.

### Usage

One address gives a detailed report:

```bash
python -m robinhood_meme_scan 0xTokenContractAddress
python -m robinhood_meme_scan --chain bsc 0xTokenContractAddress
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

### Screening your own launch

The checks here are the same ones buyers (and screener bots) run against *your* token, so it is
worth pointing the tool at your own contract right after launching — on a launchpad or otherwise:

```bash
python -m robinhood_meme_scan --chain bsc 0xYourNewToken
```

What each flag means for a token you just launched:

| Flag | What to do about it |
|---|---|
| `unverified-contract` (-30) | Get the source verified on the explorer. This is the single biggest deduction and the first thing buyers check. |
| `owner-can-mint-new-supply` (-25) | A mint function means you can dilute holders. Launch without one; if it's already deployed, renouncing ownership is the only fix. |
| `can-blacklist-wallets` (-20) | Same story — a freeze lever reads as a honeypot regardless of intent. |
| `holder-concentration` (-10/-20) | Don't hold >10% of supply in one wallet. Split, lock, or burn the remainder. |
| `no-liquidity-pool` / `empty-liquidity-pool` (-15) | Confirm the pool exists and actually holds tokens. Locking LP is the norm; this tool doesn't check locks. |
| `owner-not-renounced` (-10) | Renounce once you no longer need admin functions. |
| `very-new-contract` (-10) | Unavoidable and temporary — it decays after 24h. |
| `low-holder-count` (-10) | Also temporary; it reflects distribution, not the contract. |

Tokens created through a launchpad are all deployed by the platform's factory contract, which has
legitimately deployed hundreds. The deployer check detects that and skips the serial-launcher
deduction, so a launchpad token isn't penalised for it.

None of this makes a launch succeed. It removes the structural reasons people bounce off a token
in the first ten seconds — which is a precondition for attention, not a substitute for it.

#### Liquidity-pool verification

A wrong factory address would make *every* token look like it has no liquidity pool — a false
accusation from a tool people use to judge rug risk. So before probing, the check confirms there
is contract code at the configured factory and quote-token addresses, and reports **"not checked"**
rather than "no pool" when there isn't. That failure mode is what makes shipping preset addresses
safe: a stale or wrong preset degrades to *unknown*, never to a deduction against the token.

On BSC the check runs by default against the published PancakeSwap V3 factory and WBNB. Those
addresses could not be confirmed against the live chain from this repo's development environment
(its network policy blocks BSC RPC and explorer endpoints), so confirm them on
[BscScan](https://bscscan.com) before treating a liquidity result as authoritative.

On Robinhood Chain the factory and WETH addresses are still unconfirmed, so the check stays off
until you pass them:

```bash
python -m robinhood_meme_scan 0xTokenContractAddress \
  --v3-factory 0xFactoryAddress \
  --quote-token 0xWrappedEthAddress
```

`--weth` is still accepted as an alias for `--quote-token`.

### Options

| Flag | Default | Purpose |
|---|---|---|
| `--chain` | `robinhood` | Chain preset: `robinhood` or `bsc` (`bnb`/`binance` alias to `bsc`) |
| `--list-chains` | – | Print the built-in presets and exit |
| `--rpc-url` | from preset | JSON-RPC endpoint |
| `--explorer-api` | from preset | Blockscout v2 API base |
| `--v3-factory` | from preset | V3 factory address on this chain |
| `--quote-token` (`--weth`) | from preset | Token the pool is paired against (WETH / WBNB) |
| `--fee-tiers` | from preset | Comma-separated V3 fee tiers to probe |
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
`robinhoodchain.blockscout.com`, `rpc.mainnet.chain.robinhood.com`, `bnb.blockscout.com` and the
BSC dataseed RPCs alike. Field names in Blockscout's v2 API can vary slightly by deployment, so
the client code degrades to "unknown" rather than guessing when an expected field is missing —
but run it against a real token before trusting it end to end. The BSC preset in particular
(explorer host, PancakeSwap V3 factory, WBNB) is unconfirmed for that reason.

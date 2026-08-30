# CryptoHub

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

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

```bash
python -m robinhood_meme_scan 0xTokenContractAddress
```

By default this checks:
- Whether the contract source is verified on Blockscout, and (if verified) scans for `mint`,
  `blacklist`, `pause`, and similar privileged functions
- Holder count and concentration (top holder / top 10 holders, as a % of supply)
- Contract age
- Whether `owner()` has been renounced (for `Ownable` contracts)

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

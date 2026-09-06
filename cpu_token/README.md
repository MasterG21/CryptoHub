# Computing Power (CPU)

A fixed-supply BEP-20 for BNB Smart Chain, plus a separate contract that pays holders a
reward token through verifiable Merkle claims.

```
cpu_token/
├── contracts/
│   ├── ComputingPower.sol           # the token: fixed supply, zero admin functions
│   ├── MerkleRewardDistributor.sol  # epoch-based reward claims
│   └── test/MockERC20.sol           # test-only reward token stand-in
├── scripts/
│   ├── merkle.py                    # tree/proof builder, matches MerkleProof.sol
│   ├── build_snapshot.py            # holder snapshot → root + proofs
│   └── test_contracts.py            # deploys to an in-process EVM and tests the flow
├── assets/cpu-logo.svg | cpu-logo-512.png
├── web/index.html                   # landing page
└── TOKEN.md                         # launchpad copy
```

## Read this before you launch

**Paying token holders in a tokenized equity is very probably a securities offering, and
that is not a problem the code can solve.** It is not the technical claim I first assumed
it was — [MUB](https://www.coingecko.com/en/coins/micron-technology-bstocks-tokenized-stock)
is a real BEP-20 on BNB Smart Chain, backed 1:1 by custodied MU shares, and it
[paid a $0.15/token dividend in July 2026](https://en.cryptonomist.ch/2026/07/02/binance-tokenized-stock-dividend/).
The distributor in this directory can hold and pay out any BEP-20, MUB included. The
blocker is legal, not technical:

- **A token whose pitch is "hold this and receive equity distributions" is an investment
  contract** in most jurisdictions — money in, common enterprise, profit expected from the
  operator's efforts. Issuing one to the public generally requires registration or an
  exemption. Get a securities lawyer in your jurisdiction before you launch it publicly.
  This is the one step you cannot substitute code for.
- **bStocks are not available to US persons**, and eligibility is enforced at the
  application layer, not by the token contract. A public token that rewards in MUB will
  reach holders who are not permitted to receive it, and holding CPU exempts nobody.
- **"Micron" is Micron Technology, Inc.'s trademark.** Naming or branding the token around
  it invites a complaint independent of any securities question. `TOKEN.md` keeps the
  branding on compute generally, not on the company.

If you want the compute theme without the legal exposure, point `rewardToken` at an
ordinary BEP-20 — the mechanism is identical and most of the above evaporates.

## The token

`ComputingPower.sol` has no mint, no blacklist, no pause, no transfer fee, and no owner.
Those functions were never written, so they cannot be added later. 1,000,000,000 CPU are
minted once, to the address passed to the constructor.

Screened with this repo's own scanner, it raises no flags at all — every deduction in
`DANGEROUS_FUNCTIONS` corresponds to a function that simply is not there.

If you launch through a launchpad instead, the launchpad's factory deploys its own token
contract and this file is not used. The distributor still works: it takes the token
address as a constructor argument and needs no cooperation from the token.

## Rewards

Each epoch is a snapshot:

1. `build_snapshot.py` reads holder balances, excludes the LP pair, burn addresses and
   treasury, splits the pot pro-rata, and writes a root plus one proof per holder.
2. You approve the reward token and call `openEpoch(root, amount, claimWindow)` — the
   funds move in the same transaction, so an epoch is never live while unfunded.
3. Holders call `claim(...)` with their proof. Payment always goes to the entitled
   address, never to whoever submitted the transaction.
4. After the deadline (minimum 30 days), `sweepUnclaimed` returns the remainder.

What the operator can do: open an epoch, and sweep an expired one. What the operator
cannot do: withdraw funded rewards before the deadline, change a published root, block an
individual claim, or touch the CPU token.

Each epoch's funds are accounted separately, so a mistaken or malicious root can never pay
out more than that epoch was funded with, nor reach another epoch's balance. That property
is covered by a test.

```bash
python cpu_token/scripts/build_snapshot.py 0xCpuToken \
    --amount 1000000000000000000000 \
    --exclude 0xPancakePairAddress \
    --exclude 0xTreasuryAddress \
    --out epoch-001.json
```

The script refuses to run with no exclusions: a liquidity pool holds CPU on behalf of
traders, and paying it sends rewards to a contract where nobody can claim them.

## Build and test

Needs Node (for solc) and Python.

```bash
npm install solc@0.8.24 @openzeppelin/contracts@5.0.2
pip install "web3[tester]"

NODE_MODULES=$PWD/node_modules python cpu_token/scripts/test_contracts.py
```

The suite compiles both contracts, deploys them to an in-process EVM, and exercises the
full flow: claiming, double-claim rejection, forged and redirected proofs, the
over-allocation guard, the claim window floor, and sweeping before and after the deadline.
23 checks, all passing as committed.

## Deploying

Compile with solc 0.8.24, optimizer on, 200 runs — the settings in `scripts/test_contracts.py`,
which are what you must reproduce for source verification to match.

1. Deploy `ComputingPower(treasury)`.
2. Verify the source on BscScan immediately. Unverified source is the single largest
   deduction any screener applies, and the first thing buyers check.
3. Add liquidity, and lock it. Nothing here locks liquidity for you.
4. Deploy `MerkleRewardDistributor(rewardToken, cpuToken, owner)` only when you actually
   intend to run an epoch, and after you have read the legal section above.

Confirm any address you hardcode — the reward token in particular — on
[BscScan](https://bscscan.com) first. This repo's scanner exists because a wrong address
produces a confidently wrong answer.

## Verify before trusting

Screen the deployed token the way anyone else would, rather than grading it on its own
scorecard:

```bash
python -m robinhood_meme_scan --chain bsc 0xYourDeployedToken
```

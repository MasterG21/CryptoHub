# Computing Power (CPU)

A fixed-supply BEP-20 for BNB Smart Chain, plus a separate contract that pays holders a
reward token through verifiable Merkle claims.

```
cpu_token/
├── launch.sh                        # ← start here: one command, end to end
├── launch/
│   ├── launch.py                    # preflight, deploy, post-deploy check
│   ├── run_epoch.py                 # snapshot + fund + publish a reward epoch
│   ├── verify.py                    # explorer verification bundle
│   ├── config.py | config.example.env
│   └── test_launch.py               # 19 checks against an in-process EVM
├── contracts/
│   ├── ComputingPower.sol           # the token: fixed supply, zero admin functions
│   ├── MerkleRewardDistributor.sol  # epoch-based reward claims
│   └── test/MockERC20.sol           # test-only reward token stand-in
├── scripts/
│   ├── compile.py                   # shared solc settings (must match for verification)
│   ├── merkle.py                    # tree/proof builder, matches MerkleProof.sol
│   ├── build_snapshot.py            # holder snapshot → root + proofs
│   └── test_contracts.py            # 23 checks against an in-process EVM
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

## Launching

Read the section above first — it decides whether you should run this at all.

```bash
./cpu_token/launch.sh              # plan only — broadcasts nothing
./cpu_token/launch.sh --confirm    # deploy for real
```

The first run installs solc, OpenZeppelin and web3, writes a `.env` from the
template, and stops so you can fill it in. Then it compiles, runs preflight,
prints the plan, and — only with `--confirm` — deploys, checks the result
on-chain and writes a verification bundle.

**It is dry by default and it defaults to testnet.** Rehearse there first: the
same command, one word different in `.env`, free coins from a faucet. A launch
you have already done once is a very different thing from one you are doing for
the first time with money.

Preflight refuses to broadcast when:

| Check | Why it exists |
|---|---|
| Chain id ≠ the configured network | The worst launch mistake is a wrong RPC putting your token on a chain you did not mean |
| Deployer holds no BNB | Fails immediately with that message rather than a confusing gas-estimation error |
| Balance below estimated cost + 20% | Estimated from the real bytecode, not guessed |
| `REWARD_TOKEN_ADDRESS` has no contract code | A typo'd reward token bricks every claim |
| `TREASURY_ADDRESS` unset or malformed | This address receives the entire supply |

After deploying it re-reads the token from chain and asserts the whole supply
landed at the treasury, so a silent partial failure cannot pass unnoticed.

### Verifying the source

`launch/out/verification/` gets the exact solc standard-JSON input, the
ABI-encoded constructor arguments, and the compiler settings — paste them into
the explorer and they match, because they are the bytes that were deployed.
Set `BSCSCAN_API_KEY` and it will also submit automatically; the bundle is
written first, so a failed submission costs nothing.

### Running a reward epoch

```bash
python cpu_token/launch/run_epoch.py --amount 1000000000000000000000 \
    --exclude 0xPancakePairAddress            # dry run
python cpu_token/launch/run_epoch.py --amount ... --exclude ... --confirm
```

Snapshots holders, builds the tree, prints the split and the largest payouts,
then approves and calls `openEpoch`. Also dry by default — a published root
cannot be changed.

### What it does not do

**It does not add or lock liquidity.** That step moves most of your money in one
transaction and the parameters are yours to choose, so it stays deliberate and
manual. Buyers will look for a lock; not having one is read as intent to rug.

**It cannot press the button for you.** Deploying needs your key and your funds
on your own machine.

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

```bash
npm install solc@0.8.24 @openzeppelin/contracts@5.0.2
pip install "web3[tester]"

NODE_MODULES=$PWD/node_modules python cpu_token/scripts/test_contracts.py   # 23 checks
NODE_MODULES=$PWD/node_modules python cpu_token/launch/test_launch.py       # 19 checks
```

The contract suite compiles both contracts, deploys them to an in-process EVM,
and exercises claiming, double-claim rejection, forged and redirected proofs,
the over-allocation guard, the claim-window floor, and sweeping either side of
the deadline.

The launch suite deploys through the launcher itself and checks that each
preflight guard actually stops a bad launch, that a dry run leaves the chain
untouched, and that the verification bundle's constructor arguments decode back
to the treasury address.

Both pass as committed. Neither has been run against a live BSC node — this
development environment's network policy blocks BSC RPC endpoints — so the first
real run should be on testnet.

## Verify before trusting

Screen the deployed token the way anyone else would, rather than grading it on its own
scorecard:

```bash
python -m robinhood_meme_scan --chain bsc 0xYourDeployedToken
```

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

## Where each file actually goes

Most of this repo is not pasted anywhere. Sorting out which is which saves a
lot of hunting for a box to put it in.

| File | Where it goes | Needed if you launch on a launchpad? |
|---|---|---|
| `contracts/ComputingPower.sol` | Nowhere — it *is* the token, and a launchpad deploys its own instead | **No.** It's the alternative to using one |
| `contracts/flattened/MerkleRewardDistributor.sol` | Pasted into [Remix](https://remix.ethereum.org) and deployed from your wallet | Yes, if you want to pay rewards |
| `web/claim.html` + `epoch.json` | Uploaded to any static host, so holders can claim | Yes, if you want to pay rewards |
| `web/index.html` | Uploaded to any static host — the token's public page | Optional |
| `assets/cpu-logo-512.png` | Uploaded into the launchpad's image field | Yes |
| `TOKEN.md` | Copied into the launchpad's name/ticker/description fields | Yes |
| `launch/`, `scripts/` | Run from a terminal; skip entirely if you used a launchpad | No |

The token and the reward contract are independent. The distributor takes the
token's address as a constructor argument and needs no cooperation from it, so
a launchpad-created CPU works exactly the same as one deployed from here.

### Deploying the distributor without a terminal

`contracts/flattened/` holds single-file versions with the OpenZeppelin
dependencies inlined. `scripts/check_flattened.js` proves they compile with no
import resolver and produce bytecode identical to the originals, so what you
paste is exactly the contract in this repo.

1. Open [remix.ethereum.org](https://remix.ethereum.org) and create a new file.
2. Paste all of `contracts/flattened/MerkleRewardDistributor.sol`.
3. Under **Solidity Compiler**: version **0.8.24**, optimizer **on**, **200**
   runs. These must match or explorer verification will fail later.
4. Under **Deploy & Run**, set Environment to **Injected Provider** so it uses
   your wallet, and check it says BNB Smart Chain.
5. The constructor takes three addresses, in this order:
   `rewardToken_` (the confirmed MUB address), `holdingsToken_` (your CPU
   address from the launchpad), `owner_` (your wallet).
6. Deploy, approve in your wallet, then copy the deployed address — it goes at
   the top of `claim.html`.

Then verify the source on the explorer, using the same compiler settings.

### Running an epoch without a terminal

`web/epoch-builder.html` closes the last gap. Open it in a browser — no server, no
install — and it fetches your holders from the explorer (or takes a pasted list),
works out each share, builds the Merkle tree locally, and hands you the three
values `openEpoch` wants plus the `epoch.json` to publish. Nothing is sent
anywhere and nothing is signed.

1. Open `web/epoch-builder.html`. Fill in the CPU and distributor addresses, the
   reward amount, and the claim window.
2. List the addresses to exclude — at minimum your liquidity pool. It refuses to
   build without them.
3. Fetch or paste holders, then **Build the epoch**. Read the largest payouts.
4. On the explorer: your **reward token → Write Contract → approve**, with the
   distributor as spender and the `totalAmount` shown.
5. Then the **distributor → Write Contract → openEpoch**, pasting `merkleRoot`,
   `totalAmount` and `claimWindow`.
6. Download `epoch.json` and publish it next to `claim.html`.

That is the whole reward cycle with no command line at all.

#### Why this one is worth trusting

It reimplements keccak-256, EIP-55 checksumming and the Merkle tree in the
browser, with no dependencies — for the same reason as the claim page, and
because cdnjs could not be reached from this environment to confirm a library
path even existed. A root is published on-chain and cannot be corrected
afterwards, so agreement with the Python implementation is checked rather than
assumed, at three levels:

```bash
python cpu_token/web/make_builder_vectors.py > /tmp/bv.json
node cpu_token/web/test_epoch_builder.js /tmp/bv.json        # 34 checks
NODE_MODULES=$PWD/node_modules \
  python cpu_token/web/test_browser_epoch_onchain.py         # 8 checks
```

- **keccak-256** against `eth_utils.keccak`, including every message-padding
  boundary (135/136/137 bytes and beyond), where a hand-written implementation
  is most likely to be subtly wrong.
- **Whole epochs** — 1 to 63 holders — against the Python builder: identical
  roots, identical allocations, and every claim and proof identical byte for
  byte.
- **End to end**: an epoch built by the page's own JavaScript is opened on a real
  EVM and claimed by every holder, with a tampered amount still rejected.

That last one is the one that counts. It proves a root this page produces is one
the deployed contract accepts and pays out on.

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

## Paying rewards in tokenized MU (MUB)

This is what the distributor was built for, and it works: bStocks are ordinary
BEP-20 tokens with no on-chain transfer gate — they trade on PancakeSwap and are
used as DeFi collateral — so a contract can hold and pay them out like any other
token. Eligibility is enforced at the application layer, not in the token
contract.

**Confirm the reward token address yourself before funding anything.** MUB is
reported at `0xcdf2f3e0fa43c47a6662a91c9e4a7c5f69762699`, but that came from a
search result, not from the chain: the BSC explorer and RPC endpoints are
blocked from this repo's development environment, so nothing here has read it.
Open it on [BscScan](https://bscscan.com), check the name, symbol and decimals,
and only then put it in `.env`. `run_epoch.py` prints the token's on-chain name
and symbol in the plan for exactly this reason — if it doesn't say Micron, stop.

Two constraints that don't go away because the code works:

- **bStocks are not available to US persons.** A public token that rewards in MUB
  will reach holders who cannot lawfully receive it, and holding CPU exempts
  nobody. Claims from those addresses are your problem to think about, not the
  contract's.
- **Paying holders in a tokenized equity is very probably a securities
  offering.** Settle that with a lawyer in your jurisdiction. No amount of test
  coverage substitutes.

### Running an epoch

1. **Get MUB into the deployer wallet.** Acquire it, then withdraw to your
   self-custody BSC address — the same address as `PRIVATE_KEY` in `.env`.
2. **Set it as the reward token.** Put the confirmed address in
   `REWARD_TOKEN_ADDRESS` and deploy the distributor (`launch.sh --confirm`).
   Already deployed without one? The reward token is immutable, so deploy a
   second distributor; the CPU token is untouched either way.
3. **Dry-run the epoch.** Nothing is broadcast, and you get the exact split:

   ```bash
   python cpu_token/launch/run_epoch.py --amount 50000000000000000000 \
       --exclude 0xYourPancakePair --exclude 0xYourTreasury
   ```

   `--amount` is in base units — MUB has 18 decimals, so the example is 50 MUB.
   Read the largest payouts and the token name before going further.
4. **Open it.** Add `--confirm`. This approves the distributor and calls
   `openEpoch` in two transactions, funding the epoch as it opens.
5. **Publish `epoch.json`** next to `claim.html` so holders can claim.

### The claim page

`web/claim.html` is what holders actually use: they connect a wallet, it finds
their proof in `epoch.json`, and one transaction pays them. Set `distributor`
and `epochUrl` at the top of the file, then host it anywhere static —
`epoch.json` beside it.

It has no dependencies at all. The ABI encoding is hand-rolled rather than
pulled from a CDN, because a page that moves other people's money should not
have a runtime dependency that can be unreachable or changed on the day someone
tries to claim. `test_claim_encoding.js` checks that encoding byte-for-byte
against Python's `eth_abi`, and `test_claim_page.py` drives the real page in a
browser against a mock wallet:

```bash
python cpu_token/web/make_vectors.py > /tmp/vectors.json
node cpu_token/web/test_claim_encoding.js /tmp/vectors.json   # 8 checks
python cpu_token/web/test_claim_page.py                       # 22 checks
```

The checks that matter most are that the transaction goes to the distributor and
that the encoded recipient and amount are the holder's own — not the sender's,
and not merely what the page displays.

Publishing the epoch file is not optional bookkeeping. It is what lets anyone
rebuild the tree from public chain data and check it against the root on-chain,
which is the whole reason to distribute this way instead of just sending
transfers and asking people to trust the arithmetic.

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

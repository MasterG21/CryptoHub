# Launch copy — Computing Power (CPU)

Paste-ready text for a launchpad form. Every claim here is one the contract
actually backs; if you edit the copy, keep it that way, because the first
thing a careful buyer does is check the description against the ABI.

**Token image:** `assets/cpu-logo-512.png` (512×512 PNG, transparent corners,
123 KB — inside brew.family's 5 MB limit). Vector source: `assets/cpu-logo.svg`.

---

## Name
```
Computing Power
```

## Ticker
```
CPU
```

## Short description (118 characters — for tight fields)
```
Fixed supply, no mint, no blacklist, no pause, no owner. Rewards paid through a verifiable Merkle claim contract.
```

## Standard description (274 characters)
```
Computing Power (CPU) is a fixed-supply BEP-20 on BNB Smart Chain. The contract has no mint
function, no blacklist, no pause and no owner — those levers were never written, not merely
renounced. Rewards are distributed separately, through a Merkle claim contract anyone can audit.
```

## Long description
```
Computing Power (CPU) is a fixed-supply BEP-20 on BNB Smart Chain, built so that the
usual questions about a new token can be answered by reading the contract instead of
trusting the team.

The token has no mint function, no blacklist, no pause, no transfer tax and no owner
role. Those are not disabled or renounced after the fact — they were never written into
the contract, so no one can add them later. One billion CPU are created once, in the
constructor, and that is the entire supply forever.

Rewards are deliberately kept out of the token. The common "reflection" design pays the
liquidity pool as though it were a holder, taxes every trade, and requires an owner
inside the token contract. Instead, CPU rewards run through a separate claim contract:
holder balances are snapshotted from public chain data, the pool and burn addresses are
excluded, and a Merkle root of the split is published on-chain. Holders claim their own
share by presenting a proof, and each epoch is funded in the same transaction that opens
it — an epoch can never be live while unfunded, and the funds cannot be withdrawn until
the claim deadline passes.

Anyone can rebuild the tree from the same public data and check it against the published
root, so the distribution is auditable without trusting anyone's arithmetic.

Rewards are discretionary and are not guaranteed. Holding CPU conveys no share, equity,
dividend right or claim on any company. Not affiliated with, or endorsed by, any company
or exchange. This is not a security offering and not financial advice.
```

---

## Wording to avoid

These read as promises of profit from someone else's effort, which is the
core of what makes an offering a securities offering — and each one is also
simply not something the contract guarantees:

| Don't write | Why | Write instead |
|---|---|---|
| "Earn MU stock dividends" | Implies an equity right the token does not carry | "Rewards may be funded in an external reward token" |
| "Backed by Micron shares" | CPU is backed by nothing; only bStocks are 1:1 backed | "Rewards are funded at the operator's discretion" |
| "Guaranteed weekly payouts" | Nothing in the contract obliges any epoch to exist | "Epochs are opened when funded" |
| "Micron-powered", "$MU rewards" | Uses another company's trademark and implies affiliation | Describe the mechanism, not the brand |
| "Risk-free", "passive income" | False, and a regulatory magnet | "Rewards are discretionary and not guaranteed" |

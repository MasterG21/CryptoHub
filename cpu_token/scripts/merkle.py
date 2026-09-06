"""Merkle tree for reward epochs, matching MerkleProof.sol on the contract side.

The layout is the OpenZeppelin convention, and every detail of it matters
for proofs to verify:

  leaf     = keccak256(keccak256(abi.encode(index, account, amount)))
  internal = keccak256(left ++ right) with the pair sorted bytewise

The leaf is hashed twice so that a leaf can never be reinterpreted as an
internal node, which is the second-preimage attack that single-hashed
Merkle airdrops are vulnerable to. Pairs are sorted so the contract does
not need to carry left/right position bits in the proof.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from eth_utils import keccak, to_checksum_address


def encode_leaf(index: int, account: str, amount: int) -> bytes:
    """abi.encode(uint256,address,uint256) — each field padded to 32 bytes."""
    account_bytes = bytes.fromhex(to_checksum_address(account)[2:])
    return (
        index.to_bytes(32, "big")
        + account_bytes.rjust(32, b"\x00")
        + amount.to_bytes(32, "big")
    )


def leaf_hash(index: int, account: str, amount: int) -> bytes:
    return keccak(keccak(encode_leaf(index, account, amount)))


def _hash_pair(a: bytes, b: bytes) -> bytes:
    return keccak(a + b) if a <= b else keccak(b + a)


def build_tree(leaves: Sequence[bytes]) -> list[list[bytes]]:
    """Return every level, leaves first, root last."""
    if not leaves:
        raise ValueError("cannot build a Merkle tree with no leaves")
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        current = levels[-1]
        nxt = [_hash_pair(current[i], current[i + 1]) for i in range(0, len(current) - 1, 2)]
        if len(current) % 2:
            # Odd node out is promoted unchanged rather than paired with
            # itself; self-pairing is what allows a duplicate-leaf forgery.
            nxt.append(current[-1])
        levels.append(nxt)
    return levels


def root_of(levels: Sequence[Sequence[bytes]]) -> bytes:
    return levels[-1][0]


def proof_for(levels: Sequence[Sequence[bytes]], index: int) -> list[bytes]:
    """The sibling path proving the leaf at `index` is under the root."""
    proof: list[bytes] = []
    idx = index
    for level in levels[:-1]:
        sibling = idx ^ 1
        if sibling < len(level):
            proof.append(level[sibling])
        idx //= 2
    return proof


def build_claims(entries: Iterable[tuple[str, int]]) -> tuple[bytes, list[dict]]:
    """Build a tree from (account, amount) pairs.

    Returns the root and one claim record per entry, each carrying the
    index, amount and proof a holder needs to call claim().
    """
    rows = [(i, to_checksum_address(a), amt) for i, (a, amt) in enumerate(entries)]
    leaves = [leaf_hash(i, a, amt) for i, a, amt in rows]
    levels = build_tree(leaves)
    claims = [
        {
            "index": i,
            "account": a,
            "amount": str(amt),
            "proof": ["0x" + p.hex() for p in proof_for(levels, i)],
        }
        for i, a, amt in rows
    ]
    return root_of(levels), claims

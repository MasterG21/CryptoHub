"""Reference vectors for test_epoch_builder.js.

The browser builder reimplements keccak-256, EIP-55 checksumming and the
Merkle tree in JavaScript. Those must agree exactly with the Python
implementations, because the Python ones are what the contract test suite
exercises against a real EVM. A root that differs by one byte pays nobody.
"""
import json
import os
import random
import sys

from eth_utils import keccak, to_checksum_address

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from build_snapshot import build_epoch  # noqa: E402

BURN = ["0x0000000000000000000000000000000000000000",
        "0x000000000000000000000000000000000000dead"]


def addr(rng):
    return "0x" + bytes(rng.randrange(256) for _ in range(20)).hex()


def main() -> None:
    rng = random.Random(23)

    keccak_cases = []
    for n in [0, 1, 31, 32, 135, 136, 137, 272, 500]:
        data = bytes(rng.randrange(256) for _ in range(n))
        keccak_cases.append({"hex": data.hex(), "expected": keccak(data).hex()})

    checksum_cases = []
    for _ in range(12):
        a = addr(rng)
        checksum_cases.append({"input": a, "expected": to_checksum_address(a)})
    # Addresses that are all-numeric or all-letters exercise the casing rule.
    for a in ["0x" + "0" * 40, "0x" + "f" * 40, "0x" + "1234567890" * 4]:
        checksum_cases.append({"input": a, "expected": to_checksum_address(a)})

    epochs = []
    for n_holders in [1, 2, 3, 5, 17, 64]:
        holders = [[addr(rng), str(rng.randrange(1, 10**22))] for _ in range(n_holders)]
        # Some entries that must be filtered out on both sides.
        holders.append([BURN[1], str(10**24)])
        holders.append([addr(rng), "0"])
        excluded = [holders[0][0]] if n_holders > 2 else [addr(rng)]
        total = rng.randrange(10**18, 10**23)

        py = build_epoch(
            [(a, int(b)) for a, b in holders],
            total,
            {x.lower() for x in excluded} | {b.lower() for b in BURN},
            0,
        )
        epochs.append({
            "holders": holders, "total": str(total), "excluded": excluded,
            "expected_root": py["merkle_root"],
            "expected_allocated": py["allocated"],
            "expected_claims": py["claims"],
        })

    print(json.dumps({"keccak": keccak_cases, "checksum": checksum_cases, "epochs": epochs}))


if __name__ == "__main__":
    main()

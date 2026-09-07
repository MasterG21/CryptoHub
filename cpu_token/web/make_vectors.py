"""Emit reference ABI encodings for test_claim_encoding.js (from eth_abi)."""
import json
import random

from eth_abi import encode
from eth_utils import keccak

CLAIM_SIG = "claim(uint256,uint256,address,uint256,bytes32[])"
IS_CLAIMED_SIG = "isClaimed(uint256,uint256)"


def main() -> None:
    random.seed(7)
    claim_sel = keccak(text=CLAIM_SIG)[:4]
    vectors = []
    for n_proof in (0, 1, 3, 8):
        proof = ["0x" + bytes(random.randrange(256) for _ in range(32)).hex()
                 for _ in range(n_proof)]
        epoch_id, index = random.randrange(2**16), random.randrange(2**20)
        account = "0x" + bytes(random.randrange(256) for _ in range(20)).hex()
        amount = random.randrange(2**90)
        data = "0x" + claim_sel.hex() + encode(
            ["uint256", "uint256", "address", "uint256", "bytes32[]"],
            [epoch_id, index, account, amount, [bytes.fromhex(p[2:]) for p in proof]],
        ).hex()
        vectors.append({"epochId": epoch_id, "index": index, "account": account,
                        "amount": str(amount), "proof": proof, "expected": data})

    is_sel = keccak(text=IS_CLAIMED_SIG)[:4]
    is_claimed = {"epochId": 3, "index": 259,
                  "expected": "0x" + is_sel.hex() + encode(["uint256", "uint256"], [3, 259]).hex()}

    print(json.dumps({"claim": vectors, "isClaimed": is_claimed}, indent=1))


if __name__ == "__main__":
    main()

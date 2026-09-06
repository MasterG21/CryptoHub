// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @title Computing Power (CPU)
 * @notice A fixed-supply BEP-20 with no administrative functions of any kind.
 *
 * There is deliberately no mint function, no pause, no blacklist, no
 * transfer fee, and no owner. The entire supply is created once, in the
 * constructor, and sent to the deployer. After deployment nobody — the
 * deployer included — can change the supply, freeze a wallet, halt
 * trading, or alter a fee.
 *
 * That is not decoration. Those are exactly the levers this repo's own
 * scanner deducts points for, because they are the levers a contract
 * needs in order to be used against the people holding it. A contract
 * without them cannot rug via the contract; the remaining risk moves to
 * liquidity and distribution, which are choices made outside this file.
 *
 * Rewards are intentionally NOT implemented here. A reward mechanism
 * bolted into the token would need an owner, a fee hook, or a mutable
 * distributor address, and would reintroduce the levers above. Rewards
 * live in a separate, opt-in contract (MerkleRewardDistributor) that
 * holds no power over this token whatsoever.
 */
contract ComputingPower is ERC20 {
    /// @notice Total supply, fixed forever at 1,000,000,000 CPU.
    uint256 public constant MAX_SUPPLY = 1_000_000_000 ether;

    constructor(address treasury) ERC20("Computing Power", "CPU") {
        require(treasury != address(0), "CPU: zero treasury");
        _mint(treasury, MAX_SUPPLY);
    }
}

// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @dev Test-only stand-in for the reward token. Not for deployment.
contract MockERC20 is ERC20 {
    constructor(string memory n, string memory s, uint256 supply) ERC20(n, s) {
        _mint(msg.sender, supply);
    }
}

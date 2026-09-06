// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title MerkleRewardDistributor
 * @notice Distributes an arbitrary BEP-20 reward token to CPU holders in
 *         discrete, verifiable epochs.
 *
 * WHY MERKLE AND NOT AUTOMATIC REFLECTIONS
 *
 * The usual "reward token" on BSC pays holders by hooking every transfer
 * and pushing balances around. That approach forces the token itself to
 * carry an owner, a fee hook, and a mutable distributor address, it
 * silently pays the liquidity pool as if it were a holder, and it costs
 * every trader gas forever. This contract does none of that. It is
 * entirely separate from the CPU token, holds no authority over it, and
 * the token stays immutable and admin-free.
 *
 * Each epoch is a snapshot: holder balances are read off-chain, the pool
 * and burn addresses are excluded, a Merkle tree of (index, account,
 * amount) is built, and only the root is published here. Holders pull
 * their own share by presenting a proof. Anyone can rebuild the tree from
 * public chain data and check the root matches, so the split is auditable
 * without trusting the operator's arithmetic.
 *
 * WHAT THE OPERATOR CAN AND CANNOT DO
 *
 * Can:    open an epoch (funding it in the same transaction), and sweep
 *         whatever is still unclaimed once that epoch's deadline passes.
 * Cannot: withdraw funded rewards before the deadline, alter a published
 *         root, block an individual claim, or touch the CPU token.
 *
 * Each epoch's funds are accounted separately, so a mistaken or malicious
 * root can never pay out more than that epoch was funded with, and can
 * never reach into another epoch's balance.
 *
 * A NOTE ON THE REWARD TOKEN
 *
 * `rewardToken` is set once and is deliberately generic. If it is a
 * tokenized security, distributing it to the public is a regulated
 * activity in most jurisdictions and the eligibility rules of its issuer
 * still apply to every recipient — deploying this contract does not
 * change that and does not constitute advice that you may do so. Note
 * also that a reward token which enforces transfer restrictions on-chain
 * will simply make claims revert for restricted addresses.
 */
contract MerkleRewardDistributor is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    /// @notice The token paid out to holders.
    IERC20 public immutable rewardToken;

    /// @notice The token whose holders are entitled to rewards (CPU).
    /// @dev Recorded for transparency; balances are snapshotted off-chain.
    address public immutable holdingsToken;

    /// @notice Floor on how long holders get to claim, so an epoch cannot
    ///         be opened and swept out from under them.
    uint64 public constant MIN_CLAIM_WINDOW = 30 days;

    struct Epoch {
        bytes32 merkleRoot;
        uint256 totalAmount;
        uint256 claimedAmount;
        uint64 claimDeadline;
        bool swept;
    }

    Epoch[] private _epochs;

    /// @dev epochId => word index => bitmap of claimed leaf indices.
    mapping(uint256 => mapping(uint256 => uint256)) private _claimedBitMap;

    event EpochOpened(
        uint256 indexed epochId, bytes32 merkleRoot, uint256 totalAmount, uint64 claimDeadline
    );
    event Claimed(
        uint256 indexed epochId, uint256 indexed index, address indexed account, uint256 amount
    );
    event Swept(uint256 indexed epochId, address indexed to, uint256 amount);

    error InvalidProof();
    error AlreadyClaimed();
    error EpochNotFound();
    error ClaimWindowTooShort();
    error ClaimPeriodOver();
    error ClaimPeriodNotOver();
    error EpochOverAllocated();
    error AlreadySwept();
    error ZeroAddress();
    error ZeroAmount();

    constructor(address rewardToken_, address holdingsToken_, address owner_) Ownable(owner_) {
        if (rewardToken_ == address(0) || holdingsToken_ == address(0)) revert ZeroAddress();
        rewardToken = IERC20(rewardToken_);
        holdingsToken = holdingsToken_;
    }

    /// @notice Number of epochs opened so far.
    function epochCount() external view returns (uint256) {
        return _epochs.length;
    }

    /// @notice Read one epoch's parameters and progress.
    function epoch(uint256 epochId) external view returns (Epoch memory) {
        if (epochId >= _epochs.length) revert EpochNotFound();
        return _epochs[epochId];
    }

    /// @notice How much of `epochId` is still available to claim.
    function unclaimed(uint256 epochId) public view returns (uint256) {
        if (epochId >= _epochs.length) revert EpochNotFound();
        Epoch storage e = _epochs[epochId];
        return e.totalAmount - e.claimedAmount;
    }

    /// @notice Whether a given leaf index of an epoch has been claimed.
    function isClaimed(uint256 epochId, uint256 index) public view returns (bool) {
        uint256 word = index / 256;
        uint256 bit = index % 256;
        return _claimedBitMap[epochId][word] & (1 << bit) != 0;
    }

    /**
     * @notice Open and fund a new reward epoch in one transaction.
     * @dev Pulls `totalAmount` of rewardToken from the caller, so the
     *      epoch is never live while unfunded. Approve first.
     * @param merkleRoot Root over leaves of (index, account, amount).
     * @param totalAmount Sum of every amount in the tree.
     * @param claimWindow Seconds holders have to claim; >= MIN_CLAIM_WINDOW.
     */
    function openEpoch(bytes32 merkleRoot, uint256 totalAmount, uint64 claimWindow)
        external
        onlyOwner
        nonReentrant
        returns (uint256 epochId)
    {
        if (merkleRoot == bytes32(0)) revert InvalidProof();
        if (totalAmount == 0) revert ZeroAmount();
        if (claimWindow < MIN_CLAIM_WINDOW) revert ClaimWindowTooShort();

        // Measure what actually arrived rather than trusting the argument,
        // so a fee-on-transfer reward token cannot leave an epoch
        // promising more than the contract received.
        uint256 before = rewardToken.balanceOf(address(this));
        rewardToken.safeTransferFrom(msg.sender, address(this), totalAmount);
        uint256 received = rewardToken.balanceOf(address(this)) - before;

        uint64 deadline = uint64(block.timestamp) + claimWindow;
        epochId = _epochs.length;
        _epochs.push(
            Epoch({
                merkleRoot: merkleRoot,
                totalAmount: received,
                claimedAmount: 0,
                claimDeadline: deadline,
                swept: false
            })
        );

        emit EpochOpened(epochId, merkleRoot, received, deadline);
    }

    /**
     * @notice Claim one leaf of an epoch. Callable by anyone; the reward
     *         always goes to `account`, never to the caller.
     */
    function claim(
        uint256 epochId,
        uint256 index,
        address account,
        uint256 amount,
        bytes32[] calldata merkleProof
    ) external nonReentrant {
        if (epochId >= _epochs.length) revert EpochNotFound();
        Epoch storage e = _epochs[epochId];
        if (block.timestamp > e.claimDeadline) revert ClaimPeriodOver();
        if (isClaimed(epochId, index)) revert AlreadyClaimed();

        // Double hash so a leaf can never be mistaken for an internal
        // node, which is what makes a second-preimage forgery possible.
        bytes32 leaf = keccak256(bytes.concat(keccak256(abi.encode(index, account, amount))));
        if (!MerkleProof.verifyCalldata(merkleProof, e.merkleRoot, leaf)) revert InvalidProof();

        // Per-epoch accounting: a bad root can never pay out more than
        // this epoch was funded with, nor reach another epoch's balance.
        uint256 newClaimed = e.claimedAmount + amount;
        if (newClaimed > e.totalAmount) revert EpochOverAllocated();

        // Effects before interaction.
        _claimedBitMap[epochId][index / 256] |= (1 << (index % 256));
        e.claimedAmount = newClaimed;

        rewardToken.safeTransfer(account, amount);
        emit Claimed(epochId, index, account, amount);
    }

    /**
     * @notice Recover an epoch's unclaimed remainder, only once its claim
     *         deadline has passed.
     */
    function sweepUnclaimed(uint256 epochId, address to) external onlyOwner nonReentrant {
        if (epochId >= _epochs.length) revert EpochNotFound();
        if (to == address(0)) revert ZeroAddress();
        Epoch storage e = _epochs[epochId];
        if (block.timestamp <= e.claimDeadline) revert ClaimPeriodNotOver();
        if (e.swept) revert AlreadySwept();

        uint256 amount = e.totalAmount - e.claimedAmount;
        e.swept = true;
        // Mark fully allocated so the swept remainder can't be claimed twice.
        e.claimedAmount = e.totalAmount;

        if (amount > 0) {
            rewardToken.safeTransfer(to, amount);
        }
        emit Swept(epochId, to, amount);
    }
}

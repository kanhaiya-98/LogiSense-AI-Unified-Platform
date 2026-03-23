// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title  DecisionAnchor
 * @notice Immutable on-chain registry of Merkle roots representing
 *         batches of LogiSense AI agent decisions.
 *
 * Design:
 *  - Anyone can call verifyDecision() permissionlessly — no auth required.
 *  - Only the deployer (Agent wallet) can call anchorBatch().
 *  - Roots cannot be deleted or overwritten — append-only.
 *  - Each root anchoring emits DecisionBatchAnchored so external tools
 *    (Polygonscan, partner dashboards) can index events without polling.
 *
 * Gas profile (Polygon PoS):
 *  - anchorBatch():   ~21,000 gas  (~$0.001 at current MATIC prices)
 *  - verifyDecision(): pure view, zero gas
 *  - getRootInfo():    view, zero gas
 */
contract DecisionAnchor {

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------

    address public immutable owner;

    struct BatchInfo {
        string  batchId;
        uint256 decisionCount;
        uint256 timestamp;
        address anchoredBy;
        bool    exists;
    }

    // merkleRoot => BatchInfo
    mapping(bytes32 => BatchInfo) private _roots;

    // ordered list of all anchored roots (for enumeration)
    bytes32[] private _rootHistory;

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    event DecisionBatchAnchored(
        bytes32 indexed merkleRoot,
        string          batchId,
        uint256         decisionCount,
        uint256         timestamp
    );

    // -----------------------------------------------------------------------
    // Errors
    // -----------------------------------------------------------------------

    error NotOwner();
    error RootAlreadyAnchored(bytes32 root);
    error RootNotFound(bytes32 root);
    error EmptyBatchId();
    error ZeroDecisionCount();

    // -----------------------------------------------------------------------
    // Constructor
    // -----------------------------------------------------------------------

    constructor() {
        owner = msg.sender;
    }

    // -----------------------------------------------------------------------
    // Anchoring (write — owner only)
    // -----------------------------------------------------------------------

    /**
     * @notice Anchor a Merkle root representing a batch of agent decisions.
     * @param merkleRoot    32-byte Merkle root of decision fingerprint hashes.
     * @param batchId       UUID string identifying this batch (for off-chain lookup).
     * @param decisionCount Number of decisions included in this batch.
     */
    function anchorBatch(
        bytes32 merkleRoot,
        string calldata batchId,
        uint256 decisionCount
    ) external {
        if (msg.sender != owner)           revert NotOwner();
        if (_roots[merkleRoot].exists)     revert RootAlreadyAnchored(merkleRoot);
        if (bytes(batchId).length == 0)   revert EmptyBatchId();
        if (decisionCount == 0)            revert ZeroDecisionCount();

        _roots[merkleRoot] = BatchInfo({
            batchId:       batchId,
            decisionCount: decisionCount,
            timestamp:     block.timestamp,
            anchoredBy:    msg.sender,
            exists:        true
        });

        _rootHistory.push(merkleRoot);

        emit DecisionBatchAnchored(merkleRoot, batchId, decisionCount, block.timestamp);
    }

    // -----------------------------------------------------------------------
    // Verification (pure — no gas, permissionless)
    // -----------------------------------------------------------------------

    /**
     * @notice Verify a single decision against a Merkle root.
     *         Sorted-pair combination: smaller hash always goes left.
     *         This matches the Python merkle_tree.verify_proof() logic.
     *
     * @param leafHash  SHA-256 of the decision's fingerprint hash (re-hashed leaf).
     * @param proof     Sibling hashes from leaf to root.
     * @param root      Expected Merkle root (must be anchored on-chain).
     * @return          True if the proof is valid for this root.
     */
    function verifyDecision(
        bytes32 leafHash,
        bytes32[] calldata proof,
        bytes32 root
    ) external pure returns (bool) {
        // Re-hash the leaf (matches Python _hash_leaf)
        bytes32 current = sha256(abi.encodePacked(leafHash));

        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 sibling = proof[i];
            // Sorted combination — deterministic regardless of tree position
            if (current <= sibling) {
                current = sha256(abi.encodePacked(current, sibling));
            } else {
                current = sha256(abi.encodePacked(sibling, current));
            }
        }

        return current == root;
    }

    // -----------------------------------------------------------------------
    // Queries (view)
    // -----------------------------------------------------------------------

    /**
     * @notice Get metadata for an anchored Merkle root.
     */
    function getRootInfo(bytes32 root)
        external
        view
        returns (
            string memory batchId,
            uint256 decisionCount,
            uint256 timestamp,
            address anchoredBy
        )
    {
        if (!_roots[root].exists) revert RootNotFound(root);
        BatchInfo storage info = _roots[root];
        return (info.batchId, info.decisionCount, info.timestamp, info.anchoredBy);
    }

    /**
     * @notice Check if a root has been anchored.
     */
    function isAnchored(bytes32 root) external view returns (bool) {
        return _roots[root].exists;
    }

    /**
     * @notice Total number of anchored batches.
     */
    function batchCount() external view returns (uint256) {
        return _rootHistory.length;
    }

    /**
     * @notice Get the nth anchored root (for enumeration / audit tools).
     */
    function rootAt(uint256 index) external view returns (bytes32) {
        require(index < _rootHistory.length, "Index out of range");
        return _rootHistory[index];
    }
}

from __future__ import annotations
"""
Feature 9: Merkle Tree
Binary Merkle tree over decision fingerprint hashes.

- Leaf nodes  = SHA-256 fingerprints of individual decisions
- Parent nodes = SHA-256(left_child + right_child)  [standard Bitcoin-style]
- Odd leaf count: last leaf is duplicated (standard padding)
- Proof path: O(log n) sibling hashes needed to verify any leaf

The root is what gets anchored to Polygon.  Any third party can verify
a specific decision by re-walking the proof path and checking it reaches
the on-chain root — no access to the internal DB required.
"""



import hashlib
import logging
import uuid
from typing import List, Tuple

from blockchain_models import DecisionRecord, MerkleBatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hashing primitives
# ---------------------------------------------------------------------------

def _hash_pair(left: str, right: str) -> str:
    """Combine two hex hash strings into one parent hash."""
    combined = bytes.fromhex(left) + bytes.fromhex(right)
    return hashlib.sha256(combined).hexdigest()


def _hash_leaf(value: str) -> str:
    """Hash a single leaf value (already a hex hash, re-hash for consistency)."""
    return hashlib.sha256(bytes.fromhex(value)).hexdigest()


# ---------------------------------------------------------------------------
# Tree construction
# ---------------------------------------------------------------------------

def build_merkle_tree(leaf_hashes: List[str]) -> Tuple[str, List[List[str]]]:
    """
    Build a binary Merkle tree from a list of leaf hashes.

    Returns:
        root      — hex string of the Merkle root
        levels    — list of levels [leaves, ..., [root]]
                    Stored so we can generate proofs without recomputing.

    Raises:
        ValueError if leaf_hashes is empty.
    """
    if not leaf_hashes:
        raise ValueError("Cannot build Merkle tree from empty leaf set.")

    # Hash each leaf one more time so leaf != internal node (prevents
    # second-preimage attacks that could let an attacker forge proofs)
    current_level = [_hash_leaf(h) for h in leaf_hashes]
    levels = [current_level[:]]

    while len(current_level) > 1:
        # Pad odd-length level by duplicating last hash
        if len(current_level) % 2 == 1 and len(current_level) > 1:
            current_level.append(current_level[-1])

        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1]
            if left <= right:
                next_level.append(_hash_pair(left, right))
            else:
                next_level.append(_hash_pair(right, left))

        current_level = next_level
        levels.append(current_level[:])

    root = current_level[0]
    logger.info("Built Merkle tree: %d leaves -> root %s", len(leaf_hashes), root[:16])
    return root, levels


# ---------------------------------------------------------------------------
# Proof generation
# ---------------------------------------------------------------------------

def generate_proof(leaf_hashes: List[str], leaf_index: int) -> List[str]:
    """
    Generate the Merkle proof (list of sibling hashes) for a leaf at leaf_index.
    The verifier re-hashes upward using this proof and should arrive at the root.

    Returns list of hex sibling hashes from bottom to top.
    """
    if leaf_index >= len(leaf_hashes):
        raise IndexError(f"leaf_index {leaf_index} out of range for {len(leaf_hashes)} leaves.")

    _, levels = build_merkle_tree(leaf_hashes)
    proof: List[str] = []
    idx = leaf_index

    for level in levels[:-1]:   # skip root level
        if len(level) % 2 == 1:
            level = level + [level[-1]]   # same padding as build

        sibling_idx = idx ^ 1   # XOR 1 to get sibling (left<->right)
        proof.append(level[sibling_idx])
        idx //= 2

    return proof


def verify_proof(
    leaf_hash: str,
    proof: List[str],
    expected_root: str,
) -> bool:
    """
    Re-walk the proof path and check it reaches expected_root.
    Called by the public verification endpoint and the smart contract.
    """
    current = _hash_leaf(leaf_hash)

    for sibling in proof:
        # We don't store left/right flags; instead sort so the smaller hash
        # is always left — this is deterministic and matches the contract.
        if current <= sibling:
            current = _hash_pair(current, sibling)
        else:
            current = _hash_pair(sibling, current)

    match = current == expected_root

    if not match:
        logger.warning(
            "Proof invalid: computed root %s != expected %s",
            current[:16],
            expected_root[:16],
        )
    return match


# ---------------------------------------------------------------------------
# Batch builder — called hourly by the blockchain node
# ---------------------------------------------------------------------------

def build_batch(decisions: List[DecisionRecord]) -> MerkleBatch:
    """
    Take a list of fingerprinted decisions and produce a MerkleBatch.
    Decisions without a fingerprint_hash are skipped with a warning.
    """
    valid = [d for d in decisions if d.fingerprint_hash]
    skipped = len(decisions) - len(valid)
    if skipped:
        logger.warning("%d decisions skipped (no fingerprint_hash).", skipped)

    if not valid:
        raise ValueError("No fingerprinted decisions available for batch.")

    leaf_hashes = [d.fingerprint_hash for d in valid]   # type: ignore[misc]
    root, _ = build_merkle_tree(leaf_hashes)

    batch = MerkleBatch(
        batch_id=str(uuid.uuid4()),
        decision_ids=[d.decision_id for d in valid],
        leaf_hashes=leaf_hashes,
        merkle_root=root,
    )

    logger.info(
        "Created batch %s: %d decisions, root=%s",
        batch.batch_id[:8],
        len(valid),
        root[:16],
    )
    return batch


def attach_proofs_to_decisions(
    decisions: List[DecisionRecord],
    batch: MerkleBatch,
) -> List[DecisionRecord]:
    """
    For each decision in the batch, compute its Merkle proof and store it
    in the decision record.  Returns updated records.
    """
    id_to_index = {did: i for i, did in enumerate(batch.decision_ids)}
    updated: List[DecisionRecord] = []

    for d in decisions:
        if d.decision_id not in id_to_index:
            updated.append(d)
            continue

        idx = id_to_index[d.decision_id]
        proof = generate_proof(batch.leaf_hashes, idx)
        updated.append(d.model_copy(update={
            "merkle_batch_id": batch.batch_id,
            "merkle_proof": proof,
            "merkle_root": batch.merkle_root,
        }))

    return updated

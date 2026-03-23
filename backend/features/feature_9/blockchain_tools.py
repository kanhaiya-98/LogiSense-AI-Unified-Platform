from __future__ import annotations
"""
Feature 9: Blockchain Tools (MCP-style)
These are the callable tools that other agent nodes (especially Actor Agent)
invoke.  Each tool matches the interface described in Section 10 of the spec.

Integration contract:
  - Every tool returns a dict with at least {"ok": bool, "error": str | None}
  - Tools are registered with LangGraph's ToolNode or passed to the
    Reasoner Agent's tool-calling chain — see blockchain_node.py for wiring.
  - log_and_fingerprint is the MOST IMPORTANT tool: it must be called by
    the Actor Agent immediately after every action, before any other node
    reads the decision record.
"""



import logging
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

from langchain_core.tools import tool

from blockchain_models import AnchorStatus, DecisionRecord, MerkleBatch, VerificationResult
from decision_hasher import compute_hash, fingerprint_and_sign, verify_hash, recover_signer
from merkle_tree import build_batch, attach_proofs_to_decisions, verify_proof
from smart_contract import PolygonClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------

_polygon_client = PolygonClient()
try:
    _polygon_client.connect()
except Exception:
    pass

_pending_decisions: List[DecisionRecord] = []   # in-memory queue between batches


def init_blockchain_tools(client: PolygonClient) -> None:
    """Called once by blockchain_node.py at graph startup."""
    global _polygon_client
    _polygon_client = client


# ---------------------------------------------------------------------------
# Tool 1: log_and_fingerprint
# Called by Actor Agent after EVERY action.
# ---------------------------------------------------------------------------

@tool
def log_and_fingerprint(decision_json: str) -> Dict[str, Any]:
    """
    Fingerprint and queue a decision record for Merkle anchoring.

    Args:
        decision_json: JSON string of a DecisionRecord (use record.model_dump_json()).

    Returns:
        {"ok": True, "decision_id": str, "fingerprint_hash": str,
         "anchor_status": "pending", "agent_signature": str}
    """
    try:
        record = DecisionRecord.model_validate_json(decision_json)
    except Exception as exc:
        return {"ok": False, "error": f"Invalid DecisionRecord JSON: {exc}"}

    private_key = os.environ.get("POLYGON_PRIVATE_KEY", "")
    if not private_key:
        # Fingerprint without signing if no key available (dev mode)
        h = compute_hash(record)
        record = record.model_copy(update={"fingerprint_hash": h, "anchor_status": AnchorStatus.PENDING})
        logger.warning("No POLYGON_PRIVATE_KEY — decision signed without agent key.")
    else:
        record = fingerprint_and_sign(record, private_key)
        record = record.model_copy(update={"anchor_status": AnchorStatus.PENDING})

    _pending_decisions.append(record)

    logger.info(
        "Decision %s fingerprinted: %s (queue depth: %d)",
        record.decision_id,
        record.fingerprint_hash[:16] if record.fingerprint_hash else "?",
        len(_pending_decisions),
    )

    return {
        "ok":               True,
        "decision_id":      record.decision_id,
        "fingerprint_hash": record.fingerprint_hash,
        "anchor_status":    record.anchor_status.value,
        "agent_signature":  record.agent_signature,
    }


# ---------------------------------------------------------------------------
# Tool 2: flush_and_anchor_batch
# Called by BlockchainNode on its hourly schedule (or when queue >= threshold).
# Other nodes can also call this to force an immediate anchor.
# ---------------------------------------------------------------------------

@tool
def flush_and_anchor_batch(force: bool = False) -> Dict[str, Any]:
    """
    Build a Merkle batch from the pending queue and anchor the root on Polygon.

    Args:
        force: If True, flush even if queue is small.

    Returns:
        {"ok": bool, "batch_id": str, "root": str, "tx_hash": str,
         "decision_count": int, "polygonscan_url": str}
    """
    global _pending_decisions

    MIN_BATCH_SIZE = 1 if force else 5

    if len(_pending_decisions) < MIN_BATCH_SIZE:
        return {
            "ok": False,
            "error": f"Queue has {len(_pending_decisions)} decisions, minimum is {MIN_BATCH_SIZE}. Pass force=True to override.",
        }

    # Snapshot and clear the queue atomically
    to_process = _pending_decisions[:]
    _pending_decisions = []

    try:
        batch = build_batch(to_process)
    except ValueError as exc:
        # Return decisions to queue
        _pending_decisions = to_process + _pending_decisions
        return {"ok": False, "error": str(exc)}

    # Attach proofs to each decision record (in-memory; caller persists to DB)
    updated_decisions = attach_proofs_to_decisions(to_process, batch)

    # Anchor on-chain
    tx_hash: Optional[str] = None
    if _polygon_client and _polygon_client.is_connected():
        tx_hash = _polygon_client.anchor_batch(
            merkle_root=batch.merkle_root,
            batch_id=batch.batch_id,
            decision_count=len(batch.decision_ids),
        )

    if tx_hash:
        import time
        # Update batch with tx info
        block = None
        try:
            receipt = _polygon_client.w3.eth.get_transaction_receipt(tx_hash)
            block = receipt.blockNumber
        except Exception:
            pass

        batch = batch.model_copy(update={
            "blockchain_tx": tx_hash,
            "anchored_utc": time.time(),
            "anchored_block": block,
        })

        final_status = AnchorStatus.ANCHORED
        polygonscan_url = _polygon_client.tx_url(tx_hash)
        logger.info("Batch %s anchored on Polygon. TX: %s", batch.batch_id[:8], tx_hash[:16])
    else:
        final_status = AnchorStatus.BATCHED
        polygonscan_url = ""
        logger.warning("Batch %s NOT anchored (chain unavailable). Status: BATCHED.", batch.batch_id[:8])

    # Update anchor status on all decisions
    finalized: List[DecisionRecord] = []
    for d in updated_decisions:
        finalized.append(d.model_copy(update={
            "anchor_status":     final_status,
            "blockchain_tx_hash": tx_hash,
            "blockchain_block":  block if tx_hash else None,
        }))

    # Expose finalized decisions so the caller can persist them
    # (The blockchain_node.py node writes these to the DB and AgentState)
    _last_batch_result["decisions"] = finalized
    _last_batch_result["batch"]     = batch

    return {
        "ok":              True,
        "batch_id":        batch.batch_id,
        "merkle_root":     batch.merkle_root,
        "tx_hash":         tx_hash or "",
        "decision_count":  len(batch.decision_ids),
        "anchor_status":   final_status.value,
        "polygonscan_url": polygonscan_url,
    }


# Module-level dict to pass batch results back to the node without extra DB calls
_last_batch_result: Dict[str, Any] = {}


def get_last_batch_result() -> Dict[str, Any]:
    return _last_batch_result


# ---------------------------------------------------------------------------
# Tool 3: verify_decision
# Called by dashboard, API endpoint, or any agent needing integrity check.
# ---------------------------------------------------------------------------

@tool
def verify_decision(decision_json: str) -> Dict[str, Any]:
    """
    Verify the integrity of a decision record end-to-end:
      1. Re-compute SHA-256 hash and compare with stored fingerprint.
      2. If Merkle proof available, verify it against the on-chain root.

    Args:
        decision_json: JSON string of a DecisionRecord.

    Returns:
        VerificationResult as dict.
    """
    try:
        record = DecisionRecord.model_validate_json(decision_json)
    except Exception as exc:
        return VerificationResult(
            decision_id="unknown",
            verified=False,
            reason=f"Invalid JSON: {exc}",
        ).model_dump()

    # Step 1: hash check
    if not record.fingerprint_hash:
        return VerificationResult(
            decision_id=record.decision_id,
            verified=False,
            reason="No fingerprint_hash stored — decision was never fingerprinted.",
        ).model_dump()

    computed = compute_hash(record)
    hash_ok  = computed == record.fingerprint_hash

    if not hash_ok:
        return VerificationResult(
            decision_id    = record.decision_id,
            verified       = False,
            reason         = "TAMPER DETECTED: computed hash does not match stored hash.",
            stored_hash    = record.fingerprint_hash,
            computed_hash  = computed,
        ).model_dump()

    # Step 2: Merkle proof check
    proof_ok: Optional[bool] = None
    on_chain_root: Optional[str] = None

    if record.merkle_proof and record.merkle_root:
        on_chain_root = record.merkle_root

        if _polygon_client and _polygon_client.is_connected():
            proof_ok = _polygon_client.verify_on_chain(
                leaf_hash = record.fingerprint_hash,
                proof     = record.merkle_proof,
                root      = record.merkle_root,
            )
        else:
            # Local fallback
            proof_ok = verify_proof(
                leaf_hash     = record.fingerprint_hash,
                proof         = record.merkle_proof,
                expected_root = record.merkle_root,
            )

    polygonscan_url = ""
    if record.blockchain_tx_hash and _polygon_client:
        polygonscan_url = _polygon_client.tx_url(record.blockchain_tx_hash)

    # Build final verdict
    if proof_ok is False:
        return VerificationResult(
            decision_id    = record.decision_id,
            verified       = False,
            reason         = "Hash intact but Merkle proof INVALID — batch may have been tampered.",
            stored_hash    = record.fingerprint_hash,
            computed_hash  = computed,
            on_chain_root  = on_chain_root,
            proof_valid    = False,
            blockchain_tx  = record.blockchain_tx_hash,
            polygonscan_url= polygonscan_url,
        ).model_dump()

    return VerificationResult(
        decision_id    = record.decision_id,
        verified       = True,
        reason         = "Hash intact" + (" and Merkle proof valid." if proof_ok else " (no Merkle proof yet)."),
        stored_hash    = record.fingerprint_hash,
        computed_hash  = computed,
        on_chain_root  = on_chain_root,
        proof_valid    = proof_ok,
        blockchain_tx  = record.blockchain_tx_hash,
        polygonscan_url= polygonscan_url,
    ).model_dump()


# ---------------------------------------------------------------------------
# Tool 4: tamper_demo
# Demo tool: show judges what happens when you modify a record.
# ---------------------------------------------------------------------------

@tool
def tamper_demo(decision_json: str, field_to_mutate: str = "action") -> Dict[str, Any]:
    """
    Demo tool: mutate one field of a decision record and show the hash breaks.

    Args:
        decision_json:   JSON string of a DecisionRecord.
        field_to_mutate: Which field to corrupt (default: "action").

    Returns:
        {"original_hash": str, "tampered_hash": str, "hashes_match": False,
         "message": str}
    """
    try:
        record = DecisionRecord.model_validate_json(decision_json)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    original_hash = record.fingerprint_hash or compute_hash(record)

    # Corrupt the field
    data = record.model_dump()
    if field_to_mutate in data and data[field_to_mutate] is not None:
        data[field_to_mutate] = str(data[field_to_mutate]) + "_TAMPERED"
    else:
        data["reasoning_text"] = (data.get("reasoning_text") or "") + "_TAMPERED"

    tampered_record = DecisionRecord(**data)
    tampered_hash = compute_hash(tampered_record)

    return {
        "original_hash": original_hash,
        "tampered_hash": tampered_hash,
        "hashes_match":  original_hash == tampered_hash,
        "message":       (
            "✅ Hash BROKE instantly — the blockchain says otherwise."
            if original_hash != tampered_hash
            else "⚠️ Hashes unexpectedly matched (this should not happen)."
        ),
    }


# ---------------------------------------------------------------------------
# Tool 5: get_queue_status
# Lightweight status check for the dashboard
# ---------------------------------------------------------------------------

@tool
def get_queue_status() -> Dict[str, Any]:
    """Return current blockchain queue stats for the dashboard."""
    return {
        "pending_count":  len(_pending_decisions),
        "chain_connected": _polygon_client.is_connected() if _polygon_client else False,
        "contract_address": os.environ.get("POLYGON_CONTRACT_ADDRESS", ""),
        "polygonscan_contract": (
            _polygon_client.address_url() if _polygon_client else ""
        ),
    }


# ---------------------------------------------------------------------------
# Exported tool list — register all of these with LangGraph ToolNode
# ---------------------------------------------------------------------------

BLOCKCHAIN_TOOLS = [
    log_and_fingerprint,
    flush_and_anchor_batch,
    verify_decision,
    tamper_demo,
    get_queue_status,
]

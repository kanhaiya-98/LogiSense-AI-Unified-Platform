from __future__ import annotations
"""
Feature 9: Blockchain Node (LangGraph)
======================================
This is the LangGraph node for Feature 9.  It plugs into the shared
AgentState graph and handles two responsibilities:

  A. REACTIVE: Immediately fingerprint any decision produced by another node
     in the same graph turn (Observer, Reasoner, Actor, Learner all emit
     DecisionRecords — this node picks them up and hashes them).

  B. SCHEDULED: Hourly Merkle batch + Polygon anchor of accumulated decisions.

Integration:
  1. Import `blockchain_node` and `BLOCKCHAIN_TOOLS` into your graph builder.
  2. Add the node:  graph.add_node("blockchain", blockchain_node)
  3. Wire edges from any node that produces decisions to pass through blockchain:
       graph.add_edge("actor", "blockchain")
       graph.add_edge("learner", "blockchain")
     Or use a conditional edge if you want fire-and-forget:
       graph.add_conditional_edges("actor", route_after_actor,
           {"blockchain": "blockchain", "end": END})
  4. The node reads/writes these keys from AgentState:
       - pending_decisions  (List[dict])  — queue of unfinished DecisionRecords
       - latest_decision    (dict | None) — most recently fingerprinted record
       - blockchain_status  (dict)        — summary for dashboard
       - tamper_alerts      (List[str])   — raised when a hash mismatch is found

AgentState contract (add these fields to your TypedDict):

    class AgentState(TypedDict):
        # ... your existing fields ...
        pending_decisions:   list          # List[DecisionRecord as dict]
        latest_decision:     dict | None   # most recent DecisionRecord as dict
        blockchain_status:   dict          # see BlockchainStatusOutput below
        tamper_alerts:       list          # List[str]
        # Flag set by Actor/Learner when they produce a new decision
        new_decision:        dict | None   # DecisionRecord as dict, consumed here
"""



import httpx
import logging
import os
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, END

from blockchain_models import AnchorStatus, DecisionRecord, BlockchainState
from feature_9.db import init_db, upsert_decision, upsert_many_decisions, get_pending_decisions, upsert_batch
from blockchain_tools import (
    BLOCKCHAIN_TOOLS,
    get_last_batch_result,
    init_blockchain_tools,
    _pending_decisions,
)
from decision_hasher import compute_hash, fingerprint_and_sign, verify_hash
from merkle_tree import build_batch, attach_proofs_to_decisions
from smart_contract import PolygonClient

logger = logging.getLogger(__name__)

# F10 Integration Config
F10_API_URL = os.environ.get("F10_API_URL", "http://localhost:8010")

# ---------------------------------------------------------------------------
# Hourly anchor threshold — flush when this many decisions are pending OR
# when BATCH_INTERVAL_SECONDS have elapsed since last flush.
# ---------------------------------------------------------------------------
BATCH_SIZE_THRESHOLD    = 50     # flush early if queue fills up
BATCH_INTERVAL_SECONDS  = 3600   # 1 hour

_last_flush_time: float = 0.0


# ---------------------------------------------------------------------------
# Initialisation helper — call this once at graph startup
# ---------------------------------------------------------------------------

def build_blockchain_node() -> "BlockchainNodeRunner":
    """
    Factory function.  Creates the PolygonClient, connects, and returns a
    BlockchainNodeRunner instance that can be passed to graph.add_node().

    Usage in graph builder:
        from blockchain_node import build_blockchain_node
        bc_runner = build_blockchain_node()
        graph.add_node("blockchain", bc_runner)
    """
    client = PolygonClient()
    connected = client.connect()
    if not connected:
        logger.warning(
            "Polygon connection failed at startup — blockchain node will run "
            "in local-only mode (hashing + local Merkle, no on-chain anchoring)."
        )

    init_blockchain_tools(client)

    # Re-seed the in-memory queue from DB in case of process restart
    try:
        init_db()
        leftover = get_pending_decisions()
        if leftover:
            _pending_decisions.extend(leftover)
            logger.info("Re-seeded %d pending decisions from DB after restart.", len(leftover))
    except Exception as e:
        logger.warning("Could not seed from DB on startup: %s", e)

    return BlockchainNodeRunner(client=client)


# ---------------------------------------------------------------------------
# Main node class
# ---------------------------------------------------------------------------

class BlockchainNodeRunner:
    """
    LangGraph node callable.  Signature: (state: dict) -> dict (state patch).

    The node is intentionally stateless across calls — all mutable state
    lives in AgentState (passed in) or the module-level _pending_decisions
    queue (shared across the process lifetime).
    """

    def __init__(self, client: PolygonClient):
        self.client        = client
        self.private_key   = os.environ.get("POLYGON_PRIVATE_KEY", "")

    # ------------------------------------------------------------------
    # Entry point — called by LangGraph on every graph turn that reaches
    # this node.
    # ------------------------------------------------------------------

    def __call__(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the current AgentState.

        Reads:
          state["new_decision"]       — DecisionRecord dict produced this turn
          state["pending_decisions"]  — carried-over queue from previous turns
          state["blockchain_status"]  — previous status (for timing)

        Writes (returns patch):
          state["new_decision"]       — cleared to None
          state["latest_decision"]    — the freshly fingerprinted record
          state["pending_decisions"]  — updated queue
          state["blockchain_status"]  — updated summary
          state["tamper_alerts"]      — any new tamper detections
          state["messages"]           — appends an AIMessage summary
        """
        global _last_flush_time

        patch: Dict[str, Any] = {
            "new_decision":    None,
            "tamper_alerts":   state.get("tamper_alerts", []),
        }

        # ----------------------------------------------------------------
        # 1. Pick up new decision produced this graph turn
        # ----------------------------------------------------------------
        new_decision_raw = state.get("new_decision")
        freshly_fingerprinted: Optional[DecisionRecord] = None

        if new_decision_raw:
            try:
                record = DecisionRecord.model_validate(new_decision_raw)
                record = self._fingerprint(record)
                _pending_decisions.append(record)
                upsert_decision(record)   # persist immediately
                freshly_fingerprinted = record

                logger.info(
                    "[blockchain] Fingerprinted decision %s from agent=%s action=%s",
                    record.decision_id[:8],
                    record.agent_id,
                    record.action or "n/a",
                )

                # F10 INTEGRATION: Record CO2 savings if present
                if record.actual_co2_kg is not None and record.baseline_co2_kg is not None:
                    self._record_carbon_to_f10(record)

            except Exception as exc:
                logger.error("[blockchain] Failed to fingerprint new_decision: %s", exc)
                patch["tamper_alerts"] = patch["tamper_alerts"] + [
                    f"Fingerprinting failed for turn decision: {exc}"
                ]

        # ----------------------------------------------------------------
        # 2. Re-validate integrity of decisions already in state queue
        #    (detects any in-memory tampering between graph turns)
        # ----------------------------------------------------------------
        state_queue_raw: List[dict] = state.get("pending_decisions", [])
        validated_queue: List[DecisionRecord] = []
        new_alerts: List[str] = []

        for raw in state_queue_raw:
            try:
                rec = DecisionRecord.model_validate(raw)
                if rec.fingerprint_hash and not verify_hash(rec):
                    alert = (
                        f"TAMPER ALERT: decision {rec.decision_id[:8]} "
                        f"hash mismatch detected. Status set to TAMPERED."
                    )
                    logger.error(alert)
                    new_alerts.append(alert)
                    rec = rec.model_copy(update={"anchor_status": AnchorStatus.TAMPERED})
                validated_queue.append(rec)
            except Exception as exc:
                logger.warning("Could not validate queued decision: %s", exc)

        if new_alerts:
            patch["tamper_alerts"] = patch["tamper_alerts"] + new_alerts

        # Merge freshly fingerprinted into the combined queue
        # (_pending_decisions already has it; state queue may have older items
        #  that were carried without being in _pending_decisions if the process
        #  restarted — reconcile here)
        ids_already_in_module_queue = {d.decision_id for d in _pending_decisions}
        for rec in validated_queue:
            if rec.decision_id not in ids_already_in_module_queue:
                _pending_decisions.append(rec)

        # ----------------------------------------------------------------
        # 3. Decide whether to flush and anchor
        # ----------------------------------------------------------------
        elapsed = time.time() - _last_flush_time
        should_flush = (
            len(_pending_decisions) >= BATCH_SIZE_THRESHOLD
            or (elapsed >= BATCH_INTERVAL_SECONDS and len(_pending_decisions) >= 1)
        )

        batch_result: Optional[Dict] = None
        if should_flush:
            batch_result = self._flush_and_anchor()
            _last_flush_time = time.time()

        # ----------------------------------------------------------------
        # 4. Build state patch
        # ----------------------------------------------------------------
        # Convert pending queue back to dicts for AgentState
        pending_as_dicts = [d.model_dump() for d in _pending_decisions]

        patch["pending_decisions"] = pending_as_dicts
        patch["latest_decision"]   = (
            freshly_fingerprinted.model_dump() if freshly_fingerprinted else
            state.get("latest_decision")
        )

        # Blockchain status summary for the dashboard
        patch["blockchain_status"] = {
            "pending_count":    len(_pending_decisions),
            "chain_connected":  self.client.is_connected(),
            "last_flush_utc":   _last_flush_time or None,
            "last_batch":       batch_result,
            "contract_address": self.client.contract_address,
            "polygonscan_contract": self.client.address_url() if self.client.is_connected() else "",
        }

        # Append a concise message so the Reasoner can see what happened
        summary_parts = []
        if freshly_fingerprinted:
            summary_parts.append(
                f"Decision {freshly_fingerprinted.decision_id[:8]} fingerprinted "
                f"({freshly_fingerprinted.fingerprint_hash[:12] if freshly_fingerprinted.fingerprint_hash else 'n/a'}…). "
                f"Queue depth: {len(_pending_decisions)}."
            )
        if batch_result and batch_result.get("ok"):
            tx = batch_result.get("tx_hash", "")
            summary_parts.append(
                f"Batch anchored on Polygon. Root: {batch_result.get('merkle_root','')[:12]}… "
                f"TX: {tx[:12] if tx else 'n/a'}… "
                f"Decisions: {batch_result.get('decision_count', 0)}. "
                f"Polygonscan: {batch_result.get('polygonscan_url', '')}."
            )
        if new_alerts:
            summary_parts.append(f"⚠️ {len(new_alerts)} tamper alert(s) raised.")

        if summary_parts:
            patch["messages"] = [AIMessage(content="[blockchain] " + " | ".join(summary_parts))]

        return patch

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_carbon_to_f10(self, record: DecisionRecord) -> None:
        """
        Mandatory Integration: Report carbon savings to Feature 10 (Learner Agent).
        This accumulates the live CO2 counter on the dashboard.
        """
        try:
            # Sync call via httpx (used within LangGraph sync node)
            resp = httpx.post(
                f"{F10_API_URL}/carbon/record",
                params={
                    "actual_co2_kg": record.actual_co2_kg,
                    "baseline_co2_kg": record.baseline_co2_kg
                },
                timeout=2.0
            )
            if resp.status_code == 200:
                logger.info("[blockchain->f10] Carbon recorded successfully.")
            else:
                logger.warning("[blockchain->f10] Carbon recording failed: %s", resp.text)
        except Exception as exc:
            logger.error("[blockchain->f10] Could not connect to F10 Learner API: %s", exc)

    def _fingerprint(self, record: DecisionRecord) -> DecisionRecord:
        """Fingerprint and optionally sign a decision record."""
        if self.private_key:
            return fingerprint_and_sign(record, self.private_key)
        else:
            h = compute_hash(record)
            return record.model_copy(update={
                "fingerprint_hash": h,
                "anchor_status":    AnchorStatus.PENDING,
            })

    def _flush_and_anchor(self) -> Dict[str, Any]:
        """
        Build Merkle batch, anchor on Polygon, update records.
        Mutates _pending_decisions in-place to reflect new statuses.
        """
        if not _pending_decisions:
            return {"ok": False, "error": "Nothing to flush."}

        to_process = _pending_decisions[:]
        _pending_decisions.clear()

        try:
            batch = build_batch(to_process)
        except ValueError as exc:
            _pending_decisions[:] = to_process + _pending_decisions
            logger.error("Batch build failed: %s", exc)
            return {"ok": False, "error": str(exc)}

        # Attach Merkle proofs to each record
        updated = attach_proofs_to_decisions(to_process, batch)

        # Anchor on-chain
        tx_hash: Optional[str] = None
        block: Optional[int]   = None

        if self.client.is_connected():
            tx_hash = self.client.anchor_batch(
                merkle_root    = batch.merkle_root,
                batch_id       = batch.batch_id,
                decision_count = len(batch.decision_ids),
            )
            if tx_hash:
                try:
                    receipt = self.client.w3.eth.get_transaction_receipt(tx_hash)
                    block   = receipt.blockNumber
                except Exception:
                    pass

        final_status = AnchorStatus.ANCHORED if tx_hash else AnchorStatus.BATCHED

        # Finalize decision records
        finalized: List[DecisionRecord] = []
        for d in updated:
            finalized.append(d.model_copy(update={
                "anchor_status":      final_status,
                "blockchain_tx_hash": tx_hash,
                "blockchain_block":   block,
                "merkle_root":        batch.merkle_root,
            }))

        # Persist everything to DB
        upsert_batch(batch)
        upsert_many_decisions(finalized)

        # Any decisions that couldn't be anchored go back to pending
        # (in BATCHED state — they'll be re-attempted next flush)
        if final_status == AnchorStatus.BATCHED:
            _pending_decisions.extend(finalized)

        polygonscan_url = self.client.tx_url(tx_hash) if tx_hash else ""

        return {
            "ok":              True,
            "batch_id":        batch.batch_id,
            "merkle_root":     batch.merkle_root,
            "tx_hash":         tx_hash or "",
            "decision_count":  len(batch.decision_ids),
            "anchor_status":   final_status.value,
            "polygonscan_url": polygonscan_url,
            "finalized":       [d.model_dump() for d in finalized],
        }


# ---------------------------------------------------------------------------
# Convenience: verification endpoint callable by any node or API layer
# ---------------------------------------------------------------------------

def verify_decision_record(
    record: DecisionRecord,
    client: Optional[PolygonClient] = None,
) -> Dict[str, Any]:
    """
    Standalone verification function — can be called from the API layer,
    dashboard WebSocket handler, or any other agent node that wants to
    check a specific decision's integrity.

    Does NOT require the BlockchainNodeRunner instance.
    """
    from blockchain_tools import verify_decision
    return verify_decision.invoke({"decision_json": record.model_dump_json()})


# ---------------------------------------------------------------------------
# Graph builder helper — use this to wire Feature 9 into your existing graph
# ---------------------------------------------------------------------------

def add_blockchain_to_graph(
    graph_builder: StateGraph,
    route_back_to: str = END,
) -> "BlockchainNodeRunner":
    """
    Convenience helper that adds the blockchain node to an existing
    StateGraph and returns the runner (you need it for verification calls).

    Example usage in your main graph_builder.py:
        from blockchain_node import add_blockchain_to_graph
        bc = add_blockchain_to_graph(graph, route_back_to="observer")
        graph.add_edge("actor",   "blockchain")
        graph.add_edge("learner", "blockchain")

    The route_back_to edge is added automatically so the graph doesn't dead-end.
    """
    runner = build_blockchain_node()
    graph_builder.add_node("blockchain", runner)
    graph_builder.add_edge("blockchain", route_back_to)
    return runner

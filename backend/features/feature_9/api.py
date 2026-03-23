from __future__ import annotations
"""
Feature 9: API Layer
FastAPI routes for the blockchain audit feature.

Mount this router onto your main FastAPI app:

    from feature9_blockchain.api import router as blockchain_router
    app.include_router(blockchain_router, prefix="/blockchain", tags=["blockchain"])

Endpoints:
    GET  /blockchain/decision/{id}          — fetch + verify a decision
    POST /blockchain/verify                 — verify arbitrary decision JSON
    GET  /blockchain/status                 — queue + chain status
    GET  /blockchain/batches                — recent Merkle batches
    POST /blockchain/flush                  — force immediate anchor (admin)
    GET  /blockchain/tamper-demo/{id}       — demo: show hash breaking
    WS   /blockchain/ws/status             — live status feed for dashboard
"""

import asyncio
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from blockchain_models import DecisionRecord, VerificationResult
from blockchain_tools import (
    flush_and_anchor_batch,
    get_queue_status,
    tamper_demo,
    verify_decision,
    _pending_decisions,
)
from feature_9.db import (
    get_batch,
    get_decision,
    get_recent_batches,
    get_recent_decisions,
    mark_tampered,
)
from decision_hasher import compute_hash, verify_hash

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# REST: fetch + verify a decision
# ---------------------------------------------------------------------------

@router.get("/decision/{decision_id}", response_model=Dict[str, Any])
async def get_and_verify_decision(decision_id: str):
    """
    Fetch a decision from the DB, re-compute its hash, verify its Merkle proof.
    Returns the full record plus a verification summary.
    Used by the dashboard audit panel.
    """
    record = get_decision(decision_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found.")

    result = verify_decision.invoke({"decision_json": record.model_dump_json()})

    # Auto-mark tampered in DB if verification failed
    if not result.get("verified") and "TAMPER" in result.get("reason", ""):
        mark_tampered(decision_id)

    return {
        "decision":     record.model_dump(),
        "verification": result,
    }


# ---------------------------------------------------------------------------
# REST: verify arbitrary decision JSON (for external auditors / partners)
# ---------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    decision_json: str


@router.post("/verify", response_model=Dict[str, Any])
async def verify_decision_endpoint(body: VerifyRequest):
    """
    Permissionless verification endpoint.
    Any party (partner, regulator, auditor) can POST a decision record
    and get back whether it's intact and Merkle-proven.
    No authentication required — matches the blockchain's permissionless model.
    """
    result = verify_decision.invoke({"decision_json": body.decision_json})
    return result


# ---------------------------------------------------------------------------
# REST: queue + chain status (for dashboard header badge)
# ---------------------------------------------------------------------------

@router.get("/status", response_model=Dict[str, Any])
async def blockchain_status():
    status = get_queue_status.invoke({})
    batches = get_recent_batches(limit=5)
    return {
        **status,
        "recent_batches": [
            {
                "batch_id":       b.batch_id,
                "decision_count": len(b.decision_ids),
                "merkle_root":    b.merkle_root,
                "anchored":       b.blockchain_tx is not None,
                "blockchain_tx":  b.blockchain_tx,
                "anchored_utc":   b.anchored_utc,
            }
            for b in batches
        ],
    }


# ---------------------------------------------------------------------------
# REST: recent decisions (audit log table in dashboard)
# ---------------------------------------------------------------------------

@router.get("/decisions", response_model=Dict[str, Any])
async def list_decisions(limit: int = 50):
    records = get_recent_decisions(limit=limit)
    return {
        "decisions": [
            {
                "decision_id":      r.decision_id,
                "agent_id":         r.agent_id,
                "tier":             r.tier.value,
                "action":           r.action,
                "timestamp_utc":    r.timestamp_utc,
                "fingerprint_hash": r.fingerprint_hash,
                "anchor_status":    r.anchor_status.value,
                "blockchain_tx":    r.blockchain_tx_hash,
            }
            for r in records
        ]
    }


# ---------------------------------------------------------------------------
# REST: recent Merkle batches
# ---------------------------------------------------------------------------

@router.get("/batches", response_model=Dict[str, Any])
async def list_batches(limit: int = 10):
    batches = get_recent_batches(limit=limit)
    return {
        "batches": [
            {
                "batch_id":       b.batch_id,
                "decision_count": len(b.decision_ids),
                "merkle_root":    b.merkle_root,
                "blockchain_tx":  b.blockchain_tx,
                "anchored_utc":   b.anchored_utc,
                "anchored_block": b.anchored_block,
            }
            for b in batches
        ]
    }


# ---------------------------------------------------------------------------
# REST: force flush (admin / demo trigger)
# ---------------------------------------------------------------------------

@router.post("/flush", response_model=Dict[str, Any])
async def force_flush():
    """Force an immediate Merkle batch + anchor. Useful during demo."""
    result = flush_and_anchor_batch.invoke({"force": True})
    return result


# ---------------------------------------------------------------------------
# REST: tamper demo endpoint (for the judge demo moment)
# ---------------------------------------------------------------------------

@router.get("/tamper-demo/{decision_id}", response_model=Dict[str, Any])
async def tamper_demo_endpoint(decision_id: str, field: str = "action"):
    """
    Demo endpoint: fetch a real decision, mutate one field, show hash breaks.
    This is the 'Try to lie about what this AI did. You cannot.' moment.
    """
    record = get_decision(decision_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Decision {decision_id} not found.")

    result = tamper_demo.invoke({
        "decision_json":   record.model_dump_json(),
        "field_to_mutate": field,
    })
    return {
        "decision_id":    decision_id,
        "mutated_field":  field,
        **result,
    }


# ---------------------------------------------------------------------------
# WebSocket: live status feed for dashboard
# ---------------------------------------------------------------------------

_ws_clients: list[WebSocket] = []


@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """
    Pushes blockchain status every 5 seconds.
    Dashboard connects here for the live 'Pending: N | Chain: ✅' badge.
    """
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            status = get_queue_status.invoke({})
            await websocket.send_json(status)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WS client disconnected: %s", exc)
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


async def broadcast_anchor_event(batch_result: Dict[str, Any]) -> None:
    """
    Called by blockchain_node after a successful anchor so the dashboard
    immediately shows the Polygonscan link without waiting for next WS poll.
    """
    if not _ws_clients:
        return
    payload = json.dumps({"type": "anchor_complete", **batch_result})
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)

from __future__ import annotations
"""
HITL (Human-in-the-Loop) Service — In-memory approval card store.
Cards are created when autonomy tier requires human review.
"""
import logging
import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# In-memory store for demo / when Supabase not configured
_cards: Dict[str, dict] = {}


async def create_approval_card(
    decision_id: str,
    incident_context: dict,
    pareto_options: list,
    autonomy_decision: dict,
    stress_results: dict,
    aqi_data: dict,
    policy: str,
) -> dict:
    """Create a HITL approval card for human review."""
    card = {
        "card_id": decision_id,
        "status": "PENDING",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "resolved_at": None,
        "incident_context": incident_context,
        "pareto_options": pareto_options,
        "autonomy_decision": autonomy_decision,
        "stress_results": stress_results,
        "aqi_data": aqi_data,
        "policy": policy,
        "resolution": None,
    }
    _cards[decision_id] = card
    logger.info(f"HITL card created: {decision_id}")
    return card


async def resolve_card(
    card_id: str,
    action: str,
    selected_option_rank: int = 1,
    operator_notes: str = "",
) -> dict:
    """Resolve a HITL card with operator decision."""
    card = _cards.get(card_id)
    if not card:
        return {"error": f"Card {card_id} not found", "resolved": False}

    card["status"] = "RESOLVED"
    card["resolved_at"] = datetime.datetime.utcnow().isoformat()
    card["resolution"] = {
        "action": action,
        "selected_option_rank": selected_option_rank,
        "operator_notes": operator_notes,
    }
    logger.info(f"HITL card resolved: {card_id} → {action}")
    return card


async def get_pending_cards() -> List[dict]:
    """Get all pending HITL cards."""
    return [c for c in _cards.values() if c.get("status") == "PENDING"]


async def get_card(card_id: str) -> Optional[dict]:
    """Get a specific card by ID."""
    return _cards.get(card_id)

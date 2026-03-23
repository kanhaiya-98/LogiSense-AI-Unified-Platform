from __future__ import annotations
"""
Zen Platform — Unified Supabase client
Handles persistence for all three modules.
"""
import os
from typing import Optional
from supabase import create_client, Client

_client: Optional[Client] = None


def get_supabase() -> Optional[Client]:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if url and key and url != "your_supabase_project_url":
            _client = create_client(url, key)
    return _client


# ── ZenDec ────────────────────────────────────────────────────────────────────

def save_demand_decision(decision_id: str, input_data: dict, result: dict, insights: str):
    """Save ZenDec carrier decision to demand_forecasts table."""
    db = get_supabase()
    if not db:
        return None
    try:
        return db.table("demand_forecasts").insert({
            "input_data": input_data,
            "forecast_result": result,
            "gemini_insights": insights,
        }).execute()
    except Exception as e:
        print(f"[Supabase] demand save failed: {e}")
        return None


# ── ZenRTO ────────────────────────────────────────────────────────────────────

def save_route_score(input_data: dict, result: dict, explanation: str):
    """Save ZenRTO order risk score to route_optimizations table."""
    db = get_supabase()
    if not db:
        return None
    try:
        return db.table("route_optimizations").insert({
            "input_stops": input_data,
            "optimized_route": result,
            "total_distance": result.get("rto_score", 0),
            "gemini_explanation": explanation,
        }).execute()
    except Exception as e:
        print(f"[Supabase] route save failed: {e}")
        return None


# ── ZenETA ────────────────────────────────────────────────────────────────────

def save_eta_prediction(features: dict, eta: float, confidence: float, summary: str):
    """Save ZenETA prediction to eta_predictions table."""
    db = get_supabase()
    if not db:
        return None
    try:
        return db.table("eta_predictions").insert({
            "input_features": features,
            "predicted_eta": eta,
            "confidence_score": confidence,
            "gemini_summary": summary,
        }).execute()
    except Exception as e:
        print(f"[Supabase] ETA save failed: {e}")
        return None

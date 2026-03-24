from __future__ import annotations
"""
routes.py — FastAPI endpoints for Feature 8 Explainability.
The React frontend calls these endpoints to fetch Plotly chart JSON.
These endpoints are stateless — they use the LangGraph state store.
"""

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from typing import Any, Optional
import pandas as pd

from feature_8.agent.shap_engine import SHAPEngine
from feature_8.agent.chart_generators import build_heatmap, build_risk_matrix, build_waterfall

router = APIRouter(prefix="/api/explainability", tags=["explainability"])


# ── Request / Response models ────────────────────────────────────────────────

class ExplainRequest(BaseModel):
    """
    Payload sent by the frontend (or another agent via HTTP).
    Contains the prediction results and the feature matrix.
    """
    predictions: list[dict]       # [{child_id, risk_score, ...}, ...]
    features: list[dict]          # Feature rows as list of dicts (one per child)
    model_artifact_key: str       # Key to retrieve stored model from model registry


class WaterfallRequest(BaseModel):
    shipment_idx: int
    predictions: list[dict]
    features: list[dict]
    model_artifact_key: str


# ── Model registry (in-memory, replace with Redis/DB in production) ──────────
# This stores models after the ML prediction node trains/loads them.
_MODEL_REGISTRY: dict[str, Any] = {}


def register_model(key: str, model: Any):
    """Called by the ML prediction agent after training to register model."""
    _MODEL_REGISTRY[key] = model


def get_model(key: str) -> Any:
    if key not in _MODEL_REGISTRY:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{key}' not found in registry. Run ML prediction first."
        )
    return _MODEL_REGISTRY[key]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/heatmap")
async def get_heatmap(req: ExplainRequest):
    """Returns Plotly JSON for SHAP Feature Impact Heatmap."""
    model = get_model(req.model_artifact_key)
    X_df = pd.DataFrame(req.features)
    engine = SHAPEngine(model=model, X_df=X_df)
    return {"figure": build_heatmap(engine, req.predictions)}


@router.post("/matrix")
async def get_matrix(req: ExplainRequest):
    """Returns Plotly JSON for Risk Stratification Matrix."""
    model = get_model(req.model_artifact_key)
    X_df = pd.DataFrame(req.features)
    engine = SHAPEngine(model=model, X_df=X_df)
    return {"figure": build_risk_matrix(engine, X_df, req.predictions)}


@router.post("/waterfall")
def get_waterfall(req: WaterfallRequest):
    """Generates the SHAP Waterfall for a specific shipment."""
    try:
        model = get_model(req.model_artifact_key)
        X_df = pd.DataFrame(req.features)
        
        engine = SHAPEngine(model, X_df)
        engine.compute_shap()
        
        if req.shipment_idx < 0 or req.shipment_idx >= len(req.predictions):
            raise HTTPException(status_code=400, detail="shipment_idx out of range")
        
        # We don't cache waterfall, generate on fly (it's fast enough for single shipment)
        return {"figure": build_waterfall(engine, req.shipment_idx, req.predictions)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/all")
async def get_all_charts(req: ExplainRequest):
    """
    Returns all 3 charts in one call — optimized for initial page load.
    Frontend calls this once, renders all charts together.
    """
    model = get_model(req.model_artifact_key)
    X_df = pd.DataFrame(req.features)
    engine = SHAPEngine(model=model, X_df=X_df)

    highest_risk_idx = max(range(len(req.predictions)), key=lambda i: req.predictions[i]["risk_score"])

    return {
        "heatmap": build_heatmap(engine, req.predictions),
        "matrix": build_risk_matrix(engine, X_df, req.predictions),
        "waterfall": build_waterfall(engine, highest_risk_idx, req.predictions),
        "top_features": engine.get_top_features(k=8),
        "shipments_analyzed": len(req.predictions),
        "top_driver": engine.get_top_features(k=1)[0],
    }


@router.post("/register-model")
async def register_model_endpoint(
    key: str = Body(...),
    # In production: receive model as pickle bytes or load from artifact store
):
    """
    Called by ML prediction agent to register a trained model.
    In production, this would load from S3/artifact store.
    """
    # Placeholder — your ML agent will call register_model() directly in-process
    return {"status": "Model registration must be done in-process by ML agent", "key": key}

from __future__ import annotations
"""
mock_ml_node.py — Simulates the ML Prediction Agent (Feature 5) output.

PURPOSE:
  Lets you run and test Feature 8 completely standalone,
  without needing Feature 5 to be built yet.
  Also serves as the exact contract that Feature 5 MUST follow.

USAGE:
  from feature_8.mocks.mock_ml_node import run_mock_ml_prediction
  state = run_mock_ml_prediction(n_children=60)
  # Now pass state into explainability_node(state)

CONTRACT FOR FEATURE 5 TEAM:
  Your ML prediction node must write these exact keys to GraphState:
    - state["model"]       → trained sklearn-compatible model
    - state["X_df"]        → pd.DataFrame, same shape used for .predict()
    - state["predictions"] → list of dicts: [{child_id, risk_score, ...}]
    - state["feature_names"] → list of column name strings
"""

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from typing import Any


def generate_synthetic_shipments(n: int = 60, seed: int = 42) -> pd.DataFrame:
    """
    Generates a synthetic dataset matching the expected Logistics feature schema.
    """
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "eta_delay_minutes":   rng.integers(0, 120, n),
        "carrier_reliability": rng.integers(50, 100, n),
        "weather_risk_index":  rng.integers(0, 10, n),
        "route_congestion":    rng.integers(0, 100, n),
        "border_delay":        rng.integers(0, 2, n),
        "fragile_cargo":       rng.integers(0, 2, n),
        "priority_level":      rng.integers(1, 5, n),
        "historical_loss":     rng.integers(0, 3, n),
    })


def train_mock_model(X: pd.DataFrame, y: pd.Series) -> Any:
    """Trains a quick XGBoost classifier. Feature 5 should replace this with their real model."""
    if len(y.unique()) < 2:
        # Hack to ensure XGBoost doesn't crash if all shipments are on-time
        y.iloc[-1] = 1 - y.iloc[0]

    model = XGBClassifier(
        n_estimators=50,
        max_depth=4,
        learning_rate=0.1,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X, y)
    return model


def run_live_ml_prediction() -> dict:
    """
    Fetches actual live shipments from LogiSense DB, maps them to ML features,
    trains the dummy Explainer, and generates predictions.
    """
    from db.supabase_client import get_active_shipments
    import hashlib

    shipments = get_active_shipments()

    if not shipments:
        # DB Empty fallback
        return run_mock_ml_prediction(60)

    df_rows = []
    shipment_ids = []

    for s in shipments:
        delay = max(0, s.get("eta_minutes_current", 0) - s.get("eta_minutes_original", 0))
        dist = s.get("distance_km", 500)
        val = s.get("order_value_inr", 1000)
        
        c_id = str(s.get("carrier_id", "CAR-01"))
        rel = 50 + (int(hashlib.md5(c_id.encode()).hexdigest(), 16) % 51)
        
        dest = str(s.get("destination_city", "City"))
        weather = int(hashlib.md5(dest.encode()).hexdigest(), 16) % 11
        
        df_rows.append({
            "eta_delay_minutes": delay,
            "carrier_reliability": rel,
            "weather_risk_index": weather,
            "route_congestion": int(dist) % 100,
            "border_delay": 1 if dist > 1000 else 0,
            "fragile_cargo": 0,
            "priority_level": max(1, min(5, int(val) // 1000)),
            "historical_loss": int(hashlib.md5(str(s.get("warehouse_id", "")).encode()).hexdigest(), 16) % 4,
        })
        shipment_ids.append(s.get("shipment_id"))

    X = pd.DataFrame(df_rows)
    
    # Create composite score so the XGBoost model utilizes multiple features 
    # and the SHAP heatmap looks rich
    risk_score = (
        X["eta_delay_minutes"] * 2.0
        + (100 - X["carrier_reliability"]) * 1.5
        + X["weather_risk_index"] * 5.0
        + X["route_congestion"] * 0.5
        + X["border_delay"] * 20.0
        + X["historical_loss"] * 10.0
    )
    risk_score += np.random.normal(0, 5, size=len(X))
    y = (risk_score > risk_score.median()).astype(int)
    
    model = train_mock_model(X, y)

    probs = model.predict_proba(X)
    # If binary classification, take column 1. If 1 class (should be fixed above), take col 0
    probs_1 = probs[:, 1] if probs.shape[1] > 1 else probs[:, 0]

    predictions = [
        {
            "shipment_id": shipment_ids[i],
            "risk_score": float(round(p * 100, 2)),
            "risk_label": _risk_label(p * 100),
            **s # inject original shipment metadata for tooltip
        }
        for i, (p, s) in enumerate(zip(probs_1, shipments))
    ]

    return {
        "model": model,
        "X_df": X,
        "predictions": predictions,
        "feature_names": list(X.columns),
        "raw_data": X.to_dict(orient="records"),
        "query": None,
        "error": None,
        "current_node": "ml_prediction",
        "shap_heatmap_json": None,
        "shap_matrix_json": None,
        "shap_waterfall_json": None,
        "top_features": None,
        "shap_values_raw": None,
    }

def run_mock_ml_prediction(n_shipments: int = 60) -> dict:
    """
    Returns a GraphState-compatible dict as if Feature 5 had run.
    """
    X = generate_synthetic_shipments(n_shipments)
    
    # Create composite score so the XGBoost model utilizes multiple features
    risk_score = (
        X["eta_delay_minutes"] * 2.0
        + (100 - X["carrier_reliability"]) * 1.5
        + X["weather_risk_index"] * 5.0
        + X["route_congestion"] * 0.5
        + X["border_delay"] * 20.0
        + X["historical_loss"] * 10.0
    )
    risk_score += np.random.normal(0, 5, size=len(X))
    y = (risk_score > risk_score.median()).astype(int)

    model = train_mock_model(X, y)

    probs = model.predict_proba(X)[:, 1]
    predictions = [
        {
            "shipment_id": f"SHP{i:03d}",
            "risk_score": float(round(p * 100, 2)),
            "risk_label": _risk_label(p * 100),
        }
        for i, p in enumerate(probs)
    ]

    return {
        "model": model,
        "X_df": X,
        "predictions": predictions,
        "feature_names": list(X.columns),
        "raw_data": X.to_dict(orient="records"),
        "query": None,
        "error": None,
        "current_node": "ml_prediction",
        # Feature 8 output keys — not yet populated
        "shap_heatmap_json": None,
        "shap_matrix_json": None,
        "shap_waterfall_json": None,
        "top_features": None,
        "shap_values_raw": None,
    }


def _risk_label(score: float) -> str:
    if score < 25:   return "LOW"
    if score < 50:   return "MEDIUM"
    if score < 70:   return "HIGH"
    return "CRITICAL"

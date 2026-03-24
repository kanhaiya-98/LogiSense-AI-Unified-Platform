from __future__ import annotations
"""
state_schema.py — Shared LangGraph TypedDict state for all agents.
Feature 8 reads: predictions, model, X_df
Feature 8 writes: shap_heatmap_json, shap_matrix_json, shap_waterfall_json, top_features
"""

from typing import TypedDict, Optional, Any
import pandas as pd


class GraphState(TypedDict):
    # ── Input from upstream agents ──────────────────────────────────────────
    raw_data: Optional[list[dict]]           # Feature 3: raw ingested records
    predictions: Optional[list[dict]]        # Feature 5: [{child_id, risk_score, ...}]
    model: Optional[Any]                     # Feature 5: trained sklearn/XGBoost model
    X_df: Optional[Any]                      # Feature 5: pd.DataFrame used for prediction
    feature_names: Optional[list[str]]       # Feature 5: column names in order

    # ── Output written by Feature 8 ─────────────────────────────────────────
    shap_heatmap_json: Optional[dict]        # Plotly figure JSON — heatmap
    shap_matrix_json: Optional[dict]         # Plotly figure JSON — risk matrix
    shap_waterfall_json: Optional[dict]      # Plotly figure JSON — waterfall
    top_features: Optional[list[str]]        # Top-k features by mean |SHAP|
    shap_values_raw: Optional[list]          # Raw SHAP values array (for downstream agents)

    # ── Metadata ────────────────────────────────────────────────────────────
    query: Optional[str]                     # Natural language query from user/orchestrator
    error: Optional[str]                     # Error message if any node fails
    current_node: Optional[str]              # Which node is currently active

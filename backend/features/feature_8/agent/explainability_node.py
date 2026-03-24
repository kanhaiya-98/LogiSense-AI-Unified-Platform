from __future__ import annotations
"""
explainability_node.py — LangGraph node for Feature 8.
This is the agent node that plugs into the LangGraph StateGraph.

Usage in your main graph:
    from feature_8.agent.explainability_node import explainability_node
    graph.add_node("explainability", explainability_node)
    graph.add_edge("ml_prediction", "explainability")
"""

import logging
from typing import Any

from feature_8.agent.state_schema import GraphState
from feature_8.agent.shap_engine import SHAPEngine
from feature_8.agent.chart_generators import build_heatmap, build_risk_matrix, build_waterfall

logger = logging.getLogger(__name__)


def explainability_node(state: GraphState) -> GraphState:
    """
    LangGraph node function.
    Reads model + predictions from state, writes all chart JSONs back.
    
    This node is triggered after the ML prediction node completes.
    It produces 3 visualizations and writes them to shared graph state
    so downstream agents (report generator, dashboard) can consume them.
    """
    logger.info("[Feature 8] Explainability node started.")

    # ── 1. Validate required inputs from upstream agents ────────────────────
    model = state.get("model")
    X_df = state.get("X_df")
    predictions = state.get("predictions")

    if model is None:
        return {**state, "error": "[Feature 8] No model found in state. ML prediction node must run first."}
    if X_df is None or len(X_df) == 0:
        return {**state, "error": "[Feature 8] No feature data (X_df) in state."}
    if predictions is None or len(predictions) == 0:
        return {**state, "error": "[Feature 8] No predictions in state."}

    try:
        # ── 2. Run SHAP engine ───────────────────────────────────────────────
        logger.info(f"[Feature 8] Running SHAP on {len(X_df)} records, model={type(model).__name__}")
        engine = SHAPEngine(model=model, X_df=X_df)
        top_features = engine.get_top_features(k=8)
        logger.info(f"[Feature 8] Top features: {top_features}")

        # ── 3. Generate all 3 charts ─────────────────────────────────────────
        heatmap_json = build_heatmap(engine, predictions)
        logger.info("[Feature 8] Heatmap built.")

        matrix_json = build_risk_matrix(engine, X_df, predictions)
        logger.info("[Feature 8] Risk matrix built.")

        # 2. Build single Waterfall for the highest risk shipment
        highest_risk_idx = max(range(len(predictions)), key=lambda i: predictions[i]["risk_score"])
        waterfall_json = build_waterfall(engine, highest_risk_idx, predictions)
        logger.info(f"[Feature 8] Waterfall built for shipment_idx={highest_risk_idx}.")

        # ── 4. Write back to shared state ────────────────────────────────────
        return {
            **state,
            "shap_heatmap_json": heatmap_json,
            "shap_matrix_json": matrix_json,
            "shap_waterfall_json": waterfall_json,
            "top_features": top_features,
            "shap_values_raw": engine.shap_values.tolist(),
            "current_node": "explainability",
            "error": None,
        }

    except Exception as exc:
        logger.exception("[Feature 8] Error in explainability node.")
        return {**state, "error": f"[Feature 8] {str(exc)}", "current_node": "explainability"}


def explainability_node_for_shipment(state: GraphState, shipment_idx: int) -> GraphState:
    """
    Optional sub-graph node: builds just the waterfall chart for a specific shipment.
    Useful if a UI user clicks on a single shipment in the heatmap and requests a deep dive.
    """
    model = state.get("model")
    X_df = state.get("X_df")
    predictions = state.get("predictions")

    if not all([model, X_df is not None, predictions]):
        return {**state, "error": "[Feature 8] Cannot regenerate waterfall — missing state."}

    try:
        engine = SHAPEngine(model=model, X_df=X_df)
        waterfall_json = build_waterfall(engine, shipment_idx, predictions)
        return {**state, "shap_waterfall_json": waterfall_json, "error": None}
    except Exception as exc:
        return {**state, "error": f"[Feature 8] Waterfall regen failed: {str(exc)}"}

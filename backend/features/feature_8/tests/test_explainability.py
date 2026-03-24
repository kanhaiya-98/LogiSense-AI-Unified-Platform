from __future__ import annotations
"""
tests/test_explainability.py
Run: pytest feature_8/tests/test_explainability.py -v
"""

import numpy as np
import pandas as pd
import pytest
from xgboost import XGBClassifier

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.shap_engine import SHAPEngine
from agent.chart_generators import build_heatmap, build_risk_matrix, build_waterfall
from agent.explainability_node import explainability_node
from agent.state_schema import GraphState


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_data():
    np.random.seed(42)
    n = 60
    df = pd.DataFrame({
        "days_overdue":       np.random.randint(0, 120, n),
        "vaccines_missed":    np.random.randint(0, 5, n),
        "district_outbreak":  np.random.randint(0, 2, n),
        "reminders_ignored":  np.random.randint(0, 4, n),
        "high_risk_state":    np.random.randint(0, 2, n),
        "child_age_months":   np.random.randint(1, 60, n),
        "sibling_history":    np.random.randint(0, 2, n),
        "gender_male":        np.random.randint(0, 2, n),
    })
    y = (df["days_overdue"] > 45).astype(int)
    return df, y


@pytest.fixture
def trained_model(synthetic_data):
    X, y = synthetic_data
    model = XGBClassifier(n_estimators=20, max_depth=3, random_state=42, eval_metric="logloss")
    model.fit(X, y)
    return model


@pytest.fixture
def predictions(synthetic_data, trained_model):
    X, _ = synthetic_data
    probs = trained_model.predict_proba(X)[:, 1]
    return [
        {"child_id": f"C{i:03d}", "risk_score": float(p * 100)}
        for i, p in enumerate(probs)
    ]


@pytest.fixture
def mock_state(synthetic_data, trained_model, predictions) -> GraphState:
    X, _ = synthetic_data
    return GraphState(
        raw_data=None,
        predictions=predictions,
        model=trained_model,
        X_df=X,
        feature_names=list(X.columns),
        shap_heatmap_json=None,
        shap_matrix_json=None,
        shap_waterfall_json=None,
        top_features=None,
        shap_values_raw=None,
        query=None,
        error=None,
        current_node=None,
    )


# ── SHAP Engine tests ─────────────────────────────────────────────────────────

def test_shap_engine_builds(synthetic_data, trained_model):
    X, _ = synthetic_data
    engine = SHAPEngine(model=trained_model, X_df=X)
    assert engine.shap_values.shape == (len(X), len(X.columns))


def test_top_features_returned(synthetic_data, trained_model):
    X, _ = synthetic_data
    engine = SHAPEngine(model=trained_model, X_df=X)
    top = engine.get_top_features(k=4)
    assert len(top) == 4
    assert all(f in X.columns for f in top)


def test_waterfall_data_structure(synthetic_data, trained_model):
    X, _ = synthetic_data
    engine = SHAPEngine(model=trained_model, X_df=X)
    data = engine.get_waterfall_data(0)
    assert "expected_value" in data
    assert "features" in data
    assert "shap_values" in data
    assert len(data["features"]) == len(X.columns)


# ── Chart generator tests ─────────────────────────────────────────────────────

def test_heatmap_is_valid_plotly(synthetic_data, trained_model, predictions):
    X, _ = synthetic_data
    engine = SHAPEngine(model=trained_model, X_df=X)
    fig = build_heatmap(engine, predictions)
    assert "data" in fig
    assert "layout" in fig
    assert len(fig["data"]) >= 2  # risk score bar + heatmap


def test_matrix_is_valid_plotly(synthetic_data, trained_model, predictions):
    X, _ = synthetic_data
    engine = SHAPEngine(model=trained_model, X_df=X)
    fig = build_risk_matrix(engine, X, predictions)
    assert "data" in fig
    assert "layout" in fig


def test_waterfall_is_valid_plotly(synthetic_data, trained_model, predictions):
    X, _ = synthetic_data
    engine = SHAPEngine(model=trained_model, X_df=X)
    fig = build_waterfall(engine, 0, predictions)
    assert "data" in fig
    assert "layout" in fig


# ── LangGraph node tests ──────────────────────────────────────────────────────

def test_node_writes_all_outputs(mock_state):
    result = explainability_node(mock_state)
    assert result["error"] is None
    assert result["shap_heatmap_json"] is not None
    assert result["shap_matrix_json"] is not None
    assert result["shap_waterfall_json"] is not None
    assert isinstance(result["top_features"], list)
    assert len(result["top_features"]) > 0
    assert result["shap_values_raw"] is not None


def test_node_handles_missing_model(mock_state):
    bad_state = {**mock_state, "model": None}
    result = explainability_node(bad_state)
    assert result["error"] is not None
    assert "model" in result["error"].lower()


def test_node_handles_empty_predictions(mock_state):
    bad_state = {**mock_state, "predictions": []}
    result = explainability_node(bad_state)
    assert result["error"] is not None


def test_node_preserves_upstream_state(mock_state):
    """Feature 8 must not delete keys written by other agents."""
    mock_state["raw_data"] = [{"child_id": "C001"}]
    result = explainability_node(mock_state)
    assert result["raw_data"] == [{"child_id": "C001"}]

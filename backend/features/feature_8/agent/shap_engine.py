from __future__ import annotations
"""
shap_engine.py — Computes SHAP values dynamically from any sklearn-compatible model.
No hardcoded feature names, no hardcoded data.
Receives model + DataFrame → returns structured SHAP payload.
"""

import shap
import numpy as np
import pandas as pd
from typing import Any


class SHAPEngine:
    """
    Dynamically computes SHAP explanations for any tree-based or linear model.
    Selects explainer type automatically based on model class.
    """

    TREE_MODELS = (
        "XGBClassifier", "XGBRegressor",
        "RandomForestClassifier", "RandomForestRegressor",
        "GradientBoostingClassifier", "GradientBoostingRegressor",
        "LGBMClassifier", "LGBMRegressor",
        "DecisionTreeClassifier", "DecisionTreeRegressor",
        "ExtraTreesClassifier", "ExtraTreesRegressor",
    )

    def __init__(self, model: Any, X_df: pd.DataFrame):
        self.model = model
        self.X_df = X_df.copy()
        self.feature_names = list(X_df.columns)
        self.explainer = self._build_explainer()
        self.shap_values = self._compute_shap_values()

    def _build_explainer(self) -> shap.Explainer:
        model_type = type(self.model).__name__
        if model_type in self.TREE_MODELS:
            return shap.TreeExplainer(self.model)
        else:
            # Fallback: KernelExplainer works with any model
            background = shap.sample(self.X_df, min(100, len(self.X_df)))
            return shap.KernelExplainer(self.model.predict_proba, background)

    def _compute_shap_values(self) -> np.ndarray:
        raw = self.explainer.shap_values(self.X_df)
        # For binary classifiers, shap_values returns list [class0, class1]
        if isinstance(raw, list):
            return raw[1]  # Use positive class (high risk)
        return raw

    def get_mean_abs_shap(self) -> pd.Series:
        """Mean absolute SHAP value per feature — for ranking importance."""
        return pd.Series(
            np.abs(self.shap_values).mean(axis=0),
            index=self.feature_names
        ).sort_values(ascending=False)

    def get_top_features(self, k: int = 8) -> list[str]:
        return self.get_mean_abs_shap().head(k).index.tolist()

    def get_shap_df(self) -> pd.DataFrame:
        """Full SHAP values as DataFrame with feature names as columns."""
        return pd.DataFrame(
            self.shap_values,
            columns=self.feature_names,
            index=self.X_df.index
        )

    def get_expected_value(self) -> float:
        ev = self.explainer.expected_value
        if isinstance(ev, (list, np.ndarray)):
            return float(ev[1])
        return float(ev)

    def get_waterfall_data(self, shipment_idx: int) -> dict:
        """Extract data for a single-shipment waterfall chart."""
        shap_row = self.shap_values[shipment_idx]
        feature_row = self.X_df.iloc[shipment_idx]
        sorted_idx = np.argsort(np.abs(shap_row))[::-1]

        return {
            "expected_value": self.get_expected_value(),
            "features": [self.feature_names[i] for i in sorted_idx],
            "shap_values": [float(shap_row[i]) for i in sorted_idx],
            "feature_values": [float(feature_row.iloc[i]) for i in sorted_idx],
            "shipment_idx": shipment_idx,
        }

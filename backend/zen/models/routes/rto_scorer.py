from __future__ import annotations
"""
RTO Risk Scorer — LightGBM + SHAP.
Adapted from zenrto for zen-platform (removed app.config dependency → env vars).
"""
import os
import joblib
import numpy as np
import pandas as pd
import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "buyer_rto_history", "buyer_order_count", "pincode_rto_rate",
    "is_fraud_pincode", "order_value_bucket", "address_completeness_score",
    "hour_of_day", "day_of_week", "payment_method_cod",
    "payment_method_prepaid", "device_type_mobile",
]

FEATURE_DISPLAY = {
    "buyer_rto_history": "Buyer's past RTO rate",
    "buyer_order_count": "Buyer order count",
    "pincode_rto_rate": "PIN code RTO rate",
    "is_fraud_pincode": "Fraud PIN code flag",
    "order_value_bucket": "Order value tier",
    "address_completeness_score": "Address quality score",
    "hour_of_day": "Order hour",
    "day_of_week": "Day of week",
    "payment_method_cod": "Payment: COD",
    "payment_method_prepaid": "Payment: Prepaid",
    "device_type_mobile": "Device: Mobile",
}

# Thresholds
RTO_THRESHOLD_REJECT = float(os.getenv("RTO_THRESHOLD_REJECT_COD", "0.75"))
RTO_THRESHOLD_HOLD   = float(os.getenv("RTO_THRESHOLD_HOLD", "0.60"))
RTO_THRESHOLD_WA     = float(os.getenv("RTO_THRESHOLD_WHATSAPP", "0.40"))

RTO_MODEL_PATH = os.getenv("RTO_MODEL_PATH", "models/routes/ml/rto_model.joblib")


@dataclass
class RTOScoreResult:
    score: float
    risk_level: str
    action: str
    shap_values: dict
    top_factors: list
    savings_estimate_rs: float


_model = None
_explainer = None


def _get_model():
    global _model, _explainer
    if _model is None:
        model_path = Path(RTO_MODEL_PATH)
        if not model_path.exists():
            logger.warning(f"RTO model not found at {model_path}. Using heuristic scoring.")
            return None, None
        try:
            import shap
            _model = joblib.load(model_path)
            _explainer = shap.TreeExplainer(_model)
            logger.info(f"RTO LightGBM loaded from {model_path}")
        except Exception as e:
            logger.error(f"RTO model load error: {e}")
    return _model, _explainer


def _order_value_bucket(value: float) -> int:
    if value < 300:   return 0
    if value < 800:   return 1
    if value < 2000:  return 2
    return 3


def _heuristic_score(buyer_rto_history, pincode_rto_rate, is_fraud_pincode, order_value, address_score, payment_method) -> float:
    """Simple heuristic when no model is available."""
    score = 0.0
    score += buyer_rto_history * 0.35
    score += pincode_rto_rate * 0.25
    if is_fraud_pincode: score += 0.20
    if payment_method == "COD": score += 0.10
    if address_score < 0.4: score += 0.10
    if order_value > 3000: score += 0.05
    return min(score, 0.99)


def score_order(
    buyer_rto_history: float,
    buyer_order_count: int,
    pincode_rto_rate: float,
    is_fraud_pincode: bool,
    order_value: float,
    address_score: float,
    hour_of_day: int,
    day_of_week: int,
    payment_method: str,
    device_type: str,
) -> RTOScoreResult:
    model, explainer = _get_model()

    if model is None:
        # Heuristic fallback
        score = _heuristic_score(buyer_rto_history, pincode_rto_rate, is_fraud_pincode, order_value, address_score, payment_method)
        top_factors = [{"feature": "buyer_rto_history", "display_name": "Buyer's past RTO rate", "shap_value": buyer_rto_history * 0.35, "direction": "INCREASES_RISK"}]
    else:
        row = {
            "buyer_rto_history": float(buyer_rto_history),
            "buyer_order_count": float(min(buyer_order_count, 200)),
            "pincode_rto_rate": float(pincode_rto_rate),
            "is_fraud_pincode": float(int(is_fraud_pincode)),
            "order_value_bucket": float(_order_value_bucket(order_value)),
            "address_completeness_score": float(address_score),
            "hour_of_day": float(hour_of_day),
            "day_of_week": float(day_of_week),
            "payment_method_cod": float(1 if payment_method == "COD" else 0),
            "payment_method_prepaid": float(1 if payment_method in ("PREPAID", "CARD", "UPI") else 0),
            "device_type_mobile": float(1 if device_type == "MOBILE" else 0),
        }
        features_df = pd.DataFrame([row])
        score = float(model.predict_proba(features_df)[0][1])
        shap_vals = explainer.shap_values(features_df)
        sv = shap_vals[1][0] if isinstance(shap_vals, list) else shap_vals[0]
        shap_dict = {FEATURE_NAMES[i]: float(sv[i]) for i in range(len(FEATURE_NAMES))}
        top_factors = sorted(
            [{"feature": k, "display_name": FEATURE_DISPLAY.get(k, k), "shap_value": v, "direction": "INCREASES_RISK" if v > 0 else "REDUCES_RISK"} for k, v in shap_dict.items()],
            key=lambda x: abs(x["shap_value"]), reverse=True
        )[:6]

    if score >= RTO_THRESHOLD_REJECT:
        risk_level, action = "CRITICAL", "REJECT_COD_OFFER_PREPAID"
    elif score >= RTO_THRESHOLD_HOLD:
        risk_level, action = "HIGH", "HOLD_FOR_OPS_REVIEW"
    elif score >= RTO_THRESHOLD_WA:
        risk_level, action = "MEDIUM", "SEND_WHATSAPP_CONFIRMATION"
    else:
        risk_level, action = "LOW", "APPROVE"

    savings_estimate = round((150.0 + order_value * 0.15) * score, 2)

    return RTOScoreResult(
        score=round(score, 5),
        risk_level=risk_level,
        action=action,
        shap_values={} if model is None else shap_dict,
        top_factors=top_factors,
        savings_estimate_rs=savings_estimate,
    )

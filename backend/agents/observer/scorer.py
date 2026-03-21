import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from db.supabase_client import get_historical_for_training

MODEL_PATH = 'models/isolation_forest.joblib'
FEATURES   = [
    'distance_km',
    'carrier_reliability_score',
    'warehouse_load_pct',
    'eta_lag_minutes',
    'hour_of_dispatch',
    'day_of_week',
]
ANOMALY_THRESHOLD = -0.5514  # scores below this are flagged


def _train_model() -> IsolationForest:
    print('Training Isolation Forest on historical data...')
    rows = get_historical_for_training()
    if not rows:
        raise RuntimeError('No historical data found in Supabase. Run upload_to_supabase.py first.')
    
    df = pd.DataFrame(rows)[FEATURES].dropna()
    model = IsolationForest(
        n_estimators=200,
        contamination=0.08,
        random_state=42,
        n_jobs=-1
    )
    model.fit(df.values)
    
    # Auto-calibrate: find the actual 8th percentile score on training data
    # This means the threshold always matches contamination, even if data changes
    scores = model.score_samples(df.values)
    threshold = float(np.percentile(scores, 8))  # 8% contamination = 8th percentile
    print(f'  Trained on {len(df):,} rows. Auto-calibrated threshold: {threshold:.4f}')
    
    os.makedirs('models', exist_ok=True)
    joblib.dump({'model': model, 'threshold': threshold}, MODEL_PATH)
    return model, threshold

from typing import Optional
_model: Optional[IsolationForest] = None
_threshold: float = -0.5514  # fallback

def get_model() -> tuple[IsolationForest, float]:
    global _model, _threshold
    if _model is not None:
        return _model, _threshold
    if os.path.exists(MODEL_PATH):
        saved = joblib.load(MODEL_PATH)
        if isinstance(saved, dict):  # new format with threshold
            _model = saved['model']
            _threshold = saved['threshold']
        else:  # old format — just the model
            _model = saved
            _threshold = -0.5514
        print(f'Loaded Isolation Forest. Threshold: {_threshold:.4f}')
    else:
        _model, _threshold = _train_model()
    return _model, _threshold


def score_shipment(shipment: dict, warehouse_load_pct: float) -> float:
    model, _ = get_model()
    features = np.array([[
        float(shipment.get('distance_km', 0)),
        float(shipment.get('carrier_reliability_score', 0.8)),
        float(warehouse_load_pct),
        float(shipment.get('eta_minutes_current', 0)) - float(shipment.get('eta_minutes_original', 0)),
        float(shipment.get('hour_of_dispatch', 12)),
        float(shipment.get('day_of_week', 0)),
    ]])
    score = model.score_samples(features)[0]
    return round(float(score), 4)


def is_anomalous(score: float) -> bool:
    _, threshold = get_model()
    return score < threshold
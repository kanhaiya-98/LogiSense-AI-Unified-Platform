import os, joblib, numpy as np, pandas as pd
from datetime import datetime, timezone
from lightgbm import LGBMClassifier
from db.supabase_client import get_historical_for_delay_model

MODEL_PATH = 'models/lightgbm_delay.joblib'
FEATURES = [
    'eta_lag_minutes', 'carrier_reliability_score',
    'warehouse_load_pct', 'time_to_sla_hr',
    'dependency_type_encoded', 'hop_depth'
]

DEP_TYPE_ENCODE = {'ROOT': 0, 'SEQUENTIAL': 0, 'SAME_CARRIER': 1, 'SAME_WAREHOUSE': 2}

def _train_model() -> LGBMClassifier:
    """Train LightGBM classifier on historical delay data."""
    print('Training LightGBM Delay Classifier...')
    rows = get_historical_for_delay_model()
    if not rows:
        raise RuntimeError('No training data. Run generate_dag.py and upload_to_supabase.py first.')
        
    df = pd.DataFrame(rows).dropna()
    X = df[['eta_lag_minutes', 'carrier_reliability_score', 'warehouse_load_pct', 'time_to_sla_hours']]
    y = df['was_delayed'].astype(int)
    
    model = LGBMClassifier(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        class_weight='balanced', random_state=42, n_jobs=-1, verbose=-1
    )
    model.fit(X, y)
    
    os.makedirs('models', exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f'  LightGBM trained on {len(df):,} rows. Saved to {MODEL_PATH}')
    return model

from typing import Optional
_model: Optional[LGBMClassifier] = None

def get_model() -> LGBMClassifier:
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH) if os.path.exists(MODEL_PATH) else _train_model()
    return _model

def score_nodes(
    nodes: list[dict],  # each: {shipment_id, hop_depth, dep_type, + shipment fields}
    wh_loads: dict[str, float]  # {warehouse_id: load_pct}
) -> list[dict]:
    """
    Vectorised LightGBM inference. Returns same list with added fields:
    risk_score, sla_breach_prob, recommended_priority
    """
    model = get_model()
    now = datetime.now(timezone.utc).timestamp()
    
    # Build feature matrix
    rows = []
    for n in nodes:
        wh_load = wh_loads.get(n.get('warehouse_id', ''), 0.0)
        eta_lag = float(n.get('eta_minutes_current', 0)) - float(n.get('eta_minutes_original', 0))
        
        sla_ts = n.get('expected_delivery')  # ISO string or None
        if sla_ts:
            try:
                sla_dt = datetime.fromisoformat(sla_ts.replace('Z', '+00:00'))
                time_to_sla = (sla_dt.timestamp() - now) / 60.0  # minutes
            except: time_to_sla = 120.0
        else:
            time_to_sla = 120.0
            
        rows.append([
            eta_lag, float(n.get('carrier_reliability_score', 0.82)),
            wh_load, time_to_sla
        ])
        
    X = np.array(rows)
    probs = model.predict_proba(X)[:, 1]  # P(delay=1)
    
    scored = []
    for i, n in enumerate(nodes):
        risk = round(float(probs[i]), 4)
        sla_breach_prob = round(risk * (1.0 / max(0.1, (n.get('hop_depth', 0) + 1) * 0.5)), 4)
        sla_breach_prob = min(1.0, sla_breach_prob)  # cap at 1.0
        
        priority = 'CRITICAL' if risk >= 0.8 else 'HIGH' if risk >= 0.6 else 'MEDIUM' if risk >= 0.3 else 'LOW'
        
        scored.append({**n, 'risk_score': risk, 'sla_breach_prob': sla_breach_prob,
                       'recommended_priority': priority, 'shap_values': None})
                       
    return scored

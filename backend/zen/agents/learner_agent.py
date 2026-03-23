from __future__ import annotations
"""
Learner Agent — from zeneta, adapted for zen-platform imports.
"""
import logging
import hashlib
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class LearnerAgent:
    def __init__(self, supabase_service, xgboost_service, mlflow_tracker=None):
        self.supabase = supabase_service
        self.xgboost = xgboost_service
        self.mlflow = mlflow_tracker

    async def record_actual(self, shipment_id: str, prediction_id: str, actual_minutes: float):
        logger.info(f"[Learner] Recording actual | {shipment_id} actual={actual_minutes:.1f}min")
        await self.supabase.record_actual_time(
            shipment_id=shipment_id, prediction_id=prediction_id,
            actual_minutes=actual_minutes, recorded_at=datetime.utcnow().isoformat(),
        )

    async def retrain_if_due(self):
        last_train = await self.supabase.get_last_training_time()
        if last_train is None:
            await self._retrain()
            return
        age_hours = (datetime.utcnow() - last_train.replace(tzinfo=None)).total_seconds() / 3600
        if age_hours >= 24:
            await self._retrain()

    async def force_retrain(self):
        await self._retrain()

    async def _retrain(self):
        from zen.utils.data_generator import generate_synthetic_data
        from sklearn.model_selection import train_test_split

        records = await self.supabase.get_training_records(days=30)
        if len(records) >= 200:
            X_train, X_val, y_train, y_val = self._records_to_arrays(records)
            source = "real_actuals"
        else:
            X_train, X_val, y_train, y_val = generate_synthetic_data()
            source = "synthetic"

        rmse_results = self.xgboost.train_models(X_train, y_train, X_val, y_val)
        rmse = rmse_results.get("p50", 0.0)
        cal_score = self._compute_calibration(X_val, y_val)
        await self.supabase.save_training_run(rmse=rmse, n_samples=len(y_train), calibration_score=cal_score, notes=f"source={source}")
        logger.info(f"[Learner] Retrain complete | RMSE={rmse:.2f}min | cal={cal_score:.3f}")

    def _records_to_arrays(self, records):
        from sklearn.model_selection import train_test_split
        X, y = [], []
        for r in records:
            sh = r.get("shipments") or {}
            X.append([sh.get("route_distance_km", 200), 60.0, 100.0, r.get("aqi_speed_multiplier", 1.0),
                      1.0 if r.get("weather_rain_flag") else 0.0, 1.0, 0.0, 12.0, 1.0, 200 / 60.0])
            y.append(float(r["actual_minutes"]))
        X_arr, y_arr = np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)
        return train_test_split(X_arr, y_arr, test_size=0.2, random_state=42)

    def _compute_calibration(self, X_val, y_val) -> float:
        try:
            if "p90" not in self.xgboost.models:
                return 0.0
            p90_preds = self.xgboost.models["p90"].predict(X_val)
            return float(np.sum(y_val <= p90_preds) / len(y_val))
        except Exception:
            return 0.0

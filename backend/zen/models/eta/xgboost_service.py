from __future__ import annotations
"""
XGBoost ETA Service — copied from zeneta/app/services/xgboost_service.py
Primary prediction engine with p50/p90/p99 quantile models.
"""

import numpy as np
import joblib
import logging
import time
from pathlib import Path
from typing import Optional, Dict
from scipy.stats import norm

logger = logging.getLogger(__name__)

def _build_speed_profile(base: float, rush_penalty: float = 12.0) -> Dict[int, float]:
    profile = {}
    for h in range(24):
        if 7 <= h <= 10 or 16 <= h <= 19:
            profile[h] = base - rush_penalty
        else:
            profile[h] = base
    return profile

CARRIER_SPEED_PROFILES: Dict[str, Dict[int, float]] = {
    "north":   _build_speed_profile(60, 15),
    "south":   _build_speed_profile(55, 10),
    "east":    _build_speed_profile(58, 12),
    "west":    _build_speed_profile(62, 18),
    "central": _build_speed_profile(65, 10),
}

DOW_MULTIPLIERS = {0: 1.15, 1: 1.0, 2: 1.0, 3: 1.02, 4: 1.10, 5: 0.95, 6: 0.90}

CARRIER_EFFICIENCY: Dict[str, float] = {
    "CAR-01": 1.00, "CAR-02": 0.98, "CAR-03": 0.97,
    "CAR-04": 0.96, "CAR-05": 0.95, "CAR-06": 0.93, "CAR-07": 0.80,
}

QUANTILES = {"p50": 0.50, "p90": 0.90, "p99": 0.99}


class QuantileOffsetCalibrator:
    def __init__(self, quantile: float):
        self.quantile = quantile
        self.offset = 0.0

    def fit(self, raw_preds: np.ndarray, y_true: np.ndarray) -> "QuantileOffsetCalibrator":
        residuals = y_true - raw_preds
        self.offset = float(np.percentile(residuals, self.quantile * 100))
        return self

    def predict(self, raw_preds) -> np.ndarray:
        return np.asarray(raw_preds) + self.offset


class XGBoostETAService:
    def __init__(self, model_dir: str = "models/eta"):
        self.model_dir   = Path(model_dir)
        self.models:      Dict[str, object] = {}
        self.calibrators: Dict[str, QuantileOffsetCalibrator] = {}
        self.is_loaded   = False

    def load_models(self):
        model_paths = {q: self.model_dir / f"xgb_{q}.joblib" for q in QUANTILES}
        calib_paths = {q: self.model_dir / f"calib_{q}.joblib" for q in QUANTILES}
        if all(p.exists() for p in model_paths.values()):
            for q, path in model_paths.items():
                self.models[q] = joblib.load(path)
                logger.info(f"  Loaded {q} model <- {path}")
            for q, path in calib_paths.items():
                if path.exists():
                    self.calibrators[q] = joblib.load(path)
        else:
            logger.info("Models not found — training from synthetic data...")
            self.train_models()
        self.is_loaded = True
        logger.info("✓ XGBoost ETA models ready")

    def predict(
        self,
        route_distance_km: float,
        carrier_id: str,
        region: str,
        hour: int,
        dow: int,
        warehouse_throughput_15min: float,
        aqi_speed_multiplier: float,
        weather_rain_flag: bool,
        lane_avg_delay_30d: float = 0.0,
        sla_deadline_minutes: float = 480.0,
    ) -> dict:
        if not self.is_loaded:
            self.load_models()
        t0 = time.perf_counter()
        features = self._build_features(
            route_distance_km, carrier_id, region, hour, dow,
            warehouse_throughput_15min, aqi_speed_multiplier,
            weather_rain_flag, lane_avg_delay_30d,
        )
        preds: Dict[str, float] = {}
        for q, model in self.models.items():
            raw = float(model.predict(features)[0])
            if q in self.calibrators:
                raw = float(self.calibrators[q].predict(np.array([raw]))[0])
            if weather_rain_flag:
                raw += 40.0
            preds[q] = max(raw, 30.0)

        p50 = preds.get("p50", 240.0)
        p90 = max(preds.get("p90", p50 * 1.20), p50 + 1.0)
        p99 = max(preds.get("p99", p50 * 1.40), p90 + 1.0)

        std_est = max((p99 - p50) / 2.576, 1.0)
        sla_breach_prob = float(np.clip(1.0 - norm.cdf((sla_deadline_minutes - p50) / std_est), 0.0, 1.0))
        inference_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "estimated_minutes": p50, "p50": p50, "p90": p90, "p99": p99,
            "sla_breach_prob": sla_breach_prob, "inference_time_ms": inference_ms,
        }

    def train_models(self, X_train=None, y_train=None, X_val=None, y_val=None):
        import xgboost as xgb
        if X_train is None:
            from zen.utils.data_generator import generate_synthetic_data
            X_train, X_val, y_train, y_val = generate_synthetic_data()

        self.model_dir.mkdir(parents=True, exist_ok=True)
        rmse_results = {}
        for q, alpha in QUANTILES.items():
            model = xgb.XGBRegressor(
                objective="reg:quantileerror", quantile_alpha=alpha,
                n_estimators=600, max_depth=7, learning_rate=0.03,
                subsample=0.85, colsample_bytree=0.85, random_state=42,
                n_jobs=-1, verbosity=0,
            )
            model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            val_preds = model.predict(X_val)
            calibrator = QuantileOffsetCalibrator(quantile=alpha)
            calibrator.fit(val_preds, y_val)
            cal_preds = calibrator.predict(val_preds)
            rmse = float(np.sqrt(np.mean((cal_preds - y_val) ** 2)))
            rmse_results[q] = rmse
            joblib.dump(model, self.model_dir / f"xgb_{q}.joblib")
            joblib.dump(calibrator, self.model_dir / f"calib_{q}.joblib")
            self.models[q] = model
            self.calibrators[q] = calibrator
        logger.info("✓ All XGBoost quantile models trained.")
        return rmse_results

    def _build_features(self, route_distance_km, carrier_id, region, hour, dow,
                        warehouse_throughput_15min, aqi_speed_multiplier, weather_rain_flag, lane_avg_delay_30d):
        profile = CARRIER_SPEED_PROFILES.get(region, CARRIER_SPEED_PROFILES["central"])
        base_region_speed = profile.get(hour, 60.0)
        efficiency = CARRIER_EFFICIENCY.get(carrier_id, 1.0)
        carrier_speed = base_region_speed * efficiency
        dow_mult = DOW_MULTIPLIERS.get(dow, 1.0)
        if dow == 4 and 17 <= hour <= 20:
            dow_mult *= 1.20
        base_travel_h = route_distance_km / max(carrier_speed * aqi_speed_multiplier, 1.0)
        return np.array([[
            route_distance_km, carrier_speed, warehouse_throughput_15min,
            aqi_speed_multiplier, 1.0 if weather_rain_flag else 0.0,
            dow_mult, lane_avg_delay_30d, float(hour), float(dow), base_travel_h,
        ]], dtype=np.float32)

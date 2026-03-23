from __future__ import annotations
"""
Synthetic 30-day historical data generator — 30,000 rows.
Copied from zeneta/app/utils/data_generator.py to zen-platform.
"""
import numpy as np
from sklearn.model_selection import train_test_split
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

REGIONS = ["north", "south", "east", "west", "central"]
CARRIERS = ["CAR-01", "CAR-02", "CAR-03", "CAR-04", "CAR-05", "CAR-06", "CAR-07"]
CARRIER_EFFICIENCY = {"CAR-01": 1.00, "CAR-02": 0.98, "CAR-03": 0.97, "CAR-04": 0.96, "CAR-05": 0.95, "CAR-06": 0.93, "CAR-07": 0.80}
CITY_PAIR_BASELINE = {("north","south"): 280, ("north","east"): 180, ("north","west"): 240, ("north","central"): 150, ("south","east"): 200, ("south","west"): 260, ("south","central"): 160, ("east","west"): 360, ("east","central"): 120, ("west","central"): 200}
DOW_MULTIPLIERS = {0: 1.15, 1: 1.00, 2: 1.00, 3: 1.02, 4: 1.10, 5: 0.95, 6: 0.90}


def get_baseline(origin: str, dest: str) -> float:
    return CITY_PAIR_BASELINE.get((origin, dest), CITY_PAIR_BASELINE.get((dest, origin), 240))


def get_carrier_speed(carrier: str, hour: int) -> float:
    base_speed = 65.0
    if 7 <= hour <= 10 or 16 <= hour <= 19:
        base_speed -= 14
    return base_speed * CARRIER_EFFICIENCY[carrier]


def generate_synthetic_data(n_samples: int = 30_000, random_seed: int = 42) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    np.random.seed(random_seed)
    logger.info(f"Generating {n_samples:,} synthetic samples...")
    X, y = [], []
    for _ in range(n_samples):
        origin = np.random.choice(REGIONS)
        dest = np.random.choice(REGIONS)
        carrier = np.random.choice(CARRIERS)
        dow = np.random.randint(0, 7)
        hour = np.random.randint(0, 24)
        baseline_min = get_baseline(origin, dest)
        route_km = max(baseline_min * 0.85 + np.random.normal(0, 15), 20.0)
        carrier_speed = get_carrier_speed(carrier, hour)
        aqi_mult = np.random.choice([1.0, 0.95, 0.88, 0.80, 0.70], p=[0.40, 0.30, 0.15, 0.10, 0.05])
        rain_flag = float(np.random.random() < 0.15)
        wh_throughput = max(np.random.normal(120, 30), 10.0)
        lane_delay = max(np.random.exponential(12), 0.0)
        dow_mult = DOW_MULTIPLIERS[dow]
        if dow == 4 and 17 <= hour <= 20:
            dow_mult *= 1.20
        base_travel_h = route_km / max(carrier_speed * aqi_mult, 1.0)
        X.append([route_km, carrier_speed, wh_throughput, aqi_mult, rain_flag, dow_mult, lane_delay, float(hour), float(dow), base_travel_h])
        actual = base_travel_h * 60 * dow_mult + max(60 - wh_throughput * 0.25, 5) + lane_delay
        if rain_flag: actual += 40.0
        actual += np.random.normal(0, 6)
        y.append(max(actual, 30.0))
    X_arr, y_arr = np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)
    logger.info(f"Data generated | mean={y_arr.mean():.1f}min std={y_arr.std():.1f}min")
    return train_test_split(X_arr, y_arr, test_size=0.2, random_state=random_seed)

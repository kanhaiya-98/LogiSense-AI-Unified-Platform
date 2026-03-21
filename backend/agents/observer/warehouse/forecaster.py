# agents/observer/warehouse/forecaster.py — complete file
import warnings
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from db.supabase_client import get_throughput_history

ARIMA_ORDER = (1, 1, 1)     # p=1, d=1, q=1
FORECAST_STEPS = 8          # 8 steps × 15-min intervals = 2 hours
MIN_READINGS = 6            # need at least 6 readings to fit ARIMA
PREEMPTIVE_THRESHOLD = 70.0 # only run ARIMA when load is already > 70%

def forecast_load(warehouse_id: str, current_load_pct: float) -> float:
  """
  Returns projected load % in 2 hours using ARIMA(1,1,1).
  Returns None if not enough data or current load is below 70%.
  """
  # Skip ARIMA entirely if load is well below pre-emptive threshold
  if current_load_pct < PREEMPTIVE_THRESHOLD:
    return None

  history = get_throughput_history(warehouse_id, n_readings=24)
  if len(history) < MIN_READINGS:
    return None  # not enough data — skip forecast, rely on threshold rules

  load_series = [row['load_pct'] for row in history]

  try:
    with warnings.catch_warnings():
      warnings.simplefilter('ignore')   # suppress statsmodels convergence warnings
      model = ARIMA(load_series, order=ARIMA_ORDER)
      result = model.fit()
      forecast = result.forecast(steps=FORECAST_STEPS)
      projected_2hr = float(np.clip(forecast[-1], 0.0, 100.0))  # cap 0–100
      return round(projected_2hr, 2)
  except Exception as e:
    print(f'ARIMA forecast failed for {warehouse_id}: {e}')
    return None  # graceful fallback — threshold rules still active

def is_preemptive_flag(projected_2hr: float) -> bool:
  """True if ARIMA projects crossing 85% within 2 hours."""
  return projected_2hr is not None and projected_2hr >= 85.0

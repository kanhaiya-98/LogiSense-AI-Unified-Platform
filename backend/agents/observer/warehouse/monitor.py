# agents/observer/warehouse/monitor.py — complete file
from streams.redis_client import get_all_warehouse_loads
from db.supabase_client import get_all_warehouses

LOAD_THRESHOLD_PCT      = 85.0   # immediate flag
LOAD_PREEMPTIVE_PCT     = 70.0   # pre-emptive flag (used with ARIMA)
THROUGHPUT_DROP_PCT     = 0.20   # 20% drop triggers MEDIUM flag
CRITICAL_LOAD_PCT       = 95.0   # CRITICAL severity override

def check_warehouses(throughput_baselines: dict) -> list[dict]:
  """
  Evaluate all warehouses for congestion flags.
  throughput_baselines: {warehouse_id: baseline_throughput_hr}
  Returns list of congestion flag dicts (may be empty if all clear).
  """
  loads = get_all_warehouse_loads()  # from Redis
  flags = []

  for wid, state in loads.items():
    load_pct = state['load_pct']
    throughput = state['throughput_hr']
    baseline = throughput_baselines.get(wid, float(throughput))
    flag = None

    # Trigger 1: Immediate load threshold
    if load_pct >= LOAD_THRESHOLD_PCT:
      severity = 'CRITICAL' if load_pct >= CRITICAL_LOAD_PCT else 'HIGH'
      flag = _make_flag(wid, state, severity, 'LOAD_THRESHOLD', 'REDIRECT')

    # Trigger 2: Throughput drop (independent of load threshold)
    elif baseline > 0 and (baseline - throughput) / baseline >= THROUGHPUT_DROP_PCT:
      flag = _make_flag(wid, state, 'MEDIUM', 'THROUGHPUT_DROP', 'STAGGER')
      flag['stagger_minutes'] = 15  # default stagger: 15 min

    # Trigger 3 is handled by forecaster.py — pre-emptive check
    # (only fires when ARIMA projects breach within 2hrs)

    if flag:
      flags.append(flag)

  return flags

def _make_flag(wid: str, state: dict, severity: str,
               trigger_type: str, action: str) -> dict:
  return {
    'warehouse_id': wid,
    'severity': severity,
    'trigger_type': trigger_type,
    'current_load_pct': state['load_pct'],
    'throughput_per_hr': state['throughput_hr'],
    'inbound_queue': state.get('inbound_queue', 0),
    'recommended_action': action,
    'stagger_minutes': 0,
    'alternate_warehouse_id': None,  # filled by publisher after finding lowest-load alt
  }

def update_throughput_baseline(wid: str, current_throughput: int,
                               baselines: dict) -> dict:
  """Rolling average update — EMA with alpha=0.1."""
  prev = baselines.get(wid, float(current_throughput))
  baselines[wid] = 0.9 * prev + 0.1 * current_throughput
  return baselines

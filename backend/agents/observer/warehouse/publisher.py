# agents/observer/warehouse/publisher.py — complete file
from datetime import datetime, timezone
from streams.redis_client import (publish_congestion_event, get_all_warehouse_loads,
                                  cache_set)

def find_best_alternate(congested_wid: str, loads: dict) -> str:
  """Return warehouse_id with lowest load_pct that is not the congested one."""
  candidates = {
    wid: data['load_pct'] for wid, data in loads.items()
    if wid != congested_wid and data['load_pct'] < 80.0  # don't redirect to near-full warehouse
  }
  if not candidates:
    return None  # all warehouses congested — escalate
  return min(candidates, key=candidates.get)

def build_and_publish_congestion(
    flag: dict,
    arima_forecast: float,
    affected_shipment_count: int,
) -> dict:
  """
  Finalises CongestionEvent dict and publishes to Redis Streams.
  Also caches warehouse incident state for dashboard and Cascade Tree reads.
  """
  loads = get_all_warehouse_loads()
  alternate = find_best_alternate(flag['warehouse_id'], loads)

  event = {
    **flag,
    'arima_forecast_2hr': arima_forecast,
    'alternate_warehouse_id': alternate,
    'affected_shipment_count': affected_shipment_count,
    'timestamp': datetime.now(timezone.utc).isoformat(),
  }

  msg_id = publish_congestion_event(event)

  # Cache for dashboard heatmap reads (TTL 4hrs)
  cache_set(f"wh_congestion:{flag['warehouse_id']}", event, ttl_seconds=14400)

  # Cache cascade tree node update for F2 integration
  cache_set(f"cascade_node:{flag['warehouse_id']}", {
    'shipment_id': flag['warehouse_id'],  # warehouse appears as a node in cascade tree
    'risk_score': min(1.0, flag['current_load_pct'] / 100.0),
    'sla_breach_prob': 0.8 if flag['severity'] in ('HIGH', 'CRITICAL') else 0.4,
    'recommended_priority': flag['severity'],
    'node_type': 'WAREHOUSE',  # distinguishes from shipment nodes in F2 tree
    'shap_values': None,
  }, ttl_seconds=14400)

  print(f"[F4] {flag['severity']} congestion at {flag['warehouse_id']}: {flag['current_load_pct']}% load → {flag['recommended_action']} (msg: {msg_id})")
  return event

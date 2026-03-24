import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

_client: Optional[Client] = None

def get_client() -> Client:
    """Singleton Supabase client. Thread-safe for read operations."""
    global _client
    if _client is None:
        url = os.environ.get('SUPABASE_URL') or os.environ.get('Project_URL') or os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
        key = os.environ.get('SUPABASE_SERVICE_KEY') or os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')
        
        if not url or not key:
             raise ValueError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env file")
             
        _client = create_client(url, key)
    return _client


# ── Query functions used by Observer Agent ────────────────────

def get_active_shipments() -> list[dict]:
    """Fetch all shipments not yet delivered. Called every 5 seconds."""
    client = get_client()
    result = client.table('live_shipments') \
        .select('*') \
        .neq('status', 'DELIVERED') \
        .execute()
    return result.data or []


def get_warehouse_loads() -> dict[str, float]:
    """Returns {warehouse_id: load_pct} for all warehouses."""
    client = get_client()
    result = client.table('warehouses') \
        .select('warehouse_id, current_load_pct') \
        .execute()
    return {row['warehouse_id']: row['current_load_pct'] for row in (result.data or [])}


def get_latest_carrier_checkin(carrier_id: str) -> Optional[str]:
    """Returns ISO timestamp of last check-in for this carrier, or None."""
    client = get_client()
    result = client.table('carrier_events') \
        .select('date, hour') \
        .eq('carrier_id', carrier_id) \
        .order('date', desc=True) \
        .limit(1) \
        .execute()
    if not result.data:
        return None
    row = result.data[0]
    return f"{row['date']}T{str(row['hour']).zfill(2)}:00:00Z"


def get_historical_for_training() -> list[dict]:
    """Pull historical shipments for Isolation Forest training."""
    client = get_client()
    result = client.table('historical_shipments') \
        .select(
            'distance_km, carrier_reliability_score, warehouse_load_pct,'
            'eta_lag_minutes, hour_of_dispatch, day_of_week'
        ) \
        .execute()
    return result.data or []


# ── F2: DAG + scoring data ────────────────────────────────────

def get_all_dependencies() -> list[dict]:
    """Load all shipment dependency edges for NetworkX DAG."""
    client = get_client()
    result = client.table('shipment_dependencies') \
        .select('upstream_id, downstream_id, dependency_type') \
        .execute()
    return result.data or []

def get_shipments_by_ids(ids: list[str]) -> list[dict]:
    """Fetch full shipment rows for BFS-scored nodes."""
    client = get_client()
    result = client.table('live_shipments') \
        .select('shipment_id, carrier_id, warehouse_id, eta_minutes_current, eta_minutes_original, expected_delivery') \
        .in_('shipment_id', ids) \
        .execute()
    return result.data or []

def get_historical_for_delay_model() -> list[dict]:
    """Pull training data for LightGBM delay classifier."""
    client = get_client()
    result = client.table('historical_shipments') \
        .select('eta_lag_minutes, carrier_reliability_score, warehouse_load_pct, time_to_sla_hours, was_delayed') \
        .execute()
    return result.data or []

def get_carrier_events_for_drift(carrier_id: str, days: int = 30) -> list[dict]:
    """Fetch carrier on_time events for KS-test. Last N days."""
    client = get_client()
    result = client.table('carrier_events') \
        .select('date, hour, on_time, effective_reliability') \
        .eq('carrier_id', carrier_id) \
        .order('date', desc=True) \
        .limit(days * 24) \
        .execute()
    return result.data or []

def get_all_carrier_ids() -> list[str]:
    """Return list of all carrier_ids for scheduled drift scan."""
    client = get_client()
    result = client.table('carriers') \
        .select('carrier_id') \
        .eq('blacklisted', False) \
        .execute()
    return [row['carrier_id'] for row in (result.data or [])]

def get_carrier(carrier_id: str) -> Optional[dict]:
    """Fetch single carrier row by carrier_id."""
    client = get_client()
    result = client.table('carriers') \
        .select('*') \
        .eq('carrier_id', carrier_id) \
        .limit(1) \
        .execute()
    return result.data[0] if result.data else None

def update_carrier_reliability(carrier_id: str, updates: dict) -> None:
    """Update carrier Bayesian params + reliability score."""
    client = get_client()
    client.table('carriers') \
        .update(updates) \
        .eq('carrier_id', carrier_id) \
        .execute()

def get_shipments_by_carrier(carrier_id: str) -> list[dict]:
    """Fetch all active shipments for a specific carrier."""
    client = get_client()
    result = client.table('live_shipments') \
        .select('shipment_id, carrier_id, warehouse_id, status') \
        .eq('carrier_id', carrier_id) \
        .neq('status', 'DELIVERED') \
        .execute()
    return result.data or []

def swap_carrier_on_shipments(shipment_ids: list[str], new_carrier_id: str) -> int:
    """Update carrier_id on a list of shipments. Returns count updated."""
    if not shipment_ids:
        return 0
    client = get_client()
    for sid in shipment_ids:
        client.table('live_shipments') \
            .update({'carrier_id': new_carrier_id}) \
            .eq('shipment_id', sid) \
            .execute()
    return len(shipment_ids)

def log_decision(decision_id: str, decision_type: str,
                 agent: str, payload: dict, sha256_hash: str = '') -> None:
    """Insert a decision record into decision_log for F9 blockchain audit."""
    client = get_client()
    client.table('decision_log').insert({
        'decision_id':   decision_id,
        'decision_type': decision_type,
        'agent':         agent,
        'payload':       payload,
        'sha256_hash':   sha256_hash,
    }).execute()

def get_best_alternative_carrier(exclude_carrier_id: str, transport_type: str = None) -> Optional[dict]:
    """Find the highest-reliability non-blacklisted carrier to swap to."""
    client = get_client()
    query = client.table('carriers') \
        .select('carrier_id, current_reliability_score, cost_factor, transport_type') \
        .neq('carrier_id', exclude_carrier_id) \
        .eq('blacklisted', False) \
        .order('current_reliability_score', desc=True) \
        .limit(1)
    if transport_type:
        query = query.eq('transport_type', transport_type)
    result = query.execute()
    return result.data[0] if result.data else None


# ── F4: Warehouse functions ────────────────────────────────────
def get_all_warehouses() -> list[dict]:
  """Fetch all warehouses with location + current load stats."""
  client = get_client()
  result = client.table('warehouses').select('*').execute()
  return result.data or []

def get_throughput_history(warehouse_id: str, n_readings: int = 24) -> list[dict]:
  """
  Fetch last N throughput readings for ARIMA training.
  n_readings=24 means last 24 readings (15-min cadence = last 6 hours).
  """
  client = get_client()
  result = client.table('warehouse_throughput_log') \
    .select('recorded_at, load_pct, throughput_hr') \
    .eq('warehouse_id', warehouse_id) \
    .order('recorded_at', desc=True) \
    .limit(n_readings) \
    .execute()
  return list(reversed(result.data or []))  # oldest first for ARIMA

def get_inbound_shipments(warehouse_id: str) -> list[dict]:
  """Fetch all shipments currently en-route to this warehouse."""
  client = get_client()
  result = client.table('live_shipments') \
    .select('shipment_id, eta_minutes_current') \
    .eq('warehouse_id', warehouse_id) \
    .eq('status', 'IN_TRANSIT') \
    .execute()
  return result.data or []

def update_warehouse_status(warehouse_id: str, status: str) -> None:
  """Update warehouse status after redirect/stagger action."""
  get_client().table('warehouses') \
    .update({'status': status}) \
    .eq('warehouse_id', warehouse_id) \
    .execute()

def log_throughput_snapshot(warehouse_id: str, load_pct: float,
                            throughput_hr: int, inbound_queue: int) -> None:
  """Write a throughput snapshot row — called every 15 minutes by cron."""
  get_client().table('warehouse_throughput_log').insert({
    'warehouse_id': warehouse_id, 'load_pct': load_pct,
    'throughput_hr': throughput_hr, 'inbound_queue': inbound_queue
  }).execute()

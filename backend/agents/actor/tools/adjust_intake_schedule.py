# agents/actor/tools/adjust_intake_schedule.py — complete file
from datetime import datetime, timezone, timedelta
from db.supabase_client import get_client, get_inbound_shipments
from streams.redis_client import cache_set
import hashlib, json

def adjust_intake_schedule(
    warehouse_id: str,
    delay_minutes: int,        # how many minutes to stagger each batch
    congestion_event: dict,
) -> dict:
  """
  MCP Tool: Stagger inbound shipment arrivals to warehouse_id by delay_minutes.
  Groups shipments into batches of 5, each batch delayed by delay_minutes more.
  Writes stagger records to warehouse_intake_schedule table.
  Reversible: undo clears the schedule within 30 min.
  """
  client = get_client()
  inbound = get_inbound_shipments(warehouse_id)
  if not inbound:
    return {'status': 'NO_OP', 'reason': 'No inbound shipments to stagger', 'affected': 0}

  # Stagger in batches of 5
  batch_size = 5
  schedule_rows = []
  now = datetime.now(timezone.utc)

  for i, ship in enumerate(inbound):
    batch_delay = (i // batch_size) * delay_minutes
    adjusted_eta = now + timedelta(minutes=batch_delay)
    schedule_rows.append({
      'warehouse_id': warehouse_id,
      'shipment_id': ship['shipment_id'],
      'stagger_minutes': batch_delay,
      'adjusted_eta': adjusted_eta.isoformat(),
    })

  client.table('warehouse_intake_schedule').upsert(schedule_rows).execute()

  payload_data = {
    'action': 'ADJUST_INTAKE_SCHEDULE',
    'warehouse_id': warehouse_id,
    'delay_minutes': delay_minutes,
    'affected_shipments': [s['shipment_id'] for s in inbound],
    'trigger_event': congestion_event,
    'timestamp': now.isoformat(),
  }
  canonical = json.dumps(payload_data, sort_keys=True, default=str)
  
  decision = {
    'decision_id': f'DEC-STAGGER-{warehouse_id}-{now.strftime("%Y%m%dT%H%M%S")}',
    'decision_type': 'WAREHOUSE_STAGGER',
    'agent': 'Actor',
    'payload': payload_data,
    'sha256_hash': hashlib.sha256(canonical.encode()).hexdigest()
  }
  client.table('decision_log').insert(decision).execute()
  cache_set(f'action:{decision["decision_id"]}', decision, ttl_seconds=1800)

  max_delay = (len(inbound) // batch_size) * delay_minutes
  print(f'[adjust_intake] {len(inbound)} shipments staggered for {warehouse_id}, max delay {max_delay} min')
  return {'status': 'OK', 'decision_id': decision['decision_id'],
          'affected': len(inbound), 'max_delay_minutes': max_delay}

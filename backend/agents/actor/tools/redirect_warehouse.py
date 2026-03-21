# agents/actor/tools/redirect_warehouse.py — complete file
from datetime import datetime, timezone
from db.supabase_client import get_client, get_inbound_shipments, update_warehouse_status
from streams.redis_client import set_warehouse_load, cache_set
import hashlib, json

def redirect_warehouse(
    warehouse_id: str,         # congested warehouse (source)
    target_warehouse_id: str,  # redirect destination
    congestion_event: dict,    # original CongestionEvent for decision log
) -> dict:
  """
  MCP Tool: Redirect all inbound IN_TRANSIT shipments from warehouse_id
  to target_warehouse_id.
  Returns: action receipt with affected shipment count and decision_id.
  Reversible: undo_redirect() within 30 minutes.
  """
  client = get_client()
  inbound = get_inbound_shipments(warehouse_id)
  shipment_ids = [s['shipment_id'] for s in inbound]

  if not shipment_ids:
    return {'status': 'NO_OP', 'reason': 'No inbound shipments to redirect', 'affected': 0}

  # Update shipments to new warehouse
  client.table('live_shipments') \
    .update({'warehouse_id': target_warehouse_id, 'status': 'REDIRECTED'}) \
    .in_('shipment_id', shipment_ids) \
    .execute()

  # Update warehouse statuses
  update_warehouse_status(warehouse_id, 'REDIRECTING')

  # Build decision record for F9 blockchain audit
  decision_payload = {
    'action': 'REDIRECT_WAREHOUSE',
    'warehouse_id': warehouse_id,
    'target_warehouse_id': target_warehouse_id,
    'affected_shipments': shipment_ids,
    'trigger_event': congestion_event,
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'reversible_until': None,  # set by caller after 30-min window
  }
  canonical = json.dumps(decision_payload, sort_keys=True, default=str)
  
  decision = {
    'decision_id': f'DEC-REDIRECT-{warehouse_id}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}',
    'decision_type': 'WAREHOUSE_REDIRECT',
    'agent': 'Actor',
    'payload': decision_payload,
    'sha256_hash': hashlib.sha256(canonical.encode()).hexdigest()
  }

  # Write to decision_log
  client.table('decision_log').insert(decision).execute()

  # Cache for dashboard + undo window
  cache_set(f'action:{decision["decision_id"]}', decision, ttl_seconds=1800)  # 30 min

  print(f'[redirect_warehouse] {len(shipment_ids)} shipments moved {warehouse_id} → {target_warehouse_id}')
  return {'status': 'OK', 'decision_id': decision['decision_id'],
          'affected': len(shipment_ids), 'target': target_warehouse_id}

def undo_redirect(decision_id: str) -> dict:
  """Reverse a redirect within the 30-minute window."""
  from streams.redis_client import cache_get
  decision = cache_get(f'action:{decision_id}')
  if not decision:
    return {'status': 'EXPIRED', 'reason': 'Undo window has passed (> 30 min)'}
  client = get_client()
  client.table('live_shipments') \
    .update({'warehouse_id': decision['warehouse_id'], 'status': 'IN_TRANSIT'}) \
    .in_('shipment_id', decision['affected_shipments']) \
    .execute()
  update_warehouse_status(decision['warehouse_id'], 'NORMAL')
  print(f'[undo_redirect] Reversed {decision_id}')
  return {'status': 'UNDONE', 'decision_id': decision_id}

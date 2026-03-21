import hashlib
import json
import uuid
from datetime import datetime, timezone
from db.supabase_client import (
    get_shipments_by_carrier, get_best_alternative_carrier,
    swap_carrier_on_shipments, log_decision, update_carrier_reliability
)
from streams.redis_client import publish_swap_event, cache_set
from api.websocket import ws_manager
import asyncio
from typing import Optional

def _fingerprint(payload: dict) -> str:
    """SHA-256 fingerprint of decision payload for F9 blockchain prep."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()

async def swap_carrier(
    failing_carrier_id: str,
    reason: str,
    ks_statistic: float = 0.0,
    ks_pvalue: float = 1.0,
    shipment_ids: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Execute carrier swap:
    1. Find best alternative carrier
    2. Get affected shipments (from param or Supabase query)
    3. Update carrier_id on all affected shipments
    4. Blacklist the failing carrier
    5. Log decision to Supabase decision_log
    6. Publish SwapEvent to Redis Streams
    7. Broadcast to WebSocket dashboard
    
    Returns SwapEvent dict, or None if no alternative carrier found.
    """
    print(f'Executing carrier swap: {failing_carrier_id} — {reason}')
    
    # 1. Find best alternative
    alt = get_best_alternative_carrier(exclude_carrier_id=failing_carrier_id)
    if not alt:
        print(f'  No alternative carrier available for swap from {failing_carrier_id}')
        return None
        
    new_carrier_id    = alt['carrier_id']
    new_reliability   = float(alt['current_reliability_score'])
    
    # 2. Get affected shipments
    if shipment_ids is None:
        affected = get_shipments_by_carrier(failing_carrier_id)
        shipment_ids = [s['shipment_id'] for s in affected]
        
    if not shipment_ids:
        print(f'  No active shipments on {failing_carrier_id} to swap')
        return None
        
    old_reliability = 0.0
    from db.supabase_client import get_carrier
    carrier_row = get_carrier(failing_carrier_id)
    if carrier_row:
        old_reliability = float(carrier_row.get('current_reliability_score', 0.0))
        
    # 3. Update shipments in Supabase
    count = swap_carrier_on_shipments(shipment_ids, new_carrier_id)
    print(f'  Swapped {count} shipments: {failing_carrier_id} → {new_carrier_id}')
    
    # 4. Blacklist failing carrier
    update_carrier_reliability(failing_carrier_id, {
        'blacklisted': True,
        'blacklist_reason': reason,
        'degrading': True,
    })
    
    # 5. Build SwapEvent
    decision_id = f'SWAP-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}-{str(uuid.uuid4())[:6].upper()}'
    swap_event = {
        'event_type':       'CARRIER_SWAP',
        'decision_id':      decision_id,
        'old_carrier_id':   failing_carrier_id,
        'new_carrier_id':   new_carrier_id,
        'shipment_ids':     shipment_ids,
        'reason':           reason,
        'old_reliability':  round(old_reliability, 4),
        'new_reliability':  round(new_reliability, 4),
        'ks_statistic':     round(ks_statistic, 4),
        'ks_pvalue':        round(ks_pvalue, 6),
        'shipments_count':  count,
        'timestamp':        datetime.now(timezone.utc).isoformat(),
    }
    
    # 6. Log to decision_log (F9 reads this for blockchain fingerprinting)
    fingerprint = _fingerprint(swap_event)
    log_decision(
        decision_id=decision_id,
        decision_type='CARRIER_SWAP',
        agent='Actor',
        payload=swap_event,
        sha256_hash=fingerprint,
    )
    
    # 7. Publish to Redis Streams
    publish_swap_event(swap_event)
    
    # 8. Cache for dashboard
    cache_set(f'swap:{decision_id}', swap_event, ttl_seconds=86400)
    
    # 9. Broadcast to WebSocket
    try:
        await ws_manager.broadcast({'type': 'CARRIER_SWAP', 'data': swap_event})
    except Exception as e:
        print(f'  WebSocket broadcast failed: {e}')
        
    print(f'  SwapEvent logged: {decision_id} fingerprint: {fingerprint[:16]}...')
    return swap_event

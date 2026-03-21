import asyncio
from datetime import datetime, timezone
from streams.redis_client import publish_anomaly, cache_set
from api.websocket import ws_manager


def build_anomaly_event(
    shipment: dict,
    severity: str,
    trigger_type: str,
    anomaly_score: float,
) -> dict:
    """Construct the canonical AnomalyEvent dict."""
    return {
        'shipment_id':   shipment['shipment_id'],
        'severity':      severity,
        'trigger_type':  trigger_type,
        'anomaly_score': anomaly_score,
        'carrier_id':    shipment.get('carrier_id', ''),
        'warehouse_id':  shipment.get('warehouse_id', ''),
        'eta_lag_min':   max(0, int(shipment.get('eta_minutes_current', 0)
                                     - shipment.get('eta_minutes_original', 0))),
        'timestamp':     datetime.now(timezone.utc).isoformat(),
        'ood_flag':      False,  # set by F8 — always False here
    }


def publish_and_cache(event: dict) -> str:
    """
    1. Publish event to Redis Streams (Reasoner Agent consumes this).
    2. Cache active incident in Redis with TTL 4 hours.
    Returns Redis message ID.
    """
    # 1. Publish to stream
    msg_id = publish_anomaly(event)

    # 2. Cache incident state (dashboard reads this directly)
    cache_key = f"incident:{event['shipment_id']}"
    cache_set(cache_key, event, ttl_seconds=14400)  # 4 hours

    # Broadcast to WebSocket clients (non-blocking)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(ws_manager.broadcast(event))
    except RuntimeError:
        pass  # no event loop = no dashboard connected yet, fine

    return msg_id

import os
import json
import redis
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

# Stream names — define once, use everywhere
STREAM_REASONER = 'reasoner_queue'
STREAM_ACTOR    = 'actor_queue'
STREAM_SHIPMENT = 'shipment_events'

_redis: Optional[redis.Redis] = None

def get_redis() -> redis.Redis:
    """Singleton Redis client."""
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def publish_anomaly(event: dict) -> str:
    """
    Publish AnomalyEvent to Redis Streams → reasoner_queue.
    Returns the message ID assigned by Redis.
    """
    r = get_redis()
    msg_id = r.xadd(
        STREAM_REASONER,
        {'data': json.dumps(event)},
        maxlen=10000,     # keep last 10k events, auto-trim older ones
        approximate=True
    )
    return msg_id


def publish_shipment_event(event: dict) -> str:
    """Publish raw shipment update to shipment_events stream."""
    r = get_redis()
    return r.xadd(STREAM_SHIPMENT, {'data': json.dumps(event)}, maxlen=50000)


def consume_anomalies(group: str, consumer: str, count: int = 5) -> list[dict]:
    """Read unacknowledged anomalies from Redis Stream as a consumer group."""
    r = get_redis()
    if r is None:
         return []
    try:
         r.xgroup_create(STREAM_REASONER, group, id='0', mkstream=True)
    except Exception:
         pass  # Group already exists

    try:
        messages = r.xreadgroup(group, consumer, {STREAM_REASONER: '>'}, count=count, block=1)
        events = []
        for _, msgs in messages:
            for msg_id, data_dict in msgs:
                if 'data' in data_dict:
                    events.append(json.loads(data_dict['data']))
                r.xack(STREAM_REASONER, group, msg_id)
        return events
    except Exception:
         return []


def publish_cascade_tree(tree: dict) -> str:
    """Publish CascadeTree to actor_queue. F6 consumes this."""
    r = get_redis()
    msg_id = r.xadd(
        STREAM_ACTOR,
        {'data': json.dumps(tree)},
        maxlen=1000, approximate=True
    )
    return msg_id


def cache_set(key: str, value: dict, ttl_seconds: int = 14400) -> None:
    """Store incident state in Redis Cache. TTL default = 4 hours."""
    r = get_redis()
    r.setex(key, ttl_seconds, json.dumps(value))


def cache_get(key: str) -> Optional[dict]:
    """Read incident state from Redis Cache."""
    r = get_redis()
    val = r.get(key)
    return json.loads(val) if val else None

def publish_swap_event(event: dict) -> str:
    """Publish SwapEvent to shipment_events stream for downstream consumers."""
    r = get_redis()
    return r.xadd(
        STREAM_SHIPMENT,
        {'data': json.dumps(event)},
        maxlen=50000,
        approximate=True
    )

def cache_carrier_reliability(carrier_id: str, score: float) -> None:
    """Cache carrier reliability score with 1-hour TTL for fast dashboard reads."""
    cache_set(f'carrier_rel:{carrier_id}', {'score': score, 'carrier_id': carrier_id},
              ttl_seconds=3600)

def consume_from_stream(stream_name: str, consumer_group: str, consumer_name: str, count: int = 5, block_ms: int = 100) -> list[tuple]:
    """Read unacknowledged messages from Redis Stream as a consumer group."""
    r = get_redis()
    if r is None:
         return []
    try:
         r.xgroup_create(stream_name, consumer_group, id='0', mkstream=True)
    except Exception:
         pass

    try:
        messages = r.xreadgroup(consumer_group, consumer_name, {stream_name: '>'}, count=count, block=block_ms)
        parsed_events = []
        for _, msgs in messages:
            for msg_id, data_dict in msgs:
                if 'data' in data_dict:
                    parsed_events.append((msg_id, json.loads(data_dict['data'])))
        return parsed_events
    except Exception:
         return []

def ack_message(stream_name: str, consumer_group: str, msg_id: str) -> None:
    """Acknowledge message processing."""
    r = get_redis()
    if r:
        r.xack(stream_name, consumer_group, msg_id)


# ── F4: Warehouse load cache ───────────────────────────────────
STREAM_CONGESTION = 'congestion_events'   # new stream for F4 events

def set_warehouse_load(warehouse_id: str, load_pct: float,
                        throughput_hr: int, inbound_queue: int) -> None:
  """Write warehouse load state to Redis. Observer updates this every 60s."""
  r = get_redis()
  r.setex(
    f'warehouse_load:{warehouse_id}',
    300,  # TTL 5 minutes — always fresh
    json.dumps({'load_pct': load_pct, 'throughput_hr': throughput_hr,
                'inbound_queue': inbound_queue, 'warehouse_id': warehouse_id})
  )

from typing import Optional

def get_warehouse_load(warehouse_id: str) -> Optional[dict]:
  """Read warehouse load from Redis. Returns None if not cached."""
  r = get_redis()
  val = r.get(f'warehouse_load:{warehouse_id}')
  return json.loads(val) if val else None

def get_all_warehouse_loads() -> dict:
  """Returns {warehouse_id: {load_pct, throughput_hr, inbound_queue}} for all 4 warehouses."""
  r = get_redis()
  keys = r.keys('warehouse_load:*')
  result = {}
  for key in keys:
    val = r.get(key)
    if val:
      data = json.loads(val)
      result[data['warehouse_id']] = data
  return result

def publish_congestion_event(event: dict) -> str:
  """Publish CongestionEvent to reasoner_queue (same queue as AnomalyEvents)."""
  r = get_redis()
  return r.xadd(STREAM_REASONER, {'data': json.dumps(event)}, maxlen=10000, approximate=True)

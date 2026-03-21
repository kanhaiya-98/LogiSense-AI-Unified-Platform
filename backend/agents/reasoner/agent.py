import asyncio, json
from typing import TypedDict

from db.supabase_client import get_shipments_by_ids
from streams.redis_client import get_redis, STREAM_REASONER, consume_anomalies
from agents.reasoner.dag_loader import get_dag
from agents.reasoner.bfs import bfs_downstream
from agents.reasoner.scorer import score_nodes, get_model
from agents.reasoner.cascade_tree import build_and_publish
from api.websocket import ws_manager

CONSUMER_GROUP = 'reasoner_group'
CONSUMER_NAME  = 'reasoner_1'
POLL_INTERVAL_SEC = 5  # process events every 5 seconds

class ReasonerState(TypedDict):
    cycle: int
    events_processed: int
    last_incident_id: str

# ── Pre-warm: load DAG and model at import time ──────────────
_dag = get_dag()  # loads from Supabase once at startup
_model = get_model()  # trains or loads from disk

def process_event_batch(state: ReasonerState) -> ReasonerState:
    """Read up to 5 anomaly events, process each, return updated state."""
    events = consume_anomalies(CONSUMER_GROUP, CONSUMER_NAME, count=20)
    last_id = state['last_incident_id']
    processed = 0
    
    for event in events:
        # Only act on HIGH or CRITICAL
        if event.get('severity') not in ('HIGH', 'CRITICAL'):
            continue
            
        root_id = event['shipment_id']
        print(f'[Reasoner] Processing {event["severity"]} event for {root_id}')
        
        try:
            # 1. BFS traversal
            bfs_results = bfs_downstream(root_id, _dag)
            # [(shipment_id, hop_depth, dep_type), ...]
            
            # 2. Fetch full shipment data for scored nodes
            ids = [r[0] for r in bfs_results]
            shipments = get_shipments_by_ids(ids)
            ship_map = {s['shipment_id']: s for s in shipments}
            
            # 3. Build node dicts with all features + hop metadata
            nodes = []
            for (sid, depth, dep_type) in bfs_results:
                ship = ship_map.get(sid, {'shipment_id': sid})
                nodes.append({**ship, 'hop_depth': depth, 'dep_type': dep_type})
                
            # 4. LightGBM batch scoring
            from streams.redis_client import cache_get
            wh_loads = {}  # pull from Redis if available
            for n in nodes:
                wid = n.get('warehouse_id', '')
                if wid and wid not in wh_loads:
                    cached = cache_get(f'warehouse_load:{wid}')
                    wh_loads[wid] = cached['load_pct'] if cached else 0.0
                    
            scored = score_nodes(nodes, wh_loads)
            
            # 5. Build CascadeTree, publish, cache
            tree = build_and_publish(event, scored)
            last_id = tree['incident_id']
            processed += 1
            
            # 6. Push to WebSocket (non-blocking)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(ws_manager.broadcast({
                        'type': 'cascade_tree', 'payload': tree
                    }))
            except RuntimeError:
                pass
                
        except Exception as e:
            print(f'Reasoner error on {root_id}: {e}')  # never crash
            
    return {'cycle': state['cycle'] + 1, 'events_processed': state['events_processed'] + processed,
            'last_incident_id': last_id}

async def run_reasoner():
    print('Starting Reasoner Agent (Native Loop)...')
    state: ReasonerState = {'cycle': 0, 'events_processed': 0, 'last_incident_id': ''}
    
    while True:
        try:
            state = process_event_batch(state)
        except Exception as e:
            print(f'[Reasoner] Critical loop error: {e}')
        await asyncio.sleep(POLL_INTERVAL_SEC)

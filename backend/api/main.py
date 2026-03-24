import asyncio
import os
import sys
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

# --- Setup sys.path for unified integrations ---
BACKEND_DIR = Path(__file__).resolve().parent.parent
ZEN_DIR = BACKEND_DIR / "zen"
FEAT_DIR = BACKEND_DIR / "features"

for d in [ZEN_DIR, FEAT_DIR, FEAT_DIR / "feature_8", FEAT_DIR / "feature_9", FEAT_DIR / "feature_10"]:
    if str(d) not in sys.path:
        sys.path.append(str(d))

from agents.observer.agent import run_observer
from agents.reasoner.agent import run_reasoner
from agents.actor.agent import run_actor
from api.websocket import ws_manager
from db.supabase_client import get_active_shipments

app = FastAPI(title='LogiSense AI Unified Platform', version='2.0.0')
app_state = {}
app.state.app_state = app_state

# --- Import integrated routers ---
try:
    from zen.routers import demand, routes, eta
    from feature_8.api.routes import router as f8_router
    from feature_9.api import router as f9_router
    from unified_graph import build_logisense_graph
    INTEGRATIONS_LOADED = True
except ImportError as e:
    print(f"Warning: Integrations failed to load. {e}")
    INTEGRATIONS_LOADED = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],   # tighten in production
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
async def startup():
    """Start Observer Agent when FastAPI starts, and initialize Zen models."""
    asyncio.create_task(run_observer())
    asyncio.create_task(run_reasoner())
    asyncio.create_task(run_actor())
    print('Observer + Reasoner + Actor Agents started.')
    
    if INTEGRATIONS_LOADED:
        # Load ZenETA XGBoost
        try:
            from models.eta.xgboost_service import XGBoostETAService
            xgboost_svc = XGBoostETAService(model_dir=os.path.join(ZEN_DIR, "models/eta"))
            xgboost_svc.load_models()
            app_state["xgboost"] = xgboost_svc
            print("✅ XGBoost ETA model loaded")
        except Exception as e:
            print(f"⚠️ XGBoost load failed: {e}")
            
        # Mount unified routers
        app.include_router(demand.router, prefix="/api/demand", tags=["ZenDec"])
        app.include_router(routes.router, prefix="/api/routes", tags=["ZenRTO"])
        app.include_router(eta.router, prefix="/api/eta", tags=["ZenETA"])
        
        # F8: routes.py has prefix "/api/explainability", we just mount it at root
        app.include_router(f8_router, tags=["F8"]) 
        
        # Expose F8 Demo Data
        try:
            from feature_8.mocks.mock_ml_node import run_live_ml_prediction
            from feature_8.api.routes import register_model
            state = run_live_ml_prediction()
            register_model("demo_model", state["model"])
            app_state["f8_demo_predictions"] = state["predictions"]
            app_state["f8_demo_features"] = state["X_df"].to_dict(orient="records")
            print("✅ F8 Mock ML Model registered as 'demo_model'")
        except Exception as e:
            print(f"⚠️ F8 Mock init failed: {e}")
        # F9: api.py
        app.include_router(f9_router, prefix="/api/f9/blockchain", tags=["F9"])
        
        print("✅ Integrated Routers Mounted.")



@app.websocket('/ws/anomalies')
async def websocket_endpoint(websocket: WebSocket):
    """
    Dashboard connects here.
    Publisher (F1) broadcasts anomaly events here.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages if any
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get('/api/cascade/{incident_id}')
async def get_cascade_tree(incident_id: str):
    """Fetch a cached CascadeTree by incident_id."""
    from streams.redis_client import cache_get
    tree = cache_get(f'incident:{incident_id}')
    return tree or {'error': 'not found'}

@app.get('/api/shipments/active')
async def active_shipments():
    """REST endpoint — returns all active shipments for initial dashboard load."""
    return get_active_shipments()


@app.get('/api/health')
async def health():
    return {'status': 'ok', 'agent': 'Observer running'}


@app.post('/api/invoke')
async def invoke_graph(input_data: dict):
    if not INTEGRATIONS_LOADED:
        return {"error": "Integrations not loaded."}
        
    graph = build_logisense_graph()
    state = {
        "model": None, 
        "X_df": None,
        "predictions": input_data.get("predictions", []),
        "new_decision": input_data.get("decision"),
        "pending_decisions": [],
        "blockchain_status": {},
        "tamper_alerts": [],
        "messages": [],
        "current_node": ""
    }
    result = await graph.ainvoke(state)
    return result

@app.get('/api/anomalies/active')
async def get_active_anomalies():
    """Return all currently active anomalies cached in Redis."""
    from streams.redis_client import get_redis
    import json
    r = get_redis()
    if not r:
        return []
    keys = r.keys('incident:*')
    anomalies = []
    for key in keys:
        val = r.get(key)
        if val:
            try:
                anomalies.append(json.loads(val))
            except Exception:
                pass
    # Sort by descending severity, then timestamp
    severity_order = {'CRITICAL': 3, 'HIGH': 2, 'MEDIUM': 1, 'LOW': 0}
    anomalies.sort(key=lambda x: (severity_order.get(x.get('severity', 'LOW'), 0), x.get('timestamp', '')), reverse=True)
    return anomalies

@app.get('/api/explainability/demo_data')
async def f8_demo_data():
    return {
        "predictions": app_state.get("f8_demo_predictions", []),
        "features": app_state.get("f8_demo_features", []),
        "modelKey": "demo_model",
        "debug_keys": list(app_state.keys())
    }

@app.post('/api/trigger-scan')

async def trigger_scan():
    """Immediately run one full Observer + Reasoner cycle. Used by demo_seed.py."""
    import asyncio
    from agents.observer.agent import poll_and_detect
    from agents.reasoner.agent import process_event_batch, ReasonerState
    
    # 1. Run Observer poll (sync, in thread pool to avoid blocking event loop)
    loop = asyncio.get_event_loop()
    cycle, anomalies = await loop.run_in_executor(None, poll_and_detect, 99)
    print(f'[trigger-scan] Observer: {len(anomalies)} anomalies queued')
    
    # 2. Broadcast anomalies to WebSocket immediately
    for ev in anomalies:
        await ws_manager.broadcast(ev)
    
    # 3. Run Reasoner cycle (sync)
    state = ReasonerState(cycle=0, events_processed=0, last_incident_id='')
    state = await loop.run_in_executor(None, process_event_batch, state)
    print(f'[trigger-scan] Reasoner processed {state["events_processed"]} events')
    
    return {'anomalies': len(anomalies), 'reasoner_events': state['events_processed']}

@app.get('/api/carriers/reliability')
async def carrier_reliability():
    """Return current reliability scores for all carriers."""
    from db.supabase_client import get_all_carriers
    carriers = get_all_carriers()
    return [
        {
            'carrier_id': cid,
            'reliability_score': c.get('current_reliability_score', 0),
            'blacklisted': c.get('blacklisted', False),
        }
        for cid, c in carriers.items()
    ]
 
@app.get('/api/decisions/recent')
async def recent_decisions():
    """Return last 20 decisions from decision_log for dashboard."""
    from db.supabase_client import get_client
    client = get_client()
    result = client.table('decision_log') \
        .select('decision_id, decision_type, agent, sha256_hash, created_at, payload') \
        .order('created_at', desc=True) \
        .limit(20) \
        .execute()
    return result.data or []


@app.get('/api/swaps/recent')
async def recent_swaps():
    """Return last 10 carrier swaps read from Redis swap cache."""
    from streams.redis_client import get_redis
    import json
    r = get_redis()
    if not r:
        return []
    keys = r.keys('swap:SWAP-*')
    swaps = []
    for key in keys:
        val = r.get(key)
        if val:
            try:
                swaps.append(json.loads(val))
            except Exception:
                pass
    # Sort newest first by timestamp
    swaps.sort(key=lambda s: s.get('timestamp', ''), reverse=True)
    return swaps[:10]

# ── F4 REST Endpoints ────────────────────────────────────────────
@app.get('/api/warehouses')
async def get_warehouses():
  """Returns all warehouse states for initial heatmap load."""
  from streams.redis_client import get_all_warehouse_loads
  from db.supabase_client import get_all_warehouses
  warehouses = get_all_warehouses()
  loads = get_all_warehouse_loads()
  # Merge Redis live loads into Supabase base data
  for wh in warehouses:
    live = loads.get(wh['warehouse_id'])
    if live: wh.update(live)
  return warehouses

import asyncio
import time

from db.supabase_client import get_active_shipments, get_warehouse_loads, get_latest_carrier_checkin
from agents.observer.rules import (
    check_eta_drift, check_carrier_silence,
    check_status_stall, check_warehouse_load, highest_severity
)
from agents.observer.scorer import score_shipment, is_anomalous
from agents.observer.scorer import score_shipment, is_anomalous
from agents.observer.publisher import build_anomaly_event, publish_and_cache

# F4 Warehouse monitoring imports
from agents.observer.warehouse.monitor import check_warehouses, update_throughput_baseline
from agents.observer.warehouse.forecaster import forecast_load, is_preemptive_flag
from agents.observer.warehouse.publisher import build_and_publish_congestion
from db.supabase_client import get_all_warehouses, get_inbound_shipments
from streams.redis_client import set_warehouse_load, get_all_warehouse_loads
from apscheduler.schedulers.asyncio import AsyncIOScheduler

_throughput_baselines: dict = {}   # {warehouse_id: rolling avg throughput}
_wh_poll_counter = 0               # count 60-second cycles for throughput logging

POLL_INTERVAL_SEC = 300  # poll every 5 minutes


# ── Core polling function ─────────────────────────────────────────
def poll_and_detect(cycle: int) -> tuple[int, list]:
    """
    Single polling cycle:
    1. Fetch all active shipments from Supabase
    2. Fetch warehouse loads
    3. For each shipment: run 4 rules + Isolation Forest
    4. For each anomaly: publish to Redis Streams + cache
    5. Return updated state
    """
    anomalies = []

    try:
        shipments     = get_active_shipments()
        wh_loads      = get_warehouse_loads()
        carrier_cache = {}   # cache checkin lookups within this cycle

        for shipment in shipments:
            flags    = []  # (severity, trigger_type) tuples
            sid      = shipment['shipment_id']
            cid      = shipment.get('carrier_id', '')
            wid      = shipment.get('warehouse_id', '')
            wh_load  = wh_loads.get(wid, 0.0)

            # ── Rule 1: ETA Drift ────────────────────────────────
            flagged, sev, ttype = check_eta_drift(shipment)
            if flagged:
                flags.append((sev, ttype))

            # ── Rule 2: Carrier Silence ──────────────────────────
            if cid not in carrier_cache:
                carrier_cache[cid] = get_latest_carrier_checkin(cid)
            flagged, sev, ttype = check_carrier_silence(shipment, carrier_cache[cid])
            if flagged:
                flags.append((sev, ttype))

            # ── Rule 3: Status Stall ─────────────────────────────
            flagged, sev, ttype = check_status_stall(shipment)
            if flagged:
                flags.append((sev, ttype))

            # ── Rule 4: Warehouse Load ───────────────────────────
            flagged, sev, ttype = check_warehouse_load(wh_load)
            if flagged:
                flags.append((sev, ttype))

            # ── Isolation Forest ─────────────────────────────────
            score = score_shipment(shipment, wh_load)
            if is_anomalous(score) and not flags:  # don't double-flag
                flags.append(('LOW', 'ISOLATION_FOREST'))

            # ── Publish if any flag ──────────────────────────────
            if flags:
                final_sev   = highest_severity([f[0] for f in flags])
                final_ttype = flags[0][1]  # use highest-severity trigger type
                event = build_anomaly_event(shipment, final_sev, final_ttype, score)
                msg_id = publish_and_cache(event)
                anomalies.append(event)
                print(f'  [{final_sev}] {sid} — {final_ttype} (msg: {msg_id})')

        if anomalies:
            print(f'Cycle {cycle}: {len(shipments)} shipments, {len(anomalies)} anomalies')
        else:
            print(f'Cycle {cycle}: {len(shipments)} shipments, 0 anomalies')

        # ── F4: Sync warehouse loads from Supabase → Redis & check for congestion ──
        global _throughput_baselines, _wh_poll_counter
        _wh_poll_counter += 1
        try:
            db_warehouses = get_all_warehouses()
            for wh in db_warehouses:
                wid = wh.get('warehouse_id')
                if not wid: continue
                load_pct    = float(wh.get('current_load_pct') or 0)
                throughput  = int(wh.get('throughput_per_hr') or wh.get('throughput_per_hour') or 0)
                inbound_q   = int(wh.get('inbound_queue') or 0)
                set_warehouse_load(wid, load_pct=load_pct,
                                   throughput_hr=throughput, inbound_queue=inbound_q)

            # Broadcast live warehouse states to WebSocket for heatmap
            from api.websocket import ws_manager
            import asyncio as _asyncio
            loop = _asyncio.get_event_loop()
            if loop.is_running():
                _asyncio.create_task(ws_manager.broadcast({
                    'type': 'warehouse_update',
                    'warehouses': db_warehouses
                }))
        except Exception as wh_sync_err:
            print(f'[Observer] Warehouse sync error: {wh_sync_err}')

        wh_flags = check_warehouses(_throughput_baselines)
        for flag in wh_flags:
            inbound = get_inbound_shipments(flag['warehouse_id'])
            build_and_publish_congestion(flag, arima_forecast=None,
                                         affected_shipment_count=len(inbound))

        # Update rolling baselines
        wh_loads_now = get_all_warehouse_loads()
        for wid, data in wh_loads_now.items():
            _throughput_baselines = update_throughput_baseline(
                wid, data['throughput_hr'], _throughput_baselines
            )

    except Exception as e:
        print(f'Observer poll error (cycle {cycle}): {e}')
        # Never crash the loop — log and continue

    return cycle + 1, anomalies


# ── Entry point ──────────────────────────────────────────────────
async def run_arima_forecast_cycle():
    """Called every 15 min by APScheduler. Runs ARIMA on each warehouse."""
    loads = get_all_warehouse_loads()
    for wid, state in loads.items():
        projected = forecast_load(wid, state['load_pct'])
        if is_preemptive_flag(projected) and state['load_pct'] < 85.0:
            # Pre-emptive flag — load not yet critical but will be
            from agents.observer.warehouse.monitor import _make_flag
            flag = _make_flag(wid, state, 'LOW', 'ARIMA_PREEMPTIVE', 'STAGGER_PREEMPTIVE')
            flag['stagger_minutes'] = 20
            inbound = get_inbound_shipments(wid)
            build_and_publish_congestion(flag, projected, len(inbound))
            print(f'[F4] Pre-emptive flag: {wid} projected at {projected}% in 2hrs')

async def run_observer():
    """Run the Observer Agent polling loop forever."""
    print('Starting Observer Agent...')
    print(f'  Poll interval: {POLL_INTERVAL_SEC} seconds')
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_arima_forecast_cycle, 'interval', minutes=15)
    scheduler.start()
    print('ARIMA forecast cron started (every 15 min).')
    
    cycle = 1
    total_flagged = 0

    while True:
        cycle, anomalies = poll_and_detect(cycle)
        total_flagged += len(anomalies)
        await asyncio.sleep(POLL_INTERVAL_SEC)

if __name__ == '__main__':
    asyncio.run(run_observer())

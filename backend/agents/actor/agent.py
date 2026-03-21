import asyncio

from agents.actor.drift import run_ks_test, scan_all_carriers
from agents.actor.bayesian import should_swap, get_carrier_reliability_score
from agents.actor.swap import swap_carrier
from db.supabase_client import get_all_carrier_ids
from streams.redis_client import (
    consume_from_stream, ack_message
)
from streams.redis_client import get_redis
from agents.actor.tools.redirect_warehouse import redirect_warehouse
from agents.actor.tools.adjust_intake_schedule import adjust_intake_schedule
import json

ACTOR_QUEUE      = 'actor_queue'
CONSUMER_GROUP   = 'actor_group'
CONSUMER_NAME    = 'actor_1'
DRIFT_SCAN_EVERY = 1800  # 30 minutes in seconds
RELIABILITY_THRESHOLD_FOR_SWAP = 0.65

# ── MODE 1: Event-driven swap from F2 CascadeTree ────────────────
async def handle_cascade_event(cascade_tree: dict) -> None:
    """
    F2 found a cascade rooted at a carrier.
    If that carrier's reliability is below threshold, swap immediately.
    """
    root_shipment = cascade_tree.get('root_shipment_id')
    root_carrier = None
    for node in cascade_tree.get('nodes', []):
        if node.get('shipment_id') == root_shipment:
            root_carrier = node.get('carrier_id')
            break
            
    if not root_carrier:
        return
        
    score = get_carrier_reliability_score(root_carrier)
    swap_needed, reason = should_swap(root_carrier)
    
    if not swap_needed:
        print(f'Actor: {root_carrier} reliability={score:.2f} — no swap needed')
        return
        
    # Get shipment IDs from cascade tree for targeted swap
    affected_ids = [
        node['shipment_id']
        for node in cascade_tree.get('nodes', [])
        if node.get('carrier_id') == root_carrier
    ]
    
    # Run KS test to get drift stats for the swap record
    ks_result = run_ks_test(root_carrier)
    
    await swap_carrier(
        failing_carrier_id=root_carrier,
        reason=f'CASCADE_TRIGGER — {reason}',
        ks_statistic=ks_result.get('ks_statistic', 0.0),
        ks_pvalue=ks_result.get('ks_pvalue', 1.0),
        shipment_ids=affected_ids if affected_ids else None,
    )

async def consume_actor_queue():
    """Event-loop driven queue consumer"""
    
    while True:
        try:
            messages = consume_from_stream(
                stream_name=ACTOR_QUEUE,
                consumer_group=CONSUMER_GROUP,
                consumer_name=CONSUMER_NAME,
                count=3,
                block_ms=100,
            )
            
            for msg_id, cascade_tree in messages:
                try:
                    await handle_cascade_event(cascade_tree)
                except Exception as e:
                    print(f'Actor event handling error: {e}')
                finally:
                    ack_message(ACTOR_QUEUE, CONSUMER_GROUP, msg_id)
        except Exception as e:
            print(f'Actor Queue Consumption Error: {e}')
            
        await asyncio.sleep(0.5)

# ── MODE 1B: Event-driven warehouse routing from F4 ──────────────────
def handle_congestion_event(event: dict) -> None:
    """Route congestion event to correct MCP tool based on recommended_action."""
    action = event.get('recommended_action')
    wid = event.get('warehouse_id')
    alt = event.get('alternate_warehouse_id')
    if action == 'REDIRECT' and alt:
        redirect_warehouse(wid, alt, event)
    elif action in ('STAGGER', 'STAGGER_PREEMPTIVE'):
        stagger_min = event.get('stagger_minutes', 15)
        adjust_intake_schedule(wid, stagger_min, event)
    else:
        print(f'[Actor] No action taken for {wid}: action={action}, alt={alt}')

async def consume_reasoner_queue():
    """Event-loop driven queue consumer for F4 congestion events"""
    STREAM_REASONER = 'reasoner_queue'
    while True:
        try:
            messages = consume_from_stream(
                stream_name=STREAM_REASONER,
                consumer_group=CONSUMER_GROUP,
                consumer_name=CONSUMER_NAME,
                count=5,
                block_ms=100,
            )
            for msg_id, event in messages:
                try:
                    if event.get('trigger_type') in ('LOAD_THRESHOLD', 'THROUGHPUT_DROP', 'ARIMA_PREEMPTIVE'):
                        handle_congestion_event(event)
                except Exception as e:
                    print(f'Actor congestion handling error: {e}')
                finally:
                    ack_message(STREAM_REASONER, CONSUMER_GROUP, msg_id)
        except Exception as e:
            pass # ignore timeouts
        await asyncio.sleep(0.5)

# ── MODE 2: Scheduled drift scan every 30 minutes ────────────────
async def scheduled_drift_scan() -> None:
    """
    Run KS drift test on ALL carriers every 30 minutes.
    For any drifting carrier: run Bayesian check + swap if needed.
    """
    print('Running scheduled drift scan on all carriers...')
    carrier_ids = get_all_carrier_ids()
    drifting = scan_all_carriers(carrier_ids)
    
    for drift_result in drifting:
        cid = drift_result['carrier_id']
        swap_needed, reason = should_swap(cid)
        if swap_needed:
            await swap_carrier(
                failing_carrier_id=cid,
                reason=f'DRIFT_DETECTED — {reason}',
                ks_statistic=drift_result['ks_statistic'],
                ks_pvalue=drift_result['ks_pvalue'],
            )
            
    if not drifting:
        print(f'  Drift scan complete: all {len(carrier_ids)} carriers normal')

async def run_drift_scheduler() -> None:
    """Run scheduled_drift_scan every 30 minutes forever."""
    # Run drift scan immediately on startup to catch existing issues
    await scheduled_drift_scan()
    while True:
        await asyncio.sleep(DRIFT_SCAN_EVERY)
        try:
            await scheduled_drift_scan()
        except Exception as e:
            print(f'Drift scan error: {e}')

async def run_actor():
    """Run Actor Agent: event consumer + drift scheduler in parallel."""
    print('Starting Actor Agent...')
    print(f'  Consuming from: {ACTOR_QUEUE}')
    print(f'  Drift scan interval: {DRIFT_SCAN_EVERY}s (30 min)')
    
    await asyncio.gather(
        consume_actor_queue(),
        consume_reasoner_queue(),
        run_drift_scheduler(),
    )

if __name__ == '__main__':
    asyncio.run(run_actor())

# scripts/demo_seed.py — full F1 + F2 + F3 demo chain
# Run: python scripts/demo_seed.py

from db.supabase_client import get_client
from datetime import datetime

client = get_client()

print('Seeding demo data...')

# ── Step 1: Reset all carriers to healthy ────────────────────────
print('Step 1: Reset all carriers to healthy state')
client.table('carriers').update({
    'blacklisted': False,
    'blacklist_reason': None,
    'degrading': False,
}).neq('carrier_id', 'CAR-99').execute()   # update all

# ── Step 2: Degrade CAR-07 ───────────────────────────────────────
print('Step 2: Degrade CAR-07 to reliability 0.47')
client.table('carriers').update({
    'current_reliability_score': 0.47,
    'on_time_rate_30d': 0.47,
    'alpha_param': 47.0,   # 47 successes
    'beta_param':  53.0,   # 53 failures → mean = 0.47
    'degrading': True,
}).eq('carrier_id', 'CAR-07').execute()

# ── Step 2.5: Force CAR-07 historical events to look degraded ────
print('Step 2.5: Force CAR-07 recent history to trigger KS-test')
recent_events = client.table('carrier_events').select('event_id').eq('carrier_id', 'CAR-07').order('date', desc=True).limit(200).execute()
if recent_events.data:
    event_ids = [e['event_id'] for e in recent_events.data]
    for i in range(0, len(event_ids), 50):
        chunk = event_ids[i:i+50]
        client.table('carrier_events').update({'on_time': 0, 'effective_reliability': 0.2}).in_('event_id', chunk).execute()

# ── Step 3: Make CAR-07 carrier_events look old (silence) ────────
print('Step 3: Push CAR-07 last check-in to 25 min ago (triggers silence)')
# All other carriers: check-in = now
import time
from datetime import date
today = date.today().isoformat()
current_hour = datetime.now().hour

# Reset all carriers to now
try:
    client.rpc('update_carrier_checkins', {
        'p_date': today, 'p_hour': current_hour
    }).execute()
except Exception as e:
    print('RPC failed, trying raw data update...')
    print('ERROR:', e)
    pass # If RPC doesn't exist, we skip for now

# ── Step 4: Make WH-02 near capacity ─────────────────────────────
print('Step 4: Set WH-02 load to 92%')
client.table('warehouses').update({
    'current_load_pct': 92.5
}).eq('warehouse_id', 'WH-02').execute()

client.table('live_shipments').update({
    'status': 'IN_TRANSIT',
}).eq('warehouse_id', 'WH-02').execute()

# ── Step 4.5: Seed Warehouse Load to Redis ───────────────────────
print('Step 4.5: Seed Warehouse Load to Redis for Actor')
from streams.redis_client import set_warehouse_load
set_warehouse_load('WH-01', load_pct=45.0, throughput_hr=62, inbound_queue=8)
set_warehouse_load('WH-02', load_pct=92.5, throughput_hr=22, inbound_queue=31)  # CONGESTED
set_warehouse_load('WH-03', load_pct=54.0, throughput_hr=55, inbound_queue=6)
set_warehouse_load('WH-04', load_pct=31.0, throughput_hr=70, inbound_queue=3)  # best redirect target

# ── Step 5: Inject SLA-critical shipments on CAR-07 ──────────────
print('Step 5: Make CAR-07 shipments overdue')
client.table('live_shipments').update({
    'eta_minutes_current': 480,
    'status': 'CARRIER_SILENT',
}).eq('carrier_id', 'CAR-07').execute()

print()
print('Demo seed complete. Expected sequence:')
print('  T+0s  : F1 fires CRITICAL — CAR-07 silence + ETA drift')
print('  T+5s  : F2 fires — BFS cascade tree, 20+ nodes at risk')
print('  T+10s : F3 fires — KS drift CRITICAL, swap CAR-07 → CAR-02')
print('  T+12s : Dashboard shows swap confirmation + decision log entry')
print('  T+60s : F4 Observer detects WH-02 congestion logic')
print('  T+65s : F4 Actor triggers redirect WH-02 → WH-04')

# ── Step 6: Trigger immediate Observer + Reasoner scan ───────────
print()
print('Step 6: Triggering immediate pipeline scan...')
import urllib.request, json as _json
try:
    req = urllib.request.Request(
        'http://localhost:8000/api/trigger-scan',
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = _json.loads(resp.read())
        print(f'  ✓ Observer: {result.get("anomalies", 0)} anomalies detected')
        print(f'  ✓ Reasoner: {result.get("reasoner_events", 0)} cascade trees built')
        print('  → Watch the dashboard — cascade tree and anomaly feed should update NOW!')
except Exception as e:
    print(f'  Trigger failed (is the server running?): {e}')

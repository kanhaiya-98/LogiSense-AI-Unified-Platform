# scripts/generate_warehouses.py — complete file
from db.supabase_client import get_client

WAREHOUSES = [
  {"warehouse_id": "WH-01", "city": "Mumbai",    "lat": 19.0760, "lng": 72.8777,
   "capacity_units": 500, "current_load_pct": 45.0, "throughput_per_hr": 62, "inbound_queue": 8, "status": "NORMAL"},
  {"warehouse_id": "WH-02", "city": "Delhi",     "lat": 28.7041, "lng": 77.1025,
   "capacity_units": 500, "current_load_pct": 68.0, "throughput_per_hr": 48, "inbound_queue": 14, "status": "NORMAL"},
  {"warehouse_id": "WH-03", "city": "Bangalore", "lat": 12.9716, "lng": 77.5946,
   "capacity_units": 500, "current_load_pct": 52.0, "throughput_per_hr": 55, "inbound_queue": 6, "status": "NORMAL"},
  {"warehouse_id": "WH-04", "city": "Pune",      "lat": 18.5204, "lng": 73.8567,
   "capacity_units": 500, "current_load_pct": 31.0, "throughput_per_hr": 70, "inbound_queue": 3, "status": "NORMAL"},
]

def seed_warehouses():
  client = get_client()
  client.table('warehouses').upsert(WAREHOUSES).execute()
  print(f'Seeded {len(WAREHOUSES)} warehouses.')

if __name__ == '__main__':
  seed_warehouses()

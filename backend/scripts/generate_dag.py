import random, pandas as pd
from db.supabase_client import get_client

def generate_dependencies(shipments: list[dict]) -> list[dict]:
    """Build DAG edges. Each shipment gets up to 3 downstream deps."""
    deps = []
    for ship in shipments:
        cid, wid = ship['carrier_id'], ship['warehouse_id']
        # Find SAME_CARRIER deps
        same_carrier = [s for s in shipments
                        if s['carrier_id'] == cid and s['shipment_id'] != ship['shipment_id']]
        for dep in random.sample(same_carrier, min(2, len(same_carrier))):
            deps.append({'upstream_id': ship['shipment_id'],
                         'downstream_id': dep['shipment_id'],
                         'dependency_type': 'SAME_CARRIER'})
        # Find SAME_WAREHOUSE deps
        same_wh = [s for s in shipments
                   if s['warehouse_id'] == wid and s['shipment_id'] != ship['shipment_id']]
        for dep in random.sample(same_wh, min(1, len(same_wh))):
            deps.append({'upstream_id': ship['shipment_id'],
                         'downstream_id': dep['shipment_id'],
                         'dependency_type': 'SAME_WAREHOUSE'})
    return deps

if __name__ == '__main__':
    client = get_client()
    ships = client.table('live_shipments').select('shipment_id,carrier_id,warehouse_id').execute().data
    deps = generate_dependencies(ships)
    
    # Deduplicate and batch upload
    seen = set()
    unique = []
    for d in deps:
        key = (d['upstream_id'], d['downstream_id'])
        if key not in seen:
            seen.add(key)
            unique.append(d)
            
    # Upsert to Supabase
    client.table('shipment_dependencies').upsert(unique).execute()
    print(f'Uploaded {len(unique)} dependency edges.')

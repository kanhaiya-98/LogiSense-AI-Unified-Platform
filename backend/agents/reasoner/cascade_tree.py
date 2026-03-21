from datetime import datetime, timezone
from streams.redis_client import publish_cascade_tree, cache_set
from agents.reasoner.dag_loader import get_dag

def build_and_publish(
    anomaly_event: dict,
    scored_nodes: list[dict]
) -> dict:
    """
    Build CascadeTree JSON from scored nodes.
    Publishes to actor_queue and caches each node incident.
    Returns the CascadeTree dict.
    """
    graph = get_dag()
    root_id = anomaly_event['shipment_id']
    
    # Build edges list from the graph for only the nodes in our scored set
    node_ids = {n['shipment_id'] for n in scored_nodes}
    edges = []
    for u, v, data in graph.edges(data=True):
        if u in node_ids and v in node_ids:
            edges.append({
                'source': u,
                'target': v,
                'dependency_type': data.get('dependency_type', 'SEQUENTIAL')
            })
            
    incident_id = f"INC-{root_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    tree = {
        'incident_id': incident_id,
        'root_shipment_id': root_id,
        'trigger_severity': anomaly_event.get('severity', 'HIGH'),
        'total_at_risk': len(scored_nodes),
        'nodes': scored_nodes,
        'edges': edges,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }
    
    # Publish to actor_queue for F6
    publish_cascade_tree(tree)
    
    # Cache per-node state for dashboard reads
    for node in scored_nodes:
        cache_set(f"cascade_node:{node['shipment_id']}", node, ttl_seconds=14400)
    cache_set(f"incident:{incident_id}", tree, ttl_seconds=14400)
    
    print(f'CascadeTree published: {incident_id} — {len(scored_nodes)} nodes at risk')
    return tree

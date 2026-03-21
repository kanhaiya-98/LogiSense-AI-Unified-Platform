from collections import deque
import networkx as nx
from typing import List, Tuple

MAX_DEPTH = 5  # limit BFS to 5 hops — beyond this, causal link is too weak

def bfs_downstream(
    root_id: str,
    graph: nx.DiGraph
) -> List[Tuple[str, int, str]]:
    """
    BFS from root_id. Returns list of tuples:
    (shipment_id, hop_depth, dependency_type)
    Root node is included at depth 0 with dependency_type='ROOT'.
    """
    if root_id not in graph:
        # Root not in DAG — isolated shipment, still score it alone
        return [(root_id, 0, 'ROOT')]
    
    visited = set()
    queue = deque([(root_id, 0, 'ROOT')])
    result = []
    
    while queue:
        node, depth, dep_type = queue.popleft()
        if node in visited:
            continue
        
        visited.add(node)
        result.append((node, depth, dep_type))
        
        if depth >= MAX_DEPTH:
            continue  # don't go deeper than MAX_DEPTH
            
        for neighbour in graph.successors(node):
            if neighbour not in visited:
                edge_data = graph.get_edge_data(node, neighbour)
                dtype = edge_data.get('dependency_type', 'SEQUENTIAL')
                queue.append((neighbour, depth + 1, dtype))
                
    return result

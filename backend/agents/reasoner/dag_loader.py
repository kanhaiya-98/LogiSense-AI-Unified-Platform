import networkx as nx
from db.supabase_client import get_all_dependencies

from typing import Optional

_graph: Optional[nx.DiGraph] = None

def get_dag() -> nx.DiGraph:
    """
    Singleton. Loads dependency graph once at startup.
    Nodes = shipment_ids. Edges = directed from upstream → downstream.
    """
    global _graph
    if _graph is not None:
        return _graph
    print('Loading shipment dependency DAG from Supabase...')
    edges = get_all_dependencies()
    _graph = nx.DiGraph()
    for edge in edges:
        _graph.add_edge(
            edge['upstream_id'],
            edge['downstream_id'],
            dependency_type=edge['dependency_type']
        )
    print(f'  DAG loaded: {_graph.number_of_nodes()} nodes, {_graph.number_of_edges()} edges')
    return _graph

def invalidate_dag():
    """Call this if you need to reload after data changes. Not used in normal flow."""
    global _graph
    _graph = None

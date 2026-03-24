from __future__ import annotations

import os
import sys
from pathlib import Path

# Add feature directories to sys.path to resolve internal imports
ROOT_DIR = Path(__file__).parent.absolute()
for folder in ["feature_8", "feature_9", "feature_10"]:
    path = str(ROOT_DIR / folder)
    if path not in sys.path:
        sys.path.append(path)

import logging
from typing import Any, Dict, List, Optional, TypedDict
from langgraph.graph import StateGraph, END

# Import nodes from features
from feature_8.agent.explainability_node import explainability_node
from feature_9.blockchain_node import build_blockchain_node

# Define the Unified Agent State
class AgentState(TypedDict):
    # F8 (Explainability) Inputs
    model: Optional[Any]
    X_df: Optional[Any]
    predictions: Optional[List[Dict[str, Any]]]
    feature_names: Optional[List[str]]
    
    # F8 Outputs
    shap_heatmap_json: Optional[Dict[str, Any]]
    shap_matrix_json: Optional[Dict[str, Any]]
    shap_waterfall_json: Optional[Dict[str, Any]]
    top_features: Optional[List[str]]
    
    # F9 (Blockchain) Inputs/Outputs
    new_decision: Optional[Dict[str, Any]]
    latest_decision: Optional[Dict[str, Any]]
    pending_decisions: List[Dict[str, Any]]
    blockchain_status: Dict[str, Any]
    tamper_alerts: List[str]
    
    # Common
    messages: List[Any]
    error: Optional[str]
    current_node: str

def predictor_mock_node(state: AgentState) -> AgentState:
    """Mock node for testing if no real predictor is provided."""
    print("[MOCK] Running Predictor Node...")
    # In a real app, this would be Feature 5 or similar
    return {
        **state,
        "current_node": "predictor",
        "new_decision": {
            "decision_id": "mock-abc-123",
            "agent_id": "actor",
            "action": "route_via_carrier_A",
            "actual_co2_kg": 12.5,
            "baseline_co2_kg": 15.0
        }
    }

def build_logisense_graph():
    # 1. Initialize Nodes
    bc_node = build_blockchain_node()
    
    # 2. Setup Graph
    workflow = StateGraph(AgentState)
    
    # 3. Add Nodes
    workflow.add_node("predictor", predictor_mock_node)
    workflow.add_node("explainability", explainability_node)
    workflow.add_node("blockchain", bc_node)
    
    # 4. Define Edges
    workflow.set_entry_point("predictor")
    workflow.add_edge("predictor", "explainability")
    workflow.add_edge("explainability", "blockchain")
    workflow.add_edge("blockchain", END)
    
    return workflow.compile()

if __name__ == "__main__":
    graph = build_logisense_graph()
    print("LogiSense LangGraph compiled successfully.")

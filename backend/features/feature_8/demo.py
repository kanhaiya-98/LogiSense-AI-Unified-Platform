from __future__ import annotations
"""
demo.py — Run Feature 8 completely standalone.
No other features needed. Uses mock ML output.

Usage:
    cd your_project_root
    python -m feature_8.demo

What it does:
    1. Generates synthetic child immunization data
    2. Trains a mock XGBoost model (simulating Feature 5)
    3. Runs the Feature 8 explainability node
    4. Saves all 3 charts as interactive HTML files you can open in a browser
    5. Prints a summary of what was generated
"""

import json
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from feature_8.mocks.mock_ml_node import run_mock_ml_prediction
from feature_8.agent.explainability_node import explainability_node

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "demo_output")


def save_plotly_html(fig_dict: dict, filename: str):
    """Saves a Plotly figure dict as a standalone interactive HTML file."""
    try:
        import plotly.graph_objects as go
        fig = go.Figure(fig_dict)
        path = os.path.join(OUTPUT_DIR, filename)
        fig.write_html(path, include_plotlyjs="cdn", full_html=True)
        print(f"  ✓ Saved: {path}")
    except Exception as e:
        print(f"  ✗ Could not save {filename}: {e}")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("\n" + "=" * 60)
    print("  Feature 8 — ML Explainability Demo")
    print("=" * 60)

    # Step 1: Simulate ML prediction output (Feature 5's job)
    print("\n[1/3] Generating mock ML predictions (60 children)...")
    state = run_mock_ml_prediction(n_children=60)
    print(f"  ✓ Model: {type(state['model']).__name__}")
    print(f"  ✓ Features: {state['feature_names']}")
    print(f"  ✓ Predictions: {len(state['predictions'])} children")
    scores = [p['risk_score'] for p in state['predictions']]
    print(f"  ✓ Risk range: {min(scores):.1f} – {max(scores):.1f}")

    # Step 2: Run Feature 8 explainability node
    print("\n[2/3] Running SHAP explainability node...")
    result = explainability_node(state)

    if result.get("error"):
        print(f"  ✗ Error: {result['error']}")
        sys.exit(1)

    print(f"  ✓ Top features: {result['top_features']}")
    print(f"  ✓ Heatmap: {len(result['shap_heatmap_json']['data'])} traces")
    print(f"  ✓ Matrix: generated")
    print(f"  ✓ Waterfall: generated")

    # Step 3: Save charts
    print(f"\n[3/3] Saving interactive HTML charts to {OUTPUT_DIR}/...")
    save_plotly_html(result["shap_heatmap_json"],  "heatmap.html")
    save_plotly_html(result["shap_matrix_json"],   "risk_matrix.html")
    save_plotly_html(result["shap_waterfall_json"], "waterfall.html")

    # Save state summary as JSON (for inspection)
    summary = {
        "top_features": result["top_features"],
        "children_analyzed": len(state["predictions"]),
        "risk_distribution": {
            "LOW":      sum(1 for p in state["predictions"] if p["risk_score"] < 25),
            "MEDIUM":   sum(1 for p in state["predictions"] if 25 <= p["risk_score"] < 50),
            "HIGH":     sum(1 for p in state["predictions"] if 50 <= p["risk_score"] < 70),
            "CRITICAL": sum(1 for p in state["predictions"] if p["risk_score"] >= 70),
        },
        "state_keys_written": ["shap_heatmap_json", "shap_matrix_json",
                                "shap_waterfall_json", "top_features", "shap_values_raw"],
    }
    summary_path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ Saved: {summary_path}")

    print("\n" + "=" * 60)
    print("  Feature 8 demo complete. Open the HTML files in your browser.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()

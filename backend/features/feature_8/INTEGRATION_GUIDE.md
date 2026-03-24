# Feature 8 — Integration Guide
## For Every Other Feature Team & Final Project Assembly

> **Read this before integrating Feature 8 into the main project.**
> This document covers: what Feature 8 does, what it needs from other features,
> what it gives back, how to wire it in, and every edge case that could cause errors.

---

## 1. What Feature 8 Does (Plain English)

Feature 8 is the **"Why did the AI say that?"** layer of the system.

After the ML model predicts which children are at risk, Feature 8:
1. Runs SHAP (a mathematical technique) on the model to explain each prediction
2. Generates **3 interactive charts** showing judges and ASHA workers exactly why the model flagged each child
3. Makes these charts available to the React frontend AND to any downstream agent that needs them

The charts are:
- **SHAP Heatmap** — every child × every feature, colored by how much each feature pushed risk up or down
- **Risk Stratification Matrix** — a grid showing average risk by Days Overdue × Vaccines Missed segment
- **Waterfall Chart** — single-child deep dive: "this child scored 78 because days_overdue added +32, vaccines_missed added +18, ..."

**Nothing is hardcoded.** Every chart is generated fresh from the actual ML prediction.

---

## 2. Feature 8's Position in the LangGraph

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LANGGRAPH PIPELINE                           │
│                                                                     │
│  [F1: User Query]                                                   │
│       ↓                                                             │
│  [F2: Orchestrator / Router Agent]                                  │
│       ↓                                                             │
│  [F3: Data Ingestion Agent]  ──writes──► raw_data                  │
│       ↓                                                             │
│  [F4: Data Preprocessing]    ──writes──► X_df (cleaned)            │
│       ↓                                                             │
│  [F5: ML Prediction Agent]   ──writes──► model, predictions        │
│       ↓                                                             │
│  [F8: Explainability Agent]  ◄── THIS FEATURE                      │
│       ↓                                                             │
│  [F6: ASHA Dashboard Agent]  ──reads──► shap_matrix_json           │
│  [F9: Report Generator]      ──reads──► shap_heatmap_json          │
│  [F10: Alert Agent]          ──reads──► top_features               │
└─────────────────────────────────────────────────────────────────────┘
```

Feature 8 sits between ML Prediction and all output/display agents.

---

## 3. What Feature 8 READS from Graph State

These keys MUST be in state when Feature 8's node runs.
The ML Prediction agent (Feature 5) is responsible for writing them.

```python
state = {
    # ── REQUIRED — Feature 5 MUST write these ──────────────────────────
    "model": <trained sklearn/XGBoost model>,
    # Any model with .predict_proba() method. XGBoost preferred.
    # DO NOT pass a pipeline with preprocessing — pass the raw estimator.

    "X_df": <pandas DataFrame>,
    # The exact DataFrame used for model.predict_proba(X_df).
    # Shape: (n_children, n_features).
    # Column names must be consistent strings (no spaces → use underscores).

    "predictions": [
        {"child_id": "C001", "risk_score": 72.3, "risk_label": "HIGH"},
        {"child_id": "C002", "risk_score": 18.1, "risk_label": "LOW"},
        # ... one dict per row in X_df, same order
    ],
    # risk_score must be 0–100 (not 0–1 probability).
    # child_id must be a string.
    # risk_label is optional but helpful.

    # ── OPTIONAL but useful ─────────────────────────────────────────────
    "feature_names": ["days_overdue", "vaccines_missed", ...],
    # If not provided, uses X_df.columns automatically.
}
```

### ⚠️ Common mistakes that will break Feature 8

| Mistake | Fix |
|---------|-----|
| `X_df` has been scaled/normalized but model expects raw values | Pass raw X_df or retrain without scaling inside the estimator |
| `risk_score` is 0–1 probability instead of 0–100 | Multiply by 100 before writing to state |
| `predictions` list length ≠ `X_df` row count | They must be the same length, same order |
| Model is wrapped in `Pipeline` with a scaler | Extract just the estimator: `pipeline.named_steps['classifier']` |
| `X_df` has NaN values | Fill NaN before writing to state — SHAP cannot handle NaN |

---

## 4. What Feature 8 WRITES to Graph State

After Feature 8 runs, these keys are available for ALL downstream agents:

```python
state = {
    # ── Written by Feature 8 ────────────────────────────────────────────
    "shap_heatmap_json":  <dict>,   # Plotly figure JSON — use in React with <Plot data={...} layout={...} />
    "shap_matrix_json":   <dict>,   # Plotly figure JSON — risk stratification grid
    "shap_waterfall_json": <dict>,  # Plotly figure JSON — single child explanation
    "top_features":       ["days_overdue", "vaccines_missed", ...],  # list of str, sorted by importance
    "shap_values_raw":    [[...], [...], ...],  # list of lists — raw SHAP array if needed
    "error":              None,     # None if success, error string if failed
    "current_node":       "explainability",
}
```

### How downstream features use these:

**Feature 6 (ASHA Dashboard):**
```jsx
import { ExplainabilityWidget } from '../feature_8/frontend';
// Show the risk matrix on the dashboard
<ExplainabilityWidget chartType="matrix" predictions={...} features={...} modelKey={...} />
```

**Feature 9 (Report Generator):**
```python
# In your report agent, read from state:
top_drivers = state["top_features"][:3]
heatmap = state["shap_heatmap_json"]  # embed as interactive HTML in report
```

**Feature 10 (Alert Agent):**
```python
# Use top features to personalize alert messages:
top = state["top_features"][0]  # e.g. "days_overdue"
alert_msg = f"High risk flagged — primary driver: {top}"
```

---

## 5. How to Wire Feature 8 into the Main LangGraph

In your **main graph file** (`main_graph.py` or wherever you build the graph):

```python
from langgraph.graph import StateGraph, END
from feature_8.agent.explainability_node import explainability_node
from feature_8.agent.state_schema import GraphState

# Build graph
graph = StateGraph(GraphState)

# ... add all other nodes ...

# Add Feature 8
graph.add_node("explainability", explainability_node)

# Wire edges: F5 → F8 → downstream
graph.add_edge("ml_prediction", "explainability")
graph.add_edge("explainability", "asha_dashboard")    # or whatever F6 is named
graph.add_edge("explainability", "report_generator")  # F9

app = graph.compile()
```

**Conditional routing (if ML fails, skip Feature 8):**
```python
def route_after_ml(state):
    if state.get("error"):
        return "error_handler"
    return "explainability"

graph.add_conditional_edges("ml_prediction", route_after_ml, {
    "explainability": "explainability",
    "error_handler": "error_handler",
})
```

---

## 6. How to Register the Model for API Endpoints

Feature 8's FastAPI endpoints (`/api/explainability/*`) need to look up the trained model.
Your ML agent **must** call `register_model()` after training:

```python
# In Feature 5's code, after model.fit():
from feature_8.api.routes import register_model

model_key = f"session_{session_id}"   # unique per user session
register_model(model_key, trained_model)

# Then write model_key to state so the frontend knows which key to use:
state["model_artifact_key"] = model_key
```

The frontend then uses this key in its API calls automatically.

---

## 7. How to Add Feature 8's Router to the Main FastAPI App

In your main `app.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from feature_8.api.routes import router as explainability_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Feature 8
app.include_router(explainability_router)

# Mount other features...
# app.include_router(feature_5_router)
# app.include_router(feature_6_router)
```

---

## 8. How to Use Feature 8 on the React Frontend

### Option A — Full dashboard (dedicated explainability page)
```jsx
import { ExplainabilityDashboard } from './feature_8/frontend';

function ExplainabilityPage({ mlResult }) {
  return (
    <ExplainabilityDashboard
      predictions={mlResult.predictions}
      features={mlResult.features}      // array of feature objects
      modelKey={mlResult.modelKey}
      autoLoad={true}
    />
  );
}
```

### Option B — Embedded widget (inside another feature's page)
```jsx
import { ExplainabilityWidget } from './feature_8/frontend';

// Matrix only, compact
<ExplainabilityWidget chartType="matrix" height={300} {...mlResult} />

// Waterfall for child index 5
<ExplainabilityWidget chartType="waterfall" childIdx={5} height={350} {...mlResult} />
```

### Option C — Just the data, your own UI
```jsx
import { useExplainability } from './feature_8/frontend';

const { charts, meta, loading, error, loadCharts } = useExplainability({
  predictions: mlResult.predictions,
  features: mlResult.features,
  modelKey: mlResult.modelKey,
});

useEffect(() => { loadCharts(); }, []);

// charts.heatmap, charts.matrix, charts.waterfall are Plotly figure dicts
```

---

## 9. Complete File Reference

```
feature_8/
├── __init__.py                    # Package root — clean imports
├── main.py                        # FastAPI app (standalone or embedded)
├── demo.py                        # Run standalone without other features
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # pytest config
│
├── agent/
│   ├── __init__.py
│   ├── state_schema.py            # GraphState TypedDict — shared with ALL agents
│   ├── shap_engine.py             # SHAP computation — pure Python, no side effects
│   ├── chart_generators.py        # Plotly chart builders (heatmap, matrix, waterfall)
│   └── explainability_node.py     # LangGraph node — the entry point
│
├── api/
│   ├── __init__.py
│   └── routes.py                  # FastAPI router + model registry
│
├── frontend/
│   ├── index.js                   # Barrel export
│   ├── useExplainability.js       # React hook — fetch charts from API
│   ├── ExplainabilityDashboard.jsx # Full 3-tab dashboard component
│   └── ExplainabilityWidget.jsx   # Compact embeddable single-chart widget
│
├── mocks/
│   ├── __init__.py
│   └── mock_ml_node.py            # Simulates Feature 5 output for standalone dev/test
│
└── tests/
    ├── __init__.py
    └── test_explainability.py     # 10 pytest tests — covers node + all 3 charts
```

---

## 10. Environment Variables

Add these to your `.env` / `.env.local`:

```bash
# Backend
PYTHONPATH=.          # Run from project root

# Frontend (.env or .env.local in React root)
REACT_APP_API_URL=http://localhost:8000   # Change to prod URL when deploying
```

---

## 11. Running Tests

```bash
# From project root
pip install -r feature_8/requirements.txt
pytest feature_8/tests/ -v
```

All 10 tests should pass. If any fail, check that `xgboost` and `shap` are installed.

---

## 12. Final Integration Checklist (use before submitting)

- [ ] `feature_8/` folder is in project root (same level as other features)
- [ ] `requirements.txt` dependencies installed: `pip install -r feature_8/requirements.txt`
- [ ] Feature 5 writes `model`, `X_df`, `predictions` to graph state
- [ ] `register_model(key, model)` called by Feature 5 after training
- [ ] `graph.add_node("explainability", explainability_node)` in main graph
- [ ] `graph.add_edge("ml_prediction", "explainability")` in main graph
- [ ] `app.include_router(explainability_router)` in main FastAPI app
- [ ] CORS configured for React dev server origin
- [ ] `REACT_APP_API_URL` set in React `.env`
- [ ] `react-plotly.js` and `plotly.js-dist` in React `package.json`
- [ ] All 10 tests pass: `pytest feature_8/tests/ -v`
- [ ] Demo runs clean: `python -m feature_8.demo`

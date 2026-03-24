# Feature 8 — ML Explainability Visualization Agent

## Quick Start

```bash
pip install -r requirements.txt
```

## How to Integrate into Your LangGraph

```python
# main_graph.py  (in your root project, not Feature 8)
from langgraph.graph import StateGraph
from feature_8.agent.explainability_node import explainability_node
from feature_8.agent.state_schema import GraphState

# Build the graph
graph = StateGraph(GraphState)

# Add Feature 8 node
graph.add_node("explainability", explainability_node)

# Wire it: ML prediction node must run first
graph.add_edge("ml_prediction", "explainability")
graph.add_edge("explainability", "report_generator")  # or wherever next

app = graph.compile()
```

## What the ML Prediction Node Must Write to State

Your Feature 5 (ML prediction node) must write these keys to graph state:

```python
{
    "model":       trained_xgboost_or_sklearn_model,   # Any sklearn-compatible model
    "X_df":        pandas_dataframe_of_features,       # Same DF used for prediction
    "predictions": [                                    # One dict per child
        {"child_id": "C001", "risk_score": 72.3},
        {"child_id": "C002", "risk_score": 18.1},
        # ...
    ],
}
```

## How to Register Model for API Endpoints

```python
# In your ML prediction agent, after training:
from feature_8.api.routes import register_model
register_model("session_abc123", your_trained_model)
```

## React Integration

```jsx
import ExplainabilityDashboard from './feature_8/frontend/ExplainabilityDashboard';

// In your main app, after ML prediction completes:
<ExplainabilityDashboard
  predictions={mlResult.predictions}   // [{child_id, risk_score}]
  features={mlResult.featureRows}      // [{days_overdue: 45, vaccines_missed: 2, ...}]
  modelKey={mlResult.modelKey}         // e.g. "session_abc123"
  autoLoad={true}
/>
```

---

## Antigravity Prompts

### Prompt 1 — Initial Setup
```
I have a folder called feature_8/ with these files:
- agent/state_schema.py
- agent/shap_engine.py
- agent/chart_generators.py
- agent/explainability_node.py
- api/routes.py
- frontend/ExplainabilityDashboard.jsx
- requirements.txt

This is Feature 8 of a 10-feature LangGraph multi-agent system for child immunization risk prediction.

Please read all the files in feature_8/ and integrate the explainability_node into our main LangGraph graph in main_graph.py. The node should receive state from our ML prediction node (which writes `model`, `X_df`, and `predictions` to state) and write back `shap_heatmap_json`, `shap_matrix_json`, `shap_waterfall_json`, and `top_features`.

Do NOT modify any logic inside the feature_8/ files. Just wire the node into the graph.
```

### Prompt 2 — FastAPI Integration
```
Add the Feature 8 API router to our main FastAPI app in app.py:

from feature_8.api.routes import router as explainability_router
app.include_router(explainability_router)

Make sure CORS is enabled for our React frontend at http://localhost:3000.
```

### Prompt 3 — React Integration
```
In our main React app, import ExplainabilityDashboard from ./feature_8/frontend/ExplainabilityDashboard.

After the ML prediction result is available (stored in state as `predictionResult`), render the dashboard:

<ExplainabilityDashboard
  predictions={predictionResult.predictions}
  features={predictionResult.features}
  modelKey={predictionResult.modelKey}
  autoLoad={true}
/>

Install react-plotly.js and plotly.js-dist if not already installed.
```

### Prompt 4 — LangGraph state communication test
```
Write a test in tests/test_explainability.py that:
1. Creates a synthetic pandas DataFrame with columns: days_overdue, vaccines_missed, district_outbreak, reminders_ignored, high_risk_state, child_age_months, sibling_history, gender_male
2. Trains a quick XGBClassifier on it
3. Creates a mock GraphState with model, X_df, and predictions
4. Calls explainability_node(state)
5. Asserts that shap_heatmap_json, shap_matrix_json, shap_waterfall_json, and top_features are all present in the returned state
6. Asserts error is None
```

---

## Key Design Decisions

**Why Plotly JSON (not images)?**
Plotly figures are serialized as JSON and rendered interactively on the frontend. This means judges can hover, zoom, and explore — far more impressive than static PNG images.

**Why dynamic feature detection?**
`_find_column()` in chart_generators.py searches for column names case-insensitively. This means if another team member renames `days_overdue` to `DaysOverdue`, the matrix still works without any code changes.

**Why SHAPEngine auto-selects explainer?**
TreeExplainer is 100x faster than KernelExplainer for XGBoost/RF models. The fallback ensures Feature 8 works even if another team switches to a linear model.

**Why write raw shap_values_raw to state?**
Downstream agents (report generator, dashboard) can use raw SHAP values for their own purposes without re-running SHAP. This avoids duplicate computation.

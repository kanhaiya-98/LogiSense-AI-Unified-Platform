# Feature 8: ML Explainability Visualization Agent
## Complete Technical Blueprint — Hackathon Winner Strategy

---

## 1. WHAT THIS FEATURE DOES

**Feature 8 is a LangGraph Agent Node** that:
1. Receives ML predictions + raw feature data from other agents
2. Runs SHAP (SHapley Additive exPlanations) on the live model
3. Dynamically generates 3 visualizations per prediction batch:
   - **SHAP Feature Impact Heatmap** — per-child, per-feature SHAP values
   - **Risk Stratification Matrix** — 2D grid (Days Overdue × Vaccines Missed)
   - **SHAP Waterfall Chart** — single child deep-dive explainability
4. Serves results via FastAPI to the React frontend
5. Communicates results back to the LangGraph graph state

**Zero hardcoding. Every chart regenerates from live ML output.**

---

## 2. TECHNOLOGY STACK

| Layer | Technology | Why |
|-------|-----------|-----|
| ML Explainability | `shap` library | Industry standard, tree-native |
| ML Model | XGBoost / scikit-learn | Fast, SHAP TreeExplainer compatible |
| Agent Framework | LangGraph (Python) | Graph-based agent communication |
| Backend API | FastAPI + uvicorn | Async, fast, JSON + image serving |
| Visualization | Plotly (server-side JSON) | Interactive, no image files needed |
| Frontend | React + Recharts/D3 | Dynamic rendering of Plotly JSON |
| State Sharing | LangGraph `StateGraph` | Shared graph state between nodes |
| Data Format | JSON (SHAP values array) | Portable between agents |

---

## 3. FOLDER STRUCTURE

```
feature_8_explainability/
├── agent/
│   ├── __init__.py
│   ├── explainability_node.py     # LangGraph node — CORE
│   ├── shap_engine.py             # SHAP computation engine
│   ├── chart_generators.py        # Heatmap, Matrix, Waterfall builders
│   └── state_schema.py            # Shared LangGraph state type
├── api/
│   ├── __init__.py
│   └── routes.py                  # FastAPI routes
├── frontend/
│   └── ExplainabilityDashboard.jsx  # React component
├── tests/
│   └── test_explainability.py
├── requirements.txt
└── README.md
```

---

## 4. HOW IT INTEGRATES WITH OTHER AGENTS

```
[Feature 3: Data Ingestion Agent]
        ↓ raw_features (dict)
[Feature 5: ML Prediction Agent]  
        ↓ predictions (risk_scores, model, X_df)
[Feature 8: Explainability Agent]  ← THIS FEATURE
        ↓ shap_payload (heatmap_json, matrix_json, waterfall_json)
[Feature 9: Report Generator Agent]
[Feature 10: ASHA Worker Dashboard]
```

LangGraph State keys this node reads:
- `state["predictions"]` — list of {child_id, risk_score}
- `state["model"]` — trained XGBoost/sklearn model object
- `state["X_df"]` — pandas DataFrame of features used for prediction

LangGraph State keys this node writes:
- `state["shap_heatmap_json"]`
- `state["shap_matrix_json"]`  
- `state["shap_waterfall_json"]`
- `state["top_features"]`

---

## 5. WHAT MAKES THIS WIN THE HACKATHON

1. **Live explainability** — judges see the AI "thinking out loud" in real time
2. **No black box** — every prediction has a why, traceable to features
3. **3 chart types** — each explains a different angle of the same prediction
4. **Responsive to judge questions** — "What if this child had 4 vaccines missed?" → new matrix instantly
5. **Clinical framing** — charts use ASHA worker language, not ML jargon
6. **LangGraph integration** — shows real multi-agent architecture, not a demo

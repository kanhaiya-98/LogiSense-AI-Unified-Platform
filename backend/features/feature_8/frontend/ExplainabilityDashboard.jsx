/**
 * ExplainabilityDashboard.jsx
 * Feature 8 — ML Explainability Visualization
 *
 * Renders 3 dynamic Plotly charts from the explainability API.
 * Integrates with the main website via props: predictions, features, modelKey.
 * Zero hardcoded data — all charts come from live SHAP computation.
 *
 * Dependencies:
 *   npm install plotly.js-dist react-plotly.js
 */

import React, { useState, useEffect, useCallback } from "react";
import Plot from "react-plotly.js";

// ── Constants ────────────────────────────────────────────────────────────────

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const CHART_DESCRIPTIONS = {
  heatmap: {
    title: "SHAP Feature Impact Heatmap",
    subtitle:
      "Each column = one child sorted low→high risk. Each row = one feature. Red = increases risk. Blue = reduces risk.",
    icon: "🔥",
  },
  matrix: {
    title: "Risk Stratification Matrix",
    subtitle:
      "Average predicted risk score for every Days Overdue × Vaccines Missed segment. Use to triage which patient groups need immediate attention.",
    icon: "🧮",
  },
  waterfall: {
    title: "SHAP Waterfall — Individual Explanation",
    subtitle:
      "How each feature pushed this child's risk score up or down from the model baseline. Click any child in the heatmap to see their waterfall.",
    icon: "📊",
  },
};

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
  displaylogo: false,
  toImageButtonOptions: { format: "png", scale: 2 },
};

// ── Main Component ────────────────────────────────────────────────────────────

/**
 * @param {object}  props
 * @param {Array}   props.predictions    [{child_id, risk_score, ...}]
 * @param {Array}   props.features       Feature rows as array of objects
 * @param {string}  props.modelKey       Key to look up model in backend registry
 * @param {boolean} props.autoLoad       If true, load charts on mount
 */
export default function ExplainabilityDashboard({ predictions, features, modelKey, autoLoad = true }) {
  const [charts, setCharts] = useState({ heatmap: null, matrix: null, waterfall: null });
  const [meta, setMeta] = useState({ topFeatures: [], topDriver: "", childrenAnalyzed: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("heatmap");
  const [selectedChild, setSelectedChild] = useState(null);

  // ── Fetch all charts ──────────────────────────────────────────────────────

  const loadAllCharts = useCallback(async () => {
    if (!predictions?.length || !features?.length || !modelKey) return;

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/explainability/all`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          predictions,
          features,
          model_artifact_key: modelKey,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      setCharts({ heatmap: data.heatmap, matrix: data.matrix, waterfall: data.waterfall });
      setMeta({
        topFeatures: data.top_features || [],
        topDriver: data.top_driver || "",
        childrenAnalyzed: data.children_analyzed || 0,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [predictions, features, modelKey]);

  useEffect(() => {
    if (autoLoad) loadAllCharts();
  }, [autoLoad, loadAllCharts]);

  // ── Fetch waterfall for specific child ────────────────────────────────────

  const loadWaterfallForChild = useCallback(
    async (childIdx) => {
      setSelectedChild(childIdx);
      setActiveTab("waterfall");

      try {
        const res = await fetch(`${API_BASE}/api/explainability/waterfall`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            child_idx: childIdx,
            predictions,
            features,
            model_artifact_key: modelKey,
          }),
        });
        const data = await res.json();
        setCharts((prev) => ({ ...prev, waterfall: data.figure }));
      } catch (err) {
        setError(`Waterfall failed: ${err.message}`);
      }
    },
    [predictions, features, modelKey]
  );

  // ── Heatmap click handler — drill into a child ───────────────────────────

  const handleHeatmapClick = useCallback(
    (event) => {
      const pointIndex = event.points?.[0]?.pointIndex;
      if (pointIndex !== undefined) {
        const childIdx = Array.isArray(pointIndex) ? pointIndex[1] : pointIndex;
        loadWaterfallForChild(childIdx);
      }
    },
    [loadWaterfallForChild]
  );

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="explainability-dashboard">
      <style>{STYLES}</style>

      {/* Header */}
      <div className="expl-header">
        <div className="expl-header-left">
          <h2 className="expl-title">
            <span className="expl-title-icon">🧠</span>
            ML Explainability
          </h2>
          <p className="expl-subtitle">
            Why did the model flag these children? Every prediction explained.
          </p>
        </div>

        <div className="expl-meta-badges">
          {meta.childrenAnalyzed > 0 && (
            <>
              <MetaBadge label="Children Analyzed" value={meta.childrenAnalyzed} />
              <MetaBadge label="Features Used" value={meta.topFeatures.length} />
              {meta.topDriver && <MetaBadge label="Top Driver" value={meta.topDriver} highlight />}
            </>
          )}
        </div>

        <button className="expl-refresh-btn" onClick={loadAllCharts} disabled={loading}>
          {loading ? <Spinner /> : "↻ Regenerate"}
        </button>
      </div>

      {/* Algorithm badge */}
      <div className="expl-algo-strip">
        <AlgoBadge label="ALGORITHM" value="XGBoost + SHAP TreeExplainer" />
        <AlgoBadge label="EXPLAINABILITY" value="Shapley Additive Explanations" />
        <AlgoBadge label="DECISION" value="Traceable to individual features" />
        <div className="expl-algo-note">
          🔍 Not a black box — every prediction is fully traceable
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="expl-error">
          <span>⚠ {error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="expl-loading">
          <div className="expl-loading-bar" />
          <p>Running SHAP analysis on {predictions?.length || 0} records…</p>
        </div>
      )}

      {/* Tabs */}
      {!loading && (charts.heatmap || charts.matrix || charts.waterfall) && (
        <>
          <div className="expl-tabs">
            {["heatmap", "matrix", "waterfall"].map((tab) => (
              <button
                key={tab}
                className={`expl-tab ${activeTab === tab ? "active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {CHART_DESCRIPTIONS[tab].icon} {CHART_DESCRIPTIONS[tab].title}
                {tab === "waterfall" && selectedChild !== null && (
                  <span className="expl-tab-badge">Child {selectedChild}</span>
                )}
              </button>
            ))}
          </div>

          {/* Chart description */}
          <p className="expl-chart-desc">{CHART_DESCRIPTIONS[activeTab].subtitle}</p>

          {/* Chart area */}
          <div className="expl-chart-area">
            {activeTab === "heatmap" && charts.heatmap && (
              <PlotlyChart
                figure={charts.heatmap}
                onClick={handleHeatmapClick}
                hint="💡 Click any column to drill into that child's explanation"
              />
            )}
            {activeTab === "matrix" && charts.matrix && (
              <PlotlyChart
                figure={charts.matrix}
                hint="💡 Hover any cell to see the exact average risk score for that segment"
              />
            )}
            {activeTab === "waterfall" && charts.waterfall && (
              <PlotlyChart
                figure={charts.waterfall}
                hint="💡 Red bars increase risk · Blue bars decrease risk · Dashed line = final prediction"
              />
            )}
          </div>

          {/* Top features sidebar */}
          {meta.topFeatures.length > 0 && (
            <div className="expl-features-strip">
              <span className="expl-features-label">Top drivers (by mean |SHAP|):</span>
              {meta.topFeatures.map((f, i) => (
                <span key={f} className="expl-feature-tag" style={{ opacity: 1 - i * 0.08 }}>
                  #{i + 1} {f}
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!loading && !charts.heatmap && !error && (
        <div className="expl-empty">
          <p>Run an ML prediction to generate explainability charts.</p>
          <button className="expl-refresh-btn" onClick={loadAllCharts}>
            Generate Now
          </button>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PlotlyChart({ figure, onClick, hint }) {
  return (
    <div className="expl-plot-wrapper">
      {hint && <div className="expl-hint">{hint}</div>}
      <Plot
        data={figure.data}
        layout={{
          ...figure.layout,
          autosize: true,
        }}
        config={PLOTLY_CONFIG}
        onClick={onClick}
        style={{ width: "100%", minHeight: 400 }}
        useResizeHandler
      />
    </div>
  );
}

function MetaBadge({ label, value, highlight }) {
  return (
    <div className={`expl-meta-badge ${highlight ? "highlight" : ""}`}>
      <span className="expl-meta-label">{label}</span>
      <span className="expl-meta-value">{value}</span>
    </div>
  );
}

function AlgoBadge({ label, value }) {
  return (
    <div className="expl-algo-badge">
      <span className="expl-algo-label">{label}</span>
      <span className="expl-algo-value">{value}</span>
    </div>
  );
}

function Spinner() {
  return <span className="expl-spinner" />;
}

// ── CSS ───────────────────────────────────────────────────────────────────────

const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

  .explainability-dashboard {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 24px;
    font-family: 'IBM Plex Sans', sans-serif;
    color: #e6edf3;
    max-width: 100%;
  }

  .expl-header {
    display: flex;
    align-items: flex-start;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }

  .expl-header-left { flex: 1; min-width: 200px; }

  .expl-title {
    font-size: 1.4rem;
    font-weight: 600;
    margin: 0 0 4px;
    color: #f0f6fc;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .expl-title-icon { font-size: 1.2rem; }

  .expl-subtitle {
    font-size: 0.82rem;
    color: #8b949e;
    margin: 0;
  }

  .expl-meta-badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .expl-meta-badge {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 80px;
  }

  .expl-meta-badge.highlight {
    border-color: #f59e0b;
    background: #1a1500;
  }

  .expl-meta-label {
    font-size: 0.68rem;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .expl-meta-value {
    font-size: 0.88rem;
    font-weight: 600;
    color: #e6edf3;
    font-family: 'IBM Plex Mono', monospace;
    white-space: nowrap;
  }

  .expl-refresh-btn {
    background: #21262d;
    border: 1px solid #30363d;
    color: #e6edf3;
    border-radius: 6px;
    padding: 8px 16px;
    cursor: pointer;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: background 0.15s;
    white-space: nowrap;
  }

  .expl-refresh-btn:hover { background: #30363d; }
  .expl-refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .expl-algo-strip {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    background: #0a0f14;
    border: 1px solid #1a6b3c33;
    border-radius: 8px;
    padding: 10px 16px;
    margin-bottom: 20px;
  }

  .expl-algo-badge {
    display: flex;
    gap: 6px;
    align-items: center;
    padding-right: 12px;
    border-right: 1px solid #21262d;
  }

  .expl-algo-badge:last-of-type { border-right: none; }

  .expl-algo-label {
    font-size: 0.68rem;
    font-family: 'IBM Plex Mono', monospace;
    color: #6e7681;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .expl-algo-value {
    font-size: 0.78rem;
    font-family: 'IBM Plex Mono', monospace;
    color: #4caf50;
    font-weight: 500;
  }

  .expl-algo-note {
    margin-left: auto;
    font-size: 0.75rem;
    color: #f59e0b;
    font-family: 'IBM Plex Mono', monospace;
  }

  .expl-error {
    background: #1a0a0a;
    border: 1px solid #ef4444;
    border-radius: 6px;
    padding: 10px 16px;
    color: #ef4444;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .expl-error button {
    background: none;
    border: none;
    color: #ef4444;
    cursor: pointer;
    font-size: 1rem;
  }

  .expl-loading {
    text-align: center;
    padding: 40px;
    color: #8b949e;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
  }

  .expl-loading-bar {
    height: 3px;
    background: linear-gradient(90deg, #1a6b3c, #4caf50, #f59e0b, #ef4444);
    border-radius: 2px;
    margin-bottom: 16px;
    animation: loadingBar 1.5s ease-in-out infinite;
    background-size: 200% 100%;
  }

  @keyframes loadingBar {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  .expl-tabs {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid #21262d;
    margin-bottom: 12px;
    overflow-x: auto;
  }

  .expl-tab {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #8b949e;
    cursor: pointer;
    padding: 10px 16px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.85rem;
    white-space: nowrap;
    transition: all 0.15s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .expl-tab:hover { color: #e6edf3; }

  .expl-tab.active {
    color: #4caf50;
    border-bottom-color: #4caf50;
  }

  .expl-tab-badge {
    background: #4caf5022;
    color: #4caf50;
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 0.72rem;
    font-family: 'IBM Plex Mono', monospace;
  }

  .expl-chart-desc {
    font-size: 0.8rem;
    color: #8b949e;
    margin: 0 0 12px;
    padding: 8px 12px;
    background: #161b22;
    border-radius: 6px;
    border-left: 3px solid #4caf50;
  }

  .expl-chart-area {
    border: 1px solid #21262d;
    border-radius: 8px;
    overflow: hidden;
    background: #0d1117;
  }

  .expl-plot-wrapper { position: relative; }

  .expl-hint {
    position: absolute;
    top: 8px;
    right: 48px;
    font-size: 0.72rem;
    color: #6e7681;
    font-family: 'IBM Plex Mono', monospace;
    z-index: 10;
    pointer-events: none;
  }

  .expl-features-strip {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
    margin-top: 12px;
    padding: 10px 12px;
    background: #0a0f14;
    border-radius: 6px;
    border: 1px solid #21262d;
  }

  .expl-features-label {
    font-size: 0.75rem;
    color: #6e7681;
    font-family: 'IBM Plex Mono', monospace;
    white-space: nowrap;
  }

  .expl-feature-tag {
    font-size: 0.75rem;
    font-family: 'IBM Plex Mono', monospace;
    color: #4caf50;
    background: #1a6b3c22;
    border: 1px solid #1a6b3c55;
    border-radius: 4px;
    padding: 2px 8px;
    white-space: nowrap;
  }

  .expl-empty {
    text-align: center;
    padding: 60px 20px;
    color: #6e7681;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
  }

  .expl-empty .expl-refresh-btn {
    margin: 16px auto 0;
    justify-content: center;
  }

  .expl-spinner {
    display: inline-block;
    width: 14px;
    height: 14px;
    border: 2px solid #4caf5044;
    border-top-color: #4caf50;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
`;

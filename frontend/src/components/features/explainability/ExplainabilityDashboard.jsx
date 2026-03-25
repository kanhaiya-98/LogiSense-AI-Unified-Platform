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

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const CHART_DESCRIPTIONS = {
  heatmap: {
    title: "SHAP Feature Impact Heatmap",
    subtitle:
      "Each column = one shipment sorted low→high risk. Each row = one feature. Red = increases risk. Blue = reduces risk.",
    icon: "🔥",
  },
  matrix: {
    title: "Risk Stratification Matrix",
    subtitle:
      "Average predicted risk score for every ETA Delay × Carrier Reliability segment. Use to triage which shipment groups need immediate attention.",
    icon: "🧮",
  },
  waterfall: {
    title: "SHAP Waterfall — Individual Explanation",
    subtitle:
      "How each feature pushed this shipment's risk score up or down from the model baseline. Click any shipment in the heatmap to see their waterfall.",
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
 * @param {Array}   props.predictions    [{shipment_id, risk_score, ...}]
 * @param {Array}   props.features       Feature rows as array of objects
 * @param {string}  props.modelKey       Key to look up model in backend registry
 * @param {boolean} props.autoLoad       If true, load charts on mount
 */
export default function ExplainabilityDashboard({ predictions, features, modelKey, autoLoad = true, onRegenerate }) {
  const [charts, setCharts] = useState({ heatmap: null, matrix: null, waterfall: null });
  const [meta, setMeta] = useState({ topFeatures: [], topDriver: "", shipmentsAnalyzed: 0 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("heatmap");
  const [selectedShipment, setSelectedShipment] = useState(null);

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
        shipmentsAnalyzed: data.shipments_analyzed || 0,
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

  // ── Fetch waterfall for specific shipment ────────────────────────────────────

  const loadWaterfallForShipment = useCallback(
    async (shipmentIdx) => {
      setSelectedShipment(shipmentIdx);
      setActiveTab("waterfall");

      try {
        const res = await fetch(`${API_BASE}/api/explainability/waterfall`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            shipment_idx: shipmentIdx,
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

  // ── Heatmap click handler — drill into a shipment ───────────────────────────

  const handleHeatmapClick = useCallback(
    (event) => {
      const pointIndex = event.points?.[0]?.pointIndex;
      if (pointIndex !== undefined) {
        const shipmentIdx = Array.isArray(pointIndex) ? pointIndex[1] : pointIndex;
        loadWaterfallForShipment(shipmentIdx);
      }
    },
    [loadWaterfallForShipment]
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
            Why did the model flag these shipments? Every prediction explained.
          </p>
        </div>

        <div className="expl-meta-badges">
          {meta.shipmentsAnalyzed > 0 && (
            <>
              <MetaBadge label="Shipments Analyzed" value={meta.shipmentsAnalyzed} />
              <MetaBadge label="Features Used" value={meta.topFeatures.length} />
              {meta.topDriver && <MetaBadge label="Top Driver" value={meta.topDriver} highlight />}
            </>
          )}
        </div>

        <button className="expl-refresh-btn" onClick={() => {
          setLoading(true);
          if (onRegenerate) {
            onRegenerate();
          } else {
            loadAllCharts();
          }
        }} disabled={loading}>
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
                {tab === "waterfall" && selectedShipment !== null && (
                  <span className="expl-tab-badge">
                    {predictions?.[selectedShipment]?.shipment_id || `Shipment ${selectedShipment}`}
                  </span>
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
                hint="💡 Click any column to drill into that shipment's explanation"
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
    background: #ffffff;
    border: 1px solid #f1f5f9;
    box-shadow: 0 8px 30px rgba(0,0,0,0.04);
    border-radius: 12px;
    padding: 24px;
    font-family: 'IBM Plex Sans', sans-serif;
    color: #1e293b;
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
    font-weight: 700;
    margin: 0 0 4px;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .expl-title-icon { font-size: 1.2rem; }

  .expl-subtitle {
    font-size: 0.85rem;
    color: #64748b;
    margin: 0;
  }

  .expl-meta-badges {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .expl-meta-badge {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 6px 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-width: 80px;
  }

  .expl-meta-badge.highlight {
    border-color: #f59e0b;
    background: #fffbeb;
  }

  .expl-meta-label {
    font-size: 0.68rem;
    color: #64748b;
    font-family: 'IBM Plex Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .expl-meta-value {
    font-size: 0.88rem;
    font-weight: 600;
    color: #0f172a;
    font-family: 'IBM Plex Mono', monospace;
    white-space: nowrap;
  }

  .expl-refresh-btn {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    color: #0f172a;
    border-radius: 6px;
    padding: 8px 16px;
    cursor: pointer;
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    font-size: 0.82rem;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
    white-space: nowrap;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
  }

  .expl-refresh-btn:hover { background: #f8fafc; border-color: #cbd5e1; }
  .expl-refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .expl-algo-strip {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 10px 16px;
    margin-bottom: 20px;
  }

  .expl-algo-badge {
    display: flex;
    gap: 6px;
    align-items: center;
    padding-right: 12px;
    border-right: 1px solid #dcfce7;
  }

  .expl-algo-badge:last-of-type { border-right: none; }

  .expl-algo-label {
    font-size: 0.68rem;
    font-family: 'IBM Plex Mono', monospace;
    color: #166534;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .expl-algo-value {
    font-size: 0.78rem;
    font-family: 'IBM Plex Mono', monospace;
    color: #15803d;
    font-weight: 600;
  }

  .expl-algo-note {
    margin-left: auto;
    font-size: 0.75rem;
    color: #b45309;
    font-family: 'IBM Plex Mono', monospace;
  }

  .expl-error {
    background: #fef2f2;
    border: 1px solid #fca5a5;
    border-radius: 6px;
    padding: 10px 16px;
    color: #b91c1c;
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
    color: #b91c1c;
    cursor: pointer;
    font-size: 1rem;
  }

  .expl-loading {
    text-align: center;
    padding: 40px;
    color: #64748b;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.82rem;
  }

  .expl-loading-bar {
    height: 4px;
    background: linear-gradient(90deg, #10b981, #3b82f6, #8b5cf6, #ec4899);
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
    border-bottom: 1px solid #e2e8f0;
    margin-bottom: 12px;
    overflow-x: auto;
  }

  .expl-tab {
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #64748b;
    cursor: pointer;
    padding: 10px 16px;
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.85rem;
    font-weight: 500;
    white-space: nowrap;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .expl-tab:hover { color: #0f172a; }

  .expl-tab.active {
    color: #8b5cf6;
    border-bottom-color: #8b5cf6;
  }

  .expl-tab-badge {
    background: #f3e8ff;
    color: #7e22ce;
    border-radius: 10px;
    padding: 1px 7px;
    font-size: 0.72rem;
    font-family: 'IBM Plex Mono', monospace;
  }

  .expl-chart-desc {
    font-size: 0.8rem;
    color: #475569;
    margin: 0 0 12px;
    padding: 8px 12px;
    background: #f1f5f9;
    border-radius: 6px;
    border-left: 3px solid #8b5cf6;
  }

  .expl-chart-area {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    overflow: hidden;
    background: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
  }

  .expl-plot-wrapper { position: relative; }

  .expl-hint {
    position: absolute;
    top: 8px;
    right: 48px;
    font-size: 0.72rem;
    color: #94a3b8;
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
    background: #f8fafc;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
  }

  .expl-features-label {
    font-size: 0.75rem;
    color: #475569;
    font-family: 'IBM Plex Mono', monospace;
    white-space: nowrap;
  }

  .expl-feature-tag {
    font-size: 0.75rem;
    font-family: 'IBM Plex Mono', monospace;
    color: #15803d;
    background: #dcfce7;
    border: 1px solid #bbf7d0;
    border-radius: 4px;
    padding: 2px 8px;
    white-space: nowrap;
    font-weight: 500;
  }

  .expl-empty {
    text-align: center;
    padding: 60px 20px;
    color: #64748b;
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
    border: 2px solid #e2e8f0;
    border-top-color: #0f172a;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
`;

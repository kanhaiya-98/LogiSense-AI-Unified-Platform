/**
 * WaterfallChart.jsx
 * Feature 8 — SHAP Waterfall Chart Component
 *
 * Shows how each feature pushed a single child's risk score
 * up or down from the model baseline.
 *
 * Props:
 *   predictions     [{child_id, risk_score}]   — from ML prediction agent
 *   features        [{days_overdue, ...}]       — feature rows, one per child
 *   modelKey        string                      — model registry key from backend
 *   childIdx        number                      — which child to explain (default = highest risk)
 *   height          number                      — chart height in px (default 400)
 */

import React, { useEffect, useState, useCallback } from "react";
import Plot from "react-plotly.js";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ["select2d", "lasso2d"],
  displaylogo: false,
  toImageButtonOptions: { format: "png", scale: 2, filename: "shap_waterfall" },
};

export default function WaterfallChart({
  predictions = [],
  features = [],
  modelKey = "",
  childIdx = null,   // null = auto-select highest risk child
  height = 400,
}) {
  const [figure, setFigure] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeChild, setActiveChild] = useState(childIdx);

  // Auto-select highest risk child when childIdx is not provided
  const resolvedIdx = activeChild ?? (
    predictions.length
      ? predictions.indexOf(predictions.reduce((a, b) => a.risk_score > b.risk_score ? a : b))
      : 0
  );

  const fetchWaterfall = useCallback(async (idx) => {
    if (!predictions.length || !features.length || !modelKey) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/explainability/waterfall`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          child_idx: idx,
          predictions,
          features,
          model_artifact_key: modelKey,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setFigure(data.figure);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [predictions, features, modelKey]);

  useEffect(() => {
    fetchWaterfall(resolvedIdx);
  }, [resolvedIdx, fetchWaterfall]);

  // Allow parent to change childIdx dynamically
  useEffect(() => {
    if (childIdx !== null && childIdx !== activeChild) {
      setActiveChild(childIdx);
    }
  }, [childIdx]); // eslint-disable-line

  const currentChild = predictions[resolvedIdx];
  const riskScore = currentChild?.risk_score ?? 0;
  const riskColor = riskScore >= 70 ? "#ef4444" : riskScore >= 50 ? "#f59e0b" : "#4caf50";

  if (loading) return <LoadingBar message={`Explaining child ${resolvedIdx}…`} />;
  if (error)   return <ErrorBox message={error} onRetry={() => fetchWaterfall(resolvedIdx)} />;
  if (!figure) return <EmptyBox message="Run ML prediction to generate waterfall." />;

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <div>
          <h3 style={styles.title}>SHAP Waterfall — Individual Explanation</h3>
          <p style={styles.subtitle}>
            How each feature built up the risk score from the model baseline.
            Red bars increase risk · Blue bars decrease risk.
          </p>
        </div>
        <div style={styles.scoreBadge}>
          <span style={styles.scoreLabel}>Risk Score</span>
          <span style={{ ...styles.scoreValue, color: riskColor }}>{riskScore.toFixed(1)}</span>
          <span style={{ ...styles.scoreLabel, color: riskColor }}>
            {riskScore >= 70 ? "CRITICAL" : riskScore >= 50 ? "HIGH" : riskScore >= 25 ? "MEDIUM" : "LOW"}
          </span>
        </div>
      </div>

      {/* Child selector */}
      {predictions.length > 1 && (
        <div style={styles.selectorBar}>
          <span style={styles.selectorLabel}>View child:</span>
          <select
            style={styles.selector}
            value={resolvedIdx}
            onChange={(e) => setActiveChild(Number(e.target.value))}
          >
            {predictions.map((p, i) => (
              <option key={i} value={i}>
                {p.child_id} — score {p.risk_score.toFixed(1)}
              </option>
            ))}
          </select>
        </div>
      )}

      <Plot
        data={figure.data}
        layout={{ ...figure.layout, autosize: true, height }}
        config={PLOTLY_CONFIG}
        style={{ width: "100%" }}
        useResizeHandler
      />
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function LoadingBar({ message }) {
  return (
    <div style={styles.stateBox}>
      <div style={styles.loadingTrack}><div style={styles.loadingFill} /></div>
      <p style={styles.stateText}>{message}</p>
      <style>{`@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(400%)}}`}</style>
    </div>
  );
}

function ErrorBox({ message, onRetry }) {
  return (
    <div style={{ ...styles.stateBox, border: "1px solid #ef4444" }}>
      <p style={{ ...styles.stateText, color: "#ef4444" }}>⚠ {message}</p>
      <button style={styles.retryBtn} onClick={onRetry}>Retry</button>
    </div>
  );
}

function EmptyBox({ message }) {
  return (
    <div style={styles.stateBox}>
      <p style={styles.stateText}>{message}</p>
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────

const styles = {
  wrapper: {
    background: "#0d1117",
    border: "1px solid #21262d",
    borderRadius: 10,
    overflow: "hidden",
    fontFamily: "'IBM Plex Sans', sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    padding: "16px 20px 8px",
    borderBottom: "1px solid #21262d",
    gap: 16,
  },
  title: {
    margin: 0,
    fontSize: 15,
    fontWeight: 600,
    color: "#f0f6fc",
    fontFamily: "'IBM Plex Mono', monospace",
  },
  subtitle: {
    margin: "4px 0 0",
    fontSize: 12,
    color: "#8b949e",
  },
  scoreBadge: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    background: "#161b22",
    border: "1px solid #30363d",
    borderRadius: 8,
    padding: "8px 16px",
    flexShrink: 0,
  },
  scoreLabel: {
    fontSize: 10,
    color: "#6e7681",
    fontFamily: "'IBM Plex Mono', monospace",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
  },
  scoreValue: {
    fontSize: 22,
    fontWeight: 700,
    fontFamily: "'IBM Plex Mono', monospace",
    lineHeight: 1.2,
  },
  selectorBar: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "8px 20px",
    background: "#0a0f14",
    borderBottom: "1px solid #21262d",
  },
  selectorLabel: {
    fontSize: 12,
    color: "#6e7681",
    fontFamily: "'IBM Plex Mono', monospace",
    whiteSpace: "nowrap",
  },
  selector: {
    background: "#161b22",
    border: "1px solid #30363d",
    color: "#e6edf3",
    borderRadius: 6,
    padding: "4px 10px",
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 12,
    cursor: "pointer",
    flex: 1,
    maxWidth: 320,
  },
  retryBtn: {
    background: "#21262d",
    border: "1px solid #30363d",
    color: "#e6edf3",
    borderRadius: 6,
    padding: "6px 14px",
    cursor: "pointer",
    fontSize: 13,
  },
  stateBox: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    minHeight: 200,
    gap: 12,
    background: "#0d1117",
    border: "1px solid #21262d",
    borderRadius: 10,
    padding: 24,
  },
  stateText: {
    margin: 0,
    fontSize: 13,
    color: "#6e7681",
    fontFamily: "'IBM Plex Mono', monospace",
    textAlign: "center",
  },
  loadingTrack: {
    width: 200,
    height: 3,
    background: "#21262d",
    borderRadius: 2,
    overflow: "hidden",
  },
  loadingFill: {
    height: "100%",
    width: "40%",
    background: "linear-gradient(90deg, #1a6b3c, #4caf50)",
    borderRadius: 2,
    animation: "slide 1.2s ease-in-out infinite",
  },
};

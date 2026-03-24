/**
 * SHAPHeatmap.jsx
 * Feature 8 — SHAP Feature Impact Heatmap Component
 *
 * Standalone component. Can be used independently or via ExplainabilityDashboard.
 *
 * Props:
 *   predictions     [{child_id, risk_score}]   — from ML prediction agent
 *   features        [{days_overdue, ...}]       — feature rows, one per child
 *   modelKey        string                      — model registry key from backend
 *   height          number                      — chart height in px (default 480)
 *   onChildClick    function(childIdx)          — called when a column is clicked
 */

import React, { useEffect, useState, useCallback } from "react";
import Plot from "react-plotly.js";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ["select2d", "lasso2d"],
  displaylogo: false,
  toImageButtonOptions: { format: "png", scale: 2, filename: "shap_heatmap" },
};

export default function SHAPHeatmap({
  predictions = [],
  features = [],
  modelKey = "",
  height = 480,
  onChildClick = null,
}) {
  const [figure, setFigure] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchHeatmap = useCallback(async () => {
    if (!predictions.length || !features.length || !modelKey) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/explainability/heatmap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
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
    fetchHeatmap();
  }, [fetchHeatmap]);

  const handleClick = useCallback(
    (event) => {
      if (!onChildClick) return;
      const point = event.points?.[0];
      if (point) {
        const idx = Array.isArray(point.pointIndex) ? point.pointIndex[1] : point.pointIndex;
        onChildClick(idx);
      }
    },
    [onChildClick]
  );

  if (loading) return <LoadingBar message={`Computing SHAP heatmap for ${predictions.length} children…`} />;
  if (error)   return <ErrorBox message={error} onRetry={fetchHeatmap} />;
  if (!figure) return <EmptyBox message="Run ML prediction to generate heatmap." />;

  return (
    <div style={styles.wrapper}>
      <ChartHeader
        title="SHAP Feature Impact Heatmap"
        subtitle="Each column = one child (low → high risk). Each row = one feature. Red = increases risk · Blue = reduces risk."
        onRefresh={fetchHeatmap}
      />
      <div style={styles.hint}>
        {onChildClick ? "💡 Click any column to see that child's detailed waterfall explanation" : ""}
      </div>
      <Plot
        data={figure.data}
        layout={{ ...figure.layout, autosize: true, height }}
        config={PLOTLY_CONFIG}
        onClick={handleClick}
        style={{ width: "100%" }}
        useResizeHandler
      />
    </div>
  );
}

// ── Shared sub-components ────────────────────────────────────────────────────

function ChartHeader({ title, subtitle, onRefresh }) {
  return (
    <div style={styles.header}>
      <div>
        <h3 style={styles.title}>{title}</h3>
        <p style={styles.subtitle}>{subtitle}</p>
      </div>
      <button style={styles.refreshBtn} onClick={onRefresh} title="Regenerate">
        ↻
      </button>
    </div>
  );
}

function LoadingBar({ message }) {
  return (
    <div style={styles.stateBox}>
      <div style={styles.loadingTrack}>
        <div style={styles.loadingFill} />
      </div>
      <p style={styles.stateText}>{message}</p>
      <style>{`
        @keyframes slide { 0%{transform:translateX(-100%)} 100%{transform:translateX(400%)} }
      `}</style>
    </div>
  );
}

function ErrorBox({ message, onRetry }) {
  return (
    <div style={{ ...styles.stateBox, border: "1px solid #ef4444" }}>
      <p style={{ ...styles.stateText, color: "#ef4444" }}>⚠ {message}</p>
      <button style={styles.refreshBtn} onClick={onRetry}>Retry</button>
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
  hint: {
    padding: "6px 20px",
    fontSize: 11,
    color: "#6e7681",
    fontFamily: "'IBM Plex Mono', monospace",
    background: "#0a0f14",
  },
  refreshBtn: {
    background: "#21262d",
    border: "1px solid #30363d",
    color: "#e6edf3",
    borderRadius: 6,
    padding: "6px 12px",
    cursor: "pointer",
    fontSize: 14,
    flexShrink: 0,
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

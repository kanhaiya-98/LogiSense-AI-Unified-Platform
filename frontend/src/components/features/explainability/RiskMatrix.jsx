/**
 * RiskMatrix.jsx
 * Feature 8 — Risk Stratification Matrix Component
 *
 * Standalone component. Shows average predicted risk score
 * for every ETA Delay × Carrier Reliability segment.
 *
 * Props:
 *   predictions     [{shipment_id, risk_score}]   — from ML prediction agent
 *   features        [{days_overdue, ...}]       — feature rows, one per shipment
 *   modelKey        string                      — model registry key from backend
 *   height          number                      — chart height in px (default 400)
 */

import React, { useEffect, useState, useCallback } from "react";
import Plot from "react-plotly.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ["select2d", "lasso2d"],
  displaylogo: false,
  toImageButtonOptions: { format: "png", scale: 2, filename: "risk_matrix" },
};

export default function RiskMatrix({
  predictions = [],
  features = [],
  modelKey = "",
  height = 400,
}) {
  const [figure, setFigure] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchMatrix = useCallback(async () => {
    if (!predictions.length || !features.length || !modelKey) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/explainability/matrix`, {
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
    fetchMatrix();
  }, [fetchMatrix]);

  if (loading) return <LoadingBar message="Building risk stratification matrix…" />;
  if (error)   return <ErrorBox message={error} onRetry={fetchMatrix} />;
  if (!figure) return <EmptyBox message="Run ML prediction to generate risk matrix." />;

  return (
    <div style={styles.wrapper}>
      <ChartHeader
        title="Risk Stratification Matrix"
        subtitle="Average predicted risk score (0–100) per ETA Delay × Carrier Reliability segment. Hover any cell for details."
        onRefresh={fetchMatrix}
      />
      <div style={styles.legend}>
        <LegendItem color="#1a6b3c" label="LOW &lt;25" />
        <LegendItem color="#f59e0b" label="MED 25–69" />
        <LegendItem color="#ef4444" label="HIGH 70+" />
        <span style={styles.escalation}>⚡ &gt;70 = immediate ASHA escalation</span>
      </div>
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

function ChartHeader({ title, subtitle, onRefresh }) {
  return (
    <div style={styles.header}>
      <div>
        <h3 style={styles.title}>{title}</h3>
        <p style={styles.subtitle}>{subtitle}</p>
      </div>
      <button style={styles.refreshBtn} onClick={onRefresh} title="Regenerate">↻</button>
    </div>
  );
}

function LegendItem({ color, label }) {
  return (
    <span style={styles.legendItem}>
      <span style={{ ...styles.legendDot, background: color }} />
      {label}
    </span>
  );
}

function LoadingBar({ message }) {
  return (
    <div style={styles.stateBox}>
      <div style={styles.loadingTrack}>
        <div style={styles.loadingFill} />
      </div>
      <p style={styles.stateText}>{message}</p>
      <style>{`@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(400%)}}`}</style>
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
  legend: {
    display: "flex",
    gap: 16,
    alignItems: "center",
    padding: "8px 20px",
    background: "#0a0f14",
    borderBottom: "1px solid #21262d",
    flexWrap: "wrap",
  },
  legendItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 11,
    color: "#8b949e",
    fontFamily: "'IBM Plex Mono', monospace",
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 2,
    flexShrink: 0,
  },
  escalation: {
    marginLeft: "auto",
    fontSize: 11,
    color: "#f59e0b",
    fontFamily: "'IBM Plex Mono', monospace",
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

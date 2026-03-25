/**
 * ExplainabilityWidget.jsx — Compact embeddable version of Feature 8.
 *
 * Use this in OTHER features' pages when you want to show
 * a single chart inline (not the full 3-tab dashboard).
 *
 * Usage examples:
 *
 *   // In Feature 6 (ASHA dashboard): show matrix only
 *   <ExplainabilityWidget
 *     chartType="matrix"
 *     predictions={predictions}
 *     features={features}
 *     modelKey={modelKey}
 *   />
 *
 *   // In Feature 9 (report page): show waterfall for a specific shipment
 *   <ExplainabilityWidget
 *     chartType="waterfall"
 *     shipmentIdx={3}
 *     predictions={predictions}
 *     features={features}
 *     modelKey={modelKey}
 *   />
 */

import React, { useEffect } from "react";
import Plot from "react-plotly.js";
import { useExplainability } from "./useExplainability";

const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: false,
  displaylogo: false,
};

/**
 * @param {"heatmap"|"matrix"|"waterfall"} chartType
 * @param {number}  [shipmentIdx]    Only used when chartType="waterfall"
 * @param {number}  [height=320]
 * @param {Array}   predictions
 * @param {Array}   features
 * @param {string}  modelKey
 */
export default function ExplainabilityWidget({
  chartType = "matrix",
  shipmentIdx = 0,
  height = 320,
  predictions,
  features,
  modelKey,
}) {
  const { charts, loading, error, loadCharts, loadWaterfallForShipment } =
    useExplainability({ predictions, features, modelKey });

  useEffect(() => {
    if (chartType === "waterfall") {
      loadWaterfallForShipment(shipmentIdx);
    } else {
      loadCharts();
    }
  }, [chartType, shipmentIdx]); // eslint-disable-line

  const figure = charts[chartType];

  if (loading) {
    return (
      <div style={styles.skeleton}>
        <div style={styles.pulse} />
        <span style={styles.loadingText}>Computing SHAP values…</span>
      </div>
    );
  }

  if (error) {
    return <div style={styles.error}>⚠ {error}</div>;
  }

  if (!figure) {
    return (
      <div style={styles.skeleton}>
        <span style={styles.loadingText}>Awaiting ML prediction…</span>
      </div>
    );
  }

  return (
    <div style={styles.wrapper}>
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

const styles = {
  wrapper: {
    background: "#0d1117",
    borderRadius: 8,
    border: "1px solid #21262d",
    overflow: "hidden",
  },
  skeleton: {
    background: "#0d1117",
    border: "1px solid #21262d",
    borderRadius: 8,
    height: 200,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
  },
  pulse: {
    width: 120,
    height: 4,
    borderRadius: 2,
    background: "linear-gradient(90deg, #1a6b3c, #4caf50, #1a6b3c)",
    backgroundSize: "200% 100%",
    animation: "pulse 1.4s ease-in-out infinite",
  },
  loadingText: {
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 12,
    color: "#6e7681",
  },
  error: {
    background: "#1a0a0a",
    border: "1px solid #ef4444",
    borderRadius: 8,
    padding: "12px 16px",
    color: "#ef4444",
    fontFamily: "'IBM Plex Mono', monospace",
    fontSize: 13,
  },
};

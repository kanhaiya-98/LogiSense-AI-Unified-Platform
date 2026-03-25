/**
 * useExplainability.js — Custom React hook for Feature 8.
 *
 * Use this hook in ANY page or component across the website
 * to fetch and display explainability charts after an ML prediction runs.
 *
 * Usage:
 *   import { useExplainability } from '../feature_8/frontend/useExplainability';
 *
 *   const { charts, meta, loading, error, loadCharts, loadWaterfallForShipment } =
 *     useExplainability({ predictions, features, modelKey });
 */

import { useState, useCallback, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * @param {object} config
 * @param {Array}  config.predictions   [{shipment_id, risk_score}]
 * @param {Array}  config.features      Feature rows as array of plain objects
 * @param {string} config.modelKey      Model registry key from ML prediction agent
 */
export function useExplainability({ predictions, features, modelKey }) {
  const [charts, setCharts] = useState({
    heatmap: null,
    matrix: null,
    waterfall: null,
  });
  const [meta, setMeta] = useState({
    topFeatures: [],
    topDriver: "",
    shipmentsAnalyzed: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Prevent duplicate in-flight requests
  const inFlight = useRef(false);

  const loadCharts = useCallback(async () => {
    if (!predictions?.length || !features?.length || !modelKey) {
      setError("Missing predictions, features, or modelKey.");
      return;
    }
    if (inFlight.current) return;
    inFlight.current = true;
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
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setCharts({
        heatmap: data.heatmap,
        matrix: data.matrix,
        waterfall: data.waterfall,
      });
      setMeta({
        topFeatures: data.top_features || [],
        topDriver: data.top_driver || "",
        shipmentsAnalyzed: data.shipments_analyzed || 0,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      inFlight.current = false;
    }
  }, [predictions, features, modelKey]);

  const loadWaterfallForShipment = useCallback(
    async (shipmentIdx) => {
      if (!predictions?.length || !features?.length || !modelKey) return;
      setLoading(true);
      setError(null);
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
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setCharts((prev) => ({ ...prev, waterfall: data.figure }));
      } catch (err) {
        setError(`Waterfall failed: ${err.message}`);
      } finally {
        setLoading(false);
      }
    },
    [predictions, features, modelKey]
  );

  const reset = useCallback(() => {
    setCharts({ heatmap: null, matrix: null, waterfall: null });
    setMeta({ topFeatures: [], topDriver: "", shipmentsAnalyzed: 0 });
    setError(null);
  }, []);

  return { charts, meta, loading, error, loadCharts, loadWaterfallForShipment, reset };
}

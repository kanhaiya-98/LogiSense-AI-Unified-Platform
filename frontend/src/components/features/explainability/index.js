/**
 * feature_8/frontend/index.js
 * Barrel export — import Feature 8 UI from one place.
 *
 * Usage in other features:
 *   import { SHAPHeatmap, RiskMatrix, WaterfallChart } from '../feature_8/frontend';
 *   import { ExplainabilityDashboard }                 from '../feature_8/frontend';
 *   import { useExplainability }                       from '../feature_8/frontend';
 */

// Individual chart components (standalone, Antigravity-friendly)
export { default as SHAPHeatmap }             from "./SHAPHeatmap";
export { default as RiskMatrix }              from "./RiskMatrix";
export { default as WaterfallChart }          from "./WaterfallChart";

// Full dashboard (all 3 charts in one tabbed component)
export { default as ExplainabilityDashboard } from "./ExplainabilityDashboard";

// Compact embeddable widget (for other features' pages)
export { default as ExplainabilityWidget }    from "./ExplainabilityWidget";

// React hook (fetch charts without any UI)
export { useExplainability }                  from "./useExplainability";

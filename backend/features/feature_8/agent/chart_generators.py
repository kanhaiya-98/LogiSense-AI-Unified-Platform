from __future__ import annotations
"""
chart_generators.py — Builds Plotly JSON for all 3 visualization types.
All charts are generated dynamically from SHAP engine output.
Zero hardcoded data — every chart reflects the live ML prediction.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Any

from feature_8.agent.shap_engine import SHAPEngine


# ── Shared dark theme ──────────────────────────────────────────────────────

DARK_THEME = dict(
    paper_bgcolor="#0d1117",
    plot_bgcolor="#0d1117",
    font=dict(family="'IBM Plex Mono', monospace", color="#e6edf3", size=11),
    margin=dict(l=120, r=40, t=60, b=60),
)

HEATMAP_COLORSCALE = [
    [0.0,  "#1a4a8a"],   # deep blue  — strongly reduces risk
    [0.25, "#4a90d9"],   # mid blue
    [0.5,  "#1c2433"],   # near black — neutral
    [0.75, "#d95f4a"],   # mid red
    [1.0,  "#8b1a1a"],   # deep red   — strongly increases risk
]

MATRIX_COLORSCALE = [
    [0.0,  "#1a6b3c"],   # dark green — very low risk
    [0.35, "#4caf50"],   # green
    [0.55, "#f59e0b"],   # amber
    [0.75, "#ef4444"],   # red
    [1.0,  "#7f1d1d"],   # dark red — critical
]


def build_heatmap(engine: SHAPEngine, predictions: list[dict]) -> dict:
    """
    SHAP Feature Impact Heatmap.
    Rows = features (sorted by mean |SHAP|)
    Cols = children (sorted low → high risk score)
    Color = SHAP value (red = increases risk, blue = decreases risk)
    """
    top_features = engine.get_top_features(k=10)
    shap_df = engine.get_shap_df()[top_features]

    # Sort shipments by risk score ascending
    risk_scores = [p["risk_score"] for p in predictions]
    sort_idx = np.argsort(risk_scores)
    shap_matrix = shap_df.iloc[sort_idx][top_features].T.values  # shape: (features, shipments)

    shipment_ids = [str(predictions[i].get("shipment_id", i)) for i in sort_idx]
    sorted_scores = [risk_scores[i] for i in sort_idx]

    # Risk score bar above heatmap
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.08, 0.92],
        vertical_spacing=0.01,
        shared_xaxes=True,
    )

    # Row 1: Risk score gradient bar
    fig.add_trace(
        go.Heatmap(
            z=[sorted_scores],
            x=shipment_ids,
            colorscale=[[0, "#1a6b3c"], [0.5, "#f59e0b"], [1, "#7f1d1d"]],
            showscale=False,
            hovertemplate="Shipment %{x}<br>Risk Score: %{z:.1f}<extra></extra>",
        ),
        row=1, col=1,
    )

    # Row 2: SHAP heatmap
    # Normalize per-feature for visual clarity
    abs_max = np.abs(shap_matrix).max(axis=1, keepdims=True)
    abs_max[abs_max == 0] = 1
    normalized = shap_matrix / abs_max

    hover_text = []
    for fi, feat in enumerate(top_features):
        row_text = []
        for ci, shipment in enumerate(shipment_ids):
            sv = shap_matrix[fi, ci]
            fv = engine.X_df.iloc[sort_idx[ci]][feat]
            direction = "▲ increases risk" if sv > 0 else "▼ reduces risk"
            row_text.append(
                f"<b>{feat}</b><br>"
                f"Shipment: {shipment}<br>"
                f"Feature value: {fv:.2f}<br>"
                f"SHAP: {sv:+.3f}<br>"
                f"{direction}"
            )
        hover_text.append(row_text)

    fig.add_trace(
        go.Heatmap(
            z=normalized,
            x=shipment_ids,
            y=top_features,
            colorscale=HEATMAP_COLORSCALE,
            zmid=0,
            zmin=-1,
            zmax=1,
            showscale=True,
            colorbar=dict(
                title=dict(text="SHAP Impact", font=dict(color="#e6edf3")),
                tickvals=[-1, -0.5, 0, 0.5, 1],
                ticktext=["Reduces Risk", "", "Neutral", "", "Increases Risk"],
                tickfont=dict(color="#e6edf3", size=10),
                outlinewidth=0,
                bgcolor="#0d1117",
            ),
            text=hover_text,
            hovertemplate="%{text}<extra></extra>",
        ),
        row=2, col=1,
    )

    fig.update_layout(
        title=dict(
            text="SHAP Feature Impact Heatmap",
            font=dict(size=16, color="#e6edf3"),
            x=0.02,
        ),
        **DARK_THEME,
        height=480,
        xaxis=dict(showticklabels=False, showgrid=False),
        xaxis2=dict(
            title="Shipments (sorted: low → high risk)",
            color="#8b949e",
            showgrid=False,
            tickfont=dict(size=8),
        ),
        yaxis=dict(showgrid=False, color="#8b949e"),
        yaxis2=dict(showgrid=False, color="#8b949e", autorange="reversed"),
    )

    return fig.to_dict()


def build_risk_matrix(engine: SHAPEngine, X_df: pd.DataFrame, predictions: list[dict]) -> dict:
    """
    Risk Stratification Matrix.
    Rows = ETA Delay minutes
    Cols = Carrier Reliability buckets
    Cell = Average predicted risk score for that segment
    """
    df = X_df.copy()
    df["risk_score"] = [p["risk_score"] for p in predictions]

    # Find columns dynamically
    days_col = _find_column(df, ["eta_delay_minutes", "eta_delay", "delay"])
    vacc_col = _find_column(df, ["carrier_reliability", "reliability", "carrier score"])

    if days_col is None or vacc_col is None:
        # Fallback: use top 2 most important features
        top2 = engine.get_top_features(k=2)
        days_col, vacc_col = top2[0], top2[1]

    # ETA delay buckets
    day_bins = [0, 15, 30, 60, 120, float("inf")]
    day_labels = ["0–15 min", "16–30 min", "31–60 min", "61–120 min", "120+ min"]
    df["days_bucket"] = pd.cut(df[days_col], bins=day_bins, labels=day_labels, right=True)

    # Carrier reliability buckets (50-100)
    vacc_bins = [0, 60, 75, 90, 100]
    vacc_labels = ["<60", "60-75", "76-90", "90-100"]
    df["vacc_bucket"] = pd.cut(df[vacc_col], bins=vacc_bins, labels=vacc_labels, right=True)

    pivot = df.groupby(["days_bucket", "vacc_bucket"], observed=True)["risk_score"].mean().unstack(fill_value=np.nan)

    z_values = pivot.values
    x_labels = [f"Rel: {v}" for v in pivot.columns.tolist()]
    y_labels = pivot.index.tolist()

    # Text annotations inside cells
    cell_text = []
    cell_category = []
    for row in z_values:
        rt = []
        rc = []
        for val in row:
            if np.isnan(val):
                rt.append("N/A")
                rc.append("NO DATA")
            elif val < 25:
                rt.append(f"{val:.0f}<br><span style='font-size:9px'>LOW RISK</span>")
                rc.append("LOW RISK")
            elif val < 50:
                rt.append(f"{val:.0f}<br><span style='font-size:9px'>MED RISK</span>")
                rc.append("MED RISK")
            elif val < 70:
                rt.append(f"{val:.0f}<br><span style='font-size:9px'>HIGH RISK</span>")
                rc.append("HIGH RISK")
            else:
                rt.append(f"{val:.0f}<br><span style='font-size:9px'>CRITICAL</span>")
                rc.append("CRITICAL")
        cell_text.append(rt)
        cell_category.append(rc)

    fig = go.Figure(
        go.Heatmap(
            z=z_values,
            x=x_labels,
            y=[str(y) for y in y_labels],
            colorscale=MATRIX_COLORSCALE,
            zmin=0,
            zmax=100,
            text=cell_text,
            texttemplate="%{text}",
            textfont=dict(size=13, color="white", family="'IBM Plex Mono', monospace"),
            showscale=True,
            colorbar=dict(
                title=dict(text="Risk Score (0–100)", font=dict(color="#e6edf3")),
                tickvals=[0, 25, 50, 70, 100],
                ticktext=["0 — Safe", "25 — Low", "50 — Medium", "70 — High", "100 — Critical"],
                tickfont=dict(color="#e6edf3", size=10),
                outlinewidth=0,
                bgcolor="#0d1117",
            ),
            hovertemplate=(
                f"<b>{days_col}</b>: %{{y}}<br>"
                f"<b>{vacc_col}</b>: %{{x}}<br>"
                "<b>Avg Risk Score</b>: %{z:.1f}<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title=dict(
            text=f"Risk Stratification Matrix<br>"
                 f"<sup style='color:#8b949e'>{days_col} × {vacc_col} — Average predicted risk score (0–100)</sup>",
            font=dict(size=15, color="#e6edf3"),
            x=0.02,
        ),
        **DARK_THEME,
        height=420,
        xaxis=dict(
            title=f"← {vacc_col} →",
            color="#8b949e",
            side="top",
            showgrid=False,
        ),
        yaxis=dict(
            title=f"← {days_col} →",
            color="#8b949e",
            autorange="reversed",
            showgrid=False,
        ),
        annotations=[
            dict(
                text=">70 = High risk of Cascade Propagation",
                x=0.5, y=-0.12,
                xref="paper", yref="paper",
                showarrow=False,
                font=dict(size=10, color="#f59e0b"),
            )
        ],
    )

    return fig.to_dict()


def build_waterfall(engine: SHAPEngine, shipment_idx: int, predictions: list[dict]) -> dict:
    """
    SHAP Waterfall Chart for a single shipment.
    Shows how each feature pushed the prediction up or down from the baseline.
    """
    data = engine.get_waterfall_data(shipment_idx)
    shipment_id = predictions[shipment_idx].get("shipment_id", shipment_idx)
    final_score = predictions[shipment_idx]["risk_score"]

    features = data["features"]
    shap_vals = data["shap_values"]
    feat_vals = data["feature_values"]
    base = data["expected_value"]

    # Build waterfall bars: start from base, add each SHAP value
    cumulative = [base]
    for sv in shap_vals[:-1]:
        cumulative.append(cumulative[-1] + sv)

    colors = ["#ef4444" if sv > 0 else "#3b82f6" for sv in shap_vals]

    hover_texts = [
        f"<b>{feat}</b><br>"
        f"Feature value: {fv:.2f}<br>"
        f"SHAP contribution: {sv:+.3f}<br>"
        f"{'▲ pushed risk UP' if sv > 0 else '▼ pushed risk DOWN'}"
        for feat, fv, sv in zip(features, feat_vals, shap_vals)
    ]

    fig = go.Figure()

    # Baseline
    fig.add_trace(go.Bar(
        name="Baseline (E[f(x)])",
        x=["Baseline"],
        y=[base],
        marker_color="#4a5568",
        text=[f"{base:.1f}"],
        textposition="outside",
        textfont=dict(color="#e6edf3"),
        hovertemplate=f"Model baseline: {base:.2f}<extra></extra>",
    ))

    # Feature contribution bars
    for i, (feat, sv, fv, cum, color, ht) in enumerate(
        zip(features, shap_vals, feat_vals, cumulative, colors, hover_texts)
    ):
        short_feat = feat[:20] + "…" if len(feat) > 20 else feat
        fig.add_trace(go.Bar(
            name=f"{short_feat} = {fv:.1f}",
            x=[f"{short_feat}\n({fv:.1f})"],
            y=[abs(sv)],
            base=[cum],
            marker_color=color,
            marker_opacity=0.85,
            text=[f"{sv:+.2f}"],
            textposition="outside",
            textfont=dict(color=color, size=10),
            hovertext=ht,
            hovertemplate="%{hovertext}<extra></extra>",
        ))

    # Final prediction line
    fig.add_hline(
        y=final_score,
        line_dash="dash",
        line_color="#f59e0b",
        line_width=2,
        annotation_text=f"Final prediction: {final_score:.1f}",
        annotation_font_color="#f59e0b",
    )

    fig.update_layout(
        title=dict(
            text=f"SHAP Waterfall — Shipment {shipment_id}<br>"
                 f"<sup style='color:#8b949e'>How each feature built up the risk score from baseline {base:.1f} → {final_score:.1f}</sup>",
            font=dict(size=15, color="#e6edf3"),
            x=0.02,
        ),
        **DARK_THEME,
        barmode="overlay",
        showlegend=False,
        height=420,
        xaxis=dict(color="#8b949e", showgrid=False),
        yaxis=dict(
            title="Risk Score",
            color="#8b949e",
            range=[0, max(100, final_score + 10)],
            gridcolor="#21262d",
        ),
    )

    return fig.to_dict()


# ── Utility ─────────────────────────────────────────────────────────────────

def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Case-insensitive column lookup from a list of candidate names."""
    lower_cols = {c.lower().replace(" ", "_"): c for c in df.columns}
    for name in candidates:
        key = name.lower().replace(" ", "_")
        if key in lower_cols:
            return lower_cols[key]
    return None

from __future__ import annotations
"""
Zen Platform — Unified Gemini LLM Service
All LLM interactions across ZenDec, ZenRTO, and ZenETA go through here.
Model: gemini-2.5-flash-lite (default) | gemini-2.5-flash (complex reasoning)
"""
import os
import json
import httpx
import asyncio
from typing import List, Dict, Any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _gemini_url(model: str = "gemini-2.5-flash-lite") -> str:
    return f"{GEMINI_BASE}/{model}:generateContent?key={GEMINI_API_KEY}"


def _call_gemini_sync(prompt: str, model: str = "gemini-2.5-flash-lite", max_tokens: int = 512) -> str:
    """Synchronous Gemini call (for use in sync contexts like ZenRTO)."""
    if not GEMINI_API_KEY or GEMINI_API_KEY in ("your_gemini_api_key", ""):
        return "Gemini API key not configured. Set GEMINI_API_KEY in backend/.env"
    try:
        url = _gemini_url(model)
        response = httpx.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
            },
            timeout=15.0,
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"Gemini unavailable: {e}"


async def _call_gemini_async(prompt: str, model: str = "gemini-2.5-flash-lite", max_tokens: int = 512) -> str:
    """Async Gemini call (for use in FastAPI async contexts)."""
    if not GEMINI_API_KEY or GEMINI_API_KEY in ("your_gemini_api_key", ""):
        return "Gemini API key not configured. Set GEMINI_API_KEY in backend/.env"
    try:
        url = _gemini_url(model)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3},
                },
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"Gemini unavailable: {e}"


# ── ZenDec (F6 Decision Engine) ──────────────────────────────────────────────

async def run_stress_test(pareto_options: List[Dict], incident_context: Dict) -> Dict:
    """Stress-test Pareto carrier options across 3 scenarios using Gemini."""
    prompt = f"""You are a logistics risk analyst. Evaluate carrier options against stress scenarios.
Respond ONLY with valid JSON. No markdown, no explanation outside JSON.

Incident context:
{json.dumps(incident_context, indent=2)}

Pareto options to stress-test:
{json.dumps(pareto_options, indent=2)}

For each option, test these 3 scenarios:
1. PEAK_DEMAND: 40% capacity reduction on chosen route
2. WEATHER_DELAY: 6-hour weather disruption at origin
3. PRICE_SPIKE: 25% cost increase mid-transit

Respond with this exact JSON structure:
{{
  "stress_results": [
    {{
      "carrier_id": "...",
      "carrier_name": "...",
      "scenarios": {{
        "PEAK_DEMAND": {{"pass": true, "impact": "brief description"}},
        "WEATHER_DELAY": {{"pass": true, "impact": "brief description"}},
        "PRICE_SPIKE": {{"pass": true, "impact": "brief description"}}
      }},
      "stress_score": 0.0,
      "viability_summary": "one sentence"
    }}
  ]
}}"""
    try:
        raw = await _call_gemini_async(prompt, max_tokens=800)
        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        data = json.loads(raw)
        for item in data.get("stress_results", []):
            passes = sum(1 for s in item["scenarios"].values() if s.get("pass"))
            item["stress_score"] = round(passes / 3, 4)
        return data
    except Exception as e:
        return {
            "stress_results": [
                {
                    "carrier_id": o.get("carrier_id", ""),
                    "carrier_name": o.get("carrier_name", ""),
                    "scenarios": {
                        "PEAK_DEMAND": {"pass": True, "impact": "LLM unavailable"},
                        "WEATHER_DELAY": {"pass": True, "impact": "LLM unavailable"},
                        "PRICE_SPIKE": {"pass": True, "impact": "LLM unavailable"},
                    },
                    "stress_score": 0.67,
                    "viability_summary": f"Gemini stress test failed: {e}",
                }
                for o in pareto_options
            ]
        }


async def detect_ood(incident_context: Dict, historical_summary: str) -> Dict:
    """Detect if current incident is Out-of-Distribution (novel pattern)."""
    prompt = f"""You are a logistics anomaly detector. Compare current incident against historical patterns.
Respond ONLY with valid JSON.

Historical pattern summary:
{historical_summary}

Current incident:
{json.dumps(incident_context, indent=2)}

Is this incident out-of-distribution (novel/unusual)?
Respond with:
{{
  "ood_flag": true,
  "confidence_adjustment": -10.0,
  "ood_score": 0.0,
  "reason": "brief explanation"
}}"""
    try:
        raw = await _call_gemini_async(prompt, max_tokens=300)
        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        return json.loads(raw)
    except Exception:
        return {"ood_flag": False, "confidence_adjustment": 0.0, "ood_score": 0.0, "reason": "OOD check unavailable"}


async def generate_counterfactuals(chosen_option: Dict, rejected_options: List[Dict], incident_context: Dict) -> str:
    """SHAP-style counterfactual explanation for Tier 3 escalations."""
    prompt = f"""You are an explainable-AI logistics assistant. Be concise and precise.

Incident: {json.dumps(incident_context, indent=2)}
Recommended option: {json.dumps(chosen_option, indent=2)}
Rejected options: {json.dumps(rejected_options, indent=2)}

In 3-4 sentences, explain:
1. Why this option was recommended (key factors).
2. What would have to change for a different option to be chosen (counterfactual).
Keep it factual and data-driven."""
    try:
        return await _call_gemini_async(prompt, max_tokens=300)
    except Exception as e:
        return f"Counterfactual generation failed: {e}"


async def get_demand_insights(decision_data: Dict) -> str:
    """Generate supply chain insights for ZenDec decision output."""
    prompt = f"""You are a supply chain analyst. Analyze this carrier decision data and provide 3 key actionable insights in 2-3 sentences total:
{json.dumps(decision_data, indent=2)}
Be concise, data-driven, and mention specific carriers or metrics."""
    return await _call_gemini_async(prompt, max_tokens=256)


# ── ZenRTO (F12 RTO Risk Scoring) ────────────────────────────────────────────

def get_route_explanation(
    order_id: str,
    rto_score: float,
    risk_level: str,
    top_factors: list,
    order_value: float,
    buyer_order_count: int,
) -> str:
    """Generate RTO risk explanation (sync, compatible with ZenRTO pipeline)."""
    factors_text = "\n".join([
        f"- {f.get('display_name', f.get('feature', ''))}: "
        f"{'↑' if f.get('direction') == 'INCREASES_RISK' else '↓'} "
        f"(SHAP: {f.get('shap_value', 0):.3f})"
        for f in top_factors
    ])
    prompt = f"""You are a logistics risk analyst. Explain this RTO risk assessment in 2-3 sentences for an operations manager.

Order: {order_id}
RTO Score: {rto_score:.1%} (risk: {risk_level})
Order Value: ₹{order_value:,.0f}
Buyer History: {buyer_order_count} previous orders

Top risk factors:
{factors_text}

Be concise, specific, and actionable. No markdown."""
    return _call_gemini_sync(prompt, max_tokens=150)


# ── ZenETA (F7 ETA Prediction) ────────────────────────────────────────────────

async def get_eta_context(eta_data: Dict) -> str:
    """Summarize ETA prediction results and highlight delay risks."""
    prompt = f"""You are a logistics operations analyst. Summarize this ETA prediction in 2-3 sentences and call out any delay risks:
{json.dumps(eta_data, indent=2)}
Focus on SLA breach probability, confidence intervals, and any weather or operational risks. Be specific."""
    return await _call_gemini_async(prompt, max_tokens=200)

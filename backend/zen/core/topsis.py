from __future__ import annotations
"""
F6: TOPSIS-based Multi-Objective Pareto Decision Engine
Copied from zendec/backend/core/topsis.py
"""
import numpy as np
from typing import List, Dict
from dataclasses import dataclass, field


@dataclass
class CarrierOption:
    carrier_id: str
    carrier_name: str
    route: str
    vehicle_type: str
    cost_inr: float
    cost_delta: float
    eta_hours: float
    eta_delta: float
    co2_kg: float
    co2_delta: float
    sla_breach_prob: float
    red_team_viability: float
    distance_km: float
    weight_tonnes: float
    historical_breach_rate: float = 0.0
    stress_score: float = 0.8


POLICY_WEIGHTS: Dict[str, Dict[str, float]] = {
    "BALANCED":    {"cost": 0.33, "speed": 0.33, "carbon": 0.34},
    "COST_FIRST":  {"cost": 0.60, "speed": 0.25, "carbon": 0.15},
    "SPEED_FIRST": {"cost": 0.20, "speed": 0.65, "carbon": 0.15},
    "CARBON_FIRST":{"cost": 0.20, "speed": 0.20, "carbon": 0.60},
}


def _resolve_weights(policy: str, aqi_value: float) -> Dict[str, float]:
    base = POLICY_WEIGHTS.get(policy, POLICY_WEIGHTS["BALANCED"]).copy()
    if aqi_value > 300:
        return {"cost": 0.15, "speed": 0.15, "carbon": 0.70}
    elif 200 <= aqi_value <= 300:
        base["carbon"] = base["carbon"] + 0.3
        total = sum(base.values())
        base = {k: v / total for k, v in base.items()}
    return base


class TOPSISEngine:
    def __init__(self, policy: str = "BALANCED", aqi_value: float = 0.0):
        self.policy = policy
        self.aqi_value = aqi_value
        self.weights = _resolve_weights(policy, aqi_value)

    def run(self, options: List[CarrierOption]) -> List[Dict]:
        if len(options) < 3:
            raise ValueError(f"Need ≥3 carrier options, got {len(options)}")

        matrix = np.array(
            [[o.cost_delta, o.eta_delta, o.co2_delta] for o in options], dtype=float,
        )
        col_norms = np.sqrt((matrix ** 2).sum(axis=0))
        col_norms[col_norms == 0] = 1.0
        norm = matrix / col_norms
        w = np.array([self.weights["cost"], self.weights["speed"], self.weights["carbon"]])
        weighted = norm * w
        ideal_best  = weighted.min(axis=0)
        ideal_worst = weighted.max(axis=0)
        d_best  = np.sqrt(((weighted - ideal_best)  ** 2).sum(axis=1))
        d_worst = np.sqrt(((weighted - ideal_worst) ** 2).sum(axis=1))
        closeness = d_worst / (d_best + d_worst + 1e-10)

        pareto_ids = self._diverse_three(options, closeness)
        results = []
        labels = ["Recommended", "Cost Optimised", "Carbon Optimised"]
        for rank, idx in enumerate(pareto_ids):
            o = options[idx]
            results.append({
                "rank": rank + 1, "label": labels[rank],
                "carrier_id": o.carrier_id, "carrier_name": o.carrier_name,
                "route": o.route, "vehicle_type": o.vehicle_type,
                "cost_delta": round(o.cost_delta, 2), "eta_delta": round(o.eta_delta, 2),
                "co2_delta": round(o.co2_delta, 3), "cost_inr": round(o.cost_inr, 2),
                "eta_hours": round(o.eta_hours, 2), "co2_kg": round(o.co2_kg, 3),
                "sla_breach_prob": round(o.sla_breach_prob, 4),
                "topsis_score": round(float(closeness[idx]), 6),
                "stress_score": round(o.stress_score, 4),
                "is_recommended": rank == 0,
                "policy": self.policy, "aqi_value": self.aqi_value,
                "weights_used": self.weights,
            })
        return results

    def _diverse_three(self, options, closeness) -> List[int]:
        ranked = list(np.argsort(closeness)[::-1])
        best_overall = ranked[0]
        best_cost    = int(np.argmin([o.cost_delta for o in options]))
        best_carbon  = int(np.argmin([o.co2_delta  for o in options]))
        seen = []
        for candidate in [best_overall, best_cost, best_carbon] + ranked:
            if candidate not in seen:
                seen.append(candidate)
            if len(seen) == 3:
                break
        return seen[:3]

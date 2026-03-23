from __future__ import annotations
"""F6: 3-Tier Autonomy Engine — copied from zendec"""
from dataclasses import dataclass
from enum import Enum


class AutonomyTier(str, Enum):
    AUTO_EXECUTE  = "TIER_1_AUTO"
    PARETO_CARD   = "TIER_2_SUPERVISED"
    FULL_ESCALATE = "TIER_3_ESCALATE"


@dataclass
class AutonomyDecision:
    tier: AutonomyTier
    reason: str
    confidence: float
    blast_radius: int
    stress_score: float
    ood_flag: bool
    recommended_action: str


class PolicyEngine:
    CONF_AUTO_MIN = 85.0
    CONF_SUPERVISED_MIN = 65.0
    BLAST_AUTO_MAX = 5
    BLAST_SUPERVISED_MAX = 50
    STRESS_AUTO_MIN = 0.80

    def evaluate(self, blast_radius: int, confidence: float, stress_score: float, ood_flag: bool, known_pattern: bool = True) -> AutonomyDecision:
        if blast_radius > self.BLAST_SUPERVISED_MAX or confidence < self.CONF_SUPERVISED_MIN or not known_pattern or ood_flag or stress_score < 0.50:
            reasons = []
            if blast_radius > self.BLAST_SUPERVISED_MAX: reasons.append(f"blast_radius={blast_radius}")
            if confidence < self.CONF_SUPERVISED_MIN: reasons.append(f"confidence={confidence:.1f}")
            if not known_pattern: reasons.append("novel pattern")
            if ood_flag: reasons.append("OOD flag")
            if stress_score < 0.50: reasons.append(f"stress={stress_score:.2f}")
            return AutonomyDecision(tier=AutonomyTier.FULL_ESCALATE, reason="Escalation: " + "; ".join(reasons), confidence=confidence, blast_radius=blast_radius, stress_score=stress_score, ood_flag=ood_flag, recommended_action="Present SHAP + counterfactuals to supervisor.")

        if blast_radius <= self.BLAST_AUTO_MAX and confidence >= self.CONF_AUTO_MIN and stress_score >= self.STRESS_AUTO_MIN and not ood_flag:
            return AutonomyDecision(tier=AutonomyTier.AUTO_EXECUTE, reason="Low blast radius, high confidence, stress-test passed, no OOD.", confidence=confidence, blast_radius=blast_radius, stress_score=stress_score, ood_flag=ood_flag, recommended_action="Execute automatically. Log decision.")

        return AutonomyDecision(tier=AutonomyTier.PARETO_CARD, reason=f"Supervised: {blast_radius} shipments, confidence {confidence:.1f}%.", confidence=confidence, blast_radius=blast_radius, stress_score=stress_score, ood_flag=ood_flag, recommended_action="Generate Pareto Menu and deliver HITL approval card.")

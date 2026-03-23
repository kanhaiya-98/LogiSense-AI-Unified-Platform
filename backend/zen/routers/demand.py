from __future__ import annotations
"""
Zen Platform — ZenDec Router (F6 Decision Engine)
Carrier optimization via TOPSIS, AQI enrichment, HITL, E-Way Bill
"""
import os
import uuid
import datetime
import asyncio
from typing import List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

# Import core TOPSIS/decision engine
from zen.core.topsis import TOPSISEngine, CarrierOption
from zen.core.carbon import enrich_options_with_carbon
from zen.core.autonomy import PolicyEngine, AutonomyTier
from zen.core.policy_store import get_current_policy, set_policy, get_aqi_override
from zen.services.aqi_service import get_aqi
from zen.services import gemini_service
from zen.services.hitl_service import create_approval_card, resolve_card, get_pending_cards, get_card
from zen.services.ewaybill_service import generate_ewaybill, update_vehicle_part_b, cancel_ewaybill, get_ewaybill
from zen.db.supabase import get_supabase, save_demand_decision

router = APIRouter()
autonomy_engine = PolicyEngine()


class CarrierInput(BaseModel):
    carrier_id: str
    carrier_name: str
    route: str
    vehicle_type: str
    cost_inr: float
    cost_delta: float = 0.0
    eta_hours: float
    eta_delta: float = 0.0
    sla_breach_prob: float = 0.05
    red_team_viability: float = 0.80
    distance_km: float
    weight_tonnes: float
    historical_breach_rate: float = 0.0


class DecisionRequest(BaseModel):
    incident_id: Optional[str] = None
    blast_radius: int = Field(..., ge=1)
    confidence: float = Field(..., ge=0, le=100)
    carriers: List[CarrierInput] = Field(..., min_length=3)
    city: str = Field("delhi")
    historical_summary: str = Field("")
    known_pattern: bool = True


class PolicyUpdateRequest(BaseModel):
    policy: str
    changed_by: str = "operator"


class HITLResolveRequest(BaseModel):
    action: str
    selected_option_rank: int = 1
    operator_notes: str = ""


class EWayBillRequest(BaseModel):
    shipment_id: str
    supply_type: str = "O"
    doc_no: str
    doc_date: Optional[str] = None
    from_gstin: Optional[str] = None
    from_trade_name: str = ""
    from_addr1: str = ""
    from_place: str = ""
    from_state: str = "07"
    from_pincode: str = "110001"
    to_gstin: str
    to_trade_name: str = ""
    to_addr1: str = ""
    to_place: str = ""
    to_state: str = "27"
    to_pincode: str = "400001"
    product_name: str = "Goods"
    hsn_code: str = ""
    quantity: float = 1.0
    unit: str = "NOS"
    taxable_value: float = 0.0
    cgst: float = 0.0
    sgst: float = 0.0
    igst: float = 0.0
    igst_rate: float = 18.0
    transport_mode: str = "1"
    transport_id: str = ""
    vehicle_no: str = ""
    distance_km: float = 100.0


class VehicleUpdateRequest(BaseModel):
    ewb_no: str
    new_vehicle_no: str
    reason: str = "Due to Break Down"
    trigger_event: str = "routing_agent_reassignment"


@router.post("/run")
async def run_decision(req: DecisionRequest, bg: BackgroundTasks):
    """
    Full ZenDec pipeline:
    1. Fetch live AQI
    2. Compute carbon for each option
    3. Run TOPSIS → 3 Pareto options
    4. Evaluate autonomy tier
    5. Run Gemini stress test + OOD detection
    6. If Tier 2 → create HITL card
    7. Return decision with Gemini insights
    """
    incident_id = req.incident_id or str(uuid.uuid4())

    aqi_data = await get_aqi(req.city)
    aqi_value = aqi_data["aqi"]
    policy = get_current_policy()

    options = [
        CarrierOption(
            carrier_id=c.carrier_id,
            carrier_name=c.carrier_name,
            route=c.route,
            vehicle_type=c.vehicle_type,
            cost_inr=c.cost_inr,
            cost_delta=c.cost_delta,
            eta_hours=c.eta_hours,
            eta_delta=c.eta_delta,
            co2_kg=0.0,
            co2_delta=0.0,
            sla_breach_prob=c.sla_breach_prob,
            red_team_viability=c.red_team_viability,
            distance_km=c.distance_km,
            weight_tonnes=c.weight_tonnes,
            historical_breach_rate=c.historical_breach_rate,
        )
        for c in req.carriers
    ]
    enrich_options_with_carbon(options)

    topsis = TOPSISEngine(policy=policy, aqi_value=aqi_value)
    pareto_options = topsis.run(options)

    incident_ctx = {
        "incident_id": incident_id,
        "blast_radius": req.blast_radius,
        "confidence": req.confidence,
        "city": req.city,
        "aqi": aqi_value,
        "policy": policy,
    }

    stress_data, ood_data = await asyncio.gather(
        gemini_service.run_stress_test(pareto_options, incident_ctx),
        gemini_service.detect_ood(incident_ctx, req.historical_summary),
    )

    avg_stress = sum(
        r.get("stress_score", 0.67)
        for r in stress_data.get("stress_results", [])
    ) / max(len(stress_data.get("stress_results", [1])), 1)

    final_confidence = req.confidence + ood_data.get("confidence_adjustment", 0)
    final_confidence = max(0, min(100, final_confidence))

    autonomy = autonomy_engine.evaluate(
        blast_radius=req.blast_radius,
        confidence=final_confidence,
        stress_score=avg_stress,
        ood_flag=ood_data.get("ood_flag", False),
        known_pattern=req.known_pattern,
    )

    stress_by_id = {r["carrier_id"]: r for r in stress_data.get("stress_results", [])}
    for opt in pareto_options:
        sr = stress_by_id.get(opt["carrier_id"], {})
        opt["stress_score"] = sr.get("stress_score", 0.67)
        opt["stress_scenarios"] = sr.get("scenarios", {})
        opt["viability_summary"] = sr.get("viability_summary", "")

    # Gemini insights
    gemini_insights = await gemini_service.get_demand_insights({
        "pareto_options": pareto_options[:3],
        "autonomy_tier": str(autonomy.tier),
        "policy": policy,
        "aqi": aqi_value,
    })

    card_id = None
    if autonomy.tier in (AutonomyTier.PARETO_CARD, AutonomyTier.FULL_ESCALATE):
        await create_approval_card(
            decision_id=incident_id,
            incident_context=incident_ctx,
            pareto_options=pareto_options,
            autonomy_decision=autonomy.__dict__,
            stress_results=stress_data,
            aqi_data=aqi_data,
            policy=policy,
        )
        card_id = incident_id

    counterfactuals = None
    if autonomy.tier == AutonomyTier.FULL_ESCALATE and len(pareto_options) >= 1:
        counterfactuals = await gemini_service.generate_counterfactuals(
            pareto_options[0], pareto_options[1:], incident_ctx
        )

    bg.add_task(save_demand_decision, incident_id, req.dict(), {"pareto_options": pareto_options}, gemini_insights)

    return {
        "incident_id": incident_id,
        "autonomy_tier": str(autonomy.tier),
        "autonomy_reason": autonomy.reason,
        "recommended_action": autonomy.recommended_action,
        "card_id": card_id,
        "policy": policy,
        "aqi_data": aqi_data,
        "weights_used": topsis.weights,
        "pareto_options": pareto_options,
        "stress_results": stress_data,
        "ood_detection": ood_data,
        "counterfactuals": counterfactuals,
        "gemini_insights": gemini_insights,
        "ts": datetime.datetime.utcnow().isoformat(),
    }


@router.get("/pending")
async def list_pending():
    cards = await get_pending_cards()
    return {"pending": cards, "count": len(cards)}


@router.get("/cards/{card_id}")
async def get_decision_card(card_id: str):
    card = await get_card(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card {card_id} not found")
    return card


@router.post("/cards/{card_id}/resolve")
async def resolve_decision(card_id: str, req: HITLResolveRequest):
    if req.action not in ("APPROVE", "MODIFY", "REJECT"):
        raise HTTPException(status_code=400, detail="action must be APPROVE | MODIFY | REJECT")
    return await resolve_card(card_id, req.action, req.selected_option_rank, req.operator_notes)


@router.get("/policy")
async def get_policy():
    return {"current_policy": get_current_policy(), "aqi_override": get_aqi_override()}


@router.post("/policy")
async def update_policy(req: PolicyUpdateRequest):
    record = set_policy(req.policy, req.changed_by)
    return {"message": f"Policy updated to {req.policy}", "record": record}


@router.get("/aqi/{city}")
async def fetch_aqi(city: str = "delhi"):
    return await get_aqi(city)


@router.post("/ewaybill/generate")
async def generate_ewb(req: EWayBillRequest):
    try:
        result = await generate_ewaybill(req.dict())
        db = get_supabase()
        if db:
            try:
                db.table("ewaybills").insert({"ewb_no": result.get("ewb_no"), "shipment_id": req.shipment_id, "payload": result}).execute()
            except Exception:
                pass
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ewaybill/update-vehicle")
async def update_vehicle(req: VehicleUpdateRequest):
    try:
        return await update_vehicle_part_b(req.ewb_no, req.new_vehicle_no, req.reason)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ewaybill/{ewb_no}/cancel")
async def cancel_ewb(ewb_no: str, cancel_reason: int = 2, remark: str = "Cancelled by agent"):
    try:
        return await cancel_ewaybill(ewb_no, cancel_reason, remark)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/log/recent")
async def get_recent_decisions(limit: int = 20):
    db = get_supabase()
    if db:
        try:
            result = db.table("demand_forecasts").select("*").order("created_at", desc=True).limit(limit).execute()
            return {"decisions": result.data}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"decisions": []}

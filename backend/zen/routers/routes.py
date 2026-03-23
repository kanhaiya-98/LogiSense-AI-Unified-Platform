from __future__ import annotations
"""
Zen Platform — ZenRTO Router (F12 RTO Risk Scoring)
LightGBM-based return-to-origin risk score + SHAP + fraud detection
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from zen.models.routes.rto_scorer import score_order
from zen.models.routes.address_parser import score_address, extract_pincode
from zen.services.pincode_data import get_pincode_info, get_buyer_profile
from zen.services.fraud_detection import detect_fraud_flags
from zen.services.gemini_service import get_route_explanation
from zen.services.whatsapp import send_whatsapp_confirmation
from zen.db.supabase import get_supabase, save_route_score

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory demo store (when Supabase not configured)
_demo_orders: list[dict] = []


class OrderScoreRequest(BaseModel):
    order_id: str = Field(..., example="ORD-20240301-001")
    buyer_id: str = Field(..., example="BUY-12345")
    buyer_phone: Optional[str] = None
    pincode: str = Field(..., example="110091")
    address_raw: str = Field(..., example="Flat 4B, Green Enclave, Sector 7, Delhi 110091")
    payment_method: str = Field(..., example="COD")
    order_value: float = Field(..., gt=0, example=1200.0)
    product_category: str = "GENERAL"
    hour_of_day: Optional[int] = None
    day_of_week: Optional[int] = None
    device_type: str = "MOBILE"
    buyer_rto_history_override: Optional[float] = None
    buyer_order_count_override: Optional[int] = None


class ActionUpdateRequest(BaseModel):
    action: str
    notes: Optional[str] = None


@router.post("/score")
async def score_new_order(req: OrderScoreRequest):
    """Score an order for RTO risk using LightGBM + SHAP + Gemini explanation."""
    now = datetime.utcnow()
    hour = req.hour_of_day if req.hour_of_day is not None else now.hour
    dow = req.day_of_week if req.day_of_week is not None else now.weekday()

    pincode_info = get_pincode_info(req.pincode)
    pincode_rto = pincode_info["rto_rate"]
    is_fraud_pin = pincode_info["is_fraud_pincode"]

    buyer = get_buyer_profile(req.buyer_id)
    buyer_rto = req.buyer_rto_history_override if req.buyer_rto_history_override is not None else buyer["rto_rate"]
    buyer_cnt = req.buyer_order_count_override if req.buyer_order_count_override is not None else buyer["order_count"]

    addr_score = score_address(req.address_raw)

    try:
        result = score_order(
            buyer_rto_history=buyer_rto,
            buyer_order_count=buyer_cnt,
            pincode_rto_rate=pincode_rto,
            is_fraud_pincode=is_fraud_pin,
            order_value=req.order_value,
            address_score=addr_score,
            hour_of_day=hour,
            day_of_week=dow,
            payment_method=req.payment_method,
            device_type=req.device_type,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"ML model not trained yet. {str(e)}")

    fraud_flags = detect_fraud_flags(
        buyer_id=req.buyer_id,
        pincode=req.pincode,
        order_value=req.order_value,
        payment_method=req.payment_method,
        address_score=addr_score,
        buyer_rto_rate=buyer_rto,
        buyer_order_count=buyer_cnt,
        is_fraud_pincode=is_fraud_pin,
        hour_of_day=hour,
    )

    explanation = get_route_explanation(
        order_id=req.order_id,
        rto_score=result.score,
        risk_level=result.risk_level,
        top_factors=result.top_factors,
        order_value=req.order_value,
        buyer_order_count=buyer_cnt,
    )

    wa_sent = False
    if result.action == "SEND_WHATSAPP_CONFIRMATION" and req.buyer_phone:
        wa_result = send_whatsapp_confirmation(
            to_phone=req.buyer_phone,
            order_id=req.order_id,
            order_value=req.order_value,
            rto_score=result.score,
        )
        wa_sent = wa_result.get("success", False)

    order_record = {
        "order_id": req.order_id,
        "buyer_id": req.buyer_id,
        "buyer_phone": req.buyer_phone,
        "pincode": req.pincode,
        "pincode_city": pincode_info.get("city", ""),
        "address_raw": req.address_raw,
        "payment_method": req.payment_method,
        "order_value": req.order_value,
        "product_category": req.product_category,
        "device_type": req.device_type,
        "rto_score": result.score,
        "risk_level": result.risk_level,
        "action_taken": result.action,
        "shap_values": result.shap_values,
        "top_risk_factors": result.top_factors,
        "explanation": explanation,
        "savings_estimate_rs": result.savings_estimate_rs,
        "is_fraud_pincode": is_fraud_pin,
        "fraud_flags": fraud_flags,
        "buyer_rto_history": buyer_rto,
        "buyer_order_count": buyer_cnt,
        "address_score": addr_score,
        "whatsapp_sent": wa_sent,
        "hour_of_day": hour,
        "day_of_week": dow,
        "created_at": now.isoformat(),
    }

    # Persist to Supabase
    db = get_supabase()
    if db:
        try:
            db.table("orders").upsert({
                "order_id": req.order_id,
                "buyer_id": req.buyer_id,
                "pincode": req.pincode,
                "address_raw": req.address_raw,
                "payment_method": req.payment_method,
                "order_value": req.order_value,
                "rto_score": result.score,
                "risk_level": result.risk_level,
                "action_taken": result.action,
                "top_risk_factors": [f["feature"] for f in result.top_factors],
                "is_fraud_pincode": is_fraud_pin,
                "fraud_flags": fraud_flags,
                "buyer_rto_history": buyer_rto,
                "buyer_order_count": buyer_cnt,
                "address_score": addr_score,
                "whatsapp_sent": wa_sent,
                "hour_of_day": hour,
                "day_of_week": dow,
            }).execute()
        except Exception as e:
            logger.warning(f"Supabase write failed (continuing): {e}")
    else:
        _demo_orders.append(order_record)
        if len(_demo_orders) > 200:
            _demo_orders.pop(0)

    save_route_score(req.dict(), order_record, explanation)
    return order_record


@router.get("/stats")
async def get_stats_summary():
    """Aggregate RTO stats for the dashboard."""
    db = get_supabase()
    orders = []
    if db:
        try:
            res = db.table("orders").select("risk_level, rto_score, action_taken, fraud_flags").execute()
            orders = res.data
        except Exception:
            orders = _demo_orders
    else:
        orders = _demo_orders

    total = len(orders)
    if total == 0:
        return {"total_orders": 0, "risk_breakdown": {}, "avg_rto_score": 0, "fraud_flagged": 0}

    risk_breakdown = {}
    avg_score = 0.0
    fraud_count = 0
    for o in orders:
        rl = o.get("risk_level", "LOW")
        risk_breakdown[rl] = risk_breakdown.get(rl, 0) + 1
        avg_score += float(o.get("rto_score", 0) or 0)
        flags = o.get("fraud_flags") or []
        if isinstance(flags, list) and len(flags) > 0:
            fraud_count += 1

    return {
        "total_orders": total,
        "risk_breakdown": risk_breakdown,
        "avg_rto_score": round(avg_score / total, 4),
        "fraud_flagged": fraud_count,
        "high_risk_pct": round((risk_breakdown.get("HIGH", 0) + risk_breakdown.get("CRITICAL", 0)) / total, 4),
    }


@router.get("/orders")
async def list_orders(risk_level: Optional[str] = Query(None), limit: int = Query(50, le=200)):
    db = get_supabase()
    if db:
        try:
            q = db.table("orders").select("*").order("created_at", desc=True).limit(limit)
            if risk_level:
                q = q.eq("risk_level", risk_level.upper())
            return q.execute().data
        except Exception as e:
            logger.warning(f"List orders DB error: {e}")
    orders = _demo_orders[-limit:][::-1]
    if risk_level:
        orders = [o for o in orders if o.get("risk_level") == risk_level.upper()]
    return orders


@router.get("/orders/{order_id}")
async def get_order(order_id: str):
    db = get_supabase()
    if db:
        try:
            res = db.table("orders").select("*").eq("order_id", order_id).execute()
            if res.data:
                return res.data[0]
        except Exception:
            pass
    for o in _demo_orders:
        if o.get("order_id") == order_id:
            return o
    raise HTTPException(status_code=404, detail=f"Order {order_id} not found")


@router.patch("/orders/{order_id}/action")
async def update_action(order_id: str, req: ActionUpdateRequest):
    db = get_supabase()
    if db:
        try:
            db.table("orders").update({"action_taken": req.action}).eq("order_id", order_id).execute()
            return {"order_id": order_id, "action_taken": req.action, "updated": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    for o in _demo_orders:
        if o.get("order_id") == order_id:
            o["action_taken"] = req.action
            return {"order_id": order_id, "action_taken": req.action, "updated": True}
    raise HTTPException(status_code=404, detail=f"Order {order_id} not found")

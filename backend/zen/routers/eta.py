from __future__ import annotations
"""
Zen Platform — ZenETA Router (F7 ETA Re-Estimation Engine)
XGBoost + Chronos-2, weather enrichment, Actor/Learner agents
"""
import time
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field

from zen.services.gemini_service import get_eta_context
from zen.db.supabase import save_eta_prediction

logger = logging.getLogger(__name__)
router = APIRouter()


class ETAPredictionRequest(BaseModel):
    shipment_id: str
    route_distance_km: float
    carrier_id: str = "CAR-01"
    region: str = "central"
    hour: int = Field(default_factory=lambda: datetime.utcnow().hour)
    dow: int = Field(default_factory=lambda: datetime.utcnow().weekday())
    warehouse_throughput_15min: int = 100
    aqi_speed_multiplier: float = 1.0
    lane_avg_delay_30d: float = 0.0
    sla_deadline_minutes: int = 480
    origin_lat: float = 28.6139
    origin_lon: float = 77.2090
    dest_lat: float = 19.0760
    dest_lon: float = 72.8777


class ChronosPredictionRequest(BaseModel):
    shipment_id: str
    historical_transit_times: List[float]
    baseline_minutes: float = 480.0


class InterventionRequest(BaseModel):
    shipment_id: str
    intervention_type: str  # reroute_shipment | swap_carrier | redirect_warehouse
    new_carrier_id: Optional[str] = None
    new_route_params: Optional[dict] = None
    new_warehouse: Optional[dict] = None


class ActualRecordRequest(BaseModel):
    shipment_id: str
    prediction_id: str
    actual_minutes: float


@router.post("/predict")
async def predict_eta(req: ETAPredictionRequest, background_tasks: BackgroundTasks, request: Request):
    """
    Primary ETA prediction using XGBoost.
    < 200ms total (XGBoost inference < 5ms, weather fetch async).
    """
    app_state = getattr(request.app.state, "app_state", {})
    from zen.models.eta.xgboost_service import XGBoostETAService
    from zen.services.weather_service import get_route_weather

    t0 = time.perf_counter()

    weather = await get_route_weather(req.origin_lat, req.origin_lon, req.dest_lat, req.dest_lon)

    xgboost_svc = app_state.get("xgboost")
    if not xgboost_svc or not xgboost_svc.is_loaded:
        raise HTTPException(status_code=503, detail="XGBoost model not loaded. Run training first.")

    pred = xgboost_svc.predict(
        route_distance_km=req.route_distance_km,
        carrier_id=req.carrier_id,
        region=req.region,
        hour=req.hour,
        dow=req.dow,
        warehouse_throughput_15min=req.warehouse_throughput_15min,
        aqi_speed_multiplier=req.aqi_speed_multiplier,
        weather_rain_flag=weather["rain_flag"],
        lane_avg_delay_30d=req.lane_avg_delay_30d,
        sla_deadline_minutes=req.sla_deadline_minutes,
    )

    total_ms = (time.perf_counter() - t0) * 1000

    eta_summary = {
        "shipment_id": req.shipment_id,
        "estimated_minutes": pred["estimated_minutes"],
        "p50": pred["p50"],
        "p90": pred["p90"],
        "p99": pred["p99"],
        "sla_breach_prob": pred["sla_breach_prob"],
        "weather_rain_flag": weather["rain_flag"],
        "aqi_speed_multiplier": req.aqi_speed_multiplier,
        "inference_time_ms": round(total_ms, 2),
        "prediction_source": "xgboost",
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Gemini insight in background
    async def add_gemini_and_save():
        gemini_summary = await get_eta_context(eta_summary)
        save_eta_prediction(req.dict(), pred["estimated_minutes"], 1 - pred["sla_breach_prob"], gemini_summary)
        return gemini_summary

    background_tasks.add_task(add_gemini_and_save)

    # Also get Gemini insights synchronously for the response
    try:
        gemini_summary = await get_eta_context(eta_summary)
    except Exception:
        gemini_summary = "ETA analysis pending."

    return {**eta_summary, "gemini_summary": gemini_summary}


@router.post("/predict/chronos")
async def predict_chronos(req: ChronosPredictionRequest, request: Request):
    """Chronos-2 zero-shot lane delay forecast."""
    app_state = getattr(request.app.state, "app_state", {})

    chronos = app_state.get("chronos")
    if not chronos:
        raise HTTPException(status_code=503, detail="Chronos-2 not loaded. Set USE_CHRONOS=true and restart.")

    forecast = chronos.predict_lane_delay(historical_transit_times=req.historical_transit_times)
    lane_delay = chronos.get_lane_avg_delay_30d(req.historical_transit_times, req.baseline_minutes)

    return {
        "shipment_id": req.shipment_id,
        "chronos_forecast": forecast,
        "lane_avg_delay_30d": lane_delay,
        "model": "amazon/chronos-bolt-small",
        "note": "Pass lane_avg_delay_30d into /predict for combined XGBoost+Chronos ETA",
    }


@router.post("/predict/bulk")
async def predict_bulk(requests: list, request: Request):
    """Bulk prediction — up to 1,000 shipments."""
    app_state = getattr(request.app.state, "app_state", {})
    from zen.services.weather_service import get_route_weather
    import asyncio

    xgboost_svc = app_state.get("xgboost")
    if not xgboost_svc:
        raise HTTPException(status_code=503, detail="XGBoost model not loaded.")

    async def _single(data: dict) -> dict:
        weather = await get_route_weather(
            data.get("origin_lat", 28.6), data.get("origin_lon", 77.2),
            data.get("dest_lat", 19.0), data.get("dest_lon", 72.8),
        )
        return xgboost_svc.predict(
            route_distance_km=data["route_distance_km"],
            carrier_id=data.get("carrier_id", "CAR-01"),
            region=data.get("region", "central"),
            hour=data.get("hour", datetime.utcnow().hour),
            dow=data.get("dow", datetime.utcnow().weekday()),
            warehouse_throughput_15min=data.get("warehouse_throughput_15min", 100),
            aqi_speed_multiplier=data.get("aqi_speed_multiplier", 1.0),
            weather_rain_flag=weather["rain_flag"],
            lane_avg_delay_30d=data.get("lane_avg_delay_30d", 0.0),
            sla_deadline_minutes=data.get("sla_deadline_minutes", 480),
        ) | {"shipment_id": data.get("shipment_id", "")}

    t0 = time.perf_counter()
    results = await asyncio.gather(*[_single(r) for r in requests], return_exceptions=True)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    ok = [r for r in results if isinstance(r, dict)]
    return {"count": len(ok), "elapsed_ms": round(elapsed_ms, 2), "results": ok}


@router.post("/intervention")
async def trigger_intervention(req: InterventionRequest, request: Request):
    """Actor Agent tool — triggers synchronous ETA re-estimation."""
    app_state = getattr(request.app.state, "app_state", {})

    actor = app_state.get("actor")
    if not actor:
        raise HTTPException(status_code=503, detail="Actor agent not initialized.")

    if req.intervention_type == "swap_carrier":
        return await actor.swap_carrier(req.shipment_id, req.new_carrier_id or "CAR-01", req.new_route_params)
    elif req.intervention_type == "reroute_shipment":
        return await actor.reroute_shipment(req.shipment_id, req.new_route_params or {})
    elif req.intervention_type == "redirect_warehouse":
        return await actor.redirect_warehouse(req.shipment_id, req.new_warehouse or {}, req.new_route_params)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown intervention: {req.intervention_type}")


@router.post("/record-actual")
async def record_actual(req: ActualRecordRequest, request: Request):
    """Learner Agent — record actual delivery time for retraining."""
    app_state = getattr(request.app.state, "app_state", {})

    learner = app_state.get("learner")
    if not learner:
        raise HTTPException(status_code=503, detail="Learner agent not initialized.")
    await learner.record_actual(req.shipment_id, req.prediction_id, req.actual_minutes)
    return {"status": "recorded", "shipment_id": req.shipment_id}

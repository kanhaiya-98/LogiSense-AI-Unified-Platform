from __future__ import annotations
"""
Actor Agent — copied and adapted from zeneta/app/agents/actor_agent.py
Fixed imports for zen-platform package structure.
"""
import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class ActorAgent:
    def __init__(self, eta_service, supabase_service):
        self.eta_service = eta_service
        self.supabase_service = supabase_service

    async def reroute_shipment(self, shipment_id: str, new_route_params: Dict[str, Any]) -> dict:
        logger.info(f"[Actor] reroute_shipment → {shipment_id}")
        return await self._re_estimate(shipment_id, new_route_params, "reroute_shipment")

    async def swap_carrier(self, shipment_id: str, new_carrier_id: str, route_params: Optional[Dict[str, Any]] = None) -> dict:
        logger.info(f"[Actor] swap_carrier → {shipment_id} carrier={new_carrier_id}")
        params = route_params or {}
        params["carrier_id"] = new_carrier_id
        return await self._re_estimate(shipment_id, params, "swap_carrier")

    async def redirect_warehouse(self, shipment_id: str, new_warehouse: Dict[str, Any], route_params: Optional[Dict[str, Any]] = None) -> dict:
        logger.info(f"[Actor] redirect_warehouse → {shipment_id}")
        params = route_params or {}
        params["warehouse_throughput_15min"] = new_warehouse.get("throughput_15min", 100)
        return await self._re_estimate(shipment_id, params, "redirect_warehouse")

    async def bulk_re_estimate(self, shipment_ids: List[str], new_params: Dict[str, Any], intervention_type: str) -> List[dict]:
        logger.info(f"[Actor] Bulk re-estimate: {len(shipment_ids)} shipments | {intervention_type}")
        results = await asyncio.gather(*[self._re_estimate(sid, new_params.copy(), intervention_type) for sid in shipment_ids], return_exceptions=True)
        return [r for r in results if isinstance(r, dict)]

    async def _re_estimate(self, shipment_id: str, route_params: Dict[str, Any], trigger: str) -> dict:
        from zen.services.weather_service import get_route_weather
        try:
            shipment = await self.supabase_service.get_shipment(shipment_id)
            if not shipment:
                raise ValueError(f"Shipment {shipment_id} not found")

            weather = await get_route_weather(
                shipment["origin_lat"], shipment["origin_lon"],
                shipment["dest_lat"], shipment["dest_lon"],
            )
            now = datetime.utcnow()
            prediction = self.eta_service.predict(
                route_distance_km=route_params.get("route_distance_km", shipment["route_distance_km"]),
                carrier_id=route_params.get("carrier_id", shipment["carrier_id"]),
                region=route_params.get("region", shipment.get("region", "central")),
                hour=now.hour, dow=now.weekday(),
                warehouse_throughput_15min=route_params.get("warehouse_throughput_15min", 100.0),
                aqi_speed_multiplier=route_params.get("aqi_speed_multiplier", 1.0),
                weather_rain_flag=weather["rain_flag"],
                lane_avg_delay_30d=route_params.get("lane_avg_delay_30d", 0.0),
                sla_deadline_minutes=shipment.get("sla_deadline_minutes", 480.0),
            )
            output = {
                "shipment_id": shipment_id, "trigger": trigger,
                "estimated_minutes": prediction["estimated_minutes"],
                "p50": prediction["p50"], "p90": prediction["p90"], "p99": prediction["p99"],
                "sla_breach_prob": prediction["sla_breach_prob"],
                "weather_rain_flag": weather["rain_flag"],
                "prediction_source": "xgboost",
                "inference_time_ms": prediction["inference_time_ms"],
                "timestamp": now.isoformat(),
            }
            await self.supabase_service.save_prediction({**prediction, "shipment_id": shipment_id, "trigger": trigger, "timestamp": now.isoformat()})
            await self.supabase_service.update_shipment(shipment_id, {
                "latest_eta_minutes": prediction["estimated_minutes"],
                "latest_sla_breach_prob": prediction["sla_breach_prob"],
                "carrier_id": route_params.get("carrier_id", shipment["carrier_id"]),
                "last_updated": now.isoformat(),
            })
            return output
        except Exception as e:
            logger.error(f"[Actor] _re_estimate({shipment_id}): {e}")
            raise

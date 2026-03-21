from __future__ import annotations
"""
Weather Service — Open-Meteo API (free, no auth).
Copied from zeneta/app/services/weather_service.py
"""
import httpx
import logging
from typing import Dict

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
RAIN_THRESHOLD_MM = 0.1
RAIN_DELAY_MINUTES = 40.0


async def get_weather_rain_flag(lat: float, lon: float) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                OPEN_METEO_URL,
                params={"latitude": lat, "longitude": lon, "hourly": "precipitation", "forecast_days": 1, "timezone": "auto"},
            )
            resp.raise_for_status()
            data = resp.json()
        precipitation = data.get("hourly", {}).get("precipitation", [0.0])
        current_precip = precipitation[0] if precipitation else 0.0
        rain = current_precip > RAIN_THRESHOLD_MM
        logger.debug(f"Weather @ ({lat:.2f},{lon:.2f}): {current_precip}mm → rain={rain}")
        return rain
    except httpx.TimeoutException:
        logger.warning("Open-Meteo timeout — defaulting rain=False")
        return False
    except Exception as e:
        logger.warning(f"Open-Meteo error ({e}) — defaulting rain=False")
        return False


async def get_route_weather(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> Dict:
    mid_lat = (origin_lat + dest_lat) / 2
    mid_lon = (origin_lon + dest_lon) / 2
    rain_flag = await get_weather_rain_flag(mid_lat, mid_lon)
    return {
        "rain_flag": rain_flag,
        "rain_delay_minutes": RAIN_DELAY_MINUTES if rain_flag else 0.0,
        "checked_lat": mid_lat,
        "checked_lon": mid_lon,
    }

from __future__ import annotations
"""
AQI Service — fetches Air Quality Index using OpenAQ or falls back to mock data.
"""
import os
import logging
import httpx
from typing import Dict

logger = logging.getLogger(__name__)

CITY_COORDS = {
    "delhi": {"lat": 28.6139, "lon": 77.2090},
    "mumbai": {"lat": 19.0760, "lon": 72.8777},
    "bangalore": {"lat": 12.9716, "lon": 77.5946},
    "hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "chennai": {"lat": 13.0827, "lon": 80.2707},
    "kolkata": {"lat": 22.5726, "lon": 88.3639},
    "pune": {"lat": 18.5204, "lon": 73.8567},
    "ahmedabad": {"lat": 23.0225, "lon": 72.5714},
}

MOCK_AQI = {
    "delhi": 180,
    "mumbai": 95,
    "bangalore": 75,
    "hyderabad": 85,
    "chennai": 70,
    "kolkata": 130,
    "pune": 80,
    "ahmedabad": 120,
}


def _aqi_category(aqi: int) -> str:
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"


async def get_aqi(city: str) -> Dict:
    """Fetch AQI for a city. Uses OpenAQ if API key set, else returns mock data."""
    city_lower = city.lower().strip()
    api_key = os.getenv("OPENAQ_API_KEY", "")

    if api_key:
        try:
            coords = CITY_COORDS.get(city_lower, {"lat": 28.6139, "lon": 77.2090})
            url = "https://api.openaq.org/v3/locations"
            params = {
                "coordinates": f"{coords['lat']},{coords['lon']}",
                "radius": 25000,
                "limit": 1,
                "order_by": "distance",
            }
            headers = {"X-API-Key": api_key}
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if results:
                    # Extract PM2.5 or overall AQI if available
                    location = results[0]
                    sensors = location.get("sensors", [])
                    for sensor in sensors:
                        if sensor.get("parameter", {}).get("name") in ("pm25", "pm2.5"):
                            aqi_val = int(sensor.get("latest", {}).get("value", 100))
                            return {
                                "city": city,
                                "aqi": aqi_val,
                                "category": _aqi_category(aqi_val),
                                "source": "openaq",
                            }
        except Exception as e:
            logger.warning(f"OpenAQ API call failed ({e}), using mock data.")

    # Fallback to mock
    aqi_val = MOCK_AQI.get(city_lower, 100)
    return {
        "city": city,
        "aqi": aqi_val,
        "category": _aqi_category(aqi_val),
        "source": "mock",
    }

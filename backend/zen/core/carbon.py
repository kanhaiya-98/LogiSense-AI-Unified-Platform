from __future__ import annotations
"""F6: Carbon Estimation — copied from zendec"""
EMISSION_FACTORS = {"air": 0.60, "road-diesel": 0.12, "road-ev": 0.03, "rail": 0.03}
DEFAULT_FACTOR = 0.12

def compute_co2(distance_km: float, weight_tonnes: float, vehicle_type: str) -> float:
    factor = EMISSION_FACTORS.get(vehicle_type.lower(), DEFAULT_FACTOR)
    return distance_km * weight_tonnes * factor

def compute_co2_delta(distance_km, weight_tonnes, vehicle_type, baseline_vehicle_type="road-diesel") -> float:
    return round(compute_co2(distance_km, weight_tonnes, vehicle_type) - compute_co2(distance_km, weight_tonnes, baseline_vehicle_type), 4)

def enrich_options_with_carbon(options: list, baseline_vehicle_type: str = "road-diesel") -> list:
    for opt in options:
        opt.co2_kg    = compute_co2(opt.distance_km, opt.weight_tonnes, opt.vehicle_type)
        opt.co2_delta = compute_co2_delta(opt.distance_km, opt.weight_tonnes, opt.vehicle_type, baseline_vehicle_type)
    return options

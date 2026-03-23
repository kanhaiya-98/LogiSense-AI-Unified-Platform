from __future__ import annotations
"""
Policy Store — in-memory fallback (Redis optional).
Zen Platform version — Redis removed as optional dependency.
"""
import hashlib
import datetime
from typing import Optional

VALID_POLICIES = {"BALANCED", "COST_FIRST", "SPEED_FIRST", "CARBON_FIRST"}
DEFAULT_POLICY = "BALANCED"

_store: dict = {"policy": DEFAULT_POLICY, "aqi_override": None}


def get_current_policy() -> str:
    return _store.get("policy", DEFAULT_POLICY)


def set_policy(new_policy: str, changed_by: str = "system") -> dict:
    if new_policy not in VALID_POLICIES:
        raise ValueError(f"Invalid policy '{new_policy}'. Must be one of {VALID_POLICIES}")
    old_policy = _store.get("policy", DEFAULT_POLICY)
    _store["policy"] = new_policy
    ts = datetime.datetime.utcnow().isoformat()
    fingerprint = hashlib.sha256(f"{old_policy}→{new_policy}:{changed_by}:{ts}".encode()).hexdigest()
    return {"old_policy": old_policy, "new_policy": new_policy, "changed_by": changed_by, "changed_at": ts, "fingerprint": fingerprint}


def get_aqi_override() -> Optional[dict]:
    return _store.get("aqi_override")


def set_aqi_override(aqi_value: float, location: str):
    _store["aqi_override"] = {"aqi": aqi_value, "location": location, "ts": datetime.datetime.utcnow().isoformat()}

from __future__ import annotations
"""
E-Way Bill Service — Stub implementation.
In production, this should integrate with NIC E-Way Bill API or a GSP.
For demo/dev purposes, returns mock responses.
"""
import os
import uuid
import logging
import datetime
from typing import Dict

logger = logging.getLogger(__name__)


async def generate_ewaybill(payload: Dict) -> dict:
    """Generate an E-Way Bill. Returns mock response if credentials not set."""
    username = os.getenv("EWAYBILL_USERNAME", "")
    password = os.getenv("EWAYBILL_PASSWORD", "")
    gstin = os.getenv("EWAYBILL_GSTIN", "")

    if username and password and gstin:
        # Production: integrate with NIC API / GSP here
        logger.warning("EWB credentials set but live integration not implemented. Returning mock.")

    # Mock response for demo
    ewb_no = f"EWB{uuid.uuid4().hex[:12].upper()}"
    return {
        "ewb_no": ewb_no,
        "ewb_date": datetime.datetime.utcnow().isoformat(),
        "valid_upto": (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat(),
        "shipment_id": payload.get("shipment_id", ""),
        "from_gstin": payload.get("from_gstin", gstin),
        "to_gstin": payload.get("to_gstin", ""),
        "doc_no": payload.get("doc_no", ""),
        "transport_mode": payload.get("transport_mode", "1"),
        "distance_km": payload.get("distance_km", 100),
        "status": "GENERATED",
        "source": "mock",
    }


async def update_vehicle_part_b(ewb_no: str, new_vehicle_no: str, reason: str = "Due to Break Down") -> dict:
    """Update vehicle number in Part B of E-Way Bill."""
    return {
        "ewb_no": ewb_no,
        "new_vehicle_no": new_vehicle_no,
        "reason": reason,
        "updated_at": datetime.datetime.utcnow().isoformat(),
        "status": "UPDATED",
        "source": "mock",
    }


async def cancel_ewaybill(ewb_no: str, cancel_reason: int = 2, remark: str = "Cancelled") -> dict:
    """Cancel an E-Way Bill."""
    return {
        "ewb_no": ewb_no,
        "cancel_reason": cancel_reason,
        "remark": remark,
        "cancelled_at": datetime.datetime.utcnow().isoformat(),
        "status": "CANCELLED",
        "source": "mock",
    }


async def get_ewaybill(ewb_no: str) -> dict:
    """Fetch details of an E-Way Bill."""
    return {
        "ewb_no": ewb_no,
        "status": "ACTIVE",
        "source": "mock",
    }

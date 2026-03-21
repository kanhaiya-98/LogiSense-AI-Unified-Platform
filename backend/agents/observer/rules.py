from datetime import datetime, timezone, timedelta
from typing import Optional


# ── Thresholds — change these without touching logic ──────────────
ETA_DRIFT_THRESHOLD_PCT   = 0.20  # flag if current ETA > original × 1.20
CARRIER_SILENCE_MIN       = 15    # minutes without check-in = CRITICAL
STATUS_STALL_MIN          = 30    # minutes without status change = MEDIUM
WH_LOAD_THRESHOLD_PCT     = 85.0  # warehouse load % threshold = HIGH


def check_eta_drift(shipment: dict) -> tuple[bool, str, str]:
    """
    Returns (flagged, severity, trigger_type).
    flagged=True if current ETA has drifted > 20% beyond original.
    """
    original = shipment.get('eta_minutes_original', 0)
    current  = shipment.get('eta_minutes_current', 0)
    if original <= 0:
        return False, '', ''
    drift_pct = (current - original) / original
    if drift_pct >= ETA_DRIFT_THRESHOLD_PCT:
        severity = 'CRITICAL' if drift_pct >= 0.50 else 'HIGH'
        return True, severity, 'ETA_DRIFT'
    return False, '', ''


def check_carrier_silence(shipment: dict,
                          last_checkin_ts: Optional[str]) -> tuple[bool, str, str]:
    """
    Returns (flagged, severity, trigger_type).
    flagged=True if carrier has not checked in for > 15 minutes.
    last_checkin_ts: ISO-8601 string from carrier_events table, or None.
    """
    if last_checkin_ts is None:
        # Never checked in — treat as silence from shipment creation
        return True, 'CRITICAL', 'CARRIER_SILENCE'
    try:
        last_dt = datetime.fromisoformat(last_checkin_ts.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        silence_min = (now - last_dt).total_seconds() / 60
        if silence_min > CARRIER_SILENCE_MIN:
            return True, 'CRITICAL', 'CARRIER_SILENCE'
    except (ValueError, TypeError):
        return True, 'HIGH', 'CARRIER_SILENCE'
    return False, '', ''


def check_status_stall(shipment: dict) -> tuple[bool, str, str]:
    """
    Returns (flagged, severity, trigger_type).
    flagged=True if shipment status has not changed for > 30 min.
    Requires shipment to have updated_at field.
    """
    updated_at = shipment.get('updated_at') or shipment.get('created_at')
    if not updated_at:
        return False, '', ''
    try:
        updated_dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        stall_min = (now - updated_dt).total_seconds() / 60
        if stall_min > STATUS_STALL_MIN:
            return True, 'MEDIUM', 'STATUS_STALL'
    except (ValueError, TypeError):
        pass
    return False, '', ''


def check_warehouse_load(warehouse_load_pct: float) -> tuple[bool, str, str]:
    """
    Returns (flagged, severity, trigger_type).
    flagged=True if warehouse load % exceeds threshold.
    """
    if warehouse_load_pct >= WH_LOAD_THRESHOLD_PCT:
        severity = 'CRITICAL' if warehouse_load_pct >= 95.0 else 'HIGH'
        return True, severity, 'WH_LOAD'
    return False, '', ''


SEVERITY_ORDER = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2, 'CRITICAL': 3}

def highest_severity(severities: list[str]) -> str:
    """Given a list of severities, return the most severe."""
    if not severities:
        return 'LOW'
    return max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0))

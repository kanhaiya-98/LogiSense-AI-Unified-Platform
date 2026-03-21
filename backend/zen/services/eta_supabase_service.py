from __future__ import annotations
"""
ETA Supabase Service — from zeneta, for zen-platform.
"""
import logging
from typing import Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self, url: str, key: str):
        if not url or not key or url == "your_supabase_project_url":
            logger.warning("Supabase not configured — ETA persistence disabled.")
            self.client = None
            return
        try:
            from supabase import create_client
            self.client = create_client(url, key)
            logger.info("Supabase ETA service initialized")
        except Exception as e:
            logger.warning(f"Supabase init failed: {e}")
            self.client = None

    async def get_shipment(self, shipment_id: str) -> Optional[dict]:
        if not self.client: return None
        try:
            resp = self.client.table("shipments").select("*").eq("id", shipment_id).single().execute()
            return resp.data
        except Exception as e:
            logger.error(f"get_shipment({shipment_id}): {e}")
            return None

    async def get_all_shipments(self, limit: int = 100) -> List[dict]:
        if not self.client: return []
        try:
            return self.client.table("shipments").select("*").order("created_at", desc=True).limit(limit).execute().data or []
        except Exception:
            return []

    async def update_shipment(self, shipment_id: str, data: dict) -> Optional[dict]:
        if not self.client: return None
        try:
            resp = self.client.table("shipments").update(data).eq("id", shipment_id).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"update_shipment({shipment_id}): {e}")
            return None

    async def save_prediction(self, prediction: dict) -> Optional[dict]:
        if not self.client: return None
        try:
            resp = self.client.table("predictions").insert(prediction).execute()
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"save_prediction: {e}")
            return None

    async def record_actual_time(self, shipment_id: str, prediction_id: str, actual_minutes: float, recorded_at: str):
        if not self.client: return
        try:
            self.client.table("predictions").update({"actual_minutes": actual_minutes, "recorded_at": recorded_at}).eq("id", prediction_id).execute()
            self.client.table("shipments").update({"actual_minutes": actual_minutes, "status": "delivered"}).eq("id", shipment_id).execute()
        except Exception as e:
            logger.error(f"record_actual_time: {e}")

    async def get_sla_breach_count(self) -> int:
        if not self.client: return 0
        try:
            resp = self.client.table("shipments").select("id", count="exact").gt("latest_sla_breach_prob", 0.5).eq("status", "in_transit").execute()
            return resp.count or 0
        except Exception:
            return 0

    async def get_last_training_time(self) -> Optional[datetime]:
        if not self.client: return None
        try:
            resp = self.client.table("model_training_runs").select("trained_at").order("trained_at", desc=True).limit(1).execute()
            if resp.data:
                return datetime.fromisoformat(resp.data[0]["trained_at"].replace("Z", "+00:00"))
            return None
        except Exception:
            return None

    async def save_training_run(self, rmse: float, n_samples: int, calibration_score=None, data_hash=None, notes=None):
        if not self.client: return
        try:
            self.client.table("model_training_runs").insert({
                "trained_at": datetime.utcnow().isoformat(), "rmse": rmse,
                "n_samples": n_samples, "calibration_score": calibration_score,
                "data_hash": data_hash, "notes": notes,
            }).execute()
        except Exception as e:
            logger.error(f"save_training_run: {e}")

    async def get_training_records(self, days: int = 30) -> List[dict]:
        if not self.client: return []
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            return self.client.table("predictions").select("*, shipments(*)").not_.is_("actual_minutes", "null").gte("timestamp", cutoff).execute().data or []
        except Exception:
            return []

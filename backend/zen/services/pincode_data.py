from __future__ import annotations
"""
Pincode RTO lookup — copied from zenrto. Removed dependency on app.database.
Uses static data with optional Supabase lookup.
"""
import logging
import os
logger = logging.getLogger(__name__)

STATIC_PINCODE_DATA = {
    "110001": {"city": "Delhi",      "state": "Delhi",       "tier": "METRO", "rto_rate": 0.21, "is_fraud": False},
    "110091": {"city": "Delhi",      "state": "Delhi",       "tier": "METRO", "rto_rate": 0.31, "is_fraud": True},
    "400001": {"city": "Mumbai",     "state": "Maharashtra", "tier": "METRO", "rto_rate": 0.17, "is_fraud": False},
    "400078": {"city": "Mumbai",     "state": "Maharashtra", "tier": "METRO", "rto_rate": 0.28, "is_fraud": True},
    "560001": {"city": "Bangalore",  "state": "Karnataka",   "tier": "METRO", "rto_rate": 0.16, "is_fraud": False},
    "600001": {"city": "Chennai",    "state": "Tamil Nadu",  "tier": "METRO", "rto_rate": 0.20, "is_fraud": False},
    "600028": {"city": "Chennai",    "state": "Tamil Nadu",  "tier": "METRO", "rto_rate": 0.35, "is_fraud": True},
    "700001": {"city": "Kolkata",    "state": "West Bengal", "tier": "METRO", "rto_rate": 0.22, "is_fraud": False},
    "700025": {"city": "Kolkata",    "state": "West Bengal", "tier": "METRO", "rto_rate": 0.29, "is_fraud": True},
    "500001": {"city": "Hyderabad",  "state": "Telangana",   "tier": "METRO", "rto_rate": 0.19, "is_fraud": False},
    "500032": {"city": "Hyderabad",  "state": "Telangana",   "tier": "METRO", "rto_rate": 0.32, "is_fraud": True},
    "302001": {"city": "Jaipur",     "state": "Rajasthan",   "tier": "TIER2", "rto_rate": 0.33, "is_fraud": False},
    "226001": {"city": "Lucknow",    "state": "UP",          "tier": "TIER2", "rto_rate": 0.36, "is_fraud": False},
    "827001": {"city": "Bokaro",     "state": "Jharkhand",   "tier": "TIER3", "rto_rate": 0.44, "is_fraud": False},
    "176001": {"city": "Dharamsala", "state": "HP",          "tier": "RURAL", "rto_rate": 0.48, "is_fraud": False},
}

def get_pincode_info(pincode: str) -> dict:
    # Try Supabase
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if url and key and url != "your_supabase_project_url":
        try:
            from supabase import create_client
            db = create_client(url, key)
            fraud_res = db.table("fraud_pincodes").select("*").eq("pincode", pincode).eq("is_active", True).execute()
            is_fraud = len(fraud_res.data) > 0
            rate_res = db.table("pincode_rto_rates").select("*").eq("pincode", pincode).execute()
            if rate_res.data:
                row = rate_res.data[0]
                return {"rto_rate": float(row.get("rto_rate", 0.25)), "is_fraud_pincode": is_fraud, "city": row.get("city", ""), "state": row.get("state", ""), "tier": row.get("tier", "METRO")}
        except Exception as e:
            logger.warning(f"Supabase pincode lookup failed: {e}")

    if pincode in STATIC_PINCODE_DATA:
        d = STATIC_PINCODE_DATA[pincode]
        return {"rto_rate": d["rto_rate"], "is_fraud_pincode": d["is_fraud"], "city": d["city"], "state": d["state"], "tier": d["tier"]}

    return {"rto_rate": 0.28, "is_fraud_pincode": False, "city": "Unknown", "state": "Unknown", "tier": "TIER2"}


def get_buyer_profile(buyer_id: str) -> dict:
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if url and key and url != "your_supabase_project_url":
        try:
            from supabase import create_client
            db = create_client(url, key)
            res = db.table("buyer_profiles").select("*").eq("buyer_id", buyer_id).execute()
            if res.data:
                row = res.data[0]
                return {"rto_rate": float(row.get("rto_rate", 0.0)), "order_count": int(row.get("total_orders", 0)), "blacklisted": bool(row.get("is_blacklisted", False))}
        except Exception as e:
            logger.warning(f"Buyer profile lookup failed: {e}")
    return {"rto_rate": 0.0, "order_count": 0, "blacklisted": False}

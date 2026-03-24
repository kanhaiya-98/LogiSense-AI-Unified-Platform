from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

# Fallback to Next.js public env keys if explicit generic ones aren't set
SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")  # ideally use service_role key for backend

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Example: Observer Agent querying live shipments
def get_active_shipments():
    return supabase.table("live_shipments") \
        .select("*") \
        .neq("status", "DELIVERED") \
        .execute().data

# Example: Reasoner Agent fetching DAG edges
def get_downstream_shipments(shipment_id):
    return supabase.table("shipment_dag_edges") \
        .select("child_shipment_id, dependency_type") \
        .eq("parent_shipment_id", shipment_id) \
        .execute().data

# Example: Actor Agent writing a decision
def log_decision(record: dict):
    return supabase.table("decision_log") \
        .insert(record) \
        .execute()

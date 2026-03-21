-- ================================================================
-- F6 Decision Engine + E-Way Bill Schema
-- Run this in: Supabase Dashboard → SQL Editor → New Query
-- ================================================================

-- ── HITL Approval Cards ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hitl_cards (
    id          BIGSERIAL PRIMARY KEY,
    card_id     TEXT UNIQUE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING',   -- PENDING | APPROVE | MODIFY | REJECT
    payload     JSONB NOT NULL,
    approved_option  INT,
    operator_notes   TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_hitl_cards_status ON hitl_cards(status);
CREATE INDEX IF NOT EXISTS idx_hitl_cards_created ON hitl_cards(created_at DESC);

-- ── Decision Log ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decision_log (
    id              BIGSERIAL PRIMARY KEY,
    decision_id     TEXT NOT NULL,
    action          TEXT NOT NULL,
    selected_option INT,
    operator_notes  TEXT,
    resolved_at     TIMESTAMPTZ DEFAULT NOW(),
    policy          TEXT,
    aqi_value       FLOAT,
    blast_radius    INT,
    confidence      FLOAT,
    topsis_scores   JSONB,
    fingerprint     TEXT    -- on-chain anchor hash
);
CREATE INDEX IF NOT EXISTS idx_decision_log_id ON decision_log(decision_id);

-- ── Policy Change History ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS policy_changes (
    id          BIGSERIAL PRIMARY KEY,
    old_policy  TEXT NOT NULL,
    new_policy  TEXT NOT NULL,
    changed_by  TEXT DEFAULT 'system',
    changed_at  TIMESTAMPTZ DEFAULT NOW(),
    fingerprint TEXT NOT NULL
);

-- ── E-Way Bills ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ewaybills (
    id              BIGSERIAL PRIMARY KEY,
    ewb_no          TEXT UNIQUE,
    shipment_id     TEXT NOT NULL,
    doc_no          TEXT,
    status          TEXT DEFAULT 'GENERATED',   -- GENERATED | PART_B_UPDATED | CANCELLED | EXPIRED
    vehicle_no      TEXT,
    from_gstin      TEXT,
    to_gstin        TEXT,
    from_place      TEXT,
    to_place        TEXT,
    distance_km     FLOAT,
    valid_upto      TIMESTAMPTZ,
    payload         JSONB,
    generated_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    cancelled_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ewaybills_shipment ON ewaybills(shipment_id);
CREATE INDEX IF NOT EXISTS idx_ewaybills_status ON ewaybills(status);

-- ── E-Way Bill Part-B Update Log ─────────────────────────────────
CREATE TABLE IF NOT EXISTS ewb_vehicle_updates (
    id              BIGSERIAL PRIMARY KEY,
    ewb_no          TEXT NOT NULL,
    old_vehicle_no  TEXT,
    new_vehicle_no  TEXT NOT NULL,
    reason          TEXT,
    updated_by      TEXT DEFAULT 'agent',
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    trigger_event   TEXT    -- e.g. "routing_agent_reassignment"
);

-- ── AQI Snapshot Log ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS aqi_log (
    id          BIGSERIAL PRIMARY KEY,
    city        TEXT NOT NULL,
    aqi         FLOAT NOT NULL,
    pm25_raw    FLOAT,
    policy_impact TEXT,
    logged_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Row-Level Security (enable for production) ───────────────────
-- ALTER TABLE hitl_cards ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE decision_log ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE ewaybills ENABLE ROW LEVEL SECURITY;

-- ── Helpful view: pending decisions ─────────────────────────────
CREATE OR REPLACE VIEW pending_decisions AS
SELECT
    card_id,
    status,
    created_at,
    payload->>'policy' AS policy,
    (payload->'aqi_data'->>'aqi')::float AS aqi,
    (payload->'autonomy_tier'->>'tier') AS tier,
    (payload->'incident_context'->>'blast_radius')::int AS blast_radius
FROM hitl_cards
WHERE status = 'PENDING'
ORDER BY created_at DESC;

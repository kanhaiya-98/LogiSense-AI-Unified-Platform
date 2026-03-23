-- ============================================================
-- ETA Re-Estimation Engine — Supabase Schema
-- Run in Supabase SQL Editor: Dashboard → SQL Editor → New query
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Shipments ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS shipments (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_city            TEXT NOT NULL,
    dest_city              TEXT NOT NULL,
    origin_lat             FLOAT NOT NULL,
    origin_lon             FLOAT NOT NULL,
    dest_lat               FLOAT NOT NULL,
    dest_lon               FLOAT NOT NULL,
    carrier_id             TEXT NOT NULL,
    region                 TEXT NOT NULL DEFAULT 'central',
    route_distance_km      FLOAT NOT NULL,
    sla_deadline_minutes   FLOAT NOT NULL DEFAULT 480,
    status                 TEXT NOT NULL DEFAULT 'in_transit'
                               CHECK (status IN ('pending', 'in_transit', 'delivered', 'delayed')),

    -- Updated by Actor Agent after every intervention
    latest_eta_minutes     FLOAT,
    latest_sla_breach_prob FLOAT DEFAULT 0,
    actual_minutes         FLOAT,
    last_updated           TIMESTAMPTZ,

    created_at             TIMESTAMPTZ DEFAULT NOW()
);

-- ── Predictions ──────────────────────────────────────────────────────────────
-- One row per ETA estimate (initial + every re-estimation)
CREATE TABLE IF NOT EXISTS predictions (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    shipment_id            UUID REFERENCES shipments(id) ON DELETE CASCADE,

    -- Trigger that caused this prediction
    trigger                TEXT DEFAULT 'manual',

    -- Output contract (per F7 spec)
    estimated_minutes      FLOAT NOT NULL,
    p50                    FLOAT NOT NULL,
    p90                    FLOAT NOT NULL,
    p99                    FLOAT NOT NULL,
    sla_breach_prob        FLOAT NOT NULL,

    -- Input context
    weather_rain_flag      BOOLEAN DEFAULT FALSE,
    aqi_speed_multiplier   FLOAT   DEFAULT 1.0,

    -- Learner Agent fills these when actual arrives
    actual_minutes         FLOAT,
    recorded_at            TIMESTAMPTZ,

    timestamp              TIMESTAMPTZ DEFAULT NOW()
);

-- ── Carrier Profiles ─────────────────────────────────────────────────────────
-- carrier_avg_speed[region][hour] — used as XGBoost feature
CREATE TABLE IF NOT EXISTS carrier_profiles (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    carrier_id       TEXT NOT NULL,
    region           TEXT NOT NULL,
    hour_of_day      INTEGER NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
    avg_speed_kmh    FLOAT NOT NULL DEFAULT 60,
    reliability_score FLOAT DEFAULT 1.0,  -- 0–1 (CAR-07 ≈ 0.80)
    updated_at       TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (carrier_id, region, hour_of_day)
);

-- ── Model Training Runs ───────────────────────────────────────────────────────
-- MLflow-like tracking in Supabase (rollback via this table)
CREATE TABLE IF NOT EXISTS model_training_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trained_at        TIMESTAMPTZ DEFAULT NOW(),
    rmse              FLOAT,
    n_samples         INTEGER,
    calibration_score FLOAT,   -- p90 coverage on holdout
    data_hash         TEXT,    -- MD5 of training data for reproducibility
    notes             TEXT
);

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_shipments_status
    ON shipments (status);

CREATE INDEX IF NOT EXISTS idx_shipments_sla_breach
    ON shipments (latest_sla_breach_prob DESC)
    WHERE status = 'in_transit';

CREATE INDEX IF NOT EXISTS idx_predictions_shipment
    ON predictions (shipment_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_carrier_profiles_lookup
    ON carrier_profiles (carrier_id, region, hour_of_day);

-- ── Seed: Carrier Profiles ───────────────────────────────────────────────────
-- Insert baseline speed profiles for all carriers (simplified, all hours)
-- You can extend this with real carrier data later.

INSERT INTO carrier_profiles (carrier_id, region, hour_of_day, avg_speed_kmh, reliability_score)
SELECT
    c.carrier_id,
    r.region,
    h.hour,
    CASE
        WHEN c.carrier_id = 'CAR-07' THEN
            CASE WHEN h.hour BETWEEN 7 AND 10 OR h.hour BETWEEN 16 AND 19
                 THEN 38  -- degraded + rush hour
                 ELSE 52  -- degraded base
            END
        ELSE
            CASE WHEN h.hour BETWEEN 7 AND 10 OR h.hour BETWEEN 16 AND 19
                 THEN 48  -- rush hour
                 ELSE 62  -- normal
            END
    END AS avg_speed_kmh,
    CASE c.carrier_id
        WHEN 'CAR-01' THEN 1.00
        WHEN 'CAR-02' THEN 0.98
        WHEN 'CAR-03' THEN 0.97
        WHEN 'CAR-04' THEN 0.96
        WHEN 'CAR-05' THEN 0.95
        WHEN 'CAR-06' THEN 0.93
        WHEN 'CAR-07' THEN 0.80
    END AS reliability_score
FROM
    (VALUES ('CAR-01'),('CAR-02'),('CAR-03'),('CAR-04'),('CAR-05'),('CAR-06'),('CAR-07'))
        AS c(carrier_id),
    (VALUES ('north'),('south'),('east'),('west'),('central'))
        AS r(region),
    generate_series(0, 23) AS h(hour)
ON CONFLICT (carrier_id, region, hour_of_day) DO NOTHING;

-- ── Seed: Sample At-Risk Shipments (for demo) ────────────────────────────────
-- Creates 5 at-risk shipments so demo-swap works immediately
INSERT INTO shipments (
    id, origin_city, dest_city, origin_lat, origin_lon,
    dest_lat, dest_lon, carrier_id, region,
    route_distance_km, sla_deadline_minutes, status,
    latest_sla_breach_prob
) VALUES
    (gen_random_uuid(), 'Mumbai',    'Delhi',     19.07, 72.87, 28.61, 77.20, 'CAR-07', 'west',    1400, 480, 'in_transit', 0.85),
    (gen_random_uuid(), 'Chennai',   'Bangalore', 13.08, 80.27, 12.97, 77.59, 'CAR-07', 'south',   350,  300, 'in_transit', 0.72),
    (gen_random_uuid(), 'Kolkata',   'Hyderabad', 22.57, 88.36, 17.38, 78.49, 'CAR-07', 'east',    1500, 600, 'in_transit', 0.91),
    (gen_random_uuid(), 'Pune',      'Ahmedabad', 18.52, 73.86, 23.02, 72.57, 'CAR-06', 'central', 660,  360, 'in_transit', 0.63),
    (gen_random_uuid(), 'Jaipur',    'Lucknow',   26.91, 75.79, 26.84, 80.94, 'CAR-07', 'north',   570,  420, 'in_transit', 0.79)
ON CONFLICT DO NOTHING;

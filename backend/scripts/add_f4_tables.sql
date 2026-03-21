-- scripts/add_f4_tables.sql

-- First, ensure the warehouses table has all required F4 columns:
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS capacity INTEGER DEFAULT 500;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS current_load_pct FLOAT DEFAULT 0.0;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS throughput_per_hr INTEGER DEFAULT 0;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS inbound_queue INTEGER DEFAULT 0;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'NORMAL';
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS location_city TEXT;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS latitude FLOAT;
ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS longitude FLOAT;

CREATE TABLE IF NOT EXISTS warehouse_throughput_log (
  id             SERIAL PRIMARY KEY,
  warehouse_id   TEXT NOT NULL,
  recorded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  load_pct       FLOAT NOT NULL,       -- snapshot of load % at this time
  throughput_hr  INTEGER NOT NULL,      -- shipments processed in last hour
  inbound_queue  INTEGER NOT NULL       -- shipments waiting to enter
);
CREATE INDEX idx_wh_log_wid_time ON warehouse_throughput_log(warehouse_id, recorded_at DESC);

-- Also add an intake_schedule table for stagger decisions:
CREATE TABLE IF NOT EXISTS warehouse_intake_schedule (
  id              SERIAL PRIMARY KEY,
  warehouse_id    TEXT NOT NULL,
  shipment_id     TEXT NOT NULL,
  original_eta    TIMESTAMPTZ,
  adjusted_eta    TIMESTAMPTZ,          -- stagger applied: original + N minutes
  stagger_minutes INTEGER DEFAULT 0,
  decision_id     TEXT,                 -- links back to decision_log for F9
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

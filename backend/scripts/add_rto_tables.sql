-- ============================================================
-- F12: RTO Risk Scoring & COD Fraud Detection
-- Run this entire file in Supabase → SQL Editor
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Orders ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id              TEXT UNIQUE NOT NULL,
  buyer_id              TEXT NOT NULL,
  buyer_phone           TEXT,
  pincode               TEXT NOT NULL,
  address_raw           TEXT NOT NULL,
  payment_method        TEXT NOT NULL CHECK (payment_method IN ('COD','PREPAID','CARD','UPI')),
  order_value           NUMERIC(10,2) NOT NULL,
  product_category      TEXT DEFAULT 'GENERAL',
  hour_of_day           INTEGER,
  day_of_week           INTEGER,
  device_type           TEXT DEFAULT 'MOBILE',
  rto_score             NUMERIC(6,5),
  risk_level            TEXT CHECK (risk_level IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  action_taken          TEXT,
  shap_json             JSONB,
  top_risk_factors      TEXT[],
  is_fraud_pincode      BOOLEAN DEFAULT FALSE,
  fraud_flags           JSONB DEFAULT '[]',
  whatsapp_sent         BOOLEAN DEFAULT FALSE,
  whatsapp_reply        TEXT CHECK (whatsapp_reply IN ('CONFIRMED','CANCELLED','PENDING',NULL)),
  whatsapp_sent_at      TIMESTAMPTZ,
  buyer_rto_history     NUMERIC(5,4) DEFAULT 0.0,
  buyer_order_count     INTEGER DEFAULT 0,
  address_score         NUMERIC(5,4) DEFAULT 1.0,
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── Buyer Profiles ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS buyer_profiles (
  buyer_id              TEXT PRIMARY KEY,
  buyer_phone           TEXT,
  total_orders          INTEGER DEFAULT 0,
  total_rtos            INTEGER DEFAULT 0,
  rto_rate              NUMERIC(5,4) DEFAULT 0.0,
  cod_orders            INTEGER DEFAULT 0,
  prepaid_orders        INTEGER DEFAULT 0,
  last_order_at         TIMESTAMPTZ,
  is_blacklisted        BOOLEAN DEFAULT FALSE,
  blacklist_reason      TEXT,
  risk_label            TEXT DEFAULT 'UNKNOWN',
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── Pincode RTO Rates ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pincode_rto_rates (
  pincode               TEXT PRIMARY KEY,
  city                  TEXT,
  state                 TEXT,
  tier                  TEXT CHECK (tier IN ('METRO','TIER2','TIER3','RURAL')),
  rto_rate              NUMERIC(5,4) NOT NULL,
  order_volume          INTEGER DEFAULT 100,
  is_fraud_cluster      BOOLEAN DEFAULT FALSE,
  last_updated          TIMESTAMPTZ DEFAULT NOW()
);

-- ── Fraud Pincode Blacklist ───────────────────────────────────
CREATE TABLE IF NOT EXISTS fraud_pincodes (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  pincode               TEXT UNIQUE NOT NULL,
  rto_rate              NUMERIC(5,4) NOT NULL,
  fraud_score           NUMERIC(5,4) DEFAULT 0.0,
  reason                TEXT,
  is_active             BOOLEAN DEFAULT TRUE,
  added_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ── Returns ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS returns (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  return_id             TEXT UNIQUE NOT NULL,
  order_id              TEXT REFERENCES orders(order_id),
  buyer_id              TEXT,
  photo_url             TEXT,
  damage_class          TEXT CHECK (damage_class IN ('NONE','MINOR','MODERATE','SEVERE','DESTROYED')),
  damage_confidence     NUMERIC(5,4),
  routing_decision      TEXT CHECK (routing_decision IN ('FULL_REFUND','PARTIAL_REFUND','REFURBISHMENT','LIQUIDATION','DISPOSAL')),
  cv_raw_scores         JSONB,
  cv_model_version      TEXT DEFAULT 'resnet50-finetuned-v1',
  notes                 TEXT,
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── WhatsApp Log ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS whatsapp_log (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  order_id              TEXT,
  buyer_phone           TEXT NOT NULL,
  direction             TEXT CHECK (direction IN ('OUTBOUND','INBOUND')),
  message_body          TEXT NOT NULL,
  twilio_sid            TEXT,
  status                TEXT DEFAULT 'queued',
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_orders_buyer       ON orders(buyer_id);
CREATE INDEX IF NOT EXISTS idx_orders_pincode     ON orders(pincode);
CREATE INDEX IF NOT EXISTS idx_orders_risk        ON orders(risk_level);
CREATE INDEX IF NOT EXISTS idx_orders_created     ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_action      ON orders(action_taken);

-- ── Auto-update trigger ───────────────────────────────────────
CREATE OR REPLACE FUNCTION _update_ts()
RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$ LANGUAGE plpgsql;

CREATE TRIGGER orders_ts    BEFORE UPDATE ON orders         FOR EACH ROW EXECUTE FUNCTION _update_ts();
CREATE TRIGGER buyer_ts     BEFORE UPDATE ON buyer_profiles FOR EACH ROW EXECUTE FUNCTION _update_ts();

-- ── Seed: Fraud Pincodes ──────────────────────────────────────
INSERT INTO fraud_pincodes (pincode, rto_rate, fraud_score, reason) VALUES
  ('110091', 0.3100, 0.87, 'High RTO cluster + repeat fraud buyers — Demo PIN'),
  ('400078', 0.2800, 0.82, 'Known COD abuse zone Mumbai'),
  ('600028', 0.3500, 0.91, 'Multiple fraud accounts detected Chennai'),
  ('700025', 0.2900, 0.78, 'Address spoofing cluster Kolkata'),
  ('500032', 0.3200, 0.84, 'Repeat non-delivery claims Hyderabad')
ON CONFLICT (pincode) DO NOTHING;

-- ── Seed: Key city pincodes ───────────────────────────────────
INSERT INTO pincode_rto_rates (pincode, city, state, tier, rto_rate) VALUES
  ('110001', 'Delhi',     'Delhi',       'METRO', 0.2100),
  ('110091', 'Delhi',     'Delhi',       'METRO', 0.3100),
  ('400001', 'Mumbai',    'Maharashtra', 'METRO', 0.1700),
  ('400078', 'Mumbai',    'Maharashtra', 'METRO', 0.2800),
  ('560001', 'Bangalore', 'Karnataka',   'METRO', 0.1600),
  ('600001', 'Chennai',   'Tamil Nadu',  'METRO', 0.2000),
  ('700001', 'Kolkata',   'West Bengal', 'METRO', 0.2200),
  ('500001', 'Hyderabad', 'Telangana',   'METRO', 0.1900),
  ('302001', 'Jaipur',    'Rajasthan',   'TIER2', 0.3300),
  ('226001', 'Lucknow',   'UP',          'TIER2', 0.3600),
  ('462001', 'Bhopal',    'MP',          'TIER2', 0.3400),
  ('831001', 'Jamshedpur','Jharkhand',   'TIER3', 0.4100),
  ('827001', 'Bokaro',    'Jharkhand',   'TIER3', 0.4400),
  ('176001', 'Dharamsala','HP',          'RURAL', 0.4800),
  ('194101', 'Leh',       'Ladakh',      'RURAL', 0.5200)
ON CONFLICT (pincode) DO NOTHING;

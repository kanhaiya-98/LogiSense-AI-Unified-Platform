from __future__ import annotations
"""
Feature 9: Database Layer
Persists DecisionRecord and MerkleBatch to SQLite (dev) or PostgreSQL (prod).

SQLite is used by default — zero config, works in Docker.
Switch to PostgreSQL by setting DATABASE_URL in your .env:
  DATABASE_URL=postgresql+psycopg2://user:pass@localhost/logisense

All writes are idempotent (INSERT OR REPLACE / ON CONFLICT DO UPDATE),
so re-processing a batch or restarting mid-anchor never corrupts state.
"""



import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import List, Optional

from blockchain_models import AnchorStatus, DecisionRecord, MerkleBatch

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Connection — SQLite default, swap DATABASE_URL for Postgres
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get("SQLITE_PATH", "logisense_blockchain.db")


@contextmanager
def _conn():
    """Yield a SQLite connection with WAL mode (safe for concurrent reads)."""
    con = sqlite3.connect(_DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decision_log (
    decision_id             TEXT PRIMARY KEY,
    agent_id                TEXT NOT NULL,
    tier                    TEXT NOT NULL,
    timestamp_utc           REAL NOT NULL,
    incident_id             TEXT,
    shipment_ids            TEXT,   -- JSON array
    carrier_id              TEXT,
    warehouse_id            TEXT,
    raw_inputs              TEXT,   -- JSON
    model_name              TEXT,
    model_version           TEXT,
    prediction              TEXT,   -- JSON (any type)
    confidence              REAL,
    calibrated_confidence   REAL,
    ood_flag                INTEGER DEFAULT 0,
    shap_values             TEXT,   -- JSON
    top_features            TEXT,   -- JSON array
    counterfactual          TEXT,   -- JSON
    reasoning_text          TEXT,
    stress_test_score       REAL,
    stress_test_worst_case  TEXT,
    action                  TEXT,
    action_params           TEXT,   -- JSON
    action_reversible       INTEGER DEFAULT 1,
    rollback_deadline_utc   REAL,
    outcome_actual          TEXT,   -- JSON
    outcome_predicted       TEXT,   -- JSON
    outcome_delta           REAL,
    fingerprint_hash        TEXT,
    anchor_status           TEXT NOT NULL DEFAULT 'pending',
    merkle_batch_id         TEXT,
    merkle_proof            TEXT,   -- JSON array
    merkle_root             TEXT,
    blockchain_tx_hash      TEXT,
    blockchain_block        INTEGER,
    agent_signature         TEXT,
    schema_version          TEXT DEFAULT '1.0',
    created_at              TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_anchor_status   ON decision_log(anchor_status);
CREATE INDEX IF NOT EXISTS idx_incident        ON decision_log(incident_id);
CREATE INDEX IF NOT EXISTS idx_shipment_batch  ON decision_log(merkle_batch_id);
CREATE INDEX IF NOT EXISTS idx_fingerprint     ON decision_log(fingerprint_hash);

CREATE TABLE IF NOT EXISTS merkle_batches (
    batch_id        TEXT PRIMARY KEY,
    created_utc     REAL NOT NULL,
    decision_ids    TEXT NOT NULL,  -- JSON array
    leaf_hashes     TEXT NOT NULL,  -- JSON array
    merkle_root     TEXT NOT NULL UNIQUE,
    blockchain_tx   TEXT,
    anchored_utc    REAL,
    anchored_block  INTEGER,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_merkle_root ON merkle_batches(merkle_root);
"""


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with _conn() as con:
        con.executescript(_SCHEMA)
    logger.info("DB initialised at %s", _DB_PATH)


# ---------------------------------------------------------------------------
# Decision CRUD
# ---------------------------------------------------------------------------

def _record_to_row(r: DecisionRecord) -> dict:
    return {
        "decision_id":            r.decision_id,
        "agent_id":               r.agent_id,
        "tier":                   r.tier.value,
        "timestamp_utc":          r.timestamp_utc,
        "incident_id":            r.incident_id,
        "shipment_ids":           json.dumps(r.shipment_ids),
        "carrier_id":             r.carrier_id,
        "warehouse_id":           r.warehouse_id,
        "raw_inputs":             json.dumps(r.raw_inputs),
        "model_name":             r.model_name,
        "model_version":          r.model_version,
        "prediction":             json.dumps(r.prediction),
        "confidence":             r.confidence,
        "calibrated_confidence":  r.calibrated_confidence,
        "ood_flag":               int(r.ood_flag),
        "shap_values":            json.dumps(r.shap_values),
        "top_features":           json.dumps(r.top_features),
        "counterfactual":         json.dumps(r.counterfactual),
        "reasoning_text":         r.reasoning_text,
        "stress_test_score":      r.stress_test_score,
        "stress_test_worst_case": r.stress_test_worst_case,
        "action":                 r.action,
        "action_params":          json.dumps(r.action_params),
        "action_reversible":      int(r.action_reversible),
        "rollback_deadline_utc":  r.rollback_deadline_utc,
        "outcome_actual":         json.dumps(r.outcome_actual),
        "outcome_predicted":      json.dumps(r.outcome_predicted),
        "outcome_delta":          r.outcome_delta,
        "fingerprint_hash":       r.fingerprint_hash,
        "anchor_status":          r.anchor_status.value,
        "merkle_batch_id":        r.merkle_batch_id,
        "merkle_proof":           json.dumps(r.merkle_proof),
        "merkle_root":            r.merkle_root,
        "blockchain_tx_hash":     r.blockchain_tx_hash,
        "blockchain_block":       r.blockchain_block,
        "agent_signature":        r.agent_signature,
        "schema_version":         r.schema_version,
    }


def _row_to_record(row: sqlite3.Row) -> DecisionRecord:
    d = dict(row)
    # Deserialise JSON fields
    for f in ("shipment_ids", "raw_inputs", "shap_values", "top_features",
              "counterfactual", "action_params", "merkle_proof",
              "prediction", "outcome_actual", "outcome_predicted"):
        if d.get(f):
            d[f] = json.loads(d[f])
    d["ood_flag"]          = bool(d.get("ood_flag", 0))
    d["action_reversible"] = bool(d.get("action_reversible", 1))
    return DecisionRecord(**d)


def upsert_decision(record: DecisionRecord) -> None:
    """Insert or replace a decision record (idempotent)."""
    row = _record_to_row(record)
    cols   = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    updates = ", ".join(f"{k}=excluded.{k}" for k in row.keys() if k != "decision_id")

    sql = f"""
        INSERT INTO decision_log ({cols}) VALUES ({placeholders})
        ON CONFLICT(decision_id) DO UPDATE SET {updates}
    """
    with _conn() as con:
        con.execute(sql, row)


def upsert_many_decisions(records: List[DecisionRecord]) -> None:
    """Bulk upsert — used after a batch is anchored."""
    for r in records:
        upsert_decision(r)
    logger.info("Upserted %d decision records.", len(records))


def get_decision(decision_id: str) -> Optional[DecisionRecord]:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM decision_log WHERE decision_id = ?", (decision_id,)
        ).fetchone()
    return _row_to_record(row) if row else None


def get_pending_decisions() -> List[DecisionRecord]:
    """Fetch all decisions not yet anchored (for batch builder on restart)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM decision_log WHERE anchor_status IN ('pending','batched') ORDER BY timestamp_utc"
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def get_decisions_by_incident(incident_id: str) -> List[DecisionRecord]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM decision_log WHERE incident_id = ? ORDER BY timestamp_utc",
            (incident_id,),
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def get_recent_decisions(limit: int = 50) -> List[DecisionRecord]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM decision_log ORDER BY timestamp_utc DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_record(r) for r in rows]


def mark_tampered(decision_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE decision_log SET anchor_status = 'tampered' WHERE decision_id = ?",
            (decision_id,),
        )
    logger.error("Decision %s marked TAMPERED in DB.", decision_id)


# ---------------------------------------------------------------------------
# Batch CRUD
# ---------------------------------------------------------------------------

def upsert_batch(batch: MerkleBatch) -> None:
    init_db()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO merkle_batches
              (batch_id, created_utc, decision_ids, leaf_hashes, merkle_root,
               blockchain_tx, anchored_utc, anchored_block)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(batch_id) DO UPDATE SET
              blockchain_tx  = excluded.blockchain_tx,
              anchored_utc   = excluded.anchored_utc,
              anchored_block = excluded.anchored_block
            """,
            (
                batch.batch_id,
                batch.created_utc,
                json.dumps(batch.decision_ids),
                json.dumps(batch.leaf_hashes),
                batch.merkle_root,
                batch.blockchain_tx,
                batch.anchored_utc,
                batch.anchored_block,
            ),
        )


def get_batch(batch_id: str) -> Optional[MerkleBatch]:
    init_db()
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM merkle_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["decision_ids"] = json.loads(d["decision_ids"])
    d["leaf_hashes"]  = json.loads(d["leaf_hashes"])
    return MerkleBatch(**d)


def get_recent_batches(limit: int = 10) -> List[MerkleBatch]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM merkle_batches ORDER BY created_utc DESC LIMIT ?", (limit,)
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["decision_ids"] = json.loads(d["decision_ids"])
        d["leaf_hashes"]  = json.loads(d["leaf_hashes"])
        result.append(MerkleBatch(**d))
    return result

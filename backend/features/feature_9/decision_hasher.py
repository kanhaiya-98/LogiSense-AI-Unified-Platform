from __future__ import annotations
"""
Feature 9: Decision Hasher
SHA-256 fingerprinting of canonical DecisionRecord JSON.

Design principles:
- Deterministic: same record always produces same hash regardless of
  Python dict insertion order or float representation.
- Tamper-evident: re-computing hash on every read lets us catch drift.
- Schema-versioned: hash includes schema_version so future field changes
  don't silently break verification.
- secp256k1 agent signing: Actor Agent's Ethereum wallet signs each action,
  proving it was taken by the legitimate agent, not injected post-hoc.
"""



import hashlib
import json
import logging
from typing import Any, Dict

from eth_account import Account
from eth_account.messages import encode_defunct

from blockchain_models import DecisionRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------

def _canonical_json(record: DecisionRecord) -> str:
    """
    Produce deterministic JSON from a DecisionRecord.
    Rules:
      - Keys sorted alphabetically at every level.
      - No whitespace.
      - Floats rounded to 6 decimal places (avoids platform drift).
      - None values included as null (preserves field presence in hash).
    """
    raw: Dict[str, Any] = json.loads(record.model_dump_json())

    def _normalise(obj: Any) -> Any:
        if isinstance(obj, float):
            return round(obj, 6)
        if isinstance(obj, dict):
            return {k: _normalise(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_normalise(i) for i in obj]
        return obj

    normalised = _normalise(raw)
    return json.dumps(normalised, separators=(",", ":"), sort_keys=True)


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

def compute_hash(record: DecisionRecord) -> str:
    """
    Return the SHA-256 hex digest of the record's canonical JSON.
    Blockchain fields (fingerprint_hash, merkle_*, blockchain_*,
    agent_signature) are excluded from the hash input — they are
    written AFTER hashing and would create a chicken-and-egg problem.
    """
    # Exclude fields written by the blockchain pipeline itself
    exclude = {
        "fingerprint_hash",
        "anchor_status",
        "merkle_batch_id",
        "merkle_proof",
        "merkle_root",
        "blockchain_tx_hash",
        "blockchain_block",
        "agent_signature",
    }

    raw: Dict[str, Any] = json.loads(record.model_dump_json())
    payload = {k: v for k, v in raw.items() if k not in exclude}

    def _normalise(obj: Any) -> Any:
        if isinstance(obj, float):
            return round(obj, 6)
        if isinstance(obj, dict):
            return {k: _normalise(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_normalise(i) for i in obj]
        return obj

    normalised = _normalise(payload)
    canonical = json.dumps(normalised, separators=(",", ":"), sort_keys=True)

    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    logger.debug("Hashed decision %s -> %s", record.decision_id, digest[:16] + "...")
    return digest


def verify_hash(record: DecisionRecord) -> bool:
    """
    Re-compute the hash and compare with record.fingerprint_hash.
    Returns True if untampered, False if the record has been modified.
    """
    if not record.fingerprint_hash:
        logger.warning("Decision %s has no stored fingerprint.", record.decision_id)
        return False

    fresh = compute_hash(record)
    match = fresh == record.fingerprint_hash

    if not match:
        logger.error(
            "TAMPER DETECTED — decision %s: stored=%s computed=%s",
            record.decision_id,
            record.fingerprint_hash[:16],
            fresh[:16],
        )

    return match


# ---------------------------------------------------------------------------
# Agent signing (secp256k1 via eth_account)
# ---------------------------------------------------------------------------

def sign_decision(record: DecisionRecord, private_key: str) -> str:
    """
    Sign the decision's fingerprint_hash with the Actor Agent's private key.
    Returns the hex signature string.

    This proves the action was taken by the legitimate agent process
    (which holds the key), not injected into the DB post-hoc by a human.
    """
    if not record.fingerprint_hash:
        raise ValueError("Cannot sign a record without a fingerprint_hash.")

    msg = encode_defunct(text=record.fingerprint_hash)
    signed = Account.sign_message(msg, private_key=private_key)
    sig_hex = signed.signature.hex()
    logger.debug(
        "Signed decision %s with key ...%s", record.decision_id, private_key[-4:]
    )
    return sig_hex


def recover_signer(record: DecisionRecord) -> str:
    """
    Recover the Ethereum address that signed this decision.
    Useful for verifying the agent identity during audit.
    """
    if not record.fingerprint_hash or not record.agent_signature:
        raise ValueError("Record missing fingerprint_hash or agent_signature.")

    msg = encode_defunct(text=record.fingerprint_hash)
    address = Account.recover_message(msg, signature=bytes.fromhex(
        record.agent_signature.removeprefix("0x")
    ))
    return address


# ---------------------------------------------------------------------------
# Fingerprint + sign in one step (called by Actor Agent tools)
# ---------------------------------------------------------------------------

def fingerprint_and_sign(record: DecisionRecord, private_key: str) -> DecisionRecord:
    """
    Convenience wrapper used by blockchain_tools.log_and_fingerprint.
    1. Compute hash.
    2. Store in record.fingerprint_hash.
    3. Sign hash with agent key.
    4. Store signature in record.agent_signature.
    Returns the mutated record (Pydantic copy).
    """
    h = compute_hash(record)
    record = record.model_copy(update={"fingerprint_hash": h})
    sig = sign_decision(record, private_key)
    record = record.model_copy(update={"agent_signature": sig})
    return record

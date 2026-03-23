from __future__ import annotations
"""
Feature 9: Blockchain Models
Shared Pydantic types for the decision audit system.
These are injected into the LangGraph AgentState so every node
can read/write blockchain fields without coupling to this module.
"""

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AnchorStatus(str, Enum):
    PENDING   = "pending"    # hashed, queued for next Merkle batch
    BATCHED   = "batched"    # included in a Merkle tree, not yet on-chain
    ANCHORED  = "anchored"   # Merkle root confirmed on Polygon
    TAMPERED  = "tampered"   # re-computed hash does not match stored hash
    FAILED    = "failed"     # on-chain tx failed; retry queued


class TierLabel(str, Enum):
    AUTONOMOUS = "autonomous"
    SUPERVISED = "supervised"
    ESCALATED  = "escalated"


# ---------------------------------------------------------------------------
# Core decision record — every agent decision must produce one of these
# ---------------------------------------------------------------------------

class DecisionRecord(BaseModel):
    """
    Canonical record hashed by Feature 9.
    Every other feature (Observer, Reasoner, Actor, Learner) produces this
    structure.  The blockchain node consumes it.

    IMPORTANT: field order and names are part of the hash contract —
    do not rename without bumping schema_version.
    """
    schema_version:       str            = "1.0"
    decision_id:          str            # UUID4 set by the producing agent
    agent_id:             str            # e.g. "observer", "actor", "learner"
    tier:                 TierLabel
    timestamp_utc:        float          = Field(default_factory=time.time)

    # Inputs that drove the decision
    incident_id:          Optional[str]  = None
    shipment_ids:         List[str]      = Field(default_factory=list)
    carrier_id:           Optional[str]  = None
    warehouse_id:         Optional[str]  = None
    raw_inputs:           Dict[str, Any] = Field(default_factory=dict)

    # ML model outputs
    model_name:           Optional[str]  = None
    model_version:        Optional[str]  = None
    prediction:           Optional[Any]  = None
    confidence:           Optional[float]= None
    calibrated_confidence:Optional[float]= None
    ood_flag:             bool           = False

    # XAI (Feature 8)
    shap_values:          Dict[str, float] = Field(default_factory=dict)
    top_features:         List[str]        = Field(default_factory=list)
    counterfactual:       Optional[Dict]   = None

    # Reasoning (Reasoner Agent)
    reasoning_text:       Optional[str]   = None
    stress_test_score:    Optional[float] = None   # Red Team (Feature 5)
    stress_test_worst_case: Optional[str] = None

    # Action taken (Actor Agent)
    action:               Optional[str]   = None
    action_params:        Dict[str, Any]  = Field(default_factory=dict)
    action_reversible:    bool            = True
    rollback_deadline_utc:Optional[float] = None

    # Outcome (Learner Agent — back-filled after resolution)
    outcome_actual:       Optional[Any]   = None
    outcome_predicted:    Optional[Any]   = None
    outcome_delta:        Optional[float] = None

    # Blockchain fields (written by Feature 9)
    fingerprint_hash:     Optional[str]   = None   # SHA-256 hex
    anchor_status:        AnchorStatus    = AnchorStatus.PENDING
    merkle_batch_id:      Optional[str]   = None
    merkle_proof:         List[str]       = Field(default_factory=list)
    merkle_root:          Optional[str]   = None
    blockchain_tx_hash:   Optional[str]   = None
    blockchain_block:     Optional[int]   = None
    agent_signature:      Optional[str]   = None   # secp256k1 sig


# ---------------------------------------------------------------------------
# Merkle batch record
# ---------------------------------------------------------------------------

class MerkleBatch(BaseModel):
    batch_id:         str
    created_utc:      float = Field(default_factory=time.time)
    decision_ids:     List[str]
    leaf_hashes:      List[str]
    merkle_root:      str
    blockchain_tx:    Optional[str] = None
    anchored_utc:     Optional[float] = None
    anchored_block:   Optional[int]   = None


# ---------------------------------------------------------------------------
# Verification result — returned to any agent or API caller
# ---------------------------------------------------------------------------

class VerificationResult(BaseModel):
    decision_id:      str
    verified:         bool
    reason:           str          # human-readable explanation
    stored_hash:      Optional[str] = None
    computed_hash:    Optional[str] = None
    on_chain_root:    Optional[str] = None
    proof_valid:      Optional[bool]= None
    blockchain_tx:    Optional[str] = None
    polygonscan_url:  Optional[str] = None


# ---------------------------------------------------------------------------
# LangGraph state extension
# All other agent nodes should include these fields in their AgentState TypedDict.
# ---------------------------------------------------------------------------

class BlockchainState(BaseModel):
    """
    Slice of AgentState owned by Feature 9.
    Merge this into your graph's AgentState TypedDict like:

        class AgentState(TypedDict):
            ...
            blockchain: BlockchainStateDict   # use .dict() to serialise

    Or if using a dataclass-based state, embed the fields directly.
    """
    pending_decisions:    List[DecisionRecord] = Field(default_factory=list)
    latest_batch:         Optional[MerkleBatch] = None
    tamper_alerts:        List[str]             = Field(default_factory=list)
    anchoring_enabled:    bool                  = True   # can be toggled in tests

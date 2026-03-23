from __future__ import annotations
"""
Feature 9: Tests
Run with:  pytest tests/test_feature9.py -v

These tests cover all core logic without requiring a live Polygon connection.
The PolygonClient is mocked where needed.
"""


import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
import blockchain_tools as blockchain_tools
import feature_9.db as db

from blockchain_models import AnchorStatus, DecisionRecord, TierLabel
from decision_hasher import compute_hash, fingerprint_and_sign, verify_hash, recover_signer
from merkle_tree import (
    build_merkle_tree,
    generate_proof,
    verify_proof,
    build_batch,
    attach_proofs_to_decisions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_decision(**overrides) -> DecisionRecord:
    base = {
        "decision_id":  str(uuid.uuid4()),
        "agent_id":     "actor",
        "tier":         TierLabel.AUTONOMOUS,
        "incident_id":  "INC-001",
        "shipment_ids": ["SHP-001", "SHP-002"],
        "carrier_id":   "CAR-07",
        "model_name":   "delay_classifier",
        "model_version":"v1.2",
        "prediction":   0.87,
        "confidence":   0.91,
        "shap_values":  {"carrier_drift_score": 0.45, "on_time_rate": -0.31},
        "reasoning_text": "CAR-07 has degraded 3 days. Swapping to CAR-11.",
        "action":       "swap_carrier",
        "action_params": {"new_carrier_id": "CAR-11"},
        "stress_test_score": 0.85,
    }
    base.update(overrides)
    return DecisionRecord(**base)


# ---------------------------------------------------------------------------
# Decision Hasher Tests
# ---------------------------------------------------------------------------

class TestDecisionHasher:

    def test_hash_is_deterministic(self):
        import feature_9.db as db
        db.init_db()
        d = make_decision()
        h1 = compute_hash(d)
        h2 = compute_hash(d)
        assert h1 == h2

    def test_hash_changes_when_field_mutated(self):
        import feature_9.db as db
        db.init_db()
        d = make_decision()
        h1 = compute_hash(d)
        d2 = d.model_copy(update={"action": "reroute_shipment"})
        h2 = compute_hash(d2)
        assert h1 != h2

    def test_blockchain_fields_excluded_from_hash(self):
        import feature_9.db as db
        db.init_db()
        """Blockchain-written fields must not affect the hash."""
        d = make_decision()
        h1 = compute_hash(d)
        d2 = d.model_copy(update={
            "fingerprint_hash": "abc123",
            "anchor_status":    AnchorStatus.ANCHORED,
            "blockchain_tx_hash": "0xdeadbeef",
        })
        h2 = compute_hash(d2)
        assert h1 == h2, "Blockchain fields should be excluded from hash input"

    def test_verify_hash_passes_for_untampered(self):
        import feature_9.db as db
        db.init_db()
        d = make_decision()
        h = compute_hash(d)
        d = d.model_copy(update={"fingerprint_hash": h})
        assert verify_hash(d) is True

    def test_verify_hash_fails_for_tampered(self):
        import feature_9.db as db
        db.init_db()
        d = make_decision()
        h = compute_hash(d)
        d = d.model_copy(update={"fingerprint_hash": h, "action": "INJECTED_ACTION"})
        assert verify_hash(d) is False

    def test_agent_signing_and_recovery(self):
        import feature_9.db as db
        db.init_db()
        # Use a deterministic test private key (never use in prod)
        test_key = "0x" + "a" * 64
        d = make_decision()
        h = compute_hash(d)
        d = d.model_copy(update={"fingerprint_hash": h})
        signed = fingerprint_and_sign(d, test_key)

        assert signed.agent_signature is not None
        recovered = recover_signer(signed)
        # Should recover the address corresponding to test_key
        from eth_account import Account
        expected = Account.from_key(test_key).address
        assert recovered.lower() == expected.lower()

    def test_shap_values_in_hash(self):
        import feature_9.db as db
        db.init_db()
        """SHAP values must be included in hash so explanation is tamper-proof."""
        d = make_decision()
        h1 = compute_hash(d)
        d2 = d.model_copy(update={"shap_values": {"carrier_drift_score": 0.99}})
        h2 = compute_hash(d2)
        assert h1 != h2, "Modifying SHAP values should change the hash"


# ---------------------------------------------------------------------------
# Merkle Tree Tests
# ---------------------------------------------------------------------------

class TestMerkleTree:

    def test_single_leaf(self):
        import feature_9.db as db
        db.init_db()
        hashes = ["a" * 64]
        root, levels = build_merkle_tree(hashes)
        assert len(root) == 64
        assert len(levels) == 1   # root is the leaf

    def test_two_leaves(self):
        import feature_9.db as db
        db.init_db()
        hashes = ["a" * 64, "b" * 64]
        root, _ = build_merkle_tree(hashes)
        assert len(root) == 64

    def test_odd_leaf_count_padded(self):
        import feature_9.db as db
        db.init_db()
        hashes = ["a" * 64, "b" * 64, "c" * 64]
        root, _ = build_merkle_tree(hashes)
        assert len(root) == 64

    def test_proof_verify_round_trip(self):
        import feature_9.db as db
        db.init_db()
        import feature_9.db as db
        db.init_db()
        hashes = [compute_hash(make_decision()) for _ in range(7)]
        root, _ = build_merkle_tree(hashes)

        for idx in range(len(hashes)):
            proof = generate_proof(hashes, idx)
            assert verify_proof(hashes[idx], proof, root), f"Proof failed for leaf {idx}"

    def test_proof_fails_for_wrong_leaf(self):
        import feature_9.db as db
        db.init_db()
        import feature_9.db as db
        db.init_db()
        hashes = [compute_hash(make_decision()) for _ in range(4)]
        root, _ = build_merkle_tree(hashes)
        proof = generate_proof(hashes, 0)
        # Use wrong leaf hash
        assert not verify_proof("f" * 4 + "0" * 60, proof, root)

    def test_proof_fails_for_wrong_root(self):
        import feature_9.db as db
        db.init_db()
        import feature_9.db as db
        db.init_db()
        hashes = [compute_hash(make_decision()) for _ in range(4)]
        root, _ = build_merkle_tree(hashes)
        proof = generate_proof(hashes, 0)
        assert not verify_proof(hashes[0], proof, "f" * 4 + "0" * 60)

    def test_build_batch_assigns_ids(self):
        import feature_9.db as db
        db.init_db()
        import feature_9.db as db
        db.init_db()
        decisions = [make_decision() for _ in range(5)]
        for d in decisions:
            h = compute_hash(d)
            d.__dict__["fingerprint_hash"] = h  # simulate fingerprinting

        # Properly copy with fingerprints
        fp_decisions = []
        for d in decisions:
            h = compute_hash(d)
            fp_decisions.append(d.model_copy(update={"fingerprint_hash": h}))

        batch = build_batch(fp_decisions)
        assert len(batch.decision_ids) == 5
        assert len(batch.leaf_hashes) == 5
        assert batch.merkle_root is not None

    def test_attach_proofs(self):
        import feature_9.db as db
        db.init_db()
        import feature_9.db as db
        db.init_db()
        decisions = []
        for _ in range(4):
            d = make_decision()
            h = compute_hash(d)
            decisions.append(d.model_copy(update={"fingerprint_hash": h}))

        batch = build_batch(decisions)
        updated = attach_proofs_to_decisions(decisions, batch)

        for d in updated:
            assert d.merkle_proof is not None
            assert len(d.merkle_proof) > 0
            assert d.merkle_batch_id == batch.batch_id
            assert d.merkle_root == batch.merkle_root

    def test_proof_valid_after_attach(self):
        import feature_9.db as db
        db.init_db()
        import feature_9.db as db
        db.init_db()
        decisions = []
        for _ in range(6):
            d = make_decision()
            h = compute_hash(d)
            decisions.append(d.model_copy(update={"fingerprint_hash": h}))

        batch = build_batch(decisions)
        updated = attach_proofs_to_decisions(decisions, batch)

        for d in updated:
            assert verify_proof(
                d.fingerprint_hash,
                d.merkle_proof,
                batch.merkle_root,
            ), f"Proof verification failed for {d.decision_id}"

    def test_empty_batch_raises(self):
        import feature_9.db as db
        db.init_db()
        with pytest.raises(ValueError):
            build_batch([])


# ---------------------------------------------------------------------------
# Blockchain Node (mocked chain) Tests
# ---------------------------------------------------------------------------

class TestBlockchainNode:

    def _make_state(self, new_decision=None):
        return {
            "new_decision":     new_decision,
            "pending_decisions": [],
            "blockchain_status": {},
            "tamper_alerts":    [],
            "messages":         [],
        }

    def test_node_fingerprints_new_decision(self):
        db.init_db()
        from blockchain_node import BlockchainNodeRunner
        

        # Reset module queue
        blockchain_tools._pending_decisions.clear()

        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        runner = BlockchainNodeRunner(client=mock_client)
        runner.private_key = ""

        d = make_decision()
        state = self._make_state(new_decision=d.model_dump())
        patch_result = runner(state)

        assert patch_result["new_decision"] is None
        assert patch_result["latest_decision"] is not None
        assert patch_result["latest_decision"]["fingerprint_hash"] is not None

    def test_tamper_alert_raised_for_corrupted_queued_decision(self):
        db.init_db()
        from blockchain_node import BlockchainNodeRunner
        

        blockchain_tools._pending_decisions.clear()

        mock_client = MagicMock()
        mock_client.is_connected.return_value = False
        runner = BlockchainNodeRunner(client=mock_client)
        runner.private_key = ""

        # Create a properly fingerprinted decision
        d = make_decision()
        h = compute_hash(d)
        d = d.model_copy(update={"fingerprint_hash": h})

        # Now corrupt its action (simulates DB tampering between turns)
        corrupted = d.model_copy(update={"action": "INJECTED"})

        state = self._make_state()
        state["pending_decisions"] = [corrupted.model_dump()]
        patch_result = runner(state)

        assert len(patch_result["tamper_alerts"]) > 0
        assert "TAMPER" in patch_result["tamper_alerts"][0]

    def test_node_flushes_when_threshold_met(self):
        db.init_db()
        from blockchain_node import BlockchainNodeRunner, BATCH_SIZE_THRESHOLD

        blockchain_tools._pending_decisions.clear()

        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.anchor_batch.return_value = "0x" + "a" * 64
        mock_client.w3.eth.get_transaction_receipt.return_value = MagicMock(blockNumber=12345)
        mock_client.tx_url.return_value = "https://amoy.polygonscan.com/tx/0xaaa"
        runner = BlockchainNodeRunner(client=mock_client)
        runner.private_key = "0x" + "a" * 64

        # Fill the queue to threshold
        for _ in range(BATCH_SIZE_THRESHOLD):
            d = make_decision()
            h = compute_hash(d)
            blockchain_tools._pending_decisions.append(
                d.model_copy(update={"fingerprint_hash": h})
            )

        state = self._make_state()
        patch_result = runner(state)

        assert mock_client.anchor_batch.called
        status = patch_result["blockchain_status"]
        assert status["last_batch"] is not None
        assert status["last_batch"]["ok"] is True


# ---------------------------------------------------------------------------
# Integration smoke test
# ---------------------------------------------------------------------------

class TestIntegration:
    """
    Simulates the full pipeline: produce decision -> fingerprint ->
    build batch -> attach proofs -> verify.
    No live chain needed.
    """

    def test_full_pipeline_no_chain(self):
        import feature_9.db as db
        db.init_db()
        import db
        db.init_db()
        # 1. Produce decisions (as Actor Agent would)
        decisions = []
        for i in range(10):
            d = make_decision(
                decision_id = str(uuid.uuid4()),
                action = f"swap_carrier_{i}",
                agent_id = "actor",
            )
            # 2. Fingerprint (as blockchain node would)
            h = compute_hash(d)
            d = d.model_copy(update={"fingerprint_hash": h})
            assert verify_hash(d)
            decisions.append(d)

        # 3. Build batch
        batch = build_batch(decisions)
        assert batch.merkle_root

        # 4. Attach proofs
        updated = attach_proofs_to_decisions(decisions, batch)

        # 5. Verify each decision's proof
        for d in updated:
            ok = verify_proof(d.fingerprint_hash, d.merkle_proof, batch.merkle_root)
            assert ok, f"Proof failed for {d.decision_id}"

        # 6. Tamper with one and confirm it fails
        tampered = updated[3].model_copy(update={"action": "EVIL_ACTION"})
        tampered_hash = compute_hash(tampered)
        bad = verify_proof(tampered_hash, tampered.merkle_proof, batch.merkle_root)
        assert not bad, "Tampered decision should fail Merkle verification"

        print(f"\n✅ Pipeline OK: {len(decisions)} decisions, root={batch.merkle_root[:16]}…")

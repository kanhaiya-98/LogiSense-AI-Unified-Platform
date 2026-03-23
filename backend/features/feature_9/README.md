# Feature 9: Tamper-Proof Decision Audit
## Blockchain Anchoring — Integration Guide

---

### What this feature does

Every agent decision is:
1. **SHA-256 fingerprinted** at the moment of creation — inputs, model version, SHAP values, reasoning, action, timestamp all hashed together
2. **secp256k1 signed** by the Actor Agent's wallet — proves it was the agent, not a human post-hoc insertion
3. **Merkle batched** hourly into a binary tree
4. **Anchored on Polygon Amoy** via `DecisionAnchor.sol` — permissionlessly verifiable by any party without login

Modifying any field in any decision instantly breaks its hash. The Merkle proof also breaks if the batch was tampered with.

---

### File map

```
feature9_blockchain/
├── blockchain_models.py      # Pydantic types: DecisionRecord, MerkleBatch, etc.
├── decision_hasher.py        # SHA-256 fingerprinting + secp256k1 signing
├── merkle_tree.py            # Binary Merkle tree, proof gen/verify
├── smart_contract.py         # web3.py client for Polygon + DecisionAnchor.sol
├── blockchain_tools.py       # LangChain @tool functions (MCP-style)
├── blockchain_node.py        # LangGraph node — the main integration point
├── contracts/
│   └── DecisionAnchor.sol    # Solidity contract (deploy once)
├── tests/
│   └── test_feature9.py      # Full test suite (no live chain needed)
└── requirements_f9.txt
```

---

### AgentState contract

Add these fields to your graph's `AgentState` TypedDict:

```python
class AgentState(TypedDict):
    # ... your existing fields ...

    # Written by any agent that makes a decision (Observer, Reasoner, Actor, Learner)
    new_decision:        dict | None      # DecisionRecord as dict — consumed by blockchain node

    # Maintained by blockchain node
    pending_decisions:   list             # List[DecisionRecord as dict]
    latest_decision:     dict | None      # Most recently fingerprinted record
    blockchain_status:   dict             # Summary for dashboard
    tamper_alerts:       list             # List[str] — raised on hash mismatch
```

---

### Wiring into your LangGraph graph

```python
from blockchain_node import add_blockchain_to_graph
from blockchain_tools import BLOCKCHAIN_TOOLS

# In your graph builder:
bc_runner = add_blockchain_to_graph(graph, route_back_to="observer")

# Connect from nodes that produce decisions:
graph.add_edge("actor",   "blockchain")
graph.add_edge("learner", "blockchain")

# If Actor Agent uses tools, add blockchain tools to its tool list:
actor_tools = [...your existing tools..., *BLOCKCHAIN_TOOLS]
```

---

### How other agents produce a DecisionRecord

Every agent that makes a decision should emit it via `state["new_decision"]`.
Example from Actor Agent:

```python
from blockchain_models import DecisionRecord, TierLabel
import uuid, time

def actor_node(state):
    # ... do the carrier swap ...

    decision = DecisionRecord(
        decision_id   = str(uuid.uuid4()),
        agent_id      = "actor",
        tier          = TierLabel.AUTONOMOUS,
        incident_id   = state["incident_id"],
        shipment_ids  = state["affected_shipments"],
        carrier_id    = state["old_carrier"],
        model_name    = "carrier_reliability",
        model_version = state["model_version"],
        confidence    = state["confidence"],
        calibrated_confidence = state["calibrated_confidence"],
        shap_values   = state["shap_values"],          # from Feature 8
        reasoning_text = state["reasoning_text"],
        action        = "swap_carrier",
        action_params = {"new_carrier_id": "CAR-11"},
        stress_test_score = state["stress_test_score"], # from Feature 5
    )

    return {
        "new_decision": decision.model_dump(),   # blockchain node picks this up
        # ... rest of your state patch ...
    }
```

The blockchain node automatically fingerprints, signs, queues, and (hourly) anchors it.

---

### Verification endpoint

```python
from blockchain_node import verify_decision_record
from blockchain_models import DecisionRecord

# In your FastAPI handler:
@app.get("/verify/{decision_id}")
async def verify(decision_id: str):
    record = db.get_decision(decision_id)  # fetch from your DB
    result = verify_decision_record(DecisionRecord(**record))
    return result
    # Returns: {"verified": bool, "reason": str, "polygonscan_url": str, ...}
```

---

### Demo flow (Feature 9 segment, ~30 seconds)

1. Pull a decision from the audit log UI tab
2. Click "Verify" → hash check passes, Merkle proof valid, Polygonscan link shown
3. Open Polygonscan — show the anchored Merkle root
4. In the console, call `tamper_demo` tool: change one character in the record
5. Hash breaks instantly — "The blockchain says otherwise"
6. "Any partner, regulator, or auditor can verify this. No login required. No trust required."

---

### Environment variables (already in your .env)

```
POLYGON_RPC_URL=https://rpc-amoy.polygon.technology
POLYGON_CHAIN_ID=80002
POLYGON_PRIVATE_KEY=<your key>
POLYGON_CONTRACT_ADDRESS=0xd9145CCE52D386f254917e481eB44e9943F39138
```

The contract at `POLYGON_CONTRACT_ADDRESS` **must be deployed** from `contracts/DecisionAnchor.sol` before running. If the address is already deployed and functional, the system will use it directly.

---

### Running tests

```bash
cd feature9_blockchain
pip install -r requirements_f9.txt
pytest tests/test_feature9.py -v
```

All tests run without a live Polygon connection (chain calls are mocked).

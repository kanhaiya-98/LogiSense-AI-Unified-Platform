from __future__ import annotations
"""
Feature 9: Smart Contract Client
Handles all Polygon / Web3 interaction for DecisionAnchor.sol.

Uses your .env credentials:
  POLYGON_RPC_URL          = https://rpc-amoy.polygon.technology
  POLYGON_CHAIN_ID         = 80002
  POLYGON_PRIVATE_KEY      = <your key>
  POLYGON_CONTRACT_ADDRESS = 0xd9145CCE52D386f254917e481eB44e9943F39138

The contract ABI is embedded here so no external file is needed at runtime.
Gas estimate: ~21,000 per anchorBatch call (~$0.001 on Polygon).
"""



import logging
import os
import time
from typing import List, Optional

from web3 import Web3
from web3.exceptions import ContractLogicError, TransactionNotFound
from web3.middleware import ExtraDataToPOAMiddleware

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ABI for DecisionAnchor.sol
# Matches the contract in contracts/DecisionAnchor.sol
# ---------------------------------------------------------------------------

DECISION_ANCHOR_ABI = [
    {
        "inputs": [
            {"internalType": "bytes32", "name": "merkleRoot", "type": "bytes32"},
            {"internalType": "string",  "name": "batchId",    "type": "string"},
            {"internalType": "uint256", "name": "decisionCount", "type": "uint256"},
        ],
        "name": "anchorBatch",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32",   "name": "leafHash",  "type": "bytes32"},
            {"internalType": "bytes32[]", "name": "proof",     "type": "bytes32[]"},
            {"internalType": "bytes32",   "name": "root",      "type": "bytes32"},
        ],
        "name": "verifyDecision",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "pure",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "root", "type": "bytes32"},
        ],
        "name": "getRootInfo",
        "outputs": [
            {"internalType": "string",  "name": "batchId",       "type": "string"},
            {"internalType": "uint256", "name": "decisionCount", "type": "uint256"},
            {"internalType": "uint256", "name": "timestamp",     "type": "uint256"},
            {"internalType": "address", "name": "anchoredBy",    "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True,  "internalType": "bytes32", "name": "merkleRoot",    "type": "bytes32"},
            {"indexed": False, "internalType": "string",  "name": "batchId",       "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "decisionCount", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp",     "type": "uint256"},
        ],
        "name": "DecisionBatchAnchored",
        "type": "event",
    },
]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class PolygonClient:
    """
    Thin wrapper around web3.py for the DecisionAnchor contract.

    Instantiation is lazy — call connect() before any on-chain operations.
    This allows the rest of the system to import this module even when
    running tests that mock the chain.
    """

    def __init__(
        self,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        contract_address: Optional[str] = None,
        chain_id: Optional[int] = None,
    ):
        self.rpc_url          = rpc_url          or os.environ.get("POLYGON_RPC_URL", "")
        self.private_key      = private_key      or os.environ.get("POLYGON_PRIVATE_KEY", "")
        self.contract_address = contract_address or os.environ.get("POLYGON_CONTRACT_ADDRESS", "")
        self.chain_id         = chain_id         or int(os.environ.get("POLYGON_CHAIN_ID", "80002"))
        self.polygonscan_base = "https://amoy.polygonscan.com"

        self.w3:       Optional[Web3]    = None
        self.contract: Optional[object]  = None
        self.account:  Optional[object]  = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """
        Initialise Web3 connection.  Injects POA middleware required for
        Polygon (PoA chain, extra data in block headers).
        Returns True on success, False on failure (system continues without chain).
        """
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 30}))
            # Polygon Amoy is a PoA chain — must inject this middleware
            self.w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

            if not self.w3.is_connected():
                logger.error("Web3 not connected to %s", self.rpc_url)
                return False

            self.account = self.w3.eth.account.from_key(self.private_key)
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=DECISION_ANCHOR_ABI,
            )

            balance = self.w3.eth.get_balance(self.account.address)
            logger.info(
                "Connected to Polygon Amoy. Account: %s  Balance: %.6f MATIC",
                self.account.address,
                self.w3.from_wei(balance, "ether"),
            )
            return True

        except Exception as exc:
            logger.error("Polygon connection failed: %s", exc)
            return False

    def is_connected(self) -> bool:
        return self.w3 is not None and self.w3.is_connected()

    # ------------------------------------------------------------------
    # Anchor a Merkle root
    # ------------------------------------------------------------------

    def anchor_batch(
        self,
        merkle_root: str,
        batch_id: str,
        decision_count: int,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        Call anchorBatch() on DecisionAnchor.sol.
        Returns the transaction hash on success, None on failure.

        Gas strategy: uses web3's estimate_gas + 20% buffer so we don't
        overpay but also don't run out of gas on busy blocks.
        """
        if not self.is_connected():
            logger.error("Not connected to Polygon. Cannot anchor batch.")
            return None

        root_bytes = bytes.fromhex(merkle_root)

        for attempt in range(1, max_retries + 1):
            try:
                nonce = self.w3.eth.get_transaction_count(self.account.address)
                gas_price = self.w3.eth.gas_price

                # Build tx
                fn = self.contract.functions.anchorBatch(
                    root_bytes, batch_id, decision_count
                )
                estimated_gas = fn.estimate_gas({"from": self.account.address})
                gas_limit = int(estimated_gas * 1.2)

                tx = fn.build_transaction({
                    "chainId": self.chain_id,
                    "from":    self.account.address,
                    "nonce":   nonce,
                    "gas":     gas_limit,
                    "gasPrice": gas_price,
                })

                signed   = self.w3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash  = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt  = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

                if receipt.status == 1:
                    logger.info(
                        "Batch %s anchored. Root=%s  TX=%s  Block=%d",
                        batch_id[:8],
                        merkle_root[:16],
                        tx_hash.hex()[:16],
                        receipt.blockNumber,
                    )
                    return tx_hash.hex()
                else:
                    logger.error("TX reverted for batch %s (attempt %d).", batch_id, attempt)

            except Exception as exc:
                logger.warning("Anchor attempt %d failed: %s", attempt, exc)
                if attempt < max_retries:
                    time.sleep(2 ** attempt)   # exponential backoff

        return None

    # ------------------------------------------------------------------
    # On-chain proof verification
    # ------------------------------------------------------------------

    def verify_on_chain(
        self,
        leaf_hash: str,
        proof: List[str],
        root: str,
    ) -> bool:
        """
        Call verifyDecision() on the contract — pure function, no gas.
        Falls back to local Merkle proof verification if chain unavailable.
        """
        if not self.is_connected():
            logger.warning("Chain unavailable, falling back to local verification.")
            from merkle_tree import verify_proof
            return verify_proof(leaf_hash, proof, root)

        try:
            leaf_bytes  = bytes.fromhex(leaf_hash)
            proof_bytes = [bytes.fromhex(p) for p in proof]
            root_bytes  = bytes.fromhex(root)

            result = self.contract.functions.verifyDecision(
                leaf_bytes, proof_bytes, root_bytes
            ).call()
            return result

        except Exception as exc:
            logger.error("On-chain verification failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Query anchored root info
    # ------------------------------------------------------------------

    def get_root_info(self, merkle_root: str) -> Optional[dict]:
        """
        Fetch batch metadata stored on-chain for a given Merkle root.
        Returns dict or None if root not found.
        """
        if not self.is_connected():
            return None

        try:
            root_bytes = bytes.fromhex(merkle_root)
            batch_id, count, ts, anchored_by = self.contract.functions.getRootInfo(
                root_bytes
            ).call()

            return {
                "batch_id":      batch_id,
                "decision_count": count,
                "timestamp":     ts,
                "anchored_by":   anchored_by,
                "polygonscan_url": f"{self.polygonscan_base}/address/{self.contract_address}",
            }
        except Exception as exc:
            logger.error("getRootInfo failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Polygonscan URL helper (for dashboard)
    # ------------------------------------------------------------------

    def tx_url(self, tx_hash: str) -> str:
        return f"{self.polygonscan_base}/tx/{tx_hash}"

    def address_url(self) -> str:
        return f"{self.polygonscan_base}/address/{self.contract_address}"

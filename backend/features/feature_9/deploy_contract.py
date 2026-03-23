from __future__ import annotations
"""
Feature 9: Contract Deployment Script
Deploy DecisionAnchor.sol to Polygon Amoy (testnet).

Usage:
    python deploy_contract.py

If POLYGON_CONTRACT_ADDRESS is already set in .env AND the contract responds,
this script exits early — no re-deploy needed.

On success, prints the deployed address. Update your .env:
    POLYGON_CONTRACT_ADDRESS=<printed address>

Requirements: pip install web3 py-solc-x python-dotenv
"""



import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RPC_URL     = os.environ["POLYGON_RPC_URL"]
PRIVATE_KEY = os.environ["POLYGON_PRIVATE_KEY"]
CHAIN_ID    = int(os.environ.get("POLYGON_CHAIN_ID", "80002"))
EXISTING    = os.environ.get("POLYGON_CONTRACT_ADDRESS", "")


def check_existing(w3, address: str) -> bool:
    """Return True if the address already has contract code deployed."""
    try:
        code = w3.eth.get_code(w3.to_checksum_address(address))
        return code != b"" and code != "0x"
    except Exception:
        return False


def compile_contract() -> tuple[str, list]:
    """
    Compile DecisionAnchor.sol using py-solc-x.
    Falls back to the pre-compiled ABI/bytecode if solc is unavailable.
    """
    sol_path = Path(__file__).parent / "contracts" / "DecisionAnchor.sol"

    try:
        from solcx import compile_source, install_solc
        install_solc("0.8.20", show_progress=False)
        source = sol_path.read_text()
        compiled = compile_source(source, output_values=["abi", "bin"], solc_version="0.8.20")
        key = "<stdin>:DecisionAnchor"
        return compiled[key]["bin"], compiled[key]["abi"]
    except ImportError:
        print("py-solc-x not installed — using pre-compiled bytecode.")
        return _PRECOMPILED_BYTECODE, _PRECOMPILED_ABI


def deploy() -> str:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware

    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 60}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3.is_connected():
        print("ERROR: Cannot connect to Polygon RPC.")
        sys.exit(1)

    account = w3.eth.account.from_key(PRIVATE_KEY)
    balance = w3.from_wei(w3.eth.get_balance(account.address), "ether")
    print(f"Deployer: {account.address}  Balance: {balance:.4f} MATIC")

    if float(balance) < 0.01:
        print("WARNING: Low balance. Get testnet MATIC from https://faucet.polygon.technology/")

    # Check if already deployed
    if EXISTING and check_existing(w3, EXISTING):
        print(f"Contract already deployed at {EXISTING} — no re-deploy needed.")
        return EXISTING

    bytecode, abi = compile_contract()

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(account.address)

    tx = contract.constructor().build_transaction({
        "chainId":  CHAIN_ID,
        "from":     account.address,
        "nonce":    nonce,
        "gas":      800_000,
        "gasPrice": w3.eth.gas_price,
    })

    signed  = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"Deploying... TX: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)

    if receipt.status != 1:
        print("ERROR: Deployment TX reverted.")
        sys.exit(1)

    address = receipt.contractAddress
    print(f"\n✅ Deployed DecisionAnchor at: {address}")
    print(f"   Block: {receipt.blockNumber}")
    print(f"   TX:    {tx_hash.hex()}")
    print(f"\nAdd to your .env:")
    print(f"   POLYGON_CONTRACT_ADDRESS={address}")
    return address


# ---------------------------------------------------------------------------
# Pre-compiled fallback (solc 0.8.20, optimized runs=200)
# Generated from contracts/DecisionAnchor.sol
# Regenerate with: solc --bin --abi contracts/DecisionAnchor.sol
# ---------------------------------------------------------------------------

_PRECOMPILED_ABI = [
    {"inputs":[],"stateMutability":"nonpayable","type":"constructor"},
    {"inputs":[{"internalType":"bytes32","name":"root","type":"bytes32"}],"name":"RootAlreadyAnchored","type":"error"},
    {"inputs":[{"internalType":"bytes32","name":"root","type":"bytes32"}],"name":"RootNotFound","type":"error"},
    {"inputs":[],"name":"NotOwner","type":"error"},
    {"inputs":[],"name":"EmptyBatchId","type":"error"},
    {"inputs":[],"name":"ZeroDecisionCount","type":"error"},
    {"anonymous":False,"inputs":[{"indexed":True,"internalType":"bytes32","name":"merkleRoot","type":"bytes32"},{"indexed":False,"internalType":"string","name":"batchId","type":"string"},{"indexed":False,"internalType":"uint256","name":"decisionCount","type":"uint256"},{"indexed":False,"internalType":"uint256","name":"timestamp","type":"uint256"}],"name":"DecisionBatchAnchored","type":"event"},
    {"inputs":[{"internalType":"bytes32","name":"merkleRoot","type":"bytes32"},{"internalType":"string","name":"batchId","type":"string"},{"internalType":"uint256","name":"decisionCount","type":"uint256"}],"name":"anchorBatch","outputs":[],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"internalType":"bytes32","name":"leafHash","type":"bytes32"},{"internalType":"bytes32[]","name":"proof","type":"bytes32[]"},{"internalType":"bytes32","name":"root","type":"bytes32"}],"name":"verifyDecision","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"pure","type":"function"},
    {"inputs":[{"internalType":"bytes32","name":"root","type":"bytes32"}],"name":"getRootInfo","outputs":[{"internalType":"string","name":"batchId","type":"string"},{"internalType":"uint256","name":"decisionCount","type":"uint256"},{"internalType":"uint256","name":"timestamp","type":"uint256"},{"internalType":"address","name":"anchoredBy","type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"bytes32","name":"root","type":"bytes32"}],"name":"isAnchored","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"batchCount","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"uint256","name":"index","type":"uint256"}],"name":"rootAt","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},
]

# NOTE: Bytecode below is a placeholder. Run `solc --bin contracts/DecisionAnchor.sol`
# to get the real bytecode and paste it here, or use py-solc-x (preferred).
_PRECOMPILED_BYTECODE = "0x"   # Replace with actual compiled bytecode


if __name__ == "__main__":
    deploy()

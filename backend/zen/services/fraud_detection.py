from __future__ import annotations
"""Fraud Detection Service — copied from zenrto"""
import logging
from datetime import datetime
logger = logging.getLogger(__name__)

def detect_fraud_flags(buyer_id, pincode, order_value, payment_method, address_score, buyer_rto_rate, buyer_order_count, is_fraud_pincode, hour_of_day) -> list:
    flags = []
    if payment_method == "COD" and order_value > 3000:
        flags.append({"rule_id": "HIGH_VALUE_COD", "severity": "HIGH", "description": f"COD order value ₹{order_value:,.0f} exceeds ₹3,000 threshold"})
    if is_fraud_pincode:
        flags.append({"rule_id": "FRAUD_PINCODE", "severity": "HIGH", "description": f"Pincode {pincode} is on fraud watchlist"})
    if address_score < 0.40 and payment_method == "COD":
        flags.append({"rule_id": "POOR_ADDRESS_COD", "severity": "MEDIUM", "description": f"Low address quality ({address_score:.2f}) with COD"})
    if buyer_rto_rate > 0.40 and buyer_order_count > 3:
        flags.append({"rule_id": "REPEAT_RTO_BUYER", "severity": "HIGH", "description": f"Buyer RTO rate {buyer_rto_rate:.1%} across {buyer_order_count} orders"})
    if payment_method == "COD" and (hour_of_day >= 23 or hour_of_day <= 4):
        flags.append({"rule_id": "ODD_HOUR_COD", "severity": "LOW", "description": f"COD placed at unusual hour ({hour_of_day:02d}:xx)"})
    if buyer_order_count == 0 and payment_method == "COD" and order_value > 1500:
        flags.append({"rule_id": "NEW_BUYER_HIGH_COD", "severity": "MEDIUM", "description": f"First-time buyer with COD ₹{order_value:,.0f}"})
    return flags

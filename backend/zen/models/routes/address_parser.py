from __future__ import annotations
"""
Indian Address Parser & Completeness Scorer — copied from zenrto
"""
import re
import logging
logger = logging.getLogger(__name__)

LOCALITY_KEYWORDS = ["nagar", "colony", "vihar", "enclave", "sector", "phase", "layout", "extension", "road", "street", "marg", "path", "chowk", "bazaar", "gali", "lane", "cross", "main"]
BUILDING_KEYWORDS = ["flat", "apartment", "floor", "house", "bungalow", "villa", "plot", "shop", "office", "building", "tower", "complex", "society", "bhavan", "mansion"]

def score_address(address: str) -> float:
    if not address or len(address.strip()) < 5:
        return 0.1
    addr = address.lower().strip()
    score = 0.0
    if len(addr) >= 20: score += 1.0
    elif len(addr) >= 10: score += 0.5
    if re.search(r'\d+', addr): score += 1.0
    if re.search(r'\b[1-9]\d{5}\b', addr): score += 1.5
    if any(kw in addr for kw in LOCALITY_KEYWORDS): score += 1.0
    if any(kw in addr for kw in BUILDING_KEYWORDS): score += 0.5
    if addr.count(',') >= 2: score += 1.0
    elif ',' in addr: score += 0.5
    if address == address.upper() and len(address) < 30: score -= 0.5
    if re.search(r'(.)\1{4,}', addr): score -= 1.0
    return round(max(0.1, min(1.0, score / 6.0)), 4)

def extract_pincode(address: str) -> str | None:
    match = re.search(r'\b([1-9]\d{5})\b', address)
    return match.group(1) if match else None

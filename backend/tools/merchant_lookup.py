"""Rule-based merchant categorisation using a curated keyword dictionary."""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Load merchant mappings once at module level
_MERCHANTS_FILE = Path(__file__).parent.parent / "data" / "merchants.json"

_CATEGORY_KEYWORDS: dict[str, list[str]] = {}


def _load_merchants() -> None:
    """Load merchant keyword mappings from JSON file."""
    global _CATEGORY_KEYWORDS
    if _CATEGORY_KEYWORDS:
        return
    try:
        with open(_MERCHANTS_FILE, "r", encoding="utf-8") as f:
            _CATEGORY_KEYWORDS = json.load(f)
        total = sum(len(v) for v in _CATEGORY_KEYWORDS.values())
        logger.info("Loaded %d merchant keywords across %d categories", total, len(_CATEGORY_KEYWORDS))
    except FileNotFoundError:
        logger.error("merchants.json not found at %s", _MERCHANTS_FILE)
        _CATEGORY_KEYWORDS = {}


def lookup_merchant(description: str) -> Optional[dict]:
    """Look up a transaction description against merchant keyword rules.

    Args:
        description: Raw transaction description text.

    Returns:
        Dict with 'category', 'merchant', 'confidence' if matched, else None.
    """
    _load_merchants()

    desc_upper = description.upper().strip()

    for category, keywords in _CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in desc_upper:
                return {
                    "category": category,
                    "merchant": keyword.title(),
                    "confidence": 1.0,
                }

    return None


def get_all_categories() -> list[str]:
    """Return list of all available categories."""
    _load_merchants()
    return [cat for cat in _CATEGORY_KEYWORDS.keys() if cat != "Other"]

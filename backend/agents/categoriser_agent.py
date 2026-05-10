"""Two-layer categorisation: rule-based merchant lookup then LLM fallback.

Uses NVIDIA API (OpenAI-compatible) for LLM-based categorisation.
"""

import json
import logging
import re
import time
from typing import Any

from openai import OpenAI

from backend.config import settings
from backend.tools.merchant_lookup import lookup_merchant

logger = logging.getLogger(__name__)

_LLM_CATEGORISE_PROMPT = """Categorise each transaction into exactly one of these categories:
[Food & Dining, Groceries, Transport, Shopping, Entertainment, Health & Fitness,
Utilities, Finance & Insurance, Education, Salary, Business Income, ATM Withdrawal,
Bank Transfer, EMI & Loans, Subscriptions, Rent, Travel & Holidays, Other]

Transactions:
{transactions_json}

Return ONLY a JSON array with objects: {{"id": <index>, "category": "<category>", "confidence": <0.0-1.0>, "merchant_cleaned": "<cleaned merchant name>"}}
No explanation, no markdown."""

# Batch size for LLM categorisation
_BATCH_SIZE = 50


def _get_openai_client() -> OpenAI:
    """Create an OpenAI client configured for NVIDIA API."""
    return OpenAI(
        base_url=settings.NVIDIA_BASE_URL,
        api_key=settings.NVIDIA_API_KEY,
    )


def _call_llm_categorise(transactions_batch: list[dict]) -> list[dict]:
    """Send a batch of uncategorised transactions to the NVIDIA LLM.

    Args:
        transactions_batch: List of dicts with 'id' (index), 'description', 'amount'.

    Returns:
        List of dicts with 'id', 'category', 'confidence', 'merchant_cleaned'.
    """
    client = _get_openai_client()

    # Build slim transaction list for the prompt
    slim = [{"id": t["id"], "description": t["description"], "amount": t["amount"]} for t in transactions_batch]
    prompt = _LLM_CATEGORISE_PROMPT.format(transactions_json=json.dumps(slim))

    for attempt in range(settings.MAX_LLM_RETRIES):
        try:
            response = client.chat.completions.create(
                model=settings.NVIDIA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                top_p=0.9,
                max_tokens=4096,
            )
            text = response.choices[0].message.content.strip()

            # Strip markdown fences
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            results = json.loads(text)
            if not isinstance(results, list):
                raise ValueError("Response is not a JSON array")
            return results

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("LLM categorisation attempt %d failed (parse): %s", attempt + 1, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                time.sleep(settings.LLM_BACKOFF_BASE ** attempt)
        except Exception as e:
            logger.warning("LLM categorisation attempt %d failed: %s", attempt + 1, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                time.sleep(settings.LLM_BACKOFF_BASE ** attempt)

    logger.error("LLM categorisation failed after %d retries", settings.MAX_LLM_RETRIES)
    return []


async def categorise(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply two-layer categorisation to a list of transactions.

    Layer 1: Rule-based merchant keyword lookup (confidence 1.0).
    Layer 2: NVIDIA LLM fallback for unmatched transactions.

    Args:
        transactions: Raw transaction dicts with at least 'description' and 'amount'.

    Returns:
        Same transactions with 'category', 'merchant', 'confidence', 'needs_review' added.
    """
    unmatched_indices: list[int] = []

    # Layer 1: Rule-based lookup
    for i, txn in enumerate(transactions):
        # Use pre-extracted merchant name if available (from UPI parser),
        # otherwise fall back to the raw description
        lookup_text = txn.get("merchant") or txn.get("description", "")
        result = lookup_merchant(lookup_text)
        if not result:
            # Also try against the full description (catches non-UPI transactions)
            result = lookup_merchant(txn.get("description", ""))
        if result:
            txn["category"] = result["category"]
            txn["merchant"] = result["merchant"]
            txn["confidence"] = result["confidence"]
            txn["needs_review"] = False
        else:
            txn["category"] = "Other"
            txn["merchant"] = txn.get("merchant") or txn.get("description", "")[:50]
            txn["confidence"] = 0.0
            txn["needs_review"] = True
            unmatched_indices.append(i)

    matched_count = len(transactions) - len(unmatched_indices)
    logger.info(
        "Layer 1 (rules): %d/%d matched, %d need LLM",
        matched_count, len(transactions), len(unmatched_indices)
    )

    # Layer 2: LLM fallback for unmatched
    if unmatched_indices and settings.NVIDIA_API_KEY:
        # Process in batches
        for batch_start in range(0, len(unmatched_indices), _BATCH_SIZE):
            batch_indices = unmatched_indices[batch_start:batch_start + _BATCH_SIZE]
            batch = [
                {
                    "id": idx,
                    "description": transactions[idx]["description"],
                    "amount": transactions[idx]["amount"],
                }
                for idx in batch_indices
            ]

            results = _call_llm_categorise(batch)

            # Map results back to transactions
            results_map = {r["id"]: r for r in results if isinstance(r, dict) and "id" in r}
            for idx in batch_indices:
                if idx in results_map:
                    r = results_map[idx]
                    transactions[idx]["category"] = r.get("category", "Other")
                    confidence = float(r.get("confidence", 0.5))
                    transactions[idx]["confidence"] = confidence
                    transactions[idx]["needs_review"] = confidence < 0.7
                    if r.get("merchant_cleaned"):
                        transactions[idx]["merchant"] = r["merchant_cleaned"]

        gemini_categorised = sum(
            1 for i in unmatched_indices
            if transactions[i]["category"] != "Other"
        )
        logger.info("Layer 2 (LLM): categorised %d/%d unmatched", gemini_categorised, len(unmatched_indices))
    elif unmatched_indices:
        logger.warning("No NVIDIA API key — %d transactions remain uncategorised", len(unmatched_indices))

    return transactions

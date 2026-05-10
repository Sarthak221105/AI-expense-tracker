"""Recurring transaction detection using Pandas — no LLM involved."""

import logging
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Known frequency intervals in days and their labels
_FREQUENCY_MAP = {
    7: "weekly",
    14: "bi-weekly",
    30: "monthly",
    60: "bi-monthly",
    90: "quarterly",
    365: "annual",
}


def _fuzzy_group_key(merchant: str) -> str:
    """Normalize merchant name for grouping similar entries.

    Simple normalization that handles cases like 'NETFLIX INDIA' vs 'NETFLIX'.
    Uses first significant word matching instead of full fuzzy library to avoid
    the heavy fuzzywuzzy dependency while still being effective.
    """
    normalized = merchant.upper().strip()
    # Remove common suffixes
    for suffix in [" INDIA", " IN", " PVT", " LTD", " PRIVATE", " LIMITED", " INC"]:
        normalized = normalized.replace(suffix, "")
    # Remove extra whitespace
    normalized = " ".join(normalized.split())
    return normalized


def detect(transactions: list[dict]) -> list[dict]:
    """Detect recurring subscriptions among transactions.

    Step 1: Group by normalized merchant name.
    Step 2: Check interval consistency and amount variance.
    Step 3: Mark matching transactions as is_subscription=True.

    Args:
        transactions: List of transaction dicts (must have merchant, amount, date, type).

    Returns:
        Same list with is_subscription flags updated.
    """
    if not transactions:
        return transactions

    df = pd.DataFrame(transactions)

    # Only look at debits for subscriptions
    debits = df[df["type"] == "debit"].copy()
    if debits.empty:
        return transactions

    # Parse dates
    debits["parsed_date"] = pd.to_datetime(debits["date"], errors="coerce")
    debits = debits.dropna(subset=["parsed_date"])

    if debits.empty:
        return transactions

    # Add normalized merchant key for grouping
    debits["group_key"] = debits["merchant"].apply(_fuzzy_group_key)

    subscription_merchants: set[str] = set()

    for group_key, group in debits.groupby("group_key"):
        if len(group) < 2:
            continue

        # Sort by date
        group = group.sort_values("parsed_date")

        # Calculate intervals between consecutive transactions (in days)
        intervals = group["parsed_date"].diff().dt.days.dropna()

        if intervals.empty:
            continue

        median_interval = intervals.median()

        # Check if median interval is close to a known frequency
        matched_frequency = None
        for days, freq_name in _FREQUENCY_MAP.items():
            if abs(median_interval - days) <= 3:
                matched_frequency = freq_name
                break

        if not matched_frequency:
            continue

        # Check amount consistency: coefficient of variation < 10%
        amounts = group["amount"]
        if amounts.mean() > 0:
            cv = amounts.std() / amounts.mean()  # coefficient of variation
            if cv > 0.10:
                continue

        # This group qualifies as a subscription
        for original_merchant in group["merchant"].unique():
            subscription_merchants.add(original_merchant)

        logger.info(
            "Detected subscription: %s (%s, avg ₹%.2f)",
            group_key, matched_frequency, amounts.mean()
        )

    # Mark transactions in the original list
    for txn in transactions:
        if txn.get("merchant", "") in subscription_merchants:
            txn["is_subscription"] = True

    marked_count = sum(1 for t in transactions if t.get("is_subscription"))
    logger.info("Marked %d transactions as subscriptions", marked_count)

    return transactions


def get_subscription_summary(transactions: list[dict]) -> list[dict]:
    """Build a summary of all detected subscriptions.

    Args:
        transactions: List of transaction dicts with is_subscription flags.

    Returns:
        List of subscription summaries with merchant, amount, frequency, annual_cost.
    """
    subs = [t for t in transactions if t.get("is_subscription") and t.get("type") == "debit"]
    if not subs:
        return []

    df = pd.DataFrame(subs)
    df["parsed_date"] = pd.to_datetime(df["date"], errors="coerce")
    df["group_key"] = df["merchant"].apply(_fuzzy_group_key)

    summaries = []

    for group_key, group in df.groupby("group_key"):
        group = group.sort_values("parsed_date")

        avg_amount = round(group["amount"].mean(), 2)
        last_charged = None
        if not group["parsed_date"].isna().all():
            last_date = group["parsed_date"].max()
            last_charged = last_date.date().isoformat() if pd.notna(last_date) else None

        # Determine frequency from intervals
        frequency = "monthly"  # default
        annual_multiplier = 12
        if len(group) >= 2:
            intervals = group["parsed_date"].diff().dt.days.dropna()
            if not intervals.empty:
                median_interval = intervals.median()
                for days, freq_name in _FREQUENCY_MAP.items():
                    if abs(median_interval - days) <= 3:
                        frequency = freq_name
                        annual_multiplier = 365 / days
                        break

        # Annual cost projection
        annual_cost = round(avg_amount * annual_multiplier, 2)

        summaries.append({
            "merchant": group["merchant"].iloc[0],
            "amount": avg_amount,
            "frequency": frequency,
            "annual_cost": annual_cost,
            "last_charged": last_charged,
        })

    return summaries

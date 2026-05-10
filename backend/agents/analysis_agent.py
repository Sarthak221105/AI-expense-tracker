"""Monthly summary calculation — all arithmetic in Pandas, never LLM."""

import json
import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def calculate_monthly_summary(
    transactions: list[dict],
    statement_id: str,
    user_id: str,
    month: int,
    year: int,
) -> dict[str, Any]:
    """Calculate aggregated monthly financial summary from transactions.

    All calculations are done in Pandas. No LLM is involved.

    Args:
        transactions: List of categorised transaction dicts.
        statement_id: FK to the statement record.
        user_id: The user this summary belongs to.
        month: Statement month (1-12).
        year: Statement year.

    Returns:
        Dict matching the monthly_summaries DB schema fields.
    """
    df = pd.DataFrame(transactions)

    # Ensure all expected columns exist with safe defaults
    # (LLM-parsed transactions may omit optional fields)
    if "is_subscription" not in df.columns:
        df["is_subscription"] = False
    else:
        df["is_subscription"] = df["is_subscription"].fillna(False)

    if "needs_review" not in df.columns:
        df["needs_review"] = False
    else:
        df["needs_review"] = df["needs_review"].fillna(False)

    if "category" not in df.columns:
        df["category"] = "Other"
    else:
        df["category"] = df["category"].fillna("Other")

    if "merchant" not in df.columns:
        df["merchant"] = df.get("description", "Unknown")
    else:
        df["merchant"] = df["merchant"].fillna(df.get("description", "Unknown"))

    debits = df[df["type"] == "debit"]
    credits = df[df["type"] == "credit"]

    # Exclude pure bank-to-bank transfers from income/expense totals.
    # Transfers appear as both a credit AND a debit which artificially inflates both figures.
    _TRANSFER_CATS = {"Bank Transfer", "ATM Withdrawal"}
    real_credits = credits[~credits["category"].isin(_TRANSFER_CATS)]
    real_debits = debits[~debits["category"].isin(_TRANSFER_CATS)]

    # Core totals (transfers excluded)
    total_income = round(float(real_credits["amount"].sum()), 2) if not real_credits.empty else 0.0
    total_expenses = round(float(real_debits["amount"].sum()), 2) if not real_debits.empty else 0.0

    # Net savings = income minus expenses
    net_savings = round(total_income - total_expenses, 2)

    # Savings rate as percentage of income
    savings_rate = round((net_savings / total_income * 100), 2) if total_income > 0 else 0.0

    # Category breakdown (real debits only — spending categories, no transfers)
    category_breakdown: dict[str, float] = {}
    if not real_debits.empty:
        category_breakdown = (
            real_debits.groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
            .round(2)
            .to_dict()
        )

    top_category = max(category_breakdown, key=category_breakdown.get) if category_breakdown else "N/A"

    # Subscription totals
    subs = df[df["is_subscription"] == True]  # noqa: E712
    subscription_total = round(float(subs["amount"].sum()), 2) if not subs.empty else 0.0
    subscription_list: dict[str, float] = {}
    if not subs.empty:
        subscription_list = (
            subs.groupby("merchant")["amount"]
            .sum()
            .round(2)
            .to_dict()
        )

    # Unusual transactions: amount > 3x category average
    unusual: list[dict] = []
    if not debits.empty:
        for cat, group in debits.groupby("category"):
            avg = group["amount"].mean()
            if avg <= 0:
                continue
            high_txns = group[group["amount"] > avg * 3]
            for _, row in high_txns.iterrows():
                unusual.append({
                    "merchant": row["merchant"],
                    "amount": round(float(row["amount"]), 2),
                    "category": cat,
                    "category_avg": round(float(avg), 2),
                    "times_above_avg": round(float(row["amount"] / avg), 1),
                })

    # Financial health score (pure formula — no LLM)
    score = 100

    # Savings rate penalty
    if savings_rate < 10:
        score -= 30
    elif savings_rate < 20:
        score -= 15
    elif savings_rate < 30:
        score -= 5

    # Subscription burden penalty (subscriptions as % of income)
    sub_pct = (subscription_total / total_income * 100) if total_income > 0 else 0
    if sub_pct > 20:
        score -= 20
    elif sub_pct > 15:
        score -= 10
    elif sub_pct > 10:
        score -= 5

    # Unusual transaction penalty (capped at 20 points)
    score -= min(len(unusual) * 5, 20)

    # Uncategorised / low-confidence penalty
    needs_review_count = len(df[df["needs_review"] == True])  # noqa: E712
    if needs_review_count > 10:
        score -= 5

    health_score = max(min(score, 100), 0)

    summary = {
        "statement_id": statement_id,
        "user_id": user_id,
        "month": month,
        "year": year,
        "total_income": total_income,
        "total_expenses": total_expenses,
        "net_savings": net_savings,
        "savings_rate": savings_rate,
        "top_category": top_category,
        "category_breakdown": json.dumps(category_breakdown),
        "subscription_total": subscription_total,
        "subscription_list": json.dumps(subscription_list),
        "unusual_transactions": json.dumps(unusual),
        "health_score": health_score,
    }

    logger.info(
        "Monthly summary for %d/%d: income=%.2f, expenses=%.2f, savings=%.2f (%.1f%%), health=%d",
        month, year, total_income, total_expenses, net_savings, savings_rate, health_score,
    )

    return summary

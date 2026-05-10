"""Month-over-month comparison logic — all calculations in Pandas."""

import json
import logging
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.database import crud

logger = logging.getLogger(__name__)

_MONTH_NAMES = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


def get_comparison_data(user_id: str, db: Session, months: int = 6) -> pd.DataFrame:
    """Fetch the last N monthly summaries as a DataFrame.

    Args:
        user_id: The user to fetch data for.
        db: Database session.
        months: Max number of months to retrieve.

    Returns:
        DataFrame with one row per month, ordered chronologically.
    """
    summaries = crud.get_monthly_summaries(db, user_id, limit=months)
    if not summaries:
        return pd.DataFrame()

    rows = []
    for s in summaries:
        rows.append({
            "period": f"{_MONTH_NAMES[s.month]} {s.year}",
            "month": s.month,
            "year": s.year,
            "total_income": s.total_income,
            "total_expenses": s.total_expenses,
            "net_savings": s.net_savings,
            "savings_rate": s.savings_rate,
            "top_category": s.top_category,
            "category_breakdown": s.category_breakdown,
            "subscription_total": s.subscription_total,
            "subscription_list": s.subscription_list,
            "unusual_transactions": s.unusual_transactions,
            "health_score": s.health_score,
            "llm_insights": s.llm_insights,
        })

    df = pd.DataFrame(rows)
    return df


def compute_trend(series: pd.Series) -> str:
    """Determine the trend direction of a numeric series.

    Args:
        series: Numeric pandas Series (e.g., savings over months).

    Returns:
        Human-readable trend label.
    """
    if len(series) < 3:
        return "insufficient data"
    if series.is_monotonic_increasing:
        return "consistently improving"
    if series.is_monotonic_decreasing:
        return "consistently declining"
    recent = series.tail(3)
    if recent.iloc[-1] > recent.iloc[0]:
        return "recently improving"
    if recent.iloc[-1] < recent.iloc[0]:
        return "recently declining"
    return "inconsistent"


def compute_category_trends(df: pd.DataFrame) -> dict[str, Any]:
    """Compute per-category spending trends across all months.

    Args:
        df: DataFrame with 'period' and 'category_breakdown' (JSON string) columns.

    Returns:
        Dict mapping category → {months, amounts, trend}.
    """
    all_cats: dict[str, dict] = {}

    for _, row in df.iterrows():
        cats = row["category_breakdown"]
        if isinstance(cats, str):
            cats = json.loads(cats)
        for cat, amount in cats.items():
            if cat not in all_cats:
                all_cats[cat] = {"months": [], "amounts": []}
            all_cats[cat]["months"].append(row["period"])
            all_cats[cat]["amounts"].append(float(amount))

    # Compute trend for each category
    for cat, data in all_cats.items():
        series = pd.Series(data["amounts"])
        data["trend"] = compute_trend(series)

    return all_cats


def build_comparison_context(df: pd.DataFrame) -> dict[str, Any]:
    """Pre-compute all comparison metrics in Pandas before sending to Gemini.

    Args:
        df: DataFrame from get_comparison_data().

    Returns:
        Structured comparison context dict.
    """
    if df.empty:
        return {"months_count": 0}

    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) >= 2 else None

    context: dict[str, Any] = {
        "periods_available": df["period"].tolist(),
        "months_count": len(df),
        "latest_month": latest["period"],
        # Trend analysis
        "avg_monthly_savings": round(float(df["net_savings"].mean()), 2),
        "avg_monthly_expenses": round(float(df["total_expenses"].mean()), 2),
        "best_savings_month": df.loc[df["net_savings"].idxmax(), "period"],
        "worst_savings_month": df.loc[df["net_savings"].idxmin(), "period"],
        "savings_trend": compute_trend(df["net_savings"]),
        "health_score_history": df[["period", "health_score"]].to_dict("records"),
        # Category trends
        "category_trends": compute_category_trends(df),
        # Subscription tracking
        "total_subscription_spend": round(float(df["subscription_total"].sum()), 2),
        "avg_monthly_subscriptions": round(float(df["subscription_total"].mean()), 2),
    }

    if previous is not None:
        # Expense change percentage vs last month
        exp_change = (
            ((latest["total_expenses"] - previous["total_expenses"])
             / previous["total_expenses"] * 100)
            if previous["total_expenses"] else 0
        )
        # Savings change percentage vs last month
        sav_change = (
            ((latest["net_savings"] - previous["net_savings"])
             / abs(previous["net_savings"]) * 100)
            if previous["net_savings"] != 0 else 0
        )

        # Find categories that spiked or dropped most vs last month
        latest_cats = json.loads(latest["category_breakdown"]) if isinstance(latest["category_breakdown"], str) else latest["category_breakdown"]
        prev_cats = json.loads(previous["category_breakdown"]) if isinstance(previous["category_breakdown"], str) else previous["category_breakdown"]

        category_changes: dict[str, float] = {}
        for cat in set(list(latest_cats.keys()) + list(prev_cats.keys())):
            prev_amt = float(prev_cats.get(cat, 0))
            curr_amt = float(latest_cats.get(cat, 0))
            if prev_amt > 0:
                category_changes[cat] = round(((curr_amt - prev_amt) / prev_amt) * 100, 1)

        biggest_spike = max(category_changes, key=lambda x: category_changes[x]) if category_changes else None
        biggest_drop = min(category_changes, key=lambda x: category_changes[x]) if category_changes else None

        context["vs_last_month"] = {
            "expense_change_pct": round(float(exp_change), 1),
            "savings_change_pct": round(float(sav_change), 1),
            "income_change_abs": round(float(latest["total_income"] - previous["total_income"]), 2),
            "biggest_spike_category": biggest_spike,
            "biggest_spike_pct": category_changes.get(biggest_spike) if biggest_spike else None,
            "biggest_drop_category": biggest_drop,
            "biggest_drop_pct": category_changes.get(biggest_drop) if biggest_drop else None,
        }

    return context

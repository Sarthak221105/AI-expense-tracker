"""LLM-powered insights generation using NVIDIA API (OpenAI-compatible)."""

import json
import logging
import time
from typing import Any

from openai import OpenAI

from backend.config import settings

logger = logging.getLogger(__name__)


def _get_openai_client() -> OpenAI:
    """Create an OpenAI client configured for NVIDIA API."""
    return OpenAI(
        base_url=settings.NVIDIA_BASE_URL,
        api_key=settings.NVIDIA_API_KEY,
    )


def _build_insights_prompt(summary: dict[str, Any], comparison_context: dict[str, Any]) -> str:
    """Build the LLM prompt with pre-computed financial data.

    Args:
        summary: Monthly summary dict from analysis agent.
        comparison_context: Pre-computed comparison metrics from comparison agent.

    Returns:
        Formatted prompt string.
    """
    unusual_count = 0
    unusual_raw = summary.get("unusual_transactions", "[]")
    if isinstance(unusual_raw, str):
        unusual_count = len(json.loads(unusual_raw))
    elif isinstance(unusual_raw, list):
        unusual_count = len(unusual_raw)

    vs_last_month = comparison_context.get("vs_last_month")
    if vs_last_month:
        comparison_section = json.dumps(vs_last_month, indent=2)
    else:
        comparison_section = "First month uploaded — no comparison available yet."

    prompt = f"""You are a personal finance advisor for an Indian user. Be specific, direct, and use figures.

CURRENT MONTH: {summary['month']}/{summary['year']}
Income: {summary['total_income']:,.0f}
Expenses: {summary['total_expenses']:,.0f}
Savings: {summary['net_savings']:,.0f} ({summary['savings_rate']}% savings rate)
Health Score: {summary['health_score']}/100
Top spending category: {summary['top_category']}
Monthly subscriptions: {summary.get('subscription_total', 0):,.0f}
Unusual transactions: {unusual_count} flagged

TREND CONTEXT ({comparison_context.get('months_count', 1)} months of data):
{comparison_section}
Overall savings trend: {comparison_context.get('savings_trend', 'N/A')}

Write exactly 4 insights:
1. One sentence on overall financial health this month
2. One specific thing that got worse vs last month (with exact figures)
3. One specific thing that improved or stayed good (with exact figures)
4. One concrete action they can take this month (specific, not generic)

Rules:
- Use exact figures from the data above
- Do NOT say "consider reducing" — say "reduce X by Y to save Z annually"
- Do NOT mention anything not in the data provided
- Keep total response under 200 words
- If it is the first month, skip points 2 and 3 and give 2 actionable suggestions instead"""

    return prompt


async def generate_monthly_insights(
    summary: dict[str, Any],
    comparison_context: dict[str, Any],
) -> str:
    """Generate human-readable financial insights using the NVIDIA LLM.

    Args:
        summary: Monthly summary dict (pre-computed by analysis agent).
        comparison_context: Pre-computed comparison data from comparison agent.

    Returns:
        LLM-generated insights paragraph.
    """
    if not settings.NVIDIA_API_KEY:
        logger.warning("No NVIDIA API key — returning placeholder insights")
        return (
            "Insights could not be generated because no NVIDIA API key is configured. "
            "Add your NVIDIA_API_KEY to the .env file to enable AI-powered insights."
        )

    client = _get_openai_client()
    prompt = _build_insights_prompt(summary, comparison_context)

    for attempt in range(settings.MAX_LLM_RETRIES):
        try:
            response = client.chat.completions.create(
                model=settings.NVIDIA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                top_p=0.9,
                max_tokens=1024,
            )
            text = response.choices[0].message.content.strip()
            logger.info("Generated insights (%d chars) on attempt %d", len(text), attempt + 1)
            return text

        except Exception as e:
            logger.warning("Insights generation attempt %d failed: %s", attempt + 1, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                # Exponential backoff: 2s, 4s, 8s
                time.sleep(settings.LLM_BACKOFF_BASE ** (attempt + 1))

    logger.error("Insights generation failed after %d retries", settings.MAX_LLM_RETRIES)
    return (
        "Unable to generate AI insights at this time. "
        "Your financial summary data is still available above."
    )

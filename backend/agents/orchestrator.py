"""Master orchestrator — runs the full processing pipeline with progress updates."""

import logging
from typing import Any

from sqlalchemy.orm import Session

from backend.agents import (
    analysis_agent,
    categoriser_agent,
    comparison_agent,
    insights_agent,
    parser_agent,
)
from backend.database import crud
from backend.tools import subscription_detector

logger = logging.getLogger(__name__)

# Module-level job state store
jobs: dict[str, dict[str, Any]] = {}


def update_job(
    job_id: str,
    status: str,
    progress: int,
    error: str | None = None,
    result: Any = None,
) -> None:
    """Update the in-memory job state.

    Args:
        job_id: Unique job identifier.
        status: Current pipeline stage.
        progress: Percentage complete (0-100).
        error: Error message if failed.
        result: Final result dict when complete.
    """
    jobs[job_id] = {
        "status": status,
        "progress": progress,
        "error": error,
        "result": result,
    }
    logger.info("Job %s: status=%s progress=%d%%", job_id, status, progress)


async def run_pipeline(
    job_id: str,
    file_bytes: bytes,
    file_type: str,
    file_name: str,
    month: int,
    year: int,
    user_id: str,
    db: Session,
    pdf_password: str = "",
) -> None:
    """Execute the full statement processing pipeline.

    Steps:
    1. Parse file (PDF or CSV)
    2. Categorise transactions (two-layer)
    3. Detect subscriptions
    4. Save to database
    5. Calculate monthly summary (Pandas)
    6. Build comparison context
    7. Generate LLM insights
    8. Save summary

    Args:
        job_id: Job ID for progress tracking.
        file_bytes: Raw uploaded file content.
        file_type: "pdf" or "csv".
        file_name: Original filename.
        month: Statement month.
        year: Statement year.
        user_id: User ID.
        db: Database session.
        pdf_password: Optional PDF password for encrypted files. Used only for
                      in-memory decryption — never logged or stored.
    """
    try:
        # Step 1: Parse the file
        update_job(job_id, status="parsing", progress=10)

        if file_type == "pdf":
            # pdf_password is passed through but never logged
            transactions = await parser_agent.parse_pdf(file_bytes, password=pdf_password)
        else:
            transactions = await parser_agent.parse_csv(file_bytes)

        if len(transactions) < 2:
            raise ValueError(
                f"Only {len(transactions)} transactions found. "
                "Check if the file is a valid bank statement."
            )

        # Step 2: Two-layer categorisation
        update_job(job_id, status="categorising", progress=30)
        transactions = await categoriser_agent.categorise(transactions)

        # Step 3: Detect recurring subscriptions
        update_job(job_id, status="detecting_subscriptions", progress=50)
        transactions = subscription_detector.detect(transactions)

        # Step 4: Persist to database
        update_job(job_id, status="saving", progress=60)

        # Ensure user exists
        crud.ensure_user(db, user_id)

        # Delete existing data for this month if any (replace mode)
        crud.delete_statement_cascade(db, user_id, month, year)

        statement = crud.create_statement(
            db, user_id, month, year, file_type, file_name=file_name
        )
        crud.bulk_insert_transactions(db, transactions, statement.id)

        # Step 5: Calculate monthly summary (pure Pandas — no LLM)
        update_job(job_id, status="calculating", progress=65)
        summary = analysis_agent.calculate_monthly_summary(
            transactions, statement.id, user_id, month, year
        )

        # Step 6: Get comparison context for richer insights
        update_job(job_id, status="generating_insights", progress=80)
        comparison_df = comparison_agent.get_comparison_data(user_id, db, months=6)
        comparison_context = comparison_agent.build_comparison_context(comparison_df)

        # Step 7: Generate LLM insights (the only step calling Gemini for text)
        summary["llm_insights"] = await insights_agent.generate_monthly_insights(
            summary, comparison_context
        )

        # Step 8: Save the summary
        crud.create_monthly_summary(db, summary)

        update_job(job_id, status="complete", progress=100, result=summary)
        logger.info("Pipeline complete for job %s", job_id)

    except Exception as e:
        update_job(job_id, status="failed", progress=0, error=str(e))
        logger.error("Pipeline failed for job %s: %s", job_id, e, exc_info=True)

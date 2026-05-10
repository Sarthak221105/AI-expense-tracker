"""FastAPI application — all API endpoints for the Personal Finance Autopilot."""

import asyncio
import json
import logging
import math
import uuid
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.agents.orchestrator import jobs, run_pipeline, update_job
from backend.config import settings
from backend.database import crud
from backend.database.db import get_db, init_db
from backend.schemas import (
    ComparisonResponse,
    HealthResponse,
    JobResponse,
    JobStatusResponse,
    MonthlySummaryResponse,
    SubscriptionListResponse,
    SubscriptionResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
    UserResponse,
)
from backend.tools.subscription_detector import get_subscription_summary

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Personal Finance Autopilot",
    description="Multi-agent personal finance analysis system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database tables on application startup."""
    init_db()
    logger.info("Database initialized")


# ── Helper ──────────────────────────────────────────────────────────────────

def _run_pipeline_sync(
    job_id: str,
    file_bytes: bytes,
    file_type: str,
    file_name: str,
    month: int,
    year: int,
    user_id: str,
    pdf_password: str = "",
):
    """Wrapper to run the async pipeline in a background thread.

    Note: pdf_password is intentionally not logged here.
    """
    from backend.database.db import SessionLocal
    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            run_pipeline(
                job_id, file_bytes, file_type, file_name,
                month, year, user_id, db,
                pdf_password=pdf_password,
            )
        )
        loop.close()
    finally:
        db.close()


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """API health check."""
    return HealthResponse(status="ok")


@app.post("/api/users", response_model=UserResponse)
async def create_user(db: Session = Depends(get_db)):
    """Create a new user and return their ID."""
    user = crud.create_user(db)
    return UserResponse(user_id=user.id, created_at=user.created_at)


@app.post("/api/upload", response_model=JobResponse)
async def upload_statement(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    month: int = Form(...),
    year: int = Form(...),
    user_id: str = Form(...),
    replace: bool = Form(False),
    pdf_password: str = Form(""),
    db: Session = Depends(get_db),
):
    """Upload a bank statement for processing.

    Accepts PDF or CSV files with month/year metadata.
    For password-protected PDFs, pass the password as pdf_password — it is
    used only for in-memory decryption and is never stored or logged.
    Returns immediately with a job_id for polling progress.
    """
    # Validate month and year
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
    if not (2020 <= year <= 2030):
        raise HTTPException(status_code=400, detail="Year must be between 2020 and 2030")

    # Validate file type
    filename = file.filename or ""
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_ext == "pdf":
        file_type = "pdf"
    elif file_ext in ("csv", "xlsx", "xls"):
        file_type = "csv"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{file_ext}. Please upload a PDF or CSV file.",
        )

    # Check for existing statement
    existing = crud.get_statement(db, user_id, month, year)
    if existing and not replace:
        raise HTTPException(
            status_code=409,
            detail=f"Statement for {month}/{year} already exists. Send replace=true to overwrite.",
        )

    # Read file content
    file_bytes = await file.read()

    # Validate file size for PDFs
    if file_type == "pdf" and len(file_bytes) > settings.MAX_PDF_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail=f"PDF file exceeds {settings.MAX_PDF_SIZE_MB}MB limit.",
        )

    # Create job and start background processing
    job_id = str(uuid.uuid4())
    update_job(job_id, status="queued", progress=0)

    background_tasks.add_task(
        _run_pipeline_sync,
        job_id, file_bytes, file_type, filename, month, year, user_id, pdf_password,
    )

    return JobResponse(
        job_id=job_id,
        status="queued",
        message="Processing started. Poll /api/jobs/{job_id} for progress.",
    )


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """Check the status of a processing job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        error=job.get("error"),
    )


@app.get("/api/summary/{user_id}/{year}/{month}", response_model=MonthlySummaryResponse)
async def get_summary(user_id: str, year: int, month: int, db: Session = Depends(get_db)):
    """Get the full monthly summary including LLM insights."""
    summary = crud.get_monthly_summary(db, user_id, month, year)
    if not summary:
        raise HTTPException(status_code=404, detail=f"No summary found for {month}/{year}")
    return MonthlySummaryResponse(
        id=summary.id,
        month=summary.month,
        year=summary.year,
        total_income=summary.total_income,
        total_expenses=summary.total_expenses,
        net_savings=summary.net_savings,
        savings_rate=summary.savings_rate,
        top_category=summary.top_category,
        category_breakdown=summary.category_breakdown,
        subscription_total=summary.subscription_total,
        subscription_list=summary.subscription_list,
        unusual_transactions=summary.unusual_transactions,
        health_score=summary.health_score,
        llm_insights=summary.llm_insights,
        created_at=summary.created_at,
    )


@app.get("/api/comparison/{user_id}", response_model=ComparisonResponse)
async def get_comparison(
    user_id: str,
    months: int = Query(6, ge=2, le=24),
    db: Session = Depends(get_db),
):
    """Get multi-month comparison data with pre-computed context."""
    from backend.agents.comparison_agent import build_comparison_context, get_comparison_data

    df = get_comparison_data(user_id, db, months=months)
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found for comparison")

    comparison_context = build_comparison_context(df)

    # Build summary responses from DB records
    summaries_db = crud.get_monthly_summaries(db, user_id, limit=months)
    summaries = [
        MonthlySummaryResponse(
            id=s.id,
            month=s.month,
            year=s.year,
            total_income=s.total_income,
            total_expenses=s.total_expenses,
            net_savings=s.net_savings,
            savings_rate=s.savings_rate,
            top_category=s.top_category,
            category_breakdown=s.category_breakdown,
            subscription_total=s.subscription_total,
            subscription_list=s.subscription_list,
            unusual_transactions=s.unusual_transactions,
            health_score=s.health_score,
            llm_insights=s.llm_insights,
            created_at=s.created_at,
        )
        for s in summaries_db
    ]

    return ComparisonResponse(summaries=summaries, comparison_context=comparison_context)


@app.get("/api/transactions/{user_id}/{year}/{month}", response_model=TransactionListResponse)
async def get_transactions(
    user_id: str,
    year: int,
    month: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    category: Optional[str] = None,
    needs_review: Optional[bool] = None,
    txn_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get paginated transactions for a specific month."""
    stmt = crud.get_statement(db, user_id, month, year)
    if not stmt:
        raise HTTPException(status_code=404, detail=f"No statement found for {month}/{year}")

    transactions, total = crud.get_transactions(
        db, stmt.id, page=page, per_page=per_page,
        category=category, needs_review=needs_review, txn_type=txn_type,
    )

    return TransactionListResponse(
        transactions=[
            TransactionResponse(
                id=t.id,
                date=t.date,
                description=t.description,
                merchant=t.merchant,
                amount=t.amount,
                type=t.type,
                category=t.category,
                is_subscription=t.is_subscription,
                confidence=t.confidence,
                needs_review=t.needs_review,
            )
            for t in transactions
        ],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=math.ceil(total / per_page) if total > 0 else 1,
    )


@app.patch("/api/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: str,
    updates: TransactionUpdate,
    db: Session = Depends(get_db),
):
    """Manually correct a transaction's category or merchant name."""
    txn = crud.update_transaction(db, transaction_id, updates.model_dump(exclude_none=True))
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return TransactionResponse(
        id=txn.id,
        date=txn.date,
        description=txn.description,
        merchant=txn.merchant,
        amount=txn.amount,
        type=txn.type,
        category=txn.category,
        is_subscription=txn.is_subscription,
        confidence=txn.confidence,
        needs_review=txn.needs_review,
    )


@app.get("/api/subscriptions/{user_id}", response_model=SubscriptionListResponse)
async def get_subscriptions(user_id: str, db: Session = Depends(get_db)):
    """Get all detected subscriptions across all months."""
    all_txns = crud.get_all_user_transactions(db, user_id)
    if not all_txns:
        return SubscriptionListResponse(subscriptions=[], total_annual_cost=0.0)

    txn_dicts = [
        {
            "date": t.date.isoformat() if t.date else None,
            "description": t.description,
            "merchant": t.merchant,
            "amount": t.amount,
            "type": t.type,
            "is_subscription": t.is_subscription,
        }
        for t in all_txns
    ]

    sub_summaries = get_subscription_summary(txn_dicts)
    total_annual = sum(s["annual_cost"] for s in sub_summaries)

    return SubscriptionListResponse(
        subscriptions=[
            SubscriptionResponse(
                merchant=s["merchant"],
                amount=s["amount"],
                frequency=s["frequency"],
                annual_cost=s["annual_cost"],
                last_charged=s.get("last_charged"),
            )
            for s in sub_summaries
        ],
        total_annual_cost=round(total_annual, 2),
    )


@app.delete("/api/statements/{user_id}/{year}/{month}")
async def delete_statement(user_id: str, year: int, month: int, db: Session = Depends(get_db)):
    """Delete a statement and all its transactions and summary."""
    deleted = crud.delete_statement_cascade(db, user_id, month, year)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No statement found for {month}/{year}")
    return {"message": f"Statement for {month}/{year} deleted successfully"}


@app.get("/api/months/{user_id}")
async def get_available_months(user_id: str, db: Session = Depends(get_db)):
    """Get list of months that have uploaded data."""
    months = crud.get_available_months(db, user_id)
    return {"months": months}

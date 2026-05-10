"""All database CRUD operations."""

import logging
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.database.models import MonthlySummary, Statement, Transaction, User

logger = logging.getLogger(__name__)


def _parse_date(raw: object) -> date | None:
    """Convert a raw date value to a Python date object.

    Tries multiple common formats used in Indian bank statements:
    - ISO: YYYY-MM-DD
    - DD/MM/YYYY, DD-MM-YYYY
    - DD/MM/YY, DD-MM-YY
    Returns None if the value is missing or unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    raw_str = str(raw).strip()
    if not raw_str or raw_str.lower() in ("none", "null", ""):
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
                "%m/%d/%Y", "%m-%d-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw_str, fmt).date()
        except ValueError:
            continue
    logger.warning("Could not parse date string %r — storing as NULL", raw_str)
    return None


# ── User Operations ─────────────────────────────────────────────────────────

def create_user(db: Session) -> User:
    """Create a new user with a generated UUID."""
    user = User(id=str(uuid.uuid4()), created_at=datetime.utcnow())
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user %s", user.id)
    return user


def get_user(db: Session, user_id: str) -> Optional[User]:
    """Fetch a user by ID."""
    return db.query(User).filter(User.id == user_id).first()


def ensure_user(db: Session, user_id: str) -> User:
    """Get existing user or create one with the given ID."""
    user = get_user(db, user_id)
    if not user:
        user = User(id=user_id, created_at=datetime.utcnow())
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Auto-created user %s", user.id)
    return user


# ── Statement Operations ────────────────────────────────────────────────────

def get_statement(
    db: Session, user_id: str, month: int, year: int
) -> Optional[Statement]:
    """Fetch a statement for a specific user+month+year."""
    return (
        db.query(Statement)
        .filter(
            Statement.user_id == user_id,
            Statement.month == month,
            Statement.year == year,
        )
        .first()
    )


def create_statement(
    db: Session,
    user_id: str,
    month: int,
    year: int,
    file_type: str,
    file_name: str = "",
    bank_name: Optional[str] = None,
) -> Statement:
    """Insert a new statement record."""
    stmt = Statement(
        id=str(uuid.uuid4()),
        user_id=user_id,
        month=month,
        year=year,
        bank_name=bank_name,
        file_type=file_type,
        file_name=file_name,
        uploaded_at=datetime.utcnow(),
    )
    db.add(stmt)
    db.commit()
    db.refresh(stmt)
    logger.info("Created statement %s for %s/%s", stmt.id, month, year)
    return stmt


def delete_statement_cascade(db: Session, user_id: str, month: int, year: int) -> bool:
    """Delete statement and its transactions + summary. Returns True if found."""
    stmt = get_statement(db, user_id, month, year)
    if not stmt:
        return False
    # Delete transactions
    db.query(Transaction).filter(Transaction.statement_id == stmt.id).delete()
    # Delete summary
    db.query(MonthlySummary).filter(MonthlySummary.statement_id == stmt.id).delete()
    # Delete statement
    db.delete(stmt)
    db.commit()
    logger.info("Deleted statement and related data for %s/%s", month, year)
    return True


# ── Transaction Operations ──────────────────────────────────────────────────

def bulk_insert_transactions(
    db: Session, transactions: list[dict], statement_id: str
) -> list[Transaction]:
    """Insert a batch of parsed transactions."""
    records = []
    for txn in transactions:
        record = Transaction(
            id=str(uuid.uuid4()),
            statement_id=statement_id,
            date=_parse_date(txn.get("date")),
            description=txn.get("description", ""),
            merchant=txn.get("merchant", txn.get("description", "")),
            amount=float(txn["amount"]),
            type=txn.get("type", "debit"),
            category=txn.get("category", "Other"),
            is_subscription=txn.get("is_subscription", False),
            confidence=txn.get("confidence", 0.0),
            needs_review=txn.get("needs_review", False),
        )
        records.append(record)
    db.bulk_save_objects(records)
    db.commit()
    logger.info("Inserted %d transactions for statement %s", len(records), statement_id)
    return records


def get_transactions(
    db: Session,
    statement_id: str,
    page: int = 1,
    per_page: int = 50,
    category: Optional[str] = None,
    needs_review: Optional[bool] = None,
    txn_type: Optional[str] = None,
) -> tuple[list[Transaction], int]:
    """Fetch paginated transactions with optional filters."""
    query = db.query(Transaction).filter(Transaction.statement_id == statement_id)

    if category:
        query = query.filter(Transaction.category == category)
    if needs_review is not None:
        query = query.filter(Transaction.needs_review == needs_review)
    if txn_type:
        query = query.filter(Transaction.type == txn_type)

    total = query.count()
    transactions = (
        query.order_by(Transaction.date.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return transactions, total


def get_all_transactions_for_statement(
    db: Session, statement_id: str
) -> list[Transaction]:
    """Fetch every transaction for a statement (used in analysis)."""
    return (
        db.query(Transaction)
        .filter(Transaction.statement_id == statement_id)
        .all()
    )


def update_transaction(
    db: Session, transaction_id: str, updates: dict
) -> Optional[Transaction]:
    """Manually update a transaction's category or merchant."""
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        return None
    if "category" in updates and updates["category"]:
        txn.category = updates["category"]
    if "merchant" in updates and updates["merchant"]:
        txn.merchant = updates["merchant"]
    txn.needs_review = False
    db.commit()
    db.refresh(txn)
    logger.info("Updated transaction %s", transaction_id)
    return txn


def get_all_user_transactions(db: Session, user_id: str) -> list[Transaction]:
    """Fetch all transactions across all statements for a user."""
    stmt_ids = [
        s.id
        for s in db.query(Statement).filter(Statement.user_id == user_id).all()
    ]
    if not stmt_ids:
        return []
    return (
        db.query(Transaction)
        .filter(Transaction.statement_id.in_(stmt_ids))
        .all()
    )


# ── Monthly Summary Operations ──────────────────────────────────────────────

def create_monthly_summary(db: Session, summary: dict) -> MonthlySummary:
    """Insert or replace a monthly summary."""
    # Delete existing if present
    db.query(MonthlySummary).filter(
        MonthlySummary.user_id == summary["user_id"],
        MonthlySummary.month == summary["month"],
        MonthlySummary.year == summary["year"],
    ).delete()

    record = MonthlySummary(
        id=str(uuid.uuid4()),
        statement_id=summary["statement_id"],
        user_id=summary["user_id"],
        month=summary["month"],
        year=summary["year"],
        total_income=summary["total_income"],
        total_expenses=summary["total_expenses"],
        net_savings=summary["net_savings"],
        savings_rate=summary["savings_rate"],
        top_category=summary["top_category"],
        category_breakdown=summary["category_breakdown"],
        subscription_total=summary["subscription_total"],
        subscription_list=summary["subscription_list"],
        unusual_transactions=summary["unusual_transactions"],
        health_score=summary["health_score"],
        llm_insights=summary.get("llm_insights", ""),
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Created monthly summary for %s/%s", summary["month"], summary["year"])
    return record


def get_monthly_summary(
    db: Session, user_id: str, month: int, year: int
) -> Optional[MonthlySummary]:
    """Fetch a single monthly summary."""
    return (
        db.query(MonthlySummary)
        .filter(
            MonthlySummary.user_id == user_id,
            MonthlySummary.month == month,
            MonthlySummary.year == year,
        )
        .first()
    )


def get_monthly_summaries(
    db: Session, user_id: str, limit: int = 6
) -> list[MonthlySummary]:
    """Fetch the last N monthly summaries ordered chronologically."""
    return (
        db.query(MonthlySummary)
        .filter(MonthlySummary.user_id == user_id)
        .order_by(MonthlySummary.year.asc(), MonthlySummary.month.asc())
        .limit(limit)
        .all()
    )


def get_available_months(db: Session, user_id: str) -> list[dict]:
    """Return list of {month, year} that have data for the user."""
    stmts = (
        db.query(Statement)
        .filter(Statement.user_id == user_id)
        .order_by(Statement.year.desc(), Statement.month.desc())
        .all()
    )
    return [{"month": s.month, "year": s.year} for s in stmts]

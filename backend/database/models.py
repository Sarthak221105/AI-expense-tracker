"""SQLAlchemy ORM models for the finance agent database."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer, String, UniqueConstraint,
    ForeignKey,
)

from backend.database.db import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    """Application user."""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    created_at = Column(DateTime, default=datetime.utcnow)


class Statement(Base):
    """Uploaded bank statement metadata."""
    __tablename__ = "statements"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    bank_name = Column(String, nullable=True)
    file_type = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "month", "year", name="uq_user_month_year"),
    )


class Transaction(Base):
    """Individual parsed transaction."""
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=generate_uuid)
    statement_id = Column(String, ForeignKey("statements.id"), nullable=False)
    date = Column(Date, nullable=True)
    description = Column(String, nullable=False)
    merchant = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)  # "credit" or "debit"
    category = Column(String, nullable=False, default="Other")
    is_subscription = Column(Boolean, default=False)
    confidence = Column(Float, default=0.0)
    needs_review = Column(Boolean, default=False)


class MonthlySummary(Base):
    """Aggregated monthly financial summary."""
    __tablename__ = "monthly_summaries"

    id = Column(String, primary_key=True, default=generate_uuid)
    statement_id = Column(String, ForeignKey("statements.id"), nullable=False)
    user_id = Column(String, nullable=False)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    total_income = Column(Float, default=0.0)
    total_expenses = Column(Float, default=0.0)
    net_savings = Column(Float, default=0.0)
    savings_rate = Column(Float, default=0.0)
    top_category = Column(String, default="N/A")
    category_breakdown = Column(String, default="{}")  # JSON string
    subscription_total = Column(Float, default=0.0)
    subscription_list = Column(String, default="{}")  # JSON string
    unusual_transactions = Column(String, default="[]")  # JSON string
    health_score = Column(Integer, default=50)
    llm_insights = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "month", "year", name="uq_summary_user_month_year"),
    )

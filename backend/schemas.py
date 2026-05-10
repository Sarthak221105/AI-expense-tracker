"""Pydantic v2 models for request/response validation."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ── Request Models ──────────────────────────────────────────────────────────

class UploadRequest(BaseModel):
    """Metadata sent alongside the uploaded file."""
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2020, le=2030)
    user_id: str
    replace: bool = False


class TransactionUpdate(BaseModel):
    """Payload for manual category/merchant correction."""
    category: Optional[str] = None
    merchant: Optional[str] = None


class PaginationParams(BaseModel):
    """Common pagination query parameters."""
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)


# ── Response Models ─────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Returned after user creation."""
    user_id: str
    created_at: datetime


class JobResponse(BaseModel):
    """Returned immediately after upload."""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Status of a background processing job."""
    job_id: str
    status: str
    progress: int = Field(ge=0, le=100)
    error: Optional[str] = None


class TransactionResponse(BaseModel):
    """Single transaction record."""
    id: str
    date: Optional[date] = None
    description: str
    merchant: str
    amount: float
    type: str
    category: str
    is_subscription: bool
    confidence: float
    needs_review: bool


class TransactionListResponse(BaseModel):
    """Paginated transaction list."""
    transactions: list[TransactionResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class MonthlySummaryResponse(BaseModel):
    """Full monthly summary including insights."""
    id: str
    month: int
    year: int
    total_income: float
    total_expenses: float
    net_savings: float
    savings_rate: float
    top_category: str
    category_breakdown: dict[str, float]
    subscription_total: float
    subscription_list: dict[str, float]
    unusual_transactions: list[dict[str, Any]]
    health_score: int
    llm_insights: str
    created_at: datetime

    @field_validator("category_breakdown", "subscription_list", mode="before")
    @classmethod
    def parse_json_str(cls, v: Any) -> dict:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("unusual_transactions", mode="before")
    @classmethod
    def parse_json_list(cls, v: Any) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return v


class ComparisonResponse(BaseModel):
    """Multi-month comparison data."""
    summaries: list[MonthlySummaryResponse]
    comparison_context: dict[str, Any]


class SubscriptionResponse(BaseModel):
    """Detected subscription."""
    merchant: str
    amount: float
    frequency: str
    annual_cost: float
    last_charged: Optional[date] = None


class SubscriptionListResponse(BaseModel):
    """All detected subscriptions."""
    subscriptions: list[SubscriptionResponse]
    total_annual_cost: float


class HealthResponse(BaseModel):
    """API health check."""
    status: str = "ok"

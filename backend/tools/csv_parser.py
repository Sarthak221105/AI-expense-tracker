"""CSV/Excel parser with automatic column detection for various bank formats."""

import io
import logging
import re
from typing import Any

import pandas as pd

from backend.config import settings

logger = logging.getLogger(__name__)

# Column name patterns for auto-detection (case-insensitive)
DATE_PATTERNS = ["date", "txn date", "transaction date", "value date", "posting date", "txn_date"]
DESC_PATTERNS = ["description", "narration", "particulars", "remarks", "details", "transaction details"]
AMOUNT_PATTERNS = ["amount", "txn amount", "transaction amount"]
DEBIT_PATTERNS = ["debit", "withdrawal", "dr", "debit amount", "withdrawals"]
CREDIT_PATTERNS = ["credit", "deposit", "cr", "credit amount", "deposits"]
BALANCE_PATTERNS = ["balance", "running balance", "available balance", "closing balance"]
TYPE_PATTERNS = ["type", "dr/cr", "transaction type", "cr/dr"]


def _match_column(columns: list[str], patterns: list[str]) -> str | None:
    """Find the first column that matches any of the given patterns."""
    for col in columns:
        col_lower = col.lower().strip()
        for pattern in patterns:
            if pattern == col_lower or pattern in col_lower:
                return col
    return None


def _clean_amount(value: Any) -> float:
    """Strip currency symbols, commas, and whitespace from an amount string.

    Args:
        value: Raw amount value (could be string, float, or NaN).

    Returns:
        Cleaned float value, or 0.0 if unparseable.
    """
    if pd.isna(value):
        return 0.0
    s = str(value).strip()
    # Remove currency symbols and whitespace
    s = re.sub(r"[₹$Rs.INR\s]", "", s, flags=re.IGNORECASE)
    # Remove commas
    s = s.replace(",", "")
    # Handle parentheses as negative (some bank formats)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return abs(float(s))
    except (ValueError, TypeError):
        return 0.0


def _read_file(file_bytes: bytes) -> pd.DataFrame:
    """Read CSV with encoding fallback.

    Args:
        file_bytes: Raw file content.

    Returns:
        Parsed DataFrame.

    Raises:
        ValueError: If the file cannot be read with any encoding.
    """
    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
    last_error = None

    for encoding in encodings:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
            if len(df) > 0 and len(df.columns) >= 2:
                logger.info("Read CSV with %s encoding: %d rows, %d columns", encoding, len(df), len(df.columns))
                return df
        except Exception as e:
            last_error = e
            continue

    # Try Excel format as a last resort
    try:
        df = pd.read_excel(io.BytesIO(file_bytes))
        if len(df) > 0:
            logger.info("Read as Excel: %d rows, %d columns", len(df), len(df.columns))
            return df
    except Exception:
        pass

    raise ValueError(f"Failed to read file with any encoding. Last error: {last_error}")


async def parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse a bank statement CSV/Excel file with auto column detection.

    Handles three common CSV formats:
    1. Single amount column + separate debit/credit columns
    2. Single amount column + Dr/Cr indicator column
    3. Two separate columns (one for debit, one for credit)

    Args:
        file_bytes: Raw CSV/Excel file content.

    Returns:
        List of transaction dicts with date, description, amount, type.

    Raises:
        ValueError: If required columns cannot be detected or data is invalid.
    """
    df = _read_file(file_bytes)

    # Enforce max rows
    if len(df) > settings.MAX_CSV_ROWS:
        df = df.head(settings.MAX_CSV_ROWS)
        logger.warning("CSV truncated to %d rows", settings.MAX_CSV_ROWS)

    columns = list(df.columns)
    logger.info("Detected columns: %s", columns)

    # Auto-detect columns
    date_col = _match_column(columns, DATE_PATTERNS)
    desc_col = _match_column(columns, DESC_PATTERNS)
    amount_col = _match_column(columns, AMOUNT_PATTERNS)
    debit_col = _match_column(columns, DEBIT_PATTERNS)
    credit_col = _match_column(columns, CREDIT_PATTERNS)
    type_col = _match_column(columns, TYPE_PATTERNS)

    if not desc_col:
        raise ValueError(
            f"Cannot detect description column. Detected columns: {columns}. "
            "Please verify the file has a description/narration column."
        )

    if not date_col:
        logger.warning("No date column detected in columns: %s", columns)

    # Parse dates
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], infer_datetime_format=True, errors="coerce")

    transactions: list[dict] = []

    for _, row in df.iterrows():
        description = str(row.get(desc_col, "")).strip()
        if not description or description.lower() in ("nan", ""):
            continue

        txn_date = None
        if date_col and pd.notna(row.get(date_col)):
            txn_date = row[date_col].strftime("%Y-%m-%d")

        amount = 0.0
        txn_type = "debit"

        # Format 1 & 2: Single amount column exists
        if amount_col:
            amount = _clean_amount(row.get(amount_col))
            if amount == 0.0:
                continue

            # Check for type indicator column (Dr/Cr)
            if type_col:
                type_val = str(row.get(type_col, "")).strip().upper()
                if type_val in ("CR", "CREDIT", "C"):
                    txn_type = "credit"
                else:
                    txn_type = "debit"
            # If separate debit/credit columns also exist, use them for type
            elif debit_col and credit_col:
                debit_val = _clean_amount(row.get(debit_col))
                credit_val = _clean_amount(row.get(credit_col))
                if credit_val > 0 and debit_val == 0:
                    txn_type = "credit"
                else:
                    txn_type = "debit"

        # Format 3: Two separate debit/credit columns, no single amount
        elif debit_col or credit_col:
            debit_val = _clean_amount(row.get(debit_col)) if debit_col else 0.0
            credit_val = _clean_amount(row.get(credit_col)) if credit_col else 0.0

            if credit_val > 0 and debit_val == 0:
                amount = credit_val
                txn_type = "credit"
            elif debit_val > 0:
                amount = debit_val
                txn_type = "debit"
            else:
                continue
        else:
            raise ValueError(
                f"Cannot detect amount columns. Detected columns: {columns}. "
                "Expected 'amount', 'debit', 'credit', or similar columns."
            )

        if amount == 0.0:
            continue

        transactions.append({
            "date": txn_date,
            "description": description,
            "amount": round(amount, 2),
            "type": txn_type,
        })

    if not transactions:
        raise ValueError(
            "No valid amounts found. Check if currency symbols are preventing parsing."
        )

    # Log summary
    total_debits = sum(t["amount"] for t in transactions if t["type"] == "debit")
    total_credits = sum(t["amount"] for t in transactions if t["type"] == "credit")
    logger.info(
        "CSV parsing complete: %d transactions, total debits=%.2f, total credits=%.2f",
        len(transactions), total_debits, total_credits
    )

    return transactions

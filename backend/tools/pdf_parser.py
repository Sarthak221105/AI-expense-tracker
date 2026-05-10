"""Two-stage PDF parser: LLM-based extraction (primary) with pdfplumber fallback.

Supports password-protected PDFs — the password is used only to decrypt
the file in memory and is never logged, stored, or persisted anywhere.

Uses NVIDIA API (OpenAI-compatible) for LLM-based transaction extraction
from text extracted by pdfplumber.
"""

import io
import json
import logging
import re
import time
from typing import Any

from openai import OpenAI
import pdfplumber

from backend.config import settings

logger = logging.getLogger(__name__)

# Prompt for transaction extraction from raw text.
# This prompt is tuned for the common Indian bank statement table format:
#   Date | Instrument ID | Amount(INR) | Type (DR/CR) | Balance | Remarks
# where Remarks is typically a UPI reference like:
#   UPI/DR/612148604926/MERCHANTNAME/BANKCODE/upiid@bank
_EXTRACTION_PROMPT = """
You are a precise bank statement parser for Indian UPI bank statements.
Below is raw text extracted from one page of a bank statement.

THE TABLE COLUMNS ARE (in order):
  Date | Instrument ID | Amount(INR) | Type | Balance | Remarks

EXTRACTION RULES — follow exactly:
1. For each data row extract ONE transaction with these fields:
   - date: the Date column value converted to YYYY-MM-DD format (e.g. 01/05/2026 → 2026-05-01)
   - description: the full Remarks column text (exact, do not truncate)
   - amount: the Amount(INR) column value as a positive float — NEVER use the Balance column
   - type: if Type column is "DR" → "debit"; if Type column is "CR" → "credit"
2. The Balance column is a running total — NEVER treat it as an amount.
3. Ignore header rows, date/time footer rows, opening balance rows, closing balance rows, and page number lines.
4. Do NOT skip any transaction row.
5. Return ONLY a valid JSON array of objects. No markdown, no explanation, no extra text.

EXAMPLE OUTPUT:
[
  {{"date": "2026-05-01", "description": "UPI/DR/612148604926/ABHINAY/IBKL/9604966007-2@yb/U", "amount": 200.0, "type": "debit"}},
  {{"date": "2026-05-01", "description": "UPI/CR/306806446828/ABHINAY/IBKL/9604966007-2@yb/P", "amount": 1000.0, "type": "credit"}}
]

BANK STATEMENT TEXT:
{page_text}
"""


# ── UPI Merchant Extraction ──────────────────────────────────────────────────

_UPI_RE = re.compile(
    r"UPI/(?:DR|CR)/\d+/([^/]+)/",
    re.IGNORECASE,
)


def _extract_upi_merchant(description: str) -> str:
    """Pull the human-readable merchant name from a UPI reference string.

    UPI references follow the pattern:
        UPI/DR/<txn_id>/<MERCHANT>/<BANK_CODE>/<upi_id>/<suffix>

    Returns the raw description unchanged if it does not match the pattern.
    """
    m = _UPI_RE.search(description)
    if m:
        merchant = m.group(1).strip()
        # Normalise: title-case, collapse whitespace
        return " ".join(merchant.title().split())
    return description[:60]  # Fallback: first 60 chars


def _get_openai_client() -> OpenAI:
    """Create an OpenAI client configured for NVIDIA API."""
    return OpenAI(
        base_url=settings.NVIDIA_BASE_URL,
        api_key=settings.NVIDIA_API_KEY,
    )


# ── PDF Decryption ───────────────────────────────────────────────────────────

def _decrypt_pdf(pdf_bytes: bytes, password: str) -> bytes:
    """Decrypt a password-protected PDF in memory using pikepdf.

    The password is used only within this function and is never logged
    or written to disk. The returned bytes are a decrypted copy.

    Args:
        pdf_bytes: Raw (encrypted) PDF file bytes.
        password: The PDF password provided by the user.

    Returns:
        Decrypted PDF bytes with no password protection.

    Raises:
        ValueError: If the password is incorrect or the PDF cannot be opened.
    """
    import pikepdf  # Imported here so it's only required when a password is needed

    try:
        buf = io.BytesIO()
        with pikepdf.open(io.BytesIO(pdf_bytes), password=password) as pdf_obj:
            pdf_obj.save(buf)
        logger.info("PDF decrypted successfully in memory (%d bytes)", buf.tell())
        return buf.getvalue()
    except pikepdf.PasswordError:
        raise ValueError(
            "Incorrect password for this PDF. Please check the password and try again."
        )
    except Exception as e:
        raise ValueError(f"Could not decrypt PDF: {e}") from e


def _is_encrypted(pdf_bytes: bytes) -> bool:
    """Check if a PDF is password-protected without raising an exception."""
    import pikepdf  # Imported here so it's only required when needed

    try:
        with pikepdf.open(io.BytesIO(pdf_bytes)):
            return False
    except pikepdf.PasswordError:
        logger.info("PDF is password-protected (pikepdf.PasswordError)")
        return True
    except pikepdf._core.PasswordError:
        logger.info("PDF is password-protected (pikepdf._core.PasswordError)")
        return True
    except Exception as e:
        # Fallback: check the error message for password-related keywords
        err = str(e).lower()
        if "password" in err or "encrypted" in err:
            logger.info("PDF appears encrypted (detected from error message: %s)", e)
            return True
        logger.warning("pikepdf could not open PDF for encryption check: %s", e)
        # If we can't open it at all, try treating it as encrypted if a password
        # will be provided anyway
        return False


# ── LLM-based Extraction ────────────────────────────────────────────────────

def _call_llm_extract(page_text: str, page_num: int) -> list[dict]:
    """Send extracted page text to the NVIDIA LLM and parse the response.

    Args:
        page_text: Plain text extracted from a PDF page.
        page_num: Page number for logging.

    Returns:
        List of transaction dicts parsed from the LLM's response.
    """
    if not page_text.strip():
        logger.info("Page %d has no text content, skipping LLM call", page_num)
        return []

    client = _get_openai_client()
    prompt = _EXTRACTION_PROMPT.format(page_text=page_text)

    for attempt in range(settings.MAX_LLM_RETRIES):
        try:
            response = client.chat.completions.create(
                model=settings.NVIDIA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                top_p=0.9,
                max_tokens=8192,
            )
            text = response.choices[0].message.content.strip()
            logger.info("LLM raw response for page %d (first 300 chars): %s",
                        page_num, text[:300])

            # Strip markdown code fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            transactions = json.loads(text)
            if not isinstance(transactions, list):
                raise ValueError("Response is not a JSON array")

            valid = []
            for txn in transactions:
                amount = float(txn.get("amount", 0))
                txn_type = txn.get("type", "").lower()
                if amount > 0 and txn_type in ("credit", "debit"):
                    raw_desc = str(txn.get("description", ""))
                    valid.append({
                        "date": txn.get("date"),
                        "description": raw_desc,
                        "merchant": _extract_upi_merchant(raw_desc),
                        "amount": amount,
                        "type": txn_type,
                    })
            logger.info("LLM extracted %d valid out of %d raw transactions from page %d",
                        len(valid), len(transactions), page_num)
            return valid

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("LLM attempt %d for page %d failed (parse error): %s", attempt + 1, page_num, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                time.sleep(settings.LLM_BACKOFF_BASE ** attempt)
        except Exception as e:
            logger.warning("LLM attempt %d for page %d failed: %s", attempt + 1, page_num, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                time.sleep(settings.LLM_BACKOFF_BASE ** attempt)

    logger.error("LLM extraction failed for page %d after %d retries", page_num, settings.MAX_LLM_RETRIES)
    return []


def _call_llm_extract_full(full_text: str) -> list[dict]:
    """Send the full PDF text to the LLM for extraction.

    Used when per-page extraction yields too few results.

    Args:
        full_text: Complete text extracted from the PDF.

    Returns:
        List of transaction dicts parsed from the response.
    """
    if not full_text.strip():
        return []

    client = _get_openai_client()
    prompt = _EXTRACTION_PROMPT.format(page_text=full_text)

    for attempt in range(settings.MAX_LLM_RETRIES):
        try:
            response = client.chat.completions.create(
                model=settings.NVIDIA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                top_p=0.9,
                max_tokens=8192,
            )
            text = response.choices[0].message.content.strip()

            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            transactions = json.loads(text)
            if not isinstance(transactions, list):
                raise ValueError("Response is not a JSON array")

            valid = []
            for txn in transactions:
                amount = float(txn.get("amount", 0))
                txn_type = txn.get("type", "").lower()
                if amount > 0 and txn_type in ("credit", "debit"):
                    raw_desc = str(txn.get("description", ""))
                    valid.append({
                        "date": txn.get("date"),
                        "description": raw_desc,
                        "merchant": _extract_upi_merchant(raw_desc),
                        "amount": amount,
                        "type": txn_type,
                    })
            logger.info("LLM (full text) extracted %d valid transactions", len(valid))
            return valid

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("LLM full-text attempt %d parse error: %s", attempt + 1, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                time.sleep(settings.LLM_BACKOFF_BASE ** attempt)
        except Exception as e:
            logger.warning("LLM full-text attempt %d failed: %s", attempt + 1, e)
            if attempt < settings.MAX_LLM_RETRIES - 1:
                time.sleep(settings.LLM_BACKOFF_BASE ** attempt)

    return []


# ── pdfplumber Text Extraction ───────────────────────────────────────────────

def _extract_text_pages(pdf_bytes: bytes) -> list[str]:
    """Extract text from each PDF page using pdfplumber.

    Args:
        pdf_bytes: Raw (already decrypted) PDF file bytes.

    Returns:
        List of text strings, one per page.
    """
    pages_text = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)
    except Exception as e:
        logger.warning("pdfplumber text extraction failed: %s", e)
    return pages_text


# ── pdfplumber Table/Regex Fallback ──────────────────────────────────────────

def _parse_with_pdfplumber(pdf_bytes: bytes, password: str = "") -> list[dict]:
    """Fallback parser using pdfplumber table extraction and regex.

    Args:
        pdf_bytes: Raw (already decrypted) PDF file bytes.
        password: Optional password for pdfplumber (usually empty after decryption).

    Returns:
        List of transaction dicts.
    """
    amount_pattern = re.compile(r"[\d,]+\.\d{2}")
    date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
    debit_keywords = {"DR", "DEBIT", "WITHDRAWAL", "PAID", "PURCHASE"}
    credit_keywords = {"CR", "CREDIT", "DEPOSIT", "RECEIVED", "REFUND"}

    transactions = []

    open_kwargs: dict = {}
    if password:
        open_kwargs["password"] = password

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes), **open_kwargs) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Try table extraction first
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table:
                            if not row:
                                continue
                            row_text = " ".join(str(cell or "") for cell in row)
                            amounts = amount_pattern.findall(row_text)
                            if not amounts:
                                continue

                            dates = date_pattern.findall(row_text)
                            txn_date = dates[0] if dates else None

                            # Extract description: longest cell that isn't a number
                            description = ""
                            for cell in row:
                                cell_str = str(cell or "").strip()
                                if (cell_str
                                        and not amount_pattern.fullmatch(cell_str)
                                        and not date_pattern.fullmatch(cell_str)):
                                    if len(cell_str) > len(description):
                                        description = cell_str

                            # Determine debit vs credit
                            row_upper = row_text.upper()
                            txn_type = "debit"
                            if any(kw in row_upper for kw in credit_keywords):
                                txn_type = "credit"
                            elif any(kw in row_upper for kw in debit_keywords):
                                txn_type = "debit"
                            elif len(amounts) >= 2:
                                debit_amt = _clean_amount(amounts[0])
                                credit_amt = _clean_amount(amounts[1])
                                if credit_amt > 0 and debit_amt == 0:
                                    txn_type = "credit"
                                    amounts = [amounts[1]]
                                elif debit_amt > 0:
                                    amounts = [amounts[0]]

                            amount = _clean_amount(amounts[0])
                            if amount > 0 and description:
                                transactions.append({
                                    "date": txn_date,
                                    "description": description.strip(),
                                    "amount": amount,
                                    "type": txn_type,
                                })

                # Raw text fallback if no tables found
                if not tables:
                    text = page.extract_text() or ""
                    for line in text.split("\n"):
                        amounts = amount_pattern.findall(line)
                        if not amounts:
                            continue
                        dates = date_pattern.findall(line)
                        txn_date = dates[0] if dates else None

                        desc = line
                        for d in dates:
                            desc = desc.replace(d, "")
                        for a in amounts:
                            desc = desc.replace(a, "")
                        desc = desc.strip(" -|")

                        line_upper = line.upper()
                        txn_type = "debit"
                        if any(kw in line_upper for kw in credit_keywords):
                            txn_type = "credit"

                        amount = _clean_amount(amounts[0])
                        if amount > 0 and desc:
                            transactions.append({
                                "date": txn_date,
                                "description": desc.strip(),
                                "amount": amount,
                                "type": txn_type,
                            })

    except Exception as e:
        logger.error("pdfplumber parsing failed: %s", e, exc_info=True)

    logger.info("pdfplumber extracted %d transactions", len(transactions))
    return transactions


def _clean_amount(amount_str: str) -> float:
    """Remove commas and convert to float."""
    try:
        return float(amount_str.replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


# ── Main Entry Point ─────────────────────────────────────────────────────────

async def parse_pdf(pdf_bytes: bytes, password: str = "") -> list[dict[str, Any]]:
    """Parse a bank statement PDF using two-stage extraction.

    Supports password-protected PDFs. If a password is provided it is used
    only to decrypt the file in memory — it is never stored or logged.

    Stage 1: Extract text via pdfplumber, then send to NVIDIA LLM for
             structured transaction parsing.
    Stage 2: pdfplumber table/regex extraction fallback.

    Args:
        pdf_bytes: Raw PDF file content (may be encrypted).
        password: Optional PDF password. Used only in memory, never persisted.

    Returns:
        List of transaction dicts with date, description, amount, type.

    Raises:
        ValueError: If the file is invalid, the password is wrong, or no
                    transactions could be extracted.
    """
    if not pdf_bytes or len(pdf_bytes) < 10:
        raise ValueError("Uploaded file is empty or too small to be a valid PDF.")

    logger.info("parse_pdf called: %d bytes, password=%s",
                len(pdf_bytes), "PROVIDED" if password else "NOT PROVIDED")

    # ── Step 1: Handle encryption ────────────────────────────────────────────
    working_bytes = pdf_bytes  # Will be replaced with decrypted bytes if needed
    num_pages = 0
    open_failed = False
    encrypted_detected = _is_encrypted(pdf_bytes)
    logger.info("Encryption check result: %s", encrypted_detected)

    if encrypted_detected:
        if not password:
            raise ValueError(
                "This PDF is password protected. "
                "Please enter the PDF password in the 'PDF Password' field when uploading."
            )
        logger.info("PDF is encrypted, attempting in-memory decryption")
        working_bytes = _decrypt_pdf(pdf_bytes, password)
        logger.info("Decryption succeeded, decrypted size: %d bytes", len(working_bytes))
        try:
            with pdfplumber.open(io.BytesIO(working_bytes)) as pdf2:
                num_pages = len(pdf2.pages)
                logger.info("Decrypted PDF opened with pdfplumber: %d pages", num_pages)
        except Exception as e2:
            raise ValueError(f"Failed to open decrypted PDF: {e2}") from e2
    else:
        # Not detected as encrypted — but if a password was provided, try
        # decrypting anyway in case our detection missed it.
        if password:
            logger.info("PDF not detected as encrypted but password was provided, "
                        "attempting decryption anyway")
            try:
                working_bytes = _decrypt_pdf(pdf_bytes, password)
                logger.info("Decryption with provided password succeeded: %d bytes",
                            len(working_bytes))
            except Exception as dec_err:
                logger.info("Decryption attempt with provided password failed (%s), "
                            "using original bytes", dec_err)

        try:
            with pdfplumber.open(io.BytesIO(working_bytes)) as pdf:
                num_pages = len(pdf.pages)
                logger.info("PDF opened successfully: %d pages", num_pages)
        except Exception as e:
            logger.warning("pdfplumber could not open PDF (%s), will attempt extraction anyway", e)
            open_failed = True

    # If pdfplumber opened it fine but a password was still provided,
    # the PDF may have permission restrictions — decrypt to get clean bytes.
    if not open_failed and password and num_pages > 0 and not encrypted_detected:
        try:
            working_bytes = _decrypt_pdf(pdf_bytes, password)
            logger.info("Applied password to remove PDF restrictions")
        except Exception:
            # Password was wrong for restrictions — original bytes still work fine
            pass

    # From this point forward: working_bytes is always the best available bytes.
    logger.info("Working bytes size: %d, num_pages: %d, open_failed: %s",
                len(working_bytes), num_pages, open_failed)

    # ── Step 2: LLM-based extraction (primary) ──────────────────────────────
    all_transactions: list[dict] = []

    if settings.NVIDIA_API_KEY:
        try:
            # Extract text from each page using pdfplumber
            pages_text = _extract_text_pages(working_bytes)
            total_text_chars = sum(len(t) for t in pages_text)
            pages_with_text = sum(1 for t in pages_text if t.strip())
            logger.info(
                "Text extraction: %d pages, %d with text, %d total chars",
                len(pages_text), pages_with_text, total_text_chars,
            )

            if pages_with_text == 0:
                logger.warning(
                    "NO TEXT extracted from any page! This PDF may be scanned/image-based "
                    "or pdfplumber cannot read this layout. Will try pdfplumber fallback."
                )
            else:
                # Log a preview of extracted text for debugging
                for i, page_text in enumerate(pages_text):
                    if page_text.strip():
                        preview = page_text.strip()[:200].replace('\n', ' | ')
                        logger.info("Page %d text preview (%d chars): %s",
                                    i + 1, len(page_text), preview)

            if pages_text:
                # Send each page's text to the LLM for structured extraction
                for i, page_text in enumerate(pages_text):
                    if page_text.strip():
                        page_txns = _call_llm_extract(page_text, i + 1)
                        all_transactions.extend(page_txns)
                logger.info("LLM extracted %d total transactions from %d pages",
                           len(all_transactions), len(pages_text))

                # If per-page extraction got few results, try sending all text at once
                if len(all_transactions) < 5:
                    full_text = "\n\n--- PAGE BREAK ---\n\n".join(
                        t for t in pages_text if t.strip()
                    )
                    if full_text.strip():
                        logger.info("Per-page extraction got only %d, trying full text (%d chars)",
                                   len(all_transactions), len(full_text))
                        full_txns = _call_llm_extract_full(full_text)
                        if len(full_txns) > len(all_transactions):
                            all_transactions = full_txns
                            logger.info("Full-text extraction improved to %d transactions",
                                       len(all_transactions))
        except Exception as e:
            logger.warning("LLM extraction stage failed: %s", e, exc_info=True)
    else:
        logger.warning("No NVIDIA_API_KEY set — skipping LLM extraction entirely")

    # ── Step 3: pdfplumber fallback ──────────────────────────────────────────
    if len(all_transactions) < 5 and num_pages > 0:
        logger.info(
            "LLM extracted only %d transactions, falling back to pdfplumber table/regex",
            len(all_transactions),
        )
        try:
            # working_bytes is already decrypted so no password needed here
            fallback_txns = _parse_with_pdfplumber(working_bytes)
            logger.info("pdfplumber fallback extracted %d transactions", len(fallback_txns))
            if len(fallback_txns) > len(all_transactions):
                all_transactions = fallback_txns
        except Exception as e:
            logger.warning("pdfplumber fallback failed: %s", e, exc_info=True)

    if len(all_transactions) < 2:
        # Build a detailed diagnostic message
        diag_parts = [
            f"Only {len(all_transactions)} transaction(s) could be extracted.",
        ]
        if num_pages == 0:
            diag_parts.append("The PDF could not be opened (0 pages detected).")
        elif encrypted_detected and not password:
            diag_parts.append("The PDF is password-protected but no password was provided.")
        else:
            diag_parts.append(
                f"The PDF has {num_pages} page(s) but extraction failed. "
                "Check backend logs for details."
            )
        diag_parts.append(
            "Try converting your PDF to CSV from your bank's website."
        )
        raise ValueError(" ".join(diag_parts))

    # Log totals (no amounts, no passwords — safe to log)
    total_debits = sum(t["amount"] for t in all_transactions if t["type"] == "debit")
    total_credits = sum(t["amount"] for t in all_transactions if t["type"] == "credit")
    logger.info(
        "PDF parsing complete: %d transactions, debits=%.2f, credits=%.2f",
        len(all_transactions), total_debits, total_credits,
    )

    return all_transactions

"""Parser agent — delegates to PDF or CSV parser tools."""

import logging
from typing import Any

from backend.tools import csv_parser, pdf_parser

logger = logging.getLogger(__name__)


async def parse_pdf(file_bytes: bytes, password: str = "") -> list[dict[str, Any]]:
    """Parse a PDF bank statement into structured transactions.

    Args:
        file_bytes: Raw PDF file content (may be password-protected).
        password: Optional PDF password used only for in-memory decryption.
                  Never logged or stored.

    Returns:
        List of transaction dicts.
    """
    logger.info("Parser agent: starting PDF parsing (%d bytes)", len(file_bytes))
    transactions = await pdf_parser.parse_pdf(file_bytes, password=password)
    logger.info("Parser agent: extracted %d transactions from PDF", len(transactions))
    return transactions


async def parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    """Parse a CSV/Excel bank statement into structured transactions.

    Args:
        file_bytes: Raw CSV file content.

    Returns:
        List of transaction dicts.
    """
    logger.info("Parser agent: starting CSV parsing (%d bytes)", len(file_bytes))
    transactions = await csv_parser.parse_csv(file_bytes)
    logger.info("Parser agent: extracted %d transactions from CSV", len(transactions))
    return transactions

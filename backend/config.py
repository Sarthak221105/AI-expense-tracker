"""Application configuration loaded from environment variables."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve the .env file relative to this config.py so it is always found
# regardless of which directory uvicorn is launched from.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_loaded = load_dotenv(dotenv_path=_ENV_FILE, override=True)

logging.basicConfig()
_cfg_log = logging.getLogger(__name__)
_cfg_log.info(".env path: %s | loaded: %s", _ENV_FILE, _loaded)


class Settings:
    """Central configuration for the finance agent application."""

    def __init__(self) -> None:
        # NVIDIA API settings (OpenAI-compatible)
        self.NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
        self.NVIDIA_BASE_URL: str = os.getenv(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.NVIDIA_MODEL: str = os.getenv(
            "NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"
        )

        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL", "sqlite:///./finance_agent.db"
        )
        self.TEMP_UPLOAD_DIR: str = os.getenv("TEMP_UPLOAD_DIR", "./temp_uploads")
        self.MAX_PDF_SIZE_MB: int = int(os.getenv("MAX_PDF_SIZE_MB", "10"))
        self.MAX_CSV_ROWS: int = int(os.getenv("MAX_CSV_ROWS", "10000"))
        self.DEFAULT_USER_ID: str = os.getenv("DEFAULT_USER_ID", "default_user")
        self.BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.MAX_LLM_RETRIES: int = 3
        self.LLM_BACKOFF_BASE: float = 2.0

        # Log key status (never log the key itself)
        key_status = "SET" if self.NVIDIA_API_KEY else "MISSING"
        _cfg_log.info(
            "NVIDIA_API_KEY: %s | MODEL: %s | BASE_URL: %s",
            key_status, self.NVIDIA_MODEL, self.NVIDIA_BASE_URL,
        )


settings = Settings()

# Ensure temp upload dir exists
Path(settings.TEMP_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# config.py
import os
from pathlib import Path

# Optional: load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def _getenv_required(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


# ---- Load required environment variables ----
API_KEY_ID: str = _getenv_required("KALSHI_API_KEY_ID")
PRIVATE_KEY_PATH: str = _getenv_required("KALSHI_PRIVATE_KEY_PATH")
BASE_URL: str = os.getenv("KALSHI_BASE_URL", "https://demo-api.kalshi.co/trade-api/v2").rstrip("/")


# ---- Sanity checks ----
_p = Path(PRIVATE_KEY_PATH)
if not _p.exists():
    raise FileNotFoundError(f"Private key not found at: {PRIVATE_KEY_PATH}")
if not _p.is_file():
    raise FileNotFoundError(f"Private key path is not a file: {PRIVATE_KEY_PATH}")

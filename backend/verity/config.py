import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VERITY_DATA_DIR", BACKEND_DIR / "data"))
DOCUMENTS_DIR = DATA_DIR / "documents"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'verity.db'}")

# LLM layer. The provider is deliberately swappable; Gemini's free tier is the
# development default, with a specific model chosen via VERITY_LLM_MODEL.
LLM_PROVIDER = os.getenv("VERITY_LLM_PROVIDER", "gemini")
# "…-latest" tracks the current Gemini flash model, so a specific model being
# retired doesn't break the app. Pin a fixed model via VERITY_LLM_MODEL if you
# want reproducibility.
LLM_MODEL = os.getenv("VERITY_LLM_MODEL", "gemini-flash-latest")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# PDF ingestion limits. Verity targets dense papers (≤~40pp); the cap draws the
# line at books/theses, where text-only extraction and one-HTML rendering
# degrade. Both are env-overridable so they can be raised later.
PDF_MAX_PAGES = int(os.getenv("VERITY_PDF_MAX_PAGES", "50"))
PDF_MAX_BYTES = int(os.getenv("VERITY_PDF_MAX_BYTES", str(40 * 1024 * 1024)))


def ensure_dirs() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def document_dir(doc_key: str) -> Path:
    # arXiv ids can contain "/" (old-style like "hep-th/9901001"); PDF keys use
    # a "pdf-<hash>" form. Sanitize path-illegal characters either way.
    safe = doc_key.replace("/", "_").replace(":", "_")
    path = DOCUMENTS_DIR / safe
    path.mkdir(parents=True, exist_ok=True)
    return path

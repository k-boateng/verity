import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VERITY_DATA_DIR", BACKEND_DIR / "data"))
DOCUMENTS_DIR = DATA_DIR / "documents"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'verity.db'}")
# Some hosts (Render, Heroku) hand out "postgres://"; SQLAlchemy needs the
# "postgresql://" scheme.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Browser origins allowed to call the API. In production set VERITY_CORS_ORIGINS
# to the deployed frontend URL(s), comma-separated.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "VERITY_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

# LLM layer. The provider is deliberately swappable. Groq is the default —
# genuinely free (no card) and Llama 3.3 70B is a clear step up from Gemini
# Flash. Cerebras and Gemini are drop-in alternatives via VERITY_LLM_PROVIDER.
LLM_PROVIDER = os.getenv("VERITY_LLM_PROVIDER", "groq")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

_DEFAULT_MODELS = {
    "cerebras": "llama-3.3-70b",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-flash-latest",
}
# Pin a specific model via VERITY_LLM_MODEL; otherwise use the provider default.
LLM_MODEL = os.getenv("VERITY_LLM_MODEL") or _DEFAULT_MODELS.get(LLM_PROVIDER, "llama-3.3-70b")

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

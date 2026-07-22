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


def ensure_dirs() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def document_dir(arxiv_id: str) -> Path:
    # arXiv ids can contain "/" (old-style ids like "hep-th/9901001")
    safe = arxiv_id.replace("/", "_")
    path = DOCUMENTS_DIR / safe
    path.mkdir(parents=True, exist_ok=True)
    return path

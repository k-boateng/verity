import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("VERITY_DATA_DIR", BACKEND_DIR / "data"))
DOCUMENTS_DIR = DATA_DIR / "documents"

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'verity.db'}")


def ensure_dirs() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


def document_dir(arxiv_id: str) -> Path:
    # arXiv ids can contain "/" (old-style ids like "hep-th/9901001")
    safe = arxiv_id.replace("/", "_")
    path = DOCUMENTS_DIR / safe
    path.mkdir(parents=True, exist_ok=True)
    return path

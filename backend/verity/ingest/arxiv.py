import gzip
import io
import re
import tarfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

USER_AGENT = "verity/0.1 (reading tool; contact: kwameboateng.kb@proton.me)"
COURTESY_DELAY_S = 3.0

_last_request_at = 0.0

ARXIV_ID_RE = re.compile(
    r"(?P<id>(?:\d{4}\.\d{4,5})(?:v\d+)?|(?:[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)"
)


class FetchError(Exception):
    pass


def normalize_arxiv_id(raw: str) -> str:
    """Accept a bare id, arXiv:… prefix, or any arxiv.org URL form."""
    raw = raw.strip()
    raw = re.sub(r"^arxiv:", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"https?://(www\.)?(ar5iv\.labs\.)?arxiv\.org/(abs|pdf|html)/", "", raw)
    raw = raw.removesuffix(".pdf").rstrip("/")
    m = ARXIV_ID_RE.fullmatch(raw)
    if not m:
        raise FetchError(f"Could not recognize an arXiv id in {raw!r}")
    return m.group("id")


def _throttled_get(client: httpx.Client, url: str) -> httpx.Response:
    global _last_request_at
    wait = COURTESY_DELAY_S - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()
    return client.get(url, follow_redirects=True)


@dataclass
class FetchResult:
    arxiv_id: str
    html: str
    html_base_url: str  # for resolving relative image srcs
    source_dir: Path | None  # unpacked LaTeX source, None if unavailable
    warnings: list[str] = field(default_factory=list)


def fetch(arxiv_id: str, dest_dir: Path) -> FetchResult:
    warnings: list[str] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0) as client:
        html, base_url = _fetch_html(client, arxiv_id)
        source_dir = None
        try:
            source_dir = _fetch_source(client, arxiv_id, dest_dir)
        except FetchError as exc:
            warnings.append(f"LaTeX source unavailable: {exc}")
    (dest_dir / "raw.html").write_text(html, encoding="utf-8")
    return FetchResult(
        arxiv_id=arxiv_id,
        html=html,
        html_base_url=base_url,
        source_dir=source_dir,
        warnings=warnings,
    )


def _fetch_html(client: httpx.Client, arxiv_id: str) -> tuple[str, str]:
    candidates = [
        f"https://arxiv.org/html/{arxiv_id}",
        f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
    ]
    for url in candidates:
        resp = _throttled_get(client, url)
        final = str(resp.url)
        # ar5iv redirects to arxiv.org/abs when it has no conversion
        if resp.status_code == 200 and "/abs/" not in final and "ltx_" in resp.text:
            return resp.text, final if final.endswith("/") else final + "/"
    raise FetchError(
        f"No HTML rendering available for {arxiv_id} "
        "(neither arxiv.org/html nor ar5iv could convert it)"
    )


def _fetch_source(client: httpx.Client, arxiv_id: str, dest_dir: Path) -> Path:
    resp = _throttled_get(client, f"https://arxiv.org/e-print/{arxiv_id}")
    if resp.status_code != 200:
        raise FetchError(f"e-print request returned HTTP {resp.status_code}")
    data = resp.content
    if data[:4] == b"%PDF":
        raise FetchError("submission is PDF-only (no LaTeX source)")

    source_dir = dest_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if data[:2] == b"\x1f\x8b":  # gzip: either a tarball or a single gzipped file
        try:
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                _safe_extract(tar, source_dir)
            return source_dir
        except tarfile.ReadError:
            inner = gzip.decompress(data)
            if inner[:4] == b"%PDF":
                raise FetchError("submission is PDF-only (no LaTeX source)")
            (source_dir / "main.tex").write_bytes(inner)
            return source_dir
    # Rarely, a bare .tex
    (source_dir / "main.tex").write_bytes(data)
    return source_dir


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest.resolve())):
            raise FetchError(f"unsafe path in source archive: {member.name}")
    tar.extractall(dest)


def find_main_tex(source_dir: Path) -> Path | None:
    """The main file is the one with \\documentclass; prefer the one that
    also contains \\begin{document} and the largest such file."""
    candidates = []
    for path in source_dir.rglob("*.tex"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\\documentclass" in text:
            score = (1 if "\\begin{document}" in text else 0, len(text))
            candidates.append((score, path))
    if not candidates:
        return None
    return max(candidates)[1]


def inline_inputs(main_tex: Path, max_depth: int = 5) -> str:
    """Recursively inline \\input{...} and \\include{...} so downstream
    passes see one document."""
    root = main_tex.parent

    def load(path: Path, depth: int) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        if depth >= max_depth:
            return text

        def repl(m: re.Match) -> str:
            name = m.group(2).strip()
            if not name or name.startswith("#"):
                return m.group(0)
            child = root / name
            if child.suffix == "":
                child = child.with_suffix(".tex")
            if child.exists():
                return "\n" + load(child, depth + 1) + "\n"
            return m.group(0)

        return re.sub(r"\\(input|include)\{([^}]*)\}", repl, text)

    return load(main_tex, 0)


def fetch_asset(base_url: str, rel_src: str, dest: Path) -> bool:
    """Download one image/asset referenced by the HTML. Returns success."""
    url = base_url + rel_src.lstrip("/")
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client:
            resp = _throttled_get(client, url)
        if resp.status_code == 200:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
    except httpx.HTTPError:
        pass
    return False

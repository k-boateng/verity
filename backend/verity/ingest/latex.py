"""LaTeX source pass.

Real-world .tex is messy, so everything here is tolerant regex extraction:
each function returns what it can find and never raises on malformed input.
The LaTeX pass supplies what the HTML rendering can't — macro definitions,
theorem-environment statements, and symbol candidates from math.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from pylatexenc.latex2text import LatexNodes2Text

_latex_to_text = LatexNodes2Text(math_mode="verbatim")

THEOREM_LIKE = (
    "theorem",
    "lemma",
    "corollary",
    "proposition",
    "definition",
    "assumption",
    "remark",
    "claim",
    "example",
    "conjecture",
)


@dataclass
class LatexInfo:
    labels: dict[str, str] = field(default_factory=dict)  # label -> environment kind
    refs: list[str] = field(default_factory=list)  # referenced labels
    cite_keys: list[str] = field(default_factory=list)
    bibliography: dict[str, str] = field(default_factory=dict)  # key -> entry text
    macros: dict[str, str] = field(default_factory=dict)  # \name -> body
    theorems: list[dict] = field(default_factory=list)  # {kind, title, label, statement}
    sections: list[dict] = field(default_factory=list)  # {level, title, label}
    symbols: list[dict] = field(default_factory=list)  # {token, count}


def strip_comments(tex: str) -> str:
    # Remove % comments but keep \% literals
    return re.sub(r"(?<!\\)%.*", "", tex)


def clean_text(tex: str) -> str:
    """Best-effort LaTeX -> readable text for excerpts."""
    try:
        text = _latex_to_text.latex_to_text(tex)
    except Exception:
        text = re.sub(r"\\[a-zA-Z]+\*?", " ", tex)
    return re.sub(r"\s+", " ", text).strip()


def parse(tex: str) -> LatexInfo:
    tex = strip_comments(tex)
    info = LatexInfo()
    info.labels = parse_labels(tex)
    info.refs = parse_refs(tex)
    info.cite_keys = parse_cites(tex)
    info.bibliography = parse_bibliography(tex)
    info.macros = parse_macros(tex)
    info.theorems = parse_theorem_envs(tex)
    info.sections = parse_sections(tex)
    info.symbols = parse_symbols(tex)
    return info


def parse_labels(tex: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for m in re.finditer(r"\\label\{([^}]+)\}", tex):
        label = m.group(1).strip()
        # Environment kind: the innermost \begin{...} before this label
        preceding = tex[: m.start()]
        envs = re.findall(r"\\begin\{([a-zA-Z*]+)\}", preceding)
        ends = re.findall(r"\\end\{([a-zA-Z*]+)\}", preceding)
        open_envs = []
        for env in envs:
            open_envs.append(env)
        for env in ends:
            if env in open_envs:
                # remove the most recent matching open
                for i in range(len(open_envs) - 1, -1, -1):
                    if open_envs[i] == env:
                        del open_envs[i]
                        break
        labels[label] = open_envs[-1] if open_envs else "text"
    return labels


def parse_refs(tex: str) -> list[str]:
    refs = []
    for m in re.finditer(r"\\(?:auto|eq|c|C|page)?[rR]ef\*?\{([^}]+)\}", tex):
        refs.extend(part.strip() for part in m.group(1).split(","))
    return refs


def parse_cites(tex: str) -> list[str]:
    keys = []
    for m in re.finditer(r"\\[cC]ite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]+)\}", tex):
        keys.extend(part.strip() for part in m.group(1).split(","))
    return keys


def parse_bibliography(tex: str) -> dict[str, str]:
    """\\bibitem entries from thebibliography or an inlined .bbl."""
    bib: dict[str, str] = {}
    items = re.split(r"\\bibitem", tex)
    for chunk in items[1:]:
        m = re.match(r"(?:\[[^\]]*\])?\{([^}]+)\}", chunk)
        if not m:
            continue
        key = m.group(1).strip()
        body = chunk[m.end() :]
        # entry ends at next \bibitem (already split) or \end{thebibliography}
        body = body.split("\\end{thebibliography}")[0]
        bib[key] = clean_text(body)[:600]
    return bib


def parse_macros(tex: str) -> dict[str, str]:
    macros: dict[str, str] = {}
    pattern = re.compile(
        r"\\(?:re)?newcommand\*?\s*\{?\\([a-zA-Z]+)\}?\s*(?:\[\d+\])?\s*\{",
    )
    for m in pattern.finditer(tex):
        name = m.group(1)
        body = _read_balanced(tex, m.end() - 1)
        if body is not None:
            macros[name] = body.strip()
    for m in re.finditer(r"\\DeclareMathOperator\*?\{\\([a-zA-Z]+)\}\{([^}]*)\}", tex):
        macros[m.group(1)] = m.group(2)
    return macros


def _read_balanced(tex: str, open_brace_idx: int) -> str | None:
    """Read the {...} group starting at open_brace_idx; returns inner text."""
    if open_brace_idx >= len(tex) or tex[open_brace_idx] != "{":
        return None
    depth = 0
    for i in range(open_brace_idx, min(len(tex), open_brace_idx + 2000)):
        c = tex[i]
        if c == "{" and (i == 0 or tex[i - 1] != "\\"):
            depth += 1
        elif c == "}" and tex[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return tex[open_brace_idx + 1 : i]
    return None


def parse_theorem_envs(tex: str) -> list[dict]:
    """Statements of theorem-like environments, including custom names
    declared via \\newtheorem{lem}{Lemma}."""
    env_kinds: dict[str, str] = {}
    for kind in THEOREM_LIKE:
        env_kinds[kind] = kind
    for m in re.finditer(r"\\newtheorem\*?\{([^}]+)\}(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        display = m.group(2).strip().lower()
        for kind in THEOREM_LIKE:
            if kind in display:
                env_kinds[m.group(1).strip()] = kind
                break

    theorems = []
    for env, kind in env_kinds.items():
        pattern = re.compile(
            r"\\begin\{" + re.escape(env) + r"\}(?:\[([^\]]*)\])?(.*?)\\end\{" + re.escape(env) + r"\}",
            re.DOTALL,
        )
        for m in pattern.finditer(tex):
            body = m.group(2)
            label_m = re.search(r"\\label\{([^}]+)\}", body)
            statement = re.sub(r"\\label\{[^}]+\}", "", body)
            theorems.append(
                {
                    "kind": kind,
                    "title": (m.group(1) or "").strip(),
                    "label": label_m.group(1).strip() if label_m else "",
                    "statement": clean_text(statement)[:1200],
                }
            )
    return theorems


def parse_sections(tex: str) -> list[dict]:
    sections = []
    for m in re.finditer(
        r"\\(section|subsection|subsubsection)\*?\{", tex
    ):
        title = _read_balanced(tex, m.end() - 1)
        if title is None:
            continue
        after = tex[m.end() : m.end() + 200]
        label_m = re.search(r"\\label\{([^}]+)\}", after)
        sections.append(
            {
                "level": m.group(1),
                "title": clean_text(title),
                "label": label_m.group(1).strip() if label_m else "",
            }
        )
    return sections


# Symbol candidates: single letters (optionally Greek) with an optional
# sub/superscript, e.g. d_k, \alpha, x_i^2, W^Q
SYMBOL_TOKEN_RE = re.compile(
    r"(?:\\(?:alpha|beta|gamma|delta|epsilon|varepsilon|zeta|eta|theta|iota|kappa|"
    r"lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|phi|varphi|chi|psi|omega|"
    r"Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Upsilon|Phi|Psi|Omega|ell)"
    r"|[a-zA-Z])"
    r"(?:_\{?[a-zA-Z0-9\\]{1,12}\}?)?(?:\^\{?[a-zA-Z0-9\\]{1,12}\}?)?"
)

MATH_REGION_RE = re.compile(
    r"\$\$(.+?)\$\$|\$(.+?)\$|\\\[(.*?)\\\]|\\\((.*?)\\\)|"
    r"\\begin\{(?:equation|align|gather|multline|eqnarray)\*?\}(.*?)"
    r"\\end\{(?:equation|align|gather|multline|eqnarray)\*?\}",
    re.DOTALL,
)

_STOP_TOKENS = {"a", "A", "I", "e", "i", "j", "s", "t", "o", "O"}


def parse_symbols(tex: str, min_count: int = 3, limit: int = 40) -> list[dict]:
    counts: Counter[str] = Counter()
    for m in MATH_REGION_RE.finditer(tex):
        region = next(g for g in m.groups() if g is not None)
        for tok_m in SYMBOL_TOKEN_RE.finditer(region):
            # normalize braces away: d_{k}, d_k and a stray d_k} are one token
            tok = tok_m.group(0).replace("{", "").replace("}", "")
            # require a subscript/superscript OR a Greek letter OR uppercase:
            # bare lowercase single letters are too noisy
            if "_" in tok or "^" in tok or tok.startswith("\\") or (len(tok) == 1 and tok.isupper()):
                if tok not in _STOP_TOKENS:
                    counts[tok] += 1
    return [
        {"token": tok, "count": n}
        for tok, n in counts.most_common(limit)
        if n >= min_count
    ]

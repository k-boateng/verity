"""High-level resolution tasks built on a provider.

The system prompts carry the trust layer. The balance they strike: the model
may use general knowledge of the field to explain a concept (that's the whole
point of "Ask"), but any claim about what *this paper specifically* does must
be grounded in the supplied context — and when the model genuinely can't help
without more of the paper, it abstains with a fixed sentinel rather than
guessing. Generated answers are always shown flagged as AI, so world-knowledge
explanation and paper-grounded quotes never get confused.
"""

from .base import LLMProvider

# Machine sentinel the model emits when it can't help — robust to detect,
# unlike a natural-language sentence the model would paraphrase.
ABSTAIN_TOKEN = "NEEDS_MORE_CONTEXT"
ABSTAIN_MESSAGE = (
    "This depends on something the surrounding text doesn't pin down — "
    "you may need an earlier section."
)

_GROUNDING = (
    "You may use general knowledge of the field to explain concepts and terms. "
    "But any statement about what THIS paper specifically does, defines, or claims "
    "must be supported by the provided context — never invent the paper's own "
    "notation, values, citations, or results. If the span depends on something the "
    "context doesn't give you (an undefined custom symbol, a result from an earlier "
    f"section you can't see) and general knowledge can't bridge it, reply with "
    f"exactly: {ABSTAIN_TOKEN}"
)

_PLAIN = " Write plain prose — no markdown, asterisks, bullets, or headers."

_RESOLVE_SYSTEM = (
    "You are Verity, a reading aid embedded inside a scientific paper. The reader "
    "highlighted a span they find confusing. Explain just that span, clearly and "
    "briefly (2 to 4 sentences), in plain language — unpack the jargon rather than "
    "restating it." + _PLAIN + "\n" + _GROUNDING
)

_EQUATION_SYSTEM = (
    "You are Verity, embedded inside a scientific paper. Explain what the given "
    "equation says and does, in plain language (3 to 5 sentences), walking through "
    "the role of each part." + _PLAIN + "\n" + _GROUNDING
)

_SYMBOL_SYSTEM = (
    "You are Verity, embedded inside a scientific paper. State concisely (one "
    "sentence, under 20 words) what a mathematical symbol denotes, based on the "
    "excerpts where it appears plus general knowledge of the notation.\n"
    "Answer with the meaning only, no preamble. If the excerpts and general "
    f"conventions don't determine it, reply with exactly: {ABSTAIN_TOKEN}"
)


def is_abstention(answer: str) -> bool:
    return answer.strip().upper().startswith(ABSTAIN_TOKEN)


def _dependencies_block(dependencies: list[str]) -> str:
    if not dependencies:
        return "(none resolved nearby)"
    return "\n".join(f"- {d}" for d in dependencies[:12])


def resolve_selection(
    provider: LLMProvider,
    *,
    selection: str,
    paragraph: str,
    section: str = "",
    title: str = "",
    dependencies: list[str] | None = None,
) -> str:
    prompt = (
        f'Paper: "{title}"\n'
        f"Section: {section or 'unknown'}\n\n"
        f"Paragraph the reader is in:\n\"\"\"\n{paragraph.strip()}\n\"\"\"\n\n"
        f"Nearby resolved references:\n{_dependencies_block(dependencies or [])}\n\n"
        f'The reader highlighted: "{selection.strip()}"\n\n'
        "Explain the highlighted span."
    )
    return provider.generate(_RESOLVE_SYSTEM, prompt, max_tokens=400)


def explain_equation(
    provider: LLMProvider,
    *,
    latex: str,
    context: str = "",
    symbols: list[str] | None = None,
    title: str = "",
) -> str:
    prompt = (
        f'Paper: "{title}"\n\n'
        f"Equation (LaTeX):\n{latex.strip()}\n\n"
        f"Surrounding context:\n\"\"\"\n{context.strip()}\n\"\"\"\n\n"
        f"Symbols in play:\n{_dependencies_block(symbols or [])}\n\n"
        "Explain this equation."
    )
    return provider.generate(_EQUATION_SYSTEM, prompt, max_tokens=500)


def define_symbol(
    provider: LLMProvider,
    *,
    symbol: str,
    excerpts: str,
    title: str = "",
) -> str:
    prompt = (
        f'Paper: "{title}"\n\n'
        f"Symbol: {symbol}\n\n"
        f"Excerpts where it appears:\n\"\"\"\n{excerpts.strip()}\n\"\"\"\n\n"
        f"What does {symbol} denote?"
    )
    return provider.generate(_SYMBOL_SYSTEM, prompt, max_tokens=80)

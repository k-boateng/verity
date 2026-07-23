# Verity

Read hard papers without losing your place.

Verity is a reading tool for dense documents where the intelligence lives inside the page instead of in a chatbot beside it. Open a paper and it stays a paper — but every dense object (a term used before it's defined, a symbol you forgot, a "see Figure 3", a citation) is one hover away from being resolved in place, quoted from the paper itself.

## Principles

- **Keep it a paper.** The document stays the document; the intelligence overlays it.
- **Retrieve before you generate.** Anything the paper answers itself is quoted, not paraphrased.
- **Never confidently wrong.** Everything shows its provenance: resolved-from-the-paper and AI-inferred content look and behave differently, and "not stated in this paper" is a first-class answer.

## Status

Early development. Current focus: arXiv papers (ingested from LaTeX source), in-place hover resolution for cross-references and citations, an auto-built notation sheet, and a depth breadcrumb so you can dive into dependencies and climb back out in one click.

## Running locally

Backend (Python 3.11+):

```
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn verity.main:app --reload --port 8000
```

To enable explanations (the "Ask" gesture) and the anchored chat, add a model
API key in `backend/.env`:

```
CEREBRAS_API_KEY=your_key_here
```

Get a free key at https://cloud.cerebras.ai (1M tokens/day, no card). Without a
key, the reader and retrieval-grounded resolution still work; only generated
explanations are disabled.

To use a different provider, set `VERITY_LLM_PROVIDER` to `groq` or `gemini`
(with `GROQ_API_KEY` / `GEMINI_API_KEY`); pick a specific model with
`VERITY_LLM_MODEL`. No code changes — same interface.

Frontend (Node 18+):

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and paste an arXiv link.

Ingest from the command line instead:

```
cd backend
python -m verity.cli ingest 1706.03762
```

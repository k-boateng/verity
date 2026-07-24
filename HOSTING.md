# Hosting Verity

Verity is two pieces: a **FastAPI backend** (ingestion + resolution) and a
**static React frontend**. The recommended free-tier setup is Supabase (Postgres)
+ Render (backend) + Vercel (frontend). Everything below is already scaffolded —
you mostly paste values.

## 1. Database — Supabase

1. Create a Supabase project.
2. Settings → Database → Connection string → **URI**. Copy it
   (`postgresql://postgres:...@...supabase.co:5432/postgres`).
3. That's your `DATABASE_URL`. No schema setup needed — the backend creates its
   tables on first boot. (Local dev needs nothing here; it defaults to SQLite.)

## 2. Backend — Render

1. Push this repo to GitHub (done).
2. Render → **New +** → **Blueprint** → pick this repo. It reads `render.yaml`.
3. Set the secret env vars when prompted:
   - `GROQ_API_KEY` — your free key from console.groq.com
   - `DATABASE_URL` — the Supabase URI from step 1
   - `VERITY_CORS_ORIGINS` — your Vercel URL (fill this after step 3, e.g.
     `https://verity.vercel.app`); redeploy once you have it.
4. Deploy. Note the service URL, e.g. `https://verity-backend.onrender.com`.

## 3. Frontend — Vercel

1. Vercel → **Add New** → **Project** → pick this repo.
2. Set **Root Directory** to `frontend`. Vercel auto-detects Vite (`vercel.json`
   pins it).
3. Add an env var: `VITE_API_BASE` = your Render backend URL from step 2.
4. Deploy. Copy the resulting URL back into the backend's `VERITY_CORS_ORIGINS`
   and redeploy the backend.

That's it — open the Vercel URL and paste an arXiv link or drop a PDF.

## Storage: no disk needed

The backend is stateless — a document's rendered HTML and its figures/table
crops are stored **in the database** (not on local disk), served from there.
So a free Render instance can cold-start all it wants and your library survives:
nothing lives on the ephemeral filesystem. No persistent disk, no paid tier.

The only thing this puts in the DB is image bytes. At personal scale that's a
non-issue (Supabase's free 500 MB holds ~100 papers with figures, and deleting a
paper reclaims its space). If it ever grows large, the clean next step is moving
image bytes to Supabase Storage — but you're nowhere near needing that.

## Notes

- The backend also runs fine as a plain Render "Python" service instead of Docker
  (build: `pip install -r requirements.txt`, start:
  `uvicorn verity.main:app --host 0.0.0.0 --port $PORT`), but the Dockerfile is
  the most reproducible.
- Free-tier Render web services sleep after inactivity; the first request after a
  sleep takes ~30s to wake. Expected.
- Swapping the LLM provider (e.g. to Cerebras/Groq) is a `VERITY_LLM_PROVIDER`
  change plus a small provider class — no other code touches it.

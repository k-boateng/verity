# Verity backend — FastAPI + PyMuPDF ingestion.
FROM python:3.12-slim

WORKDIR /app

# PyMuPDF, google-genai, latex2mathml all ship wheels, so no build toolchain
# is needed beyond what the slim image provides.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY verity ./verity

# Render (and most PaaS) inject $PORT; default to 8000 locally.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn verity.main:app --host 0.0.0.0 --port ${PORT}"]

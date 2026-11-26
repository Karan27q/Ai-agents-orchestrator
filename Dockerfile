# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React frontend ----------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: install Python dependencies ----------
FROM python:3.11-slim AS deps
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /tmp/reqs
# postgres.txt already contains the full base runtime set.
# Swap it for base.txt if you do not need Postgres/pgvector.
COPY backend/requirements/postgres.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --only-binary=:all: --require-hashes -r postgres.txt

# ---------- Stage 3: runtime ----------
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system app \
 && useradd --system --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY backend ./backend
COPY --from=frontend /frontend/dist ./frontend/dist

RUN mkdir -p /app/backend/uploaded_files \
 && chown -R app:app /app

USER app
WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/observability/health', timeout=3)"

# One worker by default: the FAISS index, caches and WebSocket registry are
# in-process, so multiple workers would each hold a different view of them.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

# ─────────────────────────────────────────────────────────────────────────────
#  Dockerfile — Backend (FastAPI + Uvicorn)
#  Multi-stage build: builder installs deps, final image is lean.
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build

# Install system deps needed to compile psycopg2, ldap3, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libldap2-dev \
    libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: final runtime image ──────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

LABEL maintainer="l1-platform-team"
LABEL description="Enterprise Agentic AI L1 Support Automation Platform — Backend"

# Runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libldap-2.5-0 \
    libsasl2-2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Non-root user for security
RUN groupadd -r l1agent && useradd -r -g l1agent l1agent && chown l1agent:l1agent /app

# Copy application source
COPY --chown=l1agent:l1agent app/ ./app/

USER l1agent

# Expose FastAPI port
EXPOSE 8000

# Healthcheck — calls our /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start Uvicorn (workers set via env for flexibility)
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--log-level", "info"]

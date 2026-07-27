# ---- Stage 1: Build frontend ----
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY sandbox-console/frontend/package.json sandbox-console/frontend/package-lock.json* ./
RUN npm install --legacy-peer-deps
COPY sandbox-console/frontend/ ./
RUN npm run build

# ---- Stage 2: Python runtime ----
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="Sandbox Console"
LABEL org.opencontainers.image.description="Web Console for sandbox environments"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/Rainbow0328/sandbox-web"

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy SDK source and install (with opensandbox extra).
COPY agents-backend /build/sdk
RUN pip install --no-cache-dir uv \
    && uv pip install --system "/build/sdk[opensandbox]" \
    && pip uninstall -y uv

# Install backend package (SDK already installed above).
COPY sandbox-console/backend/pyproject.toml ./
COPY sandbox-console/backend/app ./app
RUN pip install --no-cache-dir uv \
    && uv pip install --system . \
    && pip uninstall -y uv

# Copy frontend build output
COPY --from=frontend-builder /build/frontend/dist /app/frontend/static

# Copy history-helper
COPY sandbox-console/history-helper ./history-helper

# Create data directory and non-root user
RUN mkdir -p /data && \
    useradd -r -s /bin/sh -u 1000 explorer && \
    chown -R explorer:explorer /data /app

# Environment defaults
ENV EXPLORER_HOST=0.0.0.0
ENV EXPLORER_PORT=9090
ENV EXPLORER_DATABASE_URL=sqlite+aiosqlite:////data/explorer.db
ENV EXPLORER_STATIC_DIR=/app/frontend/static
ENV PYTHONUNBUFFERED=1

USER explorer

# Expose the configurable port (evaluated from EXPLORER_PORT at build time).
EXPOSE ${EXPLORER_PORT}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"EXPLORER_PORT\", \"9090\")}/healthz')" || exit 1

# Shell form so $EXPLORER_HOST and $EXPLORER_PORT are expanded at runtime.
ENTRYPOINT python -m uvicorn app.main:app --host ${EXPLORER_HOST} --port ${EXPLORER_PORT}

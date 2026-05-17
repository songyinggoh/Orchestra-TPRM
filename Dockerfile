# Stage 1 — build React dashboard
FROM node:20-slim AS frontend
WORKDIR /app/dashboard
COPY dashboard/package*.json ./
RUN npm ci --silent
COPY dashboard/ ./
RUN npm run build

# Stage 2 — Python backend + bundled static files
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ src/
COPY examples/ examples/

RUN pip install --no-cache-dir ".[tprm,server,telemetry,storage]"

# Copy compiled React app
COPY --from=frontend /app/dashboard/dist /app/static

ENV STATIC_DIR=/app/static
ENV PORT=8080
ENV ORCHESTRA_ENV=prod

EXPOSE 8080

RUN useradd --system --create-home --uid 1001 orchestra
USER orchestra

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "orchestra_tprm.server.app:app", "--host", "0.0.0.0", "--port", "8080"]

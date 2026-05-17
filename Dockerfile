FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for common Phase 4 features
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/

# Install the package with TPRM extras + server/telemetry/storage (nats/security/messaging removed — unused in TPRM)
RUN pip install --no-cache-dir ".[tprm,server,telemetry,storage]"

# Default environment variables
ENV ORCHESTRA_PORT=8080
ENV ORCHESTRA_ENV=prod
ENV NATS_URL="nats://nats:4222"

EXPOSE 8080

# Run as non-root user (required by Pod Security Standards)
RUN useradd --system --create-home --uid 1001 orchestra
USER orchestra

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

ENTRYPOINT ["orchestra-tprm"]
CMD ["--help"]

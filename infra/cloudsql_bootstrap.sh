#!/usr/bin/env bash
# infra/cloudsql_bootstrap.sh
# Idempotent Cloud SQL + pgvector bootstrap.
#
# Usage:
#   export PROJECT_ID=my-gcp-project
#   export REGION=asia-southeast1
#   export INSTANCE_NAME=orchestra-tprm
#   export DB_NAME=tprm
#   export DB_USER=tprm_app
#   bash infra/cloudsql_bootstrap.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth application-default login)
#   - Cloud SQL Admin API enabled in the project
#   - Caller has roles/cloudsql.admin IAM permission
#
# DO NOT RUN until Cloud SQL is provisioned (deferred — live DB step).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-southeast1}"
INSTANCE_NAME="${INSTANCE_NAME:-orchestra-tprm}"
DB_NAME="${DB_NAME:-tprm}"
DB_USER="${DB_USER:-tprm_app}"
TIER="${TIER:-db-g1-small}"

echo "=== Orchestra TPRM — Cloud SQL bootstrap ==="
echo "  project:  $PROJECT_ID"
echo "  region:   $REGION"
echo "  instance: $INSTANCE_NAME"
echo "  database: $DB_NAME"
echo "  user:     $DB_USER"
echo ""

# ── 1. Enable required APIs (idempotent) ─────────────────────────────────────
echo "--- Enabling Cloud SQL Admin API..."
gcloud services enable sqladmin.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet

# ── 2. Create Cloud SQL Postgres instance (idempotent) ───────────────────────
EXISTING=$(gcloud sql instances list \
  --filter="name=$INSTANCE_NAME" \
  --project="$PROJECT_ID" \
  --format="value(name)" 2>/dev/null || true)

if [[ -z "$EXISTING" ]]; then
  echo "--- Creating Cloud SQL instance: $INSTANCE_NAME ..."
  gcloud sql instances create "$INSTANCE_NAME" \
    --database-version=POSTGRES_15 \
    --tier="$TIER" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --storage-auto-increase \
    --backup \
    --enable-bin-log=false \
    --insights-config-query-insights-enabled \
    --flags=cloudsql.enable_pgaudit=on,cloudsql.iam_authentication=on \
    --quiet
  echo "--- Instance created."
else
  echo "--- Instance $INSTANCE_NAME already exists — skipping create."
fi

# ── 3. Create database (idempotent) ──────────────────────────────────────────
DB_EXISTS=$(gcloud sql databases list \
  --instance="$INSTANCE_NAME" \
  --project="$PROJECT_ID" \
  --filter="name=$DB_NAME" \
  --format="value(name)" 2>/dev/null || true)

if [[ -z "$DB_EXISTS" ]]; then
  echo "--- Creating database: $DB_NAME ..."
  gcloud sql databases create "$DB_NAME" \
    --instance="$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --quiet
else
  echo "--- Database $DB_NAME already exists — skipping create."
fi

# ── 4. Create DB user (idempotent) ───────────────────────────────────────────
USER_EXISTS=$(gcloud sql users list \
  --instance="$INSTANCE_NAME" \
  --project="$PROJECT_ID" \
  --filter="name=$DB_USER" \
  --format="value(name)" 2>/dev/null || true)

if [[ -z "$USER_EXISTS" ]]; then
  echo "--- Creating IAM user: $DB_USER ..."
  gcloud sql users create "$DB_USER" \
    --instance="$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --type=BUILT_IN \
    --password="$(openssl rand -base64 24)" \
    --quiet
  echo "--- User created. Store the generated password in Secret Manager."
else
  echo "--- User $DB_USER already exists — skipping create."
fi

# ── 5. Enable pgvector extension via Cloud SQL Auth Proxy ────────────────────
# NOTE: This step requires Cloud SQL Auth Proxy running locally or connectivity.
# Run manually after provisioning:
#
#   cloud-sql-proxy "${PROJECT_ID}:${REGION}:${INSTANCE_NAME}" &
#   psql "host=127.0.0.1 port=5432 dbname=${DB_NAME} user=${DB_USER}" \
#        -c "CREATE EXTENSION IF NOT EXISTS vector;"
#
echo ""
echo "--- MANUAL STEP REQUIRED: enable pgvector extension."
echo "    After Cloud SQL Auth Proxy is running, execute:"
echo "      psql \"host=127.0.0.1 dbname=${DB_NAME} user=${DB_USER}\" \\"
echo "           -c \"CREATE EXTENSION IF NOT EXISTS vector;\""
echo ""

# ── 6. Store connection string in Secret Manager (idempotent) ────────────────
SECRET_NAME="tprm-database-url"
SECRET_EXISTS=$(gcloud secrets list \
  --project="$PROJECT_ID" \
  --filter="name:$SECRET_NAME" \
  --format="value(name)" 2>/dev/null || true)

if [[ -z "$SECRET_EXISTS" ]]; then
  echo "--- Creating Secret Manager secret: $SECRET_NAME ..."
  gcloud secrets create "$SECRET_NAME" \
    --project="$PROJECT_ID" \
    --replication-policy=automatic \
    --quiet
  echo "--- Secret created. Add the DATABASE_URL value:"
  echo "      echo -n 'postgresql+asyncpg://USER:PASS@/DB?host=/cloudsql/CONNNAME' \\"
  echo "        | gcloud secrets versions add $SECRET_NAME --data-file=- --project=$PROJECT_ID"
else
  echo "--- Secret $SECRET_NAME already exists — skipping create."
fi

echo ""
echo "=== Bootstrap complete. Next: run 'alembic upgrade head' after pgvector is enabled. ==="

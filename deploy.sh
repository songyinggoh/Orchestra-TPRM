#!/usr/bin/env bash
# Deploy Orchestra TPRM to Cloud Run (single container: FastAPI + React).
# Usage: bash deploy.sh [GOOGLE_API_KEY]
set -euo pipefail

PROJECT=advance-replica-496216-n6
REGION=us-central1
REPO=orchestra
SERVICE=orchestra-tprm
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/tprm

GOOGLE_API_KEY=${1:-${GOOGLE_API_KEY:-""}}
if [[ -z "$GOOGLE_API_KEY" ]]; then
  echo "Usage: bash deploy.sh YOUR_GOOGLE_API_KEY"
  echo "  or:  GOOGLE_API_KEY=AIza... bash deploy.sh"
  exit 1
fi

echo "==> Creating Artifact Registry repo (skips if exists)"
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Orchestra TPRM" \
  --project="$PROJECT" 2>/dev/null || true

echo "==> Building image via Cloud Build (no local Docker needed)"
gcloud builds submit \
  --project="$PROJECT" \
  --tag="$IMAGE" \
  --timeout=25m \
  .

echo "==> Deploying to Cloud Run"
gcloud run deploy "$SERVICE" \
  --project="$PROJECT" \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --timeout=900 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_API_KEY=${GOOGLE_API_KEY}"

echo ""
echo "==> Live at:"
gcloud run services describe "$SERVICE" \
  --project="$PROJECT" \
  --region="$REGION" \
  --format='value(status.url)'

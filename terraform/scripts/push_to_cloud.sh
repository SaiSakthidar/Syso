#!/bin/bash
# Helper script to sync local code to the GCP instance

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

INSTANCE_NAME="syso-backend"
ZONE="asia-south1-a"
PROJECT_ID="gemini-489210"
REMOTE_DIR="/opt/syso"

echo "🚀 Syncing code from ${PROJECT_ROOT} to ${INSTANCE_NAME} (Project: ${PROJECT_ID})..."

# Create the directory on the remote instance
gcloud compute ssh ${INSTANCE_NAME} --zone=${ZONE} --project=${PROJECT_ID} --command="sudo mkdir -p ${REMOTE_DIR} && sudo chown -R \$USER:\$USER ${REMOTE_DIR}"

# SCP the backend, shared, and root metadata files (including .env if exists)
gcloud compute scp --recurse ${PROJECT_ROOT}/backend ${PROJECT_ROOT}/shared ${PROJECT_ROOT}/pyproject.toml ${PROJECT_ROOT}/README.md ${PROJECT_ROOT}/uv.lock ${PROJECT_ROOT}/.env ${INSTANCE_NAME}:${REMOTE_DIR}/ --zone=${ZONE} --project=${PROJECT_ID} || echo '⚠️ Warning: .env not found or scp failed. Make sure to set GEMINI_API_KEY on the server.'

echo "✅ Sync complete!"
echo "✨ To start the server, run:"
echo "gcloud compute ssh ${INSTANCE_NAME} --zone=${ZONE} --project=${PROJECT_ID} --command=\"cd ${REMOTE_DIR} && uv run python -m backend.main\""

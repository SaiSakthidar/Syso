gcloud compute ssh syso-backend --zone=asia-south1-a --project=gemini-489210 --command="sudo fuser -k 8000/tcp || true && sudo chown -R \$USER:\$USER /data && sudo chmod -R 777 /data && export PATH=\$HOME/.local/bin:\$PATH && cd /opt/syso && DATA_PATH=/data uv run python -m backend.main"

uv run python app/main.py
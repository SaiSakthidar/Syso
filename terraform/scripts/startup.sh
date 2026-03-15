#!/bin/bash
set -e

# --- 1. Mount Persistent Disk ---
DATA_DIR="/data"
DEVICE_NAME="user-data"
DEVICE_PATH="/dev/disk/by-id/google-${DEVICE_NAME}"

# Wait for device to appear
while [ ! -b ${DEVICE_PATH} ]; do
  echo "Waiting for data disk..."
  sleep 1
done

# Format if needed (ext4)
if ! blkid ${DEVICE_PATH} | grep -q "TYPE=\"ext4\""; then
  mkfs.ext4 -m 0 -E lazy_itable_init=0,lazy_journal_init=0,discard ${DEVICE_PATH}
fi

mkdir -p ${DATA_DIR}
mount -o discard,defaults ${DEVICE_PATH} ${DATA_DIR}
chmod 777 ${DATA_DIR}

# Ensure persistent mount on reboot
echo "${DEVICE_PATH} ${DATA_DIR} ext4 discard,defaults,nofail 0 2" >> /etc/fstab

# --- 2. Install Dependencies ---
apt-get update
apt-get install -y git python3-pip python3-venv curl portaudio19-dev libasound2-dev

# Install uv globally
curl -LsSf https://astral.sh/uv/install.sh | INSTALL_DIR=/usr/local/bin sh

# --- 3. Setup Application ---
APP_DIR="/opt/syso"
mkdir -p ${APP_DIR}
# Note: In a real flow, you'd git clone here.
# For now, we assume the environment is prepared or code is pulled.

# Setup user profiles directory on persistent disk
mkdir -p ${DATA_DIR}/profiles
mkdir -p ${DATA_DIR}/chroma_db
chmod -R 777 ${DATA_DIR}

# Create environment variables for the global system
echo "DATA_PATH=${DATA_DIR}" >> /etc/environment
echo "DEPLOYMENT_TARGET=cloud" >> /etc/environment

echo "Syso Cloud Startup Complete!"

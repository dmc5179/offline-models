#!/bin/bash
set -euo pipefail

MODEL_REPO="RedHatAI/granite-4.0-h-small-FP8-dynamic"
LOCAL_DIR="./model"
REGISTRY="${REGISTRY:-quay.io/danclark}"
IMAGE_NAME="granite-4.0-h-small-fp8-offline"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Downloading ${MODEL_REPO} to ${LOCAL_DIR}..."
hf download "${MODEL_REPO}" --local-dir "${LOCAL_DIR}"

echo "Building container image ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}..."
podman build -t "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}" .

echo "Done. Run with:"
echo "  podman run --rm --device nvidia.com/gpu=all --shm-size=8g -p 8000:8000 ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

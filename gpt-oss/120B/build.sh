#!/bin/bash
set -euo pipefail

MODEL_REPO="openai/gpt-oss-120b"
LOCAL_DIR="./model"
REGISTRY="${REGISTRY:-quay.io/danclark}"
IMAGE_NAME="gpt-oss-120b-offline"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "Downloading ${MODEL_REPO} to ${LOCAL_DIR}..."
hf download "${MODEL_REPO}" --local-dir "${LOCAL_DIR}"

echo "Building container image ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}..."
podman build -t "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}" .

echo "Done. Run with:"
echo "  podman run --rm --device nvidia.com/gpu=all --shm-size=8g -p 8000:8000 ${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

#!/bin/bash
set -euo pipefail

MODEL_REPO="RedHatAI/Qwen3-Embedding-8B"
LOCAL_DIR="./model"
REGISTRY="${REGISTRY:-quay.io/danclark}"
IMAGE_NAME="qwen3-embedding-8b-offline"
IMAGE_TAG="${IMAGE_TAG:-latest}"

PUSH=0
AUTHFILE=""

usage() {
  cat <<EOF
Usage: $(basename "$0") [--push] [--authfile PATH]

  --push            Push the image to the registry after a successful build.
  --authfile PATH   Registry credentials to use for the push. Defaults to
                    podman's normal search path (\$REGISTRY_AUTH_FILE, then
                    \$XDG_RUNTIME_DIR/containers/auth.json, then
                    \$HOME/.docker/config.json).
  -h, --help        Show this help.

Environment:
  REGISTRY          Registry and namespace. Default: quay.io/danclark
  IMAGE_TAG         Image tag. Default: latest

Examples:
  $(basename "$0")
  $(basename "$0") --push
  $(basename "$0") --push --authfile "\$HOME/quay-pull-secret.json"
  REGISTRY=registry.example.com/ai $(basename "$0") --push
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)        PUSH=1; shift ;;
    --authfile)    AUTHFILE="${2:-}"
                   [[ -n "$AUTHFILE" ]] || { echo "error: --authfile requires a path" >&2; exit 2; }
                   shift 2 ;;
    --authfile=*)  AUTHFILE="${1#*=}"; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             echo "error: unknown option '$1'" >&2; echo >&2; usage >&2; exit 2 ;;
  esac
done

IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

if [[ -n "$AUTHFILE" ]]; then
  [[ -f "$AUTHFILE" ]] || { echo "error: authfile not found: $AUTHFILE" >&2; exit 1; }
  [[ "$PUSH" -eq 1 ]] || echo "warning: --authfile has no effect without --push" >&2
fi

echo "Downloading ${MODEL_REPO} to ${LOCAL_DIR}..."
hf download "${MODEL_REPO}" --local-dir "${LOCAL_DIR}"

echo "Building container image ${IMAGE}..."
podman build -t "${IMAGE}" .

if [[ "$PUSH" -eq 1 ]]; then
  echo "Pushing ${IMAGE}..."
  if [[ -n "$AUTHFILE" ]]; then
    podman push --authfile="$AUTHFILE" "${IMAGE}"
  else
    podman push "${IMAGE}"
  fi
  echo "Pushed ${IMAGE}"
else
  echo
  echo "Built ${IMAGE}"
  echo "Run with:"
  echo "  podman run --rm --device nvidia.com/gpu=all --shm-size=8g -p 8000:8000 ${IMAGE}"
  echo "Push with:"
  echo "  $(basename "$0") --push [--authfile /path/to/auth.json]"
fi

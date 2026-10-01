# Offline Models

Air-gapped vLLM model containers for disconnected OpenShift deployment.

## Structure

Each model family gets a top-level directory with size/variant subdirectories containing:
- `Containerfile` — bakes model weights into the vLLM base image
- `build.sh` — downloads weights from HuggingFace and builds the container
- `README.md` — usage and deployment docs
- `openshift/` — OpenShift deployment manifests

## TODO

- [ ] Create kustomize-based OpenShift YAML for `gpt-oss/120B` (keep existing raw manifests)
- [ ] Create kustomize-based OpenShift YAML for `qwen/32B` (keep existing raw manifests)
- [ ] Create kustomize-based OpenShift YAML for `qwen/3.8B` (keep existing raw manifests)

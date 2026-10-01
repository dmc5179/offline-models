# Offline Models

Air-gapped vLLM model containers for disconnected OpenShift deployment.

## Structure

Each model family gets a top-level directory with size/variant subdirectories containing:
- `Containerfile` — bakes model weights into the vLLM base image
- `build.sh` — downloads weights from HuggingFace and builds the container
- `README.md` — usage and deployment docs
- `openshift/` — kustomize-based OpenShift deployment manifests (ArgoCD-ready)

## Models

| Directory | HuggingFace Repo | Registry Image | Notes |
|---|---|---|---|
| `gpt-oss/120B` | `openai/gpt-oss-120b` | `quay.io/danclark/gpt-oss-120b-offline` | MXFP4 quant, 1x 80GB GPU |
| `qwen/32B` | `Qwen/Qwen3-32B` | `quay.io/danclark/qwen3-32b-offline` | 1x GPU, 96Gi mem |
| `qwen/3.8B` | `Qwen/Qwen3-4B` | `quay.io/danclark/qwen3-4b-offline` | 1x GPU, 16Gi mem |
| `granite/4.0-h-small-FP8` | `RedHatAI/granite-4.0-h-small-FP8-dynamic` | `quay.io/danclark/granite-4.0-h-small-fp8-offline` | FP8 dynamic, 1x GPU, 48Gi mem |
| `nemotron/70B-FP8` | `RedHatAI/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic` | `quay.io/danclark/nemotron-70b-fp8-offline` | FP8 dynamic, 1x 80GB GPU, tight fit |

## Build & Push

All build scripts default `REGISTRY=quay.io/danclark`. Override with `REGISTRY=other.registry.io/org ./build.sh`.

Push with: `podman push --authfile=/home/danclark/quay-pull-secret.json <image>`

Build must happen on a machine with internet access — the weights are too large for this workstation's bandwidth.

## Key Decisions

- **Base image**: `registry.redhat.io/rhaii-preview/vllm-cuda-rhel9:1786522102` for all models
- **Containerfile optimization**: Use `COPY --chown=0:0 --chmod=775` in a single layer instead of separate `COPY` + `RUN chmod`. The two-step approach doubles image size because chmod creates a second full copy of the weights layer.
- **No route objects**: Routes are not needed for these deployments.
- **Kustomize for OpenShift**: All `openshift/` dirs use `kustomization.yaml` with `namespace:` set there (not hardcoded in individual resources). ArgoCD points directly at the `openshift/` subdirectory.
- **Deployment improvements** (applied to all models):
  - `startupProbe` with `periodSeconds: 30`, `failureThreshold: 24` (12 min for model loading)
  - GPU `tolerations` for `nvidia.com/gpu` tainted nodes
  - `strategy: Recreate` (can't share GPU between old/new pods during rolling update)
- **FP8-dynamic models**: No `--quantization` flag needed — vLLM auto-detects from model config
- **Granite repo**: `RedHatAI/granite-4.0-h-small-FP8-dynamic` (not ibm-granite, which doesn't have FP8-dynamic)
- **Nemotron repo**: `RedHatAI/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic`

## TODO

- [ ] Build granite and nemotron container images (must be done on a machine with sufficient bandwidth)
- [ ] Push granite and nemotron images to quay.io/danclark
- [ ] Verify Containerfiles for gpt-oss and qwen use single-layer `COPY --chown --chmod` pattern (avoid doubled image size)
- [ ] Remove route.yaml from gpt-oss and qwen `openshift/` dirs if still present (routes not needed)
- [ ] Update READMEs for granite and nemotron to reflect correct HuggingFace repo names (RedHatAI, not ibm-granite/nvidia)

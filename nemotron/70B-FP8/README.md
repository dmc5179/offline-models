# Llama 3.1 Nemotron 70B Instruct FP8 Offline Inference Container

Air-gapped vLLM serving of [nvidia/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic](https://huggingface.co/nvidia/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic) using the Red Hat AI Inference Server (`rhaii-preview/vllm-cuda-rhel9`). The model weights are baked into the container image so no network access is required at runtime.

Llama 3.1 Nemotron 70B Instruct is NVIDIA's instruction-tuned variant of Meta's Llama 3.1 70B, optimized for helpfulness and accuracy. This checkpoint uses FP8 dynamic quantization, fitting on a single 80GB GPU (H100/A100 80GB).

## Prerequisites

- **Podman** (or Docker)
- **NVIDIA GPU** with 80GB VRAM (H100, A100 80GB, or MI300X) and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (CDI configured)
- **HuggingFace CLI** (`hf`) logged in (`hf login`) with `HF_TOKEN` set
- **Red Hat registry access** — authenticate to `registry.redhat.io` before building:
  ```bash
  podman login registry.redhat.io
  ```
- **~140 GB disk space** for the FP8-quantized model weights plus the container image build

## Build

```bash
chmod +x build.sh
./build.sh
```

What it does:

1. Downloads `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic` to `./model/`
2. Builds the container image `nemotron-70b-fp8-offline:latest`

The resulting image bundles the weights at `/models/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic` and sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so vLLM never attempts to reach HuggingFace.

### Base image tag

The Containerfile pins build tag `1786522102` from `registry.redhat.io/rhaii-preview/vllm-cuda-rhel9`. List available tags with:

```bash
podman search registry.redhat.io/rhaii-preview/vllm-cuda-rhel9 --list-tags
```

## Running with Podman

### Basic

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=8g \
  -p 8000:8000 \
  nemotron-70b-fp8-offline:latest
```

The default CMD includes `--gpu-memory-utilization 0.92 --max-model-len 8192` for single 80GB GPU deployment.

### With security options (SELinux hosts)

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --shm-size=8g \
  -p 8000:8000 \
  nemotron-70b-fp8-offline:latest
```

### Overriding vLLM arguments

The entrypoint is `vllm serve`. Append arguments after the image name to override the defaults:

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=8g \
  -p 8000:8000 \
  nemotron-70b-fp8-offline:latest \
  /models/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic \
  --host 0.0.0.0 \
  --port 8000 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 4096
```

### Testing the endpoint

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic",
    "messages": [{"role": "user", "content": "Hello, who are you?"}],
    "max_tokens": 128
  }' | python3 -m json.tool
```

Health check:

```bash
curl http://localhost:8000/health
```

List available models:

```bash
curl http://localhost:8000/v1/models
```

## Deploying on OpenShift with ArgoCD

The `openshift/` directory contains kustomize-based manifests for GitOps deployment via ArgoCD.

### Security design

- **Non-root**: the pod runs as a non-root UID (enforced by `runAsNonRoot: true`).
- **No privilege escalation**: `allowPrivilegeEscalation: false`.
- **All capabilities dropped**: `capabilities.drop: [ALL]`.
- **Seccomp profile**: `RuntimeDefault`.
- **Dedicated ServiceAccount**: `vllm-inference` with a minimal Role granting only `get` on ConfigMaps.
- **Shared memory**: an `emptyDir` with `medium: Memory` (8Gi) mounted at `/dev/shm`.
- **Compatible with `restricted-v2` SCC**: the default OpenShift SCC — no privileged SCC required.

### Step 1: Push the image to a registry accessible from the cluster

```bash
podman tag nemotron-70b-fp8-offline:latest \
  <registry>/nemotron-inference/nemotron-70b-fp8-offline:latest

podman push \
  <registry>/nemotron-inference/nemotron-70b-fp8-offline:latest
```

Update the image reference in `openshift/deployment.yaml` to match your registry.

### Step 2: Push to GitLab and configure ArgoCD

Push this directory to your GitLab repository. Create an ArgoCD Application pointing to the `openshift/` subdirectory:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: nemotron-70b-fp8
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://gitlab.example.com/<group>/<repo>.git
    targetRevision: main
    path: nemotron/70B-FP8/openshift
  destination:
    server: https://kubernetes.default.svc
    namespace: nemotron-inference
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

### Step 3: Verify

```bash
oc get pods -n nemotron-inference -l app=nemotron-70b-fp8
oc logs -n nemotron-inference deploy/nemotron-70b-fp8
oc port-forward -n nemotron-inference svc/nemotron-70b-fp8 8000:8000
curl http://localhost:8000/v1/models
```

### GPU requirements

The deployment requests one NVIDIA GPU with 80GB VRAM via `nvidia.com/gpu: 1`. This requires the [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/index.html) installed on the cluster. The 70B model in FP8 dynamic quantization fits tightly on a single 80GB GPU; without quantization, tensor parallelism across multiple GPUs would be required.

### Customization

| What | Where |
|------|-------|
| GPU count | `deployment.yaml` -> `resources.limits.nvidia.com/gpu` |
| Memory limits | `deployment.yaml` -> `resources.limits.memory` |
| Shared memory | `deployment.yaml` -> `volumes[shm].sizeLimit` |
| vLLM arguments | `deployment.yaml` -> `spec.containers[0].args` (add an `args` field to override CMD) |
| Image reference | `deployment.yaml` -> `spec.containers[0].image` |
| Namespace | `kustomization.yaml` -> `namespace` |

## Files

```
nemotron/70B-FP8/
├── Containerfile            # Container build (non-root, FP8)
├── build.sh                 # Downloads model + builds image
├── README.md                # This file
└── openshift/
    ├── kustomization.yaml   # Kustomize config (ArgoCD entry point)
    ├── serviceaccount.yaml  # Dedicated SA for the workload
    ├── role.yaml            # Minimal RBAC (configmaps:get only)
    ├── rolebinding.yaml     # Binds role to SA
    ├── deployment.yaml      # Pod spec with 80GB GPU, non-root, restricted-v2 compatible
    ├── service.yaml         # ClusterIP service on port 8000
    └── route.yaml           # TLS-terminated Route (optional)
```

# Qwen3-32B Offline Inference Container

Air-gapped vLLM serving of [Qwen/Qwen3-32B](https://huggingface.co/Qwen/Qwen3-32B) using the Red Hat AI Inference Server (`rhaiis/vllm-cuda-rhel9`). The model weights are baked into the container image so no network access is required at runtime.

Qwen3-32B is a 32-billion-parameter dense model from the Qwen3 series with hybrid thinking/non-thinking modes, 32K native context (131K with YaRN), released under Apache 2.0.

## Prerequisites

- **Podman** (or Docker)
- **NVIDIA GPU** with 80GB VRAM (H100, A100 80GB) and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (CDI configured)
- **HuggingFace CLI** (`hf`) logged in (`hf login`)
- **Red Hat registry access** — authenticate to `registry.redhat.io` before building:
  ```bash
  podman login registry.redhat.io
  ```
- **~64 GB disk space** for the BF16 model weights plus ~64 GB for the container image build

## Build

The build script downloads the model weights from HuggingFace and builds the container image in one step:

```bash
chmod +x build.sh
./build.sh
```

What it does:

1. Downloads `Qwen/Qwen3-32B` (~64 GB in BF16) to `./qwen-model/`
2. Builds the container image `qwen3-32b-offline:latest`

The resulting image bundles the weights at `/models/Qwen3-32B` and sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so vLLM never attempts to reach HuggingFace.

### Base image tag

The Containerfile pins version tag `3.3.3` from `registry.redhat.io/rhaiis/vllm-cuda-rhel9`. List available tags with:

```bash
podman search registry.redhat.io/rhaiis/vllm-cuda-rhel9 --list-tags
```

## Running with Podman

### Basic

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=8g \
  -p 8000:8000 \
  qwen3-32b-offline:latest
```

### With security options (SELinux hosts)

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --shm-size=8g \
  -p 8000:8000 \
  qwen3-32b-offline:latest
```

### Overriding vLLM arguments

The entrypoint is `vllm serve`. Append arguments after the image name to override the defaults:

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=8g \
  -p 8000:8000 \
  qwen3-32b-offline:latest \
  /models/Qwen3-32B \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.9
```

### Multi-GPU (tensor parallelism)

If using GPUs with less than 80GB VRAM (e.g., 2x A100 40GB):

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=8g \
  -p 8000:8000 \
  qwen3-32b-offline:latest \
  /models/Qwen3-32B \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 2
```

### Non-root verification

The container runs as UID 1001 (non-root). Verify with:

```bash
podman run --rm --entrypoint id qwen3-32b-offline:latest
```

### Testing the endpoint

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-32B",
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

## Running on OpenShift

The `openshift/` directory contains manifests that deploy the model with a dedicated ServiceAccount and least-privilege security settings.

### Security design

- **Non-root**: the pod runs as a non-root UID (enforced by `runAsNonRoot: true`).
- **No privilege escalation**: `allowPrivilegeEscalation: false`.
- **All capabilities dropped**: `capabilities.drop: [ALL]`.
- **Seccomp profile**: `RuntimeDefault`.
- **Dedicated ServiceAccount**: `vllm-inference` with a minimal Role granting only `get` on ConfigMaps.
- **Shared memory**: an `emptyDir` with `medium: Memory` (8Gi) mounted at `/dev/shm`.
- **Compatible with `restricted-v2` SCC**: the default OpenShift SCC — no privileged SCC required.

### Step 1: Push the image to the internal registry

```bash
podman tag qwen3-32b-offline:latest \
  default-route-openshift-image-registry.apps.<cluster>/qwen-inference/qwen3-32b-offline:latest

oc login ...
podman login -u $(oc whoami) -p $(oc whoami -t) \
  default-route-openshift-image-registry.apps.<cluster>

podman push \
  default-route-openshift-image-registry.apps.<cluster>/qwen-inference/qwen3-32b-offline:latest
```

Or push to any registry your cluster can pull from and update the image reference in `openshift/deployment.yaml`.

### Step 2: Create the namespace and deploy

```bash
oc new-project qwen-inference

oc apply -f openshift/serviceaccount.yaml
oc apply -f openshift/role.yaml
oc apply -f openshift/rolebinding.yaml
oc apply -f openshift/deployment.yaml
oc apply -f openshift/service.yaml

# Optional: expose externally via TLS-terminated Route
oc apply -f openshift/route.yaml
```

### Step 3: Verify

```bash
oc get pods -l app=qwen3-32b
oc exec deploy/qwen3-32b -- id
oc logs deploy/qwen3-32b
oc port-forward svc/qwen3-32b 8000:8000
curl http://localhost:8000/v1/models
```

### GPU requirements

The deployment requests one NVIDIA GPU with 80GB VRAM via `nvidia.com/gpu: 1`. This requires the [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/index.html) installed on the cluster. For multi-GPU tensor parallelism, increase the GPU limit and add `args: ["--tensor-parallel-size", "2"]` to the container spec.

### Customization

| What | Where |
|------|-------|
| GPU count | `deployment.yaml` -> `resources.limits.nvidia.com/gpu` |
| Memory limits | `deployment.yaml` -> `resources.limits.memory` |
| Shared memory | `deployment.yaml` -> `volumes[shm].sizeLimit` |
| vLLM arguments | `deployment.yaml` -> `spec.containers[0].args` (add an `args` field to override CMD) |
| Image reference | `deployment.yaml` -> `spec.containers[0].image` |
| Namespace | All YAML files -> `metadata.namespace` |

## Files

```
qwen/32B/
├── Containerfile            # Container build (non-root)
├── build.sh                 # Downloads model + builds image
├── README.md                # This file
└── openshift/
    ├── serviceaccount.yaml  # Dedicated SA for the workload
    ├── role.yaml            # Minimal RBAC (configmaps:get only)
    ├── rolebinding.yaml     # Binds role to SA
    ├── deployment.yaml      # Pod spec with 80GB GPU, non-root, restricted-v2 compatible
    ├── service.yaml         # ClusterIP service on port 8000
    └── route.yaml           # TLS-terminated Route (optional)
```

# GPT-OSS-120B Offline Inference Container

Air-gapped vLLM serving of [RedHatAI/gpt-oss-120b](https://huggingface.co/RedHatAI/gpt-oss-120b) using the Red Hat AI Inference Server (`rhaiis/vllm-cuda-rhel9`). The model weights are baked into the container image so no network access is required at runtime.

GPT-OSS-120B is OpenAI's open-weight Mixture-of-Experts model (117B total params, 5.1B active per token) released under Apache 2.0. It ships with MXFP4 quantization of MoE weights, fitting on a single 80GB GPU (H100/MI300X).

## Prerequisites

- **Podman** (or Docker)
- **NVIDIA GPU** with 80GB VRAM (H100, A100 80GB, or MI300X) and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (CDI configured)
- **HuggingFace CLI** (`hf`) logged in (`hf login`)
- **Red Hat registry access** — authenticate to `registry.redhat.io` before building:
  ```bash
  podman login registry.redhat.io
  ```
- **~60 GB disk space** for the MXFP4-quantized model weights plus ~60 GB for the container image build

## Build

The build script downloads the model weights from HuggingFace and builds the container image in one step:

```bash
chmod +x build.sh
./build.sh
```

What it does:

1. Downloads `RedHatAI/gpt-oss-120b` (~65 GB) to `./model/`
2. Builds the container image `gpt-oss-120b-offline:latest`

The resulting image bundles the weights at `/models/gpt-oss-120b` and sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so vLLM never attempts to reach HuggingFace.

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
  gpt-oss-120b-offline:latest
```

The default CMD includes `--quantization mxfp4 --gpu-memory-utilization 0.92 --max-model-len 32768` for single-GPU deployment.

### With security options (SELinux hosts)

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --shm-size=8g \
  -p 8000:8000 \
  gpt-oss-120b-offline:latest
```

### Overriding vLLM arguments

The entrypoint is `vllm serve`. Append arguments after the image name to override the defaults:

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=8g \
  -p 8000:8000 \
  gpt-oss-120b-offline:latest \
  /models/gpt-oss-120b \
  --host 0.0.0.0 \
  --port 8000 \
  --quantization mxfp4 \
  --gpu-memory-utilization 0.95 \
  --max-model-len 16384
```

### Non-root verification

The container runs as UID 1001 (non-root). Verify with:

```bash
podman run --rm --entrypoint id gpt-oss-120b-offline:latest
```

### Testing the endpoint

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/gpt-oss-120b",
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
podman tag gpt-oss-120b-offline:latest \
  default-route-openshift-image-registry.apps.<cluster>/gpt-oss-inference/gpt-oss-120b-offline:latest

oc login ...
podman login -u $(oc whoami) -p $(oc whoami -t) \
  default-route-openshift-image-registry.apps.<cluster>

podman push \
  default-route-openshift-image-registry.apps.<cluster>/gpt-oss-inference/gpt-oss-120b-offline:latest
```

Or push to any registry your cluster can pull from and update the image reference in `openshift/deployment.yaml`.

### Step 2: Create the namespace and deploy

```bash
oc new-project gpt-oss-inference

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
oc get pods -l app=gpt-oss-120b
oc exec deploy/gpt-oss-120b -- id
oc logs deploy/gpt-oss-120b
oc port-forward svc/gpt-oss-120b 8000:8000
curl http://localhost:8000/v1/models
```

### GPU requirements

The deployment requests one NVIDIA GPU with 80GB VRAM via `nvidia.com/gpu: 1`. This requires the [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/index.html) installed on the cluster. The model uses MXFP4 quantization to fit within a single 80GB GPU; without quantization, tensor parallelism across multiple GPUs would be required.

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
gpt-oss/120B/
├── Containerfile            # Container build (non-root, MXFP4)
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

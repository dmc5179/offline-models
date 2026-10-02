# Qwen3-4B Offline Inference Container

Air-gapped vLLM serving of [Qwen/Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B) using the Red Hat AI Inference Server (`rhaiis/vllm-cuda-rhel9`). The model weights are baked into the container image so no network access is required at runtime.

## Prerequisites

- **Podman** (or Docker)
- **NVIDIA GPU** with drivers and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (CDI configured)
- **HuggingFace CLI** (`hf`) logged in (`hf login`)
- **Red Hat registry access** — authenticate to `registry.redhat.io` before building:
  ```bash
  podman login registry.redhat.io
  ```

## Build

The build script downloads the model weights from HuggingFace and builds the container image in one step:

```bash
chmod +x build.sh
./build.sh
```

What it does:

1. Downloads `Qwen/Qwen3-4B` (~8 GB) to `./qwen-model/`
2. Builds the container image `qwen3-4b-offline:latest`

The resulting image bundles the weights at `/models/Qwen3-4B` and sets `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so vLLM never attempts to reach HuggingFace.

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
  --shm-size=4g \
  -p 8000:8000 \
  qwen3-4b-offline:latest
```

### With security options (SELinux hosts)

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --shm-size=4g \
  -p 8000:8000 \
  qwen3-4b-offline:latest
```

### Overriding vLLM arguments

The entrypoint is `vllm serve` and the CMD defaults to `/models/Qwen3-4B --host 0.0.0.0 --port 8000`. Append arguments after the image name to override:

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --shm-size=4g \
  -p 8000:8000 \
  qwen3-4b-offline:latest \
  /models/Qwen3-4B \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.9
```

### Non-root verification

The container runs as UID 1001 (non-root). Verify with:

```bash
podman run --rm --entrypoint id qwen3-4b-offline:latest
```

### Testing the endpoint

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "/models/Qwen3-4B",
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
- **Dedicated ServiceAccount**: `vllm-inference` with a minimal Role granting only `get` on ConfigMaps (sufficient for vLLM config reads — no access to secrets, pods, or other resources).
- **Shared memory**: an `emptyDir` with `medium: Memory` mounted at `/dev/shm` replaces the `--shm-size` flag from Podman.
- **Compatible with `restricted-v2` SCC**: the default OpenShift SCC — no privileged SCC required.

### Step 1: Push the image to the internal registry

```bash
# Tag for the OpenShift internal registry
podman tag qwen3-4b-offline:latest \
  default-route-openshift-image-registry.apps.<cluster>/qwen-inference/qwen3-4b-offline:latest

# Log in to the OpenShift registry
oc login ...
podman login -u $(oc whoami) -p $(oc whoami -t) \
  default-route-openshift-image-registry.apps.<cluster>

# Push
podman push \
  default-route-openshift-image-registry.apps.<cluster>/qwen-inference/qwen3-4b-offline:latest
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
# Check pod status
oc get pods -l app=qwen3-4b

# Check the pod is running as non-root
oc exec deploy/qwen3-4b -- id

# Check logs
oc logs deploy/qwen3-4b

# Port-forward to test locally
oc port-forward svc/qwen3-4b 8000:8000

# Test
curl http://localhost:8000/v1/models
```

### GPU requirements

The deployment requests one NVIDIA GPU via `nvidia.com/gpu: 1`. This requires the [NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/openshift/latest/index.html) installed on the cluster. The GPU Operator handles device injection — no privileged SCC is needed for GPU access.

### Customization

| What | Where |
|------|-------|
| GPU count | `deployment.yaml` → `resources.limits.nvidia.com/gpu` |
| Memory limits | `deployment.yaml` → `resources.limits.memory` |
| Shared memory | `deployment.yaml` → `volumes[shm].sizeLimit` |
| vLLM arguments | `deployment.yaml` → `spec.containers[0].args` (add an `args` field to override CMD) |
| Image reference | `deployment.yaml` → `spec.containers[0].image` |
| Namespace | All YAML files → `metadata.namespace` |

## Files

```
qwen/3.8B/
├── Containerfile            # Multi-stage container build (non-root)
├── build.sh                 # Downloads model + builds image
├── README.md                # This file
└── openshift/
    ├── serviceaccount.yaml  # Dedicated SA for the workload
    ├── role.yaml            # Minimal RBAC (configmaps:get only)
    ├── rolebinding.yaml     # Binds role to SA
    ├── deployment.yaml      # Pod spec with GPU, non-root, restricted-v2 compatible
    ├── service.yaml         # ClusterIP service on port 8000
    └── route.yaml           # TLS-terminated Route (optional)
```

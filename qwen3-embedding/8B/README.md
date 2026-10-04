# Qwen3-Embedding-8B — Offline Inference Container

Air-gapped vLLM serving of [RedHatAI/Qwen3-Embedding-8B](https://huggingface.co/RedHatAI/Qwen3-Embedding-8B) on the Red Hat AI
Inference Server GA image. Model weights are baked into the container image, so no network
access is required at runtime.

An embedding model. Its repo declares `Qwen3ForCausalLM`, so vLLM would otherwise start it as a text generator — the Containerfile passes `--runner pooling --convert embed` to prevent that. Queries also need an instruction prefix that vLLM will not add for you; see `gpu-sizing.md`.

**Red Hat support level: Enabled** — Red Hat ships and supports this model, but it has not
completed the full benchmarking and accuracy-evaluation pipeline that *Validated* models
receive. See `../../model-list.csv`.

| | |
|---|---|
| Weights | 15.1 GB across 4 safetensors shard(s) |
| Minimum GPU | 24 GB (g6 / L4) |
| Serves | `/v1/embeddings` |
| Served model name | `qwen3-embedding-8b` |
| Image | `quay.io/danclark/qwen3-embedding-8b-offline` |

**Read `gpu-sizing.md` before provisioning hardware.** It has the per-context memory table,
the EC2 instance matrix, and the model-specific launch details.

## Prerequisites

- **Podman**, and an NVIDIA GPU meeting the minimum above with the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (CDI configured)
- **HuggingFace CLI** (`hf`) authenticated, with `HF_TOKEN` set
- **Red Hat registry access**: `podman login registry.redhat.io`
- Disk for the weights plus the container image build

## Build

```bash
./build.sh
```

Downloads `RedHatAI/Qwen3-Embedding-8B` to `./model/` and builds
`quay.io/danclark/qwen3-embedding-8b-offline:latest`. Override the registry with
`REGISTRY=other.registry.io/org ./build.sh`.

Weights land at `/models/Qwen3-Embedding-8B`; `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` are set so vLLM never reaches out to HuggingFace.

Build on a machine with real bandwidth — not this workstation.

## Push

```bash
podman push --authfile=/home/danclark/quay-pull-secret.json \
  quay.io/danclark/qwen3-embedding-8b-offline:latest
```

## Run locally

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/qwen3-embedding-8b-offline:latest
```

Test it:

```bash
curl -s http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-embedding-8b", "input": "example passage"}' \
  | python3 -c "import sys,json; print('dim:', len(json.load(sys.stdin)['data'][0]['embedding']))"
```

## Deploy on OpenShift with ArgoCD

`openshift/` is a kustomize overlay. Point an ArgoCD Application at it:

```yaml
  source:
    repoURL: https://gitlab.example.com/<group>/<repo>.git
    targetRevision: main
    path: qwen3-embedding/8B/openshift
  destination:
    namespace: qwen3-embedding-inference
```

Or apply directly:

```bash
oc apply -k openshift
```

The manifests run non-root under the default `restricted-v2` SCC, request one GPU, tolerate
the `nvidia.com/gpu` taint, use `strategy: Recreate` (a GPU cannot be shared between old and
new pods), and allow 12 minutes for model load via a `startupProbe`.

Verify:

```bash
oc get pods -n qwen3-embedding-inference -l app=qwen3-embedding-8b
oc logs -n qwen3-embedding-inference deploy/qwen3-embedding-8b
oc port-forward -n qwen3-embedding-inference svc/qwen3-embedding-8b 8000:8000
curl http://localhost:8000/v1/models
```

In-cluster endpoint: `http://qwen3-embedding-8b.qwen3-embedding-inference.svc.cluster.local:8000`

## Files

```
qwen3-embedding/8B/
├── Containerfile       # Non-root build; weights baked in
├── build.sh            # Downloads weights + builds image
├── gpu-sizing.md       # EC2 instance selection and memory sizing
├── README.md           # This file
└── openshift/
    ├── kustomization.yaml
    ├── serviceaccount.yaml
    ├── role.yaml
    ├── rolebinding.yaml
    ├── deployment.yaml
    └── service.yaml
```

# Gemma 4 26B-A4B Instruct FP8 — Offline Inference Container

Air-gapped vLLM serving of [RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic](https://huggingface.co/RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic) on the Red Hat AI
Inference Server GA image. Model weights are baked into the container image, so no network
access is required at runtime.

A sparse MoE (128 experts, top-8, ~4B active) with FP8-dynamic weights. Its memory curve is remarkably flat — only ~5 GB separates 8k from the full 262k context. Tool calling is not available.

**Red Hat support level: Enabled** — Red Hat ships and supports this model, but it has not
completed the full benchmarking and accuracy-evaluation pipeline that *Validated* models
receive. See `../../model-list.csv`.

| | |
|---|---|
| Weights | 28.6 GB across 1 safetensors shard(s) |
| Minimum GPU | 48 GB (g6e / L40S) |
| Serves | `/v1/chat/completions` |
| Served model name | `gemma-4-26b-a4b-it-fp8` |
| Image | `quay.io/danclark/gemma-4-26b-a4b-it-fp8-offline` |

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

Downloads `RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic` to `./model/` and builds
`quay.io/danclark/gemma-4-26b-a4b-it-fp8-offline:latest`. Override the registry with
`REGISTRY=other.registry.io/org ./build.sh`.

Weights land at `/models/gemma-4-26B-A4B-it-FP8-dynamic`; `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` are set so vLLM never reaches out to HuggingFace.

Build on a machine with real bandwidth — not this workstation.

## Push

```bash
podman push --authfile=/home/danclark/quay-pull-secret.json \
  quay.io/danclark/gemma-4-26b-a4b-it-fp8-offline:latest
```

## Run locally

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/gemma-4-26b-a4b-it-fp8-offline:latest
```

Test it:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma-4-26b-a4b-it-fp8", "messages": [{"role": "user", "content": "Hello, who are you?"}], "max_tokens": 128}' \
  | python3 -m json.tool
```

## Deploy on OpenShift with ArgoCD

`openshift/` is a kustomize overlay. Point an ArgoCD Application at it:

```yaml
  source:
    repoURL: https://gitlab.example.com/<group>/<repo>.git
    targetRevision: main
    path: gemma/4-26B-A4B-FP8/openshift
  destination:
    namespace: gemma-4-26b-a4b-inference
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
oc get pods -n gemma-4-26b-a4b-inference -l app=gemma-4-26b-a4b-it-fp8
oc logs -n gemma-4-26b-a4b-inference deploy/gemma-4-26b-a4b-it-fp8
oc port-forward -n gemma-4-26b-a4b-inference svc/gemma-4-26b-a4b-it-fp8 8000:8000
curl http://localhost:8000/v1/models
```

In-cluster endpoint: `http://gemma-4-26b-a4b-it-fp8.gemma-4-26b-a4b-inference.svc.cluster.local:8000`

## Files

```
gemma/4-26B-A4B-FP8/
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

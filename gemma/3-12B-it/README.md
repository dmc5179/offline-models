# Gemma 3 12B Instruct — Offline Inference Container

Air-gapped vLLM serving of [RedHatAI/gemma-3-12b-it](https://huggingface.co/RedHatAI/gemma-3-12b-it) on the Red Hat AI
Inference Server GA image. Model weights are baked into the container image, so no network
access is required at runtime.

Multimodal and shipped **unquantized bf16**, which is why a 12B model needs 24.4 GB — more than the 26B FP8 MoE in this repository. Tool calling is not available (no Gemma parser exists in RHAIIS 3.3).

**Red Hat support level: Enabled** — Red Hat ships and supports this model, but it has not
completed the full benchmarking and accuracy-evaluation pipeline that *Validated* models
receive. See `../../model-list.csv`.

| | |
|---|---|
| Weights | 24.4 GB across 5 safetensors shard(s) |
| Minimum GPU | 48 GB (g6e / L40S) |
| Serves | `/v1/chat/completions` |
| Served model name | `gemma-3-12b-it` |
| Image | `quay.io/danclark/gemma-3-12b-it-offline` |

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

Downloads `RedHatAI/gemma-3-12b-it` to `./model/` and builds
`quay.io/danclark/gemma-3-12b-it-offline:latest`. Override the registry with
`REGISTRY=other.registry.io/org ./build.sh`.

Weights land at `/models/gemma-3-12b-it`; `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` are set so vLLM never reaches out to HuggingFace.

Build on a machine with real bandwidth — not this workstation.

## Push

```bash
podman push --authfile=/home/danclark/quay-pull-secret.json \
  quay.io/danclark/gemma-3-12b-it-offline:latest
```

## Run locally

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/gemma-3-12b-it-offline:latest
```

Test it:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "gemma-3-12b-it", "messages": [{"role": "user", "content": "Hello, who are you?"}], "max_tokens": 128}' \
  | python3 -m json.tool
```

## Deploy on OpenShift with ArgoCD

`openshift/` is a kustomize overlay. Point an ArgoCD Application at it:

```yaml
  source:
    repoURL: https://gitlab.example.com/<group>/<repo>.git
    targetRevision: main
    path: gemma/3-12B-it/openshift
  destination:
    namespace: gemma-3-12b-inference
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
oc get pods -n gemma-3-12b-inference -l app=gemma-3-12b-it
oc logs -n gemma-3-12b-inference deploy/gemma-3-12b-it
oc port-forward -n gemma-3-12b-inference svc/gemma-3-12b-it 8000:8000
curl http://localhost:8000/v1/models
```

In-cluster endpoint: `http://gemma-3-12b-it.gemma-3-12b-inference.svc.cluster.local:8000`

## Files

```
gemma/3-12B-it/
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

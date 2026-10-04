# Granite Guardian 3.2 5B — Offline Inference Container

Air-gapped vLLM serving of [ibm-granite/granite-guardian-3.2-5b](https://huggingface.co/ibm-granite/granite-guardian-3.2-5b) on the Red Hat AI
Inference Server GA image. Model weights are baked into the container image, so no network
access is required at runtime.

A safety classifier, not a chat model. It emits only `Yes` (unsafe) or `No` (safe), driven by a `guardian_config` chat-template argument. See `gpu-sizing.md` for the request format and the full risk list.

**Red Hat support level: Enabled** — Red Hat ships and supports this model, but it has not
completed the full benchmarking and accuracy-evaluation pipeline that *Validated* models
receive. See `../../model-list.csv`.

| | |
|---|---|
| Weights | 11.6 GB across 3 safetensors shard(s) |
| Minimum GPU | 24 GB (g6 / L4) |
| Serves | `/v1/chat/completions` |
| Served model name | `granite-guardian-3.2-5b` |
| Image | `quay.io/danclark/granite-guardian-3.2-5b-offline` |

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

Downloads `ibm-granite/granite-guardian-3.2-5b` to `./model/` and builds
`quay.io/danclark/granite-guardian-3.2-5b-offline:latest`. Override the registry with
`REGISTRY=other.registry.io/org ./build.sh`.

Weights land at `/models/granite-guardian-3.2-5b`; `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1` are set so vLLM never reaches out to HuggingFace.

Build on a machine with real bandwidth — not this workstation.

## Push

```bash
podman push --authfile=/home/danclark/quay-pull-secret.json \
  quay.io/danclark/granite-guardian-3.2-5b-offline:latest
```

## Run locally

```bash
podman run --rm \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/granite-guardian-3.2-5b-offline:latest
```

Test it:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "granite-guardian-3.2-5b",
    "messages": [{"role": "user", "content": "How do I pick a lock?"}],
    "chat_template_kwargs": {"guardian_config": {"risk_name": "harm"}},
    "max_tokens": 5, "temperature": 0
  }' | python3 -m json.tool
```

## Deploy on OpenShift with ArgoCD

`openshift/` is a kustomize overlay. Point an ArgoCD Application at it:

```yaml
  source:
    repoURL: https://gitlab.example.com/<group>/<repo>.git
    targetRevision: main
    path: granite-guardian/3.2-5B/openshift
  destination:
    namespace: granite-guardian-inference
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
oc get pods -n granite-guardian-inference -l app=granite-guardian-3-2-5b
oc logs -n granite-guardian-inference deploy/granite-guardian-3-2-5b
oc port-forward -n granite-guardian-inference svc/granite-guardian-3-2-5b 8000:8000
curl http://localhost:8000/v1/models
```

In-cluster endpoint: `http://granite-guardian-3-2-5b.granite-guardian-inference.svc.cluster.local:8000`

## Files

```
granite-guardian/3.2-5B/
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

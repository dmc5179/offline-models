# Nemotron 3 Super 120B-A12B (NVFP4) — GPU sizing

```
registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-nvfp4:3.0
```

Only 8 of 88 layers are attention, so KV is 4 KiB/token — about 80x cheaper than a dense 70B.

| | |
|---|---|
| Parameters | 120B total, 12B active |
| Quantization | NVFP4 mixed precision (FP4 experts, FP8 mixer) |
| Weights | 80.4 GB |
| Image to mirror | 80.4 GB |
| Architecture | LatentMoE — Mamba-2 + MoE + attention hybrid, with MTP |
| Attention layers | 8 full, of 88 total |
| **Default context** | **262,144** (vLLM derives `--max-model-len` from this) |
| KV cache dtype | FP8 (declared in checkpoint) |
| Minimum GPU (model card) | 1x B200 or 1x DGX Spark |
| Supported microarch | A100, H100-80GB, Blackwell |
| Validated on | vLLM 0.18.0 / RHAIIS 3.4 / RHOAI 3.4 |

## Recommended: 10 concurrent users at the default 262,144 context

Each sequence needs **1.2 GB** of KV plus state to hold a full context window.

```
  80.4 GB  weights
  11.6 GB  KV for 10 users x 262,144 tokens
──────
  92.0 GB  required, before activation overhead
```

### → `p4de.24xlarge` (8x A100-80) — **$29,908/month** ($40.97/hr)

$2,991 per user per month at 10 users.

## Context length is the dominant cost lever

Same 10 users, different `--max-model-len`:

| --max-model-len | KV per user | Total needed | Instance | $/month |
|---|---|---|---|---|
| 8,192 | 0.1 GB | 82 GB | `p4de.24xlarge` (8x A100-80) | $29,908 |
| 32,768 | 0.2 GB | 83 GB | `p4de.24xlarge` (8x A100-80) | $29,908 |
| 131,072 | 0.6 GB | 87 GB | `p4de.24xlarge` (8x A100-80) | $29,908 |
| 262,144 (default) | 1.2 GB | 92 GB | `p4de.24xlarge` (8x A100-80) | $29,908 |

Most agentic traffic never fills the window. Capping `--max-model-len` at what you actually use is the single biggest saving available.

## Scaling past 10 users, at default context

| Users | Instance | $/month | $/user/month |
|---|---|---|---|
| 1 | `p4de.24xlarge` (8x A100-80) | $29,908 | $29,908 |
| 5 | `p4de.24xlarge` (8x A100-80) | $29,908 | $5,982 |
| 10 | `p4de.24xlarge` (8x A100-80) | $29,908 | $2,991 |
| 25 | `p4de.24xlarge` (8x A100-80) | $29,908 | $1,196 |
| 50 | `p4de.24xlarge` (8x A100-80) | $29,908 | $598 |
| 100 | `p4de.24xlarge` (8x A100-80) | $29,908 | $299 |

## Before you quote this

- Sizing above **guarantees** every one of the 10 users can fill the full 262,144-token window at once. vLLM allocates KV blocks on demand, so real usage is lower — but this is the figure that cannot over-commit.
- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models and no throughput, latency or concurrency figures. Latency will bind before memory does. Measure:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 10 --num-prompts 100
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.
- `hack/size-nemotron-super.py` models this one in detail.

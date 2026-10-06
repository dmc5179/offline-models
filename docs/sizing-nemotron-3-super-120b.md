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
| Max context | 262,144 |
| Minimum GPU (model card) | 1x B200 or 1x DGX Spark |
| Supported microarch | A100, H100-80GB, Blackwell |
| Validated on | vLLM 0.18.0 / RHAIIS 3.4 / RHOAI 3.4 |

## Memory per concurrent sequence

Plus 87 MB Mamba2 state per sequence (constant, `--mamba-ssm-cache-dtype float16`).

| Context | KV + state per sequence |
|---|---|
| 8,192 | 121 MB |
| 32,768 | 221 MB |
| 131,072 | 624 MB |

## What fits, at 32,768 context

Restricted to the microarchitectures the model card supports (A100, H100-80GB, Blackwell). Other GPU families are excluded even where the weights would arithmetically fit.

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 2,225 |
| `p5.48xlarge` | 8x H100 | $55.04 | 2,225 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 4,255 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 5,552 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $29,908 |
| 5 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $5,982 |
| 10 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $2,991 |
| 25 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $1,196 |
| 50 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $598 |
| 100 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $299 |
| 250 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $120 |

## The price floor

**$29,908/month** — `p4de.24xlarge` (8x A100-80) at $40.97/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 100 do. Unit cost is purely a utilisation question.

> **AWS sells no single-GPU A100-80 instance** — the p-family starts at 8. $29,908/month is unavoidable even for a single user, so this model only makes economic sense at scale.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $569.03 |
| 5 | $113.81 |
| 10 | $56.90 |
| 25 | $22.76 |
| 50 | $11.38 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.
- `hack/size-nemotron-super.py` models this one in detail.

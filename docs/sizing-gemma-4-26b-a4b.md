# Gemma 4 26B-A4B Instruct (FP8) — GPU sizing

```
registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0
```

Only 5 of 30 layers do full attention, so the memory curve is nearly flat across context length.

| | |
|---|---|
| Parameters | 26B total, ~4B active |
| Quantization | FP8 dynamic |
| Weights | 28.6 GB |
| Image to mirror | 28.7 GB |
| Architecture | Sparse MoE, multimodal, 25 sliding + 5 full attention |
| Attention layers | 5 full + 25 sliding (1024-token window), of 30 total |
| Max context | 262,144 |

## Memory per concurrent sequence


| Context | KV + state per sequence |
|---|---|
| 8,192 | 545 MB |
| 32,768 | 1,552 MB |
| 131,072 | 5,578 MB |

## What fits, at 32,768 context

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `g6e.xlarge` | 1x L40S | $1.86 | 8 |
| `g6e.2xlarge` | 1x L40S | $2.24 | 8 |
| `g6.12xlarge` | 4x L4 | $4.60 | 33 |
| `g5.12xlarge` | 4x A10G | $5.67 | 33 |
| `g6e.12xlarge` | 4x L40S | $10.49 | 90 |
| `g6e.48xlarge` | 8x L40S | $30.13 | 198 |
| `p4d.24xlarge` | 8x A100-40 | $32.77 | 160 |
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 350 |
| `p5.48xlarge` | 8x H100 | $55.04 | 350 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 639 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 824 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `g6e.xlarge` | 1x L40S | $1,358 | $1,358 |
| 5 | `g6e.xlarge` | 1x L40S | $1,358 | $272 |
| 10 | `g6.12xlarge` | 4x L4 | $3,358 | $336 |
| 25 | `g6.12xlarge` | 4x L4 | $3,358 | $134 |
| 50 | `g6e.12xlarge` | 4x L40S | $7,658 | $153 |
| 100 | `g6e.48xlarge` | 8x L40S | $21,995 | $220 |
| 250 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $120 |

## The price floor

**$1,358/month** — `g6e.xlarge` (1x L40S) at $1.86/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 8 do. Unit cost is purely a utilisation question.

> At 32,768 context this instance holds **8 concurrent sequences**. Past that you step up, and the table above shows where.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $25.83 |
| 5 | $5.17 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Variants

| Variant | Image | Size |
|---|---|---|
| 12B it NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-nvfp4:3.0` | 10.3 GB |
| 12B it FP8 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-fp8-dynamic:3.0` | 15.1 GB |
| E4B it | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-e4b-it:3.0` | 16.0 GB |
| 26B-A4B NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-26b-a4b-it-nvfp4:3.0` | 16.5 GB |
| 26B-A4B FP8 | `registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0` | 28.7 GB |

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

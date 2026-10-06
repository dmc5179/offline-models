# Gemma 4 31B Instruct (FP8) — GPU sizing

```
registry.redhat.io/rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0
```

Dense rather than MoE, and 16 KV heads — twice the per-sequence KV of the 26B MoE.

| | |
|---|---|
| Parameters | 31B dense |
| Quantization | FP8 dynamic |
| Weights | 33.3 GB |
| Image to mirror | 33.3 GB |
| Architecture | Dense multimodal, 50 sliding + 10 full attention |
| Attention layers | 10 full + 50 sliding (1024-token window), of 60 total |
| Max context | 262,144 |

## Memory per concurrent sequence


| Context | KV + state per sequence |
|---|---|
| 8,192 | 2,181 MB |
| 32,768 | 6,208 MB |
| 131,072 | 22,314 MB |

## What fits, at 32,768 context

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `g6e.xlarge` | 1x L40S | $1.86 | 1 |
| `g6e.2xlarge` | 1x L40S | $2.24 | 1 |
| `g6.12xlarge` | 4x L4 | $4.60 | 7 |
| `g5.12xlarge` | 4x A10G | $5.67 | 7 |
| `g6e.12xlarge` | 4x L40S | $10.49 | 21 |
| `g6e.48xlarge` | 8x L40S | $30.13 | 48 |
| `p4d.24xlarge` | 8x A100-40 | $32.77 | 39 |
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 86 |
| `p5.48xlarge` | 8x H100 | $55.04 | 86 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 159 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 205 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `g6e.xlarge` | 1x L40S | $1,358 | $1,358 |
| 5 | `g6.12xlarge` | 4x L4 | $3,358 | $672 |
| 10 | `g6e.12xlarge` | 4x L40S | $7,658 | $766 |
| 25 | `g6e.48xlarge` | 8x L40S | $21,995 | $880 |
| 50 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $598 |
| 100 | `p5e.48xlarge` | 8x H200 | $45,099 | $451 |
| 250 | — | — | — | exceeds every instance in this list |

## The price floor

**$1,358/month** — `g6e.xlarge` (1x L40S) at $1.86/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 1 do. Unit cost is purely a utilisation question.

> At 32,768 context this instance holds **1 concurrent sequences**. Past that you step up, and the table above shows where.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $25.83 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Variants

| Variant | Image | Size |
|---|---|---|
| 31B it NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-nvfp4:3.0` | 23.3 GB |
| 31B it FP8 block | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-fp8-block:3.0` | 33.3 GB |
| 31B it FP8 dynamic | `registry.redhat.io/rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0` | 33.3 GB |
| 31B it (bf16) | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it:3.0` | 62.6 GB |

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

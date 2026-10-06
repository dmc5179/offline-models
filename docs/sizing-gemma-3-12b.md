# Gemma 3 12B Instruct — GPU sizing

```
registry.redhat.io/rhai/modelcar-gemma-3-12b-it:3.0
```

Unquantized bf16, so a 12B model costs 24.4 GB — more than the 26B FP8 MoE below it.

| | |
|---|---|
| Parameters | 12B dense |
| Quantization | none (bf16) |
| Weights | 24.4 GB |
| Image to mirror | 24.4 GB |
| Architecture | Dense multimodal, sliding-window attention |
| Attention layers | 8 full + 40 sliding (1024-token window), of 48 total |
| Max context | 131,072 |

## Memory per concurrent sequence


| Context | KV + state per sequence |
|---|---|
| 8,192 | 872 MB |
| 32,768 | 2,483 MB |
| 131,072 | 8,925 MB |

> Red Hat's config omits `layer_types`; the 40 sliding / 8 full split is inferred from Gemma 3's documented 5:1 ratio. Verify once downloaded.

## What fits, at 32,768 context

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `g6e.xlarge` | 1x L40S | $1.86 | 7 |
| `g6e.2xlarge` | 1x L40S | $2.24 | 7 |
| `g6.12xlarge` | 4x L4 | $4.60 | 22 |
| `g5.12xlarge` | 4x A10G | $5.67 | 22 |
| `g6e.12xlarge` | 4x L40S | $10.49 | 58 |
| `g6e.48xlarge` | 8x L40S | $30.13 | 126 |
| `p4d.24xlarge` | 8x A100-40 | $32.77 | 102 |
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 220 |
| `p5.48xlarge` | 8x H100 | $55.04 | 220 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 401 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 517 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `g6e.xlarge` | 1x L40S | $1,358 | $1,358 |
| 5 | `g6e.xlarge` | 1x L40S | $1,358 | $272 |
| 10 | `g6.12xlarge` | 4x L4 | $3,358 | $336 |
| 25 | `g6e.12xlarge` | 4x L40S | $7,658 | $306 |
| 50 | `g6e.12xlarge` | 4x L40S | $7,658 | $153 |
| 100 | `g6e.48xlarge` | 8x L40S | $21,995 | $220 |
| 250 | `p5e.48xlarge` | 8x H200 | $45,099 | $180 |

## The price floor

**$1,358/month** — `g6e.xlarge` (1x L40S) at $1.86/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 7 do. Unit cost is purely a utilisation question.

> At 32,768 context this instance holds **7 concurrent sequences**. Past that you step up, and the table above shows where.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $25.83 |
| 5 | $5.17 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Variants

| Variant | Image | Size |
|---|---|---|
| 3n E4B it FP8 | `registry.redhat.io/rhelai1/modelcar-gemma-3n-e4b-it-fp8-dynamic:1.5` | 11.9 GB |
| 3n E4B it | `registry.redhat.io/rhelai1/modelcar-gemma-3n-e4b-it:1.5` | 15.8 GB |
| 12B it | `registry.redhat.io/rhai/modelcar-gemma-3-12b-it:3.0` | 24.4 GB |
| 27B it | `registry.redhat.io/rhai/modelcar-gemma-3-27b-it:3.0` | 54.9 GB |

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

# Llama 3.3 70B Instruct — GPU sizing

```
registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5
```

All 80 layers are full attention, so KV is 320 KiB/token — the most expensive per-sequence of this set.

| | |
|---|---|
| Parameters | 70B dense |
| Quantization | INT4 (w4a16) |
| Weights | 39.6 GB |
| Image to mirror | 39.6 GB |
| Architecture | Dense transformer, no sliding window |
| Attention layers | 80 full, of 80 total |
| Max context | 131,072 |

## Memory per concurrent sequence


| Context | KV + state per sequence |
|---|---|
| 8,192 | 2,684 MB |
| 32,768 | 10,737 MB |
| 131,072 | 42,950 MB |

## What fits, at 32,768 context

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `g6.12xlarge` | 4x L4 | $4.60 | 3 |
| `g5.12xlarge` | 4x A10G | $5.67 | 3 |
| `g6e.12xlarge` | 4x L40S | $10.49 | 12 |
| `g6e.48xlarge` | 8x L40S | $30.13 | 27 |
| `p4d.24xlarge` | 8x A100-40 | $32.77 | 22 |
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 49 |
| `p5.48xlarge` | 8x H100 | $55.04 | 49 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 91 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 118 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `g6.12xlarge` | 4x L4 | $3,358 | $3,358 |
| 5 | `g6e.12xlarge` | 4x L40S | $7,658 | $1,532 |
| 10 | `g6e.12xlarge` | 4x L40S | $7,658 | $766 |
| 25 | `g6e.48xlarge` | 8x L40S | $21,995 | $880 |
| 50 | `p5e.48xlarge` | 8x H200 | $45,099 | $902 |
| 100 | `p6-b200.48xlarge` | 8x B200 | $67,160 | $672 |
| 250 | — | — | — | exceeds every instance in this list |

## The price floor

**$3,358/month** — `g6.12xlarge` (4x L4) at $4.60/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 3 do. Unit cost is purely a utilisation question.

> At 32,768 context this instance holds **3 concurrent sequences**. Past that you step up, and the table above shows where.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $63.89 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Variants

| Variant | Image | Size |
|---|---|---|
| INT4 w4a16 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5` | 39.6 GB |
| FP8 dynamic | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-fp8-dynamic:1.5` | 72.7 GB |
| INT8 w8a8 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w8a8:1.5` | 72.7 GB |
| BF16 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct:1.5` | 141.1 GB |

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

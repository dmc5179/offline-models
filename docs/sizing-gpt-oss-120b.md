# GPT-OSS 120B — GPU sizing

```
registry.redhat.io/rhai/modelcar-gpt-oss-120b-essential:3.0
```

A 128-token sliding window on half the layers keeps KV small despite 36 layers.

| | |
|---|---|
| Parameters | 120B total, ~5B active |
| Quantization | MXFP4 |
| Weights | 65.2 GB |
| Image to mirror | 65.3 GB |
| Architecture | Sparse MoE, 128 experts top-4, alternating sliding/full attention |
| Attention layers | 18 full + 18 sliding (128-token window), of 36 total |
| Max context | 131,072 |

## Memory per concurrent sequence


| Context | KV + state per sequence |
|---|---|
| 8,192 | 307 MB |
| 32,768 | 1,213 MB |
| 131,072 | 4,837 MB |

## What fits, at 32,768 context

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `g6.12xlarge` | 4x L4 | $4.60 | 12 |
| `g5.12xlarge` | 4x A10G | $5.67 | 12 |
| `g6e.12xlarge` | 4x L40S | $10.49 | 85 |
| `g6e.48xlarge` | 8x L40S | $30.13 | 224 |
| `p4d.24xlarge` | 8x A100-40 | $32.77 | 175 |
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 418 |
| `p5.48xlarge` | 8x H100 | $55.04 | 418 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 788 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 1,025 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `g6.12xlarge` | 4x L4 | $3,358 | $3,358 |
| 5 | `g6.12xlarge` | 4x L4 | $3,358 | $672 |
| 10 | `g6.12xlarge` | 4x L4 | $3,358 | $336 |
| 25 | `g6e.12xlarge` | 4x L40S | $7,658 | $306 |
| 50 | `g6e.12xlarge` | 4x L40S | $7,658 | $153 |
| 100 | `g6e.48xlarge` | 8x L40S | $21,995 | $220 |
| 250 | `p4de.24xlarge` | 8x A100-80 | $29,908 | $120 |

## The price floor

**$3,358/month** — `g6.12xlarge` (4x L4) at $4.60/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 12 do. Unit cost is purely a utilisation question.

> At 32,768 context this instance holds **12 concurrent sequences**. Past that you step up, and the table above shows where.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $63.89 |
| 5 | $12.78 |
| 10 | $6.39 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Variants

| Variant | Image | Size |
|---|---|---|
| 120B essential | `registry.redhat.io/rhai/modelcar-gpt-oss-120b-essential:3.0` | 65.3 GB |
| 120B full | `registry.redhat.io/rhelai1/modelcar-gpt-oss-120b:1.5` | 195.8 GB |

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

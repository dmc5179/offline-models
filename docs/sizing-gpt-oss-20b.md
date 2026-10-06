# GPT-OSS 20B — GPU sizing

```
registry.redhat.io/rhai/modelcar-gpt-oss-20b-essential:3.0
```

The cheapest model here to host — fits a single 24 GB GPU with room for hundreds of sequences.

| | |
|---|---|
| Parameters | 21B total, ~3.6B active |
| Quantization | MXFP4 |
| Weights | 13.8 GB |
| Image to mirror | 13.8 GB |
| Architecture | Sparse MoE, 32 experts top-4, alternating sliding/full attention |
| Attention layers | 12 full + 12 sliding (128-token window), of 24 total |
| Max context | 131,072 |

## Memory per concurrent sequence


| Context | KV + state per sequence |
|---|---|
| 8,192 | 204 MB |
| 32,768 | 808 MB |
| 131,072 | 3,224 MB |

## What fits, at 32,768 context

| Instance | GPUs | $/hr | Concurrent sequences that fit |
|---|---|---|---|
| `g6.xlarge` | 1x L4 | $0.80 | 7 |
| `g5.xlarge` | 1x A10G | $1.01 | 7 |
| `g6e.xlarge` | 1x L40S | $1.86 | 35 |
| `g6e.2xlarge` | 1x L40S | $2.24 | 35 |
| `g6.12xlarge` | 4x L4 | $4.60 | 82 |
| `g5.12xlarge` | 4x A10G | $5.67 | 82 |
| `g6e.12xlarge` | 4x L40S | $10.49 | 191 |
| `g6e.48xlarge` | 8x L40S | $30.13 | 400 |
| `p4d.24xlarge` | 8x A100-40 | $32.77 | 327 |
| `p4de.24xlarge` | 8x A100-80 | $40.97 | 691 |
| `p5.48xlarge` | 8x H100 | $55.04 | 691 |
| `p5e.48xlarge` | 8x H200 | $61.78 | 1,246 |
| `p6-b200.48xlarge` | 8x B200 | $92.00 | 1,601 |

## How many users needs how big a GPU

Cheapest instance that fits each user count, at 32,768 context:

| Concurrent users | Instance | GPUs | $/month | $/user/month |
|---|---|---|---|---|
| 1 | `g6.xlarge` | 1x L4 | $584 | $584 |
| 5 | `g6.xlarge` | 1x L4 | $584 | $117 |
| 10 | `g6e.xlarge` | 1x L40S | $1,358 | $136 |
| 25 | `g6e.xlarge` | 1x L40S | $1,358 | $54 |
| 50 | `g6.12xlarge` | 4x L4 | $3,358 | $67 |
| 100 | `g6e.12xlarge` | 4x L40S | $7,658 | $77 |
| 250 | `g6e.48xlarge` | 8x L40S | $21,995 | $88 |

## The price floor

**$584/month** — `g6.xlarge` (1x L4) at $0.80/hr.

That is a floor, not a starting point. It does not fall with fewer users: you rent the whole instance whether one person uses it or 7 do. Unit cost is purely a utilisation question.

> At 32,768 context this instance holds **7 concurrent sequences**. Past that you step up, and the table above shows where.

Rough output-token cost at the floor instance, assuming 20 tok/s per active user sustained:

| Users | $/1M output tokens |
|---|---|
| 1 | $11.11 |
| 5 | $2.22 |

Agentic traffic is bursty, so divide by your duty cycle — users idle 80% of the time cost roughly a fifth of this.

## Variants

| Variant | Image | Size |
|---|---|---|
| 20B essential | `registry.redhat.io/rhai/modelcar-gpt-oss-20b-essential:3.0` | 13.8 GB |
| 20B full | `registry.redhat.io/rhelai1/modelcar-gpt-oss-20b:1.5` | 41.3 GB |

## Before you quote this

- **Memory numbers above are exact**, derived from the model's `config.json`. Throughput is not modelled here — Red Hat publishes accuracy benchmarks for its validated models but no throughput, latency or concurrency figures.
- **The sequence counts are a memory ceiling, not a capacity promise.** Latency binds long before memory does. Measure before committing:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 32 --num-prompts 200
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

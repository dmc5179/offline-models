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
| **Default context** | **131,072** (vLLM derives `--max-model-len` from this) |
| KV cache dtype | FP16 (no FP8 scheme declared) |

## Recommended: 10 concurrent users at the default 131,072 context

Each sequence needs **3.2 GB** of KV to hold a full context window.

```
  13.8 GB  weights
  32.2 GB  KV for 10 users x 131,072 tokens
──────
  46.0 GB  required, before activation overhead
```

### → EC2 instance `g6.12xlarge`

| | |
|---|---|
| **EC2 instance type** | **`g6.12xlarge`** |
| GPUs | 4x L4, 96 GB total VRAM |
| Host | 48 vCPU, 192 GiB RAM, 2x940 GB NVMe |
| On-demand | $4.60/hr — **$3,358/month** |
| Per user | $336/month at 10 users |

Tensor parallelism: `--tensor-parallel-size 4`.

## Context length is the dominant cost lever

Same 10 users, different `--max-model-len`:

| --max-model-len | KV per user | Total needed | Instance | $/month |
|---|---|---|---|---|
| 8,192 | 0.2 GB | 16 GB | `g6.xlarge` (1x L4) | $584 |
| 32,768 | 0.8 GB | 22 GB | `g6e.xlarge` (1x L40S) | $1,358 |
| 131,072 (default) | 3.2 GB | 46 GB | `g6.12xlarge` (4x L4) | $3,358 |

Most agentic traffic never fills the window. Capping `--max-model-len` at what you actually use is the single biggest saving available.

## FP8 KV cache halves it

This checkpoint declares no KV cache scheme, so vLLM keeps KV in FP16. Passing `--kv-cache-dtype fp8` halves per-sequence KV from 3.2 GB to 1.6 GB:

| | Instance | $/month |
|---|---|---|
| FP16 KV (default) | `g6.12xlarge` (4x L4) | $3,358 |
| FP8 KV | `g6e.xlarge` (1x L40S) | $1,358 |

Accuracy impact is small for most workloads but is not zero — validate against your own evals before relying on it.

## Scaling past 10 users, at default context

| Users | Instance | $/month | $/user/month |
|---|---|---|---|
| 1 | `g6.xlarge` (1x L4) | $584 | $584 |
| 5 | `g6e.xlarge` (1x L40S) | $1,358 | $272 |
| 10 | `g6.12xlarge` (4x L4) | $3,358 | $336 |
| 25 | `g6e.12xlarge` (4x L40S) | $7,658 | $306 |
| 50 | `g6e.48xlarge` (8x L40S) | $21,995 | $440 |
| 100 | `g6e.48xlarge` (8x L40S) | $21,995 | $220 |

## Variants

| Variant | Image | Size |
|---|---|---|
| 20B essential | `registry.redhat.io/rhai/modelcar-gpt-oss-20b-essential:3.0` | 13.8 GB |
| 20B full | `registry.redhat.io/rhelai1/modelcar-gpt-oss-20b:1.5` | 41.3 GB |

## Before you quote this

- Sizing above **guarantees** every one of the 10 users can fill the full 131,072-token window at once. vLLM allocates KV blocks on demand, so real usage is lower — but this is the figure that cannot over-commit.
- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models and no throughput, latency or concurrency figures. Latency will bind before memory does. Measure:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 10 --num-prompts 100
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

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
| **Default context** | **131,072** (vLLM derives `--max-model-len` from this) |
| KV cache dtype | FP16 (no FP8 scheme declared) |

## Recommended: 10 concurrent users at the default 131,072 context

Each sequence needs **4.8 GB** of KV to hold a full context window.

```
  65.2 GB  weights
  48.4 GB  KV for 10 users x 131,072 tokens
──────
 113.6 GB  required, before activation overhead
```

### → EC2 instance `g6e.12xlarge`

| | |
|---|---|
| **EC2 instance type** | **`g6e.12xlarge`** |
| GPUs | 4x L40S, 192 GB total VRAM |
| Host | 48 vCPU, 384 GiB RAM, 2x1900 GB NVMe |
| On-demand | $10.49/hr — **$7,658/month** |
| Per user | $766/month at 10 users |

Tensor parallelism: `--tensor-parallel-size 4`.

## Context length is the dominant cost lever

Same 10 users, different `--max-model-len`:

| --max-model-len | KV per user | Total needed | Instance | $/month |
|---|---|---|---|---|
| 8,192 | 0.3 GB | 68 GB | `g6.12xlarge` (4x L4) | $3,358 |
| 32,768 | 1.2 GB | 77 GB | `g6.12xlarge` (4x L4) | $3,358 |
| 131,072 (default) | 4.8 GB | 114 GB | `g6e.12xlarge` (4x L40S) | $7,658 |

Most agentic traffic never fills the window. Capping `--max-model-len` at what you actually use is the single biggest saving available.

## FP8 KV cache halves it

This checkpoint declares no KV cache scheme, so vLLM keeps KV in FP16. Passing `--kv-cache-dtype fp8` halves per-sequence KV from 4.8 GB to 2.4 GB:

| | Instance | $/month |
|---|---|---|
| FP16 KV (default) | `g6e.12xlarge` (4x L40S) | $7,658 |
| FP8 KV | `g6e.12xlarge` (4x L40S) | $7,658 |

Accuracy impact is small for most workloads but is not zero — validate against your own evals before relying on it.

## Scaling past 10 users, at default context

| Users | Instance | $/month | $/user/month |
|---|---|---|---|
| 1 | `g6.12xlarge` (4x L4) | $3,358 | $3,358 |
| 5 | `g6e.12xlarge` (4x L40S) | $7,658 | $1,532 |
| 10 | `g6e.12xlarge` (4x L40S) | $7,658 | $766 |
| 25 | `g6e.48xlarge` (8x L40S) | $21,995 | $880 |
| 50 | `g6e.48xlarge` (8x L40S) | $21,995 | $440 |
| 100 | `p4de.24xlarge` (8x A100-80) | $29,908 | $299 |

## Variants

| Variant | Image | Size |
|---|---|---|
| 120B essential | `registry.redhat.io/rhai/modelcar-gpt-oss-120b-essential:3.0` | 65.3 GB |
| 120B full | `registry.redhat.io/rhelai1/modelcar-gpt-oss-120b:1.5` | 195.8 GB |

## Before you quote this

- Sizing above **guarantees** every one of the 10 users can fill the full 131,072-token window at once. vLLM allocates KV blocks on demand, so real usage is lower — but this is the figure that cannot over-commit.
- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models and no throughput, latency or concurrency figures. Latency will bind before memory does. Measure:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 10 --num-prompts 100
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

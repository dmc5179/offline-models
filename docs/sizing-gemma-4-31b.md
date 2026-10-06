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
| **Default context** | **262,144** (vLLM derives `--max-model-len` from this) |
| KV cache dtype | FP16 (no FP8 scheme declared) |

## Recommended: 10 concurrent users at the default 262,144 context

Each sequence needs **43.8 GB** of KV to hold a full context window.

```
  33.3 GB  weights
 437.9 GB  KV for 10 users x 262,144 tokens
──────
 471.2 GB  required, before activation overhead
```

### → EC2 instance `p4de.24xlarge`

| | |
|---|---|
| **EC2 instance type** | **`p4de.24xlarge`** |
| GPUs | 8x A100-80, 640 GB total VRAM |
| Host | 96 vCPU, 1,152 GiB RAM, 8x1000 GB NVMe |
| On-demand | $40.97/hr — **$29,908/month** |
| Per user | $2,991/month at 10 users |

Tensor parallelism: `--tensor-parallel-size 8`.

## Context length is the dominant cost lever

Same 10 users, different `--max-model-len`:

| --max-model-len | KV per user | Total needed | Instance | $/month |
|---|---|---|---|---|
| 8,192 | 2.2 GB | 55 GB | `g6.12xlarge` (4x L4) | $3,358 |
| 32,768 | 6.2 GB | 95 GB | `g6e.12xlarge` (4x L40S) | $7,658 |
| 131,072 | 22.3 GB | 256 GB | `g6e.48xlarge` (8x L40S) | $21,995 |
| 262,144 (default) | 43.8 GB | 471 GB | `p4de.24xlarge` (8x A100-80) | $29,908 |

Most agentic traffic never fills the window. Capping `--max-model-len` at what you actually use is the single biggest saving available.

## FP8 KV cache halves it

This checkpoint declares no KV cache scheme, so vLLM keeps KV in FP16. Passing `--kv-cache-dtype fp8` halves per-sequence KV from 43.8 GB to 21.9 GB:

| | Instance | $/month |
|---|---|---|
| FP16 KV (default) | `p4de.24xlarge` (8x A100-80) | $29,908 |
| FP8 KV | `g6e.48xlarge` (8x L40S) | $21,995 |

Accuracy impact is small for most workloads but is not zero — validate against your own evals before relying on it.

## Scaling past 10 users, at default context

| Users | Instance | $/month | $/user/month |
|---|---|---|---|
| 1 | `g6.12xlarge` (4x L4) | $3,358 | $3,358 |
| 5 | `g6e.48xlarge` (8x L40S) | $21,995 | $4,399 |
| 10 | `p4de.24xlarge` (8x A100-80) | $29,908 | $2,991 |
| 25 | `p6-b200.48xlarge` (8x B200) | $67,160 | $2,686 |
| 50 | — | — | exceeds all listed instances |
| 100 | — | — | exceeds all listed instances |

## Variants

| Variant | Image | Size |
|---|---|---|
| 31B it NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-nvfp4:3.0` | 23.3 GB |
| 31B it FP8 block | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-fp8-block:3.0` | 33.3 GB |
| 31B it FP8 dynamic | `registry.redhat.io/rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0` | 33.3 GB |
| 31B it (bf16) | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it:3.0` | 62.6 GB |

## Before you quote this

- Sizing above **guarantees** every one of the 10 users can fill the full 262,144-token window at once. vLLM allocates KV blocks on demand, so real usage is lower — but this is the figure that cannot over-commit.
- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models and no throughput, latency or concurrency figures. Latency will bind before memory does. Measure:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 10 --num-prompts 100
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

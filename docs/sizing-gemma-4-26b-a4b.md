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
| **Default context** | **262,144** (vLLM derives `--max-model-len` from this) |
| KV cache dtype | FP16 (no FP8 scheme declared) |

## Recommended: 10 concurrent users at the default 262,144 context

Each sequence needs **10.9 GB** of KV to hold a full context window.

```
  28.6 GB  weights
 109.5 GB  KV for 10 users x 262,144 tokens
──────
 138.1 GB  required, before activation overhead
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
| 8,192 | 0.5 GB | 34 GB | `g6e.xlarge` (1x L40S) | $1,358 |
| 32,768 | 1.6 GB | 44 GB | `g6.12xlarge` (4x L4) | $3,358 |
| 131,072 | 5.6 GB | 84 GB | `g6e.12xlarge` (4x L40S) | $7,658 |
| 262,144 (default) | 10.9 GB | 138 GB | `g6e.12xlarge` (4x L40S) | $7,658 |

Most agentic traffic never fills the window. Capping `--max-model-len` at what you actually use is the single biggest saving available.

## FP8 KV cache halves it

This checkpoint declares no KV cache scheme, so vLLM keeps KV in FP16. Passing `--kv-cache-dtype fp8` halves per-sequence KV from 10.9 GB to 5.5 GB:

| | Instance | $/month |
|---|---|---|
| FP16 KV (default) | `g6e.12xlarge` (4x L40S) | $7,658 |
| FP8 KV | `g6e.12xlarge` (4x L40S) | $7,658 |

Accuracy impact is small for most workloads but is not zero — validate against your own evals before relying on it.

## Scaling past 10 users, at default context

| Users | Instance | $/month | $/user/month |
|---|---|---|---|
| 1 | `g6e.xlarge` (1x L40S) | $1,358 | $1,358 |
| 5 | `g6e.12xlarge` (4x L40S) | $7,658 | $1,532 |
| 10 | `g6e.12xlarge` (4x L40S) | $7,658 | $766 |
| 25 | `g6e.48xlarge` (8x L40S) | $21,995 | $880 |
| 50 | `p5e.48xlarge` (8x H200) | $45,099 | $902 |
| 100 | `p6-b200.48xlarge` (8x B200) | $67,160 | $672 |

## Variants

| Variant | Image | Size |
|---|---|---|
| 12B it NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-nvfp4:3.0` | 10.3 GB |
| 12B it FP8 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-fp8-dynamic:3.0` | 15.1 GB |
| E4B it | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-e4b-it:3.0` | 16.0 GB |
| 26B-A4B NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-26b-a4b-it-nvfp4:3.0` | 16.5 GB |
| 26B-A4B FP8 | `registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0` | 28.7 GB |

## Before you quote this

- Sizing above **guarantees** every one of the 10 users can fill the full 262,144-token window at once. vLLM allocates KV blocks on demand, so real usage is lower — but this is the figure that cannot over-commit.
- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models and no throughput, latency or concurrency figures. Latency will bind before memory does. Measure:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 10 --num-prompts 100
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

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
| **Default context** | **131,072** (vLLM derives `--max-model-len` from this) |
| KV cache dtype | FP16 (no FP8 scheme declared) |

## Recommended: 10 concurrent users at the default 131,072 context

Each sequence needs **42.9 GB** of KV to hold a full context window.

```
  39.6 GB  weights
 429.5 GB  KV for 10 users x 131,072 tokens
──────
 469.1 GB  required, before activation overhead
```

### → `p4de.24xlarge` (8x A100-80) — **$29,908/month** ($40.97/hr)

$2,991 per user per month at 10 users.

## Context length is the dominant cost lever

Same 10 users, different `--max-model-len`:

| --max-model-len | KV per user | Total needed | Instance | $/month |
|---|---|---|---|---|
| 8,192 | 2.7 GB | 66 GB | `g6.12xlarge` (4x L4) | $3,358 |
| 32,768 | 10.7 GB | 147 GB | `g6e.12xlarge` (4x L40S) | $7,658 |
| 131,072 (default) | 42.9 GB | 469 GB | `p4de.24xlarge` (8x A100-80) | $29,908 |

Most agentic traffic never fills the window. Capping `--max-model-len` at what you actually use is the single biggest saving available.

## FP8 KV cache halves it

This checkpoint declares no KV cache scheme, so vLLM keeps KV in FP16. Passing `--kv-cache-dtype fp8` halves per-sequence KV from 42.9 GB to 21.5 GB:

| | Instance | $/month |
|---|---|---|
| FP16 KV (default) | `p4de.24xlarge` (8x A100-80) | $29,908 |
| FP8 KV | `g6e.48xlarge` (8x L40S) | $21,995 |

Accuracy impact is small for most workloads but is not zero — validate against your own evals before relying on it.

## Scaling past 10 users, at default context

| Users | Instance | $/month | $/user/month |
|---|---|---|---|
| 1 | `g6e.12xlarge` (4x L40S) | $7,658 | $7,658 |
| 5 | `g6e.48xlarge` (8x L40S) | $21,995 | $4,399 |
| 10 | `p4de.24xlarge` (8x A100-80) | $29,908 | $2,991 |
| 25 | `p6-b200.48xlarge` (8x B200) | $67,160 | $2,686 |
| 50 | — | — | exceeds all listed instances |
| 100 | — | — | exceeds all listed instances |

## Variants

| Variant | Image | Size |
|---|---|---|
| INT4 w4a16 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5` | 39.6 GB |
| FP8 dynamic | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-fp8-dynamic:1.5` | 72.7 GB |
| INT8 w8a8 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w8a8:1.5` | 72.7 GB |
| BF16 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct:1.5` | 141.1 GB |

## Before you quote this

- Sizing above **guarantees** every one of the 10 users can fill the full 131,072-token window at once. vLLM allocates KV blocks on demand, so real usage is lower — but this is the figure that cannot over-commit.
- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models and no throughput, latency or concurrency figures. Latency will bind before memory does. Measure:

  ```bash
  vllm bench serve --model <name> --host localhost --port 8000 \
    --dataset-name random --random-input-len 4000 --random-output-len 500 \
    --max-concurrency 10 --num-prompts 100
  ```

- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.

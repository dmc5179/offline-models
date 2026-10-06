# GPU sizing and cost

One doc per self-hosted model from `../generative-ai-models.md` that has a published Red Hat
ModelCar. Each is sized to run **10 concurrent users at the model's default context window** —
not merely to load the weights.

| Model | Weights | Default context | KV/user | Instance for 10 users | $/month |
|---|---|---|---|---|---|
| [GPT-OSS 20B](sizing-gpt-oss-20b.md) | 13.8 GB | 131,072 | 3.2 GB | `g6.12xlarge` (4x L4) | **$3,358** |
| [Gemma 3 12B](sizing-gemma-3-12b.md) | 24.4 GB | 131,072 | 8.9 GB | `g6e.12xlarge` (4x L40S) | **$7,658** |
| [Gemma 4 26B-A4B FP8](sizing-gemma-4-26b-a4b.md) | 28.6 GB | 262,144 | 10.9 GB | `g6e.12xlarge` (4x L40S) | **$7,658** |
| [Gemma 4 31B FP8](sizing-gemma-4-31b.md) | 33.3 GB | 262,144 | 43.8 GB | `p4de.24xlarge` (8x A100-80) | **$29,908** |
| [Llama 3.3 70B INT4](sizing-llama-3.3-70b.md) | 39.6 GB | 131,072 | 42.9 GB | `p4de.24xlarge` (8x A100-80) | **$29,908** |
| [GPT-OSS 120B](sizing-gpt-oss-120b.md) | 65.2 GB | 131,072 | 4.8 GB | `g6e.12xlarge` (4x L40S) | **$7,658** |
| [Nemotron 3 Super 120B](sizing-nemotron-3-super-120b.md) | 80.4 GB | 262,144 | 1.2 GB | `p4de.24xlarge` (8x A100-80) | **$29,908** |

Approximate us-east-1 on-demand. Each doc breaks the same model down by context length and
user count.

## Why these are bigger than "minimum to run"

Loading the weights is the easy part. Serving 10 users who can each fill the full context
window is what sets the instance. GPT-OSS 20B loads on a single $584/month L4 — but 10 users
at its native 131,072-token context need 32 GB of KV on top of 13.8 GB of weights, so the real
answer is 4x L4 at $3,358/month. That gap is the point of these docs.

## The three levers, in order of impact

**1. Context length.** KV scales linearly with `--max-model-len` and dominates everything else
at default settings. GPT-OSS 20B for 10 users costs $584/month at 8k context and $3,358/month
at its 131k default — a 5.7x swing from one flag. Most agentic traffic never fills the window.
Cap it at what you actually use.

**2. KV cache dtype.** Only Nemotron 3 Super declares an FP8 KV cache in its checkpoint. Every
other model here keeps KV in FP16 by default, so `--kv-cache-dtype fp8` halves per-sequence KV
and frequently drops you a whole instance class. Validate accuracy against your own evals first.

**3. Attention architecture, which you cannot change but should understand.** Llama 3.3 70B is
the smallest of the large models at 39.6 GB of weights, yet the most expensive to scale: all 80
layers do full attention, so each user costs 42.9 GB of KV at 128k. Nemotron 3 Super is twice
the weights but has only 8 attention layers of 88 and an FP8 KV cache — 1.2 GB per user at
*twice* the context. Sliding-window attention in the Gemma and GPT-OSS families has the same
dampening effect. Parameter count is a poor predictor of serving cost.

## What these numbers are and are not

The memory arithmetic is exact, derived from each model's `config.json`, and it is deliberately
conservative: it guarantees all 10 users can hold a full window simultaneously. vLLM allocates
KV blocks on demand, so steady-state usage is lower — but this is the figure that cannot
over-commit.

**Throughput is not modelled.** Red Hat publishes accuracy benchmarks for its validated models
and no throughput, latency or concurrency figures anywhere, so there is nothing authoritative to
cite. Latency will bind before memory does. Measure on the candidate instance:

```bash
vllm bench serve --model <name> --host localhost --port 8000 \
  --dataset-name random --random-input-len 4000 --random-output-len 500 \
  --max-concurrency 10 --num-prompts 100
```

## Not covered

- **Laya 0.3** — vLLM cannot serve it; `config.json` declares `LayaTypedDecisions` and the card
  states it *"never generates text"*. See note B in `../generative-ai-models.md`.
- **Llama 3.2 11B Vision Instruct** — Red Hat publishes no build, so there is no ModelCar to
  size. See note C.
- Cloud-hosted entries (Bedrock, Google Cloud) — GPU sizing does not apply.

Regenerate all seven with `../hack/gen-sizing-docs.py`. `../hack/size-nemotron-super.py` does
interactive what-if on Nemotron specifically, including throughput estimation.

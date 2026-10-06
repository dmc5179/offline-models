# GPU sizing and cost

One doc per self-hosted model from `../generative-ai-models.md` that has a published Red Hat
ModelCar. Each answers the same two questions: **how big a GPU for N users**, and **what is the
price floor** below which cost does not fall.

| Model | Weights | Price floor | Floor instance | Doc |
|---|---|---|---|---|
| GPT-OSS 20B | 13.8 GB | **$584/mo** | 1x L4 | [sizing-gpt-oss-20b.md](sizing-gpt-oss-20b.md) |
| Gemma 3 12B | 24.4 GB | **$1,358/mo** | 1x L40S | [sizing-gemma-3-12b.md](sizing-gemma-3-12b.md) |
| Gemma 4 26B-A4B FP8 | 28.6 GB | **$1,358/mo** | 1x L40S | [sizing-gemma-4-26b-a4b.md](sizing-gemma-4-26b-a4b.md) |
| Gemma 4 31B FP8 | 33.3 GB | **$1,358/mo** | 1x L40S | [sizing-gemma-4-31b.md](sizing-gemma-4-31b.md) |
| Llama 3.3 70B INT4 | 39.6 GB | **$3,358/mo** | 4x L4 | [sizing-llama-3.3-70b.md](sizing-llama-3.3-70b.md) |
| GPT-OSS 120B | 65.2 GB | **$3,358/mo** | 4x L4 | [sizing-gpt-oss-120b.md](sizing-gpt-oss-120b.md) |
| Nemotron 3 Super 120B | 80.4 GB | **$29,908/mo** | 8x A100-80 | [sizing-nemotron-3-super-120b.md](sizing-nemotron-3-super-120b.md) |

Floors are at 32k context, approximate us-east-1 on-demand.

## Three things worth knowing before reading any of them

**The price floor spans 51x, and it is not proportional to model size.** GPT-OSS 20B runs on a
single L4 for $584/month. Nemotron 3 Super needs 8x A100-80 for $29,908/month — 51x the cost for
6x the weights. The jump is caused by AWS not renting single A100/H100/B200 GPUs: the p-family
starts at 8, so once a model needs that class of hardware the floor leaps.

**KV cache per sequence matters more than parameter count for scaling.** Llama 3.3 70B is only
39.6 GB of weights but 5.4 GB of KV per sequence at 32k context, because all 80 of its layers do
full attention. Nemotron 3 Super is twice the weights but has only 8 attention layers out of 88,
so it costs 0.22 GB per sequence. Llama runs out of room at ~100 concurrent users on an 8-GPU
box; Nemotron fits thousands. Sliding-window attention — in both Gemma families and GPT-OSS —
has the same effect.

**These are memory ceilings, not throughput promises.** Every number here is derived from the
model's `config.json` and is exact as far as it goes, but it tells you what *fits*, not what
*performs*. Latency binds long before memory does. Red Hat publishes accuracy benchmarks for its
validated models and no throughput, latency or concurrency figures at all, so there is nothing
authoritative to cite — you have to measure:

```bash
vllm bench serve --model <name> --host localhost --port 8000 \
  --dataset-name random --random-input-len 4000 --random-output-len 500 \
  --max-concurrency 32 --num-prompts 200
```

## Not covered

- **Laya 0.3** — vLLM cannot serve it. Its `config.json` declares `LayaTypedDecisions`, not a
  vLLM architecture, and the model card states it *"never generates text"*. See note B in
  `../generative-ai-models.md`.
- **Llama 3.2 11B Vision Instruct** — Red Hat publishes no build of this model, so there is no
  ModelCar to size. See note C.
- Cloud-hosted entries (Bedrock, Google Cloud) — not self-hosted, so GPU sizing does not apply.

`../hack/size-nemotron-super.py` models Nemotron 3 Super interactively, with throughput
estimation and GuideLLM calibration. The other models have static docs only.

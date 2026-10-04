# Choosing an EC2 GPU Instance for `Qwen3-Embedding-8B`

**Audience:** customers deploying this model on Red Hat AI Inference Server (RHAIIS) 3.3
**Container:** `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3` (vLLM `0.13.0+rhai20`)
**Red Hat support level:** Enabled (shipped and supported; not fully benchmarked)
**Last updated:** 2026-10-04

---

## TL;DR

This model fits on **one 24 GB GPU**. Sizing is the easy part.

**Recommended instance family: `g6` (NVIDIA L4, 24 GB).**

Two things will bite you, and neither is about memory:

1. **It will not serve embeddings with default flags.** The repo declares
   `Qwen3ForCausalLM`, so vLLM starts it as a text generator. You must pass
   `--runner pooling --convert embed`.
2. **Queries need an instruction prefix that vLLM will not add for you.** Getting this
   wrong silently degrades retrieval quality. See [Instruction-aware embeddings](#instruction-aware-embeddings).

---

## Measured footprint

| Property | Value |
|---|---|
| Weights on disk | **15.13 GB** across 4 safetensors shards |
| Declared architecture | `Qwen3ForCausalLM` (a causal-LM repo, *not* a dedicated embedding arch) |
| Layers / hidden | 36 / 4096 |
| Attention heads | 32 attention, 8 KV, head_dim 128 |
| Embedding dimension | 4096, with Matryoshka (MRL) support for any output dim 32–4096 |
| Pooling | last-token, then L2 normalize |
| `max_position_embeddings` | 40,960 — but the model card states **32k**; use 32768 |
| ModelCar image | `registry.redhat.io/rhelai1/modelcar-qwen3-embedding-8b` |

---

## Sizing rule

```
usable GPU memory  ≈  0.92 × nameplate memory
required memory    ≈  15.13 GB (weights) + KV cache + activations
```

KV cache is 147,456 bytes/token:

| Context | KV cache | Total needed |
|---------|----------|--------------|
| 8k      | 1.21 GB  | **~16.3 GB** |
| 32k     | 4.83 GB  | **~20.0 GB** |

**These are upper bounds.** Embedding is a prefill-only workload — there is no
autoregressive decode — so steady-state KV usage is lower than the table suggests.
Throughput is bound by batch prefill, not KV capacity.

---

## EC2 instance selection

| Family  | GPU   | Mem / GPU | Verdict | Notes |
|---------|-------|-----------|---------|-------|
| `g5`    | A10G  | 24 GB     | ✅ Yes  | Fine at 8k; tight at full 32k. |
| `g6`    | L4    | 24 GB     | ✅ **Recommended** | ~22.04 GiB usable vs ~20.0 GB at 32k. Workable but tight — drop to 8k for margin. |
| `g6e`   | L40S  | 48 GB     | ✅ Yes  | Choose this for batch-embedding throughput or comfortable 32k. |
| `p4d`   | A100  | 40 GB     | ✅ Yes  | Overkill. |
| `p4de` / `p5` / `p5e` | A100/H100/H200 | 80–141 GB | ✅ Yes | Significant overkill. |

**Tensor parallelism:** 8 KV heads divide cleanly, but embedding models run TP 1 in
practice. Leave it at the default.

---

## Launch command

The critical flags are `--runner pooling` and `--convert embed`:

```bash
podman run --rm -it \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/qwen3-embedding-8b-offline:latest
```

which runs:

```
vllm serve /models/Qwen3-Embedding-8B \
  --runner pooling \
  --convert embed \
  --served-model-name qwen3-embedding-8b \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --host 0.0.0.0 --port 8000
```

> **`--task` does not exist in RHAIIS 3.3.** Older vLLM guidance says `--task embed`.
> That flag was replaced by `--runner` (`auto|draft|generate|pooling`) and `--convert`
> (`auto|classify|embed|none|reward`). Passing `--task` will fail.

`--convert embed` is belt-and-braces: `auto` should detect the sentence-transformers
config, but being explicit removes the ambiguity.

---

## This model serves `/v1/embeddings`

Not `/v1/chat/completions`.

```bash
curl -s http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-embedding-8b", "input": "example passage"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('dim:', len(d['data'][0]['embedding']))"
```

Expect `dim: 4096`.

---

## Instruction-aware embeddings

This model uses an **asymmetric** prompt scheme. Queries get an instruction prefix;
documents get none:

```
Instruct: Given a web search query, retrieve relevant passages that answer the query
Query:{your query text}
```

**vLLM does not apply this for you.** Your client must prepend it to queries only.
Applying it to both sides, or to neither, measurably degrades retrieval quality — and it
fails silently, so you will not see an error, only worse results.

Vectors are pre-normalized (the pipeline is Transformer → last-token Pooling → Normalize),
so use **cosine similarity**, and note that cosine and dot product are equivalent here.

MRL is supported: you can truncate the 4096-dim vector to any size down to 32 and
re-normalize, trading recall for index size.

---

## Verifying before you debug

```bash
# Confirm it came up in pooling mode, not generate mode
curl -s http://localhost:8000/v1/models | python3 -m json.tool

# The real test - does the embeddings endpoint answer?
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-embedding-8b","input":"test"}'
```

A `404` on `/v1/embeddings` means the server started in generate mode — check that
`--runner pooling` actually reached the process.

---

## References

- [Red Hat AI validated models](https://docs.redhat.com/documentation/en-us/red_hat_ai/3/html-single/validated_models/index)
- [RHAIIS — vLLM server arguments](https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.3/html-single/vllm_server_arguments/index)
- [RedHatAI/Qwen3-Embedding-8B](https://huggingface.co/RedHatAI/Qwen3-Embedding-8B)

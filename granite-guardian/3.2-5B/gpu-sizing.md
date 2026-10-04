# Choosing an EC2 GPU Instance for `granite-guardian-3.2-5b`

**Audience:** customers deploying this model on Red Hat AI Inference Server (RHAIIS) 3.3
**Container:** `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3` (vLLM `0.13.0+rhai20`)
**Red Hat support level:** Enabled (shipped and supported; not fully benchmarked)
**Last updated:** 2026-10-04

---

## TL;DR

This model fits comfortably on **one 24 GB GPU**. It is the cheapest model in this
repository to host.

**Recommended instance family: `g6` (NVIDIA L4, 24 GB).**

The one thing that will surprise you is not sizing — it is that **this is not a chat
model.** See [Serving a classifier](#serving-a-classifier-not-a-chat-model).

---

## Measured footprint

| Property | Value |
|---|---|
| Weights on disk | **11.56 GB** across 3 safetensors shards |
| Architecture | `GraniteForCausalLM`, dense |
| Precision | **bf16 — not quantized** |
| Layers / hidden | 28 / 4096 |
| Attention heads | 32 attention, 8 KV, head_dim 128 |
| Max context | 131,072 |

Weight size was measured by summing the canonical `*.safetensors` blobs in the
Hugging Face repo, not estimated from parameter count.

---

## Sizing rule

```
usable GPU memory  ≈  0.92 × nameplate memory
required memory    ≈  11.56 GB (weights) + KV cache + activations
```

KV cache is 114,688 bytes/token (0.109 MiB/token):

| Context | KV cache | Total needed |
|---------|----------|--------------|
| 8k      | 0.94 GB  | **12.5 GB**  |
| 32k     | 3.76 GB  | **15.3 GB**  |
| 128k    | 15.03 GB | **26.6 GB**  |

A nameplate 24 GB L4 reports ~22.04 GiB usable, so everything up to 32k context fits
with room to spare. Only full 128k context pushes you to a larger GPU.

---

## EC2 instance selection

| Family  | GPU   | Mem / GPU | Verdict | Notes |
|---------|-------|-----------|---------|-------|
| `g5`    | A10G  | 24 GB     | ✅ Yes  | Comfortable to 32k context. |
| `g6`    | L4    | 24 GB     | ✅ **Recommended** | Cheapest option that fits. ~9.5 GB headroom at 8k. |
| `g6e`   | L40S  | 48 GB     | ✅ Yes  | Only needed if you want the full 128k context. |
| `p4d`   | A100  | 40 GB     | ✅ Yes  | Overkill. |
| `p4de`  | A100  | 80 GB     | ✅ Yes  | Significant overkill. |
| `p5`    | H100  | 80 GB     | ✅ Yes  | Significant overkill. |
| `p5e`   | H200  | 141 GB    | ✅ Yes  | Significant overkill. |

**Tensor parallelism:** 8 KV heads divide cleanly by 1/2/4/8, so TP is available — but
unnecessary. Leave `--tensor-parallel-size` at its default of 1.

---

## Serving a classifier, not a chat model

This is the operational detail that matters most, and it is easy to get wrong.

Granite Guardian is served as an ordinary causal LM on `/v1/chat/completions`, but it
**only ever emits `Yes` (unsafe) or `No` (safe)**. It is not a conversational model and
IBM's model card warns it should be used *only* in this scoring mode.

Behaviour is selected by a `guardian_config` argument consumed by the model's chat
template. Pass it through vLLM's `chat_template_kwargs`:

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "granite-guardian-3.2-5b",
    "messages": [{"role": "user", "content": "How do I pick a lock?"}],
    "chat_template_kwargs": {"guardian_config": {"risk_name": "harm"}},
    "max_tokens": 5,
    "temperature": 0,
    "logprobs": true,
    "top_logprobs": 5
  }' | python3 -m json.tool
```

Available `risk_name` values:

| Category | Risks |
|---|---|
| General | `harm` (default/umbrella), `social_bias`, `jailbreak`, `violence`, `profanity`, `sexual_content`, `unethical_behavior`, `harm_engagement`, `evasiveness` |
| RAG | `context_relevance`, `groundedness`, `answer_relevance` |
| Agentic | `function_call` |

Custom risk definitions are supported but are untested per IBM.

**Request `logprobs` if you want a score rather than a label.** IBM's cookbook thresholds
on the probability of the `Yes` token, which gives you a tunable decision boundary instead
of a hard binary. Without `logprobs` you only get the argmax token.

**English only.**

---

## Launch command

Single-GPU, on a `g6` instance:

```bash
podman run --rm -it \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/granite-guardian-3.2-5b-offline:latest
```

The baked-in default is `--max-model-len 8192 --gpu-memory-utilization 0.90`. Raise
`--max-model-len` only if you actually need long-context scoring; 8k is ample for
classifying a single turn and keeps you well inside a 24 GB GPU.

---

## Verifying before you debug

```bash
# Does the container see the GPU?
podman run --rm --device nvidia.com/gpu=all --security-opt=label=disable \
  --entrypoint=/bin/bash quay.io/danclark/granite-guardian-3.2-5b-offline:latest \
  -c "nvidia-smi -L"

# Is the served name what clients expect?
curl -s http://localhost:8000/v1/models | python3 -m json.tool
```

`--device nvidia.com/gpu=all` is what exposes the GPU. If `nvidia-smi -L` lists nothing,
fix that first — it produces an OOM that looks identical to an undersized GPU.

---

## References

- [Red Hat AI validated models](https://docs.redhat.com/documentation/en-us/red_hat_ai/3/html-single/validated_models/index)
- [RHAIIS — vLLM server arguments](https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.2/html-single/vllm_server_arguments/index)
- [RHAIIS troubleshooting guide](https://access.redhat.com/articles/7118070)
- [ibm-granite/granite-guardian-3.2-5b](https://huggingface.co/ibm-granite/granite-guardian-3.2-5b)

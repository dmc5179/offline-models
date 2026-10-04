# Choosing an EC2 GPU Instance for `gemma-4-31B-it-FP8-dynamic`

**Audience:** customers deploying this model on Red Hat AI Inference Server (RHAIIS) 3.3
**Container:** `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3` (vLLM `0.13.0+rhai20`)
**Red Hat support level:** Enabled (shipped and supported; not fully benchmarked)
**Last updated:** 2026-10-04

---

## TL;DR

This model needs **one GPU with at least 48 GB** — and it is the one model in this
repository where **context length changes the instance decision.**

- **≤ 32k context → `g6e` (L40S, 48 GB).**
- **128k+ context → `p4de` or `p5` (80 GB).**

Note the trap: **`p4d` (A100 40 GB) is not a valid step up from `g6e`** despite being a
more expensive instance class. It has *less* usable memory than an L40S after the weights
load. This is the same failure mode documented for `granite-4.0-h-small-FP8-dynamic`.

> ⚠️ **Verify architecture support before downloading.** Gemma 4 is not named in the
> RHAIIS 3.3 release notes' enabled-models list. See [Open risk](#open-risk-architecture-support-unverified).

---

## Measured footprint

| Property | Value |
|---|---|
| Weights on disk | **33.27 GB** across 2 safetensors shards |
| Architecture | `Gemma4ForConditionalGeneration`, **dense**, multimodal |
| Quantization | compressed-tensors `FP8_DYNAMIC`, channel-wise weights, per-token activations |
| Quantization exclusions | `re:.*vision.*`, `lm_head`, `re:.*embed_tokens.*` |
| Layers | 60 → **50 sliding + 10 full** (explicit `layer_types`) |
| Attention | 32 heads; sliding layers 16 KV @ head_dim 256; **global layers 4 KV @ head_dim 512** |
| Max context | **262,144** |

At 33.27 GB this is almost exactly the same footprint as
`granite-4.0-h-small-FP8-dynamic` (32.7 GB), so the same instance guidance applies — with
the important difference that this model's KV cache grows much faster.

---

## Sizing rule

```
usable GPU memory  ≈  0.92 × nameplate memory
required memory    ≈  33.27 GB (weights) + KV cache + activations
```

| Context | KV cache (hybrid) | Total needed |
|---------|-------------------|--------------|
| 8k      | 1.51 GB           | **34.8 GB**  |
| 32k     | 3.52 GB           | **36.8 GB**  |
| 128k    | 11.58 GB          | **44.8 GB**  |
| 262k    | 22.31 GB          | **55.6 GB**  |

A 48 GB L40S provides ~44.2 GB usable. That covers 32k with ~7 GB headroom, is
**marginal** at 128k (44.8 GB needed vs 44.2 GB available), and cannot do 262k.

---

## EC2 instance selection

| Family  | GPU   | Mem / GPU | Verdict | Notes |
|---------|-------|-----------|---------|-------|
| `g5`    | A10G  | 24 GB     | ❌ No   | Weights alone exceed the card. |
| `g6`    | L4    | 24 GB     | ❌ No   | Same failure. |
| `g6e`   | L40S  | 48 GB     | ✅ **Recommended up to ~32k** | ~44.2 GB usable vs 36.8 GB needed. ⚠️ Marginal at 128k, fails at 262k. |
| `p4d`   | A100  | 40 GB     | ❌ No   | ~36.8 GB usable vs 33.27 GB of weights — almost nothing left for KV. **Not a step up from `g6e`.** |
| `p4de`  | A100  | 80 GB     | ✅ Yes  | Required for 128k+. |
| `p5`    | H100  | 80 GB     | ✅ Yes  | Best throughput; required for long context. |
| `p5e`   | H200  | 141 GB    | ✅ Yes  | Comfortable at full 262k. |

**Tensor parallelism:** global layers have 4 KV heads → TP 1/2/4 divide cleanly, and
`intermediate_size` 21504 divides by 2/4/8. Single-GPU is still preferred; prefer a bigger
GPU over more GPUs.

---

## Operational notes

**Multimodal.** Bound per-request images if exposing publicly:

```
--limit-mm-per-prompt '{"image": 4}'
```

**Tool calling is not available.** RHAIIS 3.3's tool-call parser reference lists only
`hermes`, `mistral`, `llama3_json`, `internlm2`, `granite-20b-fc`, `fuyu`, `phi3_json`,
and `jamba`. There is no Gemma parser — do not copy the tool-calling overlay pattern used
by the granite and nemotron directories here.

**Chat template content format.** RHAIIS 3.3.3 requires
`--chat-template-content-format openai` for TranslateGemma; likely relevant to the Gemma
family generally. Add it if you hit chat-template errors.

---

## Launch command

```bash
podman run --rm -it \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/gemma-4-31b-it-fp8-offline:latest
```

The baked-in default is `--max-model-len 8192 --gpu-memory-utilization 0.90`, which is
safe on `g6e`. **Raising `--max-model-len` past ~32k on a 48 GB GPU will OOM** — move to
an 80 GB instance first. There is no `--quantization` flag; FP8 is detected from the
checkpoint.

---

## Open risk: architecture support unverified

The RHAIIS 3.3 release notes do **not** list Gemma 4 among newly enabled models. Red Hat's
validated-models matrix ships this model, and 3.3.3 adds TranslateGemma support implying
Gemma-family plumbing exists — but that `Gemma4ForConditionalGeneration` is registered in
vLLM `0.13.0+rhai20` was not confirmed.

Check before downloading 33 GB:

```bash
podman run --rm --entrypoint python3 \
  registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3 \
  -c "from vllm.model_executor.models.registry import ModelRegistry as R; \
      print([a for a in R.get_supported_archs() if 'Gemma' in a])"
```

---

## References

- [Red Hat AI validated models](https://docs.redhat.com/documentation/en-us/red_hat_ai/3/html-single/validated_models/index)
- [RHAIIS — vLLM server arguments](https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.3/html-single/vllm_server_arguments/index)
- [RHAIIS — tool calling](https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.3/html-single/extending_red_hat_ai_inference_server_with_tool_calling_capabilities/index)
- [How to configure RHAIIS to use multiple GPUs](https://access.redhat.com/solutions/7121107)
- [RedHatAI/gemma-4-31B-it-FP8-dynamic](https://huggingface.co/RedHatAI/gemma-4-31B-it-FP8-dynamic)

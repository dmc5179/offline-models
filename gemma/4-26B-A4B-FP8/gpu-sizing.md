# Choosing an EC2 GPU Instance for `gemma-4-26B-A4B-it-FP8-dynamic`

**Audience:** customers deploying this model on Red Hat AI Inference Server (RHAIIS) 3.3
**Container:** `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3` (vLLM `0.13.0+rhai20`)
**Red Hat support level:** Enabled (shipped and supported; not fully benchmarked)
**Last updated:** 2026-10-04

---

## TL;DR

This model needs **one GPU with at least 48 GB**.

**Recommended instance family: `g6e` (NVIDIA L40S, 48 GB).**

This is the **best long-context-per-dollar model in this repository.** Only ~5 GB
separates an 8k deployment from a full 262k one, so a single `g6e` covers the entire
context range.

> ⚠️ **Verify architecture support before downloading.** Gemma 4 is not named in the
> RHAIIS 3.3 release notes' enabled-models list. See [Open risk](#open-risk-architecture-support-unverified).

---

## Measured footprint

| Property | Value |
|---|---|
| Weights on disk | **28.64 GB** in a **single** safetensors file |
| Architecture | `Gemma4ForConditionalGeneration`, **sparse MoE**, multimodal |
| MoE | 128 experts, top-8 routing, `moe_intermediate_size` 704 → ~26B total / ~4B active |
| Quantization | compressed-tensors FP8, channel-wise weights, dynamic per-token activations |
| Quantization exclusions | all `layers.N.router.proj` are kept at full precision |
| Layers | 30 → **25 sliding + 5 full** (explicit `layer_types`) |
| Attention | 16 heads; sliding layers 8 KV @ head_dim 256; **global layers 2 KV @ head_dim 512** |
| Max context | **262,144** |

The repo total is 28.67 GB against 28.64 GB of weights, confirming there is no duplicate
weight format inflating the figure.

---

## Sizing rule

```
usable GPU memory  ≈  0.92 × nameplate memory
required memory    ≈  28.64 GB (weights) + KV cache + activations
```

Only 5 of 30 layers do global attention, and those use just 2 KV heads — which is why the
memory curve is almost flat:

| Context | KV cache (hybrid) | Total needed |
|---------|-------------------|--------------|
| 8k      | 0.38 GB           | **29.0 GB**  |
| 32k     | 0.88 GB           | **29.5 GB**  |
| 128k    | 2.89 GB           | **31.5 GB**  |
| 262k    | 5.58 GB           | **34.2 GB**  |

Going from 8k to the full 262k costs about 5 GB. Most models in this repository would
need several times that.

> `attention_k_eq_v: true` is set — K and V are identical tensors. If vLLM exploits this,
> KV halves again (0.19 GB @8k). Whether it does was not verified, so the figures above
> are conservative.

---

## EC2 instance selection

| Family  | GPU   | Mem / GPU | Verdict | Notes |
|---------|-------|-----------|---------|-------|
| `g5`    | A10G  | 24 GB     | ❌ No   | 28.64 GB of weights alone. |
| `g6`    | L4    | 24 GB     | ❌ No   | Same failure. Not tunable. |
| `g6e`   | L40S  | 48 GB     | ✅ **Recommended** | Comfortable even at the full 262k context. |
| `p4d`   | A100  | 40 GB     | ✅ Yes  | Works across the context range. |
| `p4de`  | A100  | 80 GB     | ✅ Yes  | Overkill. |
| `p5`    | H100  | 80 GB     | ✅ Yes  | Best throughput; overkill on memory. |
| `p5e`   | H200  | 141 GB    | ✅ Yes  | Significant overkill. |

**Tensor parallelism — read before scaling out.** The global attention layers have only
**2 KV heads**, so `--tensor-parallel-size > 2` forces KV-head replication and wastes
memory. Use TP 1 or 2 only. It is unnecessary anyway on a 48 GB GPU. The 128 experts
divide cleanly if expert parallelism is ever needed.

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
  quay.io/danclark/gemma-4-26b-a4b-it-fp8-offline:latest
```

The baked-in default is `--max-model-len 8192 --gpu-memory-utilization 0.90`. Given the
flat memory curve, raising `--max-model-len` substantially is cheap here — 128k costs only
about 2.5 GB more than 8k. There is **no `--quantization` flag**; FP8 is detected from the
checkpoint.

---

## Open risk: architecture support unverified

The RHAIIS 3.3 release notes do **not** list Gemma 4 among newly enabled models. Red Hat's
validated-models matrix ships this model, and 3.3.3 adds TranslateGemma support implying
Gemma-family plumbing exists — but that `Gemma4ForConditionalGeneration` is registered in
vLLM `0.13.0+rhai20` was not confirmed.

Check before downloading 28 GB:

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
- [RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic](https://huggingface.co/RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic)

# Choosing an EC2 GPU Instance for `gemma-3-12b-it`

**Audience:** customers deploying this model on Red Hat AI Inference Server (RHAIIS) 3.3
**Container:** `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3` (vLLM `0.13.0+rhai20`)
**Red Hat support level:** Enabled (shipped and supported; not fully benchmarked)
**Last updated:** 2026-10-04

---

## TL;DR

This model needs **one GPU with at least 48 GB**. A 24 GB L4 will not work.

**Recommended instance family: `g6e` (NVIDIA L40S, 48 GB).**

The counterintuitive part: this 12B model is **larger on disk than the 26B MoE** in this
repository, because it ships unquantized bf16 while the Gemma 4 models are FP8.

> ⚠️ **Verify architecture support before downloading.** Gemma 3 is not named in the
> RHAIIS 3.3 release notes' enabled-models list. See [Open risk](#open-risk-architecture-support-unverified).

---

## Measured footprint

| Property | Value |
|---|---|
| Weights on disk | **24.37 GB** across 5 safetensors shards |
| Architecture | `Gemma3ForConditionalGeneration`, dense, **multimodal** (vision config present) |
| Precision | **bf16 — not quantized** |
| Layers / hidden | 48 / 3840 |
| Attention heads | 16 attention, 8 KV, head_dim **256** |
| Max context | **Not stated** in Red Hat's config.json; upstream is gated. Gemma 3 12B is 128k upstream — treat as unconfirmed |

`head_dim` is not present in Red Hat's trimmed `config.json`; it was derived from tensor
shapes in the safetensors header (`q_proj [4096,3840]` → 16×256, `k_proj [2048,3840]` →
8×256). The weight total was confirmed against `model.safetensors.index.json`
(`total_size` = 24,374,650,080 bytes — exact match).

---

## Sizing rule

```
usable GPU memory  ≈  0.92 × nameplate memory
required memory    ≈  24.37 GB (weights) + KV cache + activations
```

Gemma 3 uses sliding-window attention, so naive KV math badly overstates requirements.
Assuming the documented 5 local : 1 global layer ratio (8 global / 40 sliding):

| Context | KV cache (hybrid) | Total needed |
|---------|-------------------|--------------|
| 8k      | 0.87 GB           | **25.2 GB**  |
| 32k     | 2.48 GB           | **26.9 GB**  |
| 128k    | 8.93 GB           | **33.3 GB**  |

A nameplate 24 GB L4 reports ~22.04 GiB usable. The weights alone are 24.37 GB, so
**no amount of tuning makes a 24 GB GPU work.**

> ⚠️ **The 5:1 ratio is an assumption for this model.** Red Hat's config.json omits
> `sliding_window_pattern` / `layer_types` here, unlike both Gemma 4 repos which state it
> explicitly. If the assumption is wrong, worst case is the naive all-global figure —
> 3.22 GB @8k rising to 51.5 GB @128k — which would make 128k infeasible below 80 GB.
> **Check `layer_types` in the downloaded config before committing to a long-context
> deployment.**

---

## EC2 instance selection

| Family  | GPU   | Mem / GPU | Verdict | Notes |
|---------|-------|-----------|---------|-------|
| `g5`    | A10G  | 24 GB     | ❌ No   | 24.37 GB of weights vs ~22.1 GB usable. |
| `g6`    | L4    | 24 GB     | ❌ No   | Same failure. Not tunable. |
| `g6e`   | L40S  | 48 GB     | ✅ **Recommended** | ~19 GB headroom at 8k. |
| `p4d`   | A100  | 40 GB     | ⚠️ Marginal | Works to ~32k; tight at 128k. |
| `p4de`  | A100  | 80 GB     | ✅ Yes  | Comfortable at any context. |
| `p5`    | H100  | 80 GB     | ✅ Yes  | Best throughput. |
| `p5e`   | H200  | 141 GB    | ✅ Yes  | Overkill. |

**Tensor parallelism:** 8 KV heads divide cleanly by 1/2/4/8, but TP is unnecessary on a
single 48 GB GPU.

---

## Operational notes

**Multimodal.** A `vision_config` is present, so image inputs are supported. Bound the
per-request image count if you expose this publicly:

```
--limit-mm-per-prompt '{"image": 4}'
```

**Tool calling is not available.** RHAIIS 3.3's tool-call parser reference lists only
`hermes`, `mistral`, `llama3_json`, `internlm2`, `granite-20b-fc`, `fuyu`, `phi3_json`,
and `jamba`. There is no Gemma parser, so do not copy the tool-calling overlay pattern
used by the granite and nemotron directories in this repository.

**Chat template content format.** RHAIIS 3.3.3 requires
`--chat-template-content-format openai` for TranslateGemma; it is likely relevant to the
Gemma family generally. Add it if you see chat-template errors.

---

## Launch command

```bash
podman run --rm -it \
  --device nvidia.com/gpu=all \
  --security-opt=label=disable \
  --ipc=host --shm-size=8g \
  -p 8000:8000 \
  quay.io/danclark/gemma-3-12b-it-offline:latest
```

The baked-in default is `--max-model-len 8192 --gpu-memory-utilization 0.90`. 8192 is
deliberately conservative because the true maximum context is unconfirmed.

---

## Open risk: architecture support unverified

The RHAIIS 3.3 release notes do **not** list Gemma 3 among newly enabled models. Red Hat's
validated-models matrix does ship `RedHatAI/gemma-3-12b-it`, and 3.3.3 adds TranslateGemma
support which implies Gemma-family plumbing exists — but that
`Gemma3ForConditionalGeneration` is registered in vLLM `0.13.0+rhai20` was not confirmed.

Settle this with one command before spending bandwidth on a 24 GB download:

```bash
podman run --rm --entrypoint python3 \
  registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3 \
  -c "from vllm.model_executor.models.registry import ModelRegistry as R; \
      print([a for a in R.get_supported_archs() if 'Gemma' in a])"
```

If `Gemma3ForConditionalGeneration` is absent, this model cannot be served on the GA image
and no flag works around it.

---

## References

- [Red Hat AI validated models](https://docs.redhat.com/documentation/en-us/red_hat_ai/3/html-single/validated_models/index)
- [RHAIIS — vLLM server arguments](https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.3/html-single/vllm_server_arguments/index)
- [RHAIIS — tool calling](https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.3/html-single/extending_red_hat_ai_inference_server_with_tool_calling_capabilities/index)
- [RedHatAI/gemma-3-12b-it](https://huggingface.co/RedHatAI/gemma-3-12b-it)

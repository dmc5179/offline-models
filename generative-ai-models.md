# Required Generative AI Models

This document tracks the generative AI models required for the project.

## Priority Levels

- **Default**: Standard priority for models without a specific ranking.
- **Critical**: Required for core project functionality.
- **High**: Important for major features or workflows.
- **Medium**: Useful for supporting features or preferred workflows.
- **Low**: Optional or experimental.

## Provider Types

- **AWS Bedrock**: A cloud service provider used to access and run managed generative AI models.
- **AWS Bedrock-Mantle**: A cloud service provider used to access and run managed generative AI models.
- **Google Cloud**: Google's cloud service for accessing managed generative AI models.
- **Self-Hosted**: Models hosted internally within the Red Hat OpenShift cluster.
- **Unknown Cloud Provider**: A cloud-hosted model whose provider has not yet been determined.

## Evolving Model List

| Model Name | Version | Provider | Priority | Red Hat ModelCar (OCI image) |
| --- | --- | --- | --- | --- |
| GPT | 5.4 | AWS Bedrock-Mantle | High | n/a — not self-hosted |
| GPT Terra | 5.6 | AWS Bedrock-Mantle | High | n/a — not self-hosted |
| Nemotron3 | 120B Super | Self-Hosted | High | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-nvfp4:3.0` — **3 variants, see A** |
| GPT Astra | 6.0 | AWS Bedrock-Mantle | Default | n/a — not self-hosted |
| GPT Luna | 5.6 | AWS Bedrock-Mantle | Default | n/a — not self-hosted |
| GPT Sol | 5.6 | AWS Bedrock-Mantle | Default | n/a — not self-hosted |
| Nemotron3 | 120B Super | AWS Bedrock-Mantle | Default | n/a — not self-hosted (but see A if it moves in-house) |
| Laya | 0.3 | Self-Hosted | Low | ⚠️ **Not servable by vLLM** — a ModelCar would not help. See note B |
| Llama | 3.2 11B Vision Instruct | Self-Hosted | Low | ❌ **Must build ourselves** — Red Hat publishes none. See note C |
| Llama | 3.3 70B | Self-Hosted | Low | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5` — **4 variants, see D** |
| Gemma | 3 | Self-Hosted | Low | `registry.redhat.io/rhai/modelcar-gemma-3-12b-it:3.0` — **3 variants, see E** |
| Gemma | 4 | Self-Hosted | Low | `registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0` — **11 variants, see F** |
| Gemini | 2.5 Flash | Google Cloud | High | n/a — not self-hosted |
| GPT | 5.2 | AWS Bedrock | Low | n/a — not self-hosted |
| GPT OSS | 120B | Self-Hosted | Low | `registry.redhat.io/rhai/modelcar-gpt-oss-120b-essential:3.0` — **2 variants, see G** |
| GPT OSS | 20B | Self-Hosted | Low | `registry.redhat.io/rhai/modelcar-gpt-oss-20b-essential:3.0` — **2 variants, see G** |
| Grok | 4 | Unknown Cloud Provider | Low | n/a — not self-hosted |
| Grok | 4 Fast | Unknown Cloud Provider | Low | n/a — not self-hosted |

**All paths verified against `registry.redhat.io` on 2026-10-06.** Red Hat's published
*Validated models* documentation tables undercount what is actually in the registry, so every entry
here was confirmed by probing the registry directly rather than read off a table. Sizes are the
compressed image, which is what you transfer when mirroring — not the GPU footprint.

### A. Nemotron3 120B Super — 3 variants

| Variant | Image | Size | Minimum GPU |
| --- | --- | --- | --- |
| NVFP4 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-nvfp4:3.0` | 80.4 GB | 1× H200 (141 GB) or 2× 80 GB |
| FP8 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-fp8:3.0` | 128.4 GB | 2× 80 GB |
| BF16 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-bf16:3.0` | 247.3 GB | 4× 80 GB |

NVFP4 does **not** fit a single 80 GB card — usable memory is ~0.92 × nameplate, so 73.6 GB against
80.4 GB of weights. Despite the name it is `MIXED_PRECISION`: FP4 on the 40,961 MoE expert layers,
FP8 on the 139 Mamba mixer layers, FP8 KV cache.

Two risks to settle before committing: all three use `modelopt` quantization rather than the
`compressed-tensors` used elsewhere in this estate, and `MIXED_PRECISION` support in the GA runtime
(vLLM `0.13.0+rhai20`) is unverified. NVFP4 is also a Blackwell-native format — confirm it runs on
the GPUs you actually have.

If the goal is parity with the Bedrock-hosted copy of this model: **Bedrock does not publish its
serving precision**, so an exact match cannot be determined from outside. BF16 is the unquantized
reference and therefore closest to whatever Bedrock runs, but at 4× 80 GB that is an expensive way
to buy an unverifiable assumption. Comparing outputs from both on the same prompts is cheaper and
actually conclusive.

### B. Laya 0.3 — not a vLLM model

Building a ModelCar for Laya would not produce anything servable. The root `config.json` in both
`convaiinnovations/laya` and `convaiinnovations/laya-multilingual` is a stub declaring
`architectures: ["LayaTypedDecisions"]` — their own class, not a vLLM-registered architecture, with
no `hidden_size`, `vocab_size` or layer counts for vLLM to instantiate. The model card states it
*"never generates text"*; it is a non-autoregressive classifier loaded via `from laya import Router`,
their own pip package. A ModelCar carries weights only, and these need custom Python at inference time.

Also worth confirming with the customer: **"0.3" is the Python package version, not a model version.**
Their model card notes *"What's new in laya 0.3.20 — The checkpoints themselves are unchanged."*

There is a serving path, but it is not ours: the project ships its own container exposing
`/v1/systemone`, which the docs call *"Jev-compatible"* — explicitly not OpenAI-compatible, so it
would not work with OpenShift Lightspeed or anything expecting chat completions. If this model is
genuinely needed, the work is packaging **their runtime container**, which is a separate stack.

### C. Llama 3.2 11B Vision Instruct — must build

No ModelCar exists, and the reason is more fundamental than a missing image: **Red Hat does not
publish this model at all.** A Hugging Face search for `Llama-3.2-11B-Vision` returns only
`meta-llama/*` and third-party repackagings — there is no `RedHatAI/` build of it.

Thirty-six candidate registry paths were probed across both namespaces, all three naming
conventions, all tag variants, and the base plus `fp8-dynamic`, `quantized-w4a16` and
`quantized-w8a8` suffixes. None resolved.

This is the only model on the list that genuinely requires building a ModelCar ourselves, and doing
so means packaging upstream Meta weights — which carries **no Red Hat support statement**, unlike
every other self-hosted entry here. Worth confirming the customer needs this specific model before
committing to it; `Llama-4-Scout-17B-16E-Instruct` is a supported vision-capable alternative with
published ModelCars.

### D. Llama 3.3 70B — 4 variants

| Variant | Image | Size |
| --- | --- | --- |
| INT4 (w4a16) | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5` | 39.6 GB |
| FP8 dynamic | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-fp8-dynamic:1.5` | 72.7 GB |
| INT8 (w8a8) | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w8a8:1.5` | 72.7 GB |
| BF16 | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct:1.5` | 141.1 GB |

w4a16 is the only one that fits a single 80 GB GPU with real KV headroom; the two 72.7 GB variants
are borderline against ~73.6 GB usable.

### E. Gemma 3 — 3 variants, and "Gemma 3" needs pinning down

| Variant | Image | Size |
| --- | --- | --- |
| 3n E4B it, FP8 | `registry.redhat.io/rhelai1/modelcar-gemma-3n-e4b-it-fp8-dynamic:1.5` | 11.9 GB |
| 3n E4B it | `registry.redhat.io/rhelai1/modelcar-gemma-3n-e4b-it:1.5` | 15.8 GB |
| 3 12B it | `registry.redhat.io/rhai/modelcar-gemma-3-12b-it:3.0` | 24.4 GB |
| 3 27B it | `registry.redhat.io/rhai/modelcar-gemma-3-27b-it:3.0` | 54.9 GB |

The list says only "Gemma 3" — worth asking which size the customer means.

### F. Gemma 4 — 11 variants, all available

| Variant | Image | Size |
| --- | --- | --- |
| 12B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-nvfp4:3.0` | 10.3 GB |
| 12B it, FP8 dynamic | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-fp8-dynamic:3.0` | 15.1 GB |
| E4B it | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-e4b-it:3.0` | 16.0 GB |
| 26B-A4B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-26b-a4b-it-nvfp4:3.0` | 16.5 GB |
| 31B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-nvfp4:3.0` | 23.3 GB |
| **26B-A4B it, FP8 dynamic** | `registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0` | 28.7 GB |
| 31B it, FP8 block | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-fp8-block:3.0` | 33.3 GB |
| 31B it, FP8 dynamic | `registry.redhat.io/rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0` | 33.3 GB |
| 26B-A4B it (unquantized) | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-26b-a4b-it:3.0` | 51.7 GB |
| 31B it (unquantized) | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it:3.0` | 62.6 GB |
| 31B (base) | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b:3.0` | 62.6 GB |

Every Gemma 4 variant listed under *Models Available in Registry* has a ModelCar — nothing here
needs building. Note the two naming conventions in the table above: the FP8-dynamic pair use
`modelcar-<model>`, everything else uses `modelcar-redhatai-<model>`. See *Naming conventions* below.

### G. GPT OSS — 2 variants each, and the size difference is dramatic

| Variant | Image | Size |
| --- | --- | --- |
| 20B essential | `registry.redhat.io/rhai/modelcar-gpt-oss-20b-essential:3.0` | 13.8 GB |
| 20B full | `registry.redhat.io/rhelai1/modelcar-gpt-oss-20b:1.5` | 41.3 GB |
| 120B essential | `registry.redhat.io/rhai/modelcar-gpt-oss-120b-essential:3.0` | 65.3 GB |
| 120B full | `registry.redhat.io/rhelai1/modelcar-gpt-oss-120b:1.5` | 195.8 GB |

The non-`essential` images carry roughly three copies of the weights in different checkpoint
formats. For mirroring across an air gap the `essential` variants transfer a third of the bytes for
the same model.

### Naming conventions — there are three, and they are not interchangeable

Red Hat's ModelCar repositories do not follow one pattern. A path that looks obviously correct can
404 while the same model exists under a different form. All three are live:

| Pattern | Example |
| --- | --- |
| `rhelai1/modelcar-<model>:1.5` | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct:1.5` |
| `rhai/modelcar-<model>:3.0` | `registry.redhat.io/rhai/modelcar-gemma-3-12b-it:3.0` |
| `rhai/modelcar-<org>-<model>:3.0` | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-nvfp4:3.0` |

The `rhai` namespace also serves each of its repositories *without* the `modelcar-` prefix
(`rhai/openai-gpt-oss-safeguard-120b:3.0`) and under both `:1.5` and `:3.0`, plus build-stamped
tags like `:3.0-1782241594` and a floating `:latest`. Prefer the plain `:3.0` or `:1.5` tag; the
build stamp pins an exact build if you need reproducibility.

Because of this, **absence of a path is not evidence that a model is unavailable** until all three
patterns have been tried. An earlier pass of this document wrongly reported several Gemma 4
variants as needing to be built because only the first two patterns were probed.

### Caveats that apply to the self-hosted rows

**Gemma cannot do tool calling.** RHOAI 3.5 ships no Gemma tool-call parser, so the Gemma 3 and
Gemma 4 entries are usable for chat and RAG but cannot drive agentic workloads or OpenShift
Lightspeed cluster interaction.

**Gemma architecture support in the GA runtime is unverified.** The RHAIIS release notes do not list
Gemma 3 or Gemma 4 among enabled models. Confirm before relying on them:

```bash
podman run --rm --entrypoint python3 registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3 \
  -c "from vllm.model_executor.models.registry import ModelRegistry as R; \
      print([a for a in R.get_supported_archs() if 'Gemma' in a])"
```

## Models Available in Registry

All paths verified against `registry.redhat.io`. **45 of 47** entries have a published ModelCar; sizes are the compressed image, which is what you transfer when mirroring. See *Naming conventions* above — these span all three forms.

| Model Name | Version | Red Hat ModelCar (OCI image) | Image size |
| --- | --- | --- | --- |
| DiffusionGemma | 26B-A4B it, FP8-dynamic | `registry.redhat.io/rhai/modelcar-redhatai-diffusiongemma-26b-a4b-it-fp8-dynamic:3.0` | 27.2 GB |
| DiffusionGemma | 26B-A4B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-diffusiongemma-26b-a4b-it-nvfp4:3.0` | 18.1 GB |
| Gemma 3n | E4B it, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-gemma-3n-e4b-it-fp8-dynamic:1.5` | 11.9 GB |
| Gemma 4 | 12B it, FP8-dynamic | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-fp8-dynamic:3.0` | 15.1 GB |
| Gemma 4 | 12B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-12b-it-nvfp4:3.0` | 10.3 GB |
| Gemma 4 | 26B-A4B it | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-26b-a4b-it:3.0` | 51.7 GB |
| Gemma 4 | 26B-A4B it, FP8-dynamic | `registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0` | 28.7 GB |
| Gemma 4 | 26B-A4B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-26b-a4b-it-nvfp4:3.0` | 16.5 GB |
| Gemma 4 | 31B it | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it:3.0` | 62.6 GB |
| Gemma 4 | 31B it, FP8-block | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-fp8-block:3.0` | 33.3 GB |
| Gemma 4 | 31B it, FP8-dynamic | `registry.redhat.io/rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0` | 33.3 GB |
| Gemma 4 | 31B it, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-31b-it-nvfp4:3.0` | 23.3 GB |
| Gemma 4 | E4B it | `registry.redhat.io/rhai/modelcar-redhatai-gemma-4-e4b-it:3.0` | 16.0 GB |
| Granite 3.1 | 8B instruct | `registry.redhat.io/rhelai1/modelcar-granite-3-1-8b-instruct:1.5` | 16.4 GB |
| Granite 3.1 | 8B instruct, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-granite-3-1-8b-instruct-fp8-dynamic:1.5` | 8.8 GB |
| Granite 3.1 | 8B instruct, INT4 (w4a16) | `registry.redhat.io/rhelai1/modelcar-granite-3-1-8b-instruct-quantized-w4a16:1.5` | 4.9 GB |
| Granite 3.1 | 8B instruct, INT8 (w8a8) | `registry.redhat.io/rhelai1/modelcar-granite-3-1-8b-instruct-quantized-w8a8:1.5` | 8.8 GB |
| Granite 4.0 | h-small, FP8-dynamic | `registry.redhat.io/rhai/modelcar-granite-4-0-h-small-fp8-dynamic:3.0` | 32.7 GB |
| Granite 4.0 | h-tiny, FP8-dynamic | `registry.redhat.io/rhai/modelcar-granite-4-0-h-tiny-fp8-dynamic:3.0` | 7.1 GB |
| Llama 3.1 | 8B Instruct | `registry.redhat.io/rhelai1/modelcar-llama-3-1-8b-instruct:1.5` | 16.1 GB |
| Llama 3.1 Nemotron | 70B Instruct HF | `registry.redhat.io/rhelai1/modelcar-llama-3-1-nemotron-70b-instruct-hf:1.5` | 141.1 GB |
| Llama 3.1 Nemotron | 70B Instruct HF, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-llama-3-1-nemotron-70b-instruct-hf-fp8-dynamic:1.5` | 72.7 GB |
| Llama 3.3 | 70B Instruct | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct:1.5` | 141.1 GB |
| Llama 3.3 | 70B Instruct, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-fp8-dynamic:1.5` | 72.7 GB |
| Llama 3.3 | 70B Instruct, INT4 (w4a16) | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5` | 39.6 GB |
| Llama 3.3 | 70B Instruct, INT8 (w8a8) | `registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w8a8:1.5` | 72.7 GB |
| Llama 4 Maverick | 17B-128E Instruct | `registry.redhat.io/rhelai1/modelcar-llama-4-maverick-17b-128e-instruct:1.5` | 803.2 GB |
| Llama 4 Maverick | 17B-128E Instruct, FP8 | `registry.redhat.io/rhelai1/modelcar-llama-4-maverick-17b-128e-instruct-fp8:1.5` | 416.8 GB |
| Llama 4 Scout | 17B-16E Instruct | `registry.redhat.io/rhelai1/modelcar-llama-4-scout-17b-16e-instruct:1.5` | 217.3 GB |
| Llama 4 Scout | 17B-16E Instruct, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-llama-4-scout-17b-16e-instruct-fp8-dynamic:1.5` | 120.7 GB |
| Llama 4 Scout | 17B-16E Instruct, INT4 (w4a16) | `registry.redhat.io/rhelai1/modelcar-llama-4-scout-17b-16e-instruct-quantized-w4a16:1.5` | 64.9 GB |
| Meta Llama 3.1 | 8B Instruct, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-llama-3-1-8b-instruct-fp8-dynamic:1.5` | 9.1 GB |
| Nemotron 3 Nano | 30B-A3B, FP8 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-nano-30b-a3b-fp8:3.0` | 32.7 GB |
| Nemotron 3 Super | 120B-A12B, BF16 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-bf16:3.0` | 247.3 GB |
| Nemotron 3 Super | 120B-A12B, FP8 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-fp8:3.0` | 128.4 GB |
| Nemotron 3 Super | 120B-A12B, NVFP4 | `registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-nvfp4:3.0` | 80.4 GB |
| Nemotron 3 Ultra | 550B-A55B, FP8-block | Red Hat does not ship a ModelCar for this model | — |
| Nemotron 3 Ultra | 550B-A55B, FP8-dynamic | `registry.redhat.io/rhai/modelcar-redhatai-nvidia-nemotron-3-ultra-550b-a55b-fp8-dynamic:3.0` | 563.3 GB |
| Nemotron 3 Ultra | 550B-A55B, NVFP4 | `registry.redhat.io/rhai/modelcar-redhatai-nvidia-nemotron-3-ultra-550b-a55b-nvfp4:3.0` | 352.4 GB |
| Nemotron 3 Ultra | 550B-A55B, INT4 (w4a16) | Red Hat does not ship a ModelCar for this model | — |
| Nemotron Nano | 9B v2, FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-nvidia-nemotron-nano-9b-v2-fp8-dynamic:1.5` | 10.1 GB |
| Phi 4 | base | `registry.redhat.io/rhelai1/modelcar-phi-4:1.5` | 29.3 GB |
| Phi 4 | FP8-dynamic | `registry.redhat.io/rhelai1/modelcar-phi-4-fp8-dynamic:1.5` | 15.7 GB |
| Phi 4 mini | instruct, FP8-dynamic | `registry.redhat.io/rhai/modelcar-phi-4-mini-instruct-fp8-dynamic:3.0` | 5.7 GB |
| Phi 4 | INT4 (w4a16) | `registry.redhat.io/rhelai1/modelcar-phi-4-quantized-w4a16:1.5` | 9.1 GB |
| Phi 4 | INT8 (w8a8) | `registry.redhat.io/rhelai1/modelcar-phi-4-quantized-w8a8:1.5` | 15.7 GB |
| Phi 4 reasoning | FP8-dynamic | `registry.redhat.io/rhai/modelcar-phi-4-reasoning-fp8-dynamic:3.0` | 15.7 GB |

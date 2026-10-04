# Offline Models

Air-gapped vLLM model containers for disconnected OpenShift deployment.

## Structure

Each model family gets a top-level directory with size/variant subdirectories containing:
- `Containerfile` — bakes model weights into the vLLM base image
- `build.sh` — downloads weights from HuggingFace and builds the container
- `README.md` — usage and deployment docs
- `openshift/` — kustomize-based OpenShift deployment manifests (ArgoCD-ready)

## Models

| Directory | HuggingFace Repo | Registry Image | Notes |
|---|---|---|---|
| `gpt-oss/120B` | `RedHatAI/gpt-oss-120b` | `quay.io/danclark/gpt-oss-120b-offline` | MXFP4 quant, 1x 80GB GPU |
| `qwen/32B` | `Qwen/Qwen3-32B` | `quay.io/danclark/qwen3-32b-offline` | 1x GPU, 96Gi mem |
| `qwen/3.8B` | `Qwen/Qwen3-4B` | `quay.io/danclark/qwen3-4b-offline` | 1x GPU, 16Gi mem |
| `granite/4.0-h-small-FP8` | `RedHatAI/granite-4.0-h-small-FP8-dynamic` | `quay.io/danclark/granite-4.0-h-small-fp8-offline` | FP8 dynamic, 1x GPU, 48Gi mem |
| `nemotron/70B-FP8` | `RedHatAI/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic` | `quay.io/danclark/nemotron-70b-fp8-offline` | FP8 dynamic, 1x 80GB GPU, tight fit |

## Model support status

`model-list.csv` tracks every candidate model in `model-list.txt` against Red Hat's official
support posture. Source of truth: **"Choose a validated model for reliable serving" — Red Hat AI 3**,
https://docs.redhat.com/documentation/en-us/red_hat_ai/3/html-single/validated_models/index

Red Hat defines exactly **two** support levels, and *both* mean Red Hat ships and supports the model —
the difference is depth of testing, not whether support exists:

| Level | Meaning |
|---|---|
| **Validated** | Benchmarked with GuideLLM (performance) + LM Evaluation Harness (accuracy) on specific platform combinations. |
| **Enabled** | Shipped as ModelCar images with architecturally compatible configs, but has *not* completed the full benchmarking/accuracy pipeline. Covers embedding, safety/guard, security, reasoning. |

Current tally of the 135 candidates: **94 Validated, 5 Enabled, 4 unclear, 32 not listed.**

Two files:
- `model-list.csv` — all 135, ordered: Enabled first, then Validated ascending by weight size,
  then unclear, then not-listed.
- `model-list-supported.csv` — the 99 buildable rows only (Enabled + Validated), same ordering.
  This is the file to drive the build pipeline from; smallest models first so early runs are cheap.

**How `weights_gb` is measured.** Summed from the actual `*.safetensors` file sizes in the HF repo
tree, restricted to the canonical shard set (`model.safetensors` / `model-NNNNN-of-NNNNN.safetensors`).
Two traps this avoids, both of which produced badly wrong numbers before:
- *Do not* compute bytes from `safetensors.parameters` dtype counts. For `w4a16` checkpoints HF
  reports the **logical** parameter count against an `I32` dtype, overstating size by up to 7.5×
  (Kimi-K2 came out as 4098 GB instead of 547 GB).
- *Do not* use the `usedStorage` field. Repos that ship duplicate formats inflate it — Mistral repos
  carry a `consolidated.safetensors` beside the sharded copy (2× overcount) and
  `openai/whisper-large-v3` carries fp32 + fp16 + `.bin` copies (3× overcount).

The method is validated against a known-good figure: `granite-4.0-h-small-FP8-dynamic` measures
32.7 GB across 7 shards, matching the independently-derived ~33 GB in the GPU sizing research doc.

Caveats when reading the CSV:
- Red Hat's own table is case-inconsistent (`FP8-Dynamic` vs `FP8-dynamic`); matching is case-insensitive
  and `red_hat_model_id` shows the exact doc spelling.
- For upstream entries (`google/...`), Red Hat validates *its own rebuild* under `RedHatAI/`, not the
  upstream repo. The `notes` column flags these.
- 4 models sit in the HF monthly validated-models collection but are absent from the docs support
  matrix (`Validated (HF collection only)`) — the HF collection and the docs do not perfectly agree.
  Treat the docs matrix as authoritative for support claims.
- A base model being listed does not imply its quantized variants are, and vice versa
  (e.g. `granite-4.0-h-small-FP8-dynamic` is Validated; plain `granite-4.0-h-small` is not listed).
- `RedHatAI/Llama-3.1-8B-Instruct-essential` is in the candidate list but the HF repo is not
  accessible (404). The `gpt-oss-*-essential` repos do exist.

## Build & Push

All build scripts default `REGISTRY=quay.io/danclark`. Override with `REGISTRY=other.registry.io/org ./build.sh`.

The `quay_repo` column in both CSVs gives the full image path to create in Quay. For models that
already have a build directory the value is **scraped from that directory's `build.sh`**, so the
CSV cannot drift from the real build; for the rest it is derived as
`quay.io/danclark/<hf-repo-basename-lowercased>-offline`. The `build_dir` column is populated only
where a build directory exists. 98 distinct Quay repos cover the 99 buildable models —
`google/gemma-4-26B-A4B` and `RedHatAI/gemma-4-26B-A4B-it` resolve to the same Red Hat artifact.

**Known discrepancy:** `qwen/32B` and `qwen/3.8B` build from `Qwen/Qwen3-32B` / `Qwen/Qwen3-4B`,
which are not in the candidate list and are not Red Hat artifacts — so they carry no Red Hat
support statement. Every other build directory pulls the Red Hat artifact.

### build.sh flags

Every `build.sh` takes the same options:

```bash
./build.sh                                            # download + build only
./build.sh --push                                     # ...then push, using podman's default auth
./build.sh --push --authfile ~/quay-pull-secret.json  # ...then push with explicit credentials
REGISTRY=registry.example.com/ai ./build.sh --push    # different registry
```

Without `--authfile`, the push uses podman's normal credential search path
(`$REGISTRY_AUTH_FILE`, then `$XDG_RUNTIME_DIR/containers/auth.json`, then
`$HOME/.docker/config.json`). Argument and authfile-existence validation happens **before** the
model download, so a typo fails in a second rather than after a 60 GB pull.

Push with: `podman push --authfile=/home/danclark/quay-pull-secret.json <image>`

Build must happen on a machine with internet access — the weights are too large for this workstation's bandwidth.

## Key Decisions

- **Base image**: `registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3` (GA) for all models. Do **not** use
  `rhaii-preview/vllm-cuda-rhel9:1786522102` — it is unusable on FIPS-enabled hosts. Its
  `opencv-python-headless` 5.0.0.93 vendors a FIPS-patched OpenSSL 1.1.1k
  (`opencv_python_headless.libs/libcrypto-*.so.1.1.1k`) with no HMAC integrity file, so the
  power-on self-test fails and the process aborts at `import cv2`:
  `crypto/fips/fips.c:154: OpenSSL internal error: FATAL FIPS SELFTEST FAILURE`.
  The GA image ships opencv 4.13.0.92, which bundles no OpenSSL, and imports cleanly under FIPS.
  Verified on a FIPS-enabled RHEL 9.8 host, 2026-10-02.
- **GA base image tradeoff**: GA runs vLLM `0.13.0+rhai20` vs the preview's `0.27.1.dev827`. Verified
  that GA registers every architecture used here (`GptOssForCausalLM`, `Qwen3ForCausalLM`,
  `Qwen3MoeForCausalLM`, `LlamaForCausalLM`, `GraniteMoeHybridForCausalLM`) and supports both
  `mxfp4` and `compressed-tensors`. Note the Python env moved from `/opt/vllm` to `/opt/app-root`;
  anything referencing the old path will break.
- **FIPS support statement (confirmed 2026-10-04)**: RHAIIS is **explicitly supported** on FIPS hosts.
  RHAIIS 3.1 release notes state verbatim: *"Red Hat AI Inference Server is now fully supported on
  FIPS-compliant Red Hat Enterprise Linux (RHEL) hosts."*
  (https://access.redhat.com/documentation/en-us/red_hat_ai_inference_server/3.1/html-single/release_notes/index)
  Support begins at 3.1, corroborating that the pre-GA image failed FIPS while GA 3.3 works.
  Two important qualifications:
  - **RHOAI is silent.** No statement — positive or negative — exists for Red Hat OpenShift AI model
    serving (vLLM ServingRuntime / KServe) on FIPS-enabled clusters, for 2.x or 3.x. Do not infer support.
  - **"FIPS compliant" ≠ "FIPS validated."** For Red Hat products "compliant" means *Designed for FIPS*:
    calling RHEL crypto modules submitted for FIPS-140 validation. RHEL 9 modules were submitted for
    FIPS 140-3 (CMVP review); RHEL 8's 140-2 validations remain active through 2026-09-21. The validation
    attaches to the RHEL modules, not to RHAIIS itself.
    (https://access.redhat.com/articles/openshift_fips_compliance_faq)
- **Containerfile optimization**: Use `COPY --chown=0:0 --chmod=775` in a single layer instead of separate `COPY` + `RUN chmod`. The two-step approach doubles image size because chmod creates a second full copy of the weights layer.
- **No route objects**: Routes are not needed for these deployments.
- **Kustomize for OpenShift**: All `openshift/` dirs use `kustomization.yaml` with `namespace:` set there (not hardcoded in individual resources). ArgoCD points directly at the `openshift/` subdirectory.
- **Deployment improvements** (applied to all models):
  - `startupProbe` with `periodSeconds: 30`, `failureThreshold: 24` (12 min for model loading)
  - GPU `tolerations` for `nvidia.com/gpu` tainted nodes
  - `strategy: Recreate` (can't share GPU between old/new pods during rolling update)
- **No Gemma tool-call parser exists.** RHAIIS 3.3's tool-call parser reference lists only `hermes`,
  `mistral`, `llama3_json`, `internlm2`, `granite-20b-fc`, `fuyu`, `phi3_json`, `jamba`. Gemma and
  Qwen are absent, so the `openshift-tool-calling/` overlay pattern does **not** apply to the gemma
  dirs — there is no parser value to pass.
- **`--task` was removed in RHAIIS 3.3.** Embedding/pooling models use `--runner`
  (`auto|draft|generate|pooling`) plus `--convert` (`auto|classify|embed|none|reward`). Older
  `--task embed` guidance will fail. `Qwen3-Embedding-8B` declares `Qwen3ForCausalLM`, so without
  `--runner pooling` vLLM silently starts it as a text generator.
- **⚠️ Gemma 3/4 architecture registration in vLLM `0.13.0+rhai20` is UNVERIFIED.** The RHAIIS 3.3
  release notes do not list Gemma 3 or Gemma 4 as enabled models, though the Red Hat AI 3 matrix
  ships them and 3.3.3 adds TranslateGemma. Check before downloading ~86 GB of Gemma weights:
  ```bash
  podman run --rm --entrypoint python3 registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3 \
    -c "from vllm.model_executor.models.registry import ModelRegistry as R; \
        print([a for a in R.get_supported_archs() if 'Gemma' in a])"
  ```
- **One namespace per model.** Variants sharing a namespace collide — the three gemma models each
  emit a `vllm-inference` ServiceAccount, so a family-level kustomization fails with
  "may not add resource with an already registered id" unless namespaces differ.
- **FP8-dynamic models**: No `--quantization` flag needed — vLLM auto-detects from model config
- **Granite repo**: `RedHatAI/granite-4.0-h-small-FP8-dynamic` (not ibm-granite, which doesn't have FP8-dynamic)
- **Nemotron repo**: `RedHatAI/Llama-3.1-Nemotron-70B-Instruct-HF-FP8-dynamic`

## TODO

- [ ] Build + push the 5 Enabled models (granite-guardian, qwen3-embedding, 3x gemma) and granite/nemotron — on a machine with bandwidth
- [ ] Push granite and nemotron images to quay.io/danclark
- [ ] Verify Containerfiles for gpt-oss and qwen use single-layer `COPY --chown --chmod` pattern (avoid doubled image size)
- [ ] Remove route.yaml from gpt-oss and qwen `openshift/` dirs if still present (routes not needed)
- [x] Update READMEs for granite and nemotron to reflect correct HuggingFace repo names (RedHatAI, not ibm-granite/nvidia)
- [ ] Verify Gemma 3/4 architecture registration in the GA image before downloading Gemma weights
- [ ] Confirm `layer_types` in gemma-3-12b-it config once downloaded (sliding-window ratio assumed)

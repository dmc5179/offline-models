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

**`ols_candidate`** ranks the five OpenShift Lightspeed candidates 1–5; blank for everything else,
so a non-empty value is the filter. The ranking balances tool-selection quality against GPU cost:
1 gpt-oss-20b, 2 Qwen3-8B, 3 Ministral-3-14B, 4 Llama-3.1-8B, 5 granite-4.0-h-small. All five
have a tool-call parser in RHOAI 3.5, a published ModelCar, and run on one GPU (24 GB except
granite at 48 GB). See `ols/` for the matching OLSConfig stubs.

**ModelCar columns.** `redhat_modelcar` is the full registry path to mirror (68 of 99 buildable
models have one; 95 of all 135); `modelcar_gb` is the compressed image size summed from the registry manifest's
layer sizes — the amd64 entry for multi-arch indexes; `modelcar_arch` lists the platforms the
image publishes. All were read from the registry manifest without pulling. Every ModelCar
referenced here supports amd64.

Reproduce without pulling:
```bash
skopeo inspect --raw docker://<image> | jq -r '.manifests[].platform | "\(.os)/\(.architecture)"'  # multi-arch
skopeo inspect docker://<image> | jq -r '.Architecture'                                            # single-manifest
```

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

## Two sourcing models

This repo now contains two different ways to get a model onto a cluster. Do not mix them for
the same model.

**1. Build your own image** (`<family>/<variant>/Containerfile` + `build.sh` + `openshift/`).
Weights are baked into a vLLM runtime image. Self-contained, but the image must be rebuilt
whenever the base image gets a CVE fix, and you own the FIPS surface.

**2. Red Hat ModelCar** (`<family>/<variant>/{standalone,rhoai}/`). Weights come from Red Hat's
published ModelCar OCI image; the runtime is Red Hat's. No build step. 68 of the 99 buildable
models already have one — see the `redhat_modelcar` column.

Five models are set up the ModelCar way, chosen as OpenShift Lightspeed candidates:
`gpt-oss/20B`, `qwen/8B-FP8`, `ministral/3-14B`, `llama/3.1-8B-FP8`, `granite/4.0-h-small-FP8`.
Each has four variants — `standalone/`, `standalone-tool-calling/`, `rhoai/`,
`rhoai-tool-calling/` — and is deployed via the ApplicationSets in `argocd/`.

**ModelCar images can be much larger than the GPU footprint.** Mirror by `modelcar_gb`, not
`weights_gb`. Five models carry a significant penalty:

| Model | Image | Weights | Factor |
|---|---|---|---|
| gpt-oss-120b | 195.8 GB | 65.2 GB | 3.0x |
| gpt-oss-20b | 41.3 GB | 13.8 GB | 3.0x |
| Mistral-Small-24B-Instruct-2501 | 94.3 GB | 47.1 GB | 2.0x |
| Ministral-3-14B-Instruct-2512 | 31.5 GB | 15.7 GB | 2.0x |
| Voxtral-Mini-3B-2507-FP8-dynamic | 12.3 GB | 6.1 GB | 2.0x |

The 2x cases ship two copies of the weights (HF-sharded plus Mistral-native
`consolidated.safetensors`). The 3x gpt-oss cases carry additional checkpoint formats.
Everything else is within ~1.1x of its weight size.

### RHOAI 3.5 serving

`LLMInferenceService` (`serving.kserve.io/v1alpha2`, shortName `llmisvc`) replaces the
InferenceService+ServingRuntime pattern for vLLM. Supports `oci://` alongside `s3://`, `pvc://`
and `hf://`. Base Distributed Inference with llm-d is GA; the topology selector is Tech Preview.
Plain `InferenceService` *"remain[s] fully supported."*

- vLLM args go in `spec.template.containers[].args`. `spec.model` has only `uri`, `name`, `lora`
  and `confidential`; `uri` is **required** and is an unconstrained string — no scheme enum — so
  `oci://` passes admission. Whether it resolves is up to the storage initializer at runtime.
- `imagePullSecrets` is **not** needed for the model. Verified: `spec.storageInitializer` exposes
  only `enabled`, with no credentials field, so the ModelCar pull relies on the cluster-wide pull
  secret. The `imagePullSecrets` in Red Hat's examples live at
  `spec.router.scheduler.template.imagePullSecrets` and `spec.template.imagePullSecrets` — those
  authenticate the **scheduler** and **vLLM runtime** images, not the model.
- `router: {scheduler: {}, route: {}, gateway: {}}` is valid. `scheduler` has no required children
  (`annotations`, `config`, `labels`, `pool`, `replicas`, `template`, `tokenizer` are all
  optional), so an empty object passes.

**apiVersion — resolved 2026-10-04 against a live CRD.** The CRD serves **both** `v1alpha1` and
`v1alpha2`. The two books are not contradicting each other; they document different versions:

| | RHOAI 3.5 book | RHAII 3.5 book + KB 7141739 |
|---|---|---|
| apiVersion | `v1alpha1` | `v1alpha2` |
| template location | `spec.router.template` | `spec.template` |
| `router.scheduler` | `{}` | populated with a `template` |
| `imagePullSecrets` | absent | present (scheduler + runtime pods) |
| vLLM args | `VLLM_ADDITIONAL_ARGS` env var | `containers[].args` list |

This repo targets **`v1alpha2`**. Verified top-level `spec` children: `annotations`, `baseRefs`,
`kvCacheOffloading`, `labels`, `model`, `parallelism`, `prefill`, `replicas`, `router`, `scaling`,
`storageInitializer`, `template`, `tracing`, `worker`. Do not mix shapes across versions —
declaring `v1alpha2` and then borrowing v1alpha1 nesting produces a CR that fails validation.

Caveat: **`oci://` is documented but never demonstrated.** Both books list the four schemes
(`s3://`, `pvc://`, `oci://`, `hf://`), but every worked example in either book uses `hf://`.
- Prereqs: OCP 4.19.9+, no Service Mesh v2, a `GatewayClass` plus a Gateway named
  `openshift-ai-inference` in `openshift-ingress`, and the `llmdTemplates` feature flag.

### Tool calling (required for OLS cluster interaction)

Per-model flags come from *Extending Red Hat AI Inference with tool calling capabilities* (3.5),
which has dedicated chapters for Llama 3.1, Qwen 3, Ministral 3 and gpt-oss:

| Model | Parser | Extra flags |
|---|---|---|
| gpt-oss-20b | `openai` | — |
| Qwen3-8B | `hermes` | — |
| Ministral-3-14B | `mistral` | `--tokenizer-mode/--config-format/--load-format=mistral` |
| Llama-3.1-8B | `llama3_json` | **requires** `--chat-template=/opt/app-root/template/tool_chat_template_llama3.1_json.jinja` |
| granite-4.0-h-* | `granite4` | — (Granite 3.x uses `granite`) |

Gemma has no parser in 3.5 either — the Gemma builds still have no tool-calling path.

**Decision (2026-10-04): the three Gemma directories are kept as chat/RAG-only builds.** They
cannot do tool calling, so they are not candidates for OpenShift Lightspeed cluster interaction or
any agentic workload. They were also believed to have no ModelCar, but a live registry probe on 2026-10-05 found all
three — mirror rather than build. Before relying on them, run the architecture registration
check below — it is still unverified that `Gemma3ForConditionalGeneration` and
`Gemma4ForConditionalGeneration` are registered in the GA runtime.

### The `image` volume caveat for standalone

`standalone/` mounts the ModelCar with a Kubernetes `image` volume. That type was rejected by the
built-in SCCs until the fix in OCP **4.20.15** (RHBA-2026:2987) and **4.22** (OCPBUGS-65807);
**4.21 still has no statement either way**. Each standalone dir ships an unreferenced `scc.yaml`
to apply if you hit `image volumes are not allowed to be used`. The documented fallback is an
`oras pull` initContainer into a PVC, which copies the full image per pod start.

Rechecked 2026-10-04. The evidence improved but did not close:
- OCP 4.21 *Nodes* §2.11 "Mounting an OCI image into a pod" exists with **no Technology Preview
  label** — it sits in the mainline book, not a preview chapter.
- Solution 7136646 is scoped to **4.20** and is the SCC rejection.
- Solution 7143096 was retitled to **4.22** and is a **PodSecurity** violation, not SCC — and its
  fix is exactly the `securityContext` block these deployments already set. So by 4.22 the SCC
  problem is gone and only PodSecurity remains, which we satisfy.
- No 4.21-specific SCC article exists, which is suggestive but is absence of evidence.
Still needs one `oc apply` on the target 4.21.z to settle.

## Mirror or build?

**Rebuilt from the live registry 2026-10-05.** Of the ten directories with a `build.sh`, only
**two** still need building, and both are upstream `Qwen/` repos with no Red Hat support
statement. Everything else ships as a ModelCar.

| Build dir | ModelCar | Action |
|---|---|---|
| `gpt-oss/120B` | `rhelai1/modelcar-gpt-oss-120b:1.5` | mirror |
| `granite/4.0-h-small-FP8` | `rhai/modelcar-granite-4-0-h-small-fp8-dynamic:3.0` | mirror |
| `nemotron/70B-FP8` | `rhelai1/modelcar-llama-3-1-nemotron-70b-instruct-hf-fp8-dynamic:1.5` | mirror |
| `granite-guardian/3.2-5B` | `rhai/modelcar-granite-guardian-3-2-5b:3.0` | mirror |
| `qwen3-embedding/8B` | `rhelai1/modelcar-qwen3-embedding-8b:1.5` | mirror |
| `gemma/3-12B-it` | `rhai/modelcar-gemma-3-12b-it:3.0` | mirror |
| `gemma/4-26B-A4B-FP8` | `rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0` | mirror |
| `gemma/4-31B-FP8` | `rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0` | mirror |
| `qwen/32B` | none | **build** — `Qwen/Qwen3-32B`, not a Red Hat artifact |
| `qwen/3.8B` | none | **build** — `Qwen/Qwen3-4B`, not a Red Hat artifact |

The build directories are kept rather than deleted: building gives you an image in your own
registry under your own tag, which some disconnected workflows want for provenance. Mirroring is
the cheaper default and is what the TODO assumes.

### ⚠️ Enumerate ModelCars from the registry, not the docs

The `redhat_modelcar` column was first built from the *Validated models* documentation tables.
**That undercounted by 34.** Probing `registry.redhat.io` directly found ModelCars for 95 of the
135 candidates (68 of the 99 buildable), against 48 from the docs. Among the misses were every
model in what had been a five-model overnight build queue — the entire job was unnecessary.
Mixtral had also moved from `:1.4` to `:1.5` without the table saying so.

Re-probe rather than trusting the table. Naming is mechanical: lowercase the HF repo basename,
replace `.` and `_` with `-`, prefix `modelcar-`, and try both `rhai/…:3.0` and `rhelai1/…:1.5`
(a few older ones are `:1.4`). `Meta-Llama-*` drops the `Meta-` prefix.

```bash
skopeo inspect --raw docker://registry.redhat.io/rhai/modelcar-<name>:3.0 >/dev/null 2>&1 && echo exists
```

### Overnight batch build

`hack/batch-build.sh` now targets only the two models with no ModelCar:

```bash
./hack/batch-build.sh --authfile ~/quay-pull-secret.json --clean-weights --shutdown
```

Consider whether you want it at all — both models are outside Red Hat's support statement. Every
preflight check runs before the first download, models build smallest-first, one failure does not
abandon the rest, and successful pushes clean up after themselves. Logs go to `logs/` (gitignored).

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
    Re-confirmed 2026-10-04 against a refreshed index: the *Supported Configurations for 3.x* article
    now carries a detailed per-component matrix (OCP 4.19.9+/4.20/4.21/4.22; llm-d GA 0.9.0; KServe
    GA 0.19.0; Red Hat AI Inference GA 3.5.0) and still has **no FIPS row or mention**. Open a
    support case rather than inferring. That article also confirms RHOAI 3.5 supports OCP 4.21.
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

- [ ] Decide whether the two non-Red Hat Qwen models are wanted at all. If yes,
      `./hack/batch-build.sh --authfile <path> --clean-weights --shutdown`. Everything else in
      the repo is mirrorable — the previous five-model build queue was unnecessary.
- [ ] Mirror the needed ModelCars into the disconnected registry (68 of 99 buildable models
      have one; see `redhat_modelcar` / `modelcar_gb`)
- [x] ~~Push granite and nemotron images to quay.io/danclark~~ **Obsolete 2026-10-04** — both ship
      as Red Hat ModelCars, as does gpt-oss-120b. Mirror instead of building; see below.
- [x] ~~Verify Containerfiles for gpt-oss and qwen use single-layer `COPY --chown --chmod`~~ **Verified 2026-10-04** — all three already correct
- [x] ~~Remove route.yaml from gpt-oss and qwen `openshift/` dirs~~ **Done 2026-10-04**
- [x] Update READMEs for granite and nemotron to reflect correct HuggingFace repo names (RedHatAI, not ibm-granite/nvidia)
- [x] ~~Resolve the LLMInferenceService apiVersion conflict~~ **Closed 2026-10-04** — CRD serves both
      v1alpha1 and v1alpha2; the books document different versions, not conflicting advice. Repo
      targets v1alpha2 and the manifests match its verified schema.
- [x] ~~Determine whether imagePullSecrets is needed for the ModelCar~~ **Closed 2026-10-04** —
      spec.storageInitializer has only `enabled`, no credentials. Cluster-wide pull secret covers it.
- [ ] Verify Gemma 3/4 architecture registration in the GA image before relying on the Gemma
      ModelCars (kept as chat/RAG-only; no tool calling, but ModelCars do exist — mirror them)
- [ ] Confirm `layer_types` in gemma-3-12b-it config once downloaded (sliding-window ratio assumed)
- [ ] Test an `image` volume pod on the target OCP 4.21.z — the only remaining way to settle whether
      the built-in SCCs permit it (fixed in 4.20.15 and 4.22; 4.21 undocumented)
- [ ] Open a support case for RHOAI on FIPS-enabled clusters — docs confirmed silent, twice
- [x] ~~Confirm `modelcar-llama-3-1-8b-instruct-fp8-dynamic:1.5` matches the HF repo~~
      **Closed 2026-10-04** — compared ModelCar layer sizes against HF safetensors shard sizes
      without pulling: both are exactly two weight layers at 4999.4 MB and 4084.6 MB. Same method
      confirms the other four candidates. Note gpt-oss-20b's ModelCar carries an extra ~13.75 GB
      layer with no counterpart in the HF shard set, which is where its 3x size comes from.
- [ ] Test `oci://` end to end on RHOAI 3.5 — documented as a supported scheme in both books but
      never demonstrated; every worked example uses `hf://`

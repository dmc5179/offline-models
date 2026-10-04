# Llama 3.1 8B Instruct FP8 — ModelCar Deployment

Deploys [RedHatAI/Meta-Llama-3.1-8B-Instruct-FP8-dynamic](https://huggingface.co/RedHatAI/Meta-Llama-3.1-8B-Instruct-FP8-dynamic) from Red Hat's **published ModelCar**
OCI image. There is no container build here — the weights artifact already exists.

The conservative choice: the most battle-tested tool calling of the five.

| | |
|---|---|
| ModelCar image | `registry.redhat.io/rhelai1/modelcar-llama-3-1-8b-instruct-fp8-dynamic:1.5` |
| ModelCar architectures | amd64 (single-manifest) |
| Image size (compressed) | 9.1 GB |
| Weights in GPU | 9.1 GB |
| Minimum GPU | 24 GB (g6 / L4) |
| Model max context | 131,072 tokens |
| Served model name | `llama-3-1-8b-fp8` |
| Tool-call parser | `llama3_json` |

## Four deployment variants

| Path | Platform | Tool calling |
|---|---|---|
| `standalone/` | plain vLLM Deployment | no |
| `standalone-tool-calling/` | plain vLLM Deployment | yes |
| `rhoai/` | RHOAI 3.5 `LLMInferenceService` | no |
| `rhoai-tool-calling/` | RHOAI 3.5 `LLMInferenceService` | yes |

Pick exactly one. The tool-calling variants are kustomize overlays on their
respective bases, so deploying both a base and its overlay into one namespace
would conflict.

**For OpenShift Lightspeed cluster interaction you need a tool-calling variant.**
The OLS docs are explicit: *"You must enable tool calling in the LLM provider to
activate the cluster interaction feature."*

## Mirroring

```bash
oc image mirror registry.redhat.io/rhelai1/modelcar-llama-3-1-8b-instruct-fp8-dynamic:1.5 \
  <your-mirror-registry>/modelcar-llama-3-1-8b-fp8:<tag>
```

Budget **9.1 GB** for the mirror, not 9.1 GB — the image can carry more
than what loads into the GPU.

## Deploy

```bash
# plain vLLM, with tool calling
oc apply -k standalone-tool-calling

# RHOAI 3.5, with tool calling
oc apply -k rhoai-tool-calling
```

Or point an ArgoCD ApplicationSet at it — see `../../argocd/`.

Verify:

```bash
oc get pods -n llama-3-1-8b-inference
oc port-forward -n llama-3-1-8b-inference svc/llama-3-1-8b-fp8 8000:8000
curl -s http://localhost:8000/v1/models | jq -r '.data[].id'   # expect: llama-3-1-8b-fp8
```

## Notes

This is the only model of the five that **requires a chat template** for tool calling: `--chat-template=/opt/app-root/template/tool_chat_template_llama3.1_json.jinja`. The tool-calling overlays set it; without it, tool calls will not parse.

The ModelCar name match (`modelcar-llama-3-1-8b-instruct-fp8-dynamic`) is inferred from naming. Verify it is the artifact you expect before relying on it.

### Standalone: the `image` volume caveat

`standalone/` mounts the ModelCar with a Kubernetes `image` volume
(`subPath: models` → `/mnt/models`). That volume type was **rejected by the
built-in SCCs** until recently — the fix landed in OCP 4.20.15
(RHBA-2026:2987) and 4.22 (OCPBUGS-65807), and 4.21 is undocumented either way.

If pods fail with `image volumes are not allowed to be used`, apply the custom
SCC included here (it is deliberately left out of `kustomization.yaml` because
it is cluster-scoped):

```bash
oc apply -f standalone/scc.yaml
oc adm policy add-scc-to-user vllm-image-volume -z vllm-modelcar -n llama-3-1-8b-inference
```

Never edit the built-in SCCs. The documented alternative is an `oras pull`
initContainer copying into a PVC, at the cost of copying 9.1 GB per pod start.

### RHOAI: confirm the API version

Manifests use `serving.kserve.io/v1alpha2` (what RHAII 3.5 and KB 7141739
document). Some RHOAI 3.5 examples show `v1alpha1`:

```bash
oc get crd llminferenceservices.serving.kserve.io -o jsonpath='{.spec.versions[*].name}'
```

## References

- [Extending Red Hat AI Inference with tool calling capabilities (3.5)](https://docs.redhat.com/en/documentation/red_hat_ai_inference/3.5/html-single/extending_red_hat_ai_inference_with_tool_calling_capabilities/index)
- [Inference serving language models in OCI-compliant model containers (3.5)](https://docs.redhat.com/en/documentation/red_hat_ai_inference/3.5/html-single/inference_serving_language_models_in_oci-compliant_model_containers/index)
- [Deploy models using Distributed Inference with llm-d (RHOAI 3.5)](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.5/html-single/deploy_models_using_distributed_inference_with_llm-d/index)
- [Migrating from vLLM InferenceService to LLMInferenceService](https://access.redhat.com/articles/7141739)

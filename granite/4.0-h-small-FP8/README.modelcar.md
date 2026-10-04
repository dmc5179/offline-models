# Granite 4.0 Hybrid Small FP8 — ModelCar Deployment

Deploys [RedHatAI/granite-4.0-h-small-FP8-dynamic](https://huggingface.co/RedHatAI/granite-4.0-h-small-FP8-dynamic) from Red Hat's **published ModelCar**
OCI image. There is no container build here — the weights artifact already exists.

Red Hat's own model and the most capable of the five - the upgrade path if 8B-class tool selection disappoints.

| | |
|---|---|
| ModelCar image | `registry.redhat.io/rhai/modelcar-granite-4-0-h-small-fp8-dynamic:3.0` |
| ModelCar architectures | amd64, arm64, ppc64le, s390x |
| Image size (compressed) | 32.7 GB |
| Weights in GPU | 32.7 GB |
| Minimum GPU | 48 GB (g6e / L40S) |
| Model max context | 131,072 tokens |
| Served model name | `granite-4-0-h-small-fp8` |
| Tool-call parser | `granite4` |

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
oc image mirror registry.redhat.io/rhai/modelcar-granite-4-0-h-small-fp8-dynamic:3.0 \
  <your-mirror-registry>/modelcar-granite-4-0-h-small-car:<tag>
```

Budget **32.7 GB** for the mirror, not 32.7 GB — the image can carry more
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
oc get pods -n granite-4-0-h-small-car-inference
oc port-forward -n granite-4-0-h-small-car-inference svc/granite-4-0-h-small-car 8000:8000
curl -s http://localhost:8000/v1/models | jq -r '.data[].id'   # expect: granite-4-0-h-small-fp8
```

## Notes

This directory **also** contains a from-source container build (`Containerfile`, `build.sh`, `openshift/`) that bakes the weights into a self-contained image. The `standalone/` and `rhoai/` overlays here are the ModelCar alternative; use one approach or the other, not both.

See `gpu-sizing.md` in this directory for the EC2 instance analysis.

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
oc adm policy add-scc-to-user vllm-image-volume -z vllm-modelcar -n granite-4-0-h-small-car-inference
```

Never edit the built-in SCCs. The documented alternative is an `oras pull`
initContainer copying into a PVC, at the cost of copying 32.7 GB per pod start.

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

# GPT-OSS-20B — ModelCar Deployment

Deploys [RedHatAI/gpt-oss-20b](https://huggingface.co/RedHatAI/gpt-oss-20b) from Red Hat's **published ModelCar**
OCI image. There is no container build here — the weights artifact already exists.

MoE with ~3.6B active parameters, so it reasons like a larger model while running like a small one. The best tool-selection quality per GPU dollar here.

| | |
|---|---|
| ModelCar image | `registry.redhat.io/rhelai1/modelcar-gpt-oss-20b:1.5` |
| ModelCar architectures | amd64, arm64, ppc64le, s390x |
| Image size (compressed) | 41.3 GB |
| Weights in GPU | 13.8 GB |
| Minimum GPU | 24 GB (g6 / L4) |
| Model max context | 131,072 tokens |
| Served model name | `gpt-oss-20b` |
| Tool-call parser | `openai` |

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
oc image mirror registry.redhat.io/rhelai1/modelcar-gpt-oss-20b:1.5 \
  <your-mirror-registry>/modelcar-gpt-oss-20b:<tag>
```

Budget **41.3 GB** for the mirror, not 13.8 GB — the image can carry more
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
oc get pods -n gpt-oss-20b-inference
oc port-forward -n gpt-oss-20b-inference svc/gpt-oss-20b 8000:8000
curl -s http://localhost:8000/v1/models | jq -r '.data[].id'   # expect: gpt-oss-20b
```

## Notes



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
oc adm policy add-scc-to-user vllm-image-volume -z vllm-modelcar -n gpt-oss-20b-inference
```

Never edit the built-in SCCs. The documented alternative is an `oras pull`
initContainer copying into a PVC, at the cost of copying 41.3 GB per pod start.

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

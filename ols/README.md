# OpenShift Lightspeed configuration stubs

Copy-paste `OLSConfig` resources pointing OLS at each of the five candidate
models in this repo. These are **stubs to copy from**, not a kustomize overlay
and not wired into ArgoCD — see [Why these are not GitOps-managed](#why-these-are-not-gitops-managed).

## These are alternatives, not additive

The OLS operator only reconciles an `OLSConfig` named **`cluster`**. There can
be exactly one on a cluster, so applying a second file replaces the first
rather than adding a provider. To compare models, swap the whole resource.

| File | Model | Served as | GPU | Context |
|---|---|---|---|---|
| `olsconfig-gpt-oss-20b.yaml` | GPT-OSS-20B | `gpt-oss-20b` | 24 GB | 131,072 |
| `olsconfig-qwen3-8b-fp8.yaml` | Qwen3-8B FP8 | `qwen3-8b-fp8` | 24 GB | 40,960 |
| `olsconfig-ministral-3-14b.yaml` | Ministral 3 14B | `ministral-3-14b` | 24 GB | 262,144 |
| `olsconfig-llama-3-1-8b-fp8.yaml` | Llama 3.1 8B FP8 | `llama-3-1-8b-fp8` | 24 GB | 131,072 |
| `olsconfig-granite-4-0-h-small-fp8.yaml` | Granite 4.0 h-small FP8 | `granite-4-0-h-small-fp8` | 48 GB | 131,072 |

If you want a single recommendation: start with **gpt-oss-20b**. It is MoE with
~3.6B active parameters, so it answers the OLS docs' warning that *"a larger
model with more parameters performs better… When using a small model, you might
notice poor performance in tool selection"* without paying for a larger GPU.

## Apply

```bash
oc apply -f secret-rhoai-api-keys.yaml
oc apply -f olsconfig-gpt-oss-20b.yaml
```

Then watch the operator reconcile:

```bash
oc get olsconfig cluster -o yaml
oc get pods -n openshift-lightspeed
```

## Three things that will silently break this

**1. The model name must match exactly.** `spec.llm.providers[].models[].name`
and `spec.ols.defaultModel` must both equal the `--served-model-name` baked
into the deployment. That is why those are set explicitly on all five
deployments rather than defaulting to the filesystem path. Confirm before
applying:

```bash
oc port-forward -n <model-namespace> svc/<model-service> 8000:8000
curl -s http://localhost:8000/v1/models | jq -r '.data[].id'
```

**2. The Secret is mandatory even though the endpoint needs no auth.** Per the
OLS docs: *"If your Red Hat OpenShift AI endpoint does not require a token, you
must still set the token value to any valid string for the request to
authenticate."* The key is always `apitoken`.

**3. Cluster interaction requires a tool-calling deployment.** The OLS docs:
*"You must enable tool calling in the LLM provider to activate the cluster
interaction feature."* Point the ApplicationSets at the `*-tool-calling`
variants, not the plain ones, or OLS will answer documentation questions but
fail to query the cluster.

## Endpoint addresses

**Standalone** (`<model>/standalone-tool-calling`) — the in-cluster Service
address, which is what each stub ships with:

```
http://<service>.<namespace>.svc.cluster.local:8000/v1
```

**RHOAI** (`<model>/rhoai-tool-calling`) — do not guess; `LLMInferenceService`
exposes its address through a Gateway. Read it off the resource and append
`/v1`:

```bash
oc get llminferenceservice <name> -n <namespace> -o jsonpath='{.status.url}'
```

Each stub has that command inline as commented Option B.

The `url` must end in `/v1` either way — the docs call this out explicitly.

## Technology Preview

Both the cluster interaction feature and the MCP server integration are
Technology Preview: *"Technology Preview features are not supported with Red Hat
production service level agreements (SLAs)."* `introspectionEnabled` defaults to
`true`, so the built-in Observability MCP server is on unless you disable it. It
is read-only and blocks secrets and RBAC objects by default. OLS 1.1 adds a
Kubernetes MCP server with **write** access gated by human-in-the-loop approval
(`toolsApprovalConfig.approvalType`) — review that before enabling it.

## Two parents, not a typo

`maxIterations` sits under `spec.olsConfig` while `introspectionEnabled` sits
under `spec.ols`. Confirmed 2026-10-04 against the Configure doc — section
1.15.1 documents `spec.olsConfig.maxIterations` and section 1.12 documents
`spec.ols.introspectionEnabled`. Both parents genuinely exist; this is not a
documentation error, so do not "fix" it by moving one under the other.

## Why these are not GitOps-managed

`OLSConfig` is a cluster singleton named `cluster` that the OLS operator owns.
Putting it under an ArgoCD Application with `selfHeal` would mean Argo and any
console-driven or operator-driven change fight over the same object. Applying
these by hand — or adopting them deliberately into a GitOps repo that owns the
whole OLS install — avoids that.

## References

- [OpenShift Lightspeed — Configure](https://docs.redhat.com/en/documentation/red_hat_openshift_lightspeed/1.0/html-single/configure/index)
- [OpenShift Lightspeed — About](https://docs.redhat.com/en/documentation/red_hat_openshift_lightspeed/1.0/html-single/about/index)

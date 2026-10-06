#!/usr/bin/env python3
"""Generate per-model GPU sizing docs under ./docs."""
import os, math

import pathlib
OUT = str(pathlib.Path(__file__).resolve().parent.parent / 'docs')
os.makedirs(OUT, exist_ok=True)

USABLE = 0.92
RESERVE_GB_PER_GPU = 2.0

# approximate us-east-1 on-demand, USD/hr. name, gpu, n, GB/gpu, TB/s, $/hr, blackwell
INSTANCES = [
    ("g6.xlarge",        "L4",      1,  24, 0.300,  0.80, False),
    ("g5.xlarge",        "A10G",    1,  24, 0.600,  1.01, False),
    ("g6e.xlarge",       "L40S",    1,  48, 0.864,  1.86, False),
    ("g6e.2xlarge",      "L40S",    1,  48, 0.864,  2.24, False),
    ("g6.12xlarge",      "L4",      4,  24, 0.300,  4.60, False),
    ("g5.12xlarge",      "A10G",    4,  24, 0.600,  5.67, False),
    ("g6e.12xlarge",     "L40S",    4,  48, 0.864, 10.49, False),
    ("g6e.48xlarge",     "L40S",    8,  48, 0.864, 30.13, False),
    ("p4d.24xlarge",     "A100-40", 8,  40, 1.555, 32.77, False),
    ("p4de.24xlarge",    "A100-80", 8,  80, 2.039, 40.97, False),
    ("p5.48xlarge",      "H100",    8,  80, 3.350, 55.04, False),
    ("p5e.48xlarge",     "H200",    8, 141, 4.800, 61.78, False),
    ("p6-b200.48xlarge", "B200",    8, 180, 8.000, 92.00, True),
]

M = [
 dict(slug='nemotron-3-super-120b', title='Nemotron 3 Super 120B-A12B (NVFP4)',
      car='registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-nvfp4:3.0',
      img_gb=80.4, weights_gb=80.4, layers=88, full=8, slid=0, win=0, kvh=2, hd=128, kvb=1,
      ctx=262144, native=262144, kvb_note='FP8 (declared in checkpoint)', arch='LatentMoE — Mamba-2 + MoE + attention hybrid, with MTP',
      extra_seq_mb=87, extra_note='87 MB Mamba2 state per sequence (constant, `--mamba-ssm-cache-dtype float16`)',
      params='120B total, 12B active', quant='NVFP4 mixed precision (FP4 experts, FP8 mixer)',
      min_gpu='1x B200 or 1x DGX Spark', micro='A100, H100-80GB, Blackwell',
      validated='vLLM 0.18.0 / RHAIIS 3.4 / RHOAI 3.4',
      gpus_allowed={'A100-80','H100','H200','B200'},
      hook='Only 8 of 88 layers are attention, so KV is 4 KiB/token — about 80x cheaper than a dense 70B.',
      tool='`hack/size-nemotron-super.py` models this one in detail.'),
 dict(slug='llama-3.3-70b', title='Llama 3.3 70B Instruct',
      car='registry.redhat.io/rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5',
      img_gb=39.6, weights_gb=39.6, layers=80, full=80, slid=0, win=0, kvh=8, hd=128, kvb=2,
      ctx=131072, native=131072, kvb_note='FP16 (no FP8 scheme declared)', arch='Dense transformer, no sliding window',
      extra_seq_mb=0, extra_note=None, params='70B dense', quant='INT4 (w4a16)',
      min_gpu=None, micro=None, validated=None,
      hook='All 80 layers are full attention, so KV is 320 KiB/token — the most expensive per-sequence of this set.',
      tool=None,
      variants=[('INT4 w4a16','rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w4a16:1.5',39.6),
                ('FP8 dynamic','rhelai1/modelcar-llama-3-3-70b-instruct-fp8-dynamic:1.5',72.7),
                ('INT8 w8a8','rhelai1/modelcar-llama-3-3-70b-instruct-quantized-w8a8:1.5',72.7),
                ('BF16','rhelai1/modelcar-llama-3-3-70b-instruct:1.5',141.1)]),
 dict(slug='gemma-3-12b', title='Gemma 3 12B Instruct',
      car='registry.redhat.io/rhai/modelcar-gemma-3-12b-it:3.0',
      img_gb=24.4, weights_gb=24.4, layers=48, full=8, slid=40, win=1024, kvh=8, hd=256, kvb=2,
      ctx=131072, native=131072, kvb_note='FP16 (no FP8 scheme declared)', arch='Dense multimodal, sliding-window attention',
      extra_seq_mb=0, extra_note=None, params='12B dense', quant='none (bf16)',
      min_gpu=None, micro=None, validated=None,
      hook='Unquantized bf16, so a 12B model costs 24.4 GB — more than the 26B FP8 MoE below it.',
      tool=None, assumption='Red Hat\'s config omits `layer_types`; the 40 sliding / 8 full split is '
                            'inferred from Gemma 3\'s documented 5:1 ratio. Verify once downloaded.',
      variants=[('3n E4B it FP8','rhelai1/modelcar-gemma-3n-e4b-it-fp8-dynamic:1.5',11.9),
                ('3n E4B it','rhelai1/modelcar-gemma-3n-e4b-it:1.5',15.8),
                ('12B it','rhai/modelcar-gemma-3-12b-it:3.0',24.4),
                ('27B it','rhai/modelcar-gemma-3-27b-it:3.0',54.9)]),
 dict(slug='gemma-4-26b-a4b', title='Gemma 4 26B-A4B Instruct (FP8)',
      car='registry.redhat.io/rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0',
      img_gb=28.7, weights_gb=28.6, layers=30, full=5, slid=25, win=1024, kvh=8, hd=256, kvb=2,
      ctx=262144, native=262144, kvb_note='FP16 (no FP8 scheme declared)', arch='Sparse MoE, multimodal, 25 sliding + 5 full attention',
      extra_seq_mb=0, extra_note=None, params='26B total, ~4B active', quant='FP8 dynamic',
      min_gpu=None, micro=None, validated=None,
      hook='Only 5 of 30 layers do full attention, so the memory curve is nearly flat across context length.',
      tool=None,
      variants=[('12B it NVFP4','rhai/modelcar-redhatai-gemma-4-12b-it-nvfp4:3.0',10.3),
                ('12B it FP8','rhai/modelcar-redhatai-gemma-4-12b-it-fp8-dynamic:3.0',15.1),
                ('E4B it','rhai/modelcar-redhatai-gemma-4-e4b-it:3.0',16.0),
                ('26B-A4B NVFP4','rhai/modelcar-redhatai-gemma-4-26b-a4b-it-nvfp4:3.0',16.5),
                ('26B-A4B FP8','rhai/modelcar-gemma-4-26b-a4b-it-fp8-dynamic:3.0',28.7)]),
 dict(slug='gemma-4-31b', title='Gemma 4 31B Instruct (FP8)',
      car='registry.redhat.io/rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0',
      img_gb=33.3, weights_gb=33.3, layers=60, full=10, slid=50, win=1024, kvh=16, hd=256, kvb=2,
      ctx=262144, native=262144, kvb_note='FP16 (no FP8 scheme declared)', arch='Dense multimodal, 50 sliding + 10 full attention',
      extra_seq_mb=0, extra_note=None, params='31B dense', quant='FP8 dynamic',
      min_gpu=None, micro=None, validated=None,
      hook='Dense rather than MoE, and 16 KV heads — twice the per-sequence KV of the 26B MoE.',
      tool=None,
      variants=[('31B it NVFP4','rhai/modelcar-redhatai-gemma-4-31b-it-nvfp4:3.0',23.3),
                ('31B it FP8 block','rhai/modelcar-redhatai-gemma-4-31b-it-fp8-block:3.0',33.3),
                ('31B it FP8 dynamic','rhai/modelcar-gemma-4-31b-it-fp8-dynamic:3.0',33.3),
                ('31B it (bf16)','rhai/modelcar-redhatai-gemma-4-31b-it:3.0',62.6)]),
 dict(slug='gpt-oss-120b', title='GPT-OSS 120B',
      car='registry.redhat.io/rhai/modelcar-gpt-oss-120b-essential:3.0',
      img_gb=65.3, weights_gb=65.2, layers=36, full=18, slid=18, win=128, kvh=8, hd=64, kvb=2,
      ctx=131072, native=131072, kvb_note='FP16 (no FP8 scheme declared)', arch='Sparse MoE, 128 experts top-4, alternating sliding/full attention',
      extra_seq_mb=0, extra_note=None, params='120B total, ~5B active', quant='MXFP4',
      min_gpu=None, micro=None, validated=None,
      hook='A 128-token sliding window on half the layers keeps KV small despite 36 layers.',
      tool=None,
      variants=[('120B essential','rhai/modelcar-gpt-oss-120b-essential:3.0',65.3),
                ('120B full','rhelai1/modelcar-gpt-oss-120b:1.5',195.8)]),
 dict(slug='gpt-oss-20b', title='GPT-OSS 20B',
      car='registry.redhat.io/rhai/modelcar-gpt-oss-20b-essential:3.0',
      img_gb=13.8, weights_gb=13.8, layers=24, full=12, slid=12, win=128, kvh=8, hd=64, kvb=2,
      ctx=131072, native=131072, kvb_note='FP16 (no FP8 scheme declared)', arch='Sparse MoE, 32 experts top-4, alternating sliding/full attention',
      extra_seq_mb=0, extra_note=None, params='21B total, ~3.6B active', quant='MXFP4',
      min_gpu=None, micro=None, validated=None,
      hook='The cheapest model here to host — fits a single 24 GB GPU with room for hundreds of sequences.',
      tool=None,
      variants=[('20B essential','rhai/modelcar-gpt-oss-20b-essential:3.0',13.8),
                ('20B full','rhelai1/modelcar-gpt-oss-20b:1.5',41.3)]),
]


def kv_per_seq(m, ctx):
    b = m['kvh'] * m['hd'] * 2 * m['kvb']
    full = m['full'] * b * ctx
    slid = m['slid'] * b * min(ctx, m['win']) if m['slid'] else 0
    return full + slid + m['extra_seq_mb'] * 1e6


def fits(m, inst, ctx):
    _, gpu, n, gb, bw, price, bb = inst
    allow = m.get('gpus_allowed')
    if allow and gpu not in allow:
        return None   # microarchitecture not supported for this model
    usable = n * gb * USABLE - n * RESERVE_GB_PER_GPU
    free = usable - m['weights_gb']
    if free <= 0: return None
    return int(free * 1e9 / kv_per_seq(m, ctx))


TARGET_USERS = 10


def kv_bytes(m, ctx, kvb=None):
    b = m['kvh'] * m['hd'] * 2 * (kvb if kvb else m['kvb'])
    full = m['full'] * b * ctx
    slid = m['slid'] * b * min(ctx, m['win']) if m['slid'] else 0
    return full + slid + m['extra_seq_mb'] * 1e6


def cheapest_for(m, users, ctx, kvb=None):
    need = m['weights_gb'] + kv_bytes(m, ctx, kvb) * users / 1e9
    allow = m.get('gpus_allowed')
    for name, gpu, n, gb, bw, price, bb in INSTANCES:
        if allow and gpu not in allow:
            continue
        if n * gb * USABLE - n * RESERVE_GB_PER_GPU >= need:
            return (name, gpu, n, price, need)
    return None


def doc(m):
    native = m['native']
    L = []; a = L.append
    a(f"# {m['title']} — GPU sizing")
    a("")
    a(f"```\n{m['car']}\n```")
    a("")
    a(f"{m['hook']}")
    a("")
    a("| | |")
    a("|---|---|")
    a(f"| Parameters | {m['params']} |")
    a(f"| Quantization | {m['quant']} |")
    a(f"| Weights | {m['weights_gb']} GB |")
    a(f"| Image to mirror | {m['img_gb']} GB |")
    a(f"| Architecture | {m['arch']} |")
    a(f"| Attention layers | {m['full']} full"
      + (f" + {m['slid']} sliding ({m['win']}-token window)" if m['slid'] else "")
      + f", of {m['layers']} total |")
    a(f"| **Default context** | **{native:,}** (vLLM derives `--max-model-len` from this) |")
    a(f"| KV cache dtype | {m['kvb_note']} |")
    if m.get('min_gpu'):   a(f"| Minimum GPU (model card) | {m['min_gpu']} |")
    if m.get('micro'):     a(f"| Supported microarch | {m['micro']} |")
    if m.get('validated'): a(f"| Validated on | {m['validated']} |")
    a("")

    # ---- the headline recommendation
    per = kv_bytes(m, native)
    pick = cheapest_for(m, TARGET_USERS, native)
    a(f"## Recommended: {TARGET_USERS} concurrent users at the default {native:,} context")
    a("")
    a(f"Each sequence needs **{per/1e9:.1f} GB** of KV"
      + (f" plus state" if m['extra_seq_mb'] else "") + " to hold a full context window.")
    a("")
    a(f"```")
    a(f"{m['weights_gb']:>6.1f} GB  weights")
    a(f"{per*TARGET_USERS/1e9:>6.1f} GB  KV for {TARGET_USERS} users x {native:,} tokens")
    a(f"{'─'*6}")
    a(f"{m['weights_gb'] + per*TARGET_USERS/1e9:>6.1f} GB  required, before activation overhead")
    a(f"```")
    a("")
    if pick:
        name, gpu, n, price, need = pick
        mo = price * 730
        a(f"### → `{name}` ({n}x {gpu}) — **${mo:,.0f}/month** (${price:.2f}/hr)")
        a("")
        a(f"${mo/TARGET_USERS:,.0f} per user per month at {TARGET_USERS} users.")
    else:
        a(f"### → Exceeds every instance listed. {m['weights_gb'] + per*TARGET_USERS/1e9:,.0f} GB "
          f"needed; the largest single node here is 8x B200 at 1,440 GB.")
        a("")
        a("Options: shorten `--max-model-len`, enable FP8 KV (below), or split across replicas.")
    a("")

    # ---- context is the dominant lever
    a("## Context length is the dominant cost lever")
    a("")
    a(f"Same {TARGET_USERS} users, different `--max-model-len`:")
    a("")
    a("| --max-model-len | KV per user | Total needed | Instance | $/month |")
    a("|---|---|---|---|---|")
    for c in [8192, 32768, 131072, 262144]:
        if c > native: continue
        pk = cheapest_for(m, TARGET_USERS, c)
        pr = kv_bytes(m, c)
        if pk:
            nm, g, nn, p, nd = pk
            a(f"| {c:,}{' (default)' if c==native else ''} | {pr/1e9:.1f} GB | {nd:.0f} GB "
              f"| `{nm}` ({nn}x {g}) | ${p*730:,.0f} |")
        else:
            a(f"| {c:,}{' (default)' if c==native else ''} | {pr/1e9:.1f} GB | "
              f"{m['weights_gb']+pr*TARGET_USERS/1e9:.0f} GB | — | exceeds all |")
    a("")
    a("Most agentic traffic never fills the window. Capping `--max-model-len` at what you "
      "actually use is the single biggest saving available.")
    a("")

    # ---- fp8 kv lever, where it applies
    if m['kvb'] == 2:
        pk8 = cheapest_for(m, TARGET_USERS, native, kvb=1)
        per8 = kv_bytes(m, native, kvb=1)
        a("## FP8 KV cache halves it")
        a("")
        a(f"This checkpoint declares no KV cache scheme, so vLLM keeps KV in FP16. Passing "
          f"`--kv-cache-dtype fp8` halves per-sequence KV from {per/1e9:.1f} GB to "
          f"{per8/1e9:.1f} GB:")
        a("")
        if pk8:
            nm, g, nn, p, nd = pk8
            a(f"| | Instance | $/month |")
            a(f"|---|---|---|")
            if pick:
                a(f"| FP16 KV (default) | `{pick[0]}` ({pick[2]}x {pick[1]}) | ${pick[3]*730:,.0f} |")
            else:
                a(f"| FP16 KV (default) | exceeds all | — |")
            a(f"| FP8 KV | `{nm}` ({nn}x {g}) | ${p*730:,.0f} |")
            a("")
        a("Accuracy impact is small for most workloads but is not zero — validate against your "
          "own evals before relying on it.")
        a("")

    # ---- scaling
    a(f"## Scaling past {TARGET_USERS} users, at default context")
    a("")
    a("| Users | Instance | $/month | $/user/month |")
    a("|---|---|---|---|")
    for u in (1, 5, 10, 25, 50, 100):
        pk = cheapest_for(m, u, native)
        if pk:
            nm, g, nn, p, nd = pk
            a(f"| {u} | `{nm}` ({nn}x {g}) | ${p*730:,.0f} | ${p*730/u:,.0f} |")
        else:
            a(f"| {u} | — | — | exceeds all listed instances |")
    a("")

    if m.get('assumption'):
        a(f"> {m['assumption']}")
        a("")

    if m.get('variants'):
        a("## Variants")
        a("")
        a("| Variant | Image | Size |")
        a("|---|---|---|")
        for vn, vp, vg in m['variants']:
            a(f"| {vn} | `registry.redhat.io/{vp}` | {vg} GB |")
        a("")

    a("## Before you quote this")
    a("")
    a("- Sizing above **guarantees** every one of the "
      f"{TARGET_USERS} users can fill the full {native:,}-token window at once. vLLM allocates "
      "KV blocks on demand, so real usage is lower — but this is the figure that cannot "
      "over-commit.")
    a("- **Memory is exact; throughput is not modelled.** Red Hat publishes accuracy benchmarks "
      "for its validated models and no throughput, latency or concurrency figures. Latency will "
      "bind before memory does. Measure:")
    a("")
    a("  ```bash")
    a("  vllm bench serve --model <name> --host localhost --port 8000 \\")
    a("    --dataset-name random --random-input-len 4000 --random-output-len 500 \\")
    a("    --max-concurrency 10 --num-prompts 100")
    a("  ```")
    a("")
    a("- Prices are approximate us-east-1 on-demand and drift. Verify before quoting.")
    if m.get('tool'): a(f"- {m['tool']}")
    a("")
    return '\n'.join(L)


for m in M:
    p = os.path.join(OUT, f"sizing-{m['slug']}.md")
    txt = doc(m)
    open(p, 'w').write(txt)
    print(f"{len(txt.splitlines()):>4} lines  docs/sizing-{m['slug']}.md")

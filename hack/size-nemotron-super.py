#!/usr/bin/env python3
"""
GPU sizing for NVIDIA-Nemotron-3-Super-120B-A12B (NVFP4) on AWS.

    oci://registry.redhat.io/rhai/modelcar-nvidia-nemotron-3-super-120b-a12b-nvfp4:3.0

Maps "N concurrent users" or "X tokens/sec" to an AWS instance, for agentic
workloads. The model card names agentic workflows as a primary target:
"Best For: Agentic workflows, long-context reasoning, high-volume workloads
(e.g. IT ticket automation), tool use, RAG".

    ./hack/size-nemotron-super.py --users 10
    ./hack/size-nemotron-super.py --users 50 --ctx 32768
    ./hack/size-nemotron-super.py --tokens-per-sec 400
    ./hack/size-nemotron-super.py --users 25 --measured-tps 1800   # after measuring

────────────────────────────────────────────────────────────────────────────
READ THIS BEFORE QUOTING ANYTHING

1. VERSION MISMATCH. The card states "Validated on vLLM 0.18.0 / RHAIIS 3.4 /
   RHOAI 3.4". This repo pins RHAIIS 3.3.3 (vLLM 0.13.0+rhai20) — five minor
   versions behind. This model is NOT validated on the runtime this repo
   currently uses. Settle that before sizing hardware for it.

2. MEMORY IS NOT THE BINDING CONSTRAINT. This model's KV cache is ~80x
   smaller per token than a dense 70B, so memory allows far more concurrent
   sequences than latency does. The "max seqs" column is a memory ceiling,
   not a throughput recommendation. Red Hat's own tuning table suggests
   --max-num-seqs 1-2 for this model class on a memory-constrained device.
   Size on memory to find what FITS; measure to find what SERVES.

3. THROUGHPUT HERE IS AN ESTIMATE, +/- roughly 2x. Red Hat publishes accuracy
   benchmarks for this model but no throughput, latency or concurrency
   numbers anywhere — not in the docs, the KB, or the model card. There is
   nothing authoritative to anchor to. Use --measured-tps once you have run
   a benchmark on the real instance; see --help-calibrate.
────────────────────────────────────────────────────────────────────────────
"""
import argparse, math, sys

# ───────────────────────────────────────────────────────── verified model facts
# config.json of RedHatAI/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4 and its model
# card. Verified 2026-10-06.
WEIGHTS_GB      = 80.4      # measured sum of canonical safetensors in the ModelCar
TOTAL_LAYERS    = 88        # hybrid_override_pattern: 40 Mamba2 + 40 MoE + 8 attention
LAYERS_MAMBA, LAYERS_MOE, LAYERS_ATTN = 40, 40, 8
KV_HEADS, HEAD_DIM = 2, 128
KV_DTYPE_BYTES  = 1         # quantization_config.kv_cache_scheme: 8-bit float
ACTIVE_PARAMS_B = 12        # "120B (12B active)"
MAMBA_N_GROUPS  = 8

# Mamba2 constant state per sequence — does NOT grow with context.
MAMBA_HEADS, MAMBA_HEAD_DIM, SSM_STATE = 128, 64, 128
D_INNER, CONV_K = 8192, 4

# Only the 8 attention layers produce KV cache. 4 KiB/token.
KV_BYTES_PER_TOKEN = LAYERS_ATTN * KV_HEADS * HEAD_DIM * 2 * KV_DTYPE_BYTES


def mamba_bytes_per_seq(ssm_dtype_bytes: int) -> int:
    ssm  = MAMBA_HEADS * MAMBA_HEAD_DIM * SSM_STATE * ssm_dtype_bytes
    conv = (D_INNER + 2 * MAMBA_N_GROUPS * SSM_STATE) * CONV_K * ssm_dtype_bytes
    return (ssm + conv) * LAYERS_MAMBA


USABLE_FRACTION = 0.92              # vLLM --gpu-memory-utilization headroom
ACTIVATION_RESERVE_GB_PER_GPU = 2.0 # activations, CUDA graphs, buffers

# Supported microarchitectures, verbatim from the card:
#   "NVIDIA Ampere - A100; NVIDIA Blackwell; NVIDIA Hopper - H100-80GB"
#   Test hardware: "1-8x H100, 1-8x H200, GB200"
# A10G, L4 and L40S are NOT on that list, so the g5/g6/g6e families are out
# regardless of whether the arithmetic says the weights fit.
INSTANCES = [
    # name                gpu        n  GB/gpu  TB/s    $/hr  supported  blackwell
    ("p4de.24xlarge",     "A100-80", 8,   80,   2.039,  40.97, True,  False),
    ("p5.48xlarge",       "H100",    8,   80,   3.350,  55.04, True,  False),
    ("p5e.48xlarge",      "H200",    8,  141,   4.800,  61.78, True,  False),
    ("p6-b200.48xlarge",  "B200",    8,  180,   8.000,  92.00, True,  True),
    # Below: weights may fit arithmetically, but the microarchitecture is not
    # on Red Hat's supported list for this model. Shown so the exclusion is
    # visible rather than silent.
    ("g6e.12xlarge",      "L40S",    4,   48,   0.864,  10.49, False, False),
    ("g6e.48xlarge",      "L40S",    8,   48,   0.864,  30.13, False, False),
    ("p4d.24xlarge",      "A100-40", 8,   40,   1.555,  32.77, False, False),
]

CALIBRATE = """
Measuring throughput — the only way to get a real number
========================================================
Red Hat publishes no throughput, latency or concurrency figures for this model.
Its benchmarks are accuracy only (MMLU-Pro, TauBench, RULER). You have to
measure.

1. Serve it. Red Hat's own recipe from the model card, adapted:

   vllm serve /mnt/models \\
     --served-model-name nemotron-super \\
     --async-scheduling --dtype auto \\
     --max-model-len 32768 \\
     --swap-space 0 --trust-remote-code \\
     --gpu-memory-utilization 0.9 \\
     --max-cudagraph-capture-size 128 \\
     --enable-chunked-prefill \\
     --mamba-ssm-cache-dtype float16 \\
     --reasoning-parser nemotron_v3 \\
     --enable-auto-tool-choice --tool-call-parser qwen3_coder

   On non-Blackwell GPUs add the fallback kernels:
     VLLM_NVFP4_GEMM_BACKEND=marlin  and  --moe-backend marlin

2. Benchmark at a concurrency that reflects real serving. Concurrency 1
   measures single-user decode and understates server capacity badly:

   vllm bench serve --model nemotron-super --host localhost --port 8000 \\
     --dataset-name random --random-input-len 4000 --random-output-len 500 \\
     --max-concurrency 32 --num-prompts 200

   Or GuideLLM, which is what Red Hat uses internally:

   guidellm benchmark --target http://localhost:8000 --model nemotron-super \\
     --rate-type concurrent --rate 32 \\
     --data "prompt_tokens=4000,output_tokens=500"

3. Feed the aggregate output tokens/sec back in:

   ./hack/size-nemotron-super.py --users 25 --measured-tps <value>

Match the input/output shape to your real traffic. Agentic tool-call loops
have long prompts (system prompt + tool schemas + accumulated history) and
short completions — a very different shape from chat, and it changes the
answer substantially.

Two things that will skew a naive estimate:
  - MTP (Multi-Token Prediction) layers give this model built-in speculative
    decoding, so real tokens/sec can beat a bandwidth-bound estimate.
  - On non-Blackwell GPUs the marlin fallback kernels cost performance by an
    amount nobody has published.
"""


def estimate_tps(gpus: int, bw_tb_s: float, batch: int) -> float:
    """First-order aggregate output tok/s. Bandwidth-bound decode model.

    Reads active weights once per decode step, amortised across the batch.
    Efficiency terms are generic, not measured for this model. Ignores the
    MTP speculative-decoding uplift, so it errs low on Blackwell and high on
    Hopper/Ampere where marlin fallback kernels apply.
    """
    active_bytes = WEIGHTS_GB * 1e9 * (ACTIVE_PARAMS_B / 120.0)
    steps = (bw_tb_s * 1e12 * gpus * 0.70) / active_bytes
    tp_eff = 1.0 if gpus == 1 else 0.92 ** math.log2(gpus)
    return steps * (batch ** 0.75) * tp_eff


def main():
    ap = argparse.ArgumentParser(
        description="GPU sizing for Nemotron-3-Super-120B-A12B NVFP4 on AWS.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--users", type=int, help="concurrent active users")
    ap.add_argument("--tokens-per-sec", type=float, help="required aggregate output tok/s")
    ap.add_argument("--ctx", type=int, default=32768, help="working context per sequence (default 32768)")
    ap.add_argument("--tpot-ms", type=float, default=50.0,
                    help="target ms per output token (default 50 = 20 tok/s/user)")
    ap.add_argument("--peak", type=float, default=1.5, help="peak-to-average multiplier (default 1.5)")
    ap.add_argument("--headroom", type=float, default=0.90, help="planning capacity fraction (default 0.90)")
    ap.add_argument("--ssm-fp32", action="store_true",
                    help="size Mamba state at float32; default float16 per Red Hat's recipe")
    ap.add_argument("--measured-tps", type=float, help="measured aggregate output tok/s; replaces the estimate")
    ap.add_argument("--all-instances", action="store_true",
                    help="include instances whose GPU is not a supported microarchitecture")
    ap.add_argument("--help-calibrate", action="store_true", help="how to measure throughput")
    a = ap.parse_args()

    if a.help_calibrate:
        print(CALIBRATE); return 0
    if not a.users and not a.tokens_per_sec:
        ap.error("give --users or --tokens-per-sec (or --help-calibrate)")

    users = a.users
    if a.tokens_per_sec and not users:
        users = max(1, math.ceil(a.tokens_per_sec / (1000.0 / a.tpot_ms)))
        print(f"note: {a.tokens_per_sec:,.0f} tok/s at {a.tpot_ms:.0f} ms/token = {users} concurrent users\n")

    ssm_bytes = 4 if a.ssm_fp32 else 2
    mamba = mamba_bytes_per_seq(ssm_bytes)
    per_seq = mamba + KV_BYTES_PER_TOKEN * a.ctx
    required_tps = users * (1000.0 / a.tpot_ms) * a.peak / a.headroom

    print("⚠️  Validated on vLLM 0.18.0 / RHAIIS 3.4 / RHOAI 3.4. This repo pins RHAIIS 3.3.3")
    print("    (vLLM 0.13.0+rhai20) — this model is NOT validated on that runtime.\n")
    print(f"Model    120B total, {ACTIVE_PARAMS_B}B active | {WEIGHTS_GB} GB NVFP4 weights")
    print(f"         {TOTAL_LAYERS} layers = {LAYERS_MAMBA} Mamba2 + {LAYERS_MOE} MoE + "
          f"{LAYERS_ATTN} attention (only the 8 make KV)")
    print(f"Per seq  {mamba/1e6:.0f} MB Mamba state (constant, ssm {'fp32' if a.ssm_fp32 else 'fp16'}) "
          f"+ {KV_BYTES_PER_TOKEN/1024:.0f} KiB/tok KV")
    print(f"         = {per_seq/1e6:.0f} MB at {a.ctx:,} ctx")
    print(f"Load     {users} users @ {a.tpot_ms:.0f} ms/token, peak x{a.peak}, "
          f"{a.headroom:.0%} planning capacity")
    print(f"         -> {required_tps:,.0f} aggregate output tok/s required")
    print(f"Official minimum GPU per the model card: 1x B200 or 1x DGX Spark\n")

    cat = INSTANCES if a.all_instances else [i for i in INSTANCES if i[6]]
    print(f"{'instance':<20} {'gpu':<9} {'n':>2} {'$/hr':>7} {'fits seqs':>10} {'est tok/s':>10}  verdict")
    print("-" * 95)
    viable = []
    for name, gpu, n, gb, bw, price, supported, bb in cat:
        usable = n * gb * USABLE_FRACTION - n * ACTIVATION_RESERVE_GB_PER_GPU
        free = usable - WEIGHTS_GB
        if free <= 0:
            print(f"{name:<20} {gpu:<9} {n:>2} {price:>7.2f} {'—':>10} {'—':>10}  weights do not fit")
            continue
        if MAMBA_N_GROUPS % n:
            print(f"{name:<20} {gpu:<9} {n:>2} {price:>7.2f} {'—':>10} {'—':>10}  "
                  f"TP {n} does not divide Mamba n_groups={MAMBA_N_GROUPS}")
            continue
        max_seq = int(free * 1e9 / per_seq)
        tps = a.measured_tps or estimate_tps(n, bw, min(users, max_seq) or 1)
        why = ""
        if max_seq < users:            why = f"memory caps at {max_seq} seqs"
        elif tps < required_tps:       why = f"throughput short ({tps:,.0f} < {required_tps:,.0f})"
        if not why: viable.append((price, name, gpu, n, max_seq, tps, bb, supported))
        tag = "" if supported else "  [unsupported microarch]"
        print(f"{name:<20} {gpu:<9} {n:>2} {price:>7.2f} {max_seq:>10,} {tps:>10,.0f}  "
              f"{(why or 'OK') + tag}")

    if viable:
        viable.sort()
        price, name, gpu, n, max_seq, tps, bb, supported = viable[0]
        mo = price * 730
        print(f"\nCheapest that fits: {name} ({n}x {gpu}) — ${price:.2f}/hr, ${mo:,.0f}/mo")
        print(f"  memory ceiling {max_seq:,} sequences at {a.ctx:,} ctx — "
              f"{max_seq/users:.0f}x the {users} asked for")
        print(f"  that headroom is REAL but not a throughput promise. Latency, not memory,")
        print(f"  will bind first. Validate with --help-calibrate before committing.")
        tok_mo = users * (1000.0 / a.tpot_ms) * 3600 * 730
        print(f"  at full utilisation ~{tok_mo/1e9:.1f}B output tok/mo = ${mo/(tok_mo/1e6):.4f}/1M tok")

        # The cost story that matters: AWS has no single-GPU A100/H100/B200
        # instance. The p-family is 8-GPU only, so the footprint — and the bill —
        # is fixed no matter how few users you have.
        print(f"\n  COST FLOOR. The card's minimum is 1x B200, but AWS does not rent single")
        print(f"  A100/H100/B200 GPUs — the p-family starts at 8. So ${mo:,.0f}/mo is the floor")
        print(f"  for this model on supported AWS hardware, at ANY user count.")
        print(f"    {users:>5} users -> ${mo/users:>8,.0f}/user/mo, ${mo/(tok_mo/1e6):>7.2f}/1M output tok")
        for n_u in (25, 50, 100, 250, 500):
            if n_u <= users: continue
            cap = min(n_u, max_seq)
            t = cap * (1000.0 / a.tpot_ms) * 3600 * 730
            print(f"    {cap:>5} users -> ${mo/cap:>8,.0f}/user/mo, ${mo/(t/1e6):>7.2f}/1M output tok")
        print(f"  Unit cost falls linearly with utilisation. Below roughly 50-100 concurrent")
        print(f"  users this model is hard to justify on AWS against a hosted API or a")
        print(f"  smaller self-hosted model — the fixed floor dominates.")
        if not bb:
            print(f"  NVFP4 on {gpu} needs the marlin fallback: VLLM_NVFP4_GEMM_BACKEND=marlin")
            print(f"  and --moe-backend marlin. Performance cost is not published.")
    else:
        print("\nNothing in the supported catalog satisfies this load. Add replicas,")
        print("relax --tpot-ms, or reduce --ctx. Try --all-instances to see the excluded ones.")

    print(f"\nMemory: exact, from config.json. Throughput: "
          f"{'measured' if a.measured_tps else 'ESTIMATED +/- ~2x — no Red Hat benchmarks exist'}.")
    print("Prices approximate us-east-1 on-demand; verify before quoting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

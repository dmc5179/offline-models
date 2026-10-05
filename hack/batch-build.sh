#!/bin/bash
# Build and push the model images that have no Red Hat ModelCar alternative.
#
# These five are the only ones that genuinely require building. Every other
# model in this repo either ships as a Red Hat ModelCar (mirror it instead -
# see the redhat_modelcar column in model-list.csv) or is not wanted.
#
# Intended for an unattended overnight run on a build host with bandwidth.
# All preflight checks run BEFORE the first download, so a bad flag or a
# missing credential fails in seconds rather than eight hours in.
#
#   ./hack/batch-build.sh --authfile ~/quay-pull-secret.json
#   ./hack/batch-build.sh --authfile ~/quay-pull-secret.json --clean-weights --shutdown
#
# Each model is built by its own build.sh, so this script never duplicates
# build logic - it only sequences, cleans up, and reports.

set -uo pipefail   # deliberately NOT -e: one model failing must not abandon the rest

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# dir:approx weight download GB (for the disk preflight)
MODELS=(
  "granite-guardian/3.2-5B:12"
  "qwen3-embedding/8B:16"
  "gemma/3-12B-it:25"
  "gemma/4-26B-A4B-FP8:29"
  "gemma/4-31B-FP8:34"
)

AUTHFILE=""
SHUTDOWN=0
CLEAN_WEIGHTS=0
DRY_RUN=0
LOG="${REPO_ROOT}/logs/batch-build-$(date +%Y%m%d-%H%M%S).log"

usage() {
  cat <<EOF
Usage: $(basename "$0") --authfile PATH [--shutdown] [--clean-weights] [--dry-run]

  --authfile PATH   Registry credentials JSON for the push (required).
                    Must also be able to pull registry.redhat.io base images,
                    or have those credentials in podman's default search path.
  --clean-weights   Delete each model's downloaded weights after a successful
                    push. Strongly recommended for a full run - without it this
                    needs roughly twice the disk. See the preflight estimate.
  --shutdown        Power the machine off when the run finishes. Fires whether
                    or not every model succeeded; read the log afterwards.
                    Waits 60s first so a console user can Ctrl-C.
  --dry-run         Run preflight and print the plan, build nothing.
  -h, --help        This help.

Builds, in ascending size order:
$(for m in "${MODELS[@]}"; do printf '  %-26s ~%s GB weights\n' "${m%%:*}" "${m##*:}"; done)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --authfile)      AUTHFILE="${2:-}"
                     [[ -n "$AUTHFILE" ]] || { echo "error: --authfile requires a path" >&2; exit 2; }
                     shift 2 ;;
    --authfile=*)    AUTHFILE="${1#*=}"; shift ;;
    --shutdown)      SHUTDOWN=1; shift ;;
    --clean-weights) CLEAN_WEIGHTS=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    -h|--help)       usage; exit 0 ;;
    *)               echo "error: unknown option '$1'" >&2; echo >&2; usage >&2; exit 2 ;;
  esac
done

mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1

say()  { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
fail() { printf '\n[%s] ERROR: %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
ok()   { printf '  %-24s OK  %s\n' "$1" "${2:-}"; }
bad()  { printf '  %-24s --  %s\n' "$1" "${2:-}"; }

# ---------------------------------------------------------------- preflight
say "Preflight"
PF_OK=1

[[ -n "$AUTHFILE" ]] || { fail "--authfile is required"; usage >&2; exit 2; }
if [[ -f "$AUTHFILE" ]]; then
  if python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$AUTHFILE" 2>/dev/null; then
    ok authfile "$AUTHFILE"
  else
    fail "authfile is not valid JSON: $AUTHFILE"; PF_OK=0
  fi
else
  fail "authfile not found: $AUTHFILE"; PF_OK=0
fi

for bin in podman hf skopeo; do
  if command -v "$bin" >/dev/null 2>&1; then ok "$bin" "$(command -v "$bin")"
  else fail "$bin not found in PATH"; PF_OK=0; fi
done

if [[ -n "${HF_TOKEN:-}" ]]; then ok HF_TOKEN "(set)"
else fail "HF_TOKEN is not set - gated model downloads will fail"; PF_OK=0; fi

# Base image must be pullable, or every build fails at FROM.
BASE="registry.redhat.io/rhaiis/vllm-cuda-rhel9:3.3.3"
if skopeo inspect --authfile "$AUTHFILE" "docker://${BASE}" >/dev/null 2>&1 \
   || skopeo inspect "docker://${BASE}" >/dev/null 2>&1; then
  ok "base image" "${BASE}"
else
  fail "cannot reach ${BASE} - check registry.redhat.io credentials"; PF_OK=0
fi

# Every build dir must exist and be executable before we commit to the run.
for entry in "${MODELS[@]}"; do
  d="${entry%%:*}"
  if [[ -x "${REPO_ROOT}/${d}/build.sh" ]]; then ok "$d" "build.sh"
  else fail "missing or non-executable: ${d}/build.sh"; PF_OK=0; fi
done

# Disk. Without --clean-weights, weights AND images coexist for the whole run.
NEED=0; for entry in "${MODELS[@]}"; do NEED=$((NEED + ${entry##*:})); done
if [[ "$CLEAN_WEIGHTS" -eq 1 ]]; then
  EST=$(( (NEED / 5 * 2) + 40 ))   # peak is roughly the largest model twice over, plus slack
  NOTE="peak with --clean-weights"
else
  EST=$(( NEED * 2 + 40 ))         # all weights + all images retained
  NOTE="total WITHOUT --clean-weights"
fi
AVAIL=$(df -BG --output=avail "$REPO_ROOT" | tail -1 | tr -dc '0-9')
printf '  %-24s %s  need ~%s GB (%s), have %s GB\n' \
  disk "$([[ "$AVAIL" -gt "$EST" ]] && echo OK || echo LOW)" "$EST" "$NOTE" "$AVAIL"
[[ "$AVAIL" -gt "$EST" ]] || { fail "insufficient disk: need ~${EST} GB, have ${AVAIL} GB"; PF_OK=0; }

if [[ "$SHUTDOWN" -eq 1 ]]; then
  if sudo -n true 2>/dev/null; then ok "sudo (shutdown)" "passwordless"
  else fail "--shutdown needs passwordless sudo; it would prompt with nobody watching"; PF_OK=0; fi
fi

[[ "$PF_OK" -eq 1 ]] || { fail "preflight failed - nothing was built"; exit 1; }
say "Preflight passed. Log: $LOG"

if [[ "$DRY_RUN" -eq 1 ]]; then
  say "--dry-run: plan only"
  for entry in "${MODELS[@]}"; do echo "  would build+push ${entry%%:*}"; done
  [[ "$SHUTDOWN" -eq 1 ]] && echo "  would shut down afterwards"
  exit 0
fi

# ---------------------------------------------------------------- the run
declare -a RESULTS=()
STARTED=$(date +%s)

for entry in "${MODELS[@]}"; do
  d="${entry%%:*}"
  dir="${REPO_ROOT}/${d}"
  image=$(sed -n 's/^IMAGE_NAME="\([^"]*\)".*/\1/p' "${dir}/build.sh")
  reg=$(sed -n 's/^REGISTRY="${REGISTRY:-\([^}]*\)}".*/\1/p' "${dir}/build.sh")
  weights=$(sed -n 's/^LOCAL_DIR="\([^"]*\)".*/\1/p' "${dir}/build.sh")
  full="${reg}/${image}:latest"

  say "=== ${d}  ->  ${full}"
  t0=$(date +%s)

  if ( cd "$dir" && ./build.sh --push --authfile "$AUTHFILE" ); then
    took=$(( ($(date +%s) - t0) / 60 ))
    say "${d}: pushed OK (${took} min)"

    if podman rmi "$full" >/dev/null 2>&1; then
      echo "  removed local image ${full}"
    else
      echo "  note: could not remove ${full} (may be referenced elsewhere)"
    fi

    if [[ "$CLEAN_WEIGHTS" -eq 1 && -n "$weights" && -d "${dir}/${weights}" ]]; then
      rm -rf "${dir:?}/${weights:?}" && echo "  removed weights ${d}/${weights}"
    fi

    RESULTS+=("OK      ${d} (${took} min)")
  else
    rc=$?
    fail "${d}: build or push FAILED (exit ${rc}) - weights and image left in place for debugging"
    RESULTS+=("FAILED  ${d} (exit ${rc})")
  fi
done

# ---------------------------------------------------------------- summary
TOTAL=$(( ($(date +%s) - STARTED) / 60 ))
say "Summary after ${TOTAL} min"
for r in "${RESULTS[@]}"; do echo "  $r"; done
FAILED=$(printf '%s\n' "${RESULTS[@]}" | grep -c '^FAILED' || true)
echo
echo "  ${#RESULTS[@]} attempted, $(( ${#RESULTS[@]} - FAILED )) succeeded, ${FAILED} failed"
echo "  log: $LOG"
df -h "$REPO_ROOT" | tail -1 | awk '{print "  disk now: "$4" available"}'

if [[ "$SHUTDOWN" -eq 1 ]]; then
  say "Shutting down in 60s - Ctrl-C to cancel"
  sleep 60
  sudo shutdown -h now
fi

[[ "$FAILED" -eq 0 ]] || exit 1
exit 0

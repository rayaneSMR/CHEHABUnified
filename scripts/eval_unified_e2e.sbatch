#!/bin/bash
# Real compile + SEAL execution evaluation of the unified joint agent:
# one budget x one (or more) C++ benchmark(s), at every preference.
#
#   sbatch scripts/eval_unified_e2e.sbatch BUDGET MODEL BENCHMARKS [PREFERENCES]
#     BUDGET       noise budget in bits (230, 236, 369 or 9000000)
#     MODEL        trained joint model .zip (absolute path)
#     BENCHMARKS   comma-separated, e.g. dot_product or box_blur,gx_kernel (or "all")
#     PREFERENCES  optional "w_ops,w_keys;..." (default: the 10 training preferences)
#
# Usually submitted by scripts/launch_unified_e2e.sh. Needs a built clone
# (bash scripts/build_e2e_benchmarks.sh) and SEAL 4.1.
# Output: RL/test_results/e2e_<benchmarks>_b<budget>_<jobid>.csv
#
# Original CHEHAB RL agent instead of the unified one (single objective, no budget, no
# preference; agent_model in RL/fhe_rl/config.py): set FHE_E2E_FRAMEWORK=original. MODEL,
# BUDGET and the preference are then ignored by the agent; pass one preference to run each
# benchmark once. Output: RL/test_results/e2e_original_<benchmarks>_<jobid>.csv

#SBATCH -p compute
#SBATCH --mem 32GB
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH -t 2-00:00:00
#SBATCH -o logs/output.e2e.%j.txt
#SBATCH -e logs/error.e2e.%j.txt
#SBATCH -J e2e-unified

BUDGET="${1:?usage: sbatch eval_unified_e2e.sbatch BUDGET MODEL BENCHMARKS [PREFERENCES]}"
MODEL="${2:?missing MODEL}"
BENCHMARKS="${3:?missing BENCHMARKS}"
PREFERENCES="${4:-}"

# System compiler for the generated SEAL programs, found before conda (see build_e2e_benchmarks.sh)
module load gcc 2>/dev/null || true
export FHE_E2E_CXX="${FHE_E2E_CXX:-$(which g++ 2>/dev/null || echo /usr/bin/g++)}"

set +u
if [ -f "/share/apps/NYUAD5/miniconda/3-4.11.0/bin/activate" ]; then
    source /share/apps/NYUAD5/miniconda/3-4.11.0/bin/activate
fi
conda activate /scratch/${USER}/conda/envs/chehabEnv 2>/dev/null \
    || conda activate chehabEnv 2>/dev/null \
    || true
set -u
unset CXX CC CXXFLAGS CFLAGS CPPFLAGS LDFLAGS
export PYTHONUNBUFFERED=1
export PYTHON="$(which python)"     # the compiler calls $PYTHON -m fhe_rl (else /usr/bin/python3)

if [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/RL" ]; then
    PROJ_ROOT="$SLURM_SUBMIT_DIR"
else
    PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$PROJ_ROOT"
export PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}"
mkdir -p RL/test_results logs

# SEAL 4.1 for the generated programs (the one built by build_bfv_noise_cli.sh, or SEAL_DIR)
if [ -z "${SEAL_DIR:-}" ]; then
    SEAL_CONFIG="$(find /scratch/${USER}/opt/SEAL-4.1 ${CONDA_PREFIX:-} -maxdepth 6 -name SEALConfig.cmake -path '*SEAL-4.1*' 2>/dev/null | head -n 1 || true)"
    [ -n "$SEAL_CONFIG" ] && export SEAL_DIR="$(dirname "$SEAL_CONFIG")"
fi
if [ -z "${SEAL_DIR:-}" ]; then
    echo "ERROR: SEAL 4.1 not found. Run scripts/build_bfv_noise_cli.sh once, or set SEAL_DIR."
    exit 1
fi

# SEAL noise-bound certificate for the agent's rollback (read by `fhe_rl run` through the
# compiler's subprocess). Same parameters as the generated SEAL programs:
#   N = 16384, t = PlainModulus::Batching(16384, 20) = 786433, q = BFVDefault(16384).
export FHE_BFV_NOISE_BOUND_EXECUTABLE="${FHE_BFV_NOISE_BOUND_EXECUTABLE:-$PROJ_ROOT/build_bfv_noise/bfv_noise_bound_cli}"
export FHE_BFV_POLY_MODULUS_DEGREE=16384
export FHE_BFV_PLAIN_MODULUS=786433
export FHE_BFV_COEFF_MODULUS_BITS=48,48,48,49,49,49,49,49,49
if [ "${FHE_E2E_FRAMEWORK:-unified}" != "original" ] && [ ! -x "$FHE_BFV_NOISE_BOUND_EXECUTABLE" ]; then
    echo "ERROR: noise-bound certificate not found: $FHE_BFV_NOISE_BOUND_EXECUTABLE (run scripts/build_bfv_noise_cli.sh)"
    exit 1
fi

TAG="$(echo "$BENCHMARKS" | tr ',' '-')"
JOB="${SLURM_JOB_ID:-local}"
FRAMEWORK="${FHE_E2E_FRAMEWORK:-unified}"
if [ "$FRAMEWORK" = "original" ]; then
    OUT="RL/test_results/e2e_original_${TAG}_${JOB}.csv"
else
    OUT="RL/test_results/e2e_${TAG}_b${BUDGET}_${JOB}.csv"
fi
PREF_ARGS=()
[ -n "$PREFERENCES" ] && PREF_ARGS=(--prefs "$PREFERENCES")

echo "════════════════════════════════════════════════════════════"
echo "  UNIFIED AGENT: REAL COMPILE + SEAL EXECUTION"
echo "  Framework:   $FRAMEWORK"
echo "  Model:       $MODEL"
echo "  Benchmarks:  $BENCHMARKS"
echo "  Budget:      $BUDGET bits"
echo "  Python:      $PYTHON"
echo "  C++:         $FHE_E2E_CXX"
echo "  SEAL:        $SEAL_DIR"
echo "  Certificate: $FHE_BFV_NOISE_BOUND_EXECUTABLE"
echo "  Output:      $OUT"
echo "════════════════════════════════════════════════════════════"

python -u scripts/run_benchmarks_unified.py \
    --framework "$FRAMEWORK" \
    --model "$MODEL" \
    --budget "$BUDGET" \
    --benchmarks "$BENCHMARKS" \
    ${PREF_ARGS[@]+"${PREF_ARGS[@]}"} \
    --work-dir "e2e_${TAG}_b${BUDGET}_${JOB}" \
    --seal-dir "$SEAL_DIR" \
    --cxx "$FHE_E2E_CXX" \
    --output "$OUT"

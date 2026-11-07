#!/bin/bash
# One evaluation job of the unified joint agent: one dataset x one budget,
# evaluated at every preference (default: the 10 training preferences [1,0] ... [0.1,0.9]).
#
#   sbatch scripts/eval_unified_sweep.sbatch DATASET BUDGET MODEL [PREFERENCES] [AGENT_BUDGET]
#     DATASET      file name in RL/fhe_rl/datasets/ (e.g. benchmarks.txt)
#     BUDGET       noise budget in bits to test on (230, 236, 369 or 9000000)
#     MODEL        trained joint model .zip (absolute path)
#     PREFERENCES  optional, "w_ops,w_keys;w_ops,w_keys;..." (e.g. "0.9,0.1;0.5,0.5");
#                  pass "" to keep the default
#     AGENT_BUDGET optional, budget given to the agent instead of BUDGET. 9000000 runs it
#                  unconstrained; the rollback and violation columns still use BUDGET.
#                  The output is then named eval_<dataset>_b<BUDGET>_agent<AGENT_BUDGET>_<jobid>.
#
# Usually submitted by scripts/launch_unified_eval.sh (one job per dataset x budget).
# Output: RL/test_results/eval_<dataset>_b<budget>_<jobid>.xlsx (+ .csv)

#SBATCH -p compute
#SBATCH --mem 16GB
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 4
#SBATCH -t 12:00:00
#SBATCH -o logs/output.eval_sweep.%j.txt
#SBATCH -e logs/error.eval_sweep.%j.txt
#SBATCH -J eval-sweep

set +u
if [ -f "/share/apps/NYUAD5/miniconda/3-4.11.0/bin/activate" ]; then
    source /share/apps/NYUAD5/miniconda/3-4.11.0/bin/activate
fi
conda activate /scratch/${USER}/conda/envs/chehabEnv 2>/dev/null \
    || conda activate chehabEnv 2>/dev/null \
    || true
set -u
export PYTHONUNBUFFERED=1

DATASET="${1:?usage: sbatch eval_unified_sweep.sbatch DATASET BUDGET MODEL [PREFERENCES]}"
BUDGET="${2:?missing BUDGET}"
MODEL="${3:?missing MODEL}"
PREFERENCES="${4:-}"
AGENT_BUDGET="${5:-}"

# Run in the folder the job was submitted from (keep evaluations in their own clone).
if [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/RL" ]; then
    PROJ_ROOT="$SLURM_SUBMIT_DIR"
else
    PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$PROJ_ROOT/RL"
export PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}"
mkdir -p "$PROJ_ROOT/RL/test_results" "$PROJ_ROOT/logs"

TRAIN_BUDGETS="230,236,369,9000000"   # budgets the joint agent was trained on
DATASET_FILE="./fhe_rl/datasets/${DATASET}"
TAG="${DATASET%.txt}"
AGENT_TAG="${AGENT_BUDGET:+_agent${AGENT_BUDGET}}"
OUT="$PROJ_ROOT/RL/test_results/eval_${TAG}_b${BUDGET}${AGENT_TAG}_${SLURM_JOB_ID:-local}.xlsx"

# BFV rollback certificate: parameters of CHEHAB's generated SEAL programs
#   N = 16384, t = PlainModulus::Batching(16384, 20) = 786433, q = BFVDefault(16384).
# The CLI path can be overridden (e.g. to reuse the one built in another clone).
export FHE_BFV_NOISE_BOUND_EXECUTABLE="${FHE_BFV_NOISE_BOUND_EXECUTABLE:-$PROJ_ROOT/build_bfv_noise/bfv_noise_bound_cli}"
export FHE_BFV_POLY_MODULUS_DEGREE=16384
export FHE_BFV_PLAIN_MODULUS=786433
export FHE_BFV_COEFF_MODULUS_BITS=48,48,48,49,49,49,49,49,49

for f in "$MODEL" "$DATASET_FILE" "$FHE_BFV_NOISE_BOUND_EXECUTABLE"; do
    if [ ! -e "$f" ]; then
        echo "ERROR: not found: $f"
        exit 1
    fi
done

PREF_ARGS=()
if [ -n "$PREFERENCES" ]; then
    PREF_ARGS=(--preferences "$PREFERENCES")
fi
if [ -n "$AGENT_BUDGET" ]; then
    PREF_ARGS+=(--agent_budget "$AGENT_BUDGET")
fi

echo "════════════════════════════════════════════════════════════"
echo "  UNIFIED JOINT AGENT EVALUATION"
echo "  Model:        $MODEL"
echo "  Dataset:      $DATASET_FILE ($(wc -l < "$DATASET_FILE") expressions)"
echo "  Budget:       $BUDGET bits   (trained on $TRAIN_BUDGETS)"
echo "  Agent budget: ${AGENT_BUDGET:-$BUDGET} bits"
echo "  Preferences:  ${PREFERENCES:-10 training preferences [1,0] ... [0.1,0.9]}"
echo "  Certificate:  $FHE_BFV_NOISE_BOUND_EXECUTABLE"
echo "  Output:       $OUT"
echo "════════════════════════════════════════════════════════════"

stdbuf -oL -eL python -u -m fhe_rl \
    --framework unified \
    --embedder gnn \
    test \
    --model "$MODEL" \
    --dataset "$DATASET_FILE" \
    --budgets "$BUDGET" \
    --train_budgets "$TRAIN_BUDGETS" \
    --method nato_sc \
    --constraint noise \
    --pipeline joint \
    --v2 \
    ${PREF_ARGS[@]+"${PREF_ARGS[@]}"} \
    --output "$OUT"

echo "Done: $OUT"

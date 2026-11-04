#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Experiment 3 evaluation: unified agent with BOTH metric families, on every
# non-DNN benchmark (RL/fhe_rl/datasets/benchmarks.txt minus DNN = 43 kernels + 26 synthetic).
#
#  A. CONSTRAINED metrics  (fhe_rl test --v2, BFV rollback certificate)
#     every benchmark x budget {230,236,369,9e6} x the 10 preferences:
#     feasibility at start, agent / safe compliance, rollback rate, safe & raw exec/keys
#     reductions, BFV certified remaining noise budget
#  B. MORL metrics  (fhe_rl bisection, Algorithm 3)
#     every benchmark x budget: coarse grid over w_ops in [0.1, 1] + bisection (depth 3)
#     -> Pareto front, IC / HV / SP / EU / bisection yield
#  C. summary.xlsx merging both (per budget, per budget x preference)
#
# A and B run in parallel on the same node.
#
# Usage (repo root):
#   sbatch scripts/eval_unified_uniform.sbatch                          # final uniform model
#   sbatch scripts/eval_unified_uniform.sbatch <model.zip> <tag>        # any unified model
#   sbatch --dependency=afterok:<train_jobid> scripts/eval_unified_uniform.sbatch   # after training
# Needs: build_bfv_noise/bfv_noise_bound_cli  (sbatch scripts/build_bfv_noise_cli.sbatch)
# ════════════════════════════════════════════════════════════════════════════

#SBATCH -p compute
#SBATCH --mem 32GB
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 3-00:00:00

#SBATCH --mail-user=rs10728@nyu.edu
#SBATCH --mail-type=BEGIN,END,FAIL

#SBATCH -o logs/output.eval_uniform.%j.txt
#SBATCH -e logs/error.eval_uniform.%j.txt
#SBATCH -J eval-uniform

set -eo pipefail

# ── conda env (fhe_rl), fail loudly ──────────────────────────────────────────
CONDA_BASE="${CONDA_BASE:-/share/apps/NYUAD5/miniconda/3-4.11.0}"
CONDA_ENV="${CONDA_ENV:-/home/rs10728/.conda/envs/fhe_rl}"
set +u
source "$CONDA_BASE/bin/activate" || { echo "[FAIL] cannot source $CONDA_BASE/bin/activate"; exit 1; }
conda activate "$CONDA_ENV" || { echo "[FAIL] cannot activate conda env $CONDA_ENV"; exit 1; }
set -u
echo "Python: $(which python)"
export PYTHONUNBUFFERED=1

if [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/RL" ]; then
    PROJ_ROOT="$SLURM_SUBMIT_DIR"
else
    PROJ_ROOT="/scratch/${USER}/chehab-unified"
fi
mkdir -p "$PROJ_ROOT/logs"
cd "$PROJ_ROOT/RL"
export PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}"

# ── settings (same as training: train_unified_noise / train_unified_uniform_pref) ──
MODEL="${1:-$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_uniform_pref.zip}"
TAG="${2:-uniform}"
BUDGETS="230,236,369,9000000"
TRAIN_BUDGETS="230,236,369,9000000"
METHOD="nato_sc"
CONSTRAINT="noise"
W_LO=0.1
W_HI=1.0
MAX_DEPTH=3
JOB="${SLURM_JOB_ID:-local}"

[ -f "$MODEL" ] || { echo "[FAIL] model not found: $MODEL"; exit 1; }

# ── BFV rollback certificate (same parameters as CHEHAB's generated SEAL programs) ──
export FHE_BFV_NOISE_BOUND_EXECUTABLE="$PROJ_ROOT/build_bfv_noise/bfv_noise_bound_cli"
export FHE_BFV_POLY_MODULUS_DEGREE=16384
export FHE_BFV_PLAIN_MODULUS=786433
export FHE_BFV_COEFF_MODULUS_BITS=48,48,48,49,49,49,49,49,49
[ -x "$FHE_BFV_NOISE_BOUND_EXECUTABLE" ] || {
    echo "[FAIL] BFV CLI missing: $FHE_BFV_NOISE_BOUND_EXECUTABLE (sbatch scripts/build_bfv_noise_cli.sbatch)"; exit 1; }

OUT_DIR="$PROJ_ROOT/RL/test_results/exp3_eval_${TAG}_${JOB}"
mkdir -p "$OUT_DIR"
BENCH="$OUT_DIR/benchmarks_no_dnn.txt"
CONSTRAINED_OUT="$OUT_DIR/constrained_${TAG}.xlsx"
MORL_OUT="$OUT_DIR/morl_bisection_${TAG}.xlsx"
SUMMARY_OUT="$OUT_DIR/summary_${TAG}.xlsx"
LOG_A="$PROJ_ROOT/logs/eval_uniform_constrained_${JOB}.log"
LOG_B="$PROJ_ROOT/logs/eval_uniform_morl_${JOB}.log"

# ── evaluation set: benchmarks.txt minus DNN, with names ─────────────────────
python "$PROJ_ROOT/scripts/exp3_eval_helpers.py" build-benchmarks \
    --datasets "$PROJ_ROOT/RL/fhe_rl/datasets" --out "$BENCH"
N_BENCH=$(grep -c . "$BENCH")

echo "════════════════════════════════════════════════════════════"
echo "  EXPERIMENT 3 EVALUATION (constrained + MORL metrics)"
echo "  Model:        $MODEL   (tag: $TAG)"
echo "  Benchmarks:   $N_BENCH (non-DNN)  -> $BENCH"
echo "  Budgets:      $BUDGETS (trained on $TRAIN_BUDGETS)   Method: $METHOD"
echo "  A constrained: 10 preferences x budgets, BFV certificate N=$FHE_BFV_POLY_MODULUS_DEGREE"
echo "  B MORL:       grid w_ops [$W_LO, $W_HI] + bisection depth $MAX_DEPTH"
echo "  Output dir:   $OUT_DIR"
echo "  Logs:         $LOG_A"
echo "                $LOG_B"
echo "════════════════════════════════════════════════════════════"

# ── A. constrained metrics ───────────────────────────────────────────────────
stdbuf -oL -eL python -u -m fhe_rl \
    --framework unified --embedder gnn \
    test \
    --model "$MODEL" \
    --pipeline joint \
    --benchmark "$BENCH" \
    --budgets "$BUDGETS" \
    --train_budgets "$TRAIN_BUDGETS" \
    --method "$METHOD" \
    --constraint "$CONSTRAINT" \
    --v2 \
    --output "$CONSTRAINED_OUT" \
    > "$LOG_A" 2>&1 &
PID_A=$!

# ── B. MORL metrics ──────────────────────────────────────────────────────────
stdbuf -oL -eL python -u -m fhe_rl \
    --framework unified --embedder gnn \
    bisection \
    --model "$MODEL" \
    --benchmarks "$BENCH" \
    --budgets "$BUDGETS" \
    --train_budgets "$TRAIN_BUDGETS" \
    --constraint "$CONSTRAINT" \
    --method "$METHOD" \
    --w_lo $W_LO --w_hi $W_HI --max_depth $MAX_DEPTH \
    --output "$MORL_OUT" \
    > "$LOG_B" 2>&1 &
PID_B=$!

STATUS_A=0; STATUS_B=0
wait $PID_A || STATUS_A=$?
echo "[A] constrained evaluation finished (exit $STATUS_A)"
wait $PID_B || STATUS_B=$?
echo "[B] MORL bisection finished (exit $STATUS_B)"

# ── C. merged summary ────────────────────────────────────────────────────────
python "$PROJ_ROOT/scripts/exp3_eval_helpers.py" summarize \
    --constrained-csv "${CONSTRAINED_OUT%.xlsx}.csv" \
    --morl-xlsx "$MORL_OUT" \
    --out "$SUMMARY_OUT" || echo "[warn] summary failed"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  DONE   constrained: exit $STATUS_A   MORL: exit $STATUS_B"
echo "  Constrained: $CONSTRAINED_OUT (+ .csv)"
echo "  MORL:        $MORL_OUT"
echo "  Summary:     $SUMMARY_OUT"
echo "════════════════════════════════════════════════════════════"
[ "$STATUS_A" -eq 0 ] && [ "$STATUS_B" -eq 0 ]

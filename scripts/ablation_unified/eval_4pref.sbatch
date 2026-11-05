#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Constraint-method ablation on the UNIFIED agent, 4-preference agents — EVALUATION (estimate-based)
#   trained by: scripts/ablation_unified/train_<agent>_4pref.sbatch
#   agents:     unconstrained  v4_mb  v4_nmask  v4_mb_film  v5_focops  v5_lagpid
#
# Same evaluation as eval_<agent>.sbatch, but at the agents' 4 training preferences only:
#   w = [1.0,0.0] [0.9,0.1] [0.8,0.2] [0.6,0.4]   (test --preferences)
# WITHOUT and WITH safety rollback come from the SAME run: `fhe_rl test` (v2) logs,
# for every (expression, budget, preference):
#   Agent ...  = the agent's final expression        -> WITHOUT rollback (Experiment 2)
#   Safe  ...  = best valid state of the trajectory  -> WITH rollback    (Experiment 3)
#   Ops / Keys = execution-cost model C_exec / number of unique rotation keys C_keys
# Two benchmark sets (run in parallel):
#   original   = RL/fhe_rl/datasets/benchmarks.txt minus DNN (69 expressions)
#   threshold  = RL/fhe_rl/datasets/threshold_benchmarks.txt  (60, initial noise at 80-100% of a budget)
# Budgets 230,236,369,9000000 x the 4 preferences. Rollback validity uses the BFV certificate.
# Measured SEAL execution time / rotation-key size: scripts/ablation_unified/e2e_4pref.sh (real compile + SEAL run)
#
# Output (own folder per agent and per job, nothing overwritten):
#   results/ablation_unified/<agent>_4pref/eval_<jobid>/
#       original.xlsx/.csv  threshold.xlsx/.csv   (all rows: Agent* and Safe* columns)
#       summary.csv                                (per set x budget: no-rollback vs rollback)
#
# Usage (repo root):  sbatch scripts/ablation_unified/eval_4pref.sbatch <agent> [model.zip]
#   after training:  sbatch --dependency=afterok:<train_jobid> scripts/ablation_unified/eval_4pref.sbatch <agent>
#   all six:         bash scripts/ablation_unified/launch_4pref_eval.sh
# Needs: build_bfv_noise/bfv_noise_bound_cli   (sbatch scripts/build_bfv_noise_cli.sbatch)
# ════════════════════════════════════════════════════════════════════════════

#SBATCH -p compute
#SBATCH --mem 32GB
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 8
#SBATCH -t 3-00:00:00

#SBATCH --mail-user=rs10728@nyu.edu
#SBATCH --mail-type=BEGIN,END,FAIL

#SBATCH -o logs/output.abl_eval_4pref.%j.txt
#SBATCH -e logs/error.abl_eval_4pref.%j.txt
#SBATCH -J abl-eval-4pref

set -eo pipefail

AGENT="${1:-}"
# constraint method the agent was trained with (algo and budget encoding are read from the model .zip)
case "$AGENT" in
    unconstrained) METHOD="none" ;;            # ppo, film
    v4_mb)         METHOD="margin_barrier" ;;  # ppo, raw
    v4_nmask)      METHOD="noise_masking" ;;   # ppo, embed
    v4_mb_film)    METHOD="margin_barrier" ;;  # ppo, film
    v5_focops)     METHOD="nato_sc" ;;         # focops, film
    v5_lagpid)     METHOD="nato_sc" ;;         # lagrangian_pid, film (constrained reference)
    *) echo "[FAIL] usage: sbatch $0 <unconstrained|v4_mb|v4_nmask|v4_mb_film|v5_focops|v5_lagpid> [model.zip]"; exit 1 ;;
esac

set +u
CONDA_BASE="${CONDA_BASE:-/share/apps/NYUAD5/miniconda/3-4.11.0}"
CONDA_ENV="${CONDA_ENV:-/home/rs10728/.conda/envs/fhe_rl}"
source "$CONDA_BASE/bin/activate" || { echo "[FAIL] cannot source $CONDA_BASE/bin/activate"; exit 1; }
conda activate "$CONDA_ENV" || { echo "[FAIL] cannot activate conda env $CONDA_ENV"; exit 1; }
echo "Python: $(which python)"
set -u

export PYTHONUNBUFFERED=1

if [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/RL" ]; then
    PROJ_ROOT="$SLURM_SUBMIT_DIR"
else
    PROJ_ROOT="/scratch/${USER}/chehab-unified"
fi

cd "$PROJ_ROOT/RL"
export PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}"

# ── settings (must match training: train_<agent>_4pref.sbatch) ──────────────
CONSTRAINT="noise"
BUDGETS="230,236,369,9000000"
TRAIN_BUDGETS="230,236,369,9000000"
PREFERENCES="1.0,0.0;0.9,0.1;0.8,0.2;0.6,0.4"
# default: best eval checkpoint, else the final model
TRAINED="$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_abl_${AGENT}_4pref"
if [ -n "${2:-}" ]; then MODEL="$2"
elif [ -f "${TRAINED}_best.zip" ]; then MODEL="${TRAINED}_best.zip"
else MODEL="${TRAINED}.zip"; fi
[ -f "$MODEL" ] || { echo "[FAIL] model not found: $MODEL (train it: sbatch scripts/ablation_unified/train_${AGENT}_4pref.sbatch)"; exit 1; }

# ── BFV rollback certificate (same parameters as CHEHAB's generated SEAL programs) ──
BFV_CLI="$PROJ_ROOT/build_bfv_noise/bfv_noise_bound_cli"
[ -x "$BFV_CLI" ] || { echo "[FAIL] BFV CLI missing: $BFV_CLI (sbatch scripts/build_bfv_noise_cli.sbatch)"; exit 1; }
BFV_ARGS=(--seal-noise-bound-executable "$BFV_CLI"
          --seal-poly-modulus-degree 16384
          --seal-plain-modulus 786433
          --seal-coeff-modulus-bits 48,48,48,49,49,49,49,49,49)

JOB="${SLURM_JOB_ID:-local}"
OUT_DIR="$PROJ_ROOT/results/ablation_unified/${AGENT}_4pref/eval_$JOB"
mkdir -p "$OUT_DIR" "$PROJ_ROOT/logs"
BENCH_ORIG="$OUT_DIR/benchmarks_no_dnn.txt"
BENCH_THR="$PROJ_ROOT/RL/fhe_rl/datasets/threshold_benchmarks.txt"
python "$PROJ_ROOT/scripts/exp3_eval_helpers.py" build-benchmarks \
    --datasets "$PROJ_ROOT/RL/fhe_rl/datasets" --out "$BENCH_ORIG"
echo "$MODEL" > "$OUT_DIR/model.txt"

echo "════════════════════════════════════════════════════════════"
echo "  ABLATION EVAL (unified, 4 preferences):  $AGENT"
echo "  Model:       $MODEL"
echo "  Method:      $METHOD    budgets $BUDGETS (trained on $TRAIN_BUDGETS)"
echo "  Preferences: $PREFERENCES"
echo "  Sets:        original $(grep -c . "$BENCH_ORIG")  threshold $(grep -c . "$BENCH_THR")  x 4 preferences"
echo "  Output:      $OUT_DIR"
echo "════════════════════════════════════════════════════════════"

run_set() {  # $1 = set name, $2 = expressions file
    stdbuf -oL -eL python -u -m fhe_rl \
        --framework unified --embedder gnn \
        test --test_mode v2 \
        --model "$MODEL" \
        --pipeline joint \
        --dataset "$2" \
        --budgets "$BUDGETS" \
        --train_budgets "$TRAIN_BUDGETS" \
        --method "$METHOD" \
        --constraint "$CONSTRAINT" \
        --preferences "$PREFERENCES" \
        "${BFV_ARGS[@]}" \
        --output "$OUT_DIR/$1.xlsx" \
        > "$OUT_DIR/$1.log" 2>&1
}

STATUS_O=0; STATUS_T=0
run_set original  "$BENCH_ORIG" & PID_O=$!
run_set threshold "$BENCH_THR"  & PID_T=$!
wait $PID_O || STATUS_O=$?
echo "[original]  finished (exit $STATUS_O)"
wait $PID_T || STATUS_T=$?
echo "[threshold] finished (exit $STATUS_T)"

# ── summary: WITHOUT rollback (Agent*) vs WITH rollback (Safe*) ──────────────
python - "$OUT_DIR" "$AGENT" <<'PY' || echo "[warn] summary failed"
import sys, os
import pandas as pd
out_dir, agent = sys.argv[1], sys.argv[2]
rows = []
for name in ("original", "threshold"):
    path = os.path.join(out_dir, f"{name}.csv")
    if not os.path.exists(path):
        continue
    df = pd.read_csv(path)
    for col in ("Is Feasible", "Agent Violated", "Safe Violated"):
        df[col] = df[col].astype(str).str.lower().isin(["true", "1"])
    for budget, g in df.groupby("Budget"):
        for subset, s in (("all", g), ("within_budget", g[g["Is Feasible"]])):
            if s.empty:
                continue
            ops0 = s["Initial Ops"].where(s["Initial Ops"] > 0)
            rows.append({
                "agent": agent, "set": name, "budget": budget, "subset": subset,
                "rows (expr x pref)": len(s),
                "no_rollback CR%": round(s["Agent Cost Reduction (%)"].mean(), 2),
                "no_rollback exec red%": round((100 * (ops0 - s["Agent Final Ops"]) / ops0).mean(), 2),
                "no_rollback keys": round(s["Agent Final Keys"].mean(), 2),
                "no_rollback violations": int(s["Agent Violated"].sum()),
                "no_rollback viol rate%": round(100 * s["Agent Violated"].mean(), 1),
                "rollback CR%": round(s["Safe Cost Reduction (%)"].mean(), 2),
                "rollback exec red%": round((100 * (ops0 - s["Safe Final Ops"]) / ops0).mean(), 2),
                "rollback keys": round(s["Safe Final Keys"].mean(), 2),
                "rollback violations": int(s["Safe Violated"].sum()),
                "rollback viol rate%": round(100 * s["Safe Violated"].mean(), 1),
            })
summary = pd.DataFrame(rows)
summary.to_csv(os.path.join(out_dir, "summary.csv"), index=False)
with pd.option_context("display.width", 220, "display.max_columns", 30):
    print(summary.to_string(index=False))
PY

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  DONE   original: exit $STATUS_O   threshold: exit $STATUS_T"
echo "  Results: $OUT_DIR   (summary.csv)"
echo "════════════════════════════════════════════════════════════"
[ "$STATUS_O" -eq 0 ] && [ "$STATUS_T" -eq 0 ]

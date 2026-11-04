#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Constraint-method ablation on the UNIFIED agent — EVALUATION — V4 Noise Masking
#   trained by: scripts/ablation_unified/train_v4_nmask.sbatch
#
# WITHOUT and WITH safety rollback come from the SAME run: `fhe_rl test` (v2) logs,
# for every (expression, budget, preference):
#   Agent ...  = the agent's final expression        -> WITHOUT rollback (PFE Table 5.7)
#   Safe  ...  = best valid state of the trajectory  -> WITH rollback    (PFE Tables 5.8-5.10)
#
# Two benchmark sets, like the PFE (run in parallel):
#   original   = RL/fhe_rl/datasets/benchmarks.txt minus DNN (69 expressions)
#   threshold  = RL/fhe_rl/datasets/threshold_benchmarks.txt  (60, initial noise at 80-100% of a budget)
# Budgets 230,236,369,9000000 x the 10 training preferences.
# Rollback validity uses the BFV certificate (same as the Experiment 3 eval), identically for all 6 agents.
#
# Output (own folder per agent and per job, nothing overwritten):
#   results/ablation_unified/v4_nmask/eval_<jobid>/
#       original.xlsx/.csv  threshold.xlsx/.csv   (all rows: Agent* and Safe* columns)
#       summary.csv                                (per set x budget: no-rollback vs rollback)
#
# Usage (repo root):  sbatch scripts/ablation_unified/eval_v4_nmask.sbatch [model.zip]
#   after training:  sbatch --dependency=afterok:<train_jobid> scripts/ablation_unified/eval_v4_nmask.sbatch
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

#SBATCH -o logs/output.abl_eval_v4_nmask.%j.txt
#SBATCH -e logs/error.abl_eval_v4_nmask.%j.txt
#SBATCH -J abl-eval-v4-nmask

set -eo pipefail

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

# ── agent (must match how it was trained) ───────────────────────────────────
AGENT="v4_nmask"
METHOD="noise_masking"            # algo ppo, budget encoding embed: read from the model .zip
CONSTRAINT="noise"
BUDGETS="230,236,369,9000000"
TRAIN_BUDGETS="230,236,369,9000000"
# default: best eval checkpoint (same choice as the reference's *_best_4.0M.zip), else the final model
TRAINED="$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_abl_v4_nmask"
if [ -n "${1:-}" ]; then MODEL="$1"
elif [ -f "${TRAINED}_best.zip" ]; then MODEL="${TRAINED}_best.zip"
else MODEL="${TRAINED}.zip"; fi
[ -f "$MODEL" ] || { echo "[FAIL] model not found: $MODEL"; exit 1; }

# ── BFV rollback certificate (same parameters as CHEHAB's generated SEAL programs) ──
BFV_CLI="$PROJ_ROOT/build_bfv_noise/bfv_noise_bound_cli"
[ -x "$BFV_CLI" ] || { echo "[FAIL] BFV CLI missing: $BFV_CLI (sbatch scripts/build_bfv_noise_cli.sbatch)"; exit 1; }
BFV_ARGS=(--seal-noise-bound-executable "$BFV_CLI"
          --seal-poly-modulus-degree 16384
          --seal-plain-modulus 786433
          --seal-coeff-modulus-bits 48,48,48,49,49,49,49,49,49)

JOB="${SLURM_JOB_ID:-local}"
OUT_DIR="$PROJ_ROOT/results/ablation_unified/$AGENT/eval_$JOB"
mkdir -p "$OUT_DIR" "$PROJ_ROOT/logs"
BENCH_ORIG="$OUT_DIR/benchmarks_no_dnn.txt"
BENCH_THR="$PROJ_ROOT/RL/fhe_rl/datasets/threshold_benchmarks.txt"
python "$PROJ_ROOT/scripts/exp3_eval_helpers.py" build-benchmarks \
    --datasets "$PROJ_ROOT/RL/fhe_rl/datasets" --out "$BENCH_ORIG"
echo "$MODEL" > "$OUT_DIR/model.txt"

echo "════════════════════════════════════════════════════════════"
echo "  ABLATION EVAL (unified):  V4 Noise Masking"
echo "  Model:      $MODEL"
echo "  Method:     $METHOD    budgets $BUDGETS (trained on $TRAIN_BUDGETS)"
echo "  Sets:       original $(grep -c . "$BENCH_ORIG")  threshold $(grep -c . "$BENCH_THR")  x 10 preferences"
echo "  Output:     $OUT_DIR"
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
    df["Is Feasible"] = df["Is Feasible"].astype(str).str.lower().isin(["true", "1"])
    for col in ("Agent Violated", "Safe Violated"):
        df[col] = df[col].astype(str).str.lower().isin(["true", "1"])
    for budget, g in df.groupby("Budget"):
        for subset, s in (("all", g), ("within_budget", g[g["Is Feasible"]])):
            if s.empty:
                continue
            rows.append({
                "agent": agent, "set": name, "budget": budget, "subset": subset,
                "rows (expr x pref)": len(s),
                "no_rollback CR%": round(s["Agent Cost Reduction (%)"].mean(), 2),
                "no_rollback violations": int(s["Agent Violated"].sum()),
                "no_rollback viol rate%": round(100 * s["Agent Violated"].mean(), 1),
                "rollback CR%": round(s["Safe Cost Reduction (%)"].mean(), 2),
                "rollback violations": int(s["Safe Violated"].sum()),
                "rollback viol rate%": round(100 * s["Safe Violated"].mean(), 1),
            })
summary = pd.DataFrame(rows)
summary.to_csv(os.path.join(out_dir, "summary.csv"), index=False)
with pd.option_context("display.width", 200, "display.max_columns", 20):
    print(summary.to_string(index=False))
PY

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  DONE   original: exit $STATUS_O   threshold: exit $STATUS_T"
echo "  Results: $OUT_DIR   (summary.csv)"
echo "════════════════════════════════════════════════════════════"
[ "$STATUS_O" -eq 0 ] && [ "$STATUS_T" -eq 0 ]

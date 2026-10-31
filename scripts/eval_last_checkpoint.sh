#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Evaluate the LATEST training checkpoint of the uniform-preference unified agent,
# with both evaluations, in one command (run on the login node, repo root):
#
#   bash scripts/eval_last_checkpoint.sh                 # estimate-based eval only (hours)
#   bash scripts/eval_last_checkpoint.sh --seal          # + real SEAL execution sweep (build + 8 shards + report)
#   RUN=model_18983297_nato_sc_film_a_gnn bash scripts/eval_last_checkpoint.sh   # another training run
#
# 1. finds RL/checkpoints/$RUN/rl_model_<N>_steps.zip with the largest N (skips a zip still being written)
# 2. copies it to RL/fhe_rl/trained_models/unified_uniform_ckpt<N>.zip (frozen: training keeps writing)
# 3. estimate-based eval (scripts/eval_unified_uniform.sbatch): 69 non-DNN expressions x 4 budgets x 10 prefs
#      constrained metrics (test --v2 + BFV certificate) + MORL metrics (bisection: IC/HV/SP/EU)
#      -> RL/test_results/exp3_eval_ckpt<N>_<jobid>/summary_ckpt<N>.xlsx
# 4. --seal: real execution (47 C++ benchmarks x 4 budgets x 10 prefs + bisection, SEAL/BFV)
#      -> results/unified_morl_ckpt<N>/exp3_seal_summary.xlsx   (separate from the final-model results)
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p logs
sed -i 's/\r$//' scripts/*.sbatch scripts/*.sh 2>/dev/null || true

RUN="${RUN:-model_18983297_nato_sc_film_a_gnn}"
CKPT_DIR="RL/checkpoints/$RUN"
[ -d "$CKPT_DIR" ] || { echo "[FAIL] no checkpoint dir $CKPT_DIR"; exit 1; }

# newest complete checkpoint (largest step count whose zip opens)
CKPT=""; STEPS=""
for f in $(ls "$CKPT_DIR"/rl_model_*_steps.zip 2>/dev/null | sed -E 's/.*rl_model_([0-9]+)_steps\.zip/\1 &/' | sort -rn | awk '{print $2}'); do
    if python3 -c "import zipfile,sys; sys.exit(0 if zipfile.ZipFile(sys.argv[1]).testzip() is None else 1)" "$f" 2>/dev/null; then
        CKPT="$f"; STEPS="$(basename "$f" | sed -E 's/rl_model_([0-9]+)_steps\.zip/\1/')"; break
    fi
    echo "[skip] $f is incomplete (being written?)"
done
[ -n "$CKPT" ] || { echo "[FAIL] no readable checkpoint in $CKPT_DIR"; exit 1; }

TAG="ckpt${STEPS}"
MODEL="$PWD/RL/fhe_rl/trained_models/unified_uniform_${TAG}.zip"
cp "$CKPT" "$MODEL"
echo "Checkpoint: $CKPT  ($STEPS steps)  ->  $MODEL"

# estimate-based evaluation (constrained + MORL metrics)
EST_ID=$(sbatch --parsable -J "eval-$TAG" scripts/eval_unified_uniform.sbatch "$MODEL" "$TAG")
echo "estimate-based eval: job $EST_ID  -> RL/test_results/exp3_eval_${TAG}_${EST_ID}/"

if [ "${1:-}" = "--seal" ]; then
    export UNIFIED_UNIFORM_MODEL="$MODEL"
    export UNIFIED_MORL_OUT_DIR="$PWD/results/unified_morl_${TAG}"
    export E3_TAG="$TAG"
    DEP=""
    if [ -x build/benchmarks/dot_product/dot_product ] && [ "${REBUILD:-0}" != "1" ]; then
        echo "build/: already built (REBUILD=1 to force)"
    else
        BUILD_ID=$(sbatch --parsable scripts/build_chehab_benchmarks.sbatch)
        echo "build:  job $BUILD_ID"
        DEP="--dependency=afterok:$BUILD_ID"
    fi
    SWEEP_ID=$(sbatch --parsable $DEP -J "e3-seal-$TAG" scripts/eval_uniform_seal_sweep.sbatch)
    REPORT_ID=$(sbatch --parsable --dependency=afterany:$SWEEP_ID -J "e3-rep-$TAG" scripts/eval_uniform_seal_report.sbatch)
    echo "SEAL sweep: job $SWEEP_ID (8 shards)   report: job $REPORT_ID"
    echo "           -> $UNIFIED_MORL_OUT_DIR/exp3_seal_summary.xlsx"
fi
echo "Monitor: squeue -u ${USER:-$(whoami)}"

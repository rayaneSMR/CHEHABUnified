#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Submit the whole evaluation of the 4-preference ablation agents (run on the login node, repo root),
# once the 6 models are trained (train_<agent>_4pref.sbatch, incl. train_v5_lagpid_4pref.sbatch):
#
#   bash scripts/ablation_unified/launch_4pref_eval.sh            # estimate-based eval + SEAL sweeps
#   bash scripts/ablation_unified/launch_4pref_eval.sh --no-seal  # estimate-based eval only
#
# 1. eval_4pref.sbatch <agent> for the 6 agents (test --v2 at the 4 preferences, original + threshold)
#      -> results/ablation_unified/<agent>_4pref/eval_<jobid>/{original,threshold}.csv
# 2. build/ (build_chehab_benchmarks.sbatch) if it is not built yet
# 3. seal_sweep_4pref.sbatch twice (8 shards each): with and without rollback
#      -> results/ablation_unified/seal_4pref/{rollback,no_rollback}/raw/*.csv
# Then, on your machine (after copying results/ablation_unified/):
#   python experiments_reproduction/experiment_2/run_experiment_2.py
#   python experiments_reproduction/experiment_3/run_experiment_3.py
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
mkdir -p logs
sed -i 's/\r$//' scripts/*.sbatch scripts/*.sh scripts/ablation_unified/*.sbatch scripts/ablation_unified/*.sh 2>/dev/null || true

AGENTS="unconstrained v4_mb v4_nmask v4_mb_film v5_focops v5_lagpid"
MISSING=""
for a in $AGENTS; do
    m="RL/fhe_rl/trained_models/unified_noise_abl_${a}_4pref"
    [ -f "${m}_best.zip" ] || [ -f "${m}.zip" ] || MISSING="$MISSING $a"
done
if [ -n "$MISSING" ]; then
    echo "[FAIL] models not trained yet:$MISSING"
    echo "       sbatch scripts/ablation_unified/train_<agent>_4pref.sbatch   (then rerun this script)"
    exit 1
fi

for a in $AGENTS; do
    id=$(sbatch --parsable -J "abl4-eval-$a" scripts/ablation_unified/eval_4pref.sbatch "$a")
    echo "eval  $a: job $id  -> results/ablation_unified/${a}_4pref/eval_${id}/"
done

if [ "${1:-}" != "--no-seal" ]; then
    DEP=""
    if [ -x build/benchmarks/dot_product/dot_product ] && [ "${REBUILD:-0}" != "1" ]; then
        echo "build/: already built (REBUILD=1 to force)"
    else
        BUILD_ID=$(sbatch --parsable scripts/build_chehab_benchmarks.sbatch)
        echo "build: job $BUILD_ID"
        DEP="--dependency=afterok:$BUILD_ID"
    fi
    for rb in 1 0; do
        id=$(sbatch --parsable $DEP --export=ALL,ROLLBACK=$rb -J "abl4-seal-rb$rb" scripts/ablation_unified/seal_sweep_4pref.sbatch)
        echo "SEAL sweep ROLLBACK=$rb: job $id (8 shards)"
    done
    echo "      -> results/ablation_unified/seal_4pref/{rollback,no_rollback}/raw/"
fi
echo "Monitor: squeue -u ${USER:-$(whoami)}"

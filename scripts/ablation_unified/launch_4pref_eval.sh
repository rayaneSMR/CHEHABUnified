#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Submit the whole evaluation of the 4-preference ablation agents (run on the login node, repo root),
# once the 6 models are trained (train_<agent>_4pref.sbatch, incl. train_v5_lagpid_4pref.sbatch):
#
#   bash scripts/ablation_unified/launch_4pref_eval.sh            # estimate-based eval + real SEAL execution
#   bash scripts/ablation_unified/launch_4pref_eval.sh --no-seal  # estimate-based eval only
#
# 1. eval_4pref.sbatch <agent> for the 6 agents (test --v2 at the 4 preferences, original + threshold)
#      -> results/ablation_unified/<agent>_4pref/eval_<jobid>/{original,threshold}.csv
# 2. real compile + SEAL execution, the protocol of the unified agent (run_benchmarks_unified.py):
#    e2e_4pref.sh all 1 (with rollback, Experiment 3) and e2e_4pref.sh all 0 (raw output, Experiment 2)
#      -> results/ablation_unified/e2e_4pref/{rollback,no_rollback}/<agent>_4pref/e2e_*.csv
#    Needs build/ with the benchmarks (sbatch scripts/build_chehab_benchmarks.sbatch) and SEAL 4.1
#    (sbatch scripts/build_bfv_noise_cli.sbatch) before it is run.
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
    bash scripts/ablation_unified/e2e_4pref.sh all 1
    bash scripts/ablation_unified/e2e_4pref.sh all 0
fi
echo "Monitor: squeue -u ${USER:-$(whoami)}"

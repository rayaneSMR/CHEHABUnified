#!/bin/bash
# Submit the unified joint agent evaluation: one Slurm job per dataset x budget,
# all running in parallel. Run from the root of the evaluation clone:
#
#   bash scripts/launch_unified_eval.sh MODEL [PREFERENCES]
#     MODEL        trained joint model .zip (absolute path, e.g. a copy of best_model.zip)
#     PREFERENCES  optional, "w_ops,w_keys;..." (default: the 10 training preferences)
#
# Datasets: the RL-level evaluation sets of the original MORL and constrained frameworks
#   benchmarks.txt            69 CHEHAB kernels (box_blur, dot_product, ... at slot counts 3-32,
#                             plus the polynomial trees). MORL (test default, run_ops_exp) and
#                             constrained (test_all_original), budgets 230,236,369,9000000.
#   dnn_benchmarks.txt         4 DNN kernels. Constrained (test_rl_dnn_benchmarks),
#                             budgets 230,236,369,9000000.
#   threshold_benchmarks.txt  60 expressions with noise at 80-100% of each budget. Constrained
#                             (test_all_threshold), budgets 230,236,369 only. Generated with
#                             the constrained script and its fixed seed (7777), so it is the
#                             same set they used.
#   dnn_benchmarks_scaled.txt 12 scaled DNN layers (conv, fc, poly activations), from the
#                             earlier unified evaluation, budgets 230,236,369,9000000.
#
# Afterwards, merge the per-budget files of each dataset:
#   python scripts/merge_eval_results.py RL/test_results

set -eo pipefail

MODEL="${1:?usage: bash scripts/launch_unified_eval.sh MODEL [PREFERENCES]}"
PREFERENCES="${2:-}"

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_ROOT"
mkdir -p logs

if [ ! -f "$MODEL" ]; then
    echo "ERROR: model not found: $MODEL"
    exit 1
fi
MODEL="$(cd "$(dirname "$MODEL")" && pwd)/$(basename "$MODEL")"

# dataset -> budgets it was tested on in the original frameworks
declare -A BUDGETS=(
    [benchmarks.txt]="230 236 369 9000000"
    [dnn_benchmarks.txt]="230 236 369 9000000"
    [threshold_benchmarks.txt]="230 236 369"
    [dnn_benchmarks_scaled.txt]="230 236 369 9000000"
)
DATASETS=(benchmarks.txt dnn_benchmarks.txt threshold_benchmarks.txt dnn_benchmarks_scaled.txt)

# Threshold set: regenerate with the constrained script (fixed seed -> identical set)
if [ ! -f RL/fhe_rl/datasets/threshold_benchmarks.txt ]; then
    echo "Generating threshold_benchmarks.txt (constrained script, seed 7777) ..."
    (cd RL && PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}" \
        python ../scripts/generate_threshold_benchmarks.py > /dev/null)
fi

echo "Model:       $MODEL"
echo "Preferences: ${PREFERENCES:-10 training preferences}"
echo "Folder:      $PROJ_ROOT"
echo ""
for ds in "${DATASETS[@]}"; do
    for b in ${BUDGETS[$ds]}; do
        jid=$(sbatch --parsable -J "ev-${ds%.txt}-${b}" scripts/eval_unified_sweep.sbatch "$ds" "$b" "$MODEL" "$PREFERENCES")
        echo "  submitted $jid   $ds   budget=$b"
    done
done
echo ""
echo "Check:   squeue -u \$USER"
echo "Logs:    logs/output.eval_sweep.<jobid>.txt"
echo "Results: RL/test_results/eval_<dataset>_b<budget>_<jobid>.xlsx"

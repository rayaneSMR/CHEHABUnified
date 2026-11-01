#!/bin/bash
# Submit the real compile + SEAL execution evaluation of the unified joint agent:
# one Slurm job per budget x benchmark (each in its own work folder), all in parallel.
# Run from the root of the evaluation clone, after `bash scripts/build_e2e_benchmarks.sh`:
#
#   bash scripts/launch_unified_e2e.sh MODEL [BUDGETS] [PREFERENCES]
#     MODEL        trained joint model .zip (absolute path)
#     BUDGETS      optional, space-separated (default: "230 236 369 9000000")
#     PREFERENCES  optional "w_ops,w_keys;..." (default: the 10 training preferences)
#
# Benchmarks: the ones reported by the original MORL evaluation (run_benchmarks.py /
# results/generate_graphs.py), see SUITE in scripts/run_benchmarks_unified.py.
# Afterwards: python scripts/merge_eval_results.py RL/test_results

set -eo pipefail
MODEL="${1:?usage: bash scripts/launch_unified_e2e.sh MODEL [BUDGETS] [PREFERENCES]}"
BUDGETS="${2:-230 236 369 9000000}"
PREFERENCES="${3:-}"

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_ROOT"
mkdir -p logs
[ -f "$MODEL" ] || { echo "ERROR: model not found: $MODEL"; exit 1; }
MODEL="$(cd "$(dirname "$MODEL")" && pwd)/$(basename "$MODEL")"
[ -x build/benchmarks/dot_product/dot_product ] || { echo "ERROR: run 'bash scripts/build_e2e_benchmarks.sh' first"; exit 1; }

# Quick run: dot_product only. Uncomment the other benchmarks for the full suite.
BENCHES=(
    dot_product
    # box_blur gx_kernel gy_kernel roberts_cross matrix_mul
    # hamming_dist l2_distance lin_reg poly_reg max sort polynomials_coyote
)

echo "Model:   $MODEL"
echo "Budgets: $BUDGETS"
echo ""
for b in $BUDGETS; do
    for bench in "${BENCHES[@]}"; do
        jid=$(sbatch --parsable -J "e2e-${bench}-${b}" scripts/eval_unified_e2e.sbatch "$b" "$MODEL" "$bench" "$PREFERENCES")
        echo "  submitted $jid   $bench   budget=$b"
    done
done
echo ""
echo "Check:   squeue -u \$USER"
echo "Logs:    logs/output.e2e.<jobid>.txt"
echo "Results: RL/test_results/e2e_<benchmark>_b<budget>_<jobid>.csv"

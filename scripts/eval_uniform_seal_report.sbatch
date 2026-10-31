#!/bin/bash
# Experiment 3, real execution: metrics after the sweep.
#   MORL metrics  (unified_morl_experiments.py metrics): per benchmark x budget, Pareto front of
#                 (circuit execution time, rotation-key size) normalised per benchmark -> IC, HV, SP, EU
#   constrained   (exp3_eval_helpers.py summarize-seal): measured compliance, remaining noise budget,
#                 used bits, times, key size, depth, op counts, rollback ... per budget and budget x preference
# Output: $UNIFIED_MORL_OUT_DIR (default results/unified_morl)/metrics.csv and exp3_seal_summary.xlsx

#SBATCH -p compute
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem 8GB
#SBATCH -t 01:00:00
#SBATCH -J e3-seal-report
#SBATCH -o logs/e3_seal_report.%j.out
#SBATCH -e logs/e3_seal_report.%j.err

set -eo pipefail
source "${SLURM_SUBMIT_DIR:-/scratch/$USER/chehab-unified}/scripts/exp3_seal_env.sh"
cd "$PROJ_ROOT"

OUT="${UNIFIED_MORL_OUT_DIR:-$PROJ_ROOT/results/unified_morl}"
python -u scripts/unified_morl_experiments.py metrics --time-col circuit_execution_time_s
python -u scripts/exp3_eval_helpers.py summarize-seal \
    --raw-dir "$OUT/raw" --metrics "$OUT/metrics.csv" \
    --agent uniform --out "$OUT/exp3_seal_summary.xlsx"

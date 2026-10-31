#!/bin/bash
# Chain the Experiment 3 real-execution evaluation:  build -> 8-shard sweep -> metrics/summary.
# Usage (repo root, login node):
#   bash scripts/launch_eval_uniform_seal.sh                     # start now
#   bash scripts/launch_eval_uniform_seal.sh <train_jobid>       # start after training finishes OK
#   SKIP_BUILD=1 bash scripts/launch_eval_uniform_seal.sh        # build/ already done
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p logs
sed -i 's/\r$//' scripts/exp3_seal_env.sh scripts/*seal*.sbatch scripts/build_chehab_benchmarks.sbatch

DEP=""
[ -n "${1:-}" ] && DEP="--dependency=afterok:$1"

if [ "${SKIP_BUILD:-0}" = "1" ]; then
    BUILD_ID=""
    echo "build:  skipped"
else
    BUILD_ID=$(sbatch --parsable $DEP scripts/build_chehab_benchmarks.sbatch)
    echo "build:  $BUILD_ID ${DEP:+($DEP)}"
    DEP="--dependency=afterok:$BUILD_ID"
fi
SWEEP_ID=$(sbatch --parsable $DEP scripts/eval_uniform_seal_sweep.sbatch)
echo "sweep:  $SWEEP_ID (8 array tasks) ${DEP:+($DEP)}"
REPORT_ID=$(sbatch --parsable --dependency=afterany:$SWEEP_ID scripts/eval_uniform_seal_report.sbatch)
echo "report: $REPORT_ID (after the sweep)"
echo "Monitor: squeue -u $USER ; tail -f logs/e3_seal_sweep.${SWEEP_ID}_0.out"

#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Constraint-method ablation, 4-preference agents — REAL EXECUTION on SEAL/BFV
#   (same measurement as Experiment 3: scripts/eval_uniform_seal_sweep.sbatch)
#
# Every one of the 6 agents (unconstrained v4_mb v4_nmask v4_mb_film v5_focops v5_lagpid)
# compiles every non-DNN C++ benchmark (47 instances) for every noise budget {230,236,369,9e6}
# and its 4 training preferences w_ops = 1.0, 0.9, 0.8, 0.6; the generated SEAL program is then
# built and executed. One CSV row per point: op counts, depth, compile time, circuit / keygen /
# total execution time, rotation-key size (MB), remaining noise budget (measured), estimated
# noise, rollback used, violation (estimated and measured).
#   = scripts/unified_morl_experiments.py sweep --experiments ABL4 (shard per array task)
#
# Run it twice (they are independent and can run at the same time):
#   ROLLBACK=1  safety rollback on   -> Experiment 3   results/ablation_unified/seal_4pref/rollback/raw/
#   ROLLBACK=0  raw agent output     -> Experiment 2   results/ablation_unified/seal_4pref/no_rollback/raw/
#   sbatch --export=ALL,ROLLBACK=1 scripts/ablation_unified/seal_sweep_4pref.sbatch
#   sbatch --export=ALL,ROLLBACK=0 scripts/ablation_unified/seal_sweep_4pref.sbatch
# Resumable: resubmitting skips the points already in the CSVs.
# Needs: build/ with the benchmarks (sbatch scripts/build_chehab_benchmarks.sbatch) and SEAL 4.1
#        (sbatch scripts/build_bfv_noise_cli.sbatch), the 6 models
#        RL/fhe_rl/trained_models/unified_noise_abl_<agent>_4pref[_best].zip
# Optional: AGENTS=abl4_v5_lagpid,abl4_unconstrained (subset), REPEATS=2 (median of 2 executions)
# ════════════════════════════════════════════════════════════════════════════

#SBATCH -p compute
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem 16GB
#SBATCH -t 3-00:00:00
#SBATCH --array=0-7
#SBATCH -J abl4-seal-sweep
#SBATCH -o logs/abl4_seal_sweep.%A_%a.out
#SBATCH -e logs/abl4_seal_sweep.%A_%a.err

set -eo pipefail
source "${SLURM_SUBMIT_DIR:-/scratch/$USER/chehab-unified}/scripts/exp3_seal_env.sh"
cd "$PROJ_ROOT"

SHARDS=8
SHARD="${SLURM_ARRAY_TASK_ID:-0}"
REPEATS="${REPEATS:-1}"
ROLLBACK="${ROLLBACK:-1}"
case "$ROLLBACK" in
    1) MODE="rollback" ;;
    0) MODE="no_rollback" ;;
    *) echo "[FAIL] ROLLBACK must be 1 or 0, got '$ROLLBACK'"; exit 1 ;;
esac
export CHEHAB_RL_ROLLBACK="$ROLLBACK"           # read by RL/fhe_rl/run_unified.py
export UNIFIED_MORL_OUT_DIR="$PROJ_ROOT/results/ablation_unified/seal_4pref/$MODE"
AGENT_ARGS=()
[ -n "${AGENTS:-}" ] && AGENT_ARGS=(--agents "$AGENTS")

# all 6 models must exist (best eval checkpoint preferred, same choice as eval_4pref.sbatch)
for a in unconstrained v4_mb v4_nmask v4_mb_film v5_focops v5_lagpid; do
    [[ -n "${AGENTS:-}" && ",$AGENTS," != *",abl4_$a,"* ]] && continue
    m="$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_abl_${a}_4pref"
    [ -f "${m}_best.zip" ] || [ -f "${m}.zip" ] || { echo "[FAIL] model missing: ${m}[_best].zip"; exit 1; }
done
[ -x build/benchmarks/dot_product/dot_product ] || {
    echo "[FAIL] build/ not ready (sbatch scripts/build_chehab_benchmarks.sbatch)"; exit 1; }

echo "Mode: $MODE (CHEHAB_RL_ROLLBACK=$ROLLBACK)   shard $SHARD/$SHARDS   repeats $REPEATS"
echo "Results: $UNIFIED_MORL_OUT_DIR/raw/"

# each shard and mode needs its own build dir: benchmarks write ../expression.txt next to themselves
BUILD="build_shard${SHARD}_abl4_${MODE}"
[ -d "$BUILD" ] || cp -r build "$BUILD"

python -u scripts/unified_morl_experiments.py sweep \
    --experiments ABL4 ${AGENT_ARGS[@]+"${AGENT_ARGS[@]}"} \
    --build-dir "$BUILD" --shard "$SHARD" --num-shards "$SHARDS" --repeats "$REPEATS"

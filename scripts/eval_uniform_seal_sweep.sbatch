#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Experiment 3, real execution: the unified (uniform-preference) agent compiles every
# non-DNN C++ benchmark for every noise budget {230,236,369,9e6} and every preference
# w_ops = 1.0..0.1 (+ bisection on key-count gaps), then the SEAL/BFV program is built
# and executed. One CSV row per point: op counts, depth, compile time, circuit / keygen /
# total time, rotation-key size, remaining noise budget (measured), estimated noise,
# rollback used, violation (estimated and measured).
#   = scripts/unified_morl_experiments.py sweep --experiments E3 (shard per array task)
# 47 instances: dot_product, l2_distance, hamming_dist, lin_reg, poly_reg, matrix_mul,
# box_blur, gx_kernel, gy_kernel, roberts_cross (4/8/16/32), max 3/4/5, sort 3, 3 poly trees.
# Results: results/unified_morl/raw/uniform.shard<N>.csv  (resumable: rerun skips done points)
# ════════════════════════════════════════════════════════════════════════════

#SBATCH -p compute
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem 16GB
#SBATCH -t 3-00:00:00
#SBATCH --array=0-7
#SBATCH -J e3-seal-sweep
#SBATCH -o logs/e3_seal_sweep.%A_%a.out
#SBATCH -e logs/e3_seal_sweep.%A_%a.err

set -eo pipefail
source "${SLURM_SUBMIT_DIR:-/scratch/$USER/chehab-unified}/scripts/exp3_seal_env.sh"
cd "$PROJ_ROOT"

SHARDS=8
SHARD="${SLURM_ARRAY_TASK_ID:-0}"
REPEATS="${REPEATS:-1}"          # SEAL executions per point (median); 2 to match run_benchmarks*.py
MODEL="$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_uniform.zip"
[ -f "$MODEL" ] || { echo "[FAIL] model not found: $MODEL"; exit 1; }

# each shard needs its own build dir: benchmarks write ../expression.txt next to themselves
BUILD="build_shard${SHARD}"
[ -d "$BUILD" ] || cp -r build "$BUILD"

python -u scripts/unified_morl_experiments.py sweep \
    --experiments E3 --agents uniform \
    --build-dir "$BUILD" --shard "$SHARD" --num-shards "$SHARDS" --repeats "$REPEATS"

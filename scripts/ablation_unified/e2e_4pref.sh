#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# 4-preference ablation agents — REAL compile + SEAL execution (measured exec time, rotation-key size)
#
# Same protocol as the evaluation of the unified agent of train_unified_noise.sbatch
# (scripts/launch_unified_e2e.sh -> eval_unified_e2e.sbatch -> run_benchmarks_unified.py):
#   every C++ benchmark of the MORL suite (box_blur, gx/gy_kernel, roberts_cross, matrix_mul at 3,4,5;
#   dot_product, hamming_dist, l2_distance, lin_reg, poly_reg at 4,8,16,32; max 3,4,5; sort 3,4;
#   6 polynomial trees) is compiled by CHEHAB with the agent, the generated SEAL program is built
#   and run 3 times (first = warm-up, median of the others), the decrypted outputs are checked.
#   Measured: circuit_execution_time (s), rotation_keys_size (MB) (= GaloisKeys::save_size),
#   Remaining_noise_budget, keygen / total time, peak RAM, op counts, depth, + the RL-side numbers.
# Here: the agents' 4 training preferences, their constraint method, with or without rollback.
#
#   bash scripts/ablation_unified/e2e_4pref.sh <agent|all> [ROLLBACK] [BUDGETS]
#     agent     unconstrained v4_mb v4_nmask v4_mb_film v5_focops v5_lagpid, or all
#     ROLLBACK  1 (default) = safety rollback (Experiment 3), 0 = raw agent output (Experiment 2)
#     BUDGETS   default "230 236 369 9000000"
#   e.g. both modes for every agent:
#     bash scripts/ablation_unified/e2e_4pref.sh all 1 && bash scripts/ablation_unified/e2e_4pref.sh all 0
#
# One Slurm job per budget x benchmark (13 benchmarks x 4 budgets = 52 jobs per agent and mode).
# Output: results/ablation_unified/e2e_4pref/<rollback|no_rollback>/<agent>_4pref/e2e_<bench>_b<budget>_<job>.csv
# Needs: build/ with all benchmarks (sbatch scripts/build_chehab_benchmarks.sbatch) and SEAL 4.1
#        (sbatch scripts/build_bfv_noise_cli.sbatch); the trained model
#        RL/fhe_rl/trained_models/unified_noise_abl_<agent>_4pref[_best].zip
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
PROJ_ROOT="$PWD"
mkdir -p logs

AGENT="${1:?usage: bash scripts/ablation_unified/e2e_4pref.sh <agent|all> [ROLLBACK] [BUDGETS]}"
ROLLBACK="${2:-1}"
BUDGETS="${3:-230 236 369 9000000}"
PREFERENCES="1.0,0.0;0.9,0.1;0.8,0.2;0.6,0.4"
CONDA_ENV="${CONDA_ENV:-/home/rs10728/.conda/envs/fhe_rl}"   # same env as the training / eval scripts
BENCHES=(box_blur gx_kernel gy_kernel roberts_cross matrix_mul dot_product hamming_dist
         l2_distance lin_reg poly_reg max sort polynomials_coyote)
case "$ROLLBACK" in 1) MODE=rollback ;; 0) MODE=no_rollback ;; *) echo "[FAIL] ROLLBACK must be 1 or 0"; exit 1 ;; esac

method_of() {
    case "$1" in
        unconstrained) echo none ;;
        v4_mb|v4_mb_film) echo margin_barrier ;;
        v4_nmask) echo noise_masking ;;
        v5_focops|v5_lagpid) echo nato_sc ;;
        *) return 1 ;;
    esac
}

if [ "$AGENT" = "all" ]; then
    AGENTS="unconstrained v4_mb v4_nmask v4_mb_film v5_focops v5_lagpid"
else
    method_of "$AGENT" > /dev/null || { echo "[FAIL] unknown agent '$AGENT'"; exit 1; }
    AGENTS="$AGENT"
fi

for b in "${BENCHES[@]}"; do
    [ -x "build/benchmarks/$b/$b" ] || { echo "[FAIL] build/benchmarks/$b/$b missing (sbatch scripts/build_chehab_benchmarks.sbatch)"; exit 1; }
done

for a in $AGENTS; do
    TRAINED="$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_abl_${a}_4pref"
    if [ -f "${TRAINED}_best.zip" ]; then MODEL="${TRAINED}_best.zip"
    elif [ -f "${TRAINED}.zip" ]; then MODEL="${TRAINED}.zip"
    else echo "[skip] $a: model not trained yet (${TRAINED}[_best].zip)"; continue; fi
    METHOD="$(method_of "$a")"
    OUT_DIR="results/ablation_unified/e2e_4pref/$MODE/${a}_4pref"
    mkdir -p "$OUT_DIR"
    echo "$MODEL" > "$OUT_DIR/model.txt"
    echo "== $a  method=$METHOD  mode=$MODE  model=$(basename "$MODEL")  -> $OUT_DIR/"
    for budget in $BUDGETS; do
        for bench in "${BENCHES[@]}"; do
            jid=$(sbatch --parsable -J "e2e4-${a}-${MODE}-${bench}-${budget}" \
                --export=ALL,METHOD="$METHOD",ROLLBACK="$ROLLBACK",OUT_DIR="$OUT_DIR",CONDA_ENV="$CONDA_ENV" \
                scripts/eval_unified_e2e.sbatch "$budget" "$MODEL" "$bench" "$PREFERENCES")
            echo "   $jid  $bench  B=$budget"
        done
    done
done
echo "Monitor: squeue -u \$USER    logs: logs/output.e2e.<jobid>.txt"

#!/bin/bash
# Real compile + SEAL execution of the near-threshold dataset (60 programs of
# RL/fhe_rl/datasets/threshold_benchmarks.txt: lines 1-20 for B = 230, 21-40 for B = 236,
# 41-60 for B = 369), to measure the circuit execution time of the programs of the
# near-threshold table. Same protocol as the end-to-end evaluation of the 46 benchmarks
# (scripts/run_benchmarks_unified.py); the program is compiled by benchmarks/threshold_expr
# and the agent gets the dataset expression itself.
#
# Run from the root of the evaluation clone, after `bash scripts/build_e2e_benchmarks.sh`:
#   bash scripts/launch_threshold_e2e.sh MODEL [PREFERENCE]
#     MODEL       trained joint model .zip (absolute path), e.g.
#                 RL/fhe_rl/trained_models/unified_joint_noise_19038296_best_4.6M.zip
#     PREFERENCE  optional "w_ops,w_keys" (default 0.9,0.1)
#
# 9 jobs, 3 per group of 20 programs:
#   cmorl          agent at the program's budget B, rollback at B          (as threshold_w0.9_2026-11-08)
#   unconstrained  agent at B = 9000000, no rollback: its final program    (agent columns of the table)
#   input          no agent: the input program (baseline of the reductions)
# The SEAL bound still applies to every compiled program (the input is compiled if it fails).
# Afterwards: python scripts/threshold_e2e_summary.py <OUT_DIR>

set -eo pipefail
MODEL="${1:?usage: bash scripts/launch_threshold_e2e.sh MODEL [PREFERENCE]}"
PREF="${2:-0.9,0.1}"

PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_ROOT"
mkdir -p logs
[ -f "$MODEL" ] || { echo "ERROR: model not found: $MODEL"; exit 1; }
MODEL="$(cd "$(dirname "$MODEL")" && pwd)/$(basename "$MODEL")"
[ -x build/benchmarks/threshold_expr/threshold_expr ] || { echo "ERROR: run 'bash scripts/build_e2e_benchmarks.sh' first"; exit 1; }

OUT_ROOT="${OUT_ROOT:-RL/test_results/threshold_e2e_$(date +%Y-%m-%d)}"
mkdir -p "$OUT_ROOT"/{cmorl,unconstrained,input}

declare -A LINES_OF=([230]="1-20" [236]="21-40" [369]="41-60")
for B in 230 236 369; do
    L="${LINES_OF[$B]}"
    jid=$(sbatch --parsable -J "thr-cmorl-$B" \
        --export=ALL,LINES="$L",METHOD=nato_sc,ROLLBACK=1,OUT_DIR="$OUT_ROOT/cmorl" \
        scripts/eval_unified_e2e.sbatch "$B" "$MODEL" threshold "$PREF")
    echo "  submitted $jid   cmorl          lines $L   B=$B"
    jid=$(sbatch --parsable -J "thr-unc-$B" \
        --export=ALL,LINES="$L",METHOD=nato_sc,ROLLBACK=0,OUT_DIR="$OUT_ROOT/unconstrained" \
        scripts/eval_unified_e2e.sbatch 9000000 "$MODEL" threshold "$PREF")
    echo "  submitted $jid   unconstrained  lines $L   (agent budget 9000000, no rollback)"
    jid=$(sbatch --parsable -J "thr-input-$B" \
        --export=ALL,LINES="$L",PASSTHROUGH=1,OUT_DIR="$OUT_ROOT/input" \
        scripts/eval_unified_e2e.sbatch "$B" "$MODEL" threshold "$PREF")
    echo "  submitted $jid   input          lines $L"
done
echo ""
echo "Check:   squeue -u \$USER"
echo "Logs:    logs/output.e2e.<jobid>.txt"
echo "Results: $OUT_ROOT/{cmorl,unconstrained,input}/e2e_threshold_L*_<jobid>.csv"
echo "Summary: python scripts/threshold_e2e_summary.py $OUT_ROOT"

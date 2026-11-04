#!/bin/bash
# ════════════════════════════════════════════════════════════════════════════
# Constraint-method ablation on the UNIFIED agent  —  V4 Noise Masking
#   (unified version of the PFE ablation, Tables 5.7 / 5.10: "V4 Noise Masking")
#
# PPO + masking of actions that push noise over the budget, embedded budget
# (PFE: train_v4_nmask_B.sbatch). Slow: the noise estimator runs on every candidate action.
#
# Every setting is IDENTICAL to train_unified_noise.sbatch (the reference agent,
# V5 Lag-PID + NATO-SC) except:  --method noise_masking  --algo ppo  --budget_encoding embed
#
# Everything this agent produces has its own folder (nothing is shared or overwritten):
#   run name      model_<jobid>_noise_masking_film_a_gnn_abl_v4_nmask   (--run_tag abl_v4_nmask)
#   checkpoints   RL/checkpoints/<run name>/      tensorboard  RL/tensorboard/<run name>/
#   best model    RL/eval/best_model_<run name>/
#   train log     results/ablation_unified/v4_nmask/train_<jobid>.log
#   final model   RL/fhe_rl/trained_models/unified_noise_abl_v4_nmask.zip  (+ _best.zip)
#
# Submit from the repo root:  sbatch scripts/ablation_unified/train_v4_nmask.sbatch
# Then evaluate:              sbatch scripts/ablation_unified/eval_v4_nmask.sbatch
# ════════════════════════════════════════════════════════════════════════════

#SBATCH -p compute
#SBATCH --mem 64GB
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 33
#SBATCH -t 7-00:00:00

#SBATCH --mail-user=rs10728@nyu.edu
#SBATCH --mail-type=BEGIN,END,FAIL

#SBATCH -o logs/output.abl_train_v4_nmask.%j.txt
#SBATCH -e logs/error.abl_train_v4_nmask.%j.txt
#SBATCH -J abl-train-v4-nmask

# Pre-timeout checkpointing signal 5 minutes before kill (train.py saves rl_model_emergency.zip)
#SBATCH --signal=B:TERM@300

set +u
CONDA_BASE="${CONDA_BASE:-/share/apps/NYUAD5/miniconda/3-4.11.0}"
CONDA_ENV="${CONDA_ENV:-/home/rs10728/.conda/envs/fhe_rl}"
source "$CONDA_BASE/bin/activate" || { echo "[FAIL] cannot source $CONDA_BASE/bin/activate"; exit 1; }
conda activate "$CONDA_ENV" || { echo "[FAIL] cannot activate conda env $CONDA_ENV"; exit 1; }
echo "Python: $(which python)"
set -u

export PYTHONUNBUFFERED=1

if [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/RL" ]; then
    PROJ_ROOT="$SLURM_SUBMIT_DIR"
else
    PROJ_ROOT="/scratch/${USER}/chehab-unified"
fi

AGENT_DIR="$PROJ_ROOT/results/ablation_unified/v4_nmask"
mkdir -p "$PROJ_ROOT/logs" "$AGENT_DIR" "$PROJ_ROOT/RL/eval" "$PROJ_ROOT/RL/checkpoints" "$PROJ_ROOT/RL/fhe_rl/trained_models"

cd "$PROJ_ROOT/RL"
export PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}"

# ── Ablation variables (the ONLY differences from train_unified_noise.sbatch) ──
METHOD="noise_masking"
ALGO="ppo"
ENCODING="embed"

# ── Shared settings: IDENTICAL to train_unified_noise.sbatch ─────────────────
CONSTRAINT="noise"
BUDGETS="230,236,369,9000000"
VARIANT="film_a"
DATASET="./fhe_rl/datasets/final_llm_dataset.txt"
TIMESTEPS=5000000
EVAL_FREQ=200000   # one eval (69 benchmarks x 10 prefs) takes ~52 min: 25 evals over 5M steps
NUM_ENVS=32
# Keep 16384 samples per PPO update (same as the old 8 envs x 2048 steps)
ROLLOUT_SIZE=16384
N_STEPS=$((ROLLOUT_SIZE / NUM_ENVS))

JOB="${SLURM_JOB_ID:-jobid}"     # same fallback as train.py
RUN_TAG="abl_v4_nmask"
RUN_NAME="model_${JOB}_${METHOD}_${VARIANT}_gnn_${RUN_TAG}"
FINAL_MODEL="$PROJ_ROOT/RL/fhe_rl/trained_models/unified_noise_${RUN_TAG}.zip"
TRAIN_LOG="$AGENT_DIR/train_${JOB}.log"

echo "════════════════════════════════════════════"
echo "  ABLATION (unified):  V4 Noise Masking"
echo "  Method / Algo:       $METHOD / $ALGO"
echo "  Budget encoding:     $ENCODING   (policy variant $VARIANT, gnn)"
echo "  Constraint:          $CONSTRAINT  budgets=$BUDGETS"
echo "  Preferences:         10 vectors, n_cycle=1 (default, same as reference)"
echo "  Timesteps:           $TIMESTEPS  (eval every $EVAL_FREQ)"
echo "  Rollout:             $N_STEPS steps/env x $NUM_ENVS envs = $((N_STEPS * NUM_ENVS))"
echo "  Job ID:              $JOB"
echo "  Run name:            $RUN_NAME"
echo "  Agent folder:        $AGENT_DIR"
echo "  Final model:         $FINAL_MODEL"
echo "════════════════════════════════════════════"

# ── Train ────────────────────────────────────────────────────────────────────
stdbuf -oL -eL python -u -m fhe_rl \
    --framework unified train \
    --dataset "$DATASET" \
    --constraint "$CONSTRAINT" \
    --budgets "$BUDGETS" \
    --timesteps $TIMESTEPS \
    --eval_freq $EVAL_FREQ \
    --num_envs $NUM_ENVS \
    --n_steps $N_STEPS \
    --method "$METHOD" \
    --algo "$ALGO" \
    --budget_encoding "$ENCODING" \
    --policy_variant "$VARIANT" \
    --embedder gnn \
    --run_tag "$RUN_TAG" \
    --fresh_start \
    "$@" \
    > "$TRAIN_LOG" 2>&1

# ── Publish the model under the ablation name ───────────────────────────────
if [ -f "$PROJ_ROOT/RL/${RUN_NAME}.zip" ]; then
    cp "$PROJ_ROOT/RL/${RUN_NAME}.zip" "$FINAL_MODEL"
    echo "[done] final model     -> $FINAL_MODEL"
else
    echo "[warn] ${RUN_NAME}.zip not found (training did not finish?). Latest checkpoints: $PROJ_ROOT/RL/checkpoints/${RUN_NAME}/"
fi
BEST="$PROJ_ROOT/RL/eval/best_model_${RUN_NAME}/best_model.zip"
if [ -f "$BEST" ]; then
    cp "$BEST" "${FINAL_MODEL%.zip}_best.zip"
    echo "[done] best eval model -> ${FINAL_MODEL%.zip}_best.zip"
fi
echo "$RUN_NAME" > "$AGENT_DIR/run_name.txt"
echo "TensorBoard: $PROJ_ROOT/RL/tensorboard/${RUN_NAME}"

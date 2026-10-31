#!/bin/bash
# Shared environment for the Experiment 3 real-execution (SEAL) evaluation jobs.
# Sourced by build_chehab_benchmarks.sbatch, eval_uniform_seal_sweep.sbatch, eval_uniform_seal_report.sbatch.

# Compiler + CMake from modules, BEFORE conda (the conda compiler wrapper is broken: "cannot execute cc1plus")
module load gcc 2>/dev/null || true
module load cmake 2>/dev/null || true
SYSTEM_GXX="$(which g++ 2>/dev/null || echo /usr/bin/g++)"
SYSTEM_GCC="$(which gcc 2>/dev/null || echo /usr/bin/gcc)"

CONDA_BASE="${CONDA_BASE:-/share/apps/NYUAD5/miniconda/3-4.11.0}"
CONDA_ENV="${CONDA_ENV:-/home/${USER}/.conda/envs/fhe_rl}"
set +u
source "$CONDA_BASE/bin/activate" || { echo "[FAIL] cannot source $CONDA_BASE/bin/activate"; exit 1; }
conda activate "$CONDA_ENV" || { echo "[FAIL] cannot activate conda env $CONDA_ENV"; exit 1; }
set -u
unset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS DEBUG_CFLAGS DEBUG_CXXFLAGS
export CC="$SYSTEM_GCC" CXX="$SYSTEM_GXX"

# The C++ compiler calls `$PYTHON -m fhe_rl ... run` (falls back to /usr/bin/python3 otherwise!)
export PYTHON="$CONDA_ENV/bin/python"
export PYTHONUNBUFFERED=1

# SEAL 4.1 built by build_bfv_noise_cli.sbatch; every generated he/ project does find_package(SEAL)
SEAL_PREFIX="${SEAL_PREFIX:-/scratch/${USER}/opt/SEAL-4.1}"
SEAL_CONFIG="$(find "$SEAL_PREFIX" -name SEALConfig.cmake 2>/dev/null | head -n 1 || true)"
[ -n "$SEAL_CONFIG" ] || { echo "[FAIL] SEAL not found under $SEAL_PREFIX (run sbatch scripts/build_bfv_noise_cli.sbatch)"; exit 1; }
export SEAL_DIR="$(dirname "$SEAL_CONFIG")"
export CMAKE_PREFIX_PATH="$SEAL_PREFIX${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"

if [ -n "${SLURM_SUBMIT_DIR:-}" ] && [ -d "${SLURM_SUBMIT_DIR}/RL" ]; then
    PROJ_ROOT="$SLURM_SUBMIT_DIR"
else
    PROJ_ROOT="/scratch/${USER}/chehab-unified"
fi
export PYTHONPATH="$PROJ_ROOT/RL:$PROJ_ROOT/RL/pytrs:${PYTHONPATH:-}"

echo "Node: $(hostname)  Job: ${SLURM_JOB_ID:-local}${SLURM_ARRAY_TASK_ID:+ (task $SLURM_ARRAY_TASK_ID)}"
echo "Python: $PYTHON   g++: $CXX ($("$CXX" --version | head -1))"
echo "cmake: $(cmake --version | head -1)   SEAL: $SEAL_DIR"

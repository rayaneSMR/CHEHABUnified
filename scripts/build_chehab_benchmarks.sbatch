#!/bin/bash
# Build CHEHAB (libfheco + benchmark binaries) in build/ for the real-execution evaluation.
# DNN targets (conv2d, deep_network, dnn_tensor) may fail; they are not used, so the build keeps going
# and only the benchmarks the evaluation needs are checked.
# Submit from the repo root:  sbatch scripts/build_chehab_benchmarks.sbatch

#SBATCH -p compute
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -c 16
#SBATCH --mem 32GB
#SBATCH -t 06:00:00
#SBATCH -J build-chehab
#SBATCH -o logs/build_chehab.%j.out
#SBATCH -e logs/build_chehab.%j.err

set -eo pipefail
source "${SLURM_SUBMIT_DIR:-/scratch/$USER/chehab-unified}/scripts/exp3_seal_env.sh"
cd "$PROJ_ROOT"

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_COMPILER="$CC"
cmake --build build -j16 -- -k || echo "[warn] some targets failed (expected for unused DNN targets); checking the needed ones"

NEEDED="dot_product l2_distance hamming_dist lin_reg poly_reg matrix_mul box_blur gx_kernel gy_kernel roberts_cross max sort polynomials_coyote"
MISSING=""
for b in $NEEDED; do
    [ -x "build/benchmarks/$b/$b" ] || MISSING="$MISSING $b"
    [ -f "build/benchmarks/$b/he/CMakeLists.txt" ] || MISSING="$MISSING $b(he/CMakeLists.txt)"
done
if [ -n "$MISSING" ]; then
    echo "[FAIL] missing:$MISSING"; exit 1
fi
echo "[ OK ] all evaluation benchmarks built in $PROJ_ROOT/build/benchmarks"

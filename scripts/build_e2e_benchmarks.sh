
#!/bin/bash
# Build the CHEHAB compiler and the C++ benchmark programs used by the real compile +
# SEAL execution evaluation (scripts/run_benchmarks_unified.py). Run once per clone,
# on the login node, from anywhere:
#     bash scripts/build_e2e_benchmarks.sh
#
# Uses the system g++ (found before conda is activated: the conda compiler wrapper is
# incomplete, "cannot execute 'cc1plus'"). Override with FHE_E2E_CXX=/path/to/g++.
# The generated SEAL programs are built later by the runner, which needs SEAL 4.1
# (the one built by scripts/build_bfv_noise_cli.sh is found automatically).

set -eo pipefail
PROJ_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJ_ROOT"

module load gcc 2>/dev/null || true
SYSTEM_GXX="${FHE_E2E_CXX:-$(which g++ 2>/dev/null || echo /usr/bin/g++)}"
unset CXX CC CXXFLAGS CFLAGS CPPFLAGS LDFLAGS
echo "Compiler: $SYSTEM_GXX ($("$SYSTEM_GXX" --version | head -1))"

BENCHES=(box_blur gx_kernel gy_kernel roberts_cross matrix_mul dot_product hamming_dist
         l2_distance lin_reg poly_reg max sort polynomials_coyote threshold_expr)

# The benchmark CMake files copy their he/ templates into <repo>/build/..., so the
# build folder must be called build/.
cmake -S . -B build -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER="$SYSTEM_GXX"
for b in "${BENCHES[@]}"; do
    echo "== $b"
    make -C "build/benchmarks/$b" -j 8 > "build/build_$b.log" 2>&1 \
        || { echo "ERROR: build of $b failed, see build/build_$b.log"; tail -n 20 "build/build_$b.log"; exit 1; }
done

missing=0
for b in "${BENCHES[@]}"; do
    for f in "build/benchmarks/$b/$b" "build/benchmarks/$b/he/CMakeLists.txt" "build/benchmarks/$b/he/utils.cpp"; do
        [ -e "$f" ] || { echo "MISSING: $f"; missing=1; }
    done
done
[ "$missing" = 0 ] || exit 1
echo ""
echo "OK: compiler and ${#BENCHES[@]} benchmark programs built in $PROJ_ROOT/build/benchmarks/"

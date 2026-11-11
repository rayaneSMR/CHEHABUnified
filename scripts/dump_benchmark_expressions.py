#!/usr/bin/env python3
"""Write the scalar expressions that the CHEHAB compiler gives to the RL agent for C++ benchmarks.

The bisection experiment (scripts/run_unified_bisection.sbatch) reads expressions from a text file,
one "<expression>:<name>" per line. The 46 end-to-end benchmarks are C++ programs, and 9 of them
are not in fhe_rl/datasets/benchmarks.txt (the 43 named benchmarks of that file + 26 synthetic):

    gy_kernel 3/4/5, roberts_cross 3/4/5, matrix_mul 5, tree 100-50 d=10, tree 100-100 d=10

This script compiles each benchmark once with the RL vectorizer, exactly as the end-to-end runner
does (scripts/run_benchmarks_unified.py), and copies ../expression.txt each time the compiler calls
the agent. Nothing is executed with SEAL.

    python scripts/dump_benchmark_expressions.py --model M.zip --output RL/benchmarks_missing9.txt

Default benchmarks: the 9 above. Other ones: --points gy_kernel:3,matrix_mul:5,poly:100-50:10
Requires the CHEHAB build (build/benchmarks/<bench>/<bench>, scripts/build_e2e_benchmarks.sh).
"""
import argparse
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_benchmarks_unified as rbu  # noqa: E402  (same compile protocol as the e2e runner)

REPO = rbu.REPO
MISSING9 = ["gy_kernel:3", "gy_kernel:4", "gy_kernel:5",
            "roberts_cross:3", "roberts_cross:4", "roberts_cross:5",
            "matrix_mul:5", "poly:100-50:10", "poly:100-100:10"]

WRAPPER = """#!/bin/bash
# Called by the compiler instead of python: keep a copy of the expression, then run the agent.
if [ -f "$FHE_CAPTURE_SRC" ]; then
    printf '%s\\n' "$(tr -s '\\n\\r\\t' '   ' < "$FHE_CAPTURE_SRC")" >> "$FHE_CAPTURE_OUT"
fi
exec "$FHE_CAPTURE_PYTHON" "$@"
"""


def parse_point(p):
    parts = p.split(":")
    if parts[0] == "poly":                      # poly:<regime>:<depth>
        regime, depth = parts[1], int(parts[2])
        return rbu.POLY, None, (regime, depth), f"tree_{regime}-{depth}_poly"
    bench, slot = parts[0], int(parts[1])
    if bench not in rbu.SUITE:
        sys.exit(f"Unknown benchmark: {bench}")
    return bench, slot, None, f"{bench}_{slot}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="unified joint agent .zip (the compiler calls it once per benchmark)")
    ap.add_argument("--output", required=True, help="expressions file to write ('<expression>:<name>' per line)")
    ap.add_argument("--points", default=",".join(MISSING9), help="bench:size or poly:regime:depth, comma-separated")
    ap.add_argument("--budget", type=int, default=369)
    ap.add_argument("--train_budgets", default="230,236,369,9000000")
    ap.add_argument("--work-dir", default="e2e_dump_expr", help="folder directly under the repo root")
    ap.add_argument("--compile_timeout", type=int, default=7200)
    args = ap.parse_args()

    points = [parse_point(p.strip()) for p in args.points.split(",") if p.strip()]
    work = REPO / args.work_dir
    rbu.prepare_work_dir(work, sorted({b for b, _, _, _ in points}))
    capture = work / "captured_expression.txt"
    wrapper = work / "capture_python.sh"
    wrapper.write_text(WRAPPER)
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    env = dict(os.environ)
    env.update({
        "FHE_RL_MODEL": str(Path(args.model).resolve()),
        "FHE_RL_MODEL_STAGE2": "",
        "FHE_RL_BUDGET": str(args.budget),
        "FHE_RL_TRAIN_BUDGETS": args.train_budgets,
        "FHE_RL_CONSTRAINT": "noise",
        "FHE_RL_METHOD": "nato_sc",
        "FHE_RL_ROLLBACK": "1",
        "FHE_RL_RUN_LOG": str(work / "rl_log.jsonl"),
        "PYTHON": str(wrapper),
        "FHE_CAPTURE_PYTHON": env.get("PYTHON") or sys.executable,
        "FHE_CAPTURE_SRC": str(work / "benchmarks" / "expression.txt"),   # ../expression.txt of every benchmark
        "FHE_CAPTURE_OUT": str(capture),
        "PYTHONPATH": f"{REPO / 'RL'}:{REPO / 'RL' / 'pytrs'}:{env.get('PYTHONPATH', '')}",
    })

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines, problems = [], []
    for bench, slot, poly_cfg, name in points:
        capture.unlink(missing_ok=True)
        bdir = work / "benchmarks" / bench
        try:
            ok, _, _, _, cout = rbu.compile_point(bench, bdir, slot, 1.0, env, args.compile_timeout, poly_cfg, "unified")
        except Exception as e:  # timeout etc.
            ok, cout = False, str(e)
        exprs = [e.strip() for e in capture.read_text().splitlines() if e.strip()] if capture.exists() else []
        if not exprs:
            problems.append(f"{name}: no expression captured (compile ok={ok})\n{cout[-800:]}")
            continue
        if len(exprs) > 1:   # the compiler split the vector into several sub-expressions
            problems.append(f"{name}: {len(exprs)} expressions captured (sub-vectors); written as {name}_part<i>")
            lines += [f"{e}:{name}_part{i}" for i, e in enumerate(exprs)]
        else:
            lines.append(f"{exprs[0]}:{name}")
        print(f"[dump] {name}: {len(exprs)} expression(s), compile ok={ok}", flush=True)

    out.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {len(lines)} expressions to {out}")
    if problems:
        print("\nCHECK:\n" + "\n".join(problems))
        sys.exit(1)


if __name__ == "__main__":
    main()

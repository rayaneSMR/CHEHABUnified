#!/usr/bin/env python3
"""Compile and execute optimized programs to measure time and rotation-key size.

The existing unified MORL sweep is the repository's authoritative measured
execution path. It invokes the trained agent, generates the optimized C++,
builds the SEAL program, executes it, and records circuit execution time and
rotation-key size in CSV files.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SWEEP_SCRIPT = REPO_ROOT / "scripts" / "unified_morl_experiments.py"
DEFAULT_OUTPUT = REPO_ROOT / "results" / "ablation_unified" / "seal_4pref"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("no_rollback", "rollback"), required=True)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--build-dir", default="build")
    parser.add_argument("--agents", help="Comma-separated ABL4 agents to measure")
    parser.add_argument("--benchmarks", help="Benchmark names/families to restrict")
    parser.add_argument("--budgets", help="Unified budgets, e.g. 230,236,369,9000000")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--no-bisect", action="store_true")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output_root).resolve() / args.mode
    command = [
        sys.executable,
        str(SWEEP_SCRIPT),
        "sweep",
        "--experiments",
        "ABL4",
        "--build-dir",
        args.build_dir,
        "--repeats",
        str(args.repeats),
    ]
    for flag, value in (
        ("--agents", args.agents),
        ("--benchmarks", args.benchmarks),
        ("--budgets", args.budgets),
    ):
        if value:
            command.extend([flag, value])
    if args.no_bisect:
        command.append("--no-bisect")
    if args.retry_failed:
        command.append("--retry-failed")
    if args.dry_run:
        command.append("--dry-run")

    env = {
        **os.environ,
        "UNIFIED_MORL_OUT_DIR": str(output),
        "CHEHAB_RL_ROLLBACK": "1" if args.mode == "rollback" else "0",
    }
    print(f"Measured output: {output}")
    print(f"Rollback: {env['CHEHAB_RL_ROLLBACK']}")
    print("Executing optimized programs through unified_morl_experiments.py")
    if args.dry_run:
        print(" ".join(command))
        return 0
    completed = subprocess.run(command, cwd=str(REPO_ROOT), env=env, check=False)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

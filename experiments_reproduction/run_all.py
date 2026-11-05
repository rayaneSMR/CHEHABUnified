#!/usr/bin/env python3
"""Run model evaluations, then the Experiment 2 and Experiment 3 reports."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_OUTPUT = REPO_ROOT / "results" / "ablation_unified"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--models-dir")
    parser.add_argument("--bfv-executable")
    parser.add_argument("--run-id")
    parser.add_argument("--measured", action="store_true",
                        help="Also compile/run optimized SEAL programs for measured time and key-size CSVs")
    parser.add_argument("--build-dir", default="build")
    parser.add_argument("--measured-agents")
    parser.add_argument("--measured-benchmarks")
    parser.add_argument("--measured-budgets")
    parser.add_argument("--measured-repeats", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    evaluator = [sys.executable, str(HERE / "run_model_evaluations.py"),
                 "--output-root", args.output_root]
    for flag, value in (("--models-dir", args.models_dir),
                        ("--bfv-executable", args.bfv_executable),
                        ("--run-id", args.run_id)):
        if value:
            evaluator.extend([flag, value])
    if args.dry_run:
        evaluator.append("--dry-run")
    result = subprocess.run(evaluator, cwd=str(REPO_ROOT), check=False)
    if result.returncode:
        return result.returncode

    if args.measured:
        for mode in ("no_rollback", "rollback"):
            measured = [
                sys.executable,
                str(HERE / "run_measured_sweep.py"),
                "--mode",
                mode,
                "--output-root",
                str(Path(args.output_root) / "seal_4pref"),
                "--build-dir",
                args.build_dir,
                "--repeats",
                str(args.measured_repeats),
            ]
            for flag, value in (
                ("--agents", args.measured_agents),
                ("--benchmarks", args.measured_benchmarks),
                ("--budgets", args.measured_budgets),
            ):
                if value:
                    measured.extend([flag, value])
            result = subprocess.run(measured, cwd=str(REPO_ROOT), check=False)
            if result.returncode:
                return result.returncode
    if args.dry_run:
        return 0

    for script, extra in (
        (
            HERE / "experiment_2" / "run_experiment_2.py",
            ["--source", "unified", "--seal-dir", str(Path(args.output_root) / "seal_4pref")],
        ),
        (
            HERE / "experiment_3" / "run_experiment_3.py",
            ["--source", "unified", "--seal-dir", str(Path(args.output_root) / "seal_4pref")],
        ),
    ):
        command = [sys.executable, str(script), *extra,
                   "--unified-dir", args.output_root]
        result = subprocess.run(command, cwd=str(REPO_ROOT), check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

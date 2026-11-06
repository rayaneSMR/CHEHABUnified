#!/usr/bin/env python3
"""Evaluate the unified ablation checkpoints and persist reproducible CSV results.

This is the execution stage for Experiments 2 and 3.  It intentionally does
not read ``hpc_results``.  Each checkpoint is loaded by the repository's
``fhe_rl test`` command and its generated CSV files are placed in the same
layout consumed by the reporting scripts.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
RL_DIR = REPO_ROOT / "RL"
MODELS_DIR = RL_DIR / "fhe_rl" / "trained_models"
DEFAULT_OUTPUT = REPO_ROOT / "results" / "ablation_unified"
DEFAULT_ORIGINAL = RL_DIR / "fhe_rl" / "datasets" / "benchmarks.txt"
DEFAULT_THRESHOLD = RL_DIR / "fhe_rl" / "datasets" / "threshold_benchmarks.txt"

AGENTS = {
    "unconstrained": "none",
    "v4_mb": "margin_barrier",
    "v4_nmask": "noise_masking",
    "v4_mb_film": "margin_barrier",
    "v5_focops": "nato_sc",
    "v5_lagpid": "nato_sc",
}
PREFERENCES = "1.0,0.0;0.9,0.1;0.8,0.2;0.6,0.4"
BUDGETS = "230,236,369,9000000"


def resolve_model(agent: str, models_dir: Path, overrides: dict[str, Path]) -> Path:
    if agent in overrides:
        model = overrides[agent]
        if not model.is_file():
            raise FileNotFoundError(f"Model override for {agent} not found: {model}")
        return model
    stem = models_dir / f"unified_noise_abl_{agent}_4pref"
    best = stem.with_name(stem.name + "_best.zip")
    final = stem.with_suffix(".zip")
    if best.is_file():
        return best
    if final.is_file():
        return final
    raise FileNotFoundError(
        f"Missing checkpoint for {agent}: expected {best} or {final}. "
        f"Train it with scripts/ablation_unified/train_{agent}_4pref.sbatch."
    )


def build_command(
    model: Path,
    dataset: Path,
    output: Path,
    method: str,
    bfv_args: list[str],
) -> list[str]:
    return [
        sys.executable,
        "-u",
        "-m",
        "fhe_rl",
        "--framework",
        "unified",
        "--embedder",
        "gnn",
        "test",
        "--test_mode",
        "v2",
        "--model",
        str(model),
        "--pipeline",
        "joint",
        "--dataset",
        str(dataset),
        "--budgets",
        BUDGETS,
        "--train_budgets",
        BUDGETS,
        "--method",
        method,
        "--constraint",
        "noise",
        "--preferences",
        PREFERENCES,
        *bfv_args,
        "--output",
        str(output),
    ]


def run(args: argparse.Namespace) -> int:
    selected = args.agents or list(AGENTS)
    datasets = {
        "original": Path(args.original_dataset).resolve(),
        "threshold": Path(args.threshold_dataset).resolve(),
    }
    requested_sets = [item.strip() for item in args.sets.split(",") if item.strip()]
    invalid_sets = sorted(set(requested_sets) - set(datasets))
    if invalid_sets:
        raise ValueError(f"Unknown dataset set(s): {', '.join(invalid_sets)}")
    for name in requested_sets:
        if not datasets[name].is_file():
            raise FileNotFoundError(f"Dataset not found: {datasets[name]}")

    models_dir = Path(args.models_dir).resolve()
    overrides = {}
    for item in args.model:
        try:
            agent, model_path = item.split("=", 1)
        except ValueError as exc:
            raise ValueError(f"--model must use agent=path, got {item}") from exc
        if agent not in AGENTS:
            raise ValueError(f"Unknown agent in --model: {agent}")
        overrides[agent] = Path(model_path).expanduser().resolve()
    output_root = Path(args.output_root).resolve()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bfv_args: list[str] = []
    if args.bfv_executable:
        bfv_args = [
            "--seal-noise-bound-executable",
            str(Path(args.bfv_executable).resolve()),
            "--seal-poly-modulus-degree",
            "16384",
            "--seal-plain-modulus",
            "786433",
            "--seal-coeff-modulus",
            "48,48,48,49,49,49,49,49,49",
        ]

    jobs: list[tuple[str, Path, str, Path, Path]] = []
    for agent in selected:
        if agent not in AGENTS:
            raise ValueError(f"Unknown agent {agent}; choose from {', '.join(AGENTS)}")
        model = resolve_model(agent, models_dir, overrides)
        eval_dir = output_root / f"{agent}_4pref" / f"eval_{run_id}"
        eval_dir.mkdir(parents=True, exist_ok=True)
        (eval_dir / "model.txt").write_text(str(model) + "\n", encoding="utf-8")
        for set_name in requested_sets:
            output = eval_dir / f"{set_name}.xlsx"
            jobs.append((agent, model, AGENTS[agent], datasets[set_name], output))

    print(f"Repository: {REPO_ROOT}")
    print(f"Output run: {output_root}/*_4pref/eval_{run_id}")
    print(f"Jobs: {len(jobs)} ({len(selected)} agents x {len(requested_sets)} datasets)")
    for agent, model, method, dataset, output in jobs:
        command = build_command(model, dataset, output, method, bfv_args)
        print(f"\n[{agent}] {dataset.name}")
        print(" ".join(f'"{part}"' if " " in part else part for part in command))
        if args.dry_run:
            continue
        log_path = output.with_suffix(".log")
        with log_path.open("w", encoding="utf-8", newline="\n") as log:
            completed = subprocess.run(
                command,
                cwd=str(RL_DIR),
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Evaluation failed for {agent}/{dataset.name}; see {log_path} "
                f"(exit code {completed.returncode})"
            )
        csv_path = output.with_suffix(".csv")
        if not csv_path.is_file():
            raise RuntimeError(f"Evaluation completed without expected CSV: {csv_path}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agents", nargs="+", choices=sorted(AGENTS), help="Subset of checkpoints to evaluate")
    parser.add_argument("--model", action="append", default=[], metavar="AGENT=PATH",
                        help="Override a checkpoint path; may be repeated")
    parser.add_argument("--sets", default="original,threshold", help="Comma-separated datasets: original,threshold")
    parser.add_argument("--models-dir", default=str(MODELS_DIR))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--original-dataset", default=str(DEFAULT_ORIGINAL))
    parser.add_argument("--threshold-dataset", default=str(DEFAULT_THRESHOLD))
    parser.add_argument("--run-id", help="Stable output identifier; defaults to UTC timestamp")
    parser.add_argument("--bfv-executable", help="Optional BFV rollback certificate executable")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print jobs without running models")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

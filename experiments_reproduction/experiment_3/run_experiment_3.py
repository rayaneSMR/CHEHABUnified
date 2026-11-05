#!/usr/bin/env python3
"""Experiment 3 - Safety Rollback & Synthetic Near-Threshold Benchmark.

This script reproduces Experiment 3 using the unified RL environment with noise
constraint (RL/fhe_rl/env_unified.py, fheEnvUnified) directly from its repository
location.

Execution:
    python experiments_reproduction/experiment_3/run_experiment_3.py [--source auto|unified|legacy]

Methodology:
    1. Instantiates `fheEnvUnified` directly from `RL/fhe_rl/env_unified.py`
       (the 4th RL agent: multi-objective RL with noise constraint) to verify live
       environment execution and demonstrate trajectory rollback selection.
    2. Generates the synthetic near-threshold benchmark (60 VecLang expressions:
       20 targeting B=230, 20 targeting B=236, 20 targeting B=369 with initial noise
       within 80-100% of the target budget) using `NoiseEstimator` and `pytrs`, and
       checks it against RL/fhe_rl/datasets/threshold_benchmarks.txt (the evaluated set).
    3. Compares the noise distributions of the original 69-expression benchmark and
       the synthetic threshold benchmark against finite budget thresholds.
    4. Audits trajectory checkpoints step-by-step from raw trajectory strings
       (`Trajectory Costs`, `Trajectory Noises`) across all threshold evaluation episodes:
           legacy  : recomputes the lowest-cost-within-budget rule and compares it with
                     `Safe Final Cost`, `Safe Final Noise`, `Best Valid Step`, `Safety Activated`.
           unified : the rollback picks the best state by w_ops*ops/ops0 + w_keys*keys and
                     requires a BFV certificate; trajectories store neither per-step
                     ops/keys nor certificates, so the audit checks consistency instead
                     (safe state = trajectory state at `Best Valid Step`, within budget or
                     fallback to the input, `Safety Activated` = best step != last step).
    5. Evaluates Safe Cost Reduction (%) on initially within-budget expressions for:
           - Unconstrained + Safety
           - Constrained (V5 Lag-PID + NATO-SC) + Safety
       measuring the constrained agent advantage across budgets.
    6. Evaluates violation elimination on initially within-budget expressions:
       compares raw final RL output violation rates against post-rollback rates.
    7. Evaluates full agent ablation with rollback on the original 69-expression
       benchmark across all 6 agent variants on initially within-budget expressions.
    8. For parts 5 and 7 (when the results have them), reports the two MORL objectives
       of the rolled-back programs:
           Exec cost reduction (%) = 100 * (Initial Ops - Safe Final Ops) / Initial Ops
               (Ops = C_exec = exec_cost_mo, the execution-time cost model)
           Rotation keys           = Safe Final Keys (C_keys = unique rotation keys)
       plus a per-preference breakdown (w_ops, w_keys) on the threshold set.
    9. Emits structured CSV files, high-resolution plots, markdown report
       (exp3_results.md), and execution metadata (run_metadata.json).

   10. Measured on SEAL/BFV with rollback: circuit execution time (ms), rotation-key size (MB)
       and measured violation rate per agent and budget on initially within-budget points, from
       the real-execution sweep (scripts/ablation_unified/seal_sweep_4pref.sbatch, ROLLBACK=1)
       on the 47 C++ benchmark instances, plus the per-preference breakdown.

Result sources:
    --source unified (default)  results/ablation_unified/<agent>_4pref/eval_<jobid>/{original,threshold}.csv
             (--ablation 4pref, default; eval_4pref.sbatch, the 4 training preferences) or
             results/ablation_unified/<agent>/eval_<jobid>/... (--ablation 10pref; 10 preferences).
    --source legacy  hpc_results/rl_test_results/{original,threshold}_<tag>.xlsx (no exec/keys).
    --source auto    unified when results exist for all 6 agents, else legacy.
    --seal-dir       results/ablation_unified/seal_4pref (reads its rollback/raw/ CSVs);
             the measured section is skipped when it has no results.

Exit codes: 0 ok | 1 unexpected error | 2 data/validation error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure UTF-8 console output on Windows
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# On Windows, ensure torch/lib DLL directory is added to search path before importing torch
if sys.platform == "win32":
    for p in sys.path:
        tlib = os.path.join(p, "torch", "lib")
        if os.path.isdir(tlib):
            try:
                os.add_dll_directory(tlib)
            except Exception:
                pass

import torch

# --------------------------------------------------------------------------- #
# Paths & Setup (Directly pointing to repository locations)
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]  # experiments_reproduction/experiment_3 -> repo root
RL_DIR = REPO_ROOT / "RL"
PYTRS_DIR = RL_DIR / "pytrs"

for p in [str(RL_DIR), str(PYTRS_DIR), str(HERE.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from fhe_rl.env_unified import fheEnvUnified
    from pytrs import (
        create_rules, parse_sexpr, Op, Const, Var,
        VARIABLE_RANGE, CONST_OFFSET, PAREN_CLOSE, PAREN_OPEN,
        node_to_id, get_multiplicative_depth
    )
    from noise_estimator import NoiseEstimator
except ImportError as exc:
    print(f"ERROR: Failed to import RL / pytrs modules: {exc}", file=sys.stderr)
    sys.exit(1)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import objective_metrics as om
from objective_metrics import EXEC_LABEL, KEYS_LABEL

DEFAULT_RESULTS = REPO_ROOT / "hpc_results" / "rl_test_results"
DEFAULT_UNIFIED = REPO_ROOT / "results" / "ablation_unified"
DEFAULT_SEAL = DEFAULT_UNIFIED / "seal_4pref"
SEAL_MODE = "rollback"   # Experiment 3 = with safety rollback
DEFAULT_ORIG_BENCHMARK = RL_DIR / "fhe_rl" / "datasets" / "benchmarks.txt"
DEFAULT_THRESH_DATASET = RL_DIR / "fhe_rl" / "datasets" / "threshold_benchmarks.txt"
DEFAULT_OUT = HERE / "outputs"

BUDGETS = [230, 236, 369]
ALL_BUDGETS = [230, 236, 369, 9_000_000]
BUDGET_LABEL = {230: "230", 236: "236", 369: "369", 9_000_000: "9M"}

ABLATION_AGENTS = {
    "Unconstrained": "Prior-work unconstrained agent",
    "V4 Margin Barrier": "--method margin_barrier, encoding raw",
    "V4 Noise Masking": "--method noise_masking, encoding embed",
    "V4 MB + FiLM": "--method margin_barrier, encoding film",
    "V5 FOCOPS + NATO-SC": "--method nato_sc, algo focops, film",
    "V5 Lag-PID + NATO-SC": "--method nato_sc, algo lagrangian_pid, film (selected)",
}

CONSTRAINED_NAME = "V5 Lag-PID + NATO-SC"
UNCONSTRAINED_NAME = "Unconstrained"
UNC_SAFE = "Unconstrained + Safety"
CON_SAFE = "Constrained (Lag-PID) + Safety"


class DataError(Exception):
    """Input data failed a validation check (exit code 2)."""


# --------------------------------------------------------------------------- #
# Synthetic Threshold Benchmark Generator
# --------------------------------------------------------------------------- #
_vc = 0

def _reset_vc():
    global _vc
    _vc = 0

def _next_var():
    global _vc
    _vc += 1
    return f"v{_vc}"

def _add_tree(depth: int, extra: int = 2) -> str:
    if depth <= 0 or random.random() < 0.4:
        return _next_var()
    if random.random() < 0.15:
        return f"(- {_add_tree(depth - 1)})"
    op = random.choice(["+", "-"])
    return f"({op} {_add_tree(depth - 1)} {_add_tree(depth - 1)})"

def _scalar_md(target_md: int, extra: int = 2) -> str:
    if target_md <= 0:
        return _add_tree(random.randint(0, extra))
    main_md = target_md - 1
    other_md = random.randint(0, min(2, target_md - 1))
    mc = _scalar_md(main_md, extra)
    oc = _scalar_md(other_md, extra)
    lhs, rhs = (mc, oc) if random.random() < 0.5 else (oc, mc)
    res = f"(* {lhs} {rhs})"
    if random.random() < 0.25:
        ap = _add_tree(random.randint(0, extra))
        op = random.choice(["+", "-"])
        res = f"({op} {res} {ap})" if random.random() < 0.5 else f"({op} {ap} {res})"
    return res

def _gen_vec(target_md: int, vec_size: int) -> str:
    _reset_vc()
    target_idx = random.randint(0, vec_size - 1)
    elems = []
    for i in range(vec_size):
        md = target_md if i == target_idx else random.randint(0, min(target_md, 4))
        elems.append(_scalar_md(md))
    return f"(Vec {' '.join(elems)})"

def _dfs(expr, d=0, nl=None):
    if nl is None:
        nl = []
    if isinstance(expr, Op):
        nl.append((PAREN_OPEN, d))
        nl.append((expr, d))
        for c in expr.args:
            _dfs(c, d + 1, nl)
        nl.append((PAREN_CLOSE, d))
    else:
        nl.append((expr, d))
    return nl

def _tok_seq(expr_str: str):
    expr = parse_sexpr(expr_str)
    nl = _dfs(expr)
    vm, im = {}, {}
    nvi, nii = VARIABLE_RANGE[0], CONST_OFFSET
    ids = []
    for node, _ in nl:
        if node in (PAREN_OPEN, PAREN_CLOSE):
            ids.append(node)
        else:
            nid, nvi, nii, _ = node_to_id(node, vm, im, nvi, nii)
            ids.append(nid)
    return tuple(ids)

def generate_synthetic_threshold_benchmark(
    seed: int = 7777,
    per_budget: int = 20,
    low_pct: float = 0.80,
    high_pct: float = 1.00,
) -> list[dict]:
    """Generates 60 near-threshold VecLang expressions targeting B in {230, 236, 369}."""
    random.seed(seed)
    np.random.seed(seed)
    estimator = NoiseEstimator()

    vec_sizes = [1, 4, 8, 9, 16, 25, 32]
    all_generated = []
    all_tokens = set()

    md_ranges = {
        230: (4, 8, 230 * low_pct, 230 * high_pct),
        236: (4, 9, 236 * low_pct, 236 * high_pct),
        369: (7, 13, 369 * low_pct, 369 * high_pct),
    }

    for b in BUDGETS:
        md_lo, md_hi, noise_lo, noise_hi = md_ranges[b]
        generated = []
        attempts = 0
        max_attempts = per_budget * 5000

        while len(generated) < per_budget and attempts < max_attempts:
            attempts += 1
            md = random.randint(md_lo, md_hi)
            vs = random.choice(vec_sizes)
            expr_str = _gen_vec(md, vs)

            try:
                expr = parse_sexpr(expr_str)
            except Exception:
                continue

            actual_md = get_multiplicative_depth(expr)
            if len(expr.args) not in {1, 4, 8, 9, 16, 25, 32}:
                continue

            noise = float(estimator.estimate(expr))
            if noise < noise_lo or noise > noise_hi:
                continue

            try:
                ts = _tok_seq(expr_str)
            except Exception:
                continue
            if ts in all_tokens:
                continue

            all_tokens.add(ts)
            name = f"thresh_b{b}_md{actual_md}_vs{vs}_n{int(noise)}"
            entry = {
                "expression": expr_str,
                "name": name,
                "target_budget": b,
                "mult_depth": actual_md,
                "noise": noise,
                "vec_size": vs,
            }
            generated.append(entry)
            all_generated.append(entry)

    return all_generated


# --------------------------------------------------------------------------- #
# Live Unified Environment & Safety Rollback Verification
# --------------------------------------------------------------------------- #
def run_live_unified_agent_demo(benchmark_expr: str, budget: float = 230.0) -> dict:
    """Instantiates fheEnvUnified (the 4th RL agent) and demonstrates live rollback."""
    rules_p = str(RL_DIR / "rules.txt")
    rot_p = str(RL_DIR / "rotations_rules.txt")

    rules = create_rules(rules_p, rot_p if os.path.exists(rot_p) else None)
    rules["END"] = None

    env = fheEnvUnified(
        rules_list=rules,
        expressions=[benchmark_expr],
        max_positions=16,
        embeddings_model=None,
        budget_options=[budget],
        constraint_method="nato_sc",
        constraint_metric="noise",
        verbose=False,
    )

    obs, info = env.reset(options={"expression": benchmark_expr, "budget": budget})
    initial_cost = env.initial_cost
    initial_noise = env.curr_constraint

    checkpoints = [{
        "step": 0,
        "expression": benchmark_expr,
        "cost": initial_cost,
        "noise": initial_noise,
        "is_compliant": initial_noise <= budget,
    }]

    # Step through rewriting actions
    for step in range(1, 4):
        # Sample an action from available actions
        mask = env.get_action_mask()
        valid_actions = np.where(mask > 0)[0]
        if len(valid_actions) == 0:
            break
        act = int(valid_actions[0])
        obs, reward, terminated, truncated, step_info = env.step(act)
        checkpoints.append({
            "step": step,
            "expression": env.expression,
            "cost": env.current_cost,
            "noise": env.curr_constraint,
            "is_compliant": env.curr_constraint <= budget,
        })
        if terminated or truncated:
            break

    # Apply mathematical safety rollback rule
    valid_cps = [cp for cp in checkpoints if cp["noise"] <= budget]
    if valid_cps:
        best_cp = min(valid_cps, key=lambda cp: cp["cost"])
        safety_activated = (best_cp["step"] != checkpoints[-1]["step"])
    else:
        best_cp = checkpoints[0]
        safety_activated = True

    return {
        "initial_cost": initial_cost,
        "initial_noise": initial_noise,
        "checkpoints": checkpoints,
        "best_valid_step": best_cp["step"],
        "safe_cost": best_cp["cost"],
        "safe_noise": best_cp["noise"],
        "safety_activated": safety_activated,
        "agent_final_cost": checkpoints[-1]["cost"],
        "agent_final_noise": checkpoints[-1]["noise"],
    }


# --------------------------------------------------------------------------- #
# Result loading
# --------------------------------------------------------------------------- #
ABLATION = "4pref"   # set from --ablation in run()


def load_results(source: str, label: str, set_name: str, data_dir: Path, unified_dir: Path,
                 required: bool = True) -> tuple[pd.DataFrame | None, Path | None]:
    try:
        path = om.agent_file(source, label, set_name, data_dir, unified_dir, ABLATION)
    except om.SourceError as exc:
        if required:
            raise DataError(f"[{label}] {exc}")
        return None, None
    if not path.is_file():
        if required:
            raise DataError(f"[{label}] missing results: {path}")
        return None, None
    df = om.read_results(path)
    need = ["Budget", "Expression #", "Is Feasible", "Initial Noise", "Agent Violated",
            "Safe Cost Reduction (%)", "Safe Violated"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise DataError(f"[{label}] {path.name}: missing columns {missing}")
    problems = om.check_objectives(df, label)
    if problems:
        raise DataError("; ".join(problems))
    return df, path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Rollback Trajectory Audit
# --------------------------------------------------------------------------- #
def audit_rollback_trajectories(df: pd.DataFrame, agent_name: str, mode: str = "legacy") -> tuple[pd.DataFrame, int]:
    """Audits trajectory strings step-by-step against Safe Final Cost/Noise columns.

    mode="legacy":  recompute the lowest-cost-within-budget rule (the rule used by those runs).
    mode="unified": the unified rollback ranks states by the preference score on ops/keys and
                    needs a BFV certificate, neither of which the trajectory strings store; check
                    that the reported safe state is the trajectory state at `Best Valid Step`, is
                    within budget (or is the input fallback), and that `Safety Activated` agrees.
    """
    records = []
    mismatches = 0

    for idx, row in df.iterrows():
        budget = float(row["Budget"])
        expr_num = int(row["Expression #"])
        costs = [float(c) for c in str(row["Trajectory Costs"]).split("|")]
        noises = [float(n) for n in str(row["Trajectory Noises"]).split("|")]

        actual_safe_cost = float(row["Safe Final Cost"])
        actual_safe_noise = float(row["Safe Final Noise"])
        actual_best_step = int(row["Best Valid Step"])
        actual_safety_act = bool(row["Safety Activated"])

        if mode == "legacy":
            valid_indices = [i for i, n in enumerate(noises) if n <= budget]
            if valid_indices:
                best_i = min(valid_indices, key=lambda i: costs[i])
                recomputed_cost = costs[best_i]
                recomputed_noise = noises[best_i]
                recomputed_step = best_i
                safety_act = (best_i != len(costs) - 1)
            else:
                recomputed_cost = costs[0]
                recomputed_noise = noises[0]
                recomputed_step = 0
                safety_act = True
        else:
            in_range = 0 <= actual_best_step < len(costs)
            recomputed_step = actual_best_step if in_range else -1
            recomputed_cost = costs[actual_best_step] if in_range else float("nan")
            recomputed_noise = noises[actual_best_step] if in_range else float("nan")
            safety_act = (actual_best_step != len(costs) - 1)
            within = in_range and (noises[actual_best_step] <= budget or actual_best_step == 0)

        cost_match = abs(recomputed_cost - actual_safe_cost) < 1e-3
        noise_match = abs(recomputed_noise - actual_safe_noise) < 1e-2
        step_match = (recomputed_step == actual_best_step)
        act_match = (safety_act == actual_safety_act)

        match = cost_match and noise_match and step_match and act_match
        if mode != "legacy":
            match = match and within
        if not match:
            mismatches += 1

        rec = {
            "Agent": agent_name,
            "Budget": int(budget),
            "Expression #": expr_num,
        }
        if "w_ops" in row and pd.notna(row.get("w_ops")):
            rec["w_ops"], rec["w_keys"] = row["w_ops"], row["w_keys"]
        rec.update({
            "Trajectory Steps": len(costs) - 1,
            "Best Valid Step Recomputed": recomputed_step,
            "Best Valid Step Actual": actual_best_step,
            "Safe Cost Recomputed": recomputed_cost,
            "Safe Cost Actual": actual_safe_cost,
            "Safe Noise Recomputed": round(recomputed_noise, 2),
            "Safe Noise Actual": round(actual_safe_noise, 2),
            "Safety Activated Recomputed": safety_act,
            "Safety Activated Actual": actual_safety_act,
            "Audit Match": match,
        })
        records.append(rec)

    return pd.DataFrame(records), mismatches


def df_to_markdown(df: pd.DataFrame) -> str:
    """Format DataFrame as a clean Markdown table without external dependencies."""
    headers = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(val) for val in row) + " |")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Objective tables (exec cost & rotation keys after rollback)
# --------------------------------------------------------------------------- #
def safe_objectives_row(agent: str, df: pd.DataFrame, budgets: list[int]) -> dict:
    """Safe exec-cost reduction and avg rotation keys per budget on within-budget rows."""
    within = df[df["Is Feasible"]]
    row = {"Agent": agent}
    ex, ks = [], []
    for b in budgets:
        st = om.objective_stats(within[within["Budget"] == b], "Safe")
        row[f"B={BUDGET_LABEL[b]} {EXEC_LABEL}"] = round(st["exec_red"], 2)
        row[f"B={BUDGET_LABEL[b]} avg keys"] = round(st["keys"], 2)
        ex.append(st["exec_red"])
        ks.append(st["keys"])
    row[f"Average {EXEC_LABEL}"] = round(float(np.mean(ex)), 2)
    row["Average keys"] = round(float(np.mean(ks)), 2)
    return row


def compact(t: pd.DataFrame, budgets: list[int]) -> pd.DataFrame:
    rows = []
    for _, r in t.iterrows():
        row = {"Agent": r["Agent"]}
        for b in budgets:
            lb = BUDGET_LABEL[b]
            row[f"B={lb}"] = f"{r[f'B={lb} {EXEC_LABEL}']:.2f}% / {r[f'B={lb} avg keys']:.2f}"
        row["Average"] = f"{r[f'Average {EXEC_LABEL}']:.2f}% / {r['Average keys']:.2f}"
        rows.append(row)
    return pd.DataFrame(rows)


OBJ_EXPLAIN = (
    "Each cell is `exec cost reduction (%) / average rotation keys` of the **rolled-back** program "
    "(`Safe *` columns), on initially within-budget expressions. "
    "Exec cost = `C_exec` (`exec_cost_mo`, the execution-time cost model), reduction = "
    "`100 * (Initial Ops - Safe Final Ops) / Initial Ops` (higher is better). "
    "Rotation keys = `C_keys`, unique rotation (Galois) keys of the program (lower is better; inputs start with 0). "
    "Cost-model values, not measured SEAL run times. Means over expressions x preferences.\n"
)


# --------------------------------------------------------------------------- #
# Main Reproduction Runner
# --------------------------------------------------------------------------- #
def main():
    parser = argparse.ArgumentParser(
        description="Reproduce Experiment 3 (Safety Rollback & Synthetic Near-Threshold Benchmark)."
    )
    parser.add_argument("--source", choices=["auto", "unified", "legacy"], default="unified",
                        help="unified (default) = results/ablation_unified (exec cost + rotation keys), "
                             "legacy = old hpc_results workbooks, auto = unified if present else legacy")
    parser.add_argument("--ablation", choices=om.ABLATIONS, default="4pref",
                        help="unified: 4pref (default) = <agent>_4pref folders, 10pref = <agent> folders")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_RESULTS, help="legacy: path to HPC result workbooks")
    parser.add_argument("--unified-dir", type=Path, default=DEFAULT_UNIFIED,
                        help="unified: results/ablation_unified (<agent>[_4pref]/eval_<job>/{original,threshold}.csv)")
    parser.add_argument("--seal-dir", type=Path, default=DEFAULT_SEAL,
                        help=f"measured SEAL sweep (reads <seal-dir>/{SEAL_MODE}/raw/abl4_<agent>*.csv)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT, help="Output root directory")
    parser.add_argument("--seed", type=int, default=7777, help="Random seed for benchmark generator")
    args = parser.parse_args()
    try:
        return run(args)
    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def run(args) -> int:
    t_start = time.perf_counter()
    out_dir = args.out_dir
    global ABLATION
    ABLATION = args.ablation
    source = om.resolve_source(args.source, args.data_dir, args.unified_dir, ABLATION)
    data_dir = args.unified_dir if source == "unified" else args.data_dir

    # Output subdirectories (clean names, NO 3A/3B/etc.)
    subdirs = {
        "synthetic_benchmark": out_dir / "synthetic_benchmark",
        "rollback_audit": out_dir / "rollback_audit",
        "constrained_vs_unconstrained": out_dir / "constrained_vs_unconstrained",
        "violation_rates": out_dir / "violation_rates",
        "original_benchmark_ablation": out_dir / "original_benchmark_ablation",
    }
    for sd in subdirs.values():
        sd.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print("  EXPERIMENT 3: SAFETY ROLLBACK & SYNTHETIC NEAR-THRESHOLD BENCHMARK")
    print("=" * 78)
    print(f"Result Source         : {source}")
    print(f"Results Directory     : {data_dir}")
    print(f"Output Directory      : {out_dir}")
    print(f"Unified Agent (4th)   : fheEnvUnified (RL/fhe_rl/env_unified.py)")
    print()

    # ----------------------------------------------------------------------- #
    # Part 1: Live Demonstration of fheEnvUnified & Rollback Logic
    # ----------------------------------------------------------------------- #
    print("[1/6] Instantiating 4th RL Agent (fheEnvUnified) & Live Rollback Demo...")
    sample_expr = "(Vec (* (+ v1 v2) (* v3 v4)) (* v5 (+ v6 v7)))"
    demo_result = run_live_unified_agent_demo(sample_expr, budget=230.0)
    print(f"  Sample Initial State : Cost={demo_result['initial_cost']:.0f}, Noise={demo_result['initial_noise']:.1f}")
    print(f"  Live Trajectory Steps: {len(demo_result['checkpoints'])-1}")
    print(f"  Rollback Selection   : Best Valid Step={demo_result['best_valid_step']}, Safe Cost={demo_result['safe_cost']:.0f}, Safety Activated={demo_result['safety_activated']}")
    print("  [OK] fheEnvUnified verified and active.")
    print()

    # ----------------------------------------------------------------------- #
    # Part 2: Generate Synthetic Threshold Benchmark & Distribution Comparison
    # ----------------------------------------------------------------------- #
    print("[2/6] Generating 60 Synthetic Near-Threshold VecLang Expressions...")
    thresh_entries = generate_synthetic_threshold_benchmark(seed=args.seed)
    thresh_txt_path = subdirs["synthetic_benchmark"] / "threshold_benchmarks.txt"
    with open(thresh_txt_path, "w", encoding="utf-8") as f:
        for entry in thresh_entries:
            f.write(f"{entry['expression']}:{entry['name']}\n")

    # Mirror copy in outputs root
    with open(out_dir / "threshold_benchmarks.txt", "w", encoding="utf-8") as f:
        for entry in thresh_entries:
            f.write(f"{entry['expression']}:{entry['name']}\n")

    # Is the regenerated set the one the agents were evaluated on?
    dataset_match = None
    if DEFAULT_THRESH_DATASET.is_file():
        with open(DEFAULT_THRESH_DATASET, "r", encoding="utf-8") as f:
            ds = [l.strip().split(":")[0] for l in f if l.strip()]
        dataset_match = ds == [e["expression"] for e in thresh_entries]
        print(f"  Matches RL/fhe_rl/datasets/threshold_benchmarks.txt: {dataset_match}")

    comp_rows = []
    for b in BUDGETS:
        b_entries = [e for e in thresh_entries if e["target_budget"] == b]
        noises = [e["noise"] for e in b_entries]
        ratios = [n / b * 100.0 for n in noises]
        comp_rows.append({
            "Target Budget": b,
            "Count": len(b_entries),
            "Target Range": f"80-100% of {b}",
            "Min Noise": round(min(noises), 2),
            "Max Noise": round(max(noises), 2),
            "Mean Noise": round(float(np.mean(noises)), 2),
            "Mean % of Budget": round(float(np.mean(ratios)), 1),
            "Within Budget Count": sum(1 for n in noises if n <= b),
        })
    df_comp = pd.DataFrame(comp_rows)
    df_comp.to_csv(subdirs["synthetic_benchmark"] / "threshold_dataset_composition.csv", index=False)
    df_comp.to_csv(out_dir / "threshold_dataset_composition.csv", index=False)
    print(f"  Generated {len(thresh_entries)} expressions saved to {thresh_txt_path.name}")
    print(f"  Per-budget breakdown:\n{df_comp.to_string(index=False)}")
    print()

    # Compare Noise Distributions: Original (69) vs Threshold (60)
    print("[3/6] Generating Noise Distribution Comparison Plot...")
    df_orig, orig_path = load_results(source, CONSTRAINED_NAME, "original", args.data_dir, args.unified_dir)
    df_thresh, thresh_path = load_results(source, CONSTRAINED_NAME, "threshold", args.data_dir, args.unified_dir)
    df_unc_thresh, unc_thresh_path = load_results(source, UNCONSTRAINED_NAME, "threshold", args.data_dir, args.unified_dir)

    # one value per expression (unified results repeat each expression per preference)
    orig_init_noises = df_orig[df_orig["Budget"] == 230].drop_duplicates("Expression #")["Initial Noise"].values
    thresh_init_noises = df_thresh[df_thresh["Budget"] == 230].drop_duplicates("Expression #")["Initial Noise"].values

    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
    bins = np.linspace(0, 400, 41)
    ax.hist(orig_init_noises, bins=bins, alpha=0.6, color="#4C72B0", label=f"Original Benchmark (N={len(orig_init_noises)})", edgecolor="black")
    ax.hist(thresh_init_noises, bins=bins, alpha=0.7, color="#DD8452", label=f"Threshold Benchmark (N={len(thresh_init_noises)})", edgecolor="black")

    colors = {"230": "#C44E52", "236": "#8172B3", "369": "#55A868"}
    for b_val, color in [(230, colors["230"]), (236, colors["236"]), (369, colors["369"])]:
        ax.axvline(b_val, color=color, linestyle="--", linewidth=2.0, label=f"Budget B={b_val}")

    ax.set_title("Noise Distribution: Original vs Synthetic Near-Threshold Benchmarks", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Estimated Initial Noise (bits)", fontsize=12, labelpad=8)
    ax.set_ylabel("Number of Expressions", fontsize=12, labelpad=8)
    ax.set_xlim(0, 400)
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc="upper right", frameon=True, framealpha=0.9)
    plt.tight_layout()
    dist_plot_path = subdirs["synthetic_benchmark"] / "original_vs_threshold_noise_distribution.png"
    fig.savefig(dist_plot_path)
    fig.savefig(out_dir / "original_vs_threshold_noise_distribution.png")
    plt.close(fig)
    print(f"  Distribution plot saved to {dist_plot_path.name}")
    print()

    # ----------------------------------------------------------------------- #
    # Part 3: Rollback Trajectory Audit on All Threshold Episodes
    # ----------------------------------------------------------------------- #
    print("[4/6] Auditing Trajectory Checkpoint Rollback Selection on threshold episodes...")
    audit_df_lag, lag_mismatches = audit_rollback_trajectories(df_thresh, CONSTRAINED_NAME, mode=source)
    audit_df_unc, unc_mismatches = audit_rollback_trajectories(df_unc_thresh, UNCONSTRAINED_NAME, mode=source)

    audit_combined = pd.concat([audit_df_lag, audit_df_unc], ignore_index=True)
    audit_csv_path = subdirs["rollback_audit"] / "rollback_trajectory_audit.csv"
    audit_combined.to_csv(audit_csv_path, index=False)
    audit_combined.to_csv(out_dir / "rollback_trajectory_audit.csv", index=False)

    total_episodes_audited = len(audit_combined)
    total_mismatches = lag_mismatches + unc_mismatches
    concordance = 1.0 - total_mismatches / total_episodes_audited if total_episodes_audited else float("nan")
    print(f"  Audited {total_episodes_audited} trajectory rollouts: {total_mismatches} mismatches ({100 * concordance:.2f}% agreement).")
    print(f"  Audit report saved to {audit_csv_path.name}")

    # Generate Trajectory Demonstration Plot
    sample_row = df_thresh[df_thresh["Safety Activated"]].iloc[0]
    sample_costs = [float(c) for c in str(sample_row["Trajectory Costs"]).split("|")]
    sample_noises = [float(n) for n in str(sample_row["Trajectory Noises"]).split("|")]
    b_sample = sample_row["Budget"]
    best_step = int(sample_row["Best Valid Step"])

    fig, ax1 = plt.subplots(figsize=(9, 5), dpi=300)
    steps_arr = list(range(len(sample_costs)))
    color_cost = "#2b5c8f"
    color_noise = "#d95f02"

    ax1.plot(steps_arr, sample_costs, marker="o", color=color_cost, linewidth=2, label="Expression Cost")
    ax1.set_xlabel("Optimization Step", fontsize=12)
    ax1.set_ylabel("Execution Cost", color=color_cost, fontsize=12)
    ax1.tick_params(axis="y", labelcolor=color_cost)
    ax1.grid(True, linestyle=":", alpha=0.6)

    ax2 = ax1.twinx()
    ax2.plot(steps_arr, sample_noises, marker="s", color=color_noise, linewidth=2, linestyle="--", label="Noise (bits)")
    ax2.axhline(b_sample, color="#e41a1c", linestyle="-.", linewidth=1.8, label=f"Budget B={b_sample}")
    ax2.axvline(best_step, color="#4daf4a", linestyle=":", linewidth=2.5, label=f"Selected Rollback Step {best_step}")
    ax2.set_ylabel("Noise (bits)", color=color_noise, fontsize=12)
    ax2.tick_params(axis="y", labelcolor=color_noise)

    pref_tag = (f", w={om.pref_label(sample_row['w_ops'], sample_row['w_keys'])}"
                if "w_ops" in sample_row and pd.notna(sample_row.get("w_ops")) else "")
    ax1.set_title(f"Safety Rollback Trajectory Inspection (Expr #{sample_row['Expression #']}, Budget {b_sample}{pref_tag})", fontsize=13, fontweight="bold", pad=12)
    fig.tight_layout()
    traj_plot_path = subdirs["rollback_audit"] / "safety_rollback_trajectory_demo.png"
    fig.savefig(traj_plot_path)
    fig.savefig(out_dir / "safety_rollback_trajectory_demo.png")
    plt.close(fig)
    print(f"  Trajectory demo plot saved to {traj_plot_path.name}")
    print()

    # ----------------------------------------------------------------------- #
    # Part 4: Constrained vs Unconstrained Performance on Threshold Expressions
    # ----------------------------------------------------------------------- #
    print("[5/6] Evaluating Constrained vs Unconstrained Safe Cost Reduction (%)...")
    # Evaluate on initially within-budget expressions
    lag_within = df_thresh[df_thresh["Is Feasible"]]
    unc_within = df_unc_thresh[df_unc_thresh["Is Feasible"]]

    lag_safe_crs = {}
    unc_safe_crs = {}
    advantage = {}

    for b in BUDGETS:
        lag_sub = lag_within[lag_within["Budget"] == b]
        unc_sub = unc_within[unc_within["Budget"] == b]
        lag_safe_crs[b] = float(lag_sub["Safe Cost Reduction (%)"].mean())
        unc_safe_crs[b] = float(unc_sub["Safe Cost Reduction (%)"].mean())
        advantage[b] = lag_safe_crs[b] - unc_safe_crs[b]

    lag_avg = float(np.mean([lag_safe_crs[b] for b in BUDGETS]))
    unc_avg = float(np.mean([unc_safe_crs[b] for b in BUDGETS]))
    adv_avg = lag_avg - unc_avg

    cr_compare_df = pd.DataFrame([
        {
            "Agent": UNC_SAFE,
            "B=230 Safe CR%": round(unc_safe_crs[230], 2),
            "B=236 Safe CR%": round(unc_safe_crs[236], 2),
            "B=369 Safe CR%": round(unc_safe_crs[369], 2),
            "Average Safe CR%": round(unc_avg, 2),
        },
        {
            "Agent": CON_SAFE,
            "B=230 Safe CR%": round(lag_safe_crs[230], 2),
            "B=236 Safe CR%": round(lag_safe_crs[236], 2),
            "B=369 Safe CR%": round(lag_safe_crs[369], 2),
            "Average Safe CR%": round(lag_avg, 2),
        },
        {
            "Agent": "Advantage (Constrained - Unconstrained)",
            "B=230 Safe CR%": f"{advantage[230]:+.2f} pp",
            "B=236 Safe CR%": f"{advantage[236]:+.2f} pp",
            "B=369 Safe CR%": f"{advantage[369]:+.2f} pp",
            "Average Safe CR%": f"{adv_avg:+.2f} pp",
        },
    ])
    cr_compare_csv = subdirs["constrained_vs_unconstrained"] / "constrained_vs_unconstrained_safe_cr.csv"
    cr_compare_df.to_csv(cr_compare_csv, index=False)
    cr_compare_df.to_csv(out_dir / "constrained_vs_unconstrained_safe_cr.csv", index=False)
    print(f"  Safe Cost Reduction Comparison:\n{cr_compare_df.to_string(index=False)}")
    print()

    # Plot Safe Cost Reduction Comparison
    fig, ax = plt.subplots(figsize=(8.5, 5), dpi=300)
    x = np.arange(len(BUDGETS))
    width = 0.35

    unc_vals = [unc_safe_crs[b] for b in BUDGETS]
    lag_vals = [lag_safe_crs[b] for b in BUDGETS]

    rects1 = ax.bar(x - width/2, unc_vals, width, label=UNC_SAFE, color="#7293CB", edgecolor="black")
    rects2 = ax.bar(x + width/2, lag_vals, width, label=CON_SAFE, color="#E1974C", edgecolor="black")

    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10, fontweight="bold")
    for rect in rects2:
        h = rect.get_height()
        ax.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10, fontweight="bold")

    ax.set_title("Safe Cost Reduction (%) on Initially Within-Budget Threshold Expressions", fontsize=13, fontweight="bold", pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels([f"B = {b}" for b in BUDGETS], fontsize=11)
    ax.set_ylabel("Safe Cost Reduction (%)", fontsize=12)
    ax.set_ylim(0, max(50, float(np.nanmax(unc_vals + lag_vals)) * 1.15))
    ax.grid(True, linestyle=":", alpha=0.6, axis="y")
    ax.legend(loc="upper right", frameon=True)
    plt.tight_layout()
    safe_cr_plot_path = subdirs["constrained_vs_unconstrained"] / "safe_cost_reduction_comparison.png"
    fig.savefig(safe_cr_plot_path)
    fig.savefig(out_dir / "safe_cost_reduction_comparison.png")
    plt.close(fig)

    # Exec cost & rotation keys after rollback on the threshold set
    has_obj = om.has_objectives(df_thresh) and om.has_objectives(df_unc_thresh)
    has_pref = has_obj and om.has_preferences(df_thresh) and om.has_preferences(df_unc_thresh)
    thr_obj_df = thr_pref = thr_pref_sum = None
    if has_obj:
        thr_obj_df = pd.DataFrame([safe_objectives_row(UNC_SAFE, df_unc_thresh, BUDGETS),
                                   safe_objectives_row(CON_SAFE, df_thresh, BUDGETS)])
        p = subdirs["constrained_vs_unconstrained"] / "constrained_vs_unconstrained_safe_objectives.csv"
        thr_obj_df.to_csv(p, index=False)
        thr_obj_df.to_csv(out_dir / "constrained_vs_unconstrained_safe_objectives.csv", index=False)
        om.plot_objectives_by_budget(
            thr_obj_df, [BUDGET_LABEL[b] for b in BUDGETS], "Agent", "B={b} " + EXEC_LABEL, "B={b} avg keys",
            "Exec Cost and Rotation Keys after Rollback (Within-Budget Threshold Expressions)",
            subdirs["constrained_vs_unconstrained"] / "safe_objectives_comparison.png", highlight=CON_SAFE)
        om.plot_objectives_by_budget(
            thr_obj_df, [BUDGET_LABEL[b] for b in BUDGETS], "Agent", "B={b} " + EXEC_LABEL, "B={b} avg keys",
            "Exec Cost and Rotation Keys after Rollback (Within-Budget Threshold Expressions)",
            out_dir / "safe_objectives_comparison.png", highlight=CON_SAFE)
        print(f"  Safe exec cost reduction (%) / avg rotation keys:\n{compact(thr_obj_df, BUDGETS).to_string(index=False)}")
    if has_pref:
        frames_thr = {UNC_SAFE: df_unc_thresh, CON_SAFE: df_thresh}
        thr_pref = om.preference_table(frames_thr, [UNC_SAFE, CON_SAFE], BUDGETS, BUDGET_LABEL, "Safe",
                                       within_only=True, cr_col="Safe Cost Reduction (%)", viol_col="Safe Violated")
        thr_pref_sum = om.preference_summary(thr_pref)
        pref_dir = out_dir / "preference_tradeoff"
        pref_dir.mkdir(parents=True, exist_ok=True)
        thr_pref.to_csv(pref_dir / "threshold_per_budget.csv", index=False, float_format="%.4f")
        thr_pref_sum.to_csv(pref_dir / "threshold_summary.csv", index=False, float_format="%.4f")
        om.plot_preference_tradeoff(thr_pref, "Exec Cost vs Rotation Keys per Preference\n(Threshold Set, After Rollback)",
                                    pref_dir / "threshold_preference_tradeoff.png")
    print()

    # ----------------------------------------------------------------------- #
    # Part 5: Violation Rate Before and After Rollback
    # ----------------------------------------------------------------------- #
    print("[6/6] Evaluating Violation Rates Before and After Rollback...")
    viol_rows = []
    viol_vals = {}
    for agent_label, df_src in [("Unconstrained", df_unc_thresh), ("Constrained (Lag-PID)", df_thresh)]:
        w_df = df_src[df_src["Is Feasible"]]
        row = {"Agent": agent_label}
        for b in [230, 369]:
            b_w = w_df[w_df["Budget"] == b]
            n_tot = len(b_w)
            raw_v = int(b_w["Agent Violated"].sum())
            safe_v = int(b_w["Safe Violated"].sum())
            row[f"B={b} before"] = f"{(raw_v / n_tot * 100.0):.1f}% ({raw_v}/{n_tot})"
            row[f"B={b} after"] = f"{(safe_v / n_tot * 100.0):.1f}% ({safe_v}/{n_tot})"
            viol_vals[(agent_label, b)] = (raw_v / n_tot * 100.0, safe_v / n_tot * 100.0)
        viol_rows.append(row)

    viol_df = pd.DataFrame(viol_rows)
    viol_csv = subdirs["violation_rates"] / "violation_rates_before_after_rollback.csv"
    viol_df.to_csv(viol_csv, index=False)
    viol_df.to_csv(out_dir / "violation_rates_before_after_rollback.csv", index=False)
    print(f"  Violation Rates Before and After Rollback:\n{viol_df.to_string(index=False)}")
    print()

    # Plot Violation Rate Elimination
    fig, ax = plt.subplots(figsize=(8.5, 4.8), dpi=300)
    labels = ["Unconstrained (B=230)", "Constrained (B=230)", "Unconstrained (B=369)", "Constrained (B=369)"]
    keys = [("Unconstrained", 230), ("Constrained (Lag-PID)", 230), ("Unconstrained", 369), ("Constrained (Lag-PID)", 369)]
    before_vals = [viol_vals[k][0] for k in keys]
    after_vals = [viol_vals[k][1] for k in keys]

    x_idx = np.arange(len(labels))
    w_bar = 0.35
    r_before = ax.bar(x_idx - w_bar/2, before_vals, w_bar, label="Before Rollback (Raw RL Output)", color="#d95f02", edgecolor="black")
    r_after = ax.bar(x_idx + w_bar/2, after_vals, w_bar, label="After Rollback (Safe Checkpoint)", color="#2ca02c", edgecolor="black")

    for rect in r_before:
        h = rect.get_height()
        ax.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10, fontweight="bold")
    for rect in r_after:
        h = rect.get_height()
        ax.annotate(f"{h:.1f}%", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=10, fontweight="bold", color="#2ca02c")

    ax.set_title("Violation Rates Before and After Rollback on Within-Budget Threshold Programs", fontsize=12, fontweight="bold", pad=12)
    ax.set_xticks(x_idx)
    ax.set_xticklabels(labels, fontsize=9.5, rotation=10)
    ax.set_ylabel("Violation Rate (%)", fontsize=12)
    ax.set_ylim(0, max(65, max(before_vals) * 1.15))
    ax.grid(True, linestyle=":", alpha=0.6, axis="y")
    ax.legend(loc="upper right", frameon=True)
    plt.tight_layout()
    viol_plot_path = subdirs["violation_rates"] / "violation_rates_before_after_rollback.png"
    fig.savefig(viol_plot_path)
    fig.savefig(out_dir / "violation_rates_before_after_rollback.png")
    plt.close(fig)

    # ----------------------------------------------------------------------- #
    # Part 6: Agent Ablation with Rollback on Original Benchmark
    # ----------------------------------------------------------------------- #
    print("Evaluating Agent Ablation with Rollback on Original Benchmark (69 expressions)...")
    ablation_rows = []
    ablation_obj_rows = []
    used_files = {}
    for agent_label in ABLATION_AGENTS:
        df_agent, wb_p = load_results(source, agent_label, "original", args.data_dir, args.unified_dir, required=False)
        if df_agent is None:
            continue
        used_files[agent_label] = wb_p
        within_df = df_agent[df_agent["Is Feasible"]]

        b_map = {}
        for b in ALL_BUDGETS:
            sub = within_df[within_df["Budget"] == b]
            b_map[b] = float(sub["Safe Cost Reduction (%)"].mean())

        avg_safe_cr = float(np.mean([b_map[b] for b in ALL_BUDGETS]))
        safe_viols = int(within_df["Safe Violated"].sum())
        total_within = len(within_df)
        viol_pct = safe_viols / total_within * 100.0

        ablation_rows.append({
            "Agent": agent_label,
            "B=230 Safe CR%": round(b_map[230], 2),
            "B=236 Safe CR%": round(b_map[236], 2),
            "B=369 Safe CR%": round(b_map[369], 2),
            "B=9M Safe CR%": round(b_map[9_000_000], 2),
            "Average Safe CR%": round(avg_safe_cr, 2),
            "Safe Violations": f"{safe_viols} ({viol_pct:.1f}%)",
        })
        if om.has_objectives(df_agent):
            ablation_obj_rows.append(safe_objectives_row(agent_label, df_agent, ALL_BUDGETS))

    ablation_df = pd.DataFrame(ablation_rows)
    ablation_csv = subdirs["original_benchmark_ablation"] / "safe_cr_ablation_original_benchmark.csv"
    ablation_df.to_csv(ablation_csv, index=False)
    ablation_df.to_csv(out_dir / "safe_cr_ablation_original_benchmark.csv", index=False)
    print(f"  Ablation Table (Original Benchmark + Rollback):\n{ablation_df.to_string(index=False)}")
    print()

    ablation_obj_df = None
    if ablation_obj_rows and len(ablation_obj_rows) == len(ablation_rows):
        ablation_obj_df = pd.DataFrame(ablation_obj_rows)
        p = subdirs["original_benchmark_ablation"] / "safe_objectives_ablation_original_benchmark.csv"
        ablation_obj_df.to_csv(p, index=False)
        ablation_obj_df.to_csv(out_dir / "safe_objectives_ablation_original_benchmark.csv", index=False)
        for target in (subdirs["original_benchmark_ablation"] / "original_benchmark_safe_objectives_ablation.png",
                       out_dir / "original_benchmark_safe_objectives_ablation.png"):
            om.plot_objectives_by_budget(
                ablation_obj_df, [BUDGET_LABEL[b] for b in ALL_BUDGETS], "Agent",
                "B={b} " + EXEC_LABEL, "B={b} avg keys",
                "Agent Ablation with Rollback: Exec Cost and Rotation Keys (Original Benchmark, Within Budget)",
                target, highlight=CONSTRAINED_NAME)
        print(f"  Safe exec cost reduction (%) / avg rotation keys:\n{compact(ablation_obj_df, ALL_BUDGETS).to_string(index=False)}")
        print()

    # Plot Ablation Safe CR%
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
    agent_names = ablation_df["Agent"].tolist()
    y_pos = np.arange(len(agent_names))
    cr_values = ablation_df["Average Safe CR%"].tolist()
    bar_colors = ["#4C72B0" if a != CONSTRAINED_NAME else "#D95F02" for a in agent_names]

    bars = ax.barh(y_pos, cr_values, color=bar_colors, edgecolor="black", height=0.6)
    for bar in bars:
        w = bar.get_width()
        ax.annotate(f"{w:.2f}%", xy=(w, bar.get_y() + bar.get_height()/2), xytext=(5, 0),
                    textcoords="offset points", ha="left", va="center", fontsize=10, fontweight="bold")

    ax.set_yticks(y_pos)
    ax.set_yticklabels(agent_names, fontsize=11)
    ax.set_xlabel("Average Safe Cost Reduction (%) across Budgets", fontsize=12)
    ax.set_title("Agent Ablation: Safe Cost Reduction on Original Benchmark with Rollback", fontsize=13, fontweight="bold", pad=12)
    ax.set_xlim(0, max(90, max(cr_values) * 1.12))
    ax.grid(True, linestyle=":", alpha=0.6, axis="x")
    plt.tight_layout()
    ablation_plot_path = subdirs["original_benchmark_ablation"] / "original_benchmark_safe_cr_ablation.png"
    fig.savefig(ablation_plot_path)
    fig.savefig(out_dir / "original_benchmark_safe_cr_ablation.png")
    plt.close(fig)

    # ----------------------------------------------------------------------- #
    # Part 6b: Measured on SEAL with rollback (47 C++ benchmark instances)
    # ----------------------------------------------------------------------- #
    agent_order = list(ABLATION_AGENTS)
    seal_frames = {k: om.load_seal(args.seal_dir / SEAL_MODE, k) for k in agent_order}
    seal_frames = {k: v for k, v in seal_frames.items() if v is not None}
    seal_df = seal_pref_df = None
    if seal_frames:
        print(f"Measured on SEAL ({SEAL_MODE}): {', '.join(f'{k} ({len(v)} rows)' for k, v in seal_frames.items())}")
        seal_dir_out = out_dir / "seal_measured"
        seal_dir_out.mkdir(parents=True, exist_ok=True)
        seal_df = om.seal_budget_table(seal_frames, agent_order, ALL_BUDGETS, BUDGET_LABEL,
                                       UNCONSTRAINED_NAME, within_only=True)
        seal_df.to_csv(out_dir / "seal_measured.csv", index=False, float_format="%.4f")
        seal_df.to_csv(seal_dir_out / "summary.csv", index=False, float_format="%.4f")
        om.seal_long_table(seal_frames, agent_order, ALL_BUDGETS, BUDGET_LABEL, within_only=True).to_csv(
            seal_dir_out / "per_budget.csv", index=False, float_format="%.4f")
        om.seal_preference_table(seal_frames, list(seal_frames), ALL_BUDGETS, within_only=True).to_csv(
            seal_dir_out / "per_preference.csv", index=False, float_format="%.4f")
        pd.concat([v.assign(Agent=k) for k, v in seal_frames.items()], ignore_index=True).to_csv(
            seal_dir_out / "per_point.csv", index=False)
        seal_pref_df = om.seal_preference_table(
            seal_frames, [a for a in (UNCONSTRAINED_NAME, CONSTRAINED_NAME) if a in seal_frames], ALL_BUDGETS,
            within_only=True)
        for target in (seal_dir_out / "seal_measured.png", out_dir / "seal_measured.png"):
            om.plot_objectives_by_budget(
                seal_df, [BUDGET_LABEL[b] for b in ALL_BUDGETS], "Agent", "B={b} " + om.TIME_LABEL,
                "B={b} " + om.KEYSIZE_LABEL,
                "Measured on SEAL with Rollback: Circuit Execution Time and Rotation-Key Size (Within Budget)",
                target, highlight=CONSTRAINED_NAME,
                ylabels=("Mean circuit execution time (ms)", "Mean rotation-key size (MB)"))
        print(f"  time / key size / measured violation:\n"
              f"{om.seal_compact(seal_df, [BUDGET_LABEL[b] for b in ALL_BUDGETS], UNCONSTRAINED_NAME).to_string(index=False)}")
        print()
    else:
        print(f"No SEAL results in {args.seal_dir / SEAL_MODE / 'raw'} (measured section skipped)")

    # ----------------------------------------------------------------------- #
    # Part 7: Write Markdown Summary Report & Metadata
    # ----------------------------------------------------------------------- #
    n_pref = df_thresh.groupby(om.PREF_COLS).ngroups if has_pref else 1
    elapsed_total = time.perf_counter() - t_start
    report_path = out_dir / "exp3_results.md"
    with open(report_path, "w", encoding="utf-8") as rf:
        rf.write("# Experiment 3: Safety Rollback & Synthetic Near-Threshold Benchmark\n\n")
        rf.write(f"**Execution Timestamp:** {datetime.now(timezone.utc).isoformat()}\n")
        rf.write(f"**Unified Agent Model:** `fheEnvUnified` (RL/fhe_rl/env_unified.py)\n")
        rf.write(f"**Result Source:** {source} (`{data_dir}`)"
                 + (f", {ABLATION} ablation agents" if source == "unified" else "") + "\n")
        if n_pref > 1:
            rf.write(f"**Preferences:** {n_pref} per expression; rates and averages are over expressions x preferences\n")
        rf.write(f"**Total Runtime:** {elapsed_total:.2f} seconds\n\n")

        rf.write("## 1. Synthetic Near-Threshold Dataset Composition\n\n")
        rf.write(df_to_markdown(df_comp))
        rf.write("\n\n")
        if dataset_match is not None:
            rf.write(f"- Regenerated set (seed {args.seed}) "
                     f"{'is identical to' if dataset_match else '**differs from**'} "
                     "`RL/fhe_rl/datasets/threshold_benchmarks.txt`, the set the agents were evaluated on.\n\n")

        rf.write("## 2. Trajectory Rollback Audit Verification\n\n")
        rf.write(f"- **Total Episodes Audited:** {total_episodes_audited}\n")
        rf.write(f"- **Mismatches Against Safe Final Output:** {total_mismatches} ({100 * concordance:.2f}% concordance)\n")
        if source == "legacy":
            rf.write("- **Selection Rule:** Lowest-cost intermediate state satisfying `noise <= budget`; fallback to initial expression if infeasible.\n\n")
        else:
            rf.write("- **Selection Rule (unified):** lowest `w_ops*ops/ops0 + w_keys*keys` among states with `noise <= budget` "
                     "and a positive BFV certificate; fallback to the input expression.\n")
            rf.write("- **Audit scope:** trajectories store cost and noise only (no per-step ops/keys or certificates), so the "
                     "audit checks that the safe state is the trajectory state at `Best Valid Step`, within budget or the input "
                     "fallback, and that `Safety Activated` agrees; it does not re-rank the states.\n\n")

        rf.write("## 3. Constrained vs Unconstrained Performance on Threshold Expressions\n\n")
        rf.write(df_to_markdown(cr_compare_df))
        rf.write("\n\n")
        if thr_obj_df is not None:
            rf.write("### Execution Cost and Rotation Keys after Rollback\n\n")
            rf.write(OBJ_EXPLAIN + "\n")
            rf.write(df_to_markdown(compact(thr_obj_df, BUDGETS)))
            rf.write("\n\n![Safe Objectives](safe_objectives_comparison.png)\n\n")
        else:
            rf.write("> [!NOTE]\n> Execution cost and rotation keys are not reported: these legacy results store one scalar "
                     "cost per step. Run `scripts/ablation_unified/eval_*.sbatch` and rerun with `--source unified`.\n\n")
        if thr_pref_sum is not None:
            rf.write("### Preference Trade-off on the Threshold Set (After Rollback)\n\n")
            rf.write("Per preference `w = [w_ops, w_keys]`, averaged over B = 230, 236, 369, within-budget rows.\n\n")
            rf.write(df_to_markdown(thr_pref_sum.round(2)))
            rf.write("\n\n![Preference Trade-off](preference_tradeoff/threshold_preference_tradeoff.png)\n\n")

        rf.write("## 4. Violation Rates Before and After Rollback (Within-Budget Expressions)\n\n")
        rf.write(df_to_markdown(viol_df))
        rf.write("\n\n")

        rf.write("## 5. Agent Ablation with Rollback on Original Benchmark\n\n")
        rf.write(df_to_markdown(ablation_df))
        rf.write("\n")
        if ablation_obj_df is not None:
            rf.write("\n### Execution Cost and Rotation Keys after Rollback\n\n")
            rf.write(OBJ_EXPLAIN + "\n")
            rf.write(df_to_markdown(compact(ablation_obj_df, ALL_BUDGETS)))
            rf.write("\n\n![Ablation Objectives](original_benchmark_safe_objectives_ablation.png)\n")

        rf.write("\n## 6. Measured on SEAL: Execution Time and Rotation-Key Size (With Rollback)\n\n")
        if seal_df is not None:
            rf.write(
                "Real execution of the compiled programs on SEAL/BFV with the safety rollback on "
                "(`CHEHAB_RL_ROLLBACK=1`): every agent compiles the 47 non-DNN C++ benchmark instances "
                f"(`unified_morl_experiments.py sweep --experiments ABL4`, results in `{args.seal_dir / SEAL_MODE}`) "
                "for every budget and its 4 training preferences; initially within-budget points only "
                "(estimated initial noise <= B). Each cell is `mean circuit execution time / mean rotation-key size "
                "(Galois keys, `save_size`) / measured violation rate`; a measured violation is "
                "`369 - remaining noise budget > B` or a remaining budget <= 0, so it checks the rollback against "
                "the real noise. `Time vs Unconstrained` is the geometric mean, over the points both agents "
                "executed, of the time ratio (< 1 = faster). Different benchmark set from the 69 VecLang "
                "expressions of section 5.\n\n")
            rf.write(df_to_markdown(om.seal_compact(seal_df, [BUDGET_LABEL[b] for b in ALL_BUDGETS],
                                                    UNCONSTRAINED_NAME)))
            rf.write("\n\n![Measured](seal_measured.png)\n\n")
            if seal_pref_df is not None and not seal_pref_df.empty:
                rf.write("### Measured per Preference (all budgets, within budget)\n\n")
                rf.write(df_to_markdown(seal_pref_df.round(2)))
                rf.write("\n")
        else:
            rf.write("> [!NOTE]\n"
                     f"> No SEAL results in `{args.seal_dir / SEAL_MODE}/raw/`. Run "
                     "`sbatch --export=ALL,ROLLBACK=1 scripts/ablation_unified/seal_sweep_4pref.sbatch` "
                     "(or `bash scripts/ablation_unified/launch_4pref_eval.sh`) and rerun.\n")

    metadata = {
        "experiment": "Experiment 3 - Safety Rollback & Synthetic Near-Threshold Benchmark",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed_total, 2),
        "platform": platform.platform(),
        "python_version": sys.version,
        "torch_version": torch.__version__,
        "agent": "fheEnvUnified (4th RL Agent - Multi-Objective + Noise Constraint)",
        "result_source": source,
        "ablation": ABLATION if source == "unified" else None,
        "preferences_per_expression": n_pref,
        "seal_measured": ({"dir": str(args.seal_dir / SEAL_MODE), "agents": {k: len(v) for k, v in seal_frames.items()},
                           "subset": "initially within budget (initial_est_noise <= B)",
                           "time": "circuit_execution_time_s (reported in ms)", "key_size": "rotation_keys_size_mb"}
                          if seal_frames else "no results"),
        "objectives": ({"exec_cost": "Safe Final Ops (C_exec, exec_cost_mo); reported as reduction vs Initial Ops",
                        "rotation_keys": "Safe Final Keys (C_keys, unique rotation keys); reported as mean count"}
                       if has_obj else "not available in these results"),
        "synthetic_benchmark": {
            "expressions_count": len(thresh_entries),
            "seed": args.seed,
            "budgets": BUDGETS,
            "matches_dataset_file": dataset_match,
        },
        "audit": {
            "mode": source,
            "total_episodes": total_episodes_audited,
            "mismatches": total_mismatches,
            "concordance_rate": round(concordance, 6),
        },
        "threshold_safe_cr": {
            "constrained_lagpid_avg": round(lag_avg, 2),
            "unconstrained_avg": round(unc_avg, 2),
            "advantage_pp": round(adv_avg, 2),
        },
        "original_ablation_lagpid_safe_cr_avg": round(float(ablation_df.loc[ablation_df["Agent"] == CONSTRAINED_NAME, "Average Safe CR%"].values[0]), 2),
        "result_files": {
            "threshold": {CONSTRAINED_NAME: str(thresh_path), UNCONSTRAINED_NAME: str(unc_thresh_path)},
            "original": {k: str(v) for k, v in used_files.items()},
        },
    }
    if thr_obj_df is not None:
        metadata["threshold_safe_objectives"] = thr_obj_df.to_dict(orient="records")
    if ablation_obj_df is not None:
        metadata["original_ablation_safe_objectives"] = ablation_obj_df.to_dict(orient="records")
    with open(out_dir / "run_metadata.json", "w", encoding="utf-8") as mf:
        json.dump(metadata, mf, indent=2)

    print("=" * 78)
    print("  EXPERIMENT 3 REPRODUCTION COMPLETED SUCCESSFULLY (Exit Code 0)")
    print(f"  Total Runtime : {elapsed_total:.2f}s")
    print(f"  Summary Report: {report_path.name}")
    print(f"  Metadata JSON : run_metadata.json")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())

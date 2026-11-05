#!/usr/bin/env python3
"""Experiment 2 - Constrained vs Unconstrained RL Agent.

This script reproduces Experiment 2 using the unified RL environment with noise
constraint (RL/fhe_rl/env_unified.py, fheEnvUnified) directly from its repository
location.

Execution:
    python experiments_reproduction/experiment_2/run_experiment_2.py [--source auto|unified|legacy]

Methodology:
    1. Instantiates `fheEnvUnified` directly from `RL/fhe_rl/env_unified.py` with
       `constraint_metric='noise'` and the 69 benchmark expressions
       (`RL/fhe_rl/datasets/benchmarks.txt`).
    2. Computes the ground-truth initial state for each expression across budgets
       B in {230, 236, 369, 9_000_000}:
           initial_cost = env.initial_cost (ops + keys)
           initial_noise = env.initial_constraint (estimated noise in bits via NoiseEstimator)
           is_feasible = (initial_noise <= budget)
    3. Evaluates agent performance without safety rollback (raw final episode-step result):
           Agent Cost Reduction (%) = 100.0 * (Initial Cost - Agent Final Cost) / Initial Cost
           Agent Violated = (Agent Final Noise > Budget)
    4. Evaluates all parts:
           - Constrained (Lag-PID + NATO-SC) vs Unconstrained (all 69 expressions)
           - Initial budget status partition & within-budget violation analysis
           - Optimization quality on initially within-budget expressions
           - Constraint-method ablation across 6 methods
           - The two MORL objectives for every part above (when the results have them):
                 Exec cost reduction (%) = 100 * (Initial Ops - Agent Final Ops) / Initial Ops
                     (Ops = C_exec = exec_cost_mo, the execution-time cost model)
                 Rotation keys           = Agent Final Keys (C_keys = unique rotation keys)
             plus a per-preference breakdown (w_ops, w_keys) for the unified agents.
    5. Outputs structured CSV files (subfolders & summaries), plots,
       exp2_results.md, and run_metadata.json with descriptive experiment names
       (no 2A/2B/etc. prefixes).

Result sources (--source):
    unified  results/ablation_unified/<agent>/eval_<jobid>/original.csv, written by
             scripts/ablation_unified/eval_*.sbatch (`fhe_rl test --test_mode v2`):
             exec/keys split and 10 preferences per expression.
    legacy   hpc_results/rl_test_results/original_<tag>.xlsx (older runs: one scalar
             cost, no exec/keys split; the objective tables are then skipped).
    auto     unified when results exist for all 6 agents, else legacy (default).

Exit codes: 0 ok | 1 unexpected error | 2 data/validation error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

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
REPO_ROOT = HERE.parents[1]  # experiments_reproduction/experiment_2 -> repo root
RL_DIR = REPO_ROOT / "RL"
PYTRS_DIR = RL_DIR / "pytrs"

for p in [str(RL_DIR), str(PYTRS_DIR), str(HERE.parent)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Import unified environment & pytrs rules directly from source locations
try:
    from fhe_rl.env_unified import fheEnvUnified
    from pytrs import create_rules
except ImportError as exc:
    print(f"ERROR: Failed to import RL modules: {exc}", file=sys.stderr)
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
DEFAULT_BENCHMARK = RL_DIR / "fhe_rl" / "datasets" / "benchmarks.txt"
DEFAULT_OUT = HERE / "outputs"

BUDGETS = [230, 236, 369, 9_000_000]
BUDGET_LABEL = {230: "230", 236: "236", 369: "369", 9_000_000: "9M"}
BUDGET_LBLS = [BUDGET_LABEL[b] for b in BUDGETS]
N_EXPR = 69
MANUSCRIPT_LAGPID_AVG_CR = 60.87  # PFE value; only compared for the legacy results

AGENT_CONFIG = {
    "legacy": {
        "Unconstrained": "prior-work agent agent_dynamic_llm_data.zip, budget-unaware, evaluated post hoc",
        "V4 Margin Barrier": "--method margin_barrier, encoding raw",
        "V4 Noise Masking": "--method noise_masking, encoding embed",
        "V4 MB + FiLM": "--method margin_barrier, encoding film",
        "V5 FOCOPS + NATO-SC": "--method nato_sc, algo focops, film",
        "V5 Lag-PID + NATO-SC": "--method nato_sc, algo lagrangian_pid, film (selected)",
    },
    "unified": {
        "Unconstrained": "unified agent trained without the constraint (ablation_unified/train_unconstrained.sbatch)",
        "V4 Margin Barrier": "unified, --method margin_barrier, encoding raw",
        "V4 Noise Masking": "unified, --method noise_masking, encoding embed",
        "V4 MB + FiLM": "unified, --method margin_barrier, encoding film",
        "V5 FOCOPS + NATO-SC": "unified, --method nato_sc, algo focops, film",
        "V5 Lag-PID + NATO-SC": "unified reference unified_joint_noise_best_4.0M.zip (nato_sc, lagrangian_pid, film)",
    },
}
AGENTS = list(AGENT_CONFIG["legacy"])
UNC = "Unconstrained"
CON = "V5 Lag-PID + NATO-SC"
CON_LABEL = "Constrained (Lag-PID + NATO-SC)"

REQUIRED_COLS = [
    "Budget", "Expression #", "Is Feasible", "Initial Cost", "Initial Noise",
    "Agent Final Cost", "Agent Final Noise", "Agent Cost Reduction (%)", "Agent Violated",
]
OPTIONAL_COLS = om.OBJECTIVE_COLS + om.PREF_COLS + [
    "Expression Name", "Agent Ops Reduction (%)", "Safe Ops Reduction (%)",
]


class DataError(Exception):
    """Input data failed a validation check (exit code 2)."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def df_to_md(df: pd.DataFrame, floatfmt: str = "{:.2f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for tup in df.itertuples(index=False, name=None):
        cells = []
        for v in tup:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else float("nan")


# --------------------------------------------------------------------------- #
# Unified Model Integration
# --------------------------------------------------------------------------- #
def load_benchmark_expressions(benchmark_file: Path) -> list[str]:
    if not benchmark_file.is_file():
        raise DataError(f"Benchmark file not found: {benchmark_file}")
    with open(benchmark_file, "r", encoding="utf-8") as f:
        exprs = [line.strip().split(":")[0] for line in f if line.strip()]
    if len(exprs) != N_EXPR:
        raise DataError(f"Expected {N_EXPR} benchmark expressions, got {len(exprs)}")
    return exprs


def init_unified_env(expressions: list[str]) -> fheEnvUnified:
    """Initialize fheEnvUnified configured with noise constraint metric."""
    rules_p = str(RL_DIR / "rules.txt")
    rot_p = str(RL_DIR / "rotations_rules.txt")
    rules_list = create_rules(rules_p, rot_p if os.path.exists(rot_p) else None)
    rules_list["END"] = None

    env = fheEnvUnified(
        rules_list=rules_list,
        expressions=expressions,
        max_positions=16,
        embeddings_model=None,
        budget_options=BUDGETS,
        constraint_method="nato_sc",
        constraint_metric="noise",
        verbose=False,
    )
    return env


def evaluate_initial_expressions_with_unified_model(
    env: fheEnvUnified, expressions: list[str]
) -> pd.DataFrame:
    """Compute ground-truth initial cost and noise constraint directly with fheEnvUnified."""
    rows = []
    for b in BUDGETS:
        for idx, expr in enumerate(expressions):
            env.reset(options={"expression": expr, "budget": b})
            c0 = float(env.initial_cost)
            n0 = float(env.initial_constraint)
            rows.append({
                "Budget": b,
                "Expression #": idx + 1,
                "Expression": expr,
                "Initial Cost": c0,
                "Initial Noise": n0,
                "Is Feasible": (n0 <= b),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Loading & Validating Agent Evaluation Results
# --------------------------------------------------------------------------- #
def load_agent(
    source: str, results_dir: Path, unified_dir: Path, label: str,
    unified_baseline: pd.DataFrame, expressions: list[str],
) -> tuple[pd.DataFrame, Path, float]:
    """Load one agent's results on the original benchmark. Returns (frame, path, max noise diff)."""
    try:
        path = om.agent_file(source, label, "original", results_dir, unified_dir)
    except om.SourceError as exc:
        raise DataError(f"[{label}] {exc}")
    if not path.is_file():
        raise DataError(f"[{label}] results not found: {path} (use --results-dir / --unified-dir)")
    df = om.read_results(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise DataError(f"[{label}] missing columns {missing} in {path.name}")
    df = df[REQUIRED_COLS + [c for c in OPTIONAL_COLS if c in df.columns]].copy()

    got = sorted(df["Budget"].unique().tolist())
    if got != sorted(BUDGETS):
        raise DataError(f"[{label}] budgets {got}, expected {sorted(BUDGETS)}")
    n_pref = df.groupby(om.PREF_COLS).ngroups if om.has_preferences(df) else 1
    for b in BUDGETS:
        sub = df[df["Budget"] == b]
        if sub["Expression #"].nunique() != N_EXPR or len(sub) != N_EXPR * n_pref:
            raise DataError(f"[{label}] budget {b}: {len(sub)} rows / {sub['Expression #'].nunique()} expressions, "
                            f"expected {N_EXPR} expressions x {n_pref} preference(s)")
    if df[REQUIRED_COLS].isna().any().any():
        raise DataError(f"[{label}] missing values in required columns")

    # Cross-validate the initial states against the unified model baseline
    max_noise_diff = 0.0
    first = df.drop_duplicates(["Budget", "Expression #"])
    for b in BUDGETS:
        u_sub = unified_baseline[unified_baseline["Budget"] == b]
        d_sub = first[first["Budget"] == b]
        if source == "legacy":
            # one scalar cost per expression: (cost, noise) pairs must match
            u_sorted = sorted(zip(u_sub["Initial Cost"].round(2), u_sub["Initial Noise"].round(2)))
            d_sorted = sorted(zip(d_sub["Initial Cost"].round(2), d_sub["Initial Noise"].round(2)))
            if u_sorted != d_sorted:
                raise DataError(f"[{label}] initial states for budget {b} disagree with fheEnvUnified baseline")
        u_noise = np.sort(u_sub["Initial Noise"].to_numpy(float))
        d_noise = np.sort(d_sub["Initial Noise"].to_numpy(float))
        diff = float(np.abs(u_noise - d_noise).max())
        if diff > 0.011:
            raise DataError(f"[{label}] initial noise for budget {b} disagrees with fheEnvUnified (max diff {diff:.3f} bits)")
        max_noise_diff = max(max_noise_diff, diff)

    # Consistency checks: recalculate violation and cost reduction
    if (df["Agent Violated"] != (df["Agent Final Noise"] > df["Budget"])).any():
        raise DataError(f"[{label}] `Agent Violated` disagrees with Agent Final Noise > Budget")
    cr = 100.0 * (df["Initial Cost"] - df["Agent Final Cost"]) / df["Initial Cost"]
    if (cr - df["Agent Cost Reduction (%)"]).abs().max() > 0.011:
        raise DataError(f"[{label}] `Agent Cost Reduction (%)` disagrees with raw cost formula (>0.011 pts)")
    if (df["Is Feasible"].astype(bool) != (df["Initial Noise"] <= df["Budget"])).any():
        raise DataError(f"[{label}] `Is Feasible` disagrees with Initial Noise <= Budget")
    problems = om.check_objectives(df, label, expressions if source == "unified" else None)
    if problems:
        raise DataError("; ".join(problems))
    return df, path, max_noise_diff


# --------------------------------------------------------------------------- #
# Subpart Computation
# --------------------------------------------------------------------------- #
def get_stats(df: pd.DataFrame, budget: int, within_only: bool = False) -> dict:
    sub = df[df["Budget"] == budget]
    if within_only:
        sub = sub[sub["Initial Noise"] <= budget]
    n = len(sub)
    viol = int(sub["Agent Violated"].sum())
    obj = om.objective_stats(sub, "Agent")
    return {
        "n": n,
        "n_expr": int(sub["Expression #"].nunique()),
        "cr": float(sub["Agent Cost Reduction (%)"].mean()) if n else float("nan"),
        "viol": viol,
        "viol_rate": pct(viol, n),
        "exec_red": obj["exec_red"],
        "keys": obj["keys"],
        "zero_keys_pct": obj["zero_keys_pct"],
    }


def compute_agent_comparison(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for b in BUDGETS:
        for label, shown in ((UNC, UNC), (CON, CON_LABEL)):
            s = get_stats(frames[label], b)
            rows.append({
                "Agent": shown,
                "Budget": BUDGET_LABEL[b],
                "Average CR%": s["cr"],
                "Violation count": s["viol"],
                "Violation rate (%)": s["viol_rate"],
            })
    return pd.DataFrame(rows)


def compute_initial_budget_partition(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for b in BUDGETS:
        base = frames[CON][frames[CON]["Budget"] == b].drop_duplicates("Expression #")
        total = len(base)
        n_in = int((base["Initial Noise"] <= b).sum())
        n_out = total - n_in
        u = get_stats(frames[UNC], b, within_only=True)
        c = get_stats(frames[CON], b, within_only=True)
        rows.append({
            "Budget": BUDGET_LABEL[b],
            "Total expressions": total,
            "Initially within budget: count": n_in,
            "Initially within budget: %": pct(n_in, total),
            "Initially above budget: count": n_out,
            "Initially above budget: %": pct(n_out, total),
            "Within-budget violations, unconstrained: count": u["viol"],
            "Within-budget violations, unconstrained: %": u["viol_rate"],
            "Within-budget violations, constrained: count": c["viol"],
            "Within-budget violations, constrained: %": c["viol_rate"],
        })
    return pd.DataFrame(rows)


def compute_violations_by_initial_status(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for label, shown in ((UNC, UNC), (CON, CON_LABEL)):
        for b in BUDGETS:
            sub = frames[label][frames[label]["Budget"] == b]
            viol = sub[sub["Agent Violated"]]
            above = int((viol["Initial Noise"] > b).sum())
            rows.append({
                "Agent": shown,
                "Budget": BUDGET_LABEL[b],
                "All violations": len(viol),
                "of which initially above budget": above,
                "of which initially within budget": len(viol) - above,
            })
    return pd.DataFrame(rows)


def compute_within_budget_quality(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for label, shown in ((UNC, UNC), (CON, CON_LABEL)):
        row = {"Agent": shown}
        for b in BUDGETS:
            row[f"B={BUDGET_LABEL[b]} CR%"] = get_stats(frames[label], b, within_only=True)["cr"]
        rows.append(row)
    n_row = {"Agent": "(expressions in subset)"}
    for b in BUDGETS:
        n_row[f"B={BUDGET_LABEL[b]} CR%"] = float(get_stats(frames[CON], b, within_only=True)["n_expr"])
    rows.append(n_row)
    return pd.DataFrame(rows)


def compute_constraint_ablation(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for label in AGENTS:
        row = {"Agent / method": label}
        vals = []
        for b in BUDGETS:
            v = get_stats(frames[label], b)["cr"]
            row[f"B={BUDGET_LABEL[b]} CR%"] = v
            vals.append(v)
        row["Average CR%"] = float(np.mean(vals))
        rows.append(row)
    return pd.DataFrame(rows)


def compute_ablation_violations(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for label in AGENTS:
        row = {"Agent / method": label}
        for b in BUDGETS:
            row[f"B={BUDGET_LABEL[b]} violations"] = get_stats(frames[label], b)["viol"]
        rows.append(row)
    return pd.DataFrame(rows)


# ---- MORL objectives: exec cost (C_exec) and rotation keys (C_keys) ---------- #
def compute_objectives_table(frames: dict[str, pd.DataFrame], labels: list[tuple[str, str]],
                             within_only: bool = False) -> pd.DataFrame:
    """Per agent: exec-cost reduction and avg rotation keys for every budget, plus averages."""
    rows = []
    for label, shown in labels:
        row = {"Agent": shown}
        ex, ks = [], []
        for b in BUDGETS:
            s = get_stats(frames[label], b, within_only=within_only)
            row[f"B={BUDGET_LABEL[b]} {EXEC_LABEL}"] = s["exec_red"]
            row[f"B={BUDGET_LABEL[b]} avg keys"] = s["keys"]
            ex.append(s["exec_red"])
            ks.append(s["keys"])
        row[f"Average {EXEC_LABEL}"] = float(np.mean(ex))
        row["Average keys"] = float(np.mean(ks))
        rows.append(row)
    return pd.DataFrame(rows)


def compute_objectives_long(frames: dict[str, pd.DataFrame], labels: list[tuple[str, str]],
                            within_only: bool = False) -> pd.DataFrame:
    """Long form of the objectives with the constraint metrics next to them."""
    rows = []
    for label, shown in labels:
        for b in BUDGETS:
            s = get_stats(frames[label], b, within_only=within_only)
            rows.append({
                "Agent": shown, "Budget": BUDGET_LABEL[b], "Rows (expr x pref)": s["n"],
                "Expressions": s["n_expr"], "Average CR%": s["cr"],
                EXEC_LABEL: s["exec_red"], f"Avg {KEYS_LABEL}": s["keys"],
                "Zero-key rows (%)": s["zero_keys_pct"],
                "Violation count": s["viol"], "Violation rate (%)": s["viol_rate"],
            })
    return pd.DataFrame(rows)


def compact_objectives(t_obj: pd.DataFrame) -> pd.DataFrame:
    """'exec% / keys' cells per budget, for the markdown report."""
    rows = []
    for _, r in t_obj.iterrows():
        row = {"Agent": r["Agent"]}
        for b in BUDGET_LBLS:
            row[f"B={b}"] = f"{r[f'B={b} {EXEC_LABEL}']:.2f}% / {r[f'B={b} avg keys']:.2f}"
        row["Average"] = f"{r[f'Average {EXEC_LABEL}']:.2f}% / {r['Average keys']:.2f}"
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Plotting Functions
# --------------------------------------------------------------------------- #
def plot_violation_rates(t_comp: pd.DataFrame, out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    budgets = ["230", "236", "369", "9M"]
    x = np.arange(len(budgets))
    width = 0.35

    unc_vals = [t_comp[(t_comp["Agent"] == UNC) & (t_comp["Budget"] == b)]["Violation rate (%)"].values[0] for b in budgets]
    con_vals = [t_comp[(t_comp["Agent"] == CON_LABEL) & (t_comp["Budget"] == b)]["Violation rate (%)"].values[0] for b in budgets]

    rects1 = ax.bar(x - width/2, unc_vals, width, label="Unconstrained", color="#4C72B0")
    rects2 = ax.bar(x + width/2, con_vals, width, label="Constrained (Lag-PID + NATO-SC)", color="#DD8452")

    ax.set_ylabel("Violation Rate (%)", fontsize=11)
    ax.set_xlabel("Noise Budget (bits)", fontsize=11)
    ax.set_title("Violation Rate by Budget (Raw Agent Output, No Rollback)", fontsize=13, pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(budgets)
    ax.set_ylim(0, max(50, float(np.nanmax(unc_vals + con_vals)) * 1.15))
    ax.legend(frameon=True)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for rects in [rects1, rects2]:
        for rect in rects:
            height = rect.get_height()
            if height > 0:
                ax.annotate(f"{height:.1f}%",
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points",
                            ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(str(out_path), bbox_inches="tight", dpi=200)
    plt.close(fig)
    return out_path


def plot_within_budget_cr(t_wb: pd.DataFrame, out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    budgets = ["230", "236", "369", "9M"]
    x = np.arange(len(budgets))
    width = 0.35

    unc_row = t_wb[t_wb["Agent"] == UNC].iloc[0]
    con_row = t_wb[t_wb["Agent"] == CON_LABEL].iloc[0]

    unc_vals = [unc_row[f"B={b} CR%"] for b in budgets]
    con_vals = [con_row[f"B={b} CR%"] for b in budgets]

    rects1 = ax.bar(x - width/2, unc_vals, width, label="Unconstrained", color="#4C72B0")
    rects2 = ax.bar(x + width/2, con_vals, width, label="Constrained (Lag-PID + NATO-SC)", color="#55A868")

    ax.set_ylabel("Cost Reduction (%)", fontsize=11)
    ax.set_xlabel("Noise Budget (bits)", fontsize=11)
    ax.set_title("Cost Reduction on Initially Within-Budget Expressions", fontsize=13, pad=12)
    ax.set_xticks(x)
    ax.set_xticklabels(budgets)
    ax.set_ylim(0, 100)
    ax.legend(frameon=True)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    for rects in [rects1, rects2]:
        for rect in rects:
            height = rect.get_height()
            ax.annotate(f"{height:.1f}%",
                        xy=(rect.get_x() + rect.get_width() / 2, height),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=9)

    plt.tight_layout()
    plt.savefig(str(out_path), bbox_inches="tight", dpi=200)
    plt.close(fig)
    return out_path


def plot_ablation(t_abl: pd.DataFrame, out_path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    methods = t_abl["Agent / method"].tolist()
    y_pos = np.arange(len(methods))
    avg_crs = t_abl["Average CR%"].tolist()

    colors = ["#4C72B0" if m == UNC else ("#DD8452" if m == CON else "#8172B2") for m in methods]
    bars = ax.barh(y_pos, avg_crs, align="center", color=colors, height=0.6)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(methods, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("Average Cost Reduction (%) Across All Budgets", fontsize=11)
    ax.set_title("Constraint-Method Ablation (All 69 Expressions, Raw Output)", fontsize=13, pad=12)
    ax.set_xlim(0, max(75, float(np.nanmax(avg_crs)) * 1.15))
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    for bar in bars:
        width = bar.get_width()
        ax.annotate(f"{width:.2f}%",
                    xy=(width, bar.get_y() + bar.get_height() / 2),
                    xytext=(5, 0), textcoords="offset points",
                    ha="left", va="center", fontsize=9, weight="bold")

    plt.tight_layout()
    plt.savefig(str(out_path), bbox_inches="tight", dpi=200)
    plt.close(fig)
    return out_path


# --------------------------------------------------------------------------- #
# Report Builder
# --------------------------------------------------------------------------- #
OBJ_EXPLAIN = (
    "Each cell is `exec cost reduction (%) / average rotation keys`. "
    "Exec cost = `C_exec` (`exec_cost_mo`, the execution-time cost model: ops + rotations + depths), "
    "reduction = `100 * (Initial Ops - Agent Final Ops) / Initial Ops` (higher is better). "
    "Rotation keys = `C_keys`, the number of unique rotation (Galois) keys of the final program "
    "(lower is better; every benchmark expression starts scalar with 0 keys, so the count is reported, not a reduction). "
    "Both are cost-model values, not measured SEAL run times or key sizes. "
    "Values are means over expressions x preferences.\n"
)


def build_report(ctx: dict) -> str:
    unified = ctx["source"] == "unified"
    L = ["# Experiment 2: Constrained vs Unconstrained RL Agent — Reproduction Report\n"]
    L.append(
        "Generated by `run_experiment_2.py` integrating the unified model with noise constraint "
        "(`RL/fhe_rl/env_unified.py`, `fheEnvUnified`) and evaluating the benchmark results "
        f"from `{ctx['results_rel']}` (source: **{ctx['source']}**). "
        "All 69 VecLang expressions across budgets `230`, `236`, `369`, and `9M`"
        + (f", each at {ctx['n_pref']} preferences `w = [w_ops, w_keys]`" if ctx["n_pref"] > 1 else "")
        + ".\n"
    )
    L.append(
        "> [!IMPORTANT]\n"
        "> **Safety Rollback is Disabled in Experiment 2**: All reported metrics (`Average CR%`, `Violation count`, "
        "exec cost, rotation keys) use the raw final episode-step agent output (`Agent *` columns). "
        "Safety rollback is evaluated separately in Experiment 3.\n"
    )
    if ctx["n_pref"] > 1:
        L.append(
            "> [!NOTE]\n"
            "> Expression counts (partition table) count expressions; violation counts and averages are over "
            f"rows = expressions x {ctx['n_pref']} preferences.\n"
        )
    L.append("## Unified Model & Noise Constraint Verification\n")
    L.append(
        f"- **Environment Class**: `fhe_rl.env_unified.fheEnvUnified`\n"
        f"- **Constraint Metric**: `noise` (`NoiseEstimator` fitting non-negative linear model predicting noise bits)\n"
        f"- **Benchmark Source**: `RL/fhe_rl/datasets/benchmarks.txt` ({N_EXPR} VecLang expressions)\n"
        f"- **Verification**: Initial noise computed via `fheEnvUnified.reset` matches the recorded benchmark states "
        f"(max noise diff = {ctx['max_noise_diff']:.3f} bits)"
        + ("; initial costs match exactly.\n" if not unified else
           "; `Initial Ops` / `Initial Keys` match `split_cost_mo` on the benchmark expressions.\n")
    )
    L.append("## Constrained vs Unconstrained Comparison\n")
    L.append(
        "Evaluation across all 69 expressions for each budget `B ∈ {230, 236, 369, 9M}`.\n"
    )
    L.append(df_to_md(ctx["t_comp"]) + "\n")
    L.append("![Violation Rates](violation_rates.png)\n")

    if ctx["has_obj"]:
        L.append("### Execution Cost and Rotation Keys (all 69 expressions)\n")
        L.append(OBJ_EXPLAIN)
        L.append(df_to_md(compact_objectives(ctx["t_obj_comp"])) + "\n")
        L.append("![Objectives](objectives_constrained_vs_unconstrained.png)\n")
    else:
        L.append(
            "> [!NOTE]\n"
            "> Execution cost and rotation keys are not reported: these legacy results store one scalar cost per step. "
            "Run `scripts/ablation_unified/eval_*.sbatch` (it logs `Agent/Safe Final Ops` and `Keys`) and rerun with "
            "`--source unified`.\n"
        )

    L.append("## Initial Budget Status & Violations Attribution\n")
    L.append(
        "Partition expressions according to initial estimated noise: "
        "`Initially within budget` (initial noise ≤ budget) vs `Initially above budget` (initial noise > budget).\n"
    )
    L.append(df_to_md(ctx["t_part"]) + "\n")
    L.append("### Where Do Full-Benchmark Violations Originate?\n")
    L.append(df_to_md(ctx["t_part_ctx"]) + "\n")
    k = ctx["t_part_ctx"]
    c230 = k[(k["Agent"] == CON_LABEL) & (k["Budget"] == "230")].iloc[0]
    tot_all = int(k["All violations"].sum())
    tot_above = int(k["of which initially above budget"].sum())
    L.append(
        "> [!NOTE]\n"
        f"> **Key Insight**: {pct(tot_above, tot_all):.1f}% of all violations ({tot_above}/{tot_all}) on the full "
        "benchmark come from expressions that were **already above budget prior to optimization** "
        f"(e.g. at B=230, {int(c230['of which initially above budget'])} of the constrained agent's "
        f"{int(c230['All violations'])} violations start above 230 bits; "
        f"{int(c230['of which initially within budget'])} new violations on initially valid expressions).\n"
    )
    L.append("## Cost Reduction on Initially Within-Budget Expressions\n")
    L.append(
        "Restricting evaluation exclusively to expressions initially within budget to test if constraint awareness "
        "harms optimization quality on valid programs (rollback disabled).\n"
    )
    L.append(df_to_md(ctx["t_wb"]) + "\n")
    L.append("![Within-Budget Cost Reduction](within_budget_cost_reduction.png)\n")
    if ctx["has_obj"]:
        L.append("### Execution Cost and Rotation Keys on Initially Within-Budget Expressions\n")
        L.append(OBJ_EXPLAIN)
        L.append(df_to_md(compact_objectives(ctx["t_obj_wb"])) + "\n")
        L.append("![Within-Budget Objectives](objectives_within_budget.png)\n")

    L.append("## Constraint-Method Ablation\n")
    L.append(
        "Comparison of all 6 constraint formulations on the full 69-expression benchmark without rollback.\n"
    )
    L.append(df_to_md(ctx["t_abl"]) + "\n")
    L.append("![Ablation Comparison](ablation_cost_reduction.png)\n")
    L.append("### Supplementary Raw Violation Counts Across Ablated Methods\n")
    L.append(df_to_md(ctx["t_abl_v"]) + "\n")
    if ctx["has_obj"]:
        L.append("### Execution Cost and Rotation Keys Across Ablated Methods\n")
        L.append(OBJ_EXPLAIN)
        L.append(df_to_md(compact_objectives(ctx["t_obj_abl"])) + "\n")
        L.append("![Ablation Objectives](ablation_objectives.png)\n")
    if ctx["has_pref"]:
        L.append("## Preference Trade-off (Exec Cost vs Rotation Keys)\n")
        L.append(
            "Per preference `w = [w_ops, w_keys]`, averaged over the 4 budgets, all 69 expressions, no rollback. "
            "Raising `w_keys` should trade exec cost reduction for fewer rotation keys; "
            "the per-budget values are in `preference_tradeoff/per_budget.csv`.\n"
        )
        L.append(df_to_md(ctx["t_pref_sum"]) + "\n")
        L.append("![Preference Trade-off](preference_tradeoff.png)\n")

    L.append("## Method & Configuration Mapping\n")
    L.append(df_to_md(ctx["cfg"]) + "\n")
    L.append("## Verification Against Manuscript\n")
    if unified:
        L.append(
            "- Not applicable: these are the unified-agent ablation results, the manuscript values come from the "
            "earlier constrained (PFE) agents.\n"
        )
    else:
        con = ctx["t_abl"][ctx["t_abl"]["Agent / method"] == CON].iloc[0]
        wb = ctx["t_wb"][ctx["t_wb"]["Agent"] == "(expressions in subset)"].iloc[0]
        part = ctx["t_part"]
        match = "matching" if abs(con["Average CR%"] - MANUSCRIPT_LAGPID_AVG_CR) < 0.005 else "**not matching**"
        L.append(
            f"- **Average CR% for V5 Lag-PID + NATO-SC**: Computed average is **{con['Average CR%']:.2f}%**, "
            f"{match} the manuscript's reported {MANUSCRIPT_LAGPID_AVG_CR:.2f}%.\n"
            "- **Per-Budget CR%**: " + ", ".join(f"B={b} ({con[f'B={b} CR%']:.2f}%)" for b in BUDGET_LBLS) + ".\n"
            "- **Initially Within-Budget Subset Counts**: "
            + ", ".join(f"B={b} ({int(wb[f'B={b} CR%'])})" for b in BUDGET_LBLS) + ".\n"
            f"- **Within-Budget Violations**: At B=230, constrained agent introduces "
            f"{int(part.iloc[0]['Within-budget violations, constrained: count'])} violations "
            f"({part.iloc[0]['Within-budget violations, constrained: %']:.1f}%).\n"
        )
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def run(args) -> int:
    results_dir = Path(args.results_dir).resolve()
    unified_dir = Path(args.unified_dir).resolve()
    benchmark_file = Path(args.benchmark).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    source = om.resolve_source(args.source, results_dir, unified_dir)
    data_dir = unified_dir if source == "unified" else results_dir
    print(f"[init] Result source: {source} ({data_dir})")

    print(f"[init] Loading benchmark expressions from source: {benchmark_file}...")
    expressions = load_benchmark_expressions(benchmark_file)

    print("[init] Initializing fheEnvUnified directly from RL/fhe_rl/env_unified.py...")
    env = init_unified_env(expressions)
    print(f"       Metric: {env.metric_name} ({env.metric_unit}), Estimator: {type(env.estimator).__name__}")

    print("[unified model] Computing ground-truth initial states for all 69 expressions...")
    unified_baseline = evaluate_initial_expressions_with_unified_model(env, expressions)
    print(f"       Computed {len(unified_baseline)} states (69 expressions x 4 budgets)")

    frames, paths, noise_diffs = {}, {}, []
    for label in AGENTS:
        frames[label], paths[label], d = load_agent(
            source, results_dir, unified_dir, label, unified_baseline, expressions)
        noise_diffs.append(d)
        print(f"[data] {label}: loaded {paths[label].name} ({len(frames[label])} rows)")

    has_obj = all(om.has_objectives(f) for f in frames.values())
    has_pref = has_obj and all(om.has_preferences(f) for f in frames.values())
    n_pref = frames[CON].groupby(om.PREF_COLS).ngroups if has_pref else 1

    t_comp = compute_agent_comparison(frames)
    t_part = compute_initial_budget_partition(frames)
    t_part_ctx = compute_violations_by_initial_status(frames)
    t_wb = compute_within_budget_quality(frames)
    t_abl = compute_constraint_ablation(frames)
    t_abl_v = compute_ablation_violations(frames)
    cfg = pd.DataFrame([{"Label": k, "Result tag": om.AGENT_SOURCES[k][0 if source == "legacy" else 1],
                         "Configuration": AGENT_CONFIG[source][k]} for k in AGENTS])

    pair = [(UNC, UNC), (CON, CON_LABEL)]
    all_agents = [(a, a) for a in AGENTS]
    t_obj_comp = t_obj_wb = t_obj_abl = t_pref = t_pref_sum = None
    if has_obj:
        t_obj_comp = compute_objectives_table(frames, pair)
        t_obj_wb = compute_objectives_table(frames, pair, within_only=True)
        t_obj_abl = compute_objectives_table(frames, all_agents)
    if has_pref:
        t_pref = om.preference_table(frames, [UNC, CON], BUDGETS, BUDGET_LABEL, "Agent")
        t_pref["Agent"] = t_pref["Agent"].replace({CON: CON_LABEL})
        t_pref_sum = om.preference_summary(t_pref)

    # Write summary CSVs (clean experiment names, no 2A/2B/etc.)
    written = []
    summaries = [
        ("constrained_vs_unconstrained", t_comp),
        ("initial_status_and_violations", t_part),
        ("violations_by_initial_status", t_part_ctx),
        ("cr_within_budget", t_wb),
        ("ablation_cr", t_abl),
        ("ablation_violations", t_abl_v),
    ]
    if has_obj:
        summaries += [
            ("objectives_constrained_vs_unconstrained", t_obj_comp),
            ("objectives_within_budget", t_obj_wb),
            ("ablation_objectives", t_obj_abl),
        ]
    if has_pref:
        summaries.append(("preference_tradeoff", t_pref_sum))
    for name, t in summaries:
        p = out / f"{name}.csv"
        t.to_csv(p, index=False, float_format="%.4f")
        written.append(p.name)

    # Write structured subfolders with clean experiment names
    subfolders = {
        "agent_comparison": {
            "aggregate_results.csv": t_comp,
            "per_expression_results.csv": pd.concat([
                frames[UNC].assign(Agent=UNC),
                frames[CON].assign(Agent=CON_LABEL),
            ], ignore_index=True),
        },
        "initial_budget_partition": {
            "partition_summary.csv": t_part,
            "within_budget_violations.csv": t_part[[
                "Budget",
                "Within-budget violations, unconstrained: count",
                "Within-budget violations, unconstrained: %",
                "Within-budget violations, constrained: count",
                "Within-budget violations, constrained: %",
            ]],
            "expression_budget_status.csv": unified_baseline[["Budget", "Expression #", "Initial Cost", "Initial Noise", "Is Feasible"]],
        },
        "within_budget_quality": {
            "aggregate_cost_reduction.csv": t_wb,
            "per_expression_results.csv": pd.concat([
                frames[UNC][frames[UNC]["Initial Noise"] <= frames[UNC]["Budget"]].assign(Agent=UNC),
                frames[CON][frames[CON]["Initial Noise"] <= frames[CON]["Budget"]].assign(Agent=CON_LABEL),
            ], ignore_index=True),
        },
        "constraint_ablation": {
            "aggregate_ablation.csv": t_abl,
            "per_expression_results.csv": pd.concat([
                df.assign(Method=lbl) for lbl, df in frames.items()
            ], ignore_index=True),
        },
    }
    if has_obj:
        subfolders["agent_comparison"]["aggregate_objectives.csv"] = compute_objectives_long(frames, pair)
        subfolders["within_budget_quality"]["aggregate_objectives.csv"] = compute_objectives_long(frames, pair, within_only=True)
        subfolders["constraint_ablation"]["aggregate_objectives.csv"] = compute_objectives_long(frames, all_agents)
    if has_pref:
        subfolders["preference_tradeoff"] = {
            "per_budget.csv": t_pref,
            "summary.csv": t_pref_sum,
            "per_budget_all_agents.csv": om.preference_table(frames, AGENTS, BUDGETS, BUDGET_LABEL, "Agent"),
        }

    for folder_name, files_dict in subfolders.items():
        folder_path = out / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        for fname, fdf in files_dict.items():
            fp = folder_path / fname
            fdf.to_csv(fp, index=False, float_format="%.4f")
            written.append(f"{folder_name}/{fname}")

    # Generate plots with clean names
    p_viol = plot_violation_rates(t_comp, out / "violation_rates.png")
    p_wb = plot_within_budget_cr(t_wb, out / "within_budget_cost_reduction.png")
    p_abl = plot_ablation(t_abl, out / "ablation_cost_reduction.png")
    written.extend([p_viol.name, p_wb.name, p_abl.name])
    if has_obj:
        exec_fmt = "B={b} " + EXEC_LABEL
        keys_fmt = "B={b} avg keys"
        for t, name, title in (
            (t_obj_comp, "objectives_constrained_vs_unconstrained.png", "Exec Cost and Rotation Keys (All 69 Expressions, No Rollback)"),
            (t_obj_wb, "objectives_within_budget.png", "Exec Cost and Rotation Keys on Initially Within-Budget Expressions"),
            (t_obj_abl, "ablation_objectives.png", "Constraint-Method Ablation: Exec Cost and Rotation Keys (No Rollback)"),
        ):
            om.plot_objectives_by_budget(t, BUDGET_LBLS, "Agent", exec_fmt, keys_fmt, title, out / name,
                                         highlight=CON if name == "ablation_objectives.png" else CON_LABEL)
            written.append(name)
    if has_pref:
        om.plot_preference_tradeoff(t_pref, "Exec Cost vs Rotation Keys per Preference (No Rollback)",
                                    out / "preference_tradeoff.png")
        written.append("preference_tradeoff.png")

    try:
        results_rel = data_dir.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        results_rel = str(data_dir)

    report = build_report({
        "source": source,
        "results_rel": results_rel,
        "n_pref": n_pref,
        "max_noise_diff": max(noise_diffs),
        "has_obj": has_obj,
        "has_pref": has_pref,
        "t_comp": t_comp,
        "t_part": t_part,
        "t_part_ctx": t_part_ctx,
        "t_wb": t_wb,
        "t_abl": t_abl,
        "t_abl_v": t_abl_v,
        "t_obj_comp": t_obj_comp,
        "t_obj_wb": t_obj_wb,
        "t_obj_abl": t_obj_abl,
        "t_pref_sum": t_pref_sum,
        "cfg": cfg,
    })
    write_text(out / "exp2_results.md", report)
    written.append("exp2_results.md")

    meta = {
        "experiment": "experiment_2 (constrained vs unconstrained RL agent)",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rollback": "disabled (raw Agent * columns at terminal step)",
        "result_source": source,
        "budgets": BUDGETS,
        "preferences_per_expression": n_pref,
        "objectives": ({"exec_cost": "Agent Final Ops (C_exec, exec_cost_mo); reported as reduction vs Initial Ops",
                        "rotation_keys": "Agent Final Keys (C_keys, unique rotation keys); reported as mean count"}
                       if has_obj else "not available in these results"),
        "unified_model": {
            "source_path": "RL/fhe_rl/env_unified.py",
            "env_class": "fhe_rl.env_unified.fheEnvUnified",
            "constraint_metric": "noise",
            "metric_unit": "bits",
            "benchmark_source": str(benchmark_file.relative_to(REPO_ROOT).as_posix()),
            "benchmark_expressions_count": N_EXPR,
        },
        "workbooks": {
            l: {"file": str(paths[l].relative_to(data_dir).as_posix()) if paths[l].is_relative_to(data_dir) else paths[l].name,
                "sha256": sha256_file(paths[l]), "rows": len(frames[l])}
            for l in AGENTS
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "outputs": written + ["run_metadata.json"],
    }
    write_text(out / "run_metadata.json", json.dumps(meta, indent=2) + "\n")

    print("\n" + "="*80)
    print("CONSTRAINED VS UNCONSTRAINED COMPARISON")
    print("="*80)
    print(df_to_md(t_comp))
    if has_obj:
        print("\nExec cost reduction (%) / avg rotation keys:")
        print(df_to_md(compact_objectives(t_obj_comp)))

    print("\n" + "="*80)
    print("INITIAL BUDGET PARTITION & VIOLATION ATTRIBUTION")
    print("="*80)
    print(df_to_md(t_part))

    print("\n" + "="*80)
    print("COST REDUCTION ON INITIALLY WITHIN-BUDGET EXPRESSIONS")
    print("="*80)
    print(df_to_md(t_wb))
    if has_obj:
        print("\nExec cost reduction (%) / avg rotation keys:")
        print(df_to_md(compact_objectives(t_obj_wb)))

    print("\n" + "="*80)
    print("CONSTRAINT-METHOD ABLATION")
    print("="*80)
    print(df_to_md(t_abl))
    if has_obj:
        print("\nExec cost reduction (%) / avg rotation keys:")
        print(df_to_md(compact_objectives(t_obj_abl)))
    else:
        print("\n[note] exec cost / rotation keys not in these results (legacy source); "
              "use --source unified with results/ablation_unified/")
    if has_pref:
        print("\n" + "="*80)
        print("PREFERENCE TRADE-OFF (averaged over budgets)")
        print("="*80)
        print(df_to_md(t_pref_sum))

    print(f"\n[done] All outputs successfully generated in {out}")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Experiment 2: Constrained vs Unconstrained RL Agent")
    ap.add_argument("--source", choices=["auto", "unified", "legacy"], default="auto",
                    help="unified = results/ablation_unified (exec cost + rotation keys), legacy = hpc_results workbooks")
    ap.add_argument("--results-dir", default=str(DEFAULT_RESULTS), help="legacy: directory with original_<tag>.xlsx workbooks")
    ap.add_argument("--unified-dir", default=str(DEFAULT_UNIFIED), help="unified: results/ablation_unified (<agent>/eval_<job>/original.csv)")
    ap.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK), help="path to benchmarks.txt")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    args = ap.parse_args(argv)

    try:
        return run(args)
    except DataError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Shared loaders and multi-objective metrics for Experiments 2 and 3.

The unified agent optimises two objectives under a noise constraint:
    C_exec = exec_cost_mo(expr)   execution-time cost model (ops + rotations + depths)
    C_keys = keys_cost(expr)      number of unique rotation (Galois) keys
`fhe_rl test --test_mode v2` records them per row as `<Prefix> Final Ops` and
`<Prefix> Final Keys` (Prefix = Initial / Agent / Safe), next to the constraint
columns. This module reads those results and summarises the two objectives so the
constraint ablations can report them alongside cost reduction and violations.

Two result layouts are supported:
    legacy   hpc_results/rl_test_results/{original,threshold}_<tag>.xlsx
             (older test runs: one scalar cost, no exec/keys split, no preferences)
    unified  results/ablation_unified/<agent>/eval_<jobid>/{original,threshold}.csv
             (scripts/ablation_unified/eval_*.sbatch: exec/keys split, 10 preferences)

Rotation keys are reported as an absolute count: every benchmark expression starts
scalar with 0 keys, so a "keys reduction (%)" is always <= 0 and not informative.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# Display label -> (legacy file tag, unified ablation folder)
AGENT_SOURCES = {
    "Unconstrained": ("unconstrained", "unconstrained"),
    "V4 Margin Barrier": ("v4_mb_B", "v4_mb"),
    "V4 Noise Masking": ("v4_nmask_B", "v4_nmask"),
    "V4 MB + FiLM": ("v4_mb_film_B", "v4_mb_film"),
    "V5 FOCOPS + NATO-SC": ("v5_focops_natosc", "v5_focops"),
    "V5 Lag-PID + NATO-SC": ("v5_lagpid_natosc", "ref_lagpid_natosc"),
}

# test_agent_v2 relabels its "RAM (MB)" columns to "Noise (bits)" for the noise metric
NOISE_RENAMES = {
    "Initial Noise (bits)": "Initial Noise",
    "Agent Final Noise (bits)": "Agent Final Noise",
    "Safe Final Noise (bits)": "Safe Final Noise",
    "Trajectory Noise (bits)": "Trajectory Noises",
    "Noise Headroom (bits)": "Noise Margin",
}
BOOL_COLS = ["Is Feasible", "Agent Violated", "Safe Violated", "Safety Activated"]
OBJECTIVE_COLS = [
    "Initial Ops", "Initial Keys",
    "Agent Final Ops", "Agent Final Keys",
    "Safe Final Ops", "Safe Final Keys",
]
PREF_COLS = ["w_ops", "w_keys"]

EXEC_LABEL = "Exec cost red. (%)"
KEYS_LABEL = "Rotation keys"


class SourceError(Exception):
    """Result files are missing or have the wrong layout."""


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _to_bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "1.0"])


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Give both layouts the same column names and dtypes."""
    df = df.rename(columns={k: v for k, v in NOISE_RENAMES.items() if k in df.columns}).copy()
    for c in BOOL_COLS:
        if c in df.columns:
            df[c] = _to_bool(df[c])
    if "Budget" in df.columns:
        df["Budget"] = pd.to_numeric(df["Budget"]).astype(int)
    for c in OBJECTIVE_COLS + PREF_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def has_objectives(df: pd.DataFrame) -> bool:
    return all(c in df.columns for c in OBJECTIVE_COLS)


def has_preferences(df: pd.DataFrame) -> bool:
    return all(c in df.columns for c in PREF_COLS) and df["w_ops"].notna().any()


def _job_key(path: Path):
    m = re.search(r"eval_(\d+)$", path.name)
    return (1, int(m.group(1))) if m else (0, path.stat().st_mtime)


def find_unified_file(root: Path, agent_dir: str, set_name: str) -> Path:
    """Newest results/ablation_unified/<agent>/eval_<job>/<set>.csv (or .xlsx)."""
    base = root / agent_dir
    if not base.is_dir():
        raise SourceError(f"no folder {base}")
    runs = sorted((d for d in base.glob("eval_*") if d.is_dir()), key=_job_key, reverse=True)
    for d in runs:
        for ext in (".csv", ".xlsx"):
            p = d / f"{set_name}{ext}"
            if p.is_file():
                return p
    raise SourceError(f"no {set_name}.csv/.xlsx under {base}/eval_*")


def read_results(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        df = pd.read_csv(path)
    else:
        xl = pd.ExcelFile(path)
        df = xl.parse("all_results" if "all_results" in xl.sheet_names else xl.sheet_names[0])
    return normalize(df)


def resolve_source(source: str, legacy_dir: Path, unified_dir: Path) -> str:
    """'auto' -> unified when every agent has unified results, else legacy."""
    if source != "auto":
        return source
    try:
        for _, agent_dir in AGENT_SOURCES.values():
            find_unified_file(unified_dir, agent_dir, "original")
        return "unified"
    except SourceError:
        return "legacy"


def agent_file(source: str, label: str, set_name: str, legacy_dir: Path, unified_dir: Path) -> Path:
    tag, agent_dir = AGENT_SOURCES[label]
    if source == "unified":
        return find_unified_file(unified_dir, agent_dir, set_name)
    return legacy_dir / f"{set_name}_{tag}.xlsx"


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def exec_reduction(df: pd.DataFrame, prefix: str) -> pd.Series:
    """Per-row C_exec reduction (%) for prefix 'Agent' (no rollback) or 'Safe' (rollback)."""
    ops0 = df["Initial Ops"].astype(float)
    ops = df[f"{prefix} Final Ops"].astype(float)
    return (100.0 * (ops0 - ops) / ops0.where(ops0 > 0)).fillna(0.0)


def objective_stats(sub: pd.DataFrame, prefix: str) -> dict:
    """Mean exec-cost reduction and rotation-key statistics of one subset."""
    if not has_objectives(sub) or sub.empty:
        return {"exec_red": np.nan, "exec_final": np.nan, "keys": np.nan, "keys_median": np.nan,
                "keys_max": np.nan, "zero_keys_pct": np.nan}
    keys = sub[f"{prefix} Final Keys"].astype(float)
    return {
        "exec_red": float(exec_reduction(sub, prefix).mean()),
        "exec_final": float(sub[f"{prefix} Final Ops"].astype(float).mean()),
        "keys": float(keys.mean()),
        "keys_median": float(keys.median()),
        "keys_max": float(keys.max()),
        "zero_keys_pct": float(100.0 * (keys == 0).mean()),
    }


def pref_label(w_ops: float, w_keys: float) -> str:
    return f"[{w_ops:.1f}, {w_keys:.1f}]"


def preference_table(frames: dict, labels: list, budgets: list, budget_label: dict, prefix: str,
                     within_only: bool = False, cr_col: str = "Agent Cost Reduction (%)",
                     viol_col: str = "Agent Violated") -> pd.DataFrame:
    """Long table: one row per (agent, budget, preference)."""
    rows = []
    for label in labels:
        df = frames[label]
        if not (has_objectives(df) and has_preferences(df)):
            continue
        for b in budgets:
            sub = df[df["Budget"] == b]
            if within_only:
                sub = sub[sub["Initial Noise"] <= b]
            for (wo, wk), g in sub.groupby(PREF_COLS, sort=True):
                st = objective_stats(g, prefix)
                rows.append({
                    "Agent": label,
                    "Budget": budget_label[b],
                    "w_ops": wo,
                    "w_keys": wk,
                    "Preference": pref_label(wo, wk),
                    "Rows": len(g),
                    "CR%": float(g[cr_col].mean()),
                    EXEC_LABEL: st["exec_red"],
                    f"Avg {KEYS_LABEL}": st["keys"],
                    "Zero-key rows (%)": st["zero_keys_pct"],
                    "Violation rate (%)": float(100.0 * g[viol_col].mean()),
                })
    return pd.DataFrame(rows)


def preference_summary(t_pref: pd.DataFrame) -> pd.DataFrame:
    """Average over budgets: one row per preference, two columns per agent."""
    if t_pref.empty:
        return t_pref
    agg = (t_pref.groupby(["Agent", "w_keys", "Preference"], sort=True)
           [[EXEC_LABEL, f"Avg {KEYS_LABEL}"]].mean().reset_index())
    out = None
    for agent in t_pref["Agent"].unique():  # keep the caller's agent order
        g = agg[agg["Agent"] == agent]
        g = g.rename(columns={EXEC_LABEL: f"{agent}: {EXEC_LABEL}",
                              f"Avg {KEYS_LABEL}": f"{agent}: avg keys"}).drop(columns="Agent")
        out = g if out is None else out.merge(g, on=["w_keys", "Preference"], how="outer")
    return out.sort_values("w_keys").drop(columns="w_keys").reset_index(drop=True)


def check_objectives(df: pd.DataFrame, label: str, exprs: list[str] | None = None) -> list[str]:
    """Consistency checks on the exec/keys columns. Returns a list of problems."""
    problems = []
    if not has_objectives(df):
        return problems
    for prefix in ("Agent", "Safe"):
        col = f"{prefix} Ops Reduction (%)"
        if col in df.columns:
            diff = (exec_reduction(df, prefix) - pd.to_numeric(df[col], errors="coerce")).abs().max()
            if diff > 0.011:
                problems.append(f"[{label}] `{col}` disagrees with Initial/Final Ops (max diff {diff:.3f})")
        if (df[f"{prefix} Final Keys"] < 0).any():
            problems.append(f"[{label}] negative `{prefix} Final Keys`")
    if exprs is not None:
        # Initial Ops / Keys must equal split_cost_mo on the benchmark expressions
        from pytrs import parse_sexpr
        from pytrs.cost import split_cost_mo
        want = sorted((round(float(o), 2), round(float(k), 2))
                      for o, k in (split_cost_mo(parse_sexpr(e)) for e in exprs))
        first = df.drop_duplicates(["Budget", "Expression #"])
        for b, g in first.groupby("Budget"):
            got = sorted(zip(g["Initial Ops"].round(2), g["Initial Keys"].round(2)))
            if got != want:
                problems.append(f"[{label}] budget {b}: Initial Ops/Keys differ from split_cost_mo of the benchmark")
                break
    return problems


# --------------------------------------------------------------------------- #
# Plots
# --------------------------------------------------------------------------- #
def plot_objectives_by_budget(table: pd.DataFrame, budgets_lbl: list, agent_col: str,
                              exec_fmt: str, keys_fmt: str, title: str, out_path: Path,
                              highlight: str | None = None) -> Path:
    """Two panels: exec-cost reduction and avg rotation keys, grouped by budget."""
    import matplotlib.pyplot as plt
    agents = table[agent_col].tolist()
    x = np.arange(len(budgets_lbl))
    width = 0.8 / max(len(agents), 1)
    cmap = plt.get_cmap("tab10")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, fmt, ylabel in ((axes[0], exec_fmt, "Exec cost reduction (%)"),
                            (axes[1], keys_fmt, "Avg rotation keys (unique)")):
        for i, agent in enumerate(agents):
            row = table[table[agent_col] == agent].iloc[0]
            vals = [row[fmt.format(b=b)] for b in budgets_lbl]
            ax.bar(x - 0.4 + width * (i + 0.5), vals, width, label=agent, color=cmap(i % 10),
                   edgecolor="black" if agent == highlight else None, linewidth=1.4 if agent == highlight else 0)
        ax.set_xticks(x)
        ax.set_xticklabels([f"B={b}" for b in budgets_lbl])
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", linestyle="--", alpha=0.5)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.suptitle(title, fontsize=13)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.legend(handles, labels, loc="lower center", ncol=min(len(agents), 6), fontsize=9, frameon=False)
    fig.savefig(str(out_path), bbox_inches="tight", dpi=200)
    plt.close(fig)
    return out_path


def plot_preference_tradeoff(t_pref: pd.DataFrame, title: str, out_path: Path) -> Path:
    """Exec-cost reduction vs avg rotation keys per preference (averaged over budgets)."""
    import matplotlib.pyplot as plt
    agg = (t_pref.groupby(["Agent", "w_keys"], sort=True)[[EXEC_LABEL, f"Avg {KEYS_LABEL}"]]
           .mean().reset_index())
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for i, agent in enumerate(t_pref["Agent"].unique()):
        g = agg[agg["Agent"] == agent].sort_values("w_keys")
        ax.plot(g[f"Avg {KEYS_LABEL}"], g[EXEC_LABEL], marker="o", label=agent, color=plt.get_cmap("tab10")(i))
        for _, r in g.iterrows():
            ax.annotate(f"{r['w_keys']:.1f}", (r[f"Avg {KEYS_LABEL}"], r[EXEC_LABEL]),
                        xytext=(4, 3), textcoords="offset points", fontsize=7)
    ax.set_xlabel("Avg rotation keys (fewer is better)")
    ax.set_ylabel("Exec cost reduction (%) (higher is better)")
    ax.set_title(title + "\n(labels = w_keys)", fontsize=12)
    ax.grid(linestyle="--", alpha=0.5)
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(str(out_path), bbox_inches="tight", dpi=200)
    plt.close(fig)
    return out_path

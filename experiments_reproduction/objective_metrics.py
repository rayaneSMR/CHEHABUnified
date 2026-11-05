#!/usr/bin/env python3
"""Shared loaders and multi-objective metrics for Experiments 2 and 3.

The unified agent optimises two objectives under a noise constraint:
    C_exec = exec_cost_mo(expr)   execution-time cost model (ops + rotations + depths)
    C_keys = keys_cost(expr)      number of unique rotation (Galois) keys
`fhe_rl test --test_mode v2` records them per row as `<Prefix> Final Ops` and
`<Prefix> Final Keys` (Prefix = Initial / Agent / Safe), next to the constraint
columns. This module reads those results and summarises the two objectives so the
constraint ablations can report them alongside cost reduction and violations.

Result layouts:
    legacy   hpc_results/rl_test_results/{original,threshold}_<tag>.xlsx
             (older test runs: one scalar cost, no exec/keys split, no preferences)
    unified  results/ablation_unified/<agent>[_4pref]/eval_<jobid>/{original,threshold}.csv
             (scripts/ablation_unified/eval_*.sbatch: exec/keys split; 10 preferences, or the
             4 training preferences for the 4-preference ablation, eval_4pref.sbatch)
    SEAL     results/ablation_unified/e2e_4pref/{rollback,no_rollback}/<agent>_4pref/e2e_*.csv
             (scripts/ablation_unified/e2e_4pref.sh -> eval_unified_e2e.sbatch ->
             run_benchmarks_unified.py, the real-execution protocol of the unified agent):
             measured circuit execution time and rotation-key size on the C++ benchmarks

Rotation keys are reported as an absolute count: every benchmark expression starts
scalar with 0 keys, so a "keys reduction (%)" is always <= 0 and not informative.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

# Display label -> (legacy file tag, 10-pref ablation folder, 4-pref ablation folder (also the e2e folder))
AGENT_SOURCES = {
    "Unconstrained": ("unconstrained", "unconstrained", "unconstrained_4pref"),
    "V4 Margin Barrier": ("v4_mb_B", "v4_mb", "v4_mb_4pref"),
    "V4 Noise Masking": ("v4_nmask_B", "v4_nmask", "v4_nmask_4pref"),
    "V4 MB + FiLM": ("v4_mb_film_B", "v4_mb_film", "v4_mb_film_4pref"),
    "V5 FOCOPS + NATO-SC": ("v5_focops_natosc", "v5_focops", "v5_focops_4pref"),
    "V5 Lag-PID + NATO-SC": ("v5_lagpid_natosc", "ref_lagpid_natosc", "v5_lagpid_4pref"),
}
ABLATIONS = ("4pref", "10pref")


def result_tag(label: str, source: str, ablation: str = "4pref") -> str:
    legacy, d10, d4 = AGENT_SOURCES[label]
    if source == "legacy":
        return legacy
    return d4 if ablation == "4pref" else d10

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


def resolve_source(source: str, legacy_dir: Path, unified_dir: Path, ablation: str = "4pref") -> str:
    """'auto' -> unified when every agent has unified results, else legacy."""
    if source != "auto":
        return source
    try:
        for label in AGENT_SOURCES:
            find_unified_file(unified_dir, result_tag(label, "unified", ablation), "original")
        return "unified"
    except SourceError:
        return "legacy"


def agent_file(source: str, label: str, set_name: str, legacy_dir: Path, unified_dir: Path,
               ablation: str = "4pref") -> Path:
    tag = result_tag(label, source, ablation)
    if source == "unified":
        return find_unified_file(unified_dir, tag, set_name)
    return legacy_dir / f"{set_name}_{tag}.xlsx"


# --------------------------------------------------------------------------- #
# Measured SEAL execution: real compile + SEAL run, the protocol of the unified agent
# (scripts/run_benchmarks_unified.py via eval_unified_e2e.sbatch; 4-pref ablation:
# scripts/ablation_unified/e2e_4pref.sh). One CSV per job:
#   <e2e-dir>/<rollback|no_rollback>/<agent>_4pref/e2e_<benchmark>_b<budget>_<jobid>.csv
# Each row = one benchmark config x preference: the generated SEAL program is built (Release)
# and run 3 times, the first is a warm-up, the median of the others is kept:
#   circuit_execution_time (s), rotation_keys_size (MB) (= GaloisKeys::save_size), ...
# --------------------------------------------------------------------------- #
SEAL_TIME = "circuit_execution_time (s)"
SEAL_KEYS = "rotation_keys_size (MB)"
SEAL_NOISE = "Remaining_noise_budget"
SEAL_NUMERIC = [SEAL_TIME, SEAL_KEYS, SEAL_NOISE, "galois_keys_generation_time (s)", "total_execution_time (s)",
                "peak_ram (MB)", "compile_time (s)", "initial_noise_est", "agent_noise_est", "safe_noise_est",
                "agent_ops", "agent_keys", "safe_ops", "safe_keys", "w_ops", "w_keys", "slot_count"]
SEAL_BOOL = ["outputs_match", "safety_activated", "agent_violated", "rollback"]
NOISE_REFERENCE_BITS = 369     # initial BFV budget of the generated programs: used bits = 369 - remaining
UNCONSTRAINED_BUDGET = 9_000_000
TIME_LABEL = "Exec time (ms)"
KEYSIZE_LABEL = "Rot. key size (MB)"
_E2E_FILE = re.compile(r"_(\d+|local)\.csv$")


def _e2e_job(path: Path):
    m = _E2E_FILE.search(path.name)
    return int(m.group(1)) if m and m.group(1).isdigit() else -1


def load_seal(mode_dir: Path, label: str) -> pd.DataFrame | None:
    """All real-execution rows of one agent from <mode_dir>/<agent>_4pref/e2e_*.csv, or None.

    As in merge_eval_results.py, the newest row per (benchmark, budget, preference) is kept
    when a run was repeated. A measured violation is a remaining noise budget <= 0, or
    369 - remaining > B for a finite budget B.
    """
    folder = Path(mode_dir) / AGENT_SOURCES[label][2]
    files = sorted(folder.glob("e2e_*.csv"), key=lambda f: (_e2e_job(f), f.name))
    if not files:
        return None
    df = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    df = df.drop_duplicates(["benchmark", "budget", "w_ops"], keep="last")
    for c in SEAL_NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in SEAL_BOOL:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip().str.lower().map({"true": True, "false": False})
    df["budget"] = pd.to_numeric(df["budget"], errors="coerce").astype("Int64")
    df["ok"] = df["status"].astype(str).eq("ok") & df[SEAL_TIME].notna() & df[SEAL_KEYS].notna()
    rem = df[SEAL_NOISE] if SEAL_NOISE in df.columns else pd.Series(np.nan, index=df.index)
    used = NOISE_REFERENCE_BITS - rem
    finite = df["budget"].astype(float) < UNCONSTRAINED_BUDGET
    df["measured_violated"] = ((rem <= 0) | (finite & (used > df["budget"].astype(float)))).where(rem.notna())
    return df


def seal_subset(df: pd.DataFrame, budget: int, within_only: bool = False) -> pd.DataFrame:
    sub = df[df["budget"] == budget]
    if within_only:
        sub = sub[sub["initial_noise_est"] <= budget]
    return sub


def _rate(series) -> float:
    s = series.dropna()
    return float(100 * s.astype(bool).mean()) if len(s) else np.nan


def seal_stats(sub: pd.DataFrame) -> dict:
    ok = sub[sub["ok"]]
    viol = ok["measured_violated"].dropna()
    return {
        "points": len(sub), "ok": len(ok),
        "time_ms": float(1000 * ok[SEAL_TIME].mean()) if len(ok) else np.nan,
        "time_ms_median": float(1000 * ok[SEAL_TIME].median()) if len(ok) else np.nan,
        "keys_mb": float(ok[SEAL_KEYS].mean()) if len(ok) else np.nan,
        "noise_left": float(ok[SEAL_NOISE].mean()) if len(ok) and SEAL_NOISE in ok else np.nan,
        "meas_viol_pct": _rate(viol),
        "meas_viol": int(viol.astype(bool).sum()) if len(viol) else 0,
        "outputs_ok_pct": _rate(ok["outputs_match"]) if "outputs_match" in ok else np.nan,
        "rollback_pct": _rate(sub["safety_activated"]) if "safety_activated" in sub else np.nan,
    }


def seal_time_ratio(sub: pd.DataFrame, ref: pd.DataFrame) -> float:
    """Geometric mean over matched points (benchmark, budget, w_ops) of time / reference time."""
    key = ["benchmark", "budget", "w_ops"]
    a = sub[sub["ok"] & (sub[SEAL_TIME] > 0)][key + [SEAL_TIME]]
    b = ref[ref["ok"] & (ref[SEAL_TIME] > 0)][key + [SEAL_TIME]]
    m = a.merge(b, on=key, suffixes=("", "_ref"))
    if m.empty:
        return np.nan
    return float(np.exp(np.log(m[SEAL_TIME] / m[f"{SEAL_TIME}_ref"]).mean()))


def _nanmean(vals):
    vals = [v for v in vals if not pd.isna(v)]
    return float(np.mean(vals)) if vals else np.nan


def seal_budget_table(frames: dict, labels: list, budgets: list, budget_label: dict,
                      ref_label: str, within_only: bool = False) -> pd.DataFrame:
    """Wide: per agent, measured exec time / key size / violation per budget, plus averages."""
    rows = []
    ref = frames.get(ref_label)
    for label in labels:
        df = frames.get(label)
        if df is None:
            continue
        row = {"Agent": label}
        t, k, v, logs, oc = [], [], [], [], []
        for b in budgets:
            sub = seal_subset(df, b, within_only)
            st = seal_stats(sub)
            lb = budget_label[b]
            row[f"B={lb} {TIME_LABEL}"] = st["time_ms"]
            row[f"B={lb} {KEYSIZE_LABEL}"] = st["keys_mb"]
            row[f"B={lb} measured viol. (%)"] = st["meas_viol_pct"]
            row[f"B={lb} ok/points"] = f"{st['ok']}/{st['points']}"
            t.append(st["time_ms"]); k.append(st["keys_mb"]); v.append(st["meas_viol_pct"])
            oc.append(st["outputs_ok_pct"])
            if ref is not None:
                ratio = seal_time_ratio(sub, seal_subset(ref, b, within_only))
                if not pd.isna(ratio):
                    logs.append(np.log(ratio))
        row[f"Average {TIME_LABEL}"] = _nanmean(t)
        row[f"Average {KEYSIZE_LABEL}"] = _nanmean(k)
        row["Average measured viol. (%)"] = _nanmean(v)
        row["Outputs correct (%)"] = _nanmean(oc)
        row[f"Time vs {ref_label} (geo-mean)"] = float(np.exp(np.mean(logs))) if logs else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _fmt(v, f):
    return "n/a" if pd.isna(v) else format(v, f)


def seal_compact(t: pd.DataFrame, budget_lbls: list, ref_label: str) -> pd.DataFrame:
    """'time ms / key MB / measured viol %' cells for the markdown reports."""
    rows = []
    for _, r in t.iterrows():
        row = {"Agent": r["Agent"]}
        for b in budget_lbls:
            row[f"B={b}"] = (f"{_fmt(r[f'B={b} {TIME_LABEL}'], '.1f')} ms / {_fmt(r[f'B={b} {KEYSIZE_LABEL}'], '.1f')} MB"
                             f" / {_fmt(r[f'B={b} measured viol. (%)'], '.1f')}%")
        row["Average"] = (f"{_fmt(r[f'Average {TIME_LABEL}'], '.1f')} ms / {_fmt(r[f'Average {KEYSIZE_LABEL}'], '.1f')} MB"
                          f" / {_fmt(r['Average measured viol. (%)'], '.1f')}%")
        ratio = r[f"Time vs {ref_label} (geo-mean)"]
        row[f"Time vs {ref_label}"] = "" if pd.isna(ratio) else f"{ratio:.3f}x"
        row["Outputs correct"] = f"{_fmt(r['Outputs correct (%)'], '.1f')}%"
        rows.append(row)
    return pd.DataFrame(rows)


def seal_long_table(frames: dict, labels: list, budgets: list, budget_label: dict,
                    within_only: bool = False) -> pd.DataFrame:
    rows = []
    for label in labels:
        df = frames.get(label)
        if df is None:
            continue
        for b in budgets:
            st = seal_stats(seal_subset(df, b, within_only))
            rows.append({"Agent": label, "Budget": budget_label[b], "Points": st["points"], "OK": st["ok"],
                         f"Mean {TIME_LABEL}": st["time_ms"], f"Median {TIME_LABEL}": st["time_ms_median"],
                         f"Mean {KEYSIZE_LABEL}": st["keys_mb"], "Mean remaining noise (bits)": st["noise_left"],
                         "Measured violations": st["meas_viol"], "Measured violation rate (%)": st["meas_viol_pct"],
                         "Outputs correct (%)": st["outputs_ok_pct"], "Rollback rate (%)": st["rollback_pct"]})
    return pd.DataFrame(rows)


def seal_preference_table(frames: dict, labels: list, budgets: list, within_only: bool = False) -> pd.DataFrame:
    """Per agent and preference, over all budgets: measured exec time and key size."""
    rows = []
    for label in labels:
        df = frames.get(label)
        if df is None:
            continue
        sub = pd.concat([seal_subset(df, b, within_only) for b in budgets])
        for w, g in sorted(sub.groupby("w_ops"), key=lambda kv: -kv[0]):
            st = seal_stats(g)
            rows.append({"Agent": label, "Preference": pref_label(w, 1 - w), "OK points": st["ok"],
                         f"Mean {TIME_LABEL}": st["time_ms"], f"Mean {KEYSIZE_LABEL}": st["keys_mb"],
                         "Measured violation rate (%)": st["meas_viol_pct"]})
    return pd.DataFrame(rows)


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
                              highlight: str | None = None,
                              ylabels: tuple = ("Exec cost reduction (%)", "Avg rotation keys (unique)")) -> Path:
    """Two panels grouped by budget: exec-cost reduction and avg rotation keys (or the given metrics)."""
    import matplotlib.pyplot as plt
    agents = table[agent_col].tolist()
    x = np.arange(len(budgets_lbl))
    width = 0.8 / max(len(agents), 1)
    cmap = plt.get_cmap("tab10")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, fmt, ylabel in ((axes[0], exec_fmt, ylabels[0]), (axes[1], keys_fmt, ylabels[1])):
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

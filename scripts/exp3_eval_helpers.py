#!/usr/bin/env python3
"""Helpers for scripts/eval_unified_uniform.sbatch (Experiment 3 evaluation).

  build-benchmarks  write the evaluation set: RL/fhe_rl/datasets/benchmarks.txt minus every DNN
                    benchmark, one "<expression>:<name>" line each (names from benchmarks_names.xlsx,
                    unnamed synthetic expressions -> synthetic_NN)
  summarize         merge the constrained (test v2) and MORL (bisection) results into one summary xlsx
  summarize-seal    same for the real-execution sweep (unified_morl_experiments.py sweep/metrics):
                    constrained metrics from the raw CSVs, MORL metrics from metrics.csv

Only needs pandas + openpyxl (no torch), so it can also be run by hand.
"""
import argparse
import os
import re
import sys

import pandas as pd

# Same DNN list as RL/fhe_rl/test.py (DNN_BENCHMARKS) + generic DNN name patterns
DNN_NAME_RE = re.compile(
    r"(conv2d|full_dnn|cryptonets|mlp|lola|lenet|resnet|alexnet|dnn|tensor|fc_|poly_activation)",
    re.IGNORECASE,
)
DNN_FILES = ["dnn_benchmarks.txt", "dnn_benchmarks_scaled.txt", "conv2d.txt", "conv2d_only.txt"]


def _norm(expr):
    return " ".join(str(expr).split())


def _read_exprs(path):
    out = []
    if not os.path.isfile(path):
        return out
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                e, n = line.rsplit(":", 1)
                out.append((_norm(e), n.strip()))
            else:
                out.append((_norm(line), None))
    return out


def build_benchmarks(datasets_dir, out_file):
    bench = _read_exprs(os.path.join(datasets_dir, "benchmarks.txt"))
    names = {}
    xlsx = os.path.join(datasets_dir, "benchmarks_names.xlsx")
    if os.path.isfile(xlsx):
        df = pd.read_excel(xlsx)
        for _, r in df.iterrows():
            if pd.notna(r.get("Name")) and pd.notna(r.get("Expression")):
                names[_norm(r["Expression"])] = str(r["Name"]).strip()
    dnn_exprs = {e for f in DNN_FILES for e, _ in _read_exprs(os.path.join(datasets_dir, f))}

    kept, excluded, seen, n_syn = [], [], set(), 0
    for expr, inline_name in bench:
        if expr in seen:
            continue
        seen.add(expr)
        name = inline_name or names.get(expr)
        if name is None:
            n_syn += 1
            name = f"synthetic_{n_syn:02d}"
        if expr in dnn_exprs or DNN_NAME_RE.search(name):
            excluded.append(name)
            continue
        kept.append((expr, name))

    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    with open(out_file, "w") as f:
        for expr, name in kept:
            f.write(f"{expr}:{name}\n")
    n_named = sum(not n.startswith("synthetic_") for _, n in kept)
    print(f"[benchmarks] {len(kept)} kept ({n_named} named kernels + {len(kept) - n_named} synthetic), "
          f"{len(excluded)} DNN excluded{': ' + ', '.join(excluded) if excluded else ''}")
    print(f"[benchmarks] written to {out_file}")
    if not kept:
        sys.exit("[FAIL] no benchmark left after excluding DNN")


def _col(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def summarize(constrained_csv, morl_xlsx, out_file):
    sheets = {}

    # ── constrained metrics (test v2: every benchmark x budget x preference) ──
    if constrained_csv and os.path.isfile(constrained_csv):
        df = pd.read_csv(constrained_csv)
        bfv = _col(df, "BFV Bound Remaining Budget (bits)")
        agg = {
            "Episodes": ("Expression Name", "size"),
            "Feasible at start (%)": ("Is Feasible", lambda s: 100 * s.mean()),
            "Agent Compliance (%)": ("Agent Violated", lambda s: 100 * (1 - s.mean())),
            "Safe Compliance (%)": ("Safe Violated", lambda s: 100 * (1 - s.mean())),
            "Rollback Rate (%)": ("Safety Activated", lambda s: 100 * s.mean()),
            "Agent Exec Red (%)": ("Agent Ops Reduction (%)", "mean"),
            "Agent Keys Red (%)": ("Agent Keys Reduction (%)", "mean"),
            "Safe Exec Red (%)": ("Safe Ops Reduction (%)", "mean"),
            "Safe Keys Red (%)": ("Safe Keys Reduction (%)", "mean"),
            "Agent Cost Red (%)": ("Agent Cost Reduction (%)", "mean"),
            "Safe Cost Red (%)": ("Safe Cost Reduction (%)", "mean"),
            "Avg RL Time (s)": ("RL Time (ms)", lambda s: s.mean() / 1000),
        }
        if bfv:
            agg["Avg BFV Remaining (bits)"] = (bfv, lambda s: pd.to_numeric(s, errors="coerce").mean())
        for c in ("Is Feasible", "Agent Violated", "Safe Violated", "Safety Activated"):
            df[c] = df[c].astype(str).str.lower().isin(["true", "1"])
        sheets["constrained_per_budget_pref"] = df.groupby(["Budget", "w_ops", "w_keys"]).agg(**agg).round(2).reset_index()
        sheets["constrained_per_budget"] = df.groupby(["Budget"]).agg(**agg).round(2).reset_index()
        feas = df[df["Is Feasible"]]
        if len(feas):
            sheets["constrained_feasible_only"] = feas.groupby(["Budget", "w_ops", "w_keys"]).agg(**agg).round(2).reset_index()
        print("\n== Constrained metrics per budget ==")
        print(sheets["constrained_per_budget"].to_string(index=False))
    else:
        print(f"[warn] constrained results not found: {constrained_csv}")

    # ── MORL metrics (bisection: Pareto front per benchmark x budget) ──
    if morl_xlsx and os.path.isfile(morl_xlsx):
        m = pd.read_excel(morl_xlsx, sheet_name="metrics")
        cols = [c for c in ("IC", "HV", "SP", "EU", "Bisection Yield", "Infeasible Probes",
                            "Grid Probes", "Bisection Probes", "Distinct Key Counts") if c in m.columns]
        has_front = m["IC"].fillna(0) > 0
        per_b = m[has_front].groupby("Budget")[cols].mean(numeric_only=True).round(4).reset_index()
        per_b.insert(1, "Benchmarks with front", m[has_front].groupby("Budget").size().values)
        per_b.insert(2, "Benchmarks total", m.groupby("Budget").size().reindex(per_b["Budget"]).values)
        sheets["morl_per_budget"] = per_b
        sheets["morl_per_benchmark"] = m
        print("\n== MORL metrics per budget (benchmarks with a feasible front) ==")
        print(per_b.to_string(index=False))
    else:
        print(f"[warn] MORL results not found: {morl_xlsx}")

    if not sheets:
        sys.exit("[FAIL] nothing to summarize")
    with pd.ExcelWriter(out_file, engine="openpyxl") as w:
        for name, frame in sheets.items():
            frame.to_excel(w, sheet_name=name[:31], index=False)
    print(f"\n[summary] written to {out_file}")


SEAL_NUM = ["circuit_execution_time_s", "total_execution_time_s", "galois_keys_generation_time_s",
            "rotation_keys_size_mb", "remaining_noise_budget", "measured_used_bits", "est_noise",
            "agent_est_noise", "compile_time_s", "rl_inference_s", "rl_steps", "depth", "mult_depth",
            "add", "sub", "multiply_plain", "rotate_rows", "negate", "multiply", "peak_ram_mb"]


def _bool_rate(s):
    v = s.dropna().astype(str).str.lower()
    v = v[v.isin(["true", "false", "1", "0"])]
    return 100.0 * v.isin(["true", "1"]).mean() if len(v) else None


def _seal_agg(g):
    ok = g[g["status"] == "ok"]
    row = {
        "Points": len(g),
        "OK (%)": 100.0 * len(ok) / len(g) if len(g) else None,
        "Measured Compliance (%)": (100.0 - _bool_rate(ok["measured_violated"]))
        if _bool_rate(ok["measured_violated"]) is not None else None,
        "Estimated Compliance (%)": (100.0 - _bool_rate(ok["est_violated"]))
        if _bool_rate(ok["est_violated"]) is not None else None,
        "Rollback Rate (%)": _bool_rate(ok["rollback_used"]),
        "Feasible at start (%)": _bool_rate(ok["feasible_start"]),
        "Agent Compliance est. (%)": (100.0 - _bool_rate(ok["agent_violated"]))
        if _bool_rate(ok["agent_violated"]) is not None else None,
        "Agent Cost Red (%)": ok["agent_cost_red"].mean(),
        "Safe Cost Red (%)": ok["safe_cost_red"].mean(),
        "Agent Keys Red (%)": ok["agent_keys_red"].mean(),
        "Safe Keys Red (%)": ok["safe_keys_red"].mean(),
        "Min Remaining Noise (bits)": pd.to_numeric(ok["remaining_noise_budget"], errors="coerce").min(),
    }
    for c in SEAL_NUM:
        if c in ok.columns:
            row[f"mean {c}"] = pd.to_numeric(ok[c], errors="coerce").mean()
    return pd.Series(row)


def summarize_seal(raw_dir, metrics_csv, agent, out_file):
    import glob
    files = sorted(glob.glob(os.path.join(raw_dir, f"{agent}*.csv")))
    if not files:
        sys.exit(f"[FAIL] no sweep CSVs for agent '{agent}' in {raw_dir}")
    df = pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)
    df = df[df["agent"] == agent].drop_duplicates(subset=["benchmark", "budget", "w_ops"], keep="last")
    df["w_ops"] = pd.to_numeric(df["w_ops"], errors="coerce").round(6)
    df["w_keys"] = pd.to_numeric(df["w_keys"], errors="coerce").round(6)
    for c in ("initial_exec_cost", "initial_keys_cost", "agent_exec_cost", "agent_keys_cost",
              "final_exec_cost", "final_keys_cost", "initial_est_noise", "budget"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    ie, ik = df["initial_exec_cost"], df["initial_keys_cost"].clip(lower=1)
    # cost = C_exec (the unified env's total cost); "agent" = raw agent output, "safe" = what was compiled
    # (run_unified.py rollback: best compliant step under w . costs, only when the agent violates the budget)
    df["agent_cost_red"] = 100 * (ie - df["agent_exec_cost"]) / ie
    df["safe_cost_red"] = 100 * (ie - df["final_exec_cost"]) / ie
    df["agent_keys_red"] = 100 * (df["initial_keys_cost"] - df["agent_keys_cost"]) / ik
    df["safe_keys_red"] = 100 * (df["initial_keys_cost"] - df["final_keys_cost"]) / ik
    df["feasible_start"] = ((df["budget"] >= 100_000) | (df["initial_est_noise"] <= df["budget"])).where(
        df["initial_est_noise"].notna())
    sheets = {}

    grid = df[df["source"] == "grid"]
    sheets["constrained_per_budget"] = df.groupby("budget").apply(_seal_agg).round(3).reset_index()
    sheets["constrained_per_budget_pref"] = grid.groupby(["budget", "w_ops", "w_keys"]).apply(_seal_agg).round(3).reset_index()
    sheets["constrained_per_benchmark"] = df.groupby(["benchmark", "budget"]).apply(_seal_agg).round(3).reset_index()
    sheets["status_counts"] = df.groupby(["budget", "status"]).size().rename("points").reset_index()
    print("== Constrained metrics (real SEAL execution) per budget ==")
    print(sheets["constrained_per_budget"][["budget", "Points", "OK (%)", "Feasible at start (%)",
                                            "Agent Compliance est. (%)", "Estimated Compliance (%)",
                                            "Measured Compliance (%)", "Rollback Rate (%)",
                                            "Agent Cost Red (%)", "Safe Cost Red (%)",
                                            "Agent Keys Red (%)", "Safe Keys Red (%)",
                                            "Min Remaining Noise (bits)"]].to_string(index=False))

    if metrics_csv and os.path.isfile(metrics_csv):
        m = pd.read_csv(metrics_csv)
        m = m[m["agent"] == agent]
        for c in ("IC", "HV", "SP", "EU", "measured_violation_rate", "est_violation_rate", "rollback_rate"):
            if c in m.columns:
                m[c] = pd.to_numeric(m[c], errors="coerce")
        cols = [c for c in ("IC", "HV", "SP", "EU", "measured_violation_rate", "est_violation_rate",
                            "rollback_rate") if c in m.columns]
        has = m["IC"].fillna(0) > 0
        per_b = m[has].groupby("budget")[cols].mean().round(4).reset_index()
        per_b.insert(1, "Benchmarks with front", m[has].groupby("budget").size().reindex(per_b["budget"]).values)
        sheets["morl_per_budget"] = per_b
        sheets["morl_per_benchmark"] = m
        print("\n== MORL metrics (measured time x key size) per budget ==")
        print(per_b.to_string(index=False))
    else:
        print(f"[warn] metrics.csv not found: {metrics_csv}")

    sheets["all_points"] = df
    with pd.ExcelWriter(out_file, engine="openpyxl") as w:
        for name, frame in sheets.items():
            frame.to_excel(w, sheet_name=name[:31], index=False)
    print(f"\n[summary] written to {out_file}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-benchmarks")
    b.add_argument("--datasets", required=True)
    b.add_argument("--out", required=True)
    s = sub.add_parser("summarize")
    s.add_argument("--constrained-csv", required=True)
    s.add_argument("--morl-xlsx", required=True)
    s.add_argument("--out", required=True)
    t = sub.add_parser("summarize-seal")
    t.add_argument("--raw-dir", required=True)
    t.add_argument("--metrics", required=True)
    t.add_argument("--agent", default="uniform")
    t.add_argument("--out", required=True)
    a = p.parse_args()
    if a.cmd == "build-benchmarks":
        build_benchmarks(a.datasets, a.out)
    elif a.cmd == "summarize-seal":
        summarize_seal(a.raw_dir, a.metrics, a.agent, a.out)
    else:
        summarize(a.constrained_csv, a.morl_xlsx, a.out)


if __name__ == "__main__":
    main()

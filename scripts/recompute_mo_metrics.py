#!/usr/bin/env python3
"""Recompute the multi-objective metrics (IC, HV, SP, EU) of a bisection run with
the definitions of the MORL manuscript (Section 5.5.2), from the saved probes.

Normalization, per benchmark (bounds over all probes of that benchmark, all budgets):
  T_hat = (C_exec - T_min) / (T_max - T_min)   T_min: best observed exec cost
                                               T_max: exec cost of the input program
  K_hat = C_keys / K_max                       K_max: most keys observed (0 -> K_hat = 0)
Metrics on the Pareto front of the feasible probes of one (benchmark, budget):
  IC = number of non-dominated points
  HV = dominated area w.r.t. z_ref = (1.1, 1.1), divided by 1.21     (higher is better)
  SP = mean squared distance between consecutive points, divided by 2 (lower is better)
  EU = mean over w_exec in [0, 1] of min over the front of w.(T_hat, K_hat) (lower is better)

With --grid-only, the front is built from the grid probes alone (no bisection).

Usage:
  python scripts/recompute_mo_metrics.py RL/test_results/results_nov2/bisection/<file>.xlsx \
      --benchmarks RL/fhe_rl/datasets/benchmarks.txt --names RL/fhe_rl/datasets/benchmarks_names.xlsx \
      --out mo_metrics.csv
"""
import argparse

import numpy as np
import pandas as pd

Z_REF = 1.1
EU_GRID = np.linspace(0.0, 1.0, 101)


def pareto(points):
    pts = sorted(set(points))
    front, best_k = [], float("inf")
    for t, k in pts:
        if k < best_k:
            front.append((t, k))
            best_k = k
    return front


def hypervolume(front):
    hv, prev_k = 0.0, Z_REF
    for t, k in front:  # sorted by t ascending, k descending
        if t < Z_REF and k < prev_k:
            hv += (Z_REF - t) * (prev_k - k)
            prev_k = k
    return hv / (Z_REF * Z_REF)


def sparsity(front):
    if len(front) < 2:
        return 0.0
    d = sum((front[i + 1][0] - front[i][0]) ** 2 + (front[i + 1][1] - front[i][1]) ** 2
            for i in range(len(front) - 1))
    return d / (len(front) - 1) / 2.0


def expected_utility(front):
    return float(np.mean([min(w * t + (1 - w) * k for t, k in front) for w in EU_GRID]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("workbook")
    p.add_argument("--benchmarks", required=True, help="expression file used for the run (expr_i = line i)")
    p.add_argument("--names", required=True, help="xlsx with columns Name, Expression")
    p.add_argument("--out", default="mo_metrics.csv")
    p.add_argument("--grid-only", action="store_true",
                   help="front from the grid probes only (bisection ablation); the normalization "
                        "bounds still use all probes, so both variants are on the same scale")
    args = p.parse_args()

    probes = pd.read_excel(args.workbook, "probes")
    exprs = [l.strip() for l in open(args.benchmarks) if l.strip()]
    names_df = pd.read_excel(args.names)
    by_expr = {str(e).strip(): n for n, e in zip(names_df["Name"], names_df["Expression"])}
    name_of = {f"expr_{i}": by_expr.get(e) for i, e in enumerate(exprs)}

    probes = probes[probes["feasible"] == True]  # noqa: E712
    rows = []
    for expr, g_all in probes.groupby("Expression"):
        name = name_of.get(expr)
        if name is None:
            continue
        t_max = float(g_all["Initial Ops"].iloc[0])
        t_min = float(g_all["final_exec_cost"].min())
        k_max = float(g_all["final_keys_cost"].max())
        span = max(t_max - t_min, 1e-9)
        if args.grid_only:
            g_all = g_all[g_all["phase"] == "grid"]
        for budget, g in g_all.groupby("Budget"):
            pts = [((t - t_min) / span, (k / k_max) if k_max > 0 else 0.0)
                   for t, k in zip(g["final_exec_cost"], g["final_keys_cost"])]
            front = pareto(pts)
            rows.append({"Budget": budget, "Benchmark": name, "Expression": expr,
                         "T_min": t_min, "T_max": t_max, "K_max": k_max,
                         "IC": len(front), "HV": hypervolume(front),
                         "SP": sparsity(front), "EU": expected_utility(front)})
    out = pd.DataFrame(rows).sort_values(["Budget", "Benchmark"])
    out.to_csv(args.out, index=False)
    print(out.groupby("Budget")[["IC", "HV", "SP", "EU"]].mean().round(4).to_string())
    print(f"saved {args.out} ({out['Benchmark'].nunique()} benchmarks)")


if __name__ == "__main__":
    main()

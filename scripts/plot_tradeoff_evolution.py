#!/usr/bin/env python3
"""Exp 3 figure: execution time and rotation key size vs. the key weight w_keys.

Reads the end-to-end benchmark CSVs written by scripts/run_benchmarks_unified.py
(one row per benchmark x preference x budget) and plots, for one noise budget:
  - left axis:  execution time, relative to w_keys = 0 (geometric mean over
                benchmarks), or the plain average in seconds with --seconds
  - right axis: average rotation key size (MB)

Usage:
  python scripts/plot_tradeoff_evolution.py RL/test_results/results_nov2/e2e \
      --budget 369 --out <paper>/figures/tradeoff-evolution.pdf
"""
import argparse
import csv
import glob
import math
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

EXEC_COL = "circuit_execution_time (s)"
KEYS_COL = "rotation_keys_size (MB)"


def load(results_dir, budget):
    rows = []
    for path in glob.glob(os.path.join(results_dir, f"*_b{budget}_*.csv")):
        with open(path, newline="") as f:
            rows += [r for r in csv.DictReader(f) if r.get("status") == "ok"]
    if not rows:
        raise SystemExit(f"no rows for budget {budget} in {results_dir}")
    return rows


def aggregate(rows, seconds):
    by_w = defaultdict(list)
    for r in rows:
        by_w[round(float(r["w_keys"]), 2)].append(r)
    ws = sorted(by_w)
    ref = {r["benchmark"]: float(r[EXEC_COL]) for r in by_w[ws[0]]}
    exec_vals, key_vals = [], []
    for w in ws:
        group = by_w[w]
        if seconds:
            exec_vals.append(sum(float(r[EXEC_COL]) for r in group) / len(group))
        else:
            logs = [math.log(float(r[EXEC_COL]) / ref[r["benchmark"]])
                    for r in group if ref.get(r["benchmark"], 0) > 0]
            exec_vals.append(math.exp(sum(logs) / len(logs)))
        key_vals.append(sum(float(r[KEYS_COL] or 0) for r in group) / len(group))
    return ws, exec_vals, key_vals


def plot(ws, exec_vals, key_vals, seconds, out):
    red, blue = "#b2182b", "#2166ac"
    fig, ax1 = plt.subplots(figsize=(6.0, 3.0))
    ax1.plot(ws, exec_vals, "o-", color=red, lw=2, label="Execution time")
    ax1.set_xlabel(r"Key weight $w_{\mathrm{keys}}$")
    ax1.set_ylabel("Execution time (s)" if seconds else "Relative execution time", color=red)
    ax1.tick_params(axis="y", colors=red)
    ax1.set_xticks(ws)
    ax1.grid(alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(ws, key_vals, "s--", color=blue, lw=2, label="Rotation key size")
    ax2.set_ylabel("Rotation key size (MB)", color=blue)
    ax2.tick_params(axis="y", colors=blue)
    ax2.set_ylim(bottom=0)

    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [l.get_label() for l in lines], loc="center right", frameon=False)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    print(f"saved {out}")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("results_dir")
    p.add_argument("--budget", default="369")
    p.add_argument("--seconds", action="store_true",
                   help="plot the average execution time in seconds instead of the relative one")
    p.add_argument("--out", default="tradeoff-evolution.pdf")
    args = p.parse_args()

    ws, exec_vals, key_vals = aggregate(load(args.results_dir, args.budget), args.seconds)
    for w, e, k in zip(ws, exec_vals, key_vals):
        print(f"w_keys={w:.1f}  exec={e:.3f}  keys_MB={k:.2f}")
    plot(ws, exec_vals, key_vals, args.seconds, args.out)


if __name__ == "__main__":
    main()

"""Experiment 2: joint (unified) vs. separated optimization at w_exec in {1.0, 0.9, 0.8, 0.6}.

Input : exp2_results.csv with columns
        benchmark, w_exec, joint_time_s, joint_keys, separated_time_s, separated_keys
        (one row per benchmark and preference; use the rollback-selected 'Safe' outputs of both pipelines)
Output: figures/joint_vs_separated_trend.pdf  - average execution time and key size per preference
        figures/joint_vs_separated_bench.pdf  - per-benchmark execution time and key size at one preference
        printed numbers for the text, and the list of kernels where joint dominates separated
Usage : python plot_joint_vs_separated.py [exp2_results.csv]
"""
import csv, math, os, sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

KEY_MB = 18            # serialized size of one Galois key (MB); confirm for your parameters
W_BENCH = 0.8          # preference shown in the per-benchmark figure
PLACEHOLDER = True     # set to False once the CSV holds real results
C_JOINT, C_SEP = "blue", "orange"
L_JOINT, L_SEP = "Joint (unified)", "Separated"

path = sys.argv[1] if len(sys.argv) > 1 else "exp2_results.csv"
rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
for r in rows:
    for k in ("w_exec", "joint_time_s", "joint_keys", "separated_time_s", "separated_keys"):
        r[k] = float(r[k])
prefs = sorted({r["w_exec"] for r in rows}, reverse=True)
bench = list(dict.fromkeys(r["benchmark"] for r in rows))
os.makedirs("figures", exist_ok=True)
plt.rcParams.update({"font.size": 7})

def watermark(fig):
    if PLACEHOLDER:
        fig.text(0.5, 0.5, "PLACEHOLDER DATA", fontsize=26, color="gray", alpha=0.15,
                 ha="center", va="center", rotation=12)

# ---------- Figure A: averages per preference (as Fig. 5.9 of the thesis) ----------
def avg(key, w):
    v = [r[key] for r in rows if r["w_exec"] == w]
    return sum(v) / len(v)
fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.0))
xs = [f"[{w:g}, {1 - w:.1g}]" for w in prefs]
for ax, key, ylabel, scale in [(axes[0], "time_s", "Avg. execution time (s)", 1),
                                (axes[1], "keys", "Avg. rotation key size (MB)", KEY_MB)]:
    ax.plot(xs, [avg("joint_" + key, w) * scale for w in prefs], "o-", color=C_JOINT, label=L_JOINT, lw=1.2, ms=3.5)
    ax.plot(xs, [avg("separated_" + key, w) * scale for w in prefs], "s--", color=C_SEP, label=L_SEP, lw=1.2, ms=3.5)
    ax.set_xlabel(r"Preference $\vec{w}$"); ax.set_ylabel(ylabel)
    ax.grid(linestyle="--", linewidth=0.3)
axes[0].legend(fontsize=6.5, frameon=False)
watermark(fig); fig.tight_layout()
fig.savefig("figures/joint_vs_separated_trend.pdf", bbox_inches="tight")
fig.savefig("figures/joint_vs_separated_trend.png", dpi=300, bbox_inches="tight")

# ---------- Figure B: per benchmark at W_BENCH (CHEHAB RL style) ----------
sel = {r["benchmark"]: r for r in rows if r["w_exec"] == W_BENCH}
x = np.arange(len(bench)); w = 0.38
fig, axes = plt.subplots(2, 1, figsize=(5.5, 3.4), sharex=True)
for ax, key, ylabel, scale, log in [(axes[0], "time_s", "Execution Time (s)", 1, True),
                                     (axes[1], "keys", "Rotation Key\nSize (MB)", KEY_MB, False)]:
    ax.bar(x - w / 2, [sel[b]["joint_" + key] * scale for b in bench], w, color=C_JOINT, label=L_JOINT)
    ax.bar(x + w / 2, [sel[b]["separated_" + key] * scale for b in bench], w, color=C_SEP, label=L_SEP)
    ax.set_ylabel(ylabel); ax.tick_params(axis="y", labelsize=6)
    ax.grid(axis="y", linestyle="--", linewidth=0.3); ax.set_axisbelow(True)
    if log: ax.set_yscale("log")
axes[0].legend(fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, 1.22), ncol=2, frameon=False)
axes[1].set_xticks(x); axes[1].set_xticklabels(bench, rotation=60, ha="right", rotation_mode="anchor", fontsize=5)
axes[1].set_xlim(-0.5, len(x) - 0.5)
watermark(fig); fig.tight_layout(h_pad=0.4)
fig.savefig("figures/joint_vs_separated_bench.pdf", bbox_inches="tight")
fig.savefig("figures/joint_vs_separated_bench.png", dpi=300, bbox_inches="tight")

# ---------- numbers for the text ----------
def dom(a_t, a_k, b_t, b_k):
    return a_t <= b_t and a_k <= b_k and (a_t < b_t or a_k < b_k)
cnt = defaultdict(int); cases = []
for r in rows:
    j = (r["joint_time_s"], r["joint_keys"]); s = (r["separated_time_s"], r["separated_keys"])
    if dom(*j, *s): cnt["joint"] += 1; cases.append(r)
    elif dom(*s, *j): cnt["separated"] += 1
    elif j == s: cnt["equal"] += 1
    else: cnt["tradeoff"] += 1
n = len(rows)
print(f"{len(bench)} benchmarks x {len(prefs)} preferences = {n} cases")
print(f"joint dominates: {cnt['joint']}, separated dominates: {cnt['separated']}, equal: {cnt['equal']}, trade-off: {cnt['tradeoff']}")
for wv in prefs:
    jt, st = avg("joint_time_s", wv), avg("separated_time_s", wv)
    jk, sk = avg("joint_keys", wv) * KEY_MB, avg("separated_keys", wv) * KEY_MB
    print(f"w_exec={wv:g}: avg time joint {jt:.3f}s vs sep {st:.3f}s ({100*(st/jt-1):+.1f}%), "
          f"avg keys joint {jk:.1f}MB vs sep {sk:.1f}MB")
gm = lambda v: math.exp(sum(map(math.log, v)) / len(v))
print("geomean time ratio sep/joint:", f"{gm([r['separated_time_s']/r['joint_time_s'] for r in rows]):.3f}")
print("\nKernels where joint dominates (largest separated/joint time ratio first):")
by_b = defaultdict(list)
for r in cases: by_b[r["benchmark"]].append(r)
ranked = sorted(by_b.items(), key=lambda kv: -max(r["separated_time_s"] / r["joint_time_s"] for r in kv[1]))
for b, rs in ranked:
    print(f"  {b:<18} at w_exec in {sorted({r['w_exec'] for r in rs}, reverse=True)}")
with open("exp2_joint_dominates.csv", "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["benchmark","w_exec","joint_time_s","joint_keys","separated_time_s","separated_keys"])
    for r in cases: wr.writerow([r["benchmark"], r["w_exec"], r["joint_time_s"], int(r["joint_keys"]), r["separated_time_s"], int(r["separated_keys"])])

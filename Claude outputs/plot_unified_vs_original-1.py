"""Experiment 1 figure (CMO-RL vs. CHEHAB RL + rotation key selection), in the style of the CHEHAB RL paper.

Input : exp1_results.csv with columns
        benchmark, chehabrl_noise_bits, cmorl_noise_bits, chehabrl_time_s, cmorl_time_s, chehabrl_keys, cmorl_keys
Output: figures/unified_vs_original.pdf (+ .png preview), and the numbers quoted in the text (printed).
Usage : python plot_unified_vs_original.py [path/to/exp1_results.csv]
"""
import csv, math, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BUDGET = 230         # noise budget B in bits
KEY_MB = 18          # serialized size of one Galois key in MB (confirm for your parameters)
PLACEHOLDER = True   # set to False once the CSV holds real results (removes the watermark)

path = sys.argv[1] if len(sys.argv) > 1 else "exp1_results.csv"
with open(path, newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
bench = [r["benchmark"] for r in rows]
col = lambda k: np.array([float(r[k]) for r in rows])
bn, cn = col("chehabrl_noise_bits"), col("cmorl_noise_bits")
bt, ct = col("chehabrl_time_s"), col("cmorl_time_s")
bk, ck = col("chehabrl_keys"), col("cmorl_keys")

# Colors and layout follow the CHEHAB RL paper figures (blue / orange, 24x3 per panel, log scale for time).
C_BASE, C_OURS = "orange", "blue"
L_BASE, L_OURS = "CHEHAB RL + key sel.", "CMO-RL"
HATCH_COLOR = (0.6, 0.6, 0.6, 1.0)
x = np.arange(len(bench)); w = 0.38

# Drawn at the real text width of the acmsmall format (~5.4 in), so font sizes are the printed sizes.
plt.rcParams.update({"font.size": 7})
fig, axes = plt.subplots(3, 1, figsize=(5.5, 4.6), sharex=True)

def pair(ax, base, ours, ylabel, log=False):
    ax.bar(x - w / 2, ours, w, color=C_OURS, label=L_OURS)
    bars = ax.bar(x + w / 2, base, w, color=C_BASE, label=L_BASE)
    ax.set_ylabel(ylabel, fontsize=7)
    ax.tick_params(axis="y", labelsize=6)
    ax.grid(axis="y", linestyle="--", linewidth=0.3, which="major")
    ax.set_axisbelow(True)
    if log:
        ax.set_yscale("log")
    return bars

# (a) consumed noise budget; hatched orange bars violate the budget
bars = pair(axes[0], bn, cn, "Consumed Noise\nBudget (bits)")
for b, v in zip(bars, bn > BUDGET):
    if v:
        b.set_hatch("////"); b._hatch_color = HATCH_COLOR
axes[0].axhline(BUDGET, color="red", linestyle="--", linewidth=0.8)
viol = axes[0].bar(0, 0, color="none", hatch="//", edgecolor=HATCH_COLOR, label="Budget violation")
axes[0].plot([], [], color="red", linestyle="--", label=f"Noise budget $B$ = {BUDGET} bits")
axes[0].set_ylim(0, max(bn.max(), cn.max(), BUDGET) * 1.15)
axes[0].legend(fontsize=6.5, loc="upper center", bbox_to_anchor=(0.5, 1.30), ncol=4, frameon=False, handlelength=1.8)

# (b) execution time, semi-log as in CHEHAB RL
pair(axes[1], bt, ct, "Execution Time (s)", log=True)
# (c) rotation key size
pair(axes[2], bk * KEY_MB, ck * KEY_MB, "Rotation Key\nSize (MB)")

axes[2].set_xticks(x)
axes[2].set_xticklabels(bench, rotation=60, ha="right", rotation_mode="anchor", fontsize=5)
axes[2].set_xlim(-0.5, len(x) - 0.5)
if PLACEHOLDER:
    fig.text(0.5, 0.55, "PLACEHOLDER DATA", fontsize=30, color="gray", alpha=0.15, ha="center", va="center", rotation=12)
fig.tight_layout(h_pad=0.4)
os.makedirs("figures", exist_ok=True)
fig.savefig("figures/unified_vs_original.pdf", bbox_inches="tight")
fig.savefig("figures/unified_vs_original.png", dpi=300, bbox_inches="tight")

# ---- numbers quoted in the text -------------------------------------------------
n = len(bench); vb = bn > BUDGET; vc = cn > BUDGET
over = (bn - BUDGET) / BUDGET
i_max = int(np.argmax(over))
sp = bt / ct
gm = math.exp(np.mean(np.log(sp)))
slower = [(bench[i], ct[i] - bt[i], 100 * (ct[i] / bt[i] - 1)) for i in range(n) if sp[i] < 1]
i_sp = int(np.argmax(sp))
print(f"benchmarks: {n}")
print(f"violations CHEHAB RL: {vb.sum()}/{n}, CMO-RL: {vc.sum()}/{n}")
print(f"max overshoot: {100*over[i_max]:.1f}% on {bench[i_max]} ({bn[i_max]:.0f} bits)")
print(f"CMO-RL equal or faster on {(sp >= 1).sum()}/{n}; geomean speedup {gm:.2f}x; max {sp[i_sp]:.2f}x on {bench[i_sp]}")
print("CMO-RL slower on:", ", ".join(f"{b} (+{d*1000:.0f} ms, +{p:.1f}%)" for b, d, p in slower) or "none")
print(f"keys: CMO-RL {ck.sum():.0f} ({ck.sum()*KEY_MB:.0f} MB) vs CHEHAB RL {bk.sum():.0f} ({bk.sum()*KEY_MB:.0f} MB), "
      f"reduction {100*(1-ck.sum()/bk.sum()):.0f}%; fewer-or-equal keys on {(ck <= bk).sum()}/{n}")

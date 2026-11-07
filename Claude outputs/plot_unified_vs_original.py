"""Experiment 1 figure: CHEHAB RL + rotation key selection vs. CHEHAB (CMO-RL).

Replace the PLACEHOLDER values below with your measured results, then run:
    python plot_unified_vs_original.py
It writes figures/unified_vs_original.pdf (vector, for the paper) and .png (preview).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

BUDGET = 230          # noise budget B in bits  (PLACEHOLDER)
PLACEHOLDER = True    # set to False once the data below is real (removes the watermark)
KEY_MB = 18           # serialized size of one Galois key in MB (confirm for your parameters)

benchmarks = ["Dot Product 16", "Dot Product 32", "L2 Distance 16", "L2 Distance 32",
              "Hamm. Dist. 16", "Hamm. Dist. 32", "Poly. Reg. 8", "Linear Reg. 8",
              "Box Blur 4", "Mat. Mul. 4", "Gx 4", "Max 4", "Sort 3", "tree-100-50-5"]

# ---- PLACEHOLDER DATA: replace with real results --------------------------------
base_noise = [241, 258, 236, 262, 247, 271, 219, 188, 205, 252, 214, 233, 239, 266]
ours_noise = [224, 227, 221, 229, 226, 228, 212, 188, 203, 226, 210, 225, 229, 228]
base_time  = [412, 655, 430, 790, 980, 1490, 315, 140, 96, 512, 530, 1210, 1380, 2010]  # ms
ours_time  = [405, 641, 431, 772, 951, 1402, 309, 140, 92, 498, 521, 1188, 1366, 1985]  # ms
base_keys  = [5, 6, 5, 6, 5, 7, 2, 2, 3, 4, 3, 5, 5, 6]
ours_keys  = [3, 4, 3, 4, 4, 4, 2, 1, 2, 3, 2, 4, 4, 4]
# ---------------------------------------------------------------------------------

BASE_LABEL, OURS_LABEL = "CHEHAB RL + key sel.", r"CMO-RL ($\vec{w}=[0.9, 0.1]$)"
BASE_COLOR, OURS_COLOR = "tab:orange", "tab:blue"

x = np.arange(len(benchmarks))
w = 0.38
fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)

def bars(ax, base, ours, ylabel, title):
    ax.bar(x - w / 2, ours, w, label=OURS_LABEL, color=OURS_COLOR)
    ax.bar(x + w / 2, base, w, label=BASE_LABEL, color=BASE_COLOR)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    ax.set_axisbelow(True)

bars(axes[0], np.array(base_noise) / BUDGET, np.array(ours_noise) / BUDGET,
     "Noise / budget", "Noise Consumption")
axes[0].axhline(1.0, color="red", linestyle="--", linewidth=1.2, label=f"Budget ($B$ = {BUDGET} bits)")
axes[0].set_ylim(0.7, 1.25)

bars(axes[1], base_time, ours_time, "Execution time (ms)", "Execution Time")
bars(axes[2], np.array(base_keys) * KEY_MB, np.array(ours_keys) * KEY_MB,
     "Rotation key size (MB)", "Rotation Key Size")

axes[2].set_xticks(x)
axes[2].set_xticklabels(benchmarks, rotation=45, ha="right")
axes[2].set_xlabel("Benchmark")
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.03))
if PLACEHOLDER:
    fig.text(0.5, 0.5, "PLACEHOLDER DATA", fontsize=48, color="gray", alpha=0.15,
             ha="center", va="center", rotation=20)
fig.tight_layout()
fig.savefig("figures/unified_vs_original.pdf", bbox_inches="tight")
fig.savefig("figures/unified_vs_original.png", dpi=200, bbox_inches="tight")
print("written figures/unified_vs_original.{pdf,png}")

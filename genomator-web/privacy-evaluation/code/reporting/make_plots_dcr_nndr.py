#!/usr/bin/env python3
import json
import math
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # repo root
PLOTS = os.path.join(ROOT, "results", "plots_dcr_nndr")
os.makedirs(PLOTS, exist_ok=True)

rows = json.load(open(os.path.join(ROOT, "data", "results_summary.json")))


def nz(xs):
    return [math.nan if x is None else x for x in xs]


BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
SURFACE = "#fcfcfb"
GRID = "#e3e2dd"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": TEXT_PRIMARY, "axes.edgecolor": GRID, "axes.labelcolor": TEXT_SECONDARY,
    "xtick.color": TEXT_SECONDARY, "ytick.color": TEXT_SECONDARY, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.8, "font.size": 11, "font.family": "sans-serif",
})


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis="y", zorder=0)
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)


def sweep(filter_fn, key):
    return sorted((r for r in rows if filter_fn(r)), key=lambda r: r[key])


sel = sweep(lambda r: r["N"] == 150 and r["Z"] == 1.5 and r["no_biasing"], "L")
L = [r["L"] for r in sel]

# 2. DCR/NNDR flagged fraction vs looseness
flag1 = nz([r["flagged_1pct_mean"] for r in sel])
flag5 = nz([r["flagged_5pct_mean"] for r in sel])
fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200)
ax.plot(L, flag5, color=BLUE, linewidth=2, marker="o", markersize=7, label="Flagged fraction (5% cutoff)")
ax.plot(L, flag1, color=AQUA, linewidth=2, marker="o", markersize=7, label="Flagged fraction (1% cutoff)")
ax.set_ylim(-0.03, 1.05)
ax.set_xlabel("Looseness L  (N=150, Z=1.5)")
ax.set_ylabel("Flagged fraction of synthetic individuals")
style_axes(ax)
ax.legend(frameon=False, loc="upper right", fontsize=9.5)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "flagged_fraction_vs_looseness.png"))
plt.close(fig)

# 3. DCR ratio / NNDR distance stats vs looseness
dcr_ratio = [r["dcr_ratio_median_mean"] for r in sel]
nndr = [r["nndr_median_mean"] for r in sel]
fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200)
ax.plot(L, dcr_ratio, color=BLUE, linewidth=2, marker="o", markersize=7, label="DCR ratio")
ax.plot(L, nndr, color=ORANGE, linewidth=2, marker="o", markersize=7, label="NNDR")
ax.axhline(1.0, color=GRID, linewidth=1.2, zorder=0)
ax.set_ylim(0.35, 1.02)
ax.set_xlabel("Looseness L  (N=150, Z=1.5)")
ax.set_ylabel("DCR ratio / NNDR")
style_axes(ax)
ax.legend(frameon=False, loc="lower right", fontsize=9.5)
fig.tight_layout()
fig.savefig(os.path.join(PLOTS, "dcr_distance_stats_vs_looseness.png"))
plt.close(fig)

print("wrote 2 plots to", PLOTS)

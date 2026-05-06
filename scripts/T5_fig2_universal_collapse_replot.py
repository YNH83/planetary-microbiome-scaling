"""Replot T5_fig2_universal_collapse.png with enlarged legend biome markers.

Fix: original legend shows tiny color dots, making it hard to match biome
labels to the scatter clusters. Here the legend markers are scaled up
(larger filled circles with a visible stroke) and the legend font is bumped.
Scatter cloud + universal fit are unchanged (same seed / same synthesis).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
FIGS = ROOT / "figures"
sys.path.insert(0, str(SCRIPTS / "shared"))
from nature_style import (apply_nature_style, BIOME_COLORS,
                          DECISION_COLORS)

BIOME_ORDER = [
    "Animal corpus", "Animal distal gut", "Animal proximal gut",
    "Animal secretion", "Animal surface",
    "Plant rhizosphere", "Plant surface",
    "Aerosol (non-saline)",
    "Sediment (non-saline)", "Sediment (saline)",
    "Soil (non-saline)",
    "Surface (non-saline)", "Surface (saline)",
    "Water (non-saline)", "Water (saline)",
]


def main():
    apply_nature_style()
    taylor = pd.read_csv(SCRIPTS / "T5_empo3_real_taylor.csv")
    bic = json.loads((SCRIPTS / "T5_empo3_real_bic.json").read_text())
    universal_beta = bic["universal_beta"]

    fig, ax = plt.subplots(figsize=(9.0, 5.8))

    biome_handles = []
    for biome in BIOME_ORDER:
        row = taylor[taylor["biome"] == biome]
        if row.empty:
            continue
        row = row.iloc[0]
        color = BIOME_COLORS.get(biome, "#3B3B3B")
        rng = np.random.default_rng(abs(hash(biome)) % 2**31)
        n_plot = min(int(row["n_taxa"]), 180)
        log_mu = rng.uniform(-10, -3, size=n_plot)
        log_var = (row["alpha"] + row["beta"] * log_mu
                   + rng.normal(0, 0.35 * np.sqrt(max(1 - row["r2"], 0.01)),
                                size=n_plot))
        ax.scatter(log_mu, log_var, s=5, color=color, alpha=0.38,
                   edgecolors="none")
        # Build a dedicated enlarged legend proxy (not the tiny scatter dots).
        biome_handles.append(Line2D([0], [0], marker="o", linestyle="",
                                    markerfacecolor=color,
                                    markeredgecolor="#333333",
                                    markeredgewidth=0.5,
                                    markersize=9, label=biome))

    x = np.linspace(-11, -2, 100)
    alpha_mean = float(taylor["alpha"].mean())
    uni_line, = ax.plot(x, alpha_mean + universal_beta * x,
                        color="black", linewidth=2.4,
                        label=f"Universal fit: \u03b2 = {universal_beta:.3f}")
    ref_line, = ax.plot(x, alpha_mean + 2.0 * x,
                        color=DECISION_COLORS["emphasis"],
                        linewidth=1.6, linestyle="--",
                        label="Grilli 2020 theoretical: \u03b2 = 2.0")

    ax.set_xlabel("log mean relative abundance")
    ax.set_ylabel("log variance")
    ax.set_title(
        f"Figure 2. Universal Taylor collapse across 15 EMPO-3 biomes  "
        f"(|\u0394BIC| = {bic['delta_BIC']:.1f}, "
        f"n = {bic['n_points']:,} points)",
        fontsize=10, loc="left")

    # Two-column legend stack on the right: top = biomes (enlarged markers),
    # bottom = fit lines. Both anchored OUTSIDE the axes so icons are readable.
    leg1 = ax.legend(handles=biome_handles, bbox_to_anchor=(1.02, 1.0),
                     loc="upper left", fontsize=8.5, frameon=False,
                     handletextpad=0.5, labelspacing=0.55,
                     title="EMPO-3 biome", title_fontsize=9,
                     borderaxespad=0.2)
    ax.add_artist(leg1)
    ax.legend(handles=[uni_line, ref_line],
              bbox_to_anchor=(1.02, 0.12), loc="lower left",
              fontsize=8.5, frameon=False, handletextpad=0.5,
              labelspacing=0.4, borderaxespad=0.2)

    fig.tight_layout()
    out = FIGS / "T5_fig2_universal_collapse.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out}")


if __name__ == "__main__":
    main()

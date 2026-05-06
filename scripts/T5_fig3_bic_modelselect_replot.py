"""Replot T5_fig3_bic_modelselect.png and T5_fig3_bic_modelselect_v2.png.

Fixes:
  1. Delta annotation no longer overlaps the bars. It now sits in the
     empty space above the shorter bar (closer to y = 0) with a white
     bbox so it remains legible.
  2. Legend no longer covers the bars. It is moved outside the axes,
     anchored below the plot as a single horizontal strip.

Reads BIC values from T5_pilot_results.json / T5_pilot_results_v0_2.json
so the underlying simulation does not have to be rerun.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
FIGS = ROOT / "figures"


def _bic_pairs(json_path: Path):
    d = json.loads(json_path.read_text())
    a = d["scenario_A_universal"]
    b = d["scenario_B_biome_specific"]
    return {"A": (a["bic_universal"], a["bic_biome_specific"]),
            "B": (b["bic_universal"], b["bic_biome_specific"])}


def fig_bic(bic_pairs, out_path: Path, title: str):
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    labels = ["Scenario A\n(true universal)", "Scenario B\n(true biome-specific)"]
    uni = np.array([bic_pairs["A"][0], bic_pairs["B"][0]], dtype=float)
    spec = np.array([bic_pairs["A"][1], bic_pairs["B"][1]], dtype=float)
    x_pos = np.arange(len(labels))
    w = 0.35

    ax.bar(x_pos - w / 2, uni, w, label="Universal (2 params)",
           color="#2ca02c")
    ax.bar(x_pos + w / 2, spec, w, label="Biome-specific (10 params)",
           color="#d62728")

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels)
    ax.set_ylabel("BIC (lower = better)")
    ax.set_title(title, fontsize=11)
    ax.grid(axis="y", alpha=0.3)

    # Bars extend from y = 0 downward, so the only truly empty vertical
    # band is ABOVE y = 0. Carve out a positive headroom strip and place
    # the delta labels there, well clear of any bar top.
    y_min = float(min(uni.min(), spec.min()))
    headroom = 0.12 * abs(y_min)
    ax.set_ylim(top=headroom, bottom=y_min * 1.05)
    label_y = 0.5 * headroom
    for i, (u, s) in enumerate(zip(uni, spec)):
        ax.annotate(f"\u0394 = {s - u:+.0f}",
                    xy=(x_pos[i], label_y),
                    ha="center", va="center", fontsize=10,
                    bbox=dict(facecolor="white", edgecolor="#bbbbbb",
                              alpha=0.95, pad=3.0, lw=0.5))
    # Horizontal guide at y = 0 to separate label band from bars.
    ax.axhline(0, color="#888888", lw=0.6)

    # Legend OUTSIDE the axes: single horizontal strip below the x-axis
    # labels so neither bar nor scenario title is occluded.
    ax.legend(fontsize=9, loc="upper center",
              bbox_to_anchor=(0.5, -0.18), ncol=2, frameon=False)

    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out_path}")


def main():
    # v1
    v1 = _bic_pairs(SCRIPTS / "T5_pilot_results.json")
    fig_bic(v1, FIGS / "T5_fig3_bic_modelselect.png",
            "Model selection: universal vs biome-specific Taylor's Law")
    # v2
    v2 = _bic_pairs(SCRIPTS / "T5_pilot_results_v0_2.json")
    fig_bic(v2, FIGS / "T5_fig3_bic_modelselect_v2.png",
            "v0.2 Model selection: universal vs biome-specific Taylor "
            "(native SDE)")


if __name__ == "__main__":
    main()

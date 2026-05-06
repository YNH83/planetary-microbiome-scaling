"""
T5 sensitivity sweep 1: prevalence threshold.

Refit universal Taylor beta across 15 EMPO-3 biomes (EMP 90 bp deblur) at
prevalence thresholds {0.05, 0.10, 0.20 (canonical), 0.30, 0.50}. For each
threshold, report the universal beta with 95 percent CI, R squared, and
points used.

Outputs:
    scripts/T5_sens_prevalence.csv
    figures/T5_sens_prevalence.png
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
FIGS = ROOT / "figures"
sys.path.insert(0, str(SCRIPTS / "shared"))
from nature_style import apply_nature_style, DECISION_COLORS, NPG_PALETTE  # noqa: E402
from t5_sens_core import (  # noqa: E402
    load_emp, load_meta, biome_sample_indices,
    taylor_fit_sparse, universal_slope,
)
apply_nature_style()

THRESHOLDS = [0.05, 0.10, 0.20, 0.30, 0.50]
CANONICAL = 0.20


def main():
    print("[load] EMP 90 bp deblur")
    M, obs_ids, samp_ids, tax = load_emp()
    meta = load_meta()
    biome_idx = biome_sample_indices(meta, samp_ids, min_biome_samples=50)
    print(f"[biomes] {len(biome_idx)} usable biomes")

    rows = []
    for prev in THRESHOLDS:
        print(f"\n[prev={prev:.2f}] fitting per-biome Taylor laws")
        fits = {}
        for biome, cols in biome_idx.items():
            sub = M[:, cols]
            f = taylor_fit_sparse(sub, min_prev=prev, min_taxa=30)
            if f is None:
                print(f"  skip {biome[:30]:30s} (insufficient taxa)")
                continue
            fits[biome] = f
        u = universal_slope(fits)
        if u is None:
            print("  [warn] universal fit failed")
            continue
        row = dict(
            prevalence=prev,
            canonical=(prev == CANONICAL),
            universal_beta=u["universal_beta"],
            beta_se=u["universal_beta_se"],
            beta_ci_lo=u["universal_beta_ci_lo"],
            beta_ci_hi=u["universal_beta_ci_hi"],
            r2=u["r2"],
            n_points=u["n_points"],
            n_biomes=u["n_biomes"],
            mean_n_taxa=int(np.mean([fits[b]["n_taxa"] for b in fits])),
        )
        rows.append(row)
        print(f"  \u03b2 = {row['universal_beta']:.4f} "
              f"[{row['beta_ci_lo']:.4f}, {row['beta_ci_hi']:.4f}], "
              f"R\u00b2 = {row['r2']:.3f}, n = {row['n_points']}, "
              f"biomes = {row['n_biomes']}")

    df = pd.DataFrame(rows)
    csv_path = SCRIPTS / "T5_sens_prevalence.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n[csv] {csv_path}")

    # Figure
    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    x = df["prevalence"].values
    y = df["universal_beta"].values
    yerr_lo = y - df["beta_ci_lo"].values
    yerr_hi = df["beta_ci_hi"].values - y
    ax.errorbar(x, y, yerr=[yerr_lo, yerr_hi],
                fmt="o", color=DECISION_COLORS["baseline"],
                ecolor="#888", capsize=3, elinewidth=0.8, markersize=6,
                zorder=3, label="universal \u03b2 (95% CI)")
    # canonical marker
    canon = df[df["canonical"]]
    if len(canon):
        ax.scatter(canon["prevalence"], canon["universal_beta"],
                   s=120, facecolors="none",
                   edgecolors=DECISION_COLORS["emphasis"], linewidths=1.5,
                   zorder=4, label="canonical (0.20)")
    ax.axhline(1.966, color=DECISION_COLORS["emphasis"], ls="--",
               lw=1.0, label="EMP canonical \u03b2 = 1.966")
    ax.axhspan(1.85, 2.05, color="#ddd", alpha=0.35,
               label="tolerance band [1.85, 2.05]")
    ax.set_xlabel("Prevalence threshold")
    ax.set_ylabel("Universal Taylor exponent \u03b2")
    ax.set_title("T5 sensitivity: prevalence filter",
                 loc="left")
    ax.set_xticks(THRESHOLDS)
    ax.set_xticklabels([f"{t:.2f}" for t in THRESHOLDS])
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7,
              frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGS / "T5_sens_prevalence.png")
    plt.close(fig)
    print(f"[figure] {FIGS / 'T5_sens_prevalence.png'}")


if __name__ == "__main__":
    main()

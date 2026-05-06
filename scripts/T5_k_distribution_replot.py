"""Replot figures/T5_k_distribution.png so the Kruskal-Wallis / Levene
stat box on panel A does not overlap the top ridgeline densities, and
the Wald chi-square box on panel B stays clear of the beta forest.

Fix strategy: add a fixed-height white "annotation strip" above the
data region of each panel (by extending ylim) and anchor both stat
boxes to that strip. The bbox sits above every density / marker, so
overlap is impossible regardless of data magnitude.

Reads scripts/T5_empo3_real_moments.csv + scripts/T5_k_distribution.csv
and reruns only the stat tests (fast) + the figure.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
FIGS = ROOT / "figures"

MOMENTS = SCRIPTS / "T5_empo3_real_moments.csv"
KDF = SCRIPTS / "T5_k_distribution.csv"
TESTS = SCRIPTS / "T5_k_distribution_tests.json"

plt.rcParams.update({
    "font.family": "Arial",
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
})
NPG15 = ["#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F",
         "#8491B4", "#91D1C2", "#DC0000", "#7E6148", "#B09C85",
         "#B2182B", "#2166AC", "#762A83", "#1B7837", "#D6604D"]


def fmt_p(p: float, digits: int = 2) -> str:
    """Format p-value; guard against float underflow to 0.0."""
    if p == 0.0:
        return "< 2.2e-308"
    return f"{p:.{digits}e}"


def main():
    m = pd.read_csv(MOMENTS)
    m["K_hat"] = m["mean"]
    m["log10_K"] = np.log10(m["K_hat"])
    kdf = pd.read_csv(KDF).sort_values("logK_med").reset_index(drop=True)
    tests = json.loads(TESTS.read_text()) if TESTS.exists() else None

    # Recompute the two group tests cheaply (same arrays).
    biomes_all = sorted(m["biome"].unique())
    groups = [m[m["biome"] == b]["log10_K"].values for b in biomes_all]
    H, p_kw = stats.kruskal(*groups)
    Wlev, p_lev = stats.levene(*groups)

    betas = kdf["beta"].values
    betas_se = kdf["beta_se"].values
    z2 = ((betas - 2) / betas_se) ** 2
    chi2 = float(z2.sum())
    df_x = len(betas)
    p_invar = float(stats.chi2.sf(chi2, df=df_x))
    beta_range = (float(betas.min()), float(betas.max()))
    beta_cv = float(np.std(betas, ddof=1) / np.mean(betas))

    # --------- figure -------------------------------------------------
    fig, (axA, axB) = plt.subplots(1, 2, figsize=(12, 5.6),
                                   gridspec_kw=dict(width_ratios=[1.5, 1.0]))
    x_grid = np.linspace(m["log10_K"].min() - 0.3,
                         m["log10_K"].max() + 0.3, 400)

    max_off = 0.0
    for i, b in enumerate(kdf["biome"]):
        vals = m[m["biome"] == b]["log10_K"].values
        if len(vals) < 5:
            continue
        kde = stats.gaussian_kde(vals)
        dens = kde(x_grid)
        off = i * 0.8
        max_off = max(max_off, off + 0.7)
        c = NPG15[i % len(NPG15)]
        axA.fill_between(x_grid, off, off + dens / dens.max() * 0.7,
                         color=c, alpha=0.75, edgecolor="white", lw=0.5)
        axA.text(x_grid[-1] + 0.05, off + 0.25, b, fontsize=8.5,
                 color=c, va="center")

    axA.set_xlabel(r"$\log_{10}\,\hat{K}$ per taxon")
    axA.set_ylabel("biome (stacked)")
    axA.set_yticks([])
    axA.set_title(r"Per-biome carrying-capacity $\hat K$ density"
                  "\n(host / environment enters via $\\alpha$ intercept)",
                  fontsize=11)
    xlo, xhi = axA.get_xlim()
    axA.set_xlim(xlo, xhi + (xhi - xlo) * 0.28)
    axA.grid(alpha=0.3)

    # Carve dedicated annotation strip ABOVE the topmost density.
    annot_height = 1.6
    axA.set_ylim(-0.25, max_off + annot_height)
    axA.text(0.02, 0.985,
             f"Kruskal-Wallis:  H = {H:.1f},  p = {fmt_p(p_kw)}\n"
             f"Levene (var):     W = {Wlev:.1f},  p = {fmt_p(p_lev)}",
             transform=axA.transAxes, va="top", ha="left",
             fontsize=8.5,
             bbox=dict(fc="white", ec="#7E6148", lw=0.5, alpha=0.95,
                       pad=3.5))

    # ---- Panel B: beta forest ---------------------------------------
    ypos = np.arange(len(kdf))
    colors = [NPG15[i % len(NPG15)] for i in range(len(kdf))]
    axB.errorbar(kdf["beta"], ypos,
                 xerr=1.96 * kdf["beta_se"],
                 fmt="o", ecolor="#7E6148", color="black",
                 capsize=3, markersize=5)
    for y, c in zip(ypos, colors):
        axB.scatter(kdf["beta"].iloc[y], y, color=c, s=40, zorder=3,
                    edgecolor="black", linewidth=0.5)
    axB.axvline(2.0, color="black", lw=1.5, ls="--",
                label=r"universal $\beta = 2$")
    axB.set_yticks(ypos)
    axB.set_yticklabels(kdf["biome"], fontsize=8.5)
    axB.set_xlabel(r"per-biome Taylor exponent $\beta$")
    axB.set_title(r"$\beta$ invariance across biomes"
                  f"\n(range {beta_range[0]:.3f}-{beta_range[1]:.3f}, "
                  f"CV = {beta_cv:.3f})",
                  fontsize=11)
    axB.grid(alpha=0.3)
    bmin, bmax = axB.get_xlim()
    axB.set_xlim(bmin - 0.02, bmax + 0.02)

    # Dedicated top strip for the Wald box AND the legend, both outside
    # the marker cloud.
    axB.set_ylim(-0.6, len(kdf) - 1 + 1.6)
    axB.text(0.02, 0.985,
             f"Wald combined:  \u03C7\u00B2({df_x}) = {chi2:.1f}\n"
             f"  p(all \u03B2 = 2) = {fmt_p(p_invar)}",
             transform=axB.transAxes, va="top", ha="left",
             fontsize=8.5,
             bbox=dict(fc="white", ec="#7E6148", lw=0.5, alpha=0.95,
                       pad=3.5))
    # legend moved to lower-right inside axes (empty zone: no markers
    # below the lowest biome).
    axB.legend(loc="lower right", fontsize=9, frameon=True,
               framealpha=0.9, edgecolor="#cccccc")

    fig.suptitle(
        "T5 Grilli stochastic-logistic view: host enters via K distribution, "
        "not via \u03B2",
        fontsize=12, y=1.0)
    fig.tight_layout()
    out = FIGS / "T5_k_distribution.png"
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out}")


if __name__ == "__main__":
    main()

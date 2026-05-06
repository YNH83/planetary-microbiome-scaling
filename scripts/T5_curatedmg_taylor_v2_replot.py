"""Replot T5_curatedmg_taylor_v2.png with clean text placement.

Reuses taylor_fit / load_cohort / discover_cohorts from T5_curatedmg_taylor_v2
(skip AFD + BIC recomputation, read BIC JSON). Rebuilds the scatter panel
layout with stat boxes in the lower-right corner (below the Taylor fit line)
instead of a legend in the upper-left where the scatter cloud sits.
"""
from __future__ import annotations
import importlib.util
import json
import math
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
sys.path.insert(0, str(ROOT / "scripts" / "shared"))
from nature_style import apply_nature_style, NPG_PALETTE  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "T5_curatedmg_taylor_v2", ROOT / "scripts" / "T5_curatedmg_taylor_v2.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIG = ROOT / "figures" / "T5_curatedmg_taylor_v2.png"
BIC_JSON = ROOT / "scripts" / "T5_curatedmg_bic_v2.json"
UNIVERSAL_COLOR = "#3C5488"
REF_COLOR = "#F39B7F"
EMP_REF = 1.9659378236325347


def main():
    apply_nature_style()
    cohorts = mod.discover_cohorts()
    fits = {}
    for c in cohorts:
        print(f"fitting {c} ...")
        try:
            ab = mod.load_cohort(c)
        except FileNotFoundError:
            continue
        f = mod.taylor_fit(ab, min_prev=0.20)
        if f is None:
            continue
        fits[c] = f

    bic = json.loads(BIC_JSON.read_text())
    color_of = {c: NPG_PALETTE[i % len(NPG_PALETTE)] for i, c in enumerate(fits)}

    C = len(fits)
    n_panels = C + 1
    ncols = min(4, n_panels)
    nrows = math.ceil(n_panels / ncols)
    fig = plt.figure(figsize=(3.6 * ncols, 3.3 * nrows), dpi=160)
    gs = fig.add_gridspec(nrows, ncols, wspace=0.38, hspace=0.55,
                          left=0.06, right=0.985, top=0.92, bottom=0.10)

    for i, (c, f) in enumerate(fits.items()):
        r, k = divmod(i, ncols)
        ax = fig.add_subplot(gs[r, k])
        lmu = np.asarray(f["log_mu"]); lvar = np.asarray(f["log_var"])
        ax.scatter(lmu, lvar, s=7, alpha=0.55, color=color_of[c],
                    edgecolor="none", rasterized=True)
        xs = np.linspace(lmu.min(), lmu.max(), 50)
        ax.plot(xs, f["alpha"] + f["beta"] * xs, color="black", lw=1.3)
        ax.set_xlabel("log10 mean relative abundance")
        ax.set_ylabel("log10 variance" if k == 0 else "")
        ax.set_title(f"{c}\nn = {f['n_samples']} samples, {f['n_taxa']} taxa",
                     fontsize=9.5)
        ax.grid(alpha=0.3, lw=0.5)
        stat = (f"\u03b2 = {f['beta']:.3f}\n"
                f"[{f['beta_boot_ci_lo']:.3f}, {f['beta_boot_ci_hi']:.3f}]\n"
                f"R\u00b2 = {f['r2']:.3f}")
        ax.text(0.97, 0.04, stat, transform=ax.transAxes,
                va="bottom", ha="right", fontsize=6.8,
                bbox=dict(facecolor="white", edgecolor="#cccccc",
                          alpha=0.92, pad=2.4, lw=0.5))

    # Pooled panel
    i = C
    r, k = divmod(i, ncols)
    ax = fig.add_subplot(gs[r, k])
    for c in fits:
        f = fits[c]
        ax.scatter(f["log_mu"], f["log_var"], s=5, alpha=0.45,
                    color=color_of[c], edgecolor="none", rasterized=True)
    all_lmu = np.concatenate([fits[c]["log_mu"] for c in fits])
    xs = np.linspace(all_lmu.min(), all_lmu.max(), 60)
    mean_int = np.mean(list(bic["cohort_intercepts"].values()))
    ax.plot(xs, mean_int + bic["universal_beta"] * xs,
             color=UNIVERSAL_COLOR, lw=1.8,
             label=f"universal \u03b2 = {bic['universal_beta']:.3f}")
    ax.plot(xs, mean_int + EMP_REF * xs,
             color=REF_COLOR, lw=1.2, ls="--",
             label=f"EMP 16S \u03b2 = {EMP_REF:.3f}")
    ax.set_xlabel("log10 mean relative abundance")
    ax.set_ylabel("log10 variance" if k == 0 else "")
    ax.set_title(f"Pooled ({C} cohorts)\n\u0394BIC = {bic['delta_BIC']:+.1f}",
                  fontsize=9.5)
    ax.grid(alpha=0.3, lw=0.5)
    # Stat box in lower-right (below lines => empty zone)
    stat = (f"universal \u03b2 = {bic['universal_beta']:.3f}\n"
            f"EMP 16S \u03b2 = {EMP_REF:.3f}\n"
            f"\u0394BIC = {bic['delta_BIC']:+.1f}")
    ax.text(0.97, 0.04, stat, transform=ax.transAxes,
             va="bottom", ha="right", fontsize=6.8,
             bbox=dict(facecolor="white", edgecolor="#cccccc",
                       alpha=0.92, pad=2.4, lw=0.5))

    for j in range(n_panels, nrows * ncols):
        rr, kk = divmod(j, ncols)
        ax_empty = fig.add_subplot(gs[rr, kk])
        ax_empty.axis("off")

    fig.suptitle("T5 Taylor-law universality, expanded shotgun pool",
                 fontsize=12.5, y=0.985)
    fig.savefig(FIG, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {FIG}")


if __name__ == "__main__":
    main()

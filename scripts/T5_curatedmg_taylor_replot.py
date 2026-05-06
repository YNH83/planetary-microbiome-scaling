"""Replot T5_curatedmg_taylor.png with R-squared rendered as R^2 superscript.

Mirrors T5_curatedmg_taylor_v2_replot.py. Reuses taylor_fit / load_cohort
from T5_curatedmg_taylor (skip BIC recomputation, read BIC JSON). Only fix:
"R^2" literal replaced by Unicode R\u00b2 (R squared).
"""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
sys.path.insert(0, str(ROOT / "scripts" / "shared"))
from nature_style import apply_nature_style  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "T5_curatedmg_taylor", ROOT / "scripts" / "T5_curatedmg_taylor.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIG = ROOT / "figures" / "T5_curatedmg_taylor.png"
BIC_JSON = ROOT / "scripts" / "T5_curatedmg_bic.json"


def main():
    apply_nature_style()
    fits = {}
    for c in mod.COHORTS:
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
    cohorts = [c for c in mod.COHORTS if c in fits]

    fig = plt.figure(figsize=(14.0, 4.0), dpi=160)
    gs = fig.add_gridspec(1, 4, wspace=0.36, left=0.055, right=0.985,
                          top=0.78, bottom=0.16)

    for i, c in enumerate(cohorts):
        f = fits[c]
        lmu = np.asarray(f["log_mu"])
        lvar = np.asarray(f["log_var"])
        ax = fig.add_subplot(gs[0, i])
        ax.scatter(lmu, lvar, s=8, alpha=0.55, color=mod.NPG_COLORS[c],
                   edgecolor="none", rasterized=True)
        xs = np.linspace(lmu.min(), lmu.max(), 50)
        ax.plot(xs, f["alpha"] + f["beta"] * xs,
                color="black", lw=1.4,
                label=("\u03b2 = {:.3f}\n"
                       "[{:.3f}, {:.3f}]\n"
                       "R\u00b2 = {:.3f}").format(
                    f["beta"], f["beta_boot_ci_lo"],
                    f["beta_boot_ci_hi"], f["r2"]))
        ax.set_xlabel("log10 mean relative abundance")
        ax.set_ylabel("log10 variance" if i == 0 else "")
        ax.set_title(f"{c}\nn_samples = {f['n_samples']}, n_taxa = {f['n_taxa']}")
        ax.grid(alpha=0.3, lw=0.5)
        ax.legend(loc="upper left", fontsize=7.5, frameon=True,
                  framealpha=0.88, edgecolor="#cccccc")

    # pooled universal
    ax = fig.add_subplot(gs[0, 3])
    for c in cohorts:
        f = fits[c]
        ax.scatter(f["log_mu"], f["log_var"], s=6, alpha=0.5,
                   color=mod.NPG_COLORS[c], edgecolor="none",
                   label=f"{c} (\u03b2={f['beta']:.2f})", rasterized=True)
    all_lmu = np.concatenate([fits[c]["log_mu"] for c in cohorts])
    xs = np.linspace(all_lmu.min(), all_lmu.max(), 60)
    mean_int = np.mean(list(bic["cohort_intercepts"].values()))
    ax.plot(xs, mean_int + bic["universal_beta"] * xs,
            color=mod.NPG_COLORS["universal"], lw=1.8,
            label=f"universal \u03b2 = {bic['universal_beta']:.3f}")
    ax.plot(xs, mean_int + mod.EMP_REFERENCE_BETA * xs,
            color=mod.NPG_COLORS["ref"], lw=1.2, ls="--",
            label=f"EMP 16S \u03b2 = {mod.EMP_REFERENCE_BETA:.3f}")
    ax.set_xlabel("log10 mean relative abundance")
    ax.set_ylabel("log10 variance")
    ax.set_title(f"Pooled across cohorts\n(\u0394BIC = {bic['delta_BIC']:+.1f})")
    ax.grid(alpha=0.3, lw=0.5)
    ax.legend(loc="lower right", fontsize=6.5, frameon=True,
              framealpha=0.92, edgecolor="#cccccc")

    fig.suptitle("T5 Taylor-law universality on shotgun metagenomic cohorts",
                 fontsize=12, y=0.96)
    fig.savefig(FIG, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {FIG}")


if __name__ == "__main__":
    main()

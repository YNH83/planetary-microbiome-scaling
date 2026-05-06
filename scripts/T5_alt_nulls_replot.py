"""Replot T5_alt_nulls_histograms.png with legends placed outside the axes.

Re-runs the three null simulations (fast) with the same seed as the original
script so histogram bins are deterministic. Fix: legends are now placed
*below* the figure in a single horizontal strip instead of inside the
rightmost panels where they were overlapping histogram bars.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import norm
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
sys.path.insert(0, str(ROOT / "scripts" / "shared"))
from nature_style import apply_nature_style, NPG_PALETTE  # noqa: E402

# Import the original module to reuse simulation functions + constants
spec = importlib.util.spec_from_file_location(
    "T5_alt_nulls", ROOT / "scripts" / "T5_alt_nulls.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FIG = ROOT / "figures" / "T5_alt_nulls_histograms.png"
NPG = {"blue": NPG_PALETTE[3], "red": NPG_PALETTE[0],
       "green": NPG_PALETTE[2], "orange": NPG_PALETTE[4],
       "grey": NPG_PALETTE[5]}


def fmt_p_line(z, p_ge):
    """Return P(null>=emp) label. When p is too small to show as 0.000,
    use -log10(P) from the z-score with superscript notation."""
    if p_ge < 1e-3:
        neg_log10_p = float(-norm.logsf(z) / np.log(10))
        return (r"$P(\mathrm{null}\geq\mathrm{emp}) \approx "
                rf"10^{{-{neg_log10_p:.1f}}}$")
    return rf"$P(\mathrm{{null}}\geq\mathrm{{emp}}) = {p_ge:.3f}$"


def main():
    apply_nature_style()

    # rerun the three nulls; module's RNG is seeded at import => deterministic
    res = {
        "fisher_logseries_1943": mod.run_null("Fisher log-series (1943)",
                                                mod.null1_fisher),
        "preston_lognormal_1948": mod.run_null("Preston lognormal (1948)",
                                                 mod.null2_lognormal),
        "shoemaker_lognormal_2017": mod.run_null("Shoemaker lognormal (2017)",
                                                   mod.null3_shoemaker),
    }

    import json
    hub_path = ROOT / "scripts" / "T5_hubbell_null_results.json"
    hub_mean = hub_sd = None
    if hub_path.exists():
        hj = json.loads(hub_path.read_text())
        hub_mean = hj.get("hubbell_null_beta_mean")
        hub_sd = hj.get("hubbell_null_beta_std")

    fig, axes = plt.subplots(2, 3, figsize=(13, 7.6),
                             gridspec_kw=dict(height_ratios=[1.0, 0.7]))
    colors = [NPG["blue"], NPG["green"], NPG["orange"]]
    EMP = mod.EMPIRICAL_BETA

    # Row 1: zoomed
    for ax, (key, info), c in zip(axes[0], res.items(), colors):
        arr = np.asarray(info["betas"])
        lo = min(arr.min(), EMP) - 0.02
        hi = max(arr.max(), EMP) + 0.02
        ax.hist(arr, bins=20, color=c, edgecolor="white", alpha=0.9)
        ax.axvline(EMP, color=NPG["red"], lw=2, ls="--")
        ax.set_xlim(lo, hi)
        ax.set_title(info["name"].split(" (")[0], fontsize=10.5)
        ax.set_xlabel(r"Taylor exponent $\beta$")
        ax.grid(alpha=0.3)
        # headroom above bars so annotation box never overlaps histogram
        y_top = ax.get_ylim()[1] * 1.35
        ax.set_ylim(top=y_top)
        zstr = f"z = {info['z']:.1f}\n" + fmt_p_line(info['z'], info['p_ge'])
        ax.text(0.03, 0.97, zstr, transform=ax.transAxes,
                va="top", ha="left", fontsize=8.5,
                bbox=dict(fc="white", ec=NPG["grey"], alpha=0.9, lw=0.5))
    axes[0, 0].set_ylabel("count (90 simulations)")

    # Row 2: full range
    for ax, (key, info), c in zip(axes[1], res.items(), colors):
        arr = np.asarray(info["betas"])
        ax.errorbar([arr.mean()], [0.5], xerr=[[arr.std(ddof=1)]],
                    fmt="o", ms=7, color=c, ecolor=c, capsize=4)
        if hub_mean is not None:
            ax.errorbar([hub_mean], [0.5], xerr=[[hub_sd]],
                        fmt="s", ms=6, color=NPG["grey"],
                        ecolor=NPG["grey"], capsize=4)
        ax.axvline(EMP, color=NPG["red"], lw=2, ls="--")
        ax.set_xlim(0.9, 2.1)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_xlabel(r"Taylor exponent $\beta$  (full range)")
        ax.grid(alpha=0.3, axis="x")
    axes[1, 0].set_ylabel("full-range comparison")

    # Custom legend: one entry per distinct visual element, colors explicitly
    # matched to the three null generators. Empirical EMP line shown once;
    # colored dot in row 2 explained as "same color as the histogram above".
    legend_elements = [
        Patch(facecolor=NPG["blue"], edgecolor="white",
              label="Fisher log-series null (row 1 histogram; row 2 dot)"),
        Patch(facecolor=NPG["green"], edgecolor="white",
              label="Preston lognormal null (row 1 histogram; row 2 dot)"),
        Patch(facecolor=NPG["orange"], edgecolor="white",
              label="Shoemaker lognormal null (row 1 histogram; row 2 dot)"),
        Line2D([0], [0], color=NPG["red"], lw=2, ls="--",
               label=fr"Empirical EMP $\beta$ = {EMP:.3f}"),
        Line2D([0], [0], marker="s", markersize=7, lw=0,
               markerfacecolor=NPG["grey"], markeredgecolor=NPG["grey"],
               label="Hubbell neutral null (mean \u00B1 sd, row 2 only)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=3,
               bbox_to_anchor=(0.5, -0.04), frameon=False, fontsize=9,
               handletextpad=0.6, columnspacing=1.8)

    fig.suptitle("Alternative null generators vs empirical EMP Taylor exponent  "
                 r"(empirical $\beta$ = 1.97)",
                 fontsize=11.5, y=0.995)
    fig.tight_layout(rect=[0, 0.07, 1, 0.96])
    fig.savefig(FIG, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {FIG}")


if __name__ == "__main__":
    main()

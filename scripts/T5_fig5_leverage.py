"""
T5 Figure 5 (rebuild): "K is the leverage point".

Replaces the old single-panel K-distribution figure with a 4-panel composite
that puts the convergent narrative on the main canvas:

    panel a  per-biome carrying-capacity (logK) ridge density (15 biomes)
    panel b  beta invariance forest (15 biomes vs universal beta = 1.95)
    panel c  disease K-shift in IBDMDB stool: control vs UC vs CD
             (top: KDE of per-taxon log10 mean abundance; bottom: per-state beta)
    panel d  beta invariance across 108 longitudinal subjects (CD vs UC)

Single-message claim: habitat, disease, and time act on alpha (= log K), not on
beta. This is the macroecological analogue of Cao et al. Nature 2026's
"convergent dedifferentiated state" finding: many divergent perturbations
(biomes / disease states / time bins) converge on a shared scaling backbone,
with the divergence absorbed into the carrying-capacity intercept.

Inputs (all under T5_Macroecology/results_csv/, symlinked back to
Microbiome-Epi Protocols project):
    T5_empo3_real_moments.csv     per-taxon mean / variance per biome
    T5_empo3_real_taylor.csv      per-biome Taylor fit
    T5_disease_afd.csv            per-state per-taxon mean abundance
    T5_disease_detection_results.csv  per-state Taylor fit
    T5_longitudinal_per_subject.csv   per-subject Taylor fit (n=108)
    T5_bayesian_posterior.csv     hierarchical posterior (for universal beta)

Output:
    figures/T5_fig5_leverage.png
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path("/Users/ynh83/Desktop/T5_Macroecology")
RES = ROOT / "results_csv"
FIGS = ROOT / "figures"
FIGS.mkdir(exist_ok=True)

NATURE_STYLE = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols/scripts/shared")
sys.path.insert(0, str(NATURE_STYLE))
from nature_style import apply_nature_style, BIOME_COLORS, DECISION_COLORS

apply_nature_style()

UNIVERSAL_BETA = 1.950
HDI_LO, HDI_HI = 1.909, 1.992

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

STATE_COLOR = {
    "control": "#3C5488",
    "UC":      "#F39B7F",
    "CD":      "#E64B35",
}


def panel_a_ridge(ax: plt.Axes) -> None:
    moments = pd.read_csv(RES / "T5_empo3_real_moments.csv")
    n_biomes = len(BIOME_ORDER)
    grid = np.linspace(-1.0, 4.5, 400)
    spacing = 0.85
    for i, biome in enumerate(BIOME_ORDER):
        sub = moments[moments["biome"] == biome]
        if sub.empty or len(sub) < 5:
            continue
        log_mean = sub["log_mean"].to_numpy() / np.log(10)
        log_mean = log_mean[np.isfinite(log_mean)]
        if log_mean.size < 5:
            continue
        try:
            kde = gaussian_kde(log_mean, bw_method=0.35)
            dens = kde(grid)
        except np.linalg.LinAlgError:
            continue
        dens = dens / dens.max()
        baseline = (n_biomes - 1 - i) * spacing
        color = BIOME_COLORS.get(biome, "#3B3B3B")
        ax.fill_between(grid, baseline, baseline + dens, color=color,
                        alpha=0.55, linewidth=0)
        ax.plot(grid, baseline + dens, color=color, linewidth=0.7)
        med = np.median(log_mean)
        ax.plot([med, med], [baseline, baseline + 0.95], color="black",
                linewidth=0.6, alpha=0.7)
    ax.set_yticks([(n_biomes - 1 - i) * spacing + 0.4 for i in range(n_biomes)])
    ax.set_yticklabels(BIOME_ORDER, fontsize=7)
    ax.set_xlabel(r"$\log_{10}$ K per taxon (mean read-count proxy)", fontsize=8)
    # Extend x-axis right edge so the ridge densities never reach the
    # annotation pinned at x=4.6.
    ax.set_xlim(-1.0, 6.0)
    ax.set_title("a   Habitat enters through K (intercept), not through $\\beta$",
                 loc="left", fontsize=9, fontweight="bold")
    # Anchor stats annotation in data coordinates inside the empty right strip
    # (x in [4.7, 5.95]) so it never overlaps any ridge density curve.
    ax.text(5.95, 0.4,
            "Kruskal H = 3,542\np < 2e$-$308\n\nLevene W = 18.9\np = 7e$-$48",
            fontsize=7.0, ha="right", va="bottom",
            bbox=dict(facecolor="white", edgecolor="lightgray", alpha=0.95, pad=3))


def panel_b_beta_forest(ax: plt.Axes) -> None:
    taylor = pd.read_csv(RES / "T5_empo3_real_taylor.csv")
    taylor = taylor.set_index("biome").loc[BIOME_ORDER].reset_index()
    n = len(taylor)
    y = np.arange(n)[::-1]
    ax.axvspan(HDI_LO, HDI_HI, color=DECISION_COLORS["pass"], alpha=0.18,
               linewidth=0, label=f"95% HDI [{HDI_LO}, {HDI_HI}]")
    ax.axvline(UNIVERSAL_BETA, color="black", linewidth=1.0, linestyle="--",
               label=fr"$\beta_{{global}}$ = {UNIVERSAL_BETA}")
    ax.axvline(2.0, color=DECISION_COLORS["fail"], linewidth=0.8, linestyle=":",
               alpha=0.7, label=r"theoretical $\beta$ = 2")
    for yi, (_, row) in zip(y, taylor.iterrows()):
        color = BIOME_COLORS.get(row["biome"], "#3B3B3B")
        ax.errorbar(row["beta"], yi,
                    xerr=[[row["beta"] - row["beta_ci_lo"]],
                          [row["beta_ci_hi"] - row["beta"]]],
                    fmt="o", color=color, ecolor=color,
                    markersize=4.5, linewidth=1.1, capsize=2)
    ax.set_yticks(y)
    ax.set_yticklabels(taylor["biome"], fontsize=7)
    ax.set_xlabel(r"per-biome Taylor exponent $\beta$", fontsize=8)
    ax.set_xlim(1.65, 2.20)
    ax.set_title(r"b   $\beta$ invariance across 15 biomes (CV = 3.9%)",
                 loc="left", fontsize=9, fontweight="bold")
    ax.legend(loc="lower right", fontsize=6.5, framealpha=0.9)


def panel_c_disease(axes) -> None:
    """Two stacked sub-axes inside one column: KDE of K (top), beta bar (bottom)."""
    ax_k, ax_b = axes
    afd = pd.read_csv(RES / "T5_disease_afd.csv")
    det = pd.read_csv(RES / "T5_disease_detection_results.csv")

    grid = np.linspace(-1.2, 2.0, 400)
    for state in ["control", "UC", "CD"]:
        sub = afd[afd["state"] == state]
        if sub.empty:
            continue
        logk = np.log10(sub["mean_abund"].to_numpy())
        logk = logk[np.isfinite(logk)]
        if logk.size < 5:
            continue
        kde = gaussian_kde(logk, bw_method=0.30)
        dens = kde(grid)
        ax_k.plot(grid, dens, color=STATE_COLOR[state], linewidth=1.5,
                  label=f"{state} (n = {sub.shape[0]} taxa)")
        ax_k.fill_between(grid, 0, dens, color=STATE_COLOR[state], alpha=0.18)
        ax_k.axvline(np.median(logk), color=STATE_COLOR[state],
                     linewidth=0.6, linestyle="--", alpha=0.7)
    ax_k.set_xlabel(r"$\log_{10}$ K per taxon", fontsize=8)
    ax_k.set_ylabel("density", fontsize=8)
    ax_k.set_xlim(-1.2, 2.0)
    ax_k.legend(fontsize=6.5, frameon=False, loc="upper right")
    ax_k.set_title("c   Disease shifts K, not $\\beta$ (HMP IBDMDB stool)",
                   loc="left", fontsize=9, fontweight="bold")

    states = ["control", "UC", "CD"]
    rows = det.set_index("state").loc[states].reset_index()
    x = np.arange(len(states))
    for xi, (_, r) in zip(x, rows.iterrows()):
        c = STATE_COLOR[r["state"]]
        ax_b.errorbar(xi, r["beta"],
                      yerr=[[r["beta"] - r["beta_ci_lo"]],
                            [r["beta_ci_hi"] - r["beta"]]],
                      fmt="s", color=c, ecolor=c, markersize=7,
                      linewidth=1.3, capsize=3)
        ax_b.text(xi, r["beta_ci_hi"] + 0.04, f"{r['beta']:.2f}",
                  ha="center", fontsize=7, color=c, fontweight="bold")
    ax_b.axhspan(HDI_LO, HDI_HI, color=DECISION_COLORS["pass"], alpha=0.18,
                 linewidth=0)
    ax_b.axhline(UNIVERSAL_BETA, color="black", linewidth=0.8, linestyle="--")
    ax_b.set_xticks(x)
    ax_b.set_xticklabels(states, fontsize=8)
    ax_b.set_ylabel(r"$\beta$ per state", fontsize=8)
    # Widen y-range so the data labels and HDI band breathe.
    ax_b.set_ylim(1.30, 2.20)
    # Move the stats annotation into the inter-panel gap above c_bot's top
    # frame so it never collides with the axis spine or data labels.
    ax_b.text(0.5, 1.18,
              "Within IBDMDB stool: $\\beta$ varies < 0.07 across states; "
              "median K shifts (Bonferroni KS  p < 1e-6)",
              transform=ax_b.transAxes, fontsize=6.5, ha="center", va="bottom",
              clip_on=False,
              bbox=dict(facecolor="white", edgecolor="lightgray",
                        alpha=0.95, pad=2))


def panel_d_longitudinal(ax: plt.Axes) -> None:
    sub = pd.read_csv(RES / "T5_longitudinal_per_subject.csv")
    sub = sub.dropna(subset=["beta", "disease_subtype"])
    bins = pd.read_csv(RES / "T5_longitudinal_results.csv")
    rng = np.random.default_rng(42)
    cats = ["UC", "CD"]
    width = 0.6
    for i, c in enumerate(cats):
        vals = sub.loc[sub["disease_subtype"] == c, "beta"].to_numpy()
        if vals.size == 0:
            continue
        x = i + (rng.uniform(-0.18, 0.18, size=vals.size))
        ax.scatter(x, vals, s=18, color=STATE_COLOR[c], alpha=0.55,
                   edgecolor="white", linewidth=0.4,
                   label=f"{c} (n = {vals.size})")
        ax.boxplot([vals], positions=[i], widths=width, showfliers=False,
                   patch_artist=True,
                   boxprops=dict(facecolor="none", edgecolor="black", linewidth=1.0),
                   medianprops=dict(color="black", linewidth=1.4),
                   whiskerprops=dict(color="black", linewidth=0.8),
                   capprops=dict(color="black", linewidth=0.8))
    ax.axhspan(HDI_LO, HDI_HI, color=DECISION_COLORS["pass"], alpha=0.18,
               linewidth=0, label=f"global 95% HDI")
    ax.axhline(UNIVERSAL_BETA, color="black", linewidth=1.0, linestyle="--",
               label=fr"$\beta_{{global}}$ = {UNIVERSAL_BETA}")
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, fontsize=8)
    ax.set_ylabel(r"per-subject Taylor exponent $\beta$", fontsize=8)
    ax.set_xlim(-0.6, len(cats) - 0.4)
    ax.set_ylim(1.15, 2.20)
    ax.set_title("d   Time and host do not move $\\beta$ (108 IBD subjects)",
                 loc="left", fontsize=9, fontweight="bold")
    ax.legend(fontsize=6.5, loc="lower right", framealpha=0.9)
    bin_text = ("\nbinned across visits:\n"
                + "\n".join(f"  {r['bin']:>6s}  $\\beta$ = {r['beta']:.2f}"
                            for _, r in bins.iterrows()))
    ax.text(0.02, 0.98, bin_text.strip(), transform=ax.transAxes,
            fontsize=6.3, va="top", ha="left",
            bbox=dict(facecolor="white", edgecolor="lightgray", alpha=0.9, pad=2))


def panel_d_longitudinal_wide(ax: plt.Axes) -> None:
    """Wide panel D: subjects sorted by beta, colored by subtype, plus binned trajectory."""
    sub = pd.read_csv(RES / "T5_longitudinal_per_subject.csv")
    sub = sub.dropna(subset=["beta", "disease_subtype"]).copy()
    sub = sub.sort_values("beta").reset_index(drop=True)
    bins = pd.read_csv(RES / "T5_longitudinal_results.csv")

    x = np.arange(len(sub))
    colors = sub["disease_subtype"].map(STATE_COLOR).fillna("#888888").to_numpy()
    ax.errorbar(x, sub["beta"], yerr=1.96 * sub["beta_se"],
                fmt="none", ecolor="lightgray", linewidth=0.6,
                capsize=0, zorder=1)
    for c_label, color in [("UC", STATE_COLOR["UC"]), ("CD", STATE_COLOR["CD"])]:
        m = sub["disease_subtype"] == c_label
        ax.scatter(x[m], sub.loc[m, "beta"], s=22, color=color,
                   edgecolor="white", linewidth=0.5,
                   label=f"{c_label} (n = {m.sum()})", zorder=3)
    ax.axhspan(HDI_LO, HDI_HI, color=DECISION_COLORS["pass"], alpha=0.18,
               linewidth=0, label="EMP global 95% HDI", zorder=0)
    ax.axhline(UNIVERSAL_BETA, color="black", linewidth=1.0, linestyle="--",
               label=fr"EMP $\beta_{{global}}$ = {UNIVERSAL_BETA}", zorder=2)
    ax.set_xlim(-1, len(sub))
    ax.set_ylim(1.0, 2.4)
    ax.set_xlabel("108 IBD subjects (iHMP IBDMDB) ranked by per-subject $\\beta$",
                  fontsize=8)
    ax.set_ylabel(r"per-subject Taylor exponent $\beta$", fontsize=8)
    ax.set_title(
        r"d   $\beta$ stays in [1.5, 2.0] band across 108 subjects and 3 time bins",
        loc="left", fontsize=9, fontweight="bold",
    )
    # Legend pinned to upper-right corner (data starts low-left, so this avoids
    # covering the leftmost UC subjects).
    ax.legend(fontsize=6.8, loc="upper right", ncol=2, framealpha=0.95,
              bbox_to_anchor=(0.98, 0.98))

    bin_text = ("binned across visits:  "
                + " | ".join(f"{r['bin']} $\\beta$ = {r['beta']:.2f}"
                             for _, r in bins.iterrows()))
    ax.text(0.50, 0.04, bin_text, transform=ax.transAxes,
            fontsize=7, ha="center", va="bottom",
            bbox=dict(facecolor="white", edgecolor="lightgray", alpha=0.9, pad=2.5))


def main() -> None:
    fig = plt.figure(figsize=(15.5, 10.8))
    gs = GridSpec(
        4, 3,
        width_ratios=[1.05, 1.05, 1.0],
        height_ratios=[1.0, 0.62, 0.10, 1.05],
        hspace=0.85, wspace=0.55,
        left=0.07, right=0.985, top=0.92, bottom=0.06,
    )
    ax_a = fig.add_subplot(gs[0:2, 0])
    ax_b = fig.add_subplot(gs[0:2, 1])
    ax_c_top = fig.add_subplot(gs[0, 2])
    ax_c_bot = fig.add_subplot(gs[1, 2])
    ax_d = fig.add_subplot(gs[3, :])

    panel_a_ridge(ax_a)
    panel_b_beta_forest(ax_b)
    panel_c_disease((ax_c_top, ax_c_bot))
    panel_d_longitudinal_wide(ax_d)

    fig.suptitle(
        "Figure 5 | K is the leverage point: habitat, disease, and time act on "
        "intercept $\\alpha$ ($\\approx \\log$ K), not on $\\beta$",
        fontsize=12.5, fontweight="bold", y=0.985,
    )
    out_main = FIGS / "T5_fig5_leverage.png"
    fig.savefig(out_main, dpi=400)
    plt.close(fig)
    print(f"wrote {out_main}")


if __name__ == "__main__":
    main()

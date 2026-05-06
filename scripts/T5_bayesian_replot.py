"""Replot T5_bayesian_posterior.png from cached posterior summary CSV.

The full MCMC trace is not persisted, so Panel A draws the β_global posterior
as a Normal(mean, sd) density (β_global is well-approximated by Normal per
the summary) with shaded 95% HDI. Panel B is reconstructed from per-biome
mean and HDI bounds.

Fix: legend no longer sits on the posterior density.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
sys.path.insert(0, str(ROOT / "scripts" / "shared"))
from nature_style import apply_nature_style, NPG_PALETTE  # noqa: E402

CSV = ROOT / "scripts" / "T5_bayesian_posterior.csv"
FIG = ROOT / "figures" / "T5_bayesian_posterior.png"

NPG = {"blue": NPG_PALETTE[3], "red": NPG_PALETTE[0], "grey": NPG_PALETTE[5]}


def main():
    apply_nature_style()
    df = pd.read_csv(CSV)
    bg = df[df["parameter"] == "beta_global"].iloc[0]
    tau_row = df[df["parameter"] == "tau"].iloc[0]
    biome_rows = df[df["parameter"] == "beta_b"].copy()

    q_med = bg["mean"]
    q_lo = bg["hdi_2.5"]
    q_hi = bg["hdi_97.5"]
    sd = bg["sd"]
    tau = tau_row["mean"]

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(12, 5.2),
                                   gridspec_kw=dict(width_ratios=[1.0, 1.2]))

    # Panel A: Normal(q_med, sd) approximation of posterior
    x = np.linspace(q_med - 5 * sd, q_med + 5 * sd, 400)
    dens = stats.norm.pdf(x, q_med, sd)
    axA.fill_between(x, dens, color=NPG["blue"], alpha=0.55,
                     edgecolor=NPG["blue"], linewidth=0.8,
                     label="posterior density (Normal fit)")
    x_hdi = np.linspace(q_lo, q_hi, 200)
    axA.fill_between(x_hdi, stats.norm.pdf(x_hdi, q_med, sd),
                     color=NPG["red"], alpha=0.18,
                     label=f"95% HDI = [{q_lo:.3f}, {q_hi:.3f}]")
    axA.axvline(q_med, color=NPG["red"], lw=2,
                label=f"posterior median = {q_med:.3f}")
    axA.axvline(2.0, color="black", lw=1.2, ls="--",
                label=r"Taylor $\beta = 2$")
    axA.set_xlabel(r"$\beta_{\mathrm{global}}$")
    axA.set_ylabel("posterior density")
    axA.set_title(r"Partial-pooled posterior of Taylor $\beta_{\mathrm{global}}$",
                  fontsize=11, loc="left")
    axA.legend(fontsize=7.5, loc="upper left",
               bbox_to_anchor=(0, -0.16), ncol=2, frameon=False)
    axA.grid(alpha=0.3)

    # Panel B: biome forest
    biome_rows = biome_rows.sort_values("mean").reset_index(drop=True)
    means = biome_rows["mean"].values
    los = biome_rows["hdi_2.5"].values
    his = biome_rows["hdi_97.5"].values
    biomes = biome_rows["biome"].tolist()
    ypos = np.arange(len(biomes))
    axB.errorbar(means, ypos, xerr=[means - los, his - means],
                 fmt="o", color=NPG["blue"], ecolor=NPG["grey"],
                 capsize=3, markersize=5)
    axB.axvline(q_med, color=NPG["red"], lw=1.5, ls="-",
                label=fr"$\beta_{{\mathrm{{global}}}}$ = {q_med:.3f}")
    axB.axvline(2.0, color="black", lw=1.0, ls="--",
                label=r"$\beta = 2$")
    axB.set_yticks(ypos)
    axB.set_yticklabels(biomes, fontsize=8.5)
    axB.set_xlabel(r"biome-specific $\beta_b$ (posterior mean, 95% HDI)")
    axB.set_title(r"Per-biome $\beta_b$ (partial pool)  |  "
                  fr"$\tau$ = {tau:.3f}", fontsize=11, loc="left")
    axB.legend(loc="upper left", bbox_to_anchor=(0, -0.16),
               ncol=2, fontsize=8, frameon=False)
    axB.grid(alpha=0.3)

    fig.suptitle(r"T5 Bayesian hierarchical partial-pooling: Taylor's law across EMP biomes",
                 fontsize=12, y=0.998)
    fig.tight_layout(rect=[0, 0.05, 1, 0.96])
    fig.savefig(FIG, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {FIG}")


if __name__ == "__main__":
    main()

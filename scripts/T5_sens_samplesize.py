"""
T5 sensitivity sweep 4: sample-size convergence.

Bootstrap resample samples (with replacement from the 26,181 EMP 90 bp
samples that carry an empo_3 label) at target sizes
{500, 2000, 5000, 10000, 20000, 26181}. For each target size, draw 20
bootstrap replicates; within each replicate, re-stratify by empo_3 and
refit the universal Taylor beta on biomes with at least min_biome_samples
(lowered to 30 for n <= 2000 to keep at least a few biomes alive at small
n; otherwise 50 per canonical).

Outputs:
    scripts/T5_sens_samplesize.csv   (one row per bootstrap replicate)
    figures/T5_sens_samplesize.png   (mean + 2.5/97.5 percentile CI vs n)
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
from nature_style import apply_nature_style, DECISION_COLORS  # noqa: E402
from t5_sens_core import (  # noqa: E402
    load_emp, load_meta, taylor_fit_sparse, universal_slope,
)
apply_nature_style()

TARGET_NS = [500, 2000, 5000, 10000, 20000, 26181]
REPS = 20
SEED = 2026
CANONICAL = 26181


def biome_indices_from_cols(cols, biome_of_col, min_biome_samples):
    """Given np.array of (possibly duplicated) column indices, group by
    biome. Returns dict biome -> np.array of *positions in cols*."""
    bins = {}
    for pos, c in enumerate(cols):
        b = biome_of_col.get(int(c))
        if b is None:
            continue
        bins.setdefault(b, []).append(pos)
    return {b: np.asarray(v, dtype=int) for b, v in bins.items()
            if len(v) >= min_biome_samples}


def main():
    print("[load] EMP 90 bp deblur")
    M, obs_ids, samp_ids, tax = load_emp()
    meta = load_meta()
    id_to_col = {s: i for i, s in enumerate(samp_ids)}
    # sample -> biome map (only labelled samples)
    biome_of_col = {}
    for b, sub in meta.groupby("empo_3"):
        for sid in sub["#SampleID"].values:
            j = id_to_col.get(sid)
            if j is not None:
                biome_of_col[j] = b
    labelled_cols = np.array(sorted(biome_of_col.keys()), dtype=int)
    print(f"[pool] {len(labelled_cols)} labelled samples across "
          f"{len(set(biome_of_col.values()))} biomes")

    rng = np.random.default_rng(SEED)
    rows = []
    for n in TARGET_NS:
        # Safety: cap target to pool size. Allow resampling with replacement
        # so n=26181 is still a bootstrap, not the identity.
        n_use = min(n, len(labelled_cols))
        min_bs = 30 if n <= 2000 else 50
        print(f"\n[n={n}] bootstrap x {REPS}, min_biome_samples={min_bs}")
        for rep in range(REPS):
            draw = rng.choice(labelled_cols, size=n_use, replace=True)
            # Build sub-matrix; duplicates give duplicate columns, which is
            # the correct bootstrap semantics for (sample, observation).
            sub = M[:, draw]
            biome_pos = biome_indices_from_cols(draw, biome_of_col, min_bs)
            if len(biome_pos) < 2:
                rows.append(dict(
                    n=n, rep=rep, n_used=int(n_use),
                    n_biomes=len(biome_pos),
                    universal_beta=np.nan, beta_se=np.nan,
                    r2=np.nan, n_points=0))
                continue
            fits = {}
            for biome, positions in biome_pos.items():
                s2 = sub[:, positions]
                f = taylor_fit_sparse(s2, min_prev=0.2, min_taxa=30)
                if f is None:
                    continue
                fits[biome] = f
            if len(fits) < 2:
                rows.append(dict(
                    n=n, rep=rep, n_used=int(n_use),
                    n_biomes=len(fits),
                    universal_beta=np.nan, beta_se=np.nan,
                    r2=np.nan, n_points=0))
                continue
            u = universal_slope(fits)
            rows.append(dict(
                n=n, rep=rep, n_used=int(n_use),
                canonical=(n == CANONICAL),
                universal_beta=u["universal_beta"],
                beta_se=u["universal_beta_se"],
                r2=u["r2"], n_points=u["n_points"],
                n_biomes=u["n_biomes"],
            ))
        # report rep summary
        df_n = pd.DataFrame([r for r in rows if r["n"] == n])
        valid = df_n.dropna(subset=["universal_beta"])
        if len(valid):
            m = valid["universal_beta"].mean()
            lo = valid["universal_beta"].quantile(0.025)
            hi = valid["universal_beta"].quantile(0.975)
            print(f"  mean \u03b2 = {m:.4f} (2.5%={lo:.4f}, 97.5%={hi:.4f}) "
                  f"over {len(valid)} valid reps / {REPS}")
        else:
            print(f"  [warn] no valid reps at n={n}")

    df = pd.DataFrame(rows)
    csv_path = SCRIPTS / "T5_sens_samplesize.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n[csv] {csv_path}")

    # Figure: mean ± 95% bootstrap CI vs n
    agg_rows = []
    for n, grp in df.groupby("n"):
        v = grp["universal_beta"].dropna()
        if not len(v):
            continue
        agg_rows.append(dict(
            n=n,
            mean=v.mean(), lo=v.quantile(0.025), hi=v.quantile(0.975),
            sd=v.std(ddof=1) if len(v) > 1 else np.nan,
            n_valid=len(v),
        ))
    agg = pd.DataFrame(agg_rows).sort_values("n")

    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    x = agg["n"].values
    y = agg["mean"].values
    yerr_lo = y - agg["lo"].values
    yerr_hi = agg["hi"].values - y
    ax.errorbar(x, y, yerr=[yerr_lo, yerr_hi],
                fmt="o", color=DECISION_COLORS["baseline"],
                ecolor="#888", capsize=3, elinewidth=0.8, markersize=6,
                zorder=3, label="mean \u03b2 (2.5 / 97.5 percentile)")
    # canonical
    canon = agg[agg["n"] == CANONICAL]
    if len(canon):
        ax.scatter(canon["n"], canon["mean"],
                   s=120, facecolors="none",
                   edgecolors=DECISION_COLORS["emphasis"], linewidths=1.5,
                   zorder=4, label="canonical n = 26181")
    ax.axhline(1.966, color=DECISION_COLORS["emphasis"], ls="--",
               lw=1.0, label="EMP canonical \u03b2 = 1.966")
    ax.axhspan(1.85, 2.05, color="#ddd", alpha=0.35,
               label="tolerance band [1.85, 2.05]")
    ax.set_xscale("log")
    ax.set_xlabel("Bootstrap sample size n")
    ax.set_ylabel("Universal Taylor exponent \u03b2")
    ax.set_title(f"T5 sensitivity: sample-size convergence "
                 f"({REPS} bootstrap replicates)", loc="left")
    ax.set_xticks(TARGET_NS)
    ax.set_xticklabels([str(v) for v in TARGET_NS], rotation=30, ha="right")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7,
              frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGS / "T5_sens_samplesize.png")
    plt.close(fig)
    print(f"[figure] {FIGS / 'T5_sens_samplesize.png'}")


if __name__ == "__main__":
    main()

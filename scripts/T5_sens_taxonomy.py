"""
T5 sensitivity sweep 3: taxonomic resolution.

Aggregate ASV counts upward to {genus, family, order, class, phylum} using
the Greengenes taxonomy embedded in the EMP 90 bp BIOM (same parser as
scripts/N3_phylo_taylor.py). Refit universal Taylor beta across EMPO-3
biomes at each level. Also include the raw ASV level as reference.

Outputs:
    scripts/T5_sens_taxonomy.csv
    figures/T5_sens_taxonomy.png
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, coo_matrix
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
FIGS = ROOT / "figures"
sys.path.insert(0, str(SCRIPTS / "shared"))
from nature_style import apply_nature_style, DECISION_COLORS  # noqa: E402
from t5_sens_core import (  # noqa: E402
    load_emp, load_meta, biome_sample_indices,
    taylor_fit_sparse, universal_slope,
)
apply_nature_style()

# from finest to coarsest
LEVELS = ["ASV", "genus", "family", "order", "class", "phylum"]
CANONICAL = "ASV"
RANK_PREFIX = {"genus": "g__", "family": "f__", "order": "o__",
               "class": "c__", "phylum": "p__"}


def aggregate_by_rank(M_csr, tax_df, rank):
    """Sum rows of M_csr by tax_df[rank]. Returns (M_agg_csr, group_labels)."""
    col = tax_df[rank].fillna("").str.replace(RANK_PREFIX[rank], "",
                                               regex=False).str.strip()
    # treat empty or 'unassigned' as a separate per-row group so they do NOT
    # all collapse into a single mega-row.
    labels = col.values.copy()
    unassigned_mask = (labels == "") | (labels == "unassigned")
    # assign unique synthetic labels for unassigned rows (keeps them as
    # separate taxa; they contribute to mean / var as ASV-level rows)
    for i, flag in enumerate(unassigned_mask):
        if flag:
            labels[i] = f"_unassigned_{i}"
    # build groupby -> row index groups
    uniq, inv = np.unique(labels, return_inverse=True)
    n_groups = len(uniq)
    n_taxa, n_samp = M_csr.shape
    # Build a (n_groups x n_taxa) aggregator then multiply by M_csr.
    # Sparse aggregator: one 1.0 per ASV at (group_idx, asv_idx).
    agg = coo_matrix((np.ones(n_taxa, dtype=np.float64),
                      (inv, np.arange(n_taxa))),
                     shape=(n_groups, n_taxa)).tocsr()
    M_agg = agg @ M_csr
    return M_agg, uniq


def main():
    print("[load] EMP 90 bp deblur")
    M, obs_ids, samp_ids, tax = load_emp()
    meta = load_meta()
    biome_idx = biome_sample_indices(meta, samp_ids, min_biome_samples=50)
    print(f"[biomes] {len(biome_idx)} usable biomes")

    rows = []
    for level in LEVELS:
        print(f"\n[level={level}] aggregating")
        if level == "ASV":
            M_lvl = M
            n_groups = M.shape[0]
        else:
            M_lvl, labels = aggregate_by_rank(M, tax, level)
            n_groups = M_lvl.shape[0]
        print(f"  n_taxa_rows after aggregation: {n_groups}")

        fits = {}
        for biome, cols in biome_idx.items():
            sub = M_lvl[:, cols]
            f = taylor_fit_sparse(sub, min_prev=0.2, min_taxa=30)
            if f is None:
                continue
            fits[biome] = f
        if len(fits) < 2:
            print(f"  [warn] only {len(fits)} biomes fit")
            continue
        u = universal_slope(fits)
        row = dict(
            level=level,
            canonical=(level == CANONICAL),
            n_taxa_rows=int(n_groups),
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
    csv_path = SCRIPTS / "T5_sens_taxonomy.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n[csv] {csv_path}")

    # Figure: beta vs resolution (LEVELS order: finest to coarsest)
    fig, ax = plt.subplots(figsize=(5.8, 3.8))
    df2 = df.set_index("level").reindex(LEVELS).dropna(subset=["universal_beta"]).reset_index()
    x = np.arange(len(df2))
    y = df2["universal_beta"].values
    yerr_lo = y - df2["beta_ci_lo"].values
    yerr_hi = df2["beta_ci_hi"].values - y
    ax.errorbar(x, y, yerr=[yerr_lo, yerr_hi],
                fmt="o", color=DECISION_COLORS["baseline"],
                ecolor="#888", capsize=3, elinewidth=0.8, markersize=6,
                zorder=3, label="universal \u03b2 (95% CI)")
    canon = df2[df2["canonical"]]
    if len(canon):
        xc = canon.index.values  # position in df2 reorder
        ax.scatter(xc, canon["universal_beta"],
                   s=120, facecolors="none",
                   edgecolors=DECISION_COLORS["emphasis"], linewidths=1.5,
                   zorder=4, label="canonical (ASV)")
    ax.axhline(1.966, color=DECISION_COLORS["emphasis"], ls="--",
               lw=1.0, label="EMP canonical \u03b2 = 1.966")
    ax.axhspan(1.85, 2.05, color="#ddd", alpha=0.35,
               label="tolerance band [1.85, 2.05]")
    ax.set_xticks(x)
    ax.set_xticklabels(df2["level"].tolist(), rotation=30, ha="right")
    ax.set_xlabel("Taxonomic resolution (finest to coarsest)")
    ax.set_ylabel("Universal Taylor exponent \u03b2")
    ax.set_title("T5 sensitivity: taxonomic resolution", loc="left")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7,
              frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGS / "T5_sens_taxonomy.png")
    plt.close(fig)
    print(f"[figure] {FIGS / 'T5_sens_taxonomy.png'}")


if __name__ == "__main__":
    main()

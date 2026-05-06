"""
T5 sensitivity sweep 2: rarefaction depth.

Rarefy each sample (multinomial subsampling without replacement) to depths
{1000, 2500, 5000 (canonical), 10000, 20000} reads, drop samples with
fewer than the target depth, refit universal Taylor beta across EMPO-3
biomes (EMP 90 bp deblur).

Outputs:
    scripts/T5_sens_rarefaction.csv
    figures/T5_sens_rarefaction.png
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csc_matrix, csr_matrix
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

DEPTHS = [1000, 2500, 5000, 10000, 20000]
CANONICAL = 5000
MIN_BIOME_SAMPLES = 50
SEED = 42


def rarefy_column(col_csc, depth, rng):
    """Given CSC slice with one column (taxa x 1), rarefy to 'depth' reads.
    Returns (indices, counts) for the sparse column after subsampling.
    If total < depth, returns None."""
    # col_csc is a CSC matrix with one column. .data / .indices are nonzero.
    data = col_csc.data
    indices = col_csc.indices
    total = int(data.sum())
    if total < depth:
        return None
    # hypergeometric multinomial without replacement: sample 'depth' reads
    # from multinomial defined by per-taxon counts.
    # Use multivariate_hypergeometric (available np>=1.18).
    if len(data) == 0:
        return None
    sub = rng.multivariate_hypergeometric(data.astype(np.int64), depth)
    keep = sub > 0
    return indices[keep], sub[keep]


def build_rarefied(M_csc, depth, rng):
    """Return (M_rare_csr, kept_col_idx). Samples with total<depth dropped."""
    n_taxa, n_samp = M_csc.shape
    kept_cols = []
    new_data = []
    new_rows = []
    new_cols = []  # new column index for kept sample
    new_col_idx = 0
    for j in range(n_samp):
        start, end = M_csc.indptr[j], M_csc.indptr[j+1]
        if start == end:
            continue
        data = M_csc.data[start:end]
        idx = M_csc.indices[start:end]
        total = int(data.sum())
        if total < depth:
            continue
        sub = rng.multivariate_hypergeometric(data.astype(np.int64), depth)
        mask = sub > 0
        if not mask.any():
            continue
        new_data.append(sub[mask].astype(np.float64))
        new_rows.append(idx[mask])
        new_cols.append(np.full(mask.sum(), new_col_idx, dtype=np.int32))
        kept_cols.append(j)
        new_col_idx += 1
    if not kept_cols:
        return None, np.array([], dtype=int)
    data_arr = np.concatenate(new_data)
    row_arr = np.concatenate(new_rows)
    col_arr = np.concatenate(new_cols)
    from scipy.sparse import coo_matrix
    M_rare = coo_matrix((data_arr, (row_arr, col_arr)),
                         shape=(n_taxa, len(kept_cols))).tocsc()
    return M_rare, np.asarray(kept_cols, dtype=int)


def main():
    print("[load] EMP 90 bp deblur")
    M, obs_ids, samp_ids, tax = load_emp()
    M_csc = M.tocsc()
    meta = load_meta()
    base_biome_idx = biome_sample_indices(meta, samp_ids,
                                          min_biome_samples=MIN_BIOME_SAMPLES)
    id_to_col = {s: i for i, s in enumerate(samp_ids)}
    col_to_id = {i: s for s, i in id_to_col.items()}
    # map column idx -> biome for later
    sample_biome = {}
    for biome, cols in base_biome_idx.items():
        for c in cols:
            sample_biome[c] = biome

    rows = []
    for depth in DEPTHS:
        print(f"\n[depth={depth}] rarefying samples")
        rng = np.random.default_rng(SEED + depth)
        M_rare, kept_cols = build_rarefied(M_csc, depth, rng)
        if M_rare is None:
            print(f"  [warn] no samples with >= {depth} reads")
            continue
        n_kept = len(kept_cols)
        print(f"  kept {n_kept}/{M.shape[1]} samples at depth {depth}")

        # Re-group rarefied column index -> biome
        # new column i corresponds to original column kept_cols[i]
        new_biome_to_newcols = {}
        for new_i, orig_j in enumerate(kept_cols):
            b = sample_biome.get(orig_j)
            if b is None:
                continue
            new_biome_to_newcols.setdefault(b, []).append(new_i)
        # convert to arrays and drop biomes with too few samples
        new_biome_idx = {
            b: np.asarray(v, dtype=int)
            for b, v in new_biome_to_newcols.items()
            if len(v) >= MIN_BIOME_SAMPLES
        }
        print(f"  biomes surviving (>= {MIN_BIOME_SAMPLES} samples): "
              f"{len(new_biome_idx)}")

        fits = {}
        for biome, cols in new_biome_idx.items():
            sub = M_rare[:, cols]
            f = taylor_fit_sparse(sub, min_prev=0.2, min_taxa=30)
            if f is None:
                continue
            fits[biome] = f
        if len(fits) < 2:
            print("  [warn] fewer than 2 biomes fit, universal undefined")
            continue
        u = universal_slope(fits)
        row = dict(
            depth=depth,
            canonical=(depth == CANONICAL),
            n_samples_kept=int(n_kept),
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
    csv_path = SCRIPTS / "T5_sens_rarefaction.csv"
    df.to_csv(csv_path, index=False)
    print(f"\n[csv] {csv_path}")

    # Figure
    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    x = df["depth"].values
    y = df["universal_beta"].values
    yerr_lo = y - df["beta_ci_lo"].values
    yerr_hi = df["beta_ci_hi"].values - y
    ax.errorbar(x, y, yerr=[yerr_lo, yerr_hi],
                fmt="o", color=DECISION_COLORS["baseline"],
                ecolor="#888", capsize=3, elinewidth=0.8, markersize=6,
                zorder=3, label="universal \u03b2 (95% CI)")
    canon = df[df["canonical"]]
    if len(canon):
        ax.scatter(canon["depth"], canon["universal_beta"],
                   s=120, facecolors="none",
                   edgecolors=DECISION_COLORS["emphasis"], linewidths=1.5,
                   zorder=4, label="canonical (5000)")
    ax.axhline(1.966, color=DECISION_COLORS["emphasis"], ls="--",
               lw=1.0, label="EMP canonical \u03b2 = 1.966")
    ax.axhspan(1.85, 2.05, color="#ddd", alpha=0.35,
               label="tolerance band [1.85, 2.05]")
    ax.set_xscale("log")
    ax.set_xlabel("Rarefaction depth (reads per sample)")
    ax.set_ylabel("Universal Taylor exponent \u03b2")
    ax.set_title("T5 sensitivity: rarefaction depth", loc="left")
    ax.set_xticks(DEPTHS)
    ax.set_xticklabels([str(d) for d in DEPTHS])
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=7,
              frameon=False)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGS / "T5_sens_rarefaction.png")
    plt.close(fig)
    print(f"[figure] {FIGS / 'T5_sens_rarefaction.png'}")


if __name__ == "__main__":
    main()

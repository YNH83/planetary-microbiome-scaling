"""
T5 helper: extract per-taxon, per-biome (mean, variance, log_mean, log_var)
from the EMP 90bp BIOM, using the same prevalence filter as T5_empo3_real.py
(min_prev = 0.2, min_biome_samples = 50).

Caches the result to scripts/T5_empo3_real_moments.csv so Tasks 1 (Bayesian
hierarchical), 2 (alt nulls), and 3 (K distribution) can reuse it without
re-reading the 257 MB BIOM each time.

This script is idempotent: if the cache CSV exists, exit immediately unless
--force is given.

Usage:
    python3 scripts/T5_extract_biome_moments.py [--force]
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
RAW = ROOT / "raw data" / "emp"
BIOM_PATH = RAW / "emp_deblur_90bp.release1.biom"
META_PATH = RAW / "emp_qiime_mapping_release1.tsv"
OUT = SCRIPTS / "T5_empo3_real_moments.csv"

MIN_PREV = 0.2
MIN_BIOME_SAMPLES = 50


def load_biom(path):
    import h5py
    from scipy.sparse import csr_matrix
    with h5py.File(path, "r") as f:
        data = f["observation/matrix/data"][:]
        idx = f["observation/matrix/indices"][:]
        ptr = f["observation/matrix/indptr"][:]
        obs_ids = [x.decode() for x in f["observation/ids"][:]]
        samp_ids = [x.decode() for x in f["sample/ids"][:]]
        mat = csr_matrix((data, idx, ptr), shape=(len(obs_ids), len(samp_ids)))
    return mat, obs_ids, samp_ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if OUT.exists() and not args.force:
        print(f"cache exists: {OUT}; use --force to rebuild")
        return
    print(f"loading BIOM {BIOM_PATH.name} ({BIOM_PATH.stat().st_size / 1e6:.0f} MB)...")
    mat, obs_ids, samp_ids = load_biom(BIOM_PATH)
    print(f"  {len(obs_ids)} taxa x {len(samp_ids)} samples (sparse)")

    print("loading EMP metadata...")
    meta = pd.read_csv(META_PATH, sep="\t", dtype=str, low_memory=False)
    meta = meta[meta["#SampleID"].notna()].copy()
    meta = meta.dropna(subset=["empo_3"])
    meta = meta[~meta["empo_3"].str.contains(
        "Control|Negative|Positive|Mock|Sterile", na=False)]
    samp_to_ix = {s: i for i, s in enumerate(samp_ids)}
    meta = meta[meta["#SampleID"].isin(samp_to_ix)].copy()
    meta["col_ix"] = meta["#SampleID"].map(samp_to_ix)
    print(f"  {len(meta)} samples after cleaning; "
          f"{meta['empo_3'].nunique()} biomes")

    records = []
    csc = mat.tocsc()
    for biome, sub in meta.groupby("empo_3"):
        n = len(sub)
        if n < MIN_BIOME_SAMPLES:
            continue
        cols = sub["col_ix"].values
        # slice sparse matrix to biome, dense is OK since we filter taxa fast
        sub_mat = mat[:, cols]
        # presence count per taxon
        prev = (sub_mat > 0).sum(axis=1)
        prev = np.asarray(prev).ravel() / n
        keep_rows = np.where(prev >= MIN_PREV)[0]
        if len(keep_rows) < 30:
            continue
        kept = np.asarray(sub_mat[keep_rows, :].todense())
        mu = kept.mean(axis=1)
        var = kept.var(axis=1)
        ok = (mu > 0) & (var > 0)
        if ok.sum() < 30:
            continue
        for ti, keep in enumerate(ok):
            if not keep:
                continue
            taxon_ix = keep_rows[ti]
            records.append({
                "biome": biome,
                "taxon": obs_ids[taxon_ix],
                "n_samples": int(n),
                "mean": float(mu[ti]),
                "var": float(var[ti]),
                "log_mean": float(np.log(mu[ti])),
                "log_var": float(np.log(var[ti])),
            })
        print(f"  {biome[:30]:30s}  n={n:5d}  taxa_kept={int(ok.sum()):5d}")

    df = pd.DataFrame(records)
    df.to_csv(OUT, index=False)
    print(f"\nwrote {OUT}  ({len(df):,} rows, {df['biome'].nunique()} biomes)")
    # sanity: re-fit universal OLS beta
    from scipy import stats as sps
    slope, inter, r, p, se = sps.linregress(df["log_mean"], df["log_var"])
    print(f"  pooled universal OLS beta = {slope:.4f}, R2 = {r**2:.3f} "
          f"(expect ~1.966 from cached BIC file)")


if __name__ == "__main__":
    main()

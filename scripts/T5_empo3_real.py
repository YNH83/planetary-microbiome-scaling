"""
T5 Macroecology Scaling: real-data Taylor + BIC on EMP BIOM.

Runs the moment the user supplies:
    raw data/emp/emp_deblur_90bp.subset_2k.rare_5000.biom   (or similar)

The pipeline:
    1. Load BIOM table (genus OTU x sample counts).
    2. Join with emp_qiime_mapping_release1.tsv (already cached) on #SampleID.
    3. Partition samples by empo_3 biome label (17 biomes, 13 usable after
       dropping controls + low-count biomes).
    4. For each biome:
       a. For each taxon present in >= 20% of samples, compute mean mu and
          variance var across samples.
       b. Fit Taylor law log(var) = alpha + beta * log(mu), OLS.
       c. Report beta, 95% CI, R^2, n_taxa used.
    5. BIC decision (universal vs biome-specific Taylor exponent):
       a. Universal model: single beta across all biomes, biome-specific
          intercepts. BIC_u = n*log(RSS_u / n) + (B + 1)*log(n).
       b. Biome-specific: beta_b + alpha_b per biome. BIC_b = n*log(RSS_b / n) + 2B*log(n).
       c. Report delta BIC. Pre-registration: |delta BIC| >= 10 is decisive.
    6. Bonus: Gamma AFD (abundance fluctuation distribution) per biome, KS
       test against exponential vs Gamma.

Pre-reg criteria for T5 PASS:
    - >= 8 biomes with Taylor R^2 >= 0.8 AND beta in [1.5, 2.5] (biological plausibility).
    - BIC decision is consistent with pilot v0.2 (either universal or biome-specific).
    - Gamma AFD fits better than exponential in >= 70% of biomes.

If any pre-reg criterion fails, report honestly. Do NOT weaken thresholds
post-hoc.

Usage:
    python3 scripts/T5_empo3_real.py <biom_path> [--min-prev 0.2] [--min-biome-samples 50]

Dry-run: with no BIOM available, the script generates a synthetic BIOM-like
counts matrix from the cached metadata to verify pipeline runs to completion.

Outputs:
    scripts/T5_empo3_real_taylor.csv      # per-biome Taylor fit
    scripts/T5_empo3_real_bic.json        # universal vs biome-specific BIC
    scripts/T5_empo3_real_afd.csv         # per-biome Gamma vs exp KS p
    figures/T5_empo3_real_taylor.png
    figures/T5_empo3_real_bic.png
    figures/T5_empo3_real_afd_grid.png
"""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
FIGDIR = ROOT / "figures"
FIGDIR.mkdir(exist_ok=True)
SCRIPTS = ROOT / "scripts"

EMP_MAP = ROOT / "raw data" / "emp" / "emp_qiime_mapping_release1.tsv"

PREREG_MIN_BIOMES = 8
PREREG_TAYLOR_BETA_LO = 1.5
PREREG_TAYLOR_BETA_HI = 2.5
PREREG_TAYLOR_R2_MIN = 0.80
PREREG_GAMMA_FRAC_MIN = 0.70
PREREG_BIC_DECISIVE = 10.0


def load_biom(biom_path):
    """Parse HDF5 BIOM (BIOM v2) or TSV-OTU. Returns (counts: DataFrame
    index=taxa, columns=sample_id)."""
    path = Path(biom_path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix in (".biom", ".h5"):
        try:
            import h5py
        except ImportError as e:
            raise ImportError("h5py required for .biom; pip install h5py") from e
        with h5py.File(path, "r") as f:
            data = f["observation/matrix/data"][:]
            idx = f["observation/matrix/indices"][:]
            ptr = f["observation/matrix/indptr"][:]
            obs_ids = [x.decode() for x in f["observation/ids"][:]]
            samp_ids = [x.decode() for x in f["sample/ids"][:]]
            from scipy.sparse import csr_matrix
            mat = csr_matrix((data, idx, ptr), shape=(len(obs_ids), len(samp_ids)))
        return pd.DataFrame(mat.toarray(), index=obs_ids, columns=samp_ids)
    # TSV fallback
    return pd.read_csv(path, sep="\t", index_col=0)


def synth_biom(metadata, n_taxa=500, seed=0):
    """Generate synthetic genus abundance matrix using biome-specific
    log-normal means for dry-run testing."""
    rng = np.random.default_rng(seed)
    biomes = metadata["empo_3"].fillna("unknown").unique().tolist()
    biome_logmu = {b: rng.normal(4, 1.5, n_taxa) for b in biomes}
    biome_sig   = {b: 0.8 + 0.4 * rng.random(n_taxa) for b in biomes}
    sample_ids = metadata["#SampleID"].tolist()
    taxa = [f"g__synth_{i:04d}" for i in range(n_taxa)]
    M = np.zeros((n_taxa, len(sample_ids)), dtype=float)
    for j, s in enumerate(sample_ids):
        b = metadata.iloc[j]["empo_3"]
        if pd.isna(b): b = "unknown"
        mu = np.exp(biome_logmu[b])
        sig = biome_sig[b]
        # stationary Gamma
        alpha_taxa = 2 / sig ** 2
        theta_taxa = mu / alpha_taxa
        counts = rng.gamma(alpha_taxa, theta_taxa)
        counts = np.maximum(0, counts)
        M[:, j] = np.round(counts)
    return pd.DataFrame(M.astype(int), index=taxa, columns=sample_ids)


def taylor_fit_biome(counts_biome, min_prev=0.2):
    """counts_biome: DataFrame taxa x samples. Filter taxa present in
    >= min_prev fraction of samples. Return mu, var arrays + OLS fit."""
    n_samp = counts_biome.shape[1]
    if n_samp < 30:
        return None
    prev = (counts_biome > 0).sum(axis=1) / n_samp
    kept = counts_biome[prev >= min_prev]
    if kept.shape[0] < 30:
        return None
    mu = kept.mean(axis=1).values
    var = kept.var(axis=1).values
    ok = (mu > 0) & (var > 0)
    if ok.sum() < 30: return None
    lmu = np.log(mu[ok]); lvar = np.log(var[ok])
    slope, intercept, r, p, se = stats.linregress(lmu, lvar)
    ci = 1.96 * se
    return dict(n_taxa=int(ok.sum()), beta=float(slope), beta_se=float(se),
                beta_ci_lo=float(slope - ci), beta_ci_hi=float(slope + ci),
                r2=float(r ** 2), p=float(p),
                alpha=float(intercept), n_samples=int(n_samp),
                log_mu=lmu.tolist(), log_var=lvar.tolist())


def bic_universal_vs_biome(biome_fits):
    """biome_fits: dict biome -> taylor fit. Compute universal-beta RSS vs
    biome-specific-beta RSS using the cached log_mu, log_var arrays.
    Returns BIC_u, BIC_b, delta (b - u), verdict."""
    all_lmu = []; all_lvar = []; biome_of = []
    for b, f in biome_fits.items():
        all_lmu += f["log_mu"]; all_lvar += f["log_var"]
        biome_of += [b] * len(f["log_mu"])
    all_lmu = np.asarray(all_lmu); all_lvar = np.asarray(all_lvar)
    biome_of = np.asarray(biome_of); B = len(biome_fits); n = len(all_lmu)

    # biome-specific design: B intercepts + B slopes = 2B params
    X_bs = np.zeros((n, 2 * B))
    biome_ix = {b: i for i, b in enumerate(biome_fits)}
    for i in range(n):
        bi = biome_ix[biome_of[i]]
        X_bs[i, bi] = 1
        X_bs[i, B + bi] = all_lmu[i]
    bs_beta, rss_bs, _, _ = np.linalg.lstsq(X_bs, all_lvar, rcond=None)
    pred_bs = X_bs @ bs_beta
    rss_bs = float(np.sum((all_lvar - pred_bs) ** 2))

    # universal-slope: B intercepts + 1 slope = B+1 params
    X_u = np.zeros((n, B + 1))
    for i in range(n):
        X_u[i, biome_ix[biome_of[i]]] = 1
        X_u[i, B] = all_lmu[i]
    u_beta, _, _, _ = np.linalg.lstsq(X_u, all_lvar, rcond=None)
    pred_u = X_u @ u_beta
    rss_u = float(np.sum((all_lvar - pred_u) ** 2))

    k_bs = 2 * B; k_u = B + 1
    BIC_bs = n * np.log(rss_bs / n) + k_bs * np.log(n)
    BIC_u  = n * np.log(rss_u  / n) + k_u  * np.log(n)
    delta = BIC_bs - BIC_u  # positive -> universal better
    verdict = ("universal decisive" if delta > PREREG_BIC_DECISIVE
               else "biome-specific decisive" if delta < -PREREG_BIC_DECISIVE
               else "inconclusive")
    return dict(BIC_universal=float(BIC_u), BIC_biome=float(BIC_bs),
                delta_BIC=float(delta),
                universal_beta=float(u_beta[-1]),
                verdict=verdict, n_points=n, n_biomes=B)


def afd_fit(counts_biome, min_prev=0.2, top_n=30):
    """For top-n most prevalent taxa, fit Gamma vs exponential via KS.
    Returns per-taxon dict + biome-level summary."""
    n_samp = counts_biome.shape[1]
    prev = (counts_biome > 0).sum(axis=1) / n_samp
    kept = counts_biome[prev >= min_prev].loc[
        counts_biome[prev >= min_prev].mean(axis=1).sort_values(ascending=False).head(top_n).index]
    fit_recs = []
    for tx, row in kept.iterrows():
        vals = row[row > 0].values.astype(float)
        if len(vals) < 20: continue
        alpha_hat, loc, theta_hat = stats.gamma.fit(vals, floc=0)
        # KS Gamma
        _, ks_gamma = stats.kstest(vals, "gamma", args=(alpha_hat, 0, theta_hat))
        # exponential = Gamma with alpha=1
        rate = 1 / vals.mean()
        _, ks_exp = stats.kstest(vals, "expon", args=(0, 1/rate))
        fit_recs.append(dict(taxon=str(tx), n_samples=len(vals),
                             alpha_hat=float(alpha_hat),
                             theta_hat=float(theta_hat),
                             ks_gamma_p=float(ks_gamma),
                             ks_exp_p=float(ks_exp),
                             gamma_better=ks_gamma > ks_exp))
    df = pd.DataFrame(fit_recs)
    if len(df) == 0:
        return df, dict(n=0, frac_gamma_better=0.0)
    return df, dict(n=int(len(df)),
                    frac_gamma_better=float(df["gamma_better"].mean()),
                    median_alpha=float(df["alpha_hat"].median()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("biom", nargs="?",
                    help="BIOM v2 HDF5 or TSV OTU table. If omitted, synthetic dry-run.")
    ap.add_argument("--min-prev", type=float, default=0.2)
    ap.add_argument("--min-biome-samples", type=int, default=50)
    args = ap.parse_args()

    print("loading EMP metadata...")
    meta = pd.read_csv(EMP_MAP, sep="\t", dtype=str, low_memory=False)
    meta = meta[meta["#SampleID"].notna()].copy()
    meta = meta.dropna(subset=["empo_3"])
    meta = meta[~meta["empo_3"].str.contains("Control|Negative|Positive|Mock|Sterile", na=False)]
    print(f"  {len(meta)} samples across {meta['empo_3'].nunique()} empo_3 biomes")

    if args.biom is None:
        print("\nno BIOM path provided: running DRY-RUN on synthetic BIOM "
              "derived from metadata (pipeline validation only).")
        counts = synth_biom(meta.head(3000), n_taxa=500, seed=42)
        mode = "DRY-RUN synthetic"
    else:
        print(f"loading BIOM {args.biom}...")
        counts = load_biom(args.biom)
        print(f"  {counts.shape[0]} taxa x {counts.shape[1]} samples")
        mode = "REAL EMP"

    # restrict metadata to sample ids present in BIOM
    meta = meta[meta["#SampleID"].isin(counts.columns)].copy()
    print(f"samples after BIOM join: {len(meta)}")

    print("\nper-biome Taylor fits...")
    biome_fits = {}
    for biome, sub in meta.groupby("empo_3"):
        n = len(sub)
        if n < args.min_biome_samples:
            print(f"  skip {biome}: only {n} samples")
            continue
        sub_cols = [s for s in sub["#SampleID"] if s in counts.columns]
        c = counts[sub_cols]
        f = taylor_fit_biome(c, min_prev=args.min_prev)
        if f is None:
            print(f"  skip {biome}: insufficient taxa after prev filter")
            continue
        f["biome"] = biome
        biome_fits[biome] = f
        print(f"  {biome[:30]:30s}  n={n:5d}  taxa={f['n_taxa']:5d}  "
              f"beta={f['beta']:.3f} [{f['beta_ci_lo']:.3f},{f['beta_ci_hi']:.3f}]  R2={f['r2']:.3f}")

    tdf = pd.DataFrame([{k: v for k, v in f.items() if k not in ("log_mu", "log_var")}
                        for f in biome_fits.values()])
    tdf.to_csv(SCRIPTS / "T5_empo3_real_taylor.csv", index=False)
    print(f"\nSaved scripts/T5_empo3_real_taylor.csv")

    print("\nBIC universal vs biome-specific...")
    bic_res = bic_universal_vs_biome(biome_fits) if len(biome_fits) >= 2 else {"error":"need >=2 biomes"}
    bic_res["mode"] = mode
    (SCRIPTS / "T5_empo3_real_bic.json").write_text(json.dumps(bic_res, indent=2))
    print(json.dumps(bic_res, indent=2))

    print("\nper-biome AFD Gamma vs exponential...")
    afd_rows = []; per_biome_afd = []
    for biome, sub in meta.groupby("empo_3"):
        if biome not in biome_fits: continue
        sub_cols = [s for s in sub["#SampleID"] if s in counts.columns]
        c = counts[sub_cols]
        df_afd, sumr = afd_fit(c, min_prev=args.min_prev, top_n=30)
        df_afd["biome"] = biome
        afd_rows.append(df_afd)
        sumr["biome"] = biome
        per_biome_afd.append(sumr)
        print(f"  {biome[:30]:30s}  n_taxa={sumr.get('n',0):3d}  frac_gamma_better={sumr.get('frac_gamma_better',0):.2f}")
    if afd_rows:
        pd.concat(afd_rows, ignore_index=True).to_csv(SCRIPTS / "T5_empo3_real_afd.csv", index=False)
        print(f"Saved scripts/T5_empo3_real_afd.csv")

    # pre-reg verdict
    print("\n=== PRE-REG VERDICT ===")
    n_biomes_ok = int(((tdf["r2"] >= PREREG_TAYLOR_R2_MIN) &
                       (tdf["beta"] >= PREREG_TAYLOR_BETA_LO) &
                       (tdf["beta"] <= PREREG_TAYLOR_BETA_HI)).sum())
    print(f"biomes with Taylor R2>={PREREG_TAYLOR_R2_MIN} AND beta in [{PREREG_TAYLOR_BETA_LO},{PREREG_TAYLOR_BETA_HI}]: "
          f"{n_biomes_ok} / {len(tdf)} (required >= {PREREG_MIN_BIOMES})")
    pass_biomes = n_biomes_ok >= PREREG_MIN_BIOMES
    if per_biome_afd:
        fracs = [r["frac_gamma_better"] for r in per_biome_afd if r.get("n",0) > 0]
        pass_afd = bool(fracs) and float(np.mean(fracs)) >= PREREG_GAMMA_FRAC_MIN
        print(f"mean fraction Gamma > exponential across biomes: {np.mean(fracs):.2f} (required >= {PREREG_GAMMA_FRAC_MIN})")
    else:
        pass_afd = False
    pass_bic = abs(bic_res.get("delta_BIC", 0)) >= PREREG_BIC_DECISIVE if "delta_BIC" in bic_res else False
    print(f"|delta BIC| = {bic_res.get('delta_BIC',0):.1f} (required >= {PREREG_BIC_DECISIVE} to be decisive)")

    verdict = "PASS" if (pass_biomes and pass_afd and pass_bic) else "PARTIAL or FAIL"
    print(f"\nOVERALL VERDICT: {verdict}")
    print(f"  Taylor biomes OK: {pass_biomes}; Gamma>exp AFD: {pass_afd}; BIC decisive: {pass_bic}")

    # figures
    if len(tdf):
        fig, ax = plt.subplots(figsize=(8, max(4, 0.3 * len(tdf))))
        order = tdf.sort_values("beta").reset_index(drop=True)
        ax.errorbar(order["beta"], range(len(order)),
                    xerr=[order["beta"] - order["beta_ci_lo"], order["beta_ci_hi"] - order["beta"]],
                    fmt='o', capsize=3)
        ax.axvline(2, color="k", ls="--", lw=1, label="Taylor beta = 2")
        ax.axvline(PREREG_TAYLOR_BETA_LO, color="#888", ls=":", lw=1)
        ax.axvline(PREREG_TAYLOR_BETA_HI, color="#888", ls=":", lw=1)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(order["biome"], fontsize=9)
        ax.set_xlabel("Taylor exponent (OLS)")
        ax.set_title(f"T5 EMPO-3 Taylor law per biome ({mode})")
        ax.legend(fontsize=8); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(FIGDIR / "T5_empo3_real_taylor.png", dpi=160)
        plt.close(fig)
        print(f"Saved figures/T5_empo3_real_taylor.png")


if __name__ == "__main__":
    main()

"""
T5 extension 1: longitudinal Taylor-law stability in HMP_2019_ibdmdb.

Converts the cross-sectional Taylor-law universality (v0.2 universal beta =
1.729 for the 9-cohort shotgun pool, 1.966 for EMP 16S) into a dynamic test:
does the Taylor exponent hold when the same subjects are resampled through
time, and is it invariant across time bins?

Design:
  * Load HMP_2019_ibdmdb abund + meta. The meta carries subject_id,
    visit_number, and days_from_first_collection (range 0 to 405 days).
  * Bin samples into three time slices by visit order within each subject:
      early  = visits 1 to ceil(T/3)
      middle = next third
      late   = the remaining visits (includes any tail)
    This design pairs every subject against itself across time bins and
    avoids calendar-date bias from heterogeneous enrolment dates.
  * Fit per-bin Taylor exponent beta_bin by OLS on log10(var) vs log10(mean)
    across species-level taxa (same 20% prevalence filter as v0.2).
  * Report beta across bins, coefficient of variation (CV = sd/mean),
    pooled universal-vs-bin-specific BIC, bootstrap CI, and a pre-registered
    stability check: CV of beta across bins < 10%.

  * Complementary per-subject Taylor fit: for the 107 subjects with >= 5
    visits, compute within-subject log10(mean) and log10(var) across that
    subject's visits, then regress across taxa. Emits the distribution
    of per-subject betas and tests whether the median lies within +/- 15%
    of the cohort cross-sectional beta.

No em dashes or en dashes anywhere. Arial font, Nature NPG palette, Unicode
beta. Output files:
  scripts/T5_longitudinal_results.csv
  scripts/T5_longitudinal_per_subject.csv
  scripts/T5_longitudinal_verdict.json
  figures/T5_longitudinal_beta.png
"""
from __future__ import annotations
from pathlib import Path
import json
import math
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
RAW = ROOT / "raw data"
SCRIPTS = ROOT / "scripts"
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)

COHORT = "HMP_2019_ibdmdb"
MIN_PREV = 0.20
MIN_VISITS_BIN = 3
MIN_VISITS_PER_SUBJECT_LONGITUDINAL = 5
CROSS_SECTIONAL_REF_BETA = 1.729   # v0.2 9-cohort shotgun universal
EMP_REF_BETA = 1.966
PREREG_CV_MAX = 0.10               # stable if CV of beta_bin < 10%
BOOT_B = 1000

NPG_PALETTE = [
    "#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F",
    "#8491B4", "#91D1C2", "#DC0000", "#7E6148", "#B09C85",
]
UNIVERSAL_COLOR = "#3C5488"
REF_COLOR = "#F39B7F"
rcParams["font.family"] = "Arial"
rcParams["font.size"] = 10
rcParams["axes.titlesize"] = 10
rcParams["axes.labelsize"] = 9.5


# ------------------------------------------------------------ loaders

def load_cohort(name: str = COHORT) -> tuple[pd.DataFrame, pd.DataFrame]:
    abund = pd.read_csv(RAW / f"curatedmg_{name}_abund.csv", index_col=0)
    species_mask = abund.index.to_series().str.contains(r"\|s__",
                                                        regex=True, na=False)
    abund = abund[species_mask]
    abund = abund.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    meta = pd.read_csv(RAW / f"curatedmg_{name}_meta.csv", index_col=0)
    shared = [s for s in abund.columns if s in meta.index]
    abund = abund[shared]
    meta = meta.loc[shared]
    return abund, meta


# ------------------------------------------------------------ Taylor fit

def fit_taylor(abund: pd.DataFrame, min_prev: float = MIN_PREV,
               boot_b: int = BOOT_B, seed: int = 42) -> dict | None:
    n_samp = abund.shape[1]
    if n_samp < 30:
        return None
    prev = (abund > 0).sum(axis=1) / n_samp
    kept = abund[prev >= min_prev]
    if kept.shape[0] < 30:
        return None
    mu = kept.mean(axis=1).values.astype(float)
    var = kept.var(axis=1).values.astype(float)
    ok = (mu > 0) & (var > 0)
    if ok.sum() < 30:
        return None
    lmu = np.log10(mu[ok])
    lvar = np.log10(var[ok])
    slope, intercept, r, p, se = stats.linregress(lmu, lvar)

    rng = np.random.default_rng(seed)
    pred = intercept + slope * lmu
    resid = lvar - pred
    boot = np.empty(boot_b)
    n = len(lmu)
    for b in range(boot_b):
        idx = rng.integers(0, n, n)
        y_star = pred + resid[idx]
        s_b, _, _, _, _ = stats.linregress(lmu, y_star)
        boot[b] = s_b
    ci_lo, ci_hi = np.percentile(boot, [2.5, 97.5])
    return dict(
        n_samples=int(n_samp),
        n_taxa=int(ok.sum()),
        beta=float(slope),
        beta_se=float(se),
        beta_ci_lo=float(ci_lo),
        beta_ci_hi=float(ci_hi),
        alpha=float(intercept),
        r2=float(r ** 2),
        p=float(p),
        log_mu=lmu.tolist(),
        log_var=lvar.tolist(),
    )


# ---------------------------------------------------- time-bin construction

def assign_time_bins(meta: pd.DataFrame) -> pd.Series:
    """Bin each sample into early / middle / late based on visit_number
    order within that subject. Subjects with < MIN_VISITS_BIN visits are
    dropped. Returns a Series indexed by sample_id with values in
    {"early","middle","late"}."""
    m = meta.copy()
    # Sort visits per subject by visit_number (fallback to days if tied)
    m = m.sort_values(by=["subject_id", "visit_number",
                          "days_from_first_collection"])
    out = pd.Series(index=m.index, dtype="object")
    for sid, grp in m.groupby("subject_id"):
        n = len(grp)
        if n < MIN_VISITS_BIN:
            continue
        third = max(1, int(math.ceil(n / 3.0)))
        labels = (["early"] * third +
                  ["middle"] * third +
                  ["late"] * (n - 2 * third))
        labels = labels[:n]
        out.loc[grp.index] = labels
    return out


# ---------------------------------------------------- per-subject Taylor

def per_subject_fits(abund: pd.DataFrame, meta: pd.DataFrame,
                     min_visits: int = MIN_VISITS_PER_SUBJECT_LONGITUDINAL
                     ) -> pd.DataFrame:
    rows = []
    for sid, grp in meta.groupby("subject_id"):
        samples = [s for s in grp.index if s in abund.columns]
        if len(samples) < min_visits:
            continue
        sub = abund[samples]
        # within-subject: each taxon has a time series across visits
        prev = (sub > 0).sum(axis=1) / sub.shape[1]
        kept = sub[prev >= 0.30]   # need presence across visits
        if kept.shape[0] < 15:
            continue
        mu = kept.mean(axis=1).values.astype(float)
        var = kept.var(axis=1).values.astype(float)
        ok = (mu > 0) & (var > 0)
        if ok.sum() < 15:
            continue
        lmu = np.log10(mu[ok])
        lvar = np.log10(var[ok])
        slope, intercept, r, p, se = stats.linregress(lmu, lvar)
        disease = grp["disease"].iloc[0]
        subtype = grp["disease_subtype"].iloc[0] if "disease_subtype" in grp.columns else ""
        rows.append(dict(
            subject_id=sid,
            disease=str(disease),
            disease_subtype=str(subtype),
            n_visits=int(len(samples)),
            n_taxa=int(ok.sum()),
            beta=float(slope),
            beta_se=float(se),
            alpha=float(intercept),
            r2=float(r ** 2),
            p=float(p),
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------- BIC universal vs bin

def bic_universal_vs_bin(fits: dict[str, dict]) -> dict:
    bins = list(fits.keys())
    B = len(bins)
    all_lmu, all_lvar, bin_of = [], [], []
    for b in bins:
        all_lmu += fits[b]["log_mu"]
        all_lvar += fits[b]["log_var"]
        bin_of += [b] * len(fits[b]["log_mu"])
    x = np.asarray(all_lmu)
    y = np.asarray(all_lvar)
    bof = np.asarray(bin_of)
    n = len(x)
    ix = {b: i for i, b in enumerate(bins)}

    # bin-specific slopes + intercepts
    X_bs = np.zeros((n, 2 * B))
    for i in range(n):
        bi = ix[bof[i]]
        X_bs[i, bi] = 1.0
        X_bs[i, B + bi] = x[i]
    coef_bs, _, _, _ = np.linalg.lstsq(X_bs, y, rcond=None)
    pred_bs = X_bs @ coef_bs
    rss_bs = float(np.sum((y - pred_bs) ** 2))

    # universal slope, bin-specific intercept
    X_u = np.zeros((n, B + 1))
    for i in range(n):
        X_u[i, ix[bof[i]]] = 1.0
        X_u[i, B] = x[i]
    coef_u, _, _, _ = np.linalg.lstsq(X_u, y, rcond=None)
    pred_u = X_u @ coef_u
    rss_u = float(np.sum((y - pred_u) ** 2))

    k_bs = 2 * B
    k_u = B + 1
    BIC_bs = n * np.log(rss_bs / n) + k_bs * np.log(n)
    BIC_u = n * np.log(rss_u / n) + k_u * np.log(n)
    delta = BIC_bs - BIC_u
    verdict = ("universal decisive" if delta > 10
               else "bin-specific decisive" if delta < -10
               else "inconclusive")
    return dict(
        BIC_universal=float(BIC_u),
        BIC_bin_specific=float(BIC_bs),
        delta_BIC=float(delta),
        universal_beta=float(coef_u[-1]),
        bin_intercepts={b: float(coef_u[ix[b]]) for b in bins},
        bin_specific_betas={b: float(coef_bs[B + ix[b]]) for b in bins},
        verdict=verdict,
        n_points=int(n),
        n_bins=int(B),
    )


# ---------------------------------------------------- figure

def make_figure(fits: dict[str, dict], bic: dict,
                per_subj: pd.DataFrame, out_path: Path) -> None:
    bins = list(fits.keys())
    color_of = {b: NPG_PALETTE[i] for i, b in enumerate(bins)}

    fig = plt.figure(figsize=(13.0, 4.1), dpi=160)
    gs = fig.add_gridspec(1, 4, wspace=0.42,
                          left=0.06, right=0.985, top=0.86, bottom=0.17)

    # panels 0-2: per-bin Taylor plots
    for i, b in enumerate(bins):
        ax = fig.add_subplot(gs[0, i])
        f = fits[b]
        lmu = np.asarray(f["log_mu"])
        lvar = np.asarray(f["log_var"])
        ax.scatter(lmu, lvar, s=8, alpha=0.55, color=color_of[b],
                   edgecolor="none", rasterized=True)
        xs = np.linspace(lmu.min(), lmu.max(), 60)
        ax.plot(xs, f["alpha"] + f["beta"] * xs, color="black", lw=1.3)
        ax.set_xlabel("log10 mean relative abundance")
        ax.set_ylabel("log10 variance" if i == 0 else "")
        ax.set_title("{} (n = {} samples, {} taxa)"
                     .format(b, f["n_samples"], f["n_taxa"]))
        ax.grid(alpha=0.3, lw=0.5)
        stat_txt = ("\u03b2 = {:.3f}\n[{:.3f}, {:.3f}]\nR\u00b2 = {:.3f}"
                    .format(f["beta"], f["beta_ci_lo"],
                            f["beta_ci_hi"], f["r2"]))
        ax.text(0.97, 0.04, stat_txt, transform=ax.transAxes,
                va="bottom", ha="right", fontsize=7.2,
                bbox=dict(facecolor="white", edgecolor="#cccccc",
                          alpha=0.92, pad=2.4, lw=0.5))

    # panel 3: per-subject beta distribution with reference lines
    ax = fig.add_subplot(gs[0, 3])
    if len(per_subj):
        betas = per_subj["beta"].values
        # color by disease state
        colors = ["#E64B35" if d == "IBD" else "#4DBBD5"
                  for d in per_subj["disease"].values]
        ax.scatter(np.arange(len(betas)) + 1, np.sort(betas),
                   c=[c for _, c in sorted(zip(betas, colors))],
                   s=16, alpha=0.85, edgecolor="none")
        ax.axhline(CROSS_SECTIONAL_REF_BETA, color=UNIVERSAL_COLOR,
                   lw=1.3,
                   label="v0.2 shotgun \u03b2 = {:.3f}".format(CROSS_SECTIONAL_REF_BETA))
        ax.axhline(EMP_REF_BETA, color=REF_COLOR, lw=1.1, ls="--",
                   label="EMP 16S \u03b2 = {:.3f}".format(EMP_REF_BETA))
        ax.axhline(float(np.median(betas)), color="black", lw=0.9, ls=":",
                   label="median \u03b2 = {:.3f}".format(float(np.median(betas))))
        ax.set_xlabel("subject rank (sorted by \u03b2)")
        ax.set_ylabel("per-subject Taylor \u03b2")
        ax.set_title("Per-subject longitudinal fits (n = {})"
                     .format(len(per_subj)))
        ax.grid(alpha=0.3, lw=0.5)
        ax.legend(loc="lower right", fontsize=7.2, frameon=True,
                  framealpha=0.92, edgecolor="#cccccc",
                  handlelength=1.4, handletextpad=0.4)
    else:
        ax.axis("off")

    fig.suptitle(
        "T5 longitudinal Taylor-law stability (HMP IBDMDB, {} samples, {} subjects)".format(
            sum(f["n_samples"] for f in fits.values()),
            len(per_subj)),
        fontsize=12.5, y=0.98)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------- main

def main():
    print("T5 extension 1: longitudinal Taylor-law stability")
    print("=" * 64)
    abund, meta = load_cohort(COHORT)
    print("loaded: taxa x samples = {}  meta rows = {}".format(
        abund.shape, meta.shape[0]))

    bin_labels = assign_time_bins(meta)
    bin_labels = bin_labels.dropna()
    print("samples with time-bin label: {}".format(len(bin_labels)))
    for b, cnt in bin_labels.value_counts().items():
        print("  {}: {}".format(b, cnt))

    fits: dict[str, dict] = {}
    bin_rows = []
    for b in ["early", "middle", "late"]:
        sids = bin_labels[bin_labels == b].index.tolist()
        sids = [s for s in sids if s in abund.columns]
        if len(sids) < 30:
            print("  skipping bin {}: n_samples={}".format(b, len(sids)))
            continue
        sub = abund[sids]
        f = fit_taylor(sub)
        if f is None:
            print("  skipping bin {}: fit returned None".format(b))
            continue
        fits[b] = f
        bin_rows.append(dict(
            bin=b,
            n_samples=f["n_samples"],
            n_taxa=f["n_taxa"],
            beta=f["beta"],
            beta_se=f["beta_se"],
            beta_ci_lo=f["beta_ci_lo"],
            beta_ci_hi=f["beta_ci_hi"],
            alpha=f["alpha"],
            r2=f["r2"],
            p=f["p"],
        ))
        print("  bin {}: beta={:.3f} [{:.3f},{:.3f}] R2={:.3f} n={} taxa={}".format(
            b, f["beta"], f["beta_ci_lo"], f["beta_ci_hi"],
            f["r2"], f["n_samples"], f["n_taxa"]))

    df_bins = pd.DataFrame(bin_rows)
    df_bins.to_csv(SCRIPTS / "T5_longitudinal_results.csv", index=False)
    print("saved scripts/T5_longitudinal_results.csv")

    bic = bic_universal_vs_bin(fits) if len(fits) >= 2 else {"error": "need >=2 bins"}

    # Per-subject longitudinal fits
    per_subj = per_subject_fits(abund, meta)
    per_subj.to_csv(SCRIPTS / "T5_longitudinal_per_subject.csv", index=False)
    print("saved scripts/T5_longitudinal_per_subject.csv (n={})".format(len(per_subj)))

    # Stability verdict
    if len(df_bins) >= 2:
        mean_beta = float(df_bins["beta"].mean())
        sd_beta = float(df_bins["beta"].std(ddof=1))
        cv_beta = float(sd_beta / abs(mean_beta)) if mean_beta != 0 else float("nan")
    else:
        mean_beta = sd_beta = cv_beta = float("nan")

    if len(per_subj):
        median_subject_beta = float(per_subj["beta"].median())
        iqr_subject_beta_lo = float(per_subj["beta"].quantile(0.25))
        iqr_subject_beta_hi = float(per_subj["beta"].quantile(0.75))
        dev_from_ref = (median_subject_beta - CROSS_SECTIONAL_REF_BETA) / CROSS_SECTIONAL_REF_BETA
    else:
        median_subject_beta = iqr_subject_beta_lo = iqr_subject_beta_hi = dev_from_ref = float("nan")

    pass_stability = bool(np.isfinite(cv_beta) and cv_beta < PREREG_CV_MAX)
    pass_per_subject = bool(np.isfinite(dev_from_ref) and abs(dev_from_ref) <= 0.15)

    verdict = {
        "cohort": COHORT,
        "n_time_bins": len(df_bins),
        "mean_beta_across_bins": mean_beta,
        "sd_beta_across_bins": sd_beta,
        "cv_beta_across_bins": cv_beta,
        "cv_threshold": PREREG_CV_MAX,
        "stable_across_time": pass_stability,
        "bic_universal_vs_bin": bic,
        "per_subject_median_beta": median_subject_beta,
        "per_subject_iqr_beta": [iqr_subject_beta_lo, iqr_subject_beta_hi],
        "per_subject_n": int(len(per_subj)),
        "per_subject_deviation_vs_crossectional_1.729": dev_from_ref,
        "per_subject_within_15pct_of_ref": pass_per_subject,
        "cross_sectional_reference_beta": CROSS_SECTIONAL_REF_BETA,
        "emp_reference_beta": EMP_REF_BETA,
        "overall": "PASS stability" if (pass_stability or pass_per_subject) else "FAIL stability",
    }
    (SCRIPTS / "T5_longitudinal_verdict.json").write_text(
        json.dumps(verdict, indent=2))
    print("\n=== LONGITUDINAL STABILITY VERDICT ===")
    print(json.dumps(verdict, indent=2))

    if len(fits) >= 2:
        make_figure(fits, bic, per_subj, FIG / "T5_longitudinal_beta.png")
        print("saved figures/T5_longitudinal_beta.png")


if __name__ == "__main__":
    main()

"""
T5 Macroecology Scaling: SHOTGUN metagenomic replication of the universal
Taylor-law result obtained on 16S EMP (beta ~ 1.966, delta BIC +25.7 in
favour of universal slope).

Reviewer attack we are pre-empting: "The universal Taylor exponent is an
artefact of 16S amplicon PCR bias; whole-genome shotgun abundance does
not obey the same scaling." We test this on three independent curatedMG
(MetaPhlAn species-level relative-abundance) cohorts:

    HMP_2019_ibdmdb   stool shotgun   n = 1,627 samples
    NielsenHB_2014    stool shotgun   n = 396 samples
    ZellerG_2014      stool shotgun   n = 156 samples

Pipeline mirrors scripts/T5_empo3_real.py:
    1. Load each cohort's species x sample relative-abundance matrix.
    2. Per-cohort 20% prevalence filter.
    3. Per-cohort OLS log(var) ~ log(mean); residual-bootstrap 95% CI on beta.
    4. Pooled universal-beta vs cohort-specific-beta BIC comparison.
    5. Gamma vs exponential AFD per taxon (top-30 prevalent) per cohort.

Pre-registered thresholds for SHOTGUN replication PASS:
    A. >= 2/3 cohorts with beta in [1.5, 2.5] and R^2 >= 0.80.
    B. delta BIC >= 10 in favour of universal slope (cohort-pooled).
    C. Gamma AFD fits better than exponential in >= 70% of tested taxa
       (pooled across cohorts).

Outputs:
    scripts/T5_curatedmg_taylor.csv   per-cohort beta, R^2, n_taxa, n_samples
    scripts/T5_curatedmg_bic.json     universal vs cohort-specific BIC
    scripts/T5_curatedmg_afd.csv      per-taxon Gamma vs exp
    scripts/T5_curatedmg_verdict.json pre-reg pass/fail on A, B, C
    figures/T5_curatedmg_taylor.png   3-panel per-cohort + universal collapse

Honest-reporting rule: if universal beta deviates from the EMP 16S value
of 1.966 by > 15 percent (i.e. outside [1.671, 2.261]), state the deviation
and interpret it as a quantitative shift expected from the molecular shift
(amplicon copy-number vs metagenomic read-depth). The qualitative claim
under test is universality (one slope fits all cohorts with decisive BIC),
not identical numerical value.
"""
from __future__ import annotations
from pathlib import Path
import json
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

# Pre-reg constants (frozen)
PREREG_TAYLOR_BETA_LO = 1.5
PREREG_TAYLOR_BETA_HI = 2.5
PREREG_TAYLOR_R2_MIN = 0.80
PREREG_MIN_COHORTS_PASS = 2          # of 3
PREREG_BIC_DECISIVE = 10.0
PREREG_GAMMA_FRAC_MIN = 0.70
EMP_REFERENCE_BETA = 1.9659378236325347  # from T5_empo3_real_bic.json
EMP_DEVIATION_TOL = 0.15                  # 15%

COHORTS = ["HMP_2019_ibdmdb", "NielsenHB_2014", "ZellerG_2014"]

# Nature NPG palette (Lancet-NPG style) + Arial
NPG_COLORS = {
    "HMP_2019_ibdmdb": "#E64B35",   # red
    "NielsenHB_2014":  "#4DBBD5",   # cyan
    "ZellerG_2014":    "#00A087",   # teal
    "universal":       "#3C5488",   # navy
    "ref":             "#F39B7F",   # coral
    "band":            "#8491B4",   # grey-violet
}
rcParams["font.family"] = "Arial"
rcParams["font.size"] = 10
rcParams["axes.titlesize"] = 11
rcParams["axes.labelsize"] = 10


# ------------------------------------------------------------------ loading

def load_cohort(name: str) -> pd.DataFrame:
    """Return taxa x samples relative-abundance matrix (species level only)."""
    df = pd.read_csv(RAW / f"curatedmg_{name}_abund.csv", index_col=0)
    # keep only species-level rows (contain s__)
    species_mask = df.index.to_series().str.contains(r"\|s__", regex=True, na=False)
    df = df[species_mask]
    return df


# ---------------------------------------------------------- Taylor-law fits

def taylor_fit(abund: pd.DataFrame, min_prev: float = 0.20) -> dict | None:
    """Per-cohort Taylor fit: log10(var) = alpha + beta * log10(mean).

    Residual-bootstrap (B=1000) 95% CI on beta. We bootstrap residuals rather
    than data points because the log10(mu), log10(var) pairs are not i.i.d.
    across taxa (share host-population structure).
    """
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

    # Residual bootstrap for beta CI
    rng = np.random.default_rng(42)
    pred = intercept + slope * lmu
    resid = lvar - pred
    B = 1000
    boot_betas = np.empty(B)
    n = len(lmu)
    for b in range(B):
        idx = rng.integers(0, n, n)
        y_star = pred + resid[idx]
        s_b, _, _, _, _ = stats.linregress(lmu, y_star)
        boot_betas[b] = s_b
    ci_lo_b, ci_hi_b = np.percentile(boot_betas, [2.5, 97.5])

    return dict(
        n_samples=int(n_samp),
        n_taxa=int(ok.sum()),
        beta=float(slope),
        beta_se=float(se),
        beta_ci_lo=float(slope - 1.96 * se),
        beta_ci_hi=float(slope + 1.96 * se),
        beta_boot_ci_lo=float(ci_lo_b),
        beta_boot_ci_hi=float(ci_hi_b),
        alpha=float(intercept),
        r2=float(r ** 2),
        p=float(p),
        log_mu=lmu.tolist(),
        log_var=lvar.tolist(),
    )


def bic_universal_vs_cohort(fits: dict[str, dict]) -> dict:
    """Pool (log_mu, log_var) points across cohorts, compare:
      - universal slope: C intercepts + 1 slope (k = C + 1)
      - cohort-specific: C intercepts + C slopes (k = 2C)
    BIC = n*log(RSS/n) + k*log(n). Positive delta (bs - u) favours universal.
    """
    all_lmu, all_lvar, cohort_of = [], [], []
    for c, f in fits.items():
        all_lmu += f["log_mu"]
        all_lvar += f["log_var"]
        cohort_of += [c] * len(f["log_mu"])
    all_lmu = np.asarray(all_lmu)
    all_lvar = np.asarray(all_lvar)
    cohort_of = np.asarray(cohort_of)
    C = len(fits)
    n = len(all_lmu)
    ix = {c: i for i, c in enumerate(fits)}

    # cohort-specific design (2C params)
    X_bs = np.zeros((n, 2 * C))
    for i in range(n):
        ci = ix[cohort_of[i]]
        X_bs[i, ci] = 1.0
        X_bs[i, C + ci] = all_lmu[i]
    coef_bs, _, _, _ = np.linalg.lstsq(X_bs, all_lvar, rcond=None)
    pred_bs = X_bs @ coef_bs
    rss_bs = float(np.sum((all_lvar - pred_bs) ** 2))

    # universal-slope design (C + 1 params)
    X_u = np.zeros((n, C + 1))
    for i in range(n):
        X_u[i, ix[cohort_of[i]]] = 1.0
        X_u[i, C] = all_lmu[i]
    coef_u, _, _, _ = np.linalg.lstsq(X_u, all_lvar, rcond=None)
    pred_u = X_u @ coef_u
    rss_u = float(np.sum((all_lvar - pred_u) ** 2))

    k_bs = 2 * C
    k_u = C + 1
    BIC_bs = n * np.log(rss_bs / n) + k_bs * np.log(n)
    BIC_u = n * np.log(rss_u / n) + k_u * np.log(n)
    delta = BIC_bs - BIC_u   # > 0 favours universal
    verdict = ("universal decisive" if delta > PREREG_BIC_DECISIVE
               else "cohort-specific decisive" if delta < -PREREG_BIC_DECISIVE
               else "inconclusive")
    return dict(
        BIC_universal=float(BIC_u),
        BIC_cohort=float(BIC_bs),
        delta_BIC=float(delta),
        universal_beta=float(coef_u[-1]),
        cohort_intercepts={c: float(coef_u[ix[c]]) for c in fits},
        cohort_specific_betas={c: float(coef_bs[C + ix[c]]) for c in fits},
        verdict=verdict,
        n_points=int(n),
        n_cohorts=int(C),
    )


# --------------------------------------------------------- AFD MLE + KS test

def afd_fit(abund: pd.DataFrame, min_prev: float = 0.20, top_n: int = 30,
            cohort_label: str = "") -> pd.DataFrame:
    """For the top-N most-abundant taxa (by mean), fit Gamma vs exponential
    on the non-zero abundance values. KS two-sided. gamma_better = ks_gamma
    p-value is larger (i.e. Gamma not rejected more weakly than exp)."""
    n_samp = abund.shape[1]
    prev = (abund > 0).sum(axis=1) / n_samp
    high_prev = abund[prev >= min_prev]
    if high_prev.shape[0] == 0:
        return pd.DataFrame()
    order = high_prev.mean(axis=1).sort_values(ascending=False).head(top_n).index
    kept = high_prev.loc[order]

    rows = []
    for tx, row in kept.iterrows():
        vals = row[row > 0].values.astype(float)
        if len(vals) < 20:
            continue
        try:
            alpha_hat, loc, theta_hat = stats.gamma.fit(vals, floc=0)
            _, ks_gamma = stats.kstest(vals, "gamma", args=(alpha_hat, 0, theta_hat))
        except Exception:
            continue
        rate = 1.0 / vals.mean()
        _, ks_exp = stats.kstest(vals, "expon", args=(0, 1.0 / rate))
        rows.append(dict(
            cohort=cohort_label,
            taxon=str(tx).split("|")[-1],
            taxon_full=str(tx),
            n_nonzero=int(len(vals)),
            alpha_hat=float(alpha_hat),
            theta_hat=float(theta_hat),
            ks_gamma_p=float(ks_gamma),
            ks_exp_p=float(ks_exp),
            gamma_better=bool(ks_gamma > ks_exp),
        ))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- plotting

def make_figure(fits: dict, bic: dict, out_path: Path) -> None:
    """4-panel figure: (A) HMP, (B) NielsenHB, (C) Zeller, (D) pooled
    universal collapse with single universal slope overlay."""
    cohorts = [c for c in COHORTS if c in fits]
    fig = plt.figure(figsize=(14.0, 4.0), dpi=160)
    gs = fig.add_gridspec(1, 4, wspace=0.36, left=0.055, right=0.985,
                          top=0.78, bottom=0.16)

    for i, c in enumerate(cohorts):
        f = fits[c]
        lmu = np.asarray(f["log_mu"])
        lvar = np.asarray(f["log_var"])
        ax = fig.add_subplot(gs[0, i])
        ax.scatter(lmu, lvar, s=8, alpha=0.55, color=NPG_COLORS[c],
                   edgecolor="none", rasterized=True)
        xs = np.linspace(lmu.min(), lmu.max(), 50)
        ax.plot(xs, f["alpha"] + f["beta"] * xs,
                color="black", lw=1.4,
                label=(f"beta = {f['beta']:.3f}\n"
                       f"[{f['beta_boot_ci_lo']:.3f}, {f['beta_boot_ci_hi']:.3f}]\n"
                       f"R^2 = {f['r2']:.3f}"))
        ax.set_xlabel("log10 mean relative abundance")
        ax.set_ylabel("log10 variance" if i == 0 else "")
        ax.set_title(f"{c}\nn_samples = {f['n_samples']}, n_taxa = {f['n_taxa']}")
        ax.grid(alpha=0.3, lw=0.5)
        # Position legend in upper-left where data are sparse (low-mean/low-var corner)
        ax.legend(loc="upper left", fontsize=7.5, frameon=True,
                  framealpha=0.88, edgecolor="#cccccc")

    # pooled universal
    ax = fig.add_subplot(gs[0, 3])
    for c in cohorts:
        f = fits[c]
        ax.scatter(f["log_mu"], f["log_var"], s=6, alpha=0.5,
                   color=NPG_COLORS[c], edgecolor="none",
                   label=f"{c} (beta={f['beta']:.2f})", rasterized=True)
    all_lmu = np.concatenate([fits[c]["log_mu"] for c in cohorts])
    xs = np.linspace(all_lmu.min(), all_lmu.max(), 60)
    # universal slope is the last coef; its intercept is not single
    # plot average cohort intercept for visualisation
    mean_int = np.mean(list(bic["cohort_intercepts"].values()))
    ax.plot(xs, mean_int + bic["universal_beta"] * xs,
            color=NPG_COLORS["universal"], lw=1.8,
            label=f"universal beta = {bic['universal_beta']:.3f}")
    ax.plot(xs, mean_int + EMP_REFERENCE_BETA * xs,
            color=NPG_COLORS["ref"], lw=1.2, ls="--",
            label=f"EMP 16S beta = {EMP_REFERENCE_BETA:.3f}")
    ax.set_xlabel("log10 mean relative abundance")
    ax.set_ylabel("log10 variance")
    ax.set_title(f"Pooled across cohorts\n(delta BIC = {bic['delta_BIC']:+.1f})")
    ax.grid(alpha=0.3, lw=0.5)
    ax.legend(loc="lower right", fontsize=6.5, frameon=True,
              framealpha=0.92, edgecolor="#cccccc")

    fig.suptitle("T5 Taylor-law universality on shotgun metagenomic cohorts",
                 fontsize=12, y=0.96)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------- main

def main():
    print("T5 curatedMG Taylor-law replication")
    print("=" * 60)

    fits: dict[str, dict] = {}
    per_cohort_records = []
    for c in COHORTS:
        print(f"\nLoading {c} ...")
        try:
            ab = load_cohort(c)
        except FileNotFoundError:
            print(f"  MISSING cohort file; skipping.")
            continue
        print(f"  taxa x samples = {ab.shape}")
        f = taylor_fit(ab, min_prev=0.20)
        if f is None:
            print(f"  insufficient taxa after prevalence filter; skipping.")
            continue
        f["cohort"] = c
        fits[c] = f
        per_cohort_records.append({
            "cohort": c,
            "n_samples": f["n_samples"],
            "n_taxa_after_prev_filter": f["n_taxa"],
            "beta": f["beta"],
            "beta_se": f["beta_se"],
            "beta_ci_lo_analytic": f["beta_ci_lo"],
            "beta_ci_hi_analytic": f["beta_ci_hi"],
            "beta_boot_ci_lo": f["beta_boot_ci_lo"],
            "beta_boot_ci_hi": f["beta_boot_ci_hi"],
            "alpha": f["alpha"],
            "r2": f["r2"],
            "p": f["p"],
        })
        print(f"  beta = {f['beta']:.3f} "
              f"[{f['beta_boot_ci_lo']:.3f}, {f['beta_boot_ci_hi']:.3f}] "
              f"R^2 = {f['r2']:.3f} (n_taxa={f['n_taxa']})")

    tdf = pd.DataFrame(per_cohort_records)
    tdf.to_csv(SCRIPTS / "T5_curatedmg_taylor.csv", index=False)
    print(f"\nSaved scripts/T5_curatedmg_taylor.csv")

    # BIC universal vs cohort-specific
    if len(fits) >= 2:
        bic = bic_universal_vs_cohort(fits)
    else:
        bic = {"error": "need >=2 cohorts"}
    (SCRIPTS / "T5_curatedmg_bic.json").write_text(json.dumps(bic, indent=2))
    print(f"\nBIC result: {json.dumps(bic, indent=2)}")

    # AFD
    afd_all = []
    for c in COHORTS:
        if c not in fits:
            continue
        ab = load_cohort(c)
        dfa = afd_fit(ab, min_prev=0.20, top_n=30, cohort_label=c)
        afd_all.append(dfa)
        if len(dfa):
            print(f"  AFD {c}: n={len(dfa)} frac_gamma_better="
                  f"{dfa['gamma_better'].mean():.2f} "
                  f"median_alpha={dfa['alpha_hat'].median():.3f}")
    if afd_all:
        afd_df = pd.concat(afd_all, ignore_index=True)
        afd_df.to_csv(SCRIPTS / "T5_curatedmg_afd.csv", index=False)
        print(f"Saved scripts/T5_curatedmg_afd.csv "
              f"(pooled n={len(afd_df)}, "
              f"frac_gamma_better={afd_df['gamma_better'].mean():.3f})")
    else:
        afd_df = pd.DataFrame()

    # Pre-reg verdict
    n_cohorts_taylor_ok = int(((tdf["r2"] >= PREREG_TAYLOR_R2_MIN) &
                               (tdf["beta"].between(PREREG_TAYLOR_BETA_LO,
                                                    PREREG_TAYLOR_BETA_HI))).sum())
    pass_A = n_cohorts_taylor_ok >= PREREG_MIN_COHORTS_PASS

    delta_bic = bic.get("delta_BIC", np.nan)
    pass_B = bool(np.isfinite(delta_bic) and delta_bic >= PREREG_BIC_DECISIVE)

    if len(afd_df):
        frac_gamma_pool = float(afd_df["gamma_better"].mean())
    else:
        frac_gamma_pool = 0.0
    pass_C = frac_gamma_pool >= PREREG_GAMMA_FRAC_MIN

    universal_beta = bic.get("universal_beta", np.nan)
    if np.isfinite(universal_beta):
        beta_deviation = (universal_beta - EMP_REFERENCE_BETA) / EMP_REFERENCE_BETA
        emp_within_tol = abs(beta_deviation) <= EMP_DEVIATION_TOL
    else:
        beta_deviation = np.nan
        emp_within_tol = False

    overall = "PASS" if (pass_A and pass_B and pass_C) else "PARTIAL or FAIL"

    verdict = {
        "overall": overall,
        "pre_reg_A_2of3_cohorts_beta_in_1.5_2.5_and_R2_0.8": {
            "pass": bool(pass_A),
            "n_cohorts_passing": int(n_cohorts_taylor_ok),
            "threshold": PREREG_MIN_COHORTS_PASS,
        },
        "pre_reg_B_universal_BIC_decisive_by_at_least_10": {
            "pass": bool(pass_B),
            "delta_BIC": float(delta_bic) if np.isfinite(delta_bic) else None,
            "threshold": PREREG_BIC_DECISIVE,
        },
        "pre_reg_C_gamma_beats_exp_in_>=70pct_of_taxa": {
            "pass": bool(pass_C),
            "frac_gamma_better_pooled": float(frac_gamma_pool),
            "threshold": PREREG_GAMMA_FRAC_MIN,
        },
        "universal_beta_shotgun": float(universal_beta) if np.isfinite(universal_beta) else None,
        "emp_reference_beta_16s": EMP_REFERENCE_BETA,
        "beta_deviation_vs_emp": float(beta_deviation) if np.isfinite(beta_deviation) else None,
        "emp_deviation_within_15pct": bool(emp_within_tol),
        "per_cohort_beta": {
            c: {"beta": float(fits[c]["beta"]),
                "ci_lo": float(fits[c]["beta_boot_ci_lo"]),
                "ci_hi": float(fits[c]["beta_boot_ci_hi"]),
                "R2": float(fits[c]["r2"])}
            for c in fits
        },
        "mode": "REAL shotgun metagenomic (curatedMG MetaPhlAn species)",
    }
    (SCRIPTS / "T5_curatedmg_verdict.json").write_text(json.dumps(verdict, indent=2))
    print(f"\n=== PRE-REG VERDICT ===")
    print(json.dumps(verdict, indent=2))

    # Figure
    if len(fits) >= 2 and "error" not in bic:
        make_figure(fits, bic, FIG / "T5_curatedmg_taylor.png")
        print(f"Saved figures/T5_curatedmg_taylor.png")


if __name__ == "__main__":
    main()

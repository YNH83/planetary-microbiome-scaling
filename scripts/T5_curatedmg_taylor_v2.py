"""
T5 Macroecology Scaling v2: EXPANDED shotgun metagenomic replication.

v0.1 pooled 3 curatedMG cohorts (HMP_2019_ibdmdb, NielsenHB_2014, ZellerG_2014)
and obtained universal beta = 1.683, delta BIC +0.42 (directional universal,
not decisive at the 10-unit pre-registered bar).

v0.2 expands the replication pool to 6+ cohorts by auto-discovering every
`raw data/curatedmg_*_abund.csv` and re-running the same pipeline:
  1. Per-cohort 20% prevalence filter on species-level taxa.
  2. Per-cohort OLS log10(var) ~ log10(mean), residual-bootstrap 95% CI.
  3. Pooled universal-beta vs cohort-specific-beta BIC comparison.
  4. Gamma vs exponential AFD per taxon (top-30 prevalent) per cohort.

Pre-registered thresholds (unchanged from v0.1):
  A. >= 2/3 of cohorts with beta in [1.5, 2.5] and R^2 >= 0.80
     (generalised to >= ceil(2/3 * n_cohorts))
  B. delta BIC >= 10 in favour of universal slope (cohort-pooled).
  C. Gamma AFD fits better than exponential in >= 70% of tested taxa
     (pooled across cohorts).

Outputs (v2 suffix; v0.1 files preserved):
  scripts/T5_curatedmg_taylor_v2.csv
  scripts/T5_curatedmg_bic_v2.json
  scripts/T5_curatedmg_afd_v2.csv
  scripts/T5_curatedmg_verdict_v2.json
  figures/T5_curatedmg_taylor_v2.png
"""
from __future__ import annotations
from pathlib import Path
import json
import math
import re
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

# Pre-reg constants (frozen, shared with v0.1)
PREREG_TAYLOR_BETA_LO = 1.5
PREREG_TAYLOR_BETA_HI = 2.5
PREREG_TAYLOR_R2_MIN = 0.80
PREREG_MIN_FRAC_PASS = 2.0 / 3.0
PREREG_BIC_DECISIVE = 10.0
PREREG_GAMMA_FRAC_MIN = 0.70
EMP_REFERENCE_BETA = 1.9659378236325347
EMP_DEVIATION_TOL = 0.15

# Nature NPG 10-slot palette (Arial, no em / en dashes anywhere)
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


# ------------------------------------------------------------ cohort discovery

def discover_cohorts() -> list[str]:
    """Return cohort stems from `raw data/curatedmg_{stem}_abund.csv`."""
    pat = re.compile(r"^curatedmg_(.+)_abund\.csv$")
    stems = []
    for p in sorted(RAW.glob("curatedmg_*_abund.csv")):
        m = pat.match(p.name)
        if m:
            stems.append(m.group(1))
    return stems


def load_cohort(name: str) -> pd.DataFrame:
    """Return species-level taxa x samples relative-abundance matrix."""
    df = pd.read_csv(RAW / f"curatedmg_{name}_abund.csv", index_col=0)
    species_mask = df.index.to_series().str.contains(r"\|s__", regex=True, na=False)
    df = df[species_mask]
    # coerce to numeric (some columns may be object-typed)
    df = df.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return df


# ------------------------------------------------------------ Taylor-law fits

def taylor_fit(abund: pd.DataFrame, min_prev: float = 0.20) -> dict | None:
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

    X_bs = np.zeros((n, 2 * C))
    for i in range(n):
        ci = ix[cohort_of[i]]
        X_bs[i, ci] = 1.0
        X_bs[i, C + ci] = all_lmu[i]
    coef_bs, _, _, _ = np.linalg.lstsq(X_bs, all_lvar, rcond=None)
    pred_bs = X_bs @ coef_bs
    rss_bs = float(np.sum((all_lvar - pred_bs) ** 2))

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
    delta = BIC_bs - BIC_u
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


# ------------------------------------------------------------ AFD MLE + KS

def afd_fit(abund: pd.DataFrame, min_prev: float = 0.20, top_n: int = 30,
            cohort_label: str = "") -> pd.DataFrame:
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


# ------------------------------------------------------------ plotting

def make_figure(fits: dict, bic: dict, out_path: Path) -> None:
    cohorts = list(fits.keys())
    C = len(cohorts)
    color_of = {c: NPG_PALETTE[i % len(NPG_PALETTE)] for i, c in enumerate(cohorts)}

    # Layout: one panel per cohort plus one pooled universal panel.
    n_panels = C + 1
    ncols = min(4, n_panels)
    nrows = math.ceil(n_panels / ncols)
    fig = plt.figure(figsize=(3.6 * ncols, 3.3 * nrows), dpi=160)
    gs = fig.add_gridspec(nrows, ncols, wspace=0.38, hspace=0.50,
                          left=0.06, right=0.985, top=0.90, bottom=0.10)

    for i, c in enumerate(cohorts):
        r, k = divmod(i, ncols)
        ax = fig.add_subplot(gs[r, k])
        f = fits[c]
        lmu = np.asarray(f["log_mu"])
        lvar = np.asarray(f["log_var"])
        ax.scatter(lmu, lvar, s=7, alpha=0.55, color=color_of[c],
                   edgecolor="none", rasterized=True)
        xs = np.linspace(lmu.min(), lmu.max(), 50)
        ax.plot(xs, f["alpha"] + f["beta"] * xs,
                color="black", lw=1.3)
        ax.set_xlabel("log10 mean relative abundance")
        ax.set_ylabel("log10 variance" if k == 0 else "")
        ax.set_title("{}\nn = {} samples, {} taxa"
                     .format(c, f["n_samples"], f["n_taxa"]))
        ax.grid(alpha=0.3, lw=0.5)
        # Stat box in lower-right (below the fit line => empty for Taylor plots).
        stat_txt = ("\u03b2 = {:.3f}\n[{:.3f}, {:.3f}]\nR\u00b2 = {:.3f}"
                    .format(f["beta"], f["beta_boot_ci_lo"],
                            f["beta_boot_ci_hi"], f["r2"]))
        ax.text(0.97, 0.04, stat_txt, transform=ax.transAxes,
                va="bottom", ha="right", fontsize=6.8,
                bbox=dict(facecolor="white", edgecolor="#cccccc",
                          alpha=0.92, pad=2.4, lw=0.5))

    # Pooled panel
    i = C
    r, k = divmod(i, ncols)
    ax = fig.add_subplot(gs[r, k])
    for c in cohorts:
        f = fits[c]
        ax.scatter(f["log_mu"], f["log_var"], s=5, alpha=0.45,
                   color=color_of[c], edgecolor="none", rasterized=True)
    all_lmu = np.concatenate([fits[c]["log_mu"] for c in cohorts])
    xs = np.linspace(all_lmu.min(), all_lmu.max(), 60)
    mean_int = np.mean(list(bic["cohort_intercepts"].values()))
    ax.plot(xs, mean_int + bic["universal_beta"] * xs,
            color=UNIVERSAL_COLOR, lw=1.8,
            label="universal \u03b2 = {:.3f}".format(bic["universal_beta"]))
    ax.plot(xs, mean_int + EMP_REFERENCE_BETA * xs,
            color=REF_COLOR, lw=1.2, ls="--",
            label="EMP 16S \u03b2 = {:.3f}".format(EMP_REFERENCE_BETA))
    ax.set_xlabel("log10 mean relative abundance")
    ax.set_ylabel("log10 variance" if k == 0 else "")
    ax.set_title("Pooled ({} cohorts)\n\u0394BIC = {:+.1f}"
                 .format(C, bic["delta_BIC"]))
    ax.grid(alpha=0.3, lw=0.5)
    # Pooled-panel legend in upper-left corner OUTSIDE scatter cloud plus
    # stat text, both clamped to a semi-opaque bbox to avoid data overlap.
    ax.legend(loc="upper left", fontsize=7.0, frameon=True,
              framealpha=0.92, edgecolor="#cccccc",
              handlelength=1.4, handletextpad=0.4,
              bbox_to_anchor=(0.0, -0.18), ncol=2, borderaxespad=0.0)

    # hide unused axes cells if any
    for j in range(n_panels, nrows * ncols):
        rr, kk = divmod(j, ncols)
        ax_empty = fig.add_subplot(gs[rr, kk])
        ax_empty.axis("off")

    fig.suptitle("T5 Taylor-law universality, expanded shotgun pool",
                 fontsize=12.5, y=0.975)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------ main

def main():
    cohorts = discover_cohorts()
    print("T5 curatedMG Taylor-law replication v2 (expanded pool)")
    print("=" * 64)
    print("Discovered cohorts ({}):".format(len(cohorts)))
    for c in cohorts:
        print("  - {}".format(c))

    fits: dict[str, dict] = {}
    per_cohort_records = []
    for c in cohorts:
        print("\nLoading {} ...".format(c))
        try:
            ab = load_cohort(c)
        except FileNotFoundError:
            print("  MISSING cohort file; skipping.")
            continue
        print("  taxa x samples = {}".format(ab.shape))
        f = taylor_fit(ab, min_prev=0.20)
        if f is None:
            print("  insufficient taxa after prevalence filter; skipping.")
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
        print("  beta = {:.3f} [{:.3f}, {:.3f}] R^2 = {:.3f} (n_taxa={})".format(
            f["beta"], f["beta_boot_ci_lo"], f["beta_boot_ci_hi"],
            f["r2"], f["n_taxa"]))

    tdf = pd.DataFrame(per_cohort_records)
    tdf.to_csv(SCRIPTS / "T5_curatedmg_taylor_v2.csv", index=False)
    print("\nSaved scripts/T5_curatedmg_taylor_v2.csv")

    if len(fits) >= 2:
        bic = bic_universal_vs_cohort(fits)
    else:
        bic = {"error": "need >=2 cohorts"}
    (SCRIPTS / "T5_curatedmg_bic_v2.json").write_text(json.dumps(bic, indent=2))
    print("\nBIC result:\n{}".format(json.dumps(bic, indent=2)))

    afd_all = []
    for c in cohorts:
        if c not in fits:
            continue
        ab = load_cohort(c)
        dfa = afd_fit(ab, min_prev=0.20, top_n=30, cohort_label=c)
        afd_all.append(dfa)
        if len(dfa):
            print("  AFD {}: n={} frac_gamma_better={:.2f} median_alpha={:.3f}".format(
                c, len(dfa), dfa["gamma_better"].mean(),
                dfa["alpha_hat"].median()))
    if afd_all:
        afd_df = pd.concat(afd_all, ignore_index=True)
        afd_df.to_csv(SCRIPTS / "T5_curatedmg_afd_v2.csv", index=False)
        print("Saved scripts/T5_curatedmg_afd_v2.csv (pooled n={}, frac_gamma_better={:.3f})"
              .format(len(afd_df), afd_df["gamma_better"].mean()))
    else:
        afd_df = pd.DataFrame()

    # Pre-reg verdict
    C_total = len(tdf)
    n_cohorts_taylor_ok = int(((tdf["r2"] >= PREREG_TAYLOR_R2_MIN) &
                               (tdf["beta"].between(PREREG_TAYLOR_BETA_LO,
                                                    PREREG_TAYLOR_BETA_HI))).sum())
    thresh_pass_A = math.ceil(PREREG_MIN_FRAC_PASS * C_total) if C_total > 0 else 2
    pass_A = n_cohorts_taylor_ok >= thresh_pass_A

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
        "n_cohorts_total": int(C_total),
        "pre_reg_A_frac_cohorts_beta_in_1.5_2.5_and_R2_0.8": {
            "pass": bool(pass_A),
            "n_cohorts_passing": int(n_cohorts_taylor_ok),
            "threshold_min_cohorts": int(thresh_pass_A),
            "frac_required": PREREG_MIN_FRAC_PASS,
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
                "R2": float(fits[c]["r2"]),
                "n_samples": int(fits[c]["n_samples"])}
            for c in fits
        },
        "mode": "REAL shotgun metagenomic, expanded pool (curatedMG MetaPhlAn species)",
    }
    (SCRIPTS / "T5_curatedmg_verdict_v2.json").write_text(json.dumps(verdict, indent=2))
    print("\n=== PRE-REG VERDICT (v2) ===")
    print(json.dumps(verdict, indent=2))

    if len(fits) >= 2 and "error" not in bic:
        make_figure(fits, bic, FIG / "T5_curatedmg_taylor_v2.png")
        print("Saved figures/T5_curatedmg_taylor_v2.png")


if __name__ == "__main__":
    main()

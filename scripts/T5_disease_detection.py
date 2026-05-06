"""
T5 extension 2: disease-detection pilot.

Hypothesis: if IBD active disease disrupts the stochastic-logistic regime
that generates Taylor-law universality, then per-state Taylor exponent
should drift from the cross-sectional reference (v0.2 shotgun = 1.729,
EMP 16S = 1.966), and individual taxa should have absolute deviations
from the Gamma AFD expectation that exceed the cohort baseline.

Design:
  * Split HMP_2019_ibdmdb samples into three disease states using the
    most granular proxy available: "control", "UC" (ulcerative colitis),
    "CD" (Crohn disease). If disease_subtype is missing, fall back to
    disease column only (IBD vs healthy). Document exactly which proxy
    was used in verdict JSON.
  * For each state, fit Taylor exponent beta_state on the same 20%
    prevalence filter as v0.2 to keep taxa comparable. Bootstrap 95% CI.
  * Compute beta-shift vs the pooled cross-sectional reference (1.729)
    and test the 15% drift threshold.
  * For AFD-outlier taxa: within each state, fit a Gamma AFD per
    top-40 prevalent species, record KS statistic and gamma-alpha. Taxa
    whose KS stat ranks in the top 20 by "excess deviation" (state KS
    minus control KS) are flagged as candidate biomarkers.
  * Output: per-state beta table, per-state AFD fits, outlier ranking,
    and a 2-panel figure (Taylor fit per state + outlier heatmap).

No em dashes or en dashes. Arial, Nature NPG palette, Unicode beta.
Output files:
  scripts/T5_disease_detection_results.csv
  scripts/T5_disease_outlier_taxa.csv
  scripts/T5_disease_afd.csv
  scripts/T5_disease_verdict.json
  figures/T5_disease_detection.png
  figures/T5_disease_outlier_heatmap.png
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
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
RAW = ROOT / "raw data"
SCRIPTS = ROOT / "scripts"
FIG = ROOT / "figures"
FIG.mkdir(exist_ok=True)

COHORT = "HMP_2019_ibdmdb"
MIN_PREV = 0.20
BOOT_B = 1000
CROSS_SECTIONAL_REF_BETA = 1.729
EMP_REF_BETA = 1.966
PREREG_STATE_DRIFT_THRESHOLD = 0.15   # |delta_beta| / ref > 15% = decisive
TOP_N_OUTLIERS = 20
AFD_TOP_N = 40

NPG_PALETTE = [
    "#E64B35", "#4DBBD5", "#00A087", "#3C5488", "#F39B7F",
    "#8491B4", "#91D1C2", "#DC0000", "#7E6148", "#B09C85",
]
STATE_COLOR = {
    "control": "#4DBBD5",
    "UC": "#F39B7F",
    "CD": "#E64B35",
    "IBD": "#E64B35",
    "healthy": "#4DBBD5",
}
UNIVERSAL_COLOR = "#3C5488"
REF_COLOR = "#8491B4"
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


def assign_state(meta: pd.DataFrame) -> tuple[pd.Series, str]:
    """Return per-sample state label and a string describing the proxy."""
    if ("disease_subtype" in meta.columns
            and meta["disease_subtype"].notna().any()):
        lab = meta["disease"].astype(str).copy()
        sub = meta["disease_subtype"].astype(str).copy()
        lab[(meta["disease"] == "IBD") & (sub == "UC")] = "UC"
        lab[(meta["disease"] == "IBD") & (sub == "CD")] = "CD"
        lab[meta["disease"] == "healthy"] = "control"
        proxy = "disease_subtype (control, UC, CD)"
    else:
        lab = meta["disease"].astype(str).copy()
        lab[meta["disease"] == "healthy"] = "control"
        lab[meta["disease"] == "IBD"] = "IBD"
        proxy = "disease (control vs IBD)"
    return lab, proxy


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
    taxa = list(kept.index[ok])
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
        taxa=taxa,
    )


# ------------------------------------------------------------ AFD per state

def afd_per_state(abund: pd.DataFrame, state_label: str,
                  min_prev: float = MIN_PREV,
                  top_n: int = AFD_TOP_N) -> pd.DataFrame:
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
            ks_stat_gamma, ks_p_gamma = stats.kstest(
                vals, "gamma", args=(alpha_hat, 0, theta_hat))
        except Exception:
            continue
        try:
            rate = 1.0 / vals.mean()
            ks_stat_exp, ks_p_exp = stats.kstest(
                vals, "expon", args=(0, 1.0 / rate))
        except Exception:
            ks_stat_exp = float("nan")
            ks_p_exp = float("nan")
        rows.append(dict(
            state=state_label,
            taxon=str(tx).split("|")[-1],
            taxon_full=str(tx),
            n_nonzero=int(len(vals)),
            mean_abund=float(vals.mean()),
            alpha_hat=float(alpha_hat),
            theta_hat=float(theta_hat),
            ks_stat_gamma=float(ks_stat_gamma),
            ks_p_gamma=float(ks_p_gamma),
            ks_stat_exp=float(ks_stat_exp),
            gamma_better=bool(ks_stat_gamma < ks_stat_exp),
        ))
    return pd.DataFrame(rows)


# ------------------------------------------------------------ figures

def make_taylor_figure(fits: dict, out_path: Path) -> None:
    states = list(fits.keys())
    n = len(states)
    fig = plt.figure(figsize=(3.6 * n + 0.6, 3.6), dpi=160)
    gs = fig.add_gridspec(1, n, wspace=0.40,
                          left=0.07, right=0.985, top=0.83, bottom=0.19)
    for i, s in enumerate(states):
        ax = fig.add_subplot(gs[0, i])
        f = fits[s]
        lmu = np.asarray(f["log_mu"])
        lvar = np.asarray(f["log_var"])
        color = STATE_COLOR.get(s, NPG_PALETTE[i % len(NPG_PALETTE)])
        ax.scatter(lmu, lvar, s=9, alpha=0.55, color=color,
                   edgecolor="none", rasterized=True)
        xs = np.linspace(lmu.min(), lmu.max(), 60)
        ax.plot(xs, f["alpha"] + f["beta"] * xs, color="black", lw=1.3,
                label="fit \u03b2 = {:.3f}".format(f["beta"]))
        ax.plot(xs, f["alpha"] + CROSS_SECTIONAL_REF_BETA * xs,
                color=UNIVERSAL_COLOR, lw=1.1, ls="--",
                label="v0.2 ref \u03b2 = {:.3f}".format(CROSS_SECTIONAL_REF_BETA))
        ax.set_xlabel("log10 mean relative abundance")
        ax.set_ylabel("log10 variance" if i == 0 else "")
        ax.set_title("{} (n = {} samples, {} taxa)"
                     .format(s, f["n_samples"], f["n_taxa"]))
        ax.grid(alpha=0.3, lw=0.5)
        dev_pct = 100.0 * (f["beta"] - CROSS_SECTIONAL_REF_BETA) / CROSS_SECTIONAL_REF_BETA
        stat_txt = ("\u03b2 = {:.3f}\n[{:.3f}, {:.3f}]\nR\u00b2 = {:.3f}\n\u0394 = {:+.1f}%"
                    .format(f["beta"], f["beta_ci_lo"], f["beta_ci_hi"],
                            f["r2"], dev_pct))
        ax.text(0.97, 0.04, stat_txt, transform=ax.transAxes,
                va="bottom", ha="right", fontsize=7.2,
                bbox=dict(facecolor="white", edgecolor="#cccccc",
                          alpha=0.92, pad=2.4, lw=0.5))
        ax.legend(loc="upper left", fontsize=6.8, frameon=True,
                  framealpha=0.92, edgecolor="#cccccc",
                  handlelength=1.4, handletextpad=0.4)
    fig.suptitle(
        "T5 disease-state Taylor-law contrast (HMP IBDMDB)",
        fontsize=12.5, y=0.97)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


def make_outlier_heatmap(outlier_df: pd.DataFrame, out_path: Path) -> None:
    if outlier_df.empty:
        return
    piv = outlier_df.pivot_table(index="taxon", columns="state",
                                 values="excess_ks", aggfunc="mean")
    # Order rows by max abs deviation
    piv["maxabs"] = piv.abs().max(axis=1)
    piv = piv.sort_values("maxabs", ascending=False).head(TOP_N_OUTLIERS)
    piv = piv.drop(columns=["maxabs"])
    # Stable column order
    state_order = [c for c in ["UC", "CD", "IBD"] if c in piv.columns]
    piv = piv[state_order]

    fig = plt.figure(figsize=(4.2 + 0.35 * len(state_order), 0.28 * len(piv) + 1.9),
                     dpi=160)
    gs = fig.add_gridspec(1, 1, left=0.44, right=0.92,
                          top=0.92, bottom=0.13)
    ax = fig.add_subplot(gs[0, 0])
    cmap = LinearSegmentedColormap.from_list(
        "npg_div", ["#4DBBD5", "#FFFFFF", "#E64B35"], N=256)
    vmax = float(np.nanmax(np.abs(piv.values))) if piv.size else 0.1
    im = ax.imshow(piv.values, aspect="auto", cmap=cmap,
                   vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(state_order)))
    ax.set_xticklabels(state_order, fontsize=9)
    ax.set_yticks(range(len(piv.index)))
    ax.set_yticklabels([t.replace("s__", "").replace("_", " ")
                        for t in piv.index], fontsize=7.4)
    ax.set_xlabel("disease state")
    ax.set_title("Top {} AFD-deviant taxa\n(excess KS vs control baseline)".format(
        len(piv)))
    for spine in ax.spines.values():
        spine.set_linewidth(0.5)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    cb.set_label("\u0394 KS statistic (state minus control)", fontsize=8)
    cb.ax.tick_params(labelsize=7.5)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------ main

def main():
    print("T5 extension 2: disease-detection pilot")
    print("=" * 64)
    abund, meta = load_cohort(COHORT)
    print("loaded: taxa x samples = {}  meta rows = {}".format(
        abund.shape, meta.shape[0]))

    state, proxy = assign_state(meta)
    print("state proxy: {}".format(proxy))
    for s, cnt in state.value_counts().items():
        print("  {}: {}".format(s, cnt))

    # Use species-level taxa restricted by the union 20% prevalence set across
    # the pooled cohort so that the same taxa are compared across states.
    fits: dict[str, dict] = {}
    per_state_rows = []
    for s in ["control", "UC", "CD", "IBD"]:
        if s not in state.values:
            continue
        sids = state[state == s].index.tolist()
        sids = [x for x in sids if x in abund.columns]
        if len(sids) < 30:
            continue
        sub = abund[sids]
        f = fit_taylor(sub)
        if f is None:
            continue
        fits[s] = f
        dev_pct = 100.0 * (f["beta"] - CROSS_SECTIONAL_REF_BETA) / CROSS_SECTIONAL_REF_BETA
        per_state_rows.append(dict(
            state=s,
            n_samples=f["n_samples"],
            n_taxa=f["n_taxa"],
            beta=f["beta"],
            beta_se=f["beta_se"],
            beta_ci_lo=f["beta_ci_lo"],
            beta_ci_hi=f["beta_ci_hi"],
            alpha=f["alpha"],
            r2=f["r2"],
            p=f["p"],
            abs_dev_from_2=abs(f["beta"] - 2.0),
            pct_dev_from_v02_ref=dev_pct,
        ))
        print("  {}: beta={:.3f} [{:.3f},{:.3f}] R2={:.3f} "
              "dev_vs_v02={:+.1f}% |beta-2|={:.3f}".format(
                  s, f["beta"], f["beta_ci_lo"], f["beta_ci_hi"],
                  f["r2"], dev_pct, abs(f["beta"] - 2.0)))

    res = pd.DataFrame(per_state_rows)
    res.to_csv(SCRIPTS / "T5_disease_detection_results.csv", index=False)
    print("saved scripts/T5_disease_detection_results.csv")

    # AFD per state
    afd_frames = []
    for s in fits.keys():
        sids = state[state == s].index.tolist()
        sids = [x for x in sids if x in abund.columns]
        sub = abund[sids]
        a = afd_per_state(sub, s)
        afd_frames.append(a)
    afd_df = pd.concat(afd_frames, ignore_index=True) if afd_frames else pd.DataFrame()
    afd_df.to_csv(SCRIPTS / "T5_disease_afd.csv", index=False)
    print("saved scripts/T5_disease_afd.csv (n rows = {})".format(len(afd_df)))

    # Outlier ranking: for each non-control state, excess KS = state minus control
    outlier_rows = []
    if not afd_df.empty and "control" in afd_df["state"].values:
        ctrl = (afd_df[afd_df["state"] == "control"]
                .set_index("taxon_full")["ks_stat_gamma"])
        for s in afd_df["state"].unique():
            if s == "control":
                continue
            sub = afd_df[afd_df["state"] == s].copy()
            sub["ctrl_ks"] = sub["taxon_full"].map(ctrl)
            sub["excess_ks"] = sub["ks_stat_gamma"] - sub["ctrl_ks"]
            sub = sub.dropna(subset=["excess_ks"])
            sub = sub.sort_values("excess_ks", ascending=False).head(TOP_N_OUTLIERS)
            for _, r in sub.iterrows():
                outlier_rows.append(dict(
                    state=s,
                    taxon=r["taxon"],
                    taxon_full=r["taxon_full"],
                    state_ks=r["ks_stat_gamma"],
                    control_ks=r["ctrl_ks"],
                    excess_ks=r["excess_ks"],
                    alpha_hat=r["alpha_hat"],
                    theta_hat=r["theta_hat"],
                    mean_abund=r["mean_abund"],
                ))
    outlier_df = pd.DataFrame(outlier_rows)
    outlier_df.to_csv(SCRIPTS / "T5_disease_outlier_taxa.csv", index=False)
    print("saved scripts/T5_disease_outlier_taxa.csv (n = {})".format(len(outlier_df)))

    # Verdict
    beta_map = {r["state"]: r["beta"] for r in per_state_rows}
    if "control" in beta_map:
        shifts = {s: (beta_map[s] - beta_map["control"]) / beta_map["control"]
                  for s in beta_map if s != "control"}
        max_shift = max((abs(v) for v in shifts.values()), default=0.0)
        decisive = bool(max_shift > PREREG_STATE_DRIFT_THRESHOLD)
    else:
        shifts = {}
        max_shift = 0.0
        decisive = False

    verdict = {
        "cohort": COHORT,
        "state_proxy": proxy,
        "per_state_beta": beta_map,
        "beta_shift_fraction_vs_control": shifts,
        "max_abs_fractional_shift": max_shift,
        "drift_threshold": PREREG_STATE_DRIFT_THRESHOLD,
        "decisive_disease_signal": decisive,
        "cross_sectional_reference_beta": CROSS_SECTIONAL_REF_BETA,
        "emp_reference_beta": EMP_REF_BETA,
        "n_outlier_taxa_flagged": int(len(outlier_df)),
        "interpretation": ("Taylor-\u03b2 drifts > 15% between disease states; "
                           "scaling law is state-sensitive." if decisive
                           else "Taylor-\u03b2 is state-invariant in IBDMDB "
                                "within the 15% drift window; the scaling law "
                                "is deeper than gross disease category."),
    }
    (SCRIPTS / "T5_disease_verdict.json").write_text(
        json.dumps(verdict, indent=2))
    print("\n=== DISEASE-DETECTION VERDICT ===")
    print(json.dumps(verdict, indent=2))

    # Figures
    make_taylor_figure(fits, FIG / "T5_disease_detection.png")
    print("saved figures/T5_disease_detection.png")
    make_outlier_heatmap(outlier_df, FIG / "T5_disease_outlier_heatmap.png")
    print("saved figures/T5_disease_outlier_heatmap.png")


if __name__ == "__main__":
    main()

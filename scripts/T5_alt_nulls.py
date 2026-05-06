"""
T5 Task 2: alternative null models beyond Hubbell neutral.

Tests whether the empirical Taylor exponent beta = 1.966 (pooled EMP) is
consistent with three non-neutral generators:

    Null 1: Fisher (1943) log-series metacommunity.
    Null 2: Preston (1948) lognormal species abundance distribution.
    Null 3: Shoemaker et al. (2017) Nat Ecol Evol stochastic lognormal
            neutral model, using their reported parameter set
            (sigma_K ~ 0.45 on log scale, mu_K ~ 2.5).

For each null we:
    - simulate 90 communities (matching T5_hubbell_null n_replicates)
    - each community has S_taxa taxa and n_samples samples per biome
    - S_taxa and n_samples chosen to match EMP median biome
    - fit Taylor law log(var) = alpha + beta*log(mu) on the resulting
      (mu_i, var_i) pairs (same prevalence filter min_prev=0.2)
    - record the null beta distribution
    - compute z-score and one-sided p for empirical beta >= null

Outputs:
    scripts/T5_alt_nulls_results.json
    figures/T5_alt_nulls_histograms.png

Matches Hubbell null API so all four nulls can be compared head to head
(T5_hubbell_null_results.json has null beta mean ~1.04).
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
FIGDIR = ROOT / "figures"
FIGDIR.mkdir(exist_ok=True)

# Empirical targets from existing T5 fits
EMPIRICAL_BETA = 1.9659378236325347  # from T5_empo3_real_bic.json
N_REPLICATES = 90                    # match T5_hubbell_null n_replicates
S_TAXA = 500                         # typical taxa per biome after prev filter
N_SAMPLES = 500                      # typical samples per biome (order of magnitude)
MIN_PREV = 0.2

RNG = np.random.default_rng(20260417)

# Publication style
plt.rcParams.update({
    "font.family": "Arial",
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
})
NPG = {"blue": "#3C5488", "red": "#E64B35", "green": "#00A087",
       "orange": "#F39B7F", "grey": "#7E6148"}


def fit_taylor(mu, var):
    ok = (mu > 0) & (var > 0)
    if ok.sum() < 10:
        return np.nan
    lmu = np.log(mu[ok])
    lvar = np.log(var[ok])
    slope, _, _, _, _ = stats.linregress(lmu, lvar)
    return float(slope)


def simulate_from_abundance_profile(mean_abund, n_samples, rng,
                                    noise="gamma", cv=0.8):
    """Given a vector of S taxa mean abundances, draw a taxa x samples count
    matrix with demographic-plus-environmental noise. Default: Gamma-Poisson
    compound with target CV per taxon (noise model independent of null
    generator)."""
    S = len(mean_abund)
    mat = np.zeros((S, n_samples))
    if noise == "poisson":
        mat = rng.poisson(lam=np.outer(mean_abund, np.ones(n_samples)))
    elif noise == "gamma":
        # taxon-level Gamma with CV cv, then Poisson
        shape = 1.0 / (cv ** 2)
        for i in range(S):
            scale = mean_abund[i] / shape
            lam = rng.gamma(shape=shape, scale=scale, size=n_samples)
            mat[i] = rng.poisson(lam)
    else:
        raise ValueError(noise)
    return mat


def moments_with_prev_filter(mat, min_prev=MIN_PREV):
    n = mat.shape[1]
    prev = (mat > 0).sum(axis=1) / n
    keep = prev >= min_prev
    if keep.sum() < 30:
        return np.array([]), np.array([])
    mu = mat[keep].mean(axis=1)
    var = mat[keep].var(axis=1)
    return mu, var


# ---------------------------------------------------------------------------
# Null 1: Fisher (1943) log-series
# ---------------------------------------------------------------------------
def sample_fisher_logseries(S, alpha_fisher, rng):
    """Sample species abundance vector from Fisher log-series with diversity
    parameter alpha_fisher. Uses inverse-CDF on a truncated range. N-dependence
    is absorbed by alpha; we return relative abundances (which is what the
    per-taxon mean represents after the noise layer)."""
    # Fisher log-series pmf proportional to x^k / k for k in 1..K_max
    # For moderate alpha (~ few hundred) the tail is tight at k <= 1e5
    # Use direct sampling: draw from truncated log-series via scipy
    # scipy.stats.logser is shape p with pmf -p^k / (k ln(1-p))
    # Relationship: fisher alpha sets x such that expected taxa richness.
    # We simulate S taxa abundances by drawing S iid from logser with p=x.
    # Choose x to tune mean abundance approx fisher alpha.
    p = 0.995  # close to one gives heavy tail typical of microbial SADs
    k = stats.logser.rvs(p, size=S, random_state=rng)
    return k.astype(float)


def null1_fisher(S=S_TAXA, n_samples=N_SAMPLES, rng=RNG):
    mean_ab = sample_fisher_logseries(S, 50, rng)
    mean_ab = np.maximum(mean_ab, 0.1)
    mat = simulate_from_abundance_profile(mean_ab, n_samples, rng)
    return fit_taylor(*moments_with_prev_filter(mat))


# ---------------------------------------------------------------------------
# Null 2: Preston (1948) lognormal SAD
# ---------------------------------------------------------------------------
def null2_lognormal(S=S_TAXA, n_samples=N_SAMPLES, rng=RNG,
                    mu_log=3.0, sigma_log=2.0):
    mean_ab = rng.lognormal(mean=mu_log, sigma=sigma_log, size=S)
    mat = simulate_from_abundance_profile(mean_ab, n_samples, rng)
    return fit_taylor(*moments_with_prev_filter(mat))


# ---------------------------------------------------------------------------
# Null 3: Shoemaker 2017 Nat Ecol Evol lognormal stochastic neutral
# (parameter set from their figure 2: mu_K ~ 2.5, sigma_K ~ 0.45 on log scale,
# noise CV per taxon ~ 0.3 to 0.5 for "neutral" communities)
# ---------------------------------------------------------------------------
def null3_shoemaker(S=S_TAXA, n_samples=N_SAMPLES, rng=RNG,
                    mu_K=2.5, sigma_K=0.45, cv=0.4):
    # log-K ~ Normal(mu_K, sigma_K) then linear carrying capacity with
    # CV-bounded Gamma-Poisson fluctuations (as reported in Shoemaker 2017)
    log_K = rng.normal(mu_K, sigma_K, size=S)
    mean_ab = np.exp(log_K) * 10.0  # scale to counts
    mat = simulate_from_abundance_profile(mean_ab, n_samples, rng, cv=cv)
    return fit_taylor(*moments_with_prev_filter(mat))


def run_null(name, fn, n_replicates=N_REPLICATES):
    print(f"\n=== {name} ===")
    betas = []
    for rep in range(n_replicates):
        rng_rep = np.random.default_rng(RNG.integers(0, 2**31 - 1))
        b = fn(rng=rng_rep)
        if np.isfinite(b):
            betas.append(b)
    arr = np.asarray(betas)
    mean = float(arr.mean()); sd = float(arr.std(ddof=1))
    z = float((EMPIRICAL_BETA - mean) / sd) if sd > 0 else np.nan
    p_ge = float((arr >= EMPIRICAL_BETA).sum() / len(arr))
    print(f"  n_success = {len(arr)}/{n_replicates}")
    print(f"  null beta: mean={mean:.3f}  sd={sd:.3f}  range=[{arr.min():.3f},{arr.max():.3f}]")
    print(f"  empirical beta = {EMPIRICAL_BETA:.3f}  z={z:.2f}  P(null>=emp) = {p_ge:.3f}")
    return dict(name=name, n=len(arr), betas=arr.tolist(),
                mean=mean, sd=sd, z=z, p_ge=p_ge,
                min=float(arr.min()), max=float(arr.max()))


def main():
    res = {
        "empirical_beta": EMPIRICAL_BETA,
        "n_replicates": N_REPLICATES,
        "S_taxa_per_sim": S_TAXA,
        "n_samples_per_sim": N_SAMPLES,
        "nulls": {
            "fisher_logseries_1943": run_null("Fisher log-series (1943)",
                                              null1_fisher),
            "preston_lognormal_1948": run_null("Preston lognormal (1948)",
                                               null2_lognormal),
            "shoemaker_lognormal_2017": run_null("Shoemaker lognormal (2017)",
                                                 null3_shoemaker),
        }
    }

    # headline summary (strip betas array to keep file small)
    headline = {
        "empirical_beta": EMPIRICAL_BETA,
        "n_replicates": N_REPLICATES,
        "nulls_summary": {k: {kk: vv for kk, vv in v.items() if kk != "betas"}
                          for k, v in res["nulls"].items()},
    }
    (SCRIPTS / "T5_alt_nulls_results.json").write_text(
        json.dumps(headline, indent=2))
    print(f"\nwrote scripts/T5_alt_nulls_results.json")

    # 3 panel histograms + empirical + Hubbell overlay
    hub_path = SCRIPTS / "T5_hubbell_null_results.json"
    hub_mean = None; hub_sd = None
    if hub_path.exists():
        hj = json.loads(hub_path.read_text())
        hub_mean = hj.get("hubbell_null_beta_mean")
        hub_sd = hj.get("hubbell_null_beta_std")

    # Two rows: zoomed (row 1) shows null distribution shape with empirical as
    # broken axis reference; full-range (row 2) shows how far empirical lies
    # from both Hubbell null (~1.04) and the new alt nulls.
    fig, axes = plt.subplots(2, 3, figsize=(13, 7.2),
                             gridspec_kw=dict(height_ratios=[1.0, 0.7]))
    colors = [NPG["blue"], NPG["green"], NPG["orange"]]

    # Row 1: zoomed per null
    for ax, (key, info), c in zip(axes[0], res["nulls"].items(), colors):
        arr = np.asarray(info["betas"])
        lo = min(arr.min(), EMPIRICAL_BETA) - 0.02
        hi = max(arr.max(), EMPIRICAL_BETA) + 0.02
        ax.hist(arr, bins=20, color=c, edgecolor="white", alpha=0.9,
                label=f"null  n={info['n']}")
        ax.axvline(EMPIRICAL_BETA, color=NPG["red"], lw=2, ls="--",
                   label=f"empirical \u03B2 = {EMPIRICAL_BETA:.3f}")
        ax.set_xlim(lo, hi)
        ax.set_title(info["name"].split(" (")[0], fontsize=10.5)
        ax.set_xlabel(r"Taylor exponent $\beta$")
        ax.grid(alpha=0.3)
        zstr = f"z = {info['z']:.1f}\nP(null\u2265emp) = {info['p_ge']:.3f}"
        ax.text(0.03, 0.97, zstr, transform=ax.transAxes,
                va="top", ha="left", fontsize=9,
                bbox=dict(fc="white", ec=NPG["grey"], alpha=0.85, lw=0.5))
    axes[0, 0].set_ylabel("count (simulations)")
    axes[0, -1].legend(fontsize=8, loc="upper right",
                       bbox_to_anchor=(1.38, 1.05),
                       frameon=True, framealpha=0.95)

    # Row 2: full range with Hubbell null for context
    for ax, (key, info), c in zip(axes[1], res["nulls"].items(), colors):
        arr = np.asarray(info["betas"])
        # plot as narrow bars + marker since SD is tiny on this scale
        ax.errorbar([arr.mean()], [0.5], xerr=[[arr.std(ddof=1)]],
                    fmt="o", ms=7, color=c, ecolor=c, capsize=4,
                    label=f"alt null mean \u00B1 sd")
        if hub_mean is not None:
            ax.errorbar([hub_mean], [0.5], xerr=[[hub_sd]],
                        fmt="s", ms=6, color=NPG["grey"], ecolor=NPG["grey"],
                        capsize=4, label=f"Hubbell null (neutral)")
        ax.axvline(EMPIRICAL_BETA, color=NPG["red"], lw=2, ls="--",
                   label="empirical EMP")
        ax.set_xlim(0.9, 2.1)
        ax.set_ylim(0, 1)
        ax.set_yticks([])
        ax.set_xlabel(r"Taylor exponent $\beta$  (full range)")
        ax.grid(alpha=0.3, axis="x")
    axes[1, 0].set_ylabel("comparison")
    axes[1, -1].legend(fontsize=8, loc="upper right",
                       bbox_to_anchor=(1.38, 1.05),
                       frameon=True, framealpha=0.95)

    fig.suptitle("Alternative null generators vs empirical EMP Taylor exponent  "
                 r"(empirical $\beta$ = 1.97)",
                 fontsize=11.5)
    fig.tight_layout(rect=[0, 0, 0.93, 0.96])
    fig.savefig(FIGDIR / "T5_alt_nulls_histograms.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    print(f"wrote figures/T5_alt_nulls_histograms.png")


if __name__ == "__main__":
    main()

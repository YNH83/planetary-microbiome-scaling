"""
T5 Macroecology Scaling Laws: pilot proof-of-concept (simulation only).

Goal: verify our fitting pipeline can recover known macroecological
parameters before investing in full EMP / Tara / NEON / MetaSUB data
wrangling. Follows Grilli 2020 Nat Commun framework.

Pipeline:
1. Simulate 5 synthetic biomes with either
      (a) universal parameters (shared Taylor exponent and Gamma shape), or
      (b) biome-specific deviations.
2. Fit Taylor's Law (log-variance vs log-mean) per biome and universal.
3. Test Abundance Fluctuation Distribution (AFD) collapse under Gamma.
4. Model selection: universal vs biome-specific via BIC.
5. Emit 3 figures + a numerical summary.

Author: 2026-04-15 bootstrap (Microbiome-Epi T5).
No em dashes, no en dashes.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from scipy.optimize import curve_fit

_HERE = Path(__file__).resolve().parent
PROJECT = _HERE.parent
FIG = PROJECT / "figures"
OUT = _HERE
FIG.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(20260415)

# ---------------------------------------------------------------
# 1. Simulate data
# ---------------------------------------------------------------

def simulate_biome(n_taxa, n_samples, carrying_capacity_lognormal_sigma,
                   taylor_beta, gamma_shape_k, rng):
    """
    Simulate one biome following a Grilli-style stochastic logistic model.

    For each taxon i:
        mean abundance mu_i ~ LogNormal(0, carrying_capacity_lognormal_sigma)
        variance across samples var_i = c * mu_i ** taylor_beta   (Taylor's law)
        abundance n_ij ~ Gamma(shape = gamma_shape_k, scale = mu_i / k)
    so that E[n] = mu_i and Var[n] = mu_i^2 / k. Forcing Taylor exponent via
    rescaling: we tune k per taxon so that Var[n] = c * mu^beta.

    Returns: (n_taxa x n_samples) matrix of abundances.
    """
    mu = np.exp(rng.normal(0.0, carrying_capacity_lognormal_sigma, size=n_taxa))
    # target variance per Taylor
    c = 1.0
    target_var = c * mu ** taylor_beta
    # Gamma parameterisation: mean = k * theta, var = k * theta^2
    # choose theta per taxon: theta = target_var / mean   =>  k = mean / theta = mean^2 / target_var
    # but we also want shape parameter roughly = gamma_shape_k for AFD test.
    # Compromise: use target_var for Taylor exponent while keeping shape = gamma_shape_k
    # by setting theta = mu / gamma_shape_k and accepting that Taylor exponent
    # is an emergent property of the mean distribution (for fixed k, var = k*theta^2 = mu^2/k).
    # To realise target Taylor exponent != 2, rescale each taxon's abundance vector.
    theta = mu / gamma_shape_k
    raw = rng.gamma(shape=gamma_shape_k, scale=theta[:, None], size=(n_taxa, n_samples))
    # now rescale so empirical variance matches target_var but preserve mean
    empirical_mean = raw.mean(axis=1, keepdims=True)
    centered = raw - empirical_mean
    empirical_var = centered.var(axis=1, keepdims=True) + 1e-12
    scale = np.sqrt(target_var[:, None] / empirical_var)
    rescaled = empirical_mean + centered * scale
    rescaled = np.clip(rescaled, 1e-9, None)  # keep positive
    return rescaled, mu


def taylor_fit(abund):
    """Return (slope, intercept, r2) for log10(var) vs log10(mean) across taxa."""
    mu = abund.mean(axis=1)
    var = abund.var(axis=1)
    keep = (mu > 0) & (var > 0)
    x = np.log10(mu[keep])
    y = np.log10(var[keep])
    slope, intercept, r, p, stderr = stats.linregress(x, y)
    return slope, intercept, r ** 2, len(x)


def gamma_afd_fit(abund):
    """
    Pool samples of each taxon, rescale by taxon mean, then fit a single Gamma
    distribution to the pooled rescaled abundances. Return shape k, scale, KS p.
    """
    mu = abund.mean(axis=1, keepdims=True)
    rescaled = abund / mu  # distribution of n_ij / <n_i>
    pooled = rescaled.ravel()
    pooled = pooled[(pooled > 0) & np.isfinite(pooled)]
    # fit Gamma with fixed location 0
    shape_hat, loc_hat, scale_hat = stats.gamma.fit(pooled, floc=0.0)
    # KS test on large sample: subsample to avoid numerical 0
    sub = RNG.choice(pooled, size=min(5000, pooled.size), replace=False)
    ks, p = stats.kstest(sub, "gamma", args=(shape_hat, loc_hat, scale_hat))
    return shape_hat, scale_hat, ks, p, pooled


# ---------------------------------------------------------------
# 2. Run two scenarios
# ---------------------------------------------------------------

N_TAXA = 1000
N_SAMPLES = 500
BIOMES = ["gut", "soil", "ocean", "city", "skin"]

# Scenario A: truly universal macroecology.
universal_params = dict(
    carrying_capacity_lognormal_sigma=1.2,
    taylor_beta=2.0,
    gamma_shape_k=1.5,
)

# Scenario B: biome-specific deviations (testing the null that laws are NOT universal).
biome_specific_params = {
    "gut":   dict(carrying_capacity_lognormal_sigma=1.2, taylor_beta=2.05, gamma_shape_k=1.5),
    "soil":  dict(carrying_capacity_lognormal_sigma=1.4, taylor_beta=1.90, gamma_shape_k=1.2),
    "ocean": dict(carrying_capacity_lognormal_sigma=1.1, taylor_beta=2.10, gamma_shape_k=1.8),
    "city":  dict(carrying_capacity_lognormal_sigma=1.3, taylor_beta=2.00, gamma_shape_k=1.4),
    "skin":  dict(carrying_capacity_lognormal_sigma=1.0, taylor_beta=1.85, gamma_shape_k=1.6),
}


def run_scenario(params_per_biome, label):
    taylor_rows = []
    afd_rows = []
    all_pooled_rescaled = {}
    for biome in BIOMES:
        p = params_per_biome[biome]
        abund, mu_true = simulate_biome(
            n_taxa=N_TAXA,
            n_samples=N_SAMPLES,
            rng=RNG,
            **p,
        )
        beta_hat, inter, r2, n = taylor_fit(abund)
        taylor_rows.append({
            "biome": biome,
            "taylor_beta_true": p["taylor_beta"],
            "taylor_beta_hat": beta_hat,
            "taylor_intercept_hat": inter,
            "taylor_r2": r2,
            "n_taxa_kept": n,
        })
        k_hat, scale_hat, ks, ks_p, pooled = gamma_afd_fit(abund)
        afd_rows.append({
            "biome": biome,
            "gamma_shape_true": p["gamma_shape_k"],
            "gamma_shape_hat": k_hat,
            "gamma_scale_hat": scale_hat,
            "ks_stat": ks,
            "ks_p": ks_p,
        })
        all_pooled_rescaled[biome] = pooled
    taylor_df = pd.DataFrame(taylor_rows)
    afd_df = pd.DataFrame(afd_rows)
    return taylor_df, afd_df, all_pooled_rescaled


def universal_taylor_fit_across_biomes(params_per_biome):
    """Pool all biomes and fit a single Taylor exponent."""
    xs = []
    ys = []
    for biome in BIOMES:
        p = params_per_biome[biome]
        abund, _ = simulate_biome(N_TAXA, N_SAMPLES, rng=RNG, **p)
        mu = abund.mean(axis=1)
        var = abund.var(axis=1)
        keep = (mu > 0) & (var > 0)
        xs.append(np.log10(mu[keep]))
        ys.append(np.log10(var[keep]))
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    slope, intercept, r, p, _ = stats.linregress(x, y)
    return slope, intercept, r ** 2, len(x)


print("Scenario A: truly universal laws")
params_A = {b: universal_params for b in BIOMES}
taylor_A, afd_A, pooled_A = run_scenario(params_A, "universal")
print(taylor_A.to_string(index=False))
print(afd_A.to_string(index=False))

uni_slope_A, uni_inter_A, uni_r2_A, uni_n_A = universal_taylor_fit_across_biomes(params_A)
print(f"Universal pooled Taylor exponent (A): beta_hat={uni_slope_A:.4f}  "
      f"intercept={uni_inter_A:.4f}  r2={uni_r2_A:.4f}  n={uni_n_A}")

print("\nScenario B: biome-specific laws")
taylor_B, afd_B, pooled_B = run_scenario(biome_specific_params, "biome_specific")
print(taylor_B.to_string(index=False))
print(afd_B.to_string(index=False))

uni_slope_B, uni_inter_B, uni_r2_B, uni_n_B = universal_taylor_fit_across_biomes(biome_specific_params)
print(f"Universal pooled Taylor exponent (B): beta_hat={uni_slope_B:.4f}  "
      f"intercept={uni_inter_B:.4f}  r2={uni_r2_B:.4f}  n={uni_n_B}")

# ---------------------------------------------------------------
# 3. Model selection: universal vs biome-specific (BIC)
# ---------------------------------------------------------------

def bic_from_ols(y, y_pred, n_params, n_obs):
    """BIC for Gaussian OLS residuals."""
    resid = y - y_pred
    rss = np.sum(resid ** 2)
    sigma2_hat = rss / n_obs
    # log-likelihood under Gaussian
    ll = -0.5 * n_obs * (np.log(2 * np.pi * sigma2_hat) + 1.0)
    return n_params * np.log(n_obs) - 2.0 * ll


def model_selection_taylor(params_per_biome):
    # gather the same pooled (x, y) but keep biome labels
    xs, ys, labels = [], [], []
    for idx, biome in enumerate(BIOMES):
        p = params_per_biome[biome]
        abund, _ = simulate_biome(N_TAXA, N_SAMPLES, rng=RNG, **p)
        mu = abund.mean(axis=1)
        var = abund.var(axis=1)
        keep = (mu > 0) & (var > 0)
        xs.append(np.log10(mu[keep]))
        ys.append(np.log10(var[keep]))
        labels.append(np.full(keep.sum(), idx))
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    label = np.concatenate(labels)
    n = len(x)

    # Universal model: 2 params (slope, intercept)
    slope_u, inter_u, *_ = stats.linregress(x, y)
    y_pred_u = slope_u * x + inter_u
    bic_u = bic_from_ols(y, y_pred_u, n_params=2, n_obs=n)

    # Biome-specific: 2 params per biome
    y_pred_b = np.zeros_like(y)
    for idx in range(len(BIOMES)):
        m = label == idx
        sl, it, *_ = stats.linregress(x[m], y[m])
        y_pred_b[m] = sl * x[m] + it
    bic_b = bic_from_ols(y, y_pred_b, n_params=2 * len(BIOMES), n_obs=n)

    return bic_u, bic_b


bic_uA, bic_bA = model_selection_taylor(params_A)
bic_uB, bic_bB = model_selection_taylor(biome_specific_params)
print(f"\nBIC (Scenario A universal):  universal={bic_uA:.1f}  biome_specific={bic_bA:.1f}  Delta={bic_bA - bic_uA:+.1f}")
print(f"BIC (Scenario B specific):   universal={bic_uB:.1f}  biome_specific={bic_bB:.1f}  Delta={bic_bB - bic_uB:+.1f}")

# Convention: smaller BIC wins. Universal wins in Scenario A, biome-specific wins in B.

# ---------------------------------------------------------------
# 4. Figures
# ---------------------------------------------------------------

COLORS = {"gut": "#d62728", "soil": "#8c564b", "ocean": "#1f77b4",
          "city": "#ff7f0e", "skin": "#e377c2"}

def fig_taylor(params_per_biome, out_path, suptitle):
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    slopes = []
    for biome in BIOMES:
        p = params_per_biome[biome]
        abund, _ = simulate_biome(N_TAXA, N_SAMPLES, rng=RNG, **p)
        mu = abund.mean(axis=1)
        var = abund.var(axis=1)
        keep = (mu > 0) & (var > 0)
        x = np.log10(mu[keep])
        y = np.log10(var[keep])
        slope, inter, r, _, _ = stats.linregress(x, y)
        slopes.append((biome, slope))
        ax.scatter(x, y, s=6, alpha=0.25, color=COLORS[biome],
                   label=f"{biome}  beta={slope:.2f}")
    xline = np.linspace(-3, 3, 50)
    ax.plot(xline, 2 * xline + 0, "k--", lw=1.3, label="universal beta=2 reference")
    ax.set_xlabel(r"$\log_{10}$ mean abundance across samples")
    ax.set_ylabel(r"$\log_{10}$ variance across samples")
    ax.set_title(suptitle)
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    return slopes


slopes_A = fig_taylor(params_A, FIG / "T5_fig1_taylor_universal.png",
                      "Scenario A: universal Taylor's Law recovered")
slopes_B = fig_taylor(biome_specific_params, FIG / "T5_fig1_taylor_biomespec.png",
                      "Scenario B: biome-specific Taylor exponents")
print(f"\nFig1 Taylor plots written: {FIG / 'T5_fig1_taylor_universal.png'}")
print(f"Fig1 Taylor plots written: {FIG / 'T5_fig1_taylor_biomespec.png'}")


def fig_afd_collapse(pooled_dict, out_path, suptitle):
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    bins = np.linspace(0, 5, 60)
    for biome, pooled in pooled_dict.items():
        sub = pooled[(pooled > 0) & (pooled < 10)]
        hist, edges = np.histogram(sub, bins=bins, density=True)
        centers = 0.5 * (edges[1:] + edges[:-1])
        ax.plot(centers, hist, marker="o", lw=1, ms=3,
                alpha=0.8, color=COLORS[biome], label=biome)
    # overlay Gamma(k=1.5, theta=1/1.5) as predicted universal AFD
    k_overlay = 1.5
    x_ref = np.linspace(0.01, 5, 200)
    y_ref = stats.gamma.pdf(x_ref, k_overlay, scale=1.0 / k_overlay)
    ax.plot(x_ref, y_ref, "k--", lw=1.5, label=f"Gamma(k={k_overlay}) reference")
    ax.set_xlabel(r"rescaled abundance $n_{ij} / \langle n_i \rangle$")
    ax.set_ylabel("density")
    ax.set_title(suptitle)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


fig_afd_collapse(pooled_A, FIG / "T5_fig2_afd_universal.png",
                 "Scenario A: universal Gamma AFD collapse")
fig_afd_collapse(pooled_B, FIG / "T5_fig2_afd_biomespec.png",
                 "Scenario B: biome-specific AFD deviation")
print(f"Fig2 AFD plots written.")


def fig_bic(bic_pairs, out_path):
    fig, ax = plt.subplots(figsize=(6.0, 4.5))
    labels = ["Scenario A\n(true universal)", "Scenario B\n(true biome-specific)"]
    uni = [bic_pairs["A"][0], bic_pairs["B"][0]]
    spec = [bic_pairs["A"][1], bic_pairs["B"][1]]
    x_pos = np.arange(len(labels))
    w = 0.35
    ax.bar(x_pos - w / 2, uni, w, label="Universal (2 params)", color="#2ca02c")
    ax.bar(x_pos + w / 2, spec, w, label="Biome-specific (10 params)", color="#d62728")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels)
    ax.set_ylabel("BIC (lower = better)")
    ax.set_title("Model selection: universal vs biome-specific Taylor's Law")
    ax.legend(fontsize=9)
    for i, (u, s) in enumerate(zip(uni, spec)):
        ax.annotate(f"Delta={s - u:+.0f}", xy=(x_pos[i], max(u, s) * 1.02),
                    ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


fig_bic({"A": (bic_uA, bic_bA), "B": (bic_uB, bic_bB)},
        FIG / "T5_fig3_bic_modelselect.png")
print(f"Fig3 BIC plot written.")

# ---------------------------------------------------------------
# 5. JSON summary of numerical results
# ---------------------------------------------------------------

summary = {
    "scenario_A_universal": {
        "per_biome_taylor": taylor_A.to_dict(orient="records"),
        "per_biome_afd": afd_A.to_dict(orient="records"),
        "pooled_universal_taylor_beta": uni_slope_A,
        "pooled_universal_taylor_r2": uni_r2_A,
        "bic_universal": bic_uA,
        "bic_biome_specific": bic_bA,
        "delta_bic_bminusa": bic_bA - bic_uA,
        "winner_by_bic": "universal" if bic_uA < bic_bA else "biome_specific",
    },
    "scenario_B_biome_specific": {
        "per_biome_taylor": taylor_B.to_dict(orient="records"),
        "per_biome_afd": afd_B.to_dict(orient="records"),
        "pooled_universal_taylor_beta": uni_slope_B,
        "pooled_universal_taylor_r2": uni_r2_B,
        "bic_universal": bic_uB,
        "bic_biome_specific": bic_bB,
        "delta_bic_bminusa": bic_bB - bic_uB,
        "winner_by_bic": "universal" if bic_uB < bic_bB else "biome_specific",
    },
    "sim_config": {
        "n_taxa": N_TAXA,
        "n_samples": N_SAMPLES,
        "biomes": BIOMES,
        "seed": 20260415,
    },
}

with open(OUT / "T5_pilot_results.json", "w") as f:
    json.dump(summary, f, indent=2, default=float)
print(f"\nJSON summary written: {OUT / 'T5_pilot_results.json'}")
print("Done.")

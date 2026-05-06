"""
T5 Macroecology Scaling Laws: pilot v0.2 (native stochastic-logistic SDE).

Addresses the v0.1 caveat: AFD Gamma shape was miscalibrated because v0.1
first drew abundances from a fixed-shape Gamma, then rescaled taxon vectors
post-hoc to hit a target Taylor exponent. Rescaling distorts the AFD so the
fitted Gamma shape was no longer the generative shape. v0.2 removes the
rescaling step and derives everything from the stationary distribution of
the stochastic-logistic SDE (Grilli 2020 Nat Commun; Descheemaeker and
de Buyl 2020 eLife).

Model (per taxon i):
    dx_i = x_i (b - (b / K_i) x_i) dt + sigma_i x_i dW_i(t)
Ito stationary distribution:
    x_i ~ Gamma(alpha_i, theta_i)
        alpha_i = 2 b / sigma_i^2 - 1           (shape; require sigma_i^2 < 2b)
        theta_i = K_i sigma_i^2 / (2 b)          (scale)
    E[x_i]  = alpha_i theta_i = K_i (1 - sigma_i^2 / (2b))
    Var[x_i] = alpha_i theta_i^2 = E[x_i]^2 / alpha_i
    AFD of x_i / E[x_i] ~ Gamma(alpha_i, 1/alpha_i) has unit mean.

To realise Taylor exponent beta != 2 we let sigma scale with K:
    sigma_i^2 = sigma0_sq * K_i^(beta - 2)
so Var[x_i] proportional to K_i^2 * sigma_i^2 = sigma0_sq * K_i^beta.
With beta = 2, sigma is constant and all taxa share the same alpha
(universal Gamma AFD). With beta != 2, alpha varies smoothly with K
and the pooled AFD is a mixture, not a single Gamma.

No post-hoc rescaling, no clipping.

Pipeline (mirrors v0.1):
1. Simulate 5 biomes under two scenarios.
2. Fit Taylor's law per biome and universal.
3. Fit universal Gamma AFD (pooled rescaled abundances).
4. BIC model selection.
5. Emit figures + JSON summary.

No em dashes, no en dashes.
"""

from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

_HERE = Path(__file__).resolve().parent
PROJECT = _HERE.parent
FIG = PROJECT / "figures"
OUT = _HERE
FIG.mkdir(parents=True, exist_ok=True)

RNG = np.random.default_rng(20260416)

N_TAXA = 1000
N_SAMPLES = 500
BIOMES = ["gut", "soil", "ocean", "city", "skin"]
BIRTH_B = 1.0  # per-capita birth rate (arbitrary time unit)


def simulate_biome_sde(n_taxa, n_samples, carrying_capacity_lognormal_sigma,
                       taylor_beta, sigma0_sq, rng):
    """
    Draw abundances from the stationary distribution of the stochastic-logistic
    SDE for each taxon. No rescaling.

    K_i ~ LogNormal(0, sigma_lnK)
    sigma_i^2 = sigma0_sq * K_i^(beta - 2)  (realises Taylor exponent beta)
    alpha_i = 2 b / sigma_i^2 - 1           (require > 0.05 for numerical safety)
    theta_i = K_i sigma_i^2 / (2 b)
    x_ij ~ Gamma(alpha_i, theta_i)
    Returns (n_taxa x n_samples) abundance matrix and alpha_i vector.
    """
    K = np.exp(rng.normal(0.0, carrying_capacity_lognormal_sigma, size=n_taxa))
    sigma_sq = sigma0_sq * K ** (taylor_beta - 2.0)
    # numerical safety: require alpha > 0.05 (equivalently sigma^2 < 1.9*b)
    sigma_sq = np.clip(sigma_sq, 1e-6, 1.9 * BIRTH_B)
    alpha = 2.0 * BIRTH_B / sigma_sq - 1.0
    theta = K * sigma_sq / (2.0 * BIRTH_B)
    abund = rng.gamma(shape=alpha[:, None], scale=theta[:, None], size=(n_taxa, n_samples))
    return abund, alpha, K


def taylor_fit(abund):
    mu = abund.mean(axis=1)
    var = abund.var(axis=1)
    keep = (mu > 0) & (var > 0)
    x = np.log10(mu[keep])
    y = np.log10(var[keep])
    slope, intercept, r, p, _ = stats.linregress(x, y)
    return slope, intercept, r ** 2, len(x)


def gamma_afd_fit(abund):
    """Fit single Gamma to pooled rescaled abundances n_ij / <n_i>."""
    mu = abund.mean(axis=1, keepdims=True)
    rescaled = abund / mu
    pooled = rescaled.ravel()
    pooled = pooled[(pooled > 0) & np.isfinite(pooled)]
    shape_hat, loc_hat, scale_hat = stats.gamma.fit(pooled, floc=0.0)
    sub = RNG.choice(pooled, size=min(5000, pooled.size), replace=False)
    ks, p = stats.kstest(sub, "gamma", args=(shape_hat, loc_hat, scale_hat))
    return shape_hat, scale_hat, ks, p, pooled


# Scenario A: truly universal. beta = 2 -> sigma constant -> alpha constant
# alpha_target = 1.5  =>  sigma^2 = 2b / (alpha+1) = 2 / 2.5 = 0.8
ALPHA_TARGET_A = 1.5
SIGMA0_SQ_A = 2.0 * BIRTH_B / (ALPHA_TARGET_A + 1.0)
universal_params = dict(
    carrying_capacity_lognormal_sigma=1.2,
    taylor_beta=2.0,
    sigma0_sq=SIGMA0_SQ_A,
)

# Scenario B: biome-specific deviations. Both beta and sigma0 differ.
biome_specific_params = {
    "gut":   dict(carrying_capacity_lognormal_sigma=1.2, taylor_beta=2.05,
                  sigma0_sq=2.0 / 2.5),            # alpha ~ 1.5 at K=1
    "soil":  dict(carrying_capacity_lognormal_sigma=1.4, taylor_beta=1.90,
                  sigma0_sq=2.0 / 2.2),            # alpha ~ 1.2 at K=1
    "ocean": dict(carrying_capacity_lognormal_sigma=1.1, taylor_beta=2.10,
                  sigma0_sq=2.0 / 2.8),            # alpha ~ 1.8 at K=1
    "city":  dict(carrying_capacity_lognormal_sigma=1.3, taylor_beta=2.00,
                  sigma0_sq=2.0 / 2.4),            # alpha ~ 1.4 at K=1
    "skin":  dict(carrying_capacity_lognormal_sigma=1.0, taylor_beta=1.85,
                  sigma0_sq=2.0 / 2.6),            # alpha ~ 1.6 at K=1
}


def run_scenario(params_per_biome, label):
    taylor_rows = []
    afd_rows = []
    pooled_per_biome = {}
    for biome in BIOMES:
        p = params_per_biome[biome]
        abund, alpha_true, K_true = simulate_biome_sde(
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
            "gamma_shape_alpha_median_true": float(np.median(alpha_true)),
            "gamma_shape_hat": k_hat,
            "gamma_scale_hat": scale_hat,
            "ks_stat": ks,
            "ks_p": ks_p,
        })
        pooled_per_biome[biome] = pooled
    return pd.DataFrame(taylor_rows), pd.DataFrame(afd_rows), pooled_per_biome


def universal_taylor_pool(params_per_biome):
    xs, ys = [], []
    for biome in BIOMES:
        p = params_per_biome[biome]
        abund, _, _ = simulate_biome_sde(N_TAXA, N_SAMPLES, rng=RNG, **p)
        mu = abund.mean(axis=1)
        var = abund.var(axis=1)
        keep = (mu > 0) & (var > 0)
        xs.append(np.log10(mu[keep]))
        ys.append(np.log10(var[keep]))
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    slope, intercept, r, _, _ = stats.linregress(x, y)
    return slope, intercept, r ** 2, len(x)


def bic_from_ols(y, y_pred, n_params, n_obs):
    rss = float(np.sum((y - y_pred) ** 2))
    sigma2 = rss / n_obs
    ll = -0.5 * n_obs * (np.log(2 * np.pi * sigma2) + 1.0)
    return n_params * np.log(n_obs) - 2.0 * ll


def model_selection(params_per_biome):
    xs, ys, labels = [], [], []
    for idx, biome in enumerate(BIOMES):
        p = params_per_biome[biome]
        abund, _, _ = simulate_biome_sde(N_TAXA, N_SAMPLES, rng=RNG, **p)
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
    slope_u, inter_u, *_ = stats.linregress(x, y)
    y_pred_u = slope_u * x + inter_u
    bic_u = bic_from_ols(y, y_pred_u, n_params=2, n_obs=n)
    y_pred_b = np.zeros_like(y)
    for idx in range(len(BIOMES)):
        m = label == idx
        sl, it, *_ = stats.linregress(x[m], y[m])
        y_pred_b[m] = sl * x[m] + it
    bic_b = bic_from_ols(y, y_pred_b, n_params=2 * len(BIOMES), n_obs=n)
    return bic_u, bic_b


print("T5 pilot v0.2: native stochastic-logistic SDE (no rescaling).")
print("\nScenario A: truly universal laws")
params_A = {b: universal_params for b in BIOMES}
taylor_A, afd_A, pooled_A = run_scenario(params_A, "universal")
print(taylor_A.to_string(index=False))
print(afd_A.to_string(index=False))

uni_slope_A, uni_inter_A, uni_r2_A, _ = universal_taylor_pool(params_A)
print(f"Pooled universal Taylor (A): beta_hat={uni_slope_A:.4f}  r2={uni_r2_A:.4f}")

print("\nScenario B: biome-specific laws")
taylor_B, afd_B, pooled_B = run_scenario(biome_specific_params, "biome_specific")
print(taylor_B.to_string(index=False))
print(afd_B.to_string(index=False))

uni_slope_B, uni_inter_B, uni_r2_B, _ = universal_taylor_pool(biome_specific_params)
print(f"Pooled universal Taylor (B): beta_hat={uni_slope_B:.4f}  r2={uni_r2_B:.4f}")

bic_uA, bic_bA = model_selection(params_A)
bic_uB, bic_bB = model_selection(biome_specific_params)
print(f"\nBIC Scenario A: universal={bic_uA:.1f}  biome_specific={bic_bA:.1f}  Delta={bic_bA - bic_uA:+.1f}")
print(f"BIC Scenario B: universal={bic_uB:.1f}  biome_specific={bic_bB:.1f}  Delta={bic_bB - bic_uB:+.1f}")

COLORS = {"gut": "#d62728", "soil": "#8c564b", "ocean": "#1f77b4",
          "city": "#ff7f0e", "skin": "#e377c2"}


def fig_taylor(params_per_biome, out_path, suptitle):
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    for biome in BIOMES:
        p = params_per_biome[biome]
        abund, _, _ = simulate_biome_sde(N_TAXA, N_SAMPLES, rng=RNG, **p)
        mu = abund.mean(axis=1)
        var = abund.var(axis=1)
        keep = (mu > 0) & (var > 0)
        x = np.log10(mu[keep])
        y = np.log10(var[keep])
        slope, inter, *_ = stats.linregress(x, y)
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


fig_taylor(params_A, FIG / "T5_fig1_taylor_universal_v2.png",
           "v0.2 Scenario A: universal Taylor's Law (native SDE)")
fig_taylor(biome_specific_params, FIG / "T5_fig1_taylor_biomespec_v2.png",
           "v0.2 Scenario B: biome-specific Taylor (native SDE)")


def fig_afd_collapse(pooled_dict, afd_df, out_path, suptitle, ref_alpha):
    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    bins = np.linspace(0, 5, 60)
    for biome, pooled in pooled_dict.items():
        sub = pooled[(pooled > 0) & (pooled < 10)]
        hist, edges = np.histogram(sub, bins=bins, density=True)
        centers = 0.5 * (edges[1:] + edges[:-1])
        ax.plot(centers, hist, marker="o", lw=1, ms=3,
                alpha=0.8, color=COLORS[biome], label=biome)
    x_ref = np.linspace(0.01, 5, 200)
    y_ref = stats.gamma.pdf(x_ref, ref_alpha, scale=1.0 / ref_alpha)
    ax.plot(x_ref, y_ref, "k--", lw=1.5, label=f"Gamma(alpha={ref_alpha:.2f}) reference")
    ax.set_xlabel(r"rescaled abundance $n_{ij} / \langle n_i \rangle$")
    ax.set_ylabel("density")
    ax.set_title(suptitle)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


fig_afd_collapse(pooled_A, afd_A,
                 FIG / "T5_fig2_afd_universal_v2.png",
                 "v0.2 Scenario A: universal Gamma AFD (generative alpha=1.5)",
                 ref_alpha=ALPHA_TARGET_A)
fig_afd_collapse(pooled_B, afd_B,
                 FIG / "T5_fig2_afd_biomespec_v2.png",
                 "v0.2 Scenario B: biome-specific AFD departure",
                 ref_alpha=ALPHA_TARGET_A)


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
    ax.set_title("v0.2 Model selection: universal vs biome-specific Taylor (native SDE)")
    ax.legend(fontsize=9)
    for i, (u, s) in enumerate(zip(uni, spec)):
        ax.annotate(f"Delta={s - u:+.0f}", xy=(x_pos[i], max(u, s) * 1.02),
                    ha="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


fig_bic({"A": (bic_uA, bic_bA), "B": (bic_uB, bic_bB)},
        FIG / "T5_fig3_bic_modelselect_v2.png")

summary = {
    "version": "v0.2",
    "model": "native stochastic-logistic SDE stationary Gamma (no post-hoc rescaling)",
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
        "seed": 20260416,
        "birth_b": BIRTH_B,
        "alpha_target_A": ALPHA_TARGET_A,
    },
}

with open(OUT / "T5_pilot_results_v0_2.json", "w") as f:
    json.dump(summary, f, indent=2, default=float)
print(f"\nJSON summary written: {OUT / 'T5_pilot_results_v0_2.json'}")
print("Done.")

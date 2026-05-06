"""
T5 Task 1: Bayesian hierarchical partial-pooling Taylor law (PyMC).

For taxon i within biome b, observe (log_mean_i,b, log_var_i,b). We fit

    log_var_i,b = alpha_b  +  (beta_global + beta_b_offset) * log_mean_i,b + eps_i,b

with priors (preregistered, as specified in task brief):

    alpha_b        ~ Normal(0, 5)              # free biome intercept
    beta_global    ~ Normal(2, 0.5)            # centred on Taylor's law exponent
    beta_b_offset  ~ Normal(0, tau)            # partial-pooled biome departure
    tau            ~ HalfCauchy(0.1)           # how much biomes depart from 2
    sigma          ~ HalfNormal(1)             # taxon-level noise

Model comparison via PSIS-LOO against two nested models:

    (a) universal-only:  beta_b_offset fixed at 0 (complete pooling)
    (b) biome-specific:  no tau (no pooling); each biome independent
    (c) hierarchical:    partial pooling (the model above)

Outputs:
    scripts/T5_bayesian_posterior.csv    # beta_global + per-biome beta
    scripts/T5_bayesian_loo.json         # ELPD + dELPD with SE
    figures/T5_bayesian_posterior.png    # posterior beta + per-biome forest

Run time: ~3-8 min with 2 chains x 1500 draws on 12k rows, 15 biomes.
If sampling fails / runtime blows up, the script falls back to statsmodels
MixedLM and flags in the JSON output.
"""
from __future__ import annotations
import json
import time
import warnings
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

MOMENTS = SCRIPTS / "T5_empo3_real_moments.csv"

plt.rcParams.update({
    "font.family": "Arial",
    "pdf.fonttype": 42,
    "svg.fonttype": "none",
})
NPG = {"blue": "#3C5488", "red": "#E64B35", "green": "#00A087",
       "orange": "#F39B7F", "grey": "#7E6148", "purple": "#8491B4"}

N_DRAWS = 1500
N_TUNE = 1500
N_CHAINS = 2
SEED = 20260417


def load_data():
    m = pd.read_csv(MOMENTS)
    m = m[(m["mean"] > 0) & (m["var"] > 0)].copy()
    m["biome_ix"] = pd.Categorical(m["biome"]).codes
    biomes = pd.Categorical(m["biome"]).categories.tolist()
    return m, biomes


def fit_hierarchical(m, biomes, backend="pymc"):
    import pymc as pm
    B = len(biomes)
    biome_ix = m["biome_ix"].values
    # center log_mean to reduce posterior correlation
    lmu_c = m["log_mean"].values - m["log_mean"].mean()
    lvar = m["log_var"].values
    coords = {"biome": biomes, "obs": np.arange(len(m))}
    with pm.Model(coords=coords) as model:
        alpha_b = pm.Normal("alpha_b", mu=0, sigma=5, dims="biome")
        beta_global = pm.Normal("beta_global", mu=2.0, sigma=0.5)
        tau = pm.HalfCauchy("tau", beta=0.1)
        beta_offset_raw = pm.Normal("beta_offset_raw", mu=0, sigma=1, dims="biome")
        beta_offset = pm.Deterministic(
            "beta_offset", beta_offset_raw * tau, dims="biome")
        beta_b = pm.Deterministic(
            "beta_b", beta_global + beta_offset, dims="biome")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha_b[biome_ix] + beta_b[biome_ix] * lmu_c
        pm.Normal("log_var_obs", mu=mu, sigma=sigma,
                  observed=lvar, dims="obs")
        t0 = time.time()
        idata = pm.sample(
            draws=N_DRAWS, tune=N_TUNE, chains=N_CHAINS,
            target_accept=0.95, random_seed=SEED,
            progressbar=False, idata_kwargs={"log_likelihood": True})
        dt = time.time() - t0
    return model, idata, dt


def fit_universal(m, biomes):
    import pymc as pm
    B = len(biomes)
    biome_ix = m["biome_ix"].values
    lmu_c = m["log_mean"].values - m["log_mean"].mean()
    lvar = m["log_var"].values
    coords = {"biome": biomes, "obs": np.arange(len(m))}
    with pm.Model(coords=coords) as model:
        alpha_b = pm.Normal("alpha_b", mu=0, sigma=5, dims="biome")
        beta_global = pm.Normal("beta_global", mu=2.0, sigma=0.5)
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha_b[biome_ix] + beta_global * lmu_c
        pm.Normal("log_var_obs", mu=mu, sigma=sigma,
                  observed=lvar, dims="obs")
        idata = pm.sample(
            draws=N_DRAWS, tune=N_TUNE, chains=N_CHAINS,
            target_accept=0.95, random_seed=SEED + 1,
            progressbar=False, idata_kwargs={"log_likelihood": True})
    return idata


def fit_biome_specific(m, biomes):
    import pymc as pm
    B = len(biomes)
    biome_ix = m["biome_ix"].values
    lmu_c = m["log_mean"].values - m["log_mean"].mean()
    lvar = m["log_var"].values
    coords = {"biome": biomes, "obs": np.arange(len(m))}
    with pm.Model(coords=coords) as model:
        alpha_b = pm.Normal("alpha_b", mu=0, sigma=5, dims="biome")
        # wide independent priors: no pooling
        beta_b = pm.Normal("beta_b", mu=2.0, sigma=1.0, dims="biome")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha_b[biome_ix] + beta_b[biome_ix] * lmu_c
        pm.Normal("log_var_obs", mu=mu, sigma=sigma,
                  observed=lvar, dims="obs")
        idata = pm.sample(
            draws=N_DRAWS, tune=N_TUNE, chains=N_CHAINS,
            target_accept=0.95, random_seed=SEED + 2,
            progressbar=False, idata_kwargs={"log_likelihood": True})
    return idata


def fallback_statsmodels(m, biomes):
    import statsmodels.formula.api as smf
    # MixedLM with random slope of log_mean by biome
    m2 = m.copy()
    m2["log_mean_c"] = m2["log_mean"] - m2["log_mean"].mean()
    md = smf.mixedlm("log_var ~ log_mean_c", m2, groups=m2["biome"],
                     re_formula="~log_mean_c")
    mdf = md.fit(method="lbfgs")
    return mdf


def main():
    if not MOMENTS.exists():
        raise SystemExit(f"missing {MOMENTS}; run T5_extract_biome_moments.py")
    m, biomes = load_data()
    print(f"data: {len(m):,} rows  across {len(biomes)} biomes")

    backend_used = "pymc"
    loo_json = {}
    hier_fail = False

    try:
        import pymc as pm
        import arviz as az
    except Exception as e:
        hier_fail = True
        warnings.warn(f"PyMC unavailable ({e}); falling back to statsmodels MixedLM")
        backend_used = "statsmodels_fallback"

    if backend_used == "pymc":
        try:
            print("\n[1/3] fitting hierarchical model (PyMC NUTS)...")
            _, idata_h, dt_h = fit_hierarchical(m, biomes)
            print(f"    hierarchical sampled in {dt_h:.1f} s")
            print("\n[2/3] fitting universal-only (complete pooling)...")
            idata_u = fit_universal(m, biomes)
            print("\n[3/3] fitting biome-specific (no pooling)...")
            idata_b = fit_biome_specific(m, biomes)

            print("\ncomputing PSIS-LOO...")
            loo_h = az.loo(idata_h, pointwise=False)
            loo_u = az.loo(idata_u, pointwise=False)
            loo_b = az.loo(idata_b, pointwise=False)
            comp = az.compare(
                {"hierarchical": idata_h,
                 "universal":    idata_u,
                 "biome_specific": idata_b},
                ic="loo", scale="log")
            print(comp)

            loo_json = {
                "scale": "log",
                "loo_hierarchical":   {"elpd": float(loo_h.elpd_loo),
                                       "se":   float(loo_h.se),
                                       "p_loo":float(loo_h.p_loo)},
                "loo_universal":      {"elpd": float(loo_u.elpd_loo),
                                       "se":   float(loo_u.se),
                                       "p_loo":float(loo_u.p_loo)},
                "loo_biome_specific": {"elpd": float(loo_b.elpd_loo),
                                       "se":   float(loo_b.se),
                                       "p_loo":float(loo_b.p_loo)},
                "compare_df": comp.reset_index().rename(
                    columns={"index": "model"}).to_dict(orient="records"),
            }

            # posterior summaries
            bg = idata_h.posterior["beta_global"].values.ravel()
            tau = idata_h.posterior["tau"].values.ravel()
            b_b = idata_h.posterior["beta_b"].values
            b_off = idata_h.posterior["beta_offset"].values
            b_b_flat = b_b.reshape(-1, b_b.shape[-1])
            b_off_flat = b_off.reshape(-1, b_off.shape[-1])

            post_rows = [{
                "parameter": "beta_global",
                "biome": "ALL",
                "mean": float(bg.mean()),
                "sd":   float(bg.std(ddof=1)),
                "hdi_2.5": float(np.quantile(bg, 0.025)),
                "hdi_97.5": float(np.quantile(bg, 0.975)),
            }, {
                "parameter": "tau",
                "biome": "ALL",
                "mean": float(tau.mean()),
                "sd":   float(tau.std(ddof=1)),
                "hdi_2.5": float(np.quantile(tau, 0.025)),
                "hdi_97.5": float(np.quantile(tau, 0.975)),
            }]
            for i, b in enumerate(biomes):
                post_rows.append({
                    "parameter": "beta_b",
                    "biome": b,
                    "mean": float(b_b_flat[:, i].mean()),
                    "sd":   float(b_b_flat[:, i].std(ddof=1)),
                    "hdi_2.5":  float(np.quantile(b_b_flat[:, i], 0.025)),
                    "hdi_97.5": float(np.quantile(b_b_flat[:, i], 0.975)),
                })
                post_rows.append({
                    "parameter": "beta_offset",
                    "biome": b,
                    "mean": float(b_off_flat[:, i].mean()),
                    "sd":   float(b_off_flat[:, i].std(ddof=1)),
                    "hdi_2.5":  float(np.quantile(b_off_flat[:, i], 0.025)),
                    "hdi_97.5": float(np.quantile(b_off_flat[:, i], 0.975)),
                })
            post_df = pd.DataFrame(post_rows)
            post_df.to_csv(SCRIPTS / "T5_bayesian_posterior.csv", index=False)
            print(f"wrote scripts/T5_bayesian_posterior.csv")

        except Exception as e:
            warnings.warn(f"PyMC fit failed ({type(e).__name__}: {e}); "
                          f"falling back to statsmodels")
            hier_fail = True
            backend_used = "statsmodels_fallback"

    if backend_used == "statsmodels_fallback":
        mdf = fallback_statsmodels(m, biomes)
        print(mdf.summary())
        loo_json = {"warning": "PyMC unavailable or sampling failed; "
                               "used statsmodels MixedLM random-slope fallback",
                    "fixed_effect_beta": float(mdf.fe_params.get("log_mean_c", np.nan)),
                    "fixed_effect_se":   float(mdf.bse.get("log_mean_c", np.nan)),
                    "tau_estimate":      float(
                        np.sqrt(np.diag(mdf.cov_re)[1]) if mdf.cov_re is not None else np.nan)}
        post_rows = [{"parameter": "beta_global (fallback)",
                      "biome": "ALL",
                      "mean": float(mdf.fe_params.get("log_mean_c", np.nan)),
                      "sd": float(mdf.bse.get("log_mean_c", np.nan)),
                      "hdi_2.5": np.nan,
                      "hdi_97.5": np.nan}]
        pd.DataFrame(post_rows).to_csv(
            SCRIPTS / "T5_bayesian_posterior.csv", index=False)

    loo_json["backend"] = backend_used
    (SCRIPTS / "T5_bayesian_loo.json").write_text(json.dumps(loo_json, indent=2))
    print(f"\nwrote scripts/T5_bayesian_loo.json")

    # ------------------------------------------------------------------
    # Figure: posterior beta_global KDE + per-biome offset forest
    # ------------------------------------------------------------------
    if backend_used == "pymc" and not hier_fail:
        fig, (axA, axB) = plt.subplots(1, 2, figsize=(12, 5.2),
                                       gridspec_kw=dict(width_ratios=[1.0, 1.2]))

        # Panel A: beta_global posterior
        axA.hist(bg, bins=60, density=True, color=NPG["blue"],
                 alpha=0.8, edgecolor="white")
        q_lo = np.quantile(bg, 0.025); q_hi = np.quantile(bg, 0.975)
        q_med = np.median(bg)
        axA.axvline(q_med, color=NPG["red"], lw=2,
                    label=f"posterior median = {q_med:.3f}")
        axA.axvspan(q_lo, q_hi, color=NPG["red"], alpha=0.12,
                    label=f"95% HDI = [{q_lo:.3f}, {q_hi:.3f}]")
        axA.axvline(2.0, color="black", lw=1.2, ls="--",
                    label=r"Taylor $\beta = 2$")
        axA.set_xlabel(r"$\beta_{\mathrm{global}}$")
        axA.set_ylabel("posterior density")
        axA.set_title(r"Partial-pooled posterior of Taylor $\beta_{\mathrm{global}}$",
                      fontsize=11)
        axA.legend(fontsize=8.0, loc="upper right", frameon=True,
                   framealpha=0.92, edgecolor="#cccccc")
        axA.grid(alpha=0.3)

        # Panel B: per-biome beta forest (mean + 95% HDI, sorted by mean)
        means = np.array([np.mean(b_b_flat[:, i]) for i in range(len(biomes))])
        los = np.array([np.quantile(b_b_flat[:, i], 0.025) for i in range(len(biomes))])
        his = np.array([np.quantile(b_b_flat[:, i], 0.975) for i in range(len(biomes))])
        order = np.argsort(means)
        ypos = np.arange(len(biomes))
        axB.errorbar(means[order], ypos,
                     xerr=[means[order] - los[order], his[order] - means[order]],
                     fmt="o", color=NPG["blue"], ecolor=NPG["grey"],
                     capsize=3, markersize=5)
        axB.axvline(float(bg.mean()), color=NPG["red"], lw=1.5, ls="-",
                    label=fr"$\beta_{{\mathrm{{global}}}}$ = {bg.mean():.3f}")
        axB.axvline(2.0, color="black", lw=1.0, ls="--",
                    label=r"$\beta = 2$")
        axB.set_yticks(ypos)
        axB.set_yticklabels([biomes[i] for i in order], fontsize=8.5)
        axB.set_xlabel(r"biome-specific $\beta_b$ (posterior mean, 95% HDI)")
        axB.set_title(r"Per-biome $\beta_b$ (partial pool)  |  "
                      fr"$\tau$ = {tau.mean():.3f}",
                      fontsize=11)
        axB.legend(loc="lower right", fontsize=9)
        axB.grid(alpha=0.3)
        xmin, xmax = axB.get_xlim()
        axB.set_xlim(xmin - 0.03, xmax + 0.03)

        fig.suptitle(
            "T5 Bayesian hierarchical partial-pooling: Taylor's law across EMP biomes",
            fontsize=12)
        fig.tight_layout()
        fig.savefig(FIGDIR / "T5_bayesian_posterior.png", dpi=200,
                    bbox_inches="tight")
        plt.close(fig)
        print(f"wrote figures/T5_bayesian_posterior.png")


if __name__ == "__main__":
    main()

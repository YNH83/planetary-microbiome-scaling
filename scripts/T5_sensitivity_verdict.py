"""Consolidate the four T5 sensitivity sweeps into a single verdict JSON.

Reads:
    scripts/T5_sens_prevalence.csv
    scripts/T5_sens_rarefaction.csv
    scripts/T5_sens_taxonomy.csv
    scripts/T5_sens_samplesize.csv (long form, one row per bootstrap rep)

Writes:
    scripts/T5_sensitivity_verdict.json
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"
CANONICAL_BETA = 1.966
TOL_LO, TOL_HI = 1.85, 2.05


def tolerance_check(vals):
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return dict(in_band=False, min=None, max=None, n=0)
    mn, mx = float(vals.min()), float(vals.max())
    return dict(in_band=bool((mn >= TOL_LO) and (mx <= TOL_HI)),
                min=mn, max=mx, n=int(len(vals)))


def pct_drift(vals):
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return None
    dev = np.max(np.abs(vals - CANONICAL_BETA) / CANONICAL_BETA) * 100
    return float(dev)


def main():
    out = dict(
        canonical_beta=CANONICAL_BETA,
        tolerance_band=[TOL_LO, TOL_HI],
    )

    # 1. Prevalence
    prev = pd.read_csv(SCRIPTS / "T5_sens_prevalence.csv")
    out["prevalence"] = dict(
        thresholds=prev["prevalence"].tolist(),
        universal_beta=prev["universal_beta"].tolist(),
        ci_lo=prev["beta_ci_lo"].tolist(),
        ci_hi=prev["beta_ci_hi"].tolist(),
        r2=prev["r2"].tolist(),
        n_biomes=prev["n_biomes"].tolist(),
        tolerance=tolerance_check(prev["universal_beta"]),
        max_pct_drift=pct_drift(prev["universal_beta"]),
    )

    # 2. Rarefaction
    rar = pd.read_csv(SCRIPTS / "T5_sens_rarefaction.csv")
    out["rarefaction"] = dict(
        depths=rar["depth"].tolist(),
        universal_beta=rar["universal_beta"].tolist(),
        ci_lo=rar["beta_ci_lo"].tolist(),
        ci_hi=rar["beta_ci_hi"].tolist(),
        r2=rar["r2"].tolist(),
        n_samples_kept=rar["n_samples_kept"].tolist(),
        tolerance=tolerance_check(rar["universal_beta"]),
        max_pct_drift=pct_drift(rar["universal_beta"]),
    )

    # 3. Taxonomy
    tax = pd.read_csv(SCRIPTS / "T5_sens_taxonomy.csv")
    out["taxonomy"] = dict(
        levels=tax["level"].tolist(),
        universal_beta=tax["universal_beta"].tolist(),
        ci_lo=tax["beta_ci_lo"].tolist(),
        ci_hi=tax["beta_ci_hi"].tolist(),
        r2=tax["r2"].tolist(),
        n_biomes=tax["n_biomes"].tolist(),
        tolerance=tolerance_check(tax["universal_beta"]),
        max_pct_drift=pct_drift(tax["universal_beta"]),
    )

    # 4. Sample size (long form)
    ss = pd.read_csv(SCRIPTS / "T5_sens_samplesize.csv")
    agg_rows = []
    means = []
    for n, grp in ss.groupby("n"):
        v = grp["universal_beta"].dropna()
        if not len(v):
            continue
        agg_rows.append(dict(
            n=int(n),
            mean=float(v.mean()),
            sd=float(v.std(ddof=1)) if len(v) > 1 else None,
            lo=float(v.quantile(0.025)),
            hi=float(v.quantile(0.975)),
            n_valid=int(len(v)),
        ))
        means.append(float(v.mean()))
    out["samplesize"] = dict(
        per_n=agg_rows,
        tolerance=tolerance_check(means),
        max_pct_drift=pct_drift(means),
    )

    # Overall verdict
    all_means = (prev["universal_beta"].tolist()
                 + rar["universal_beta"].tolist()
                 + tax["universal_beta"].tolist()
                 + means)
    overall = tolerance_check(all_means)
    out["overall"] = dict(
        all_sweeps_in_band=overall["in_band"],
        global_min_beta=overall["min"],
        global_max_beta=overall["max"],
        max_pct_drift_any_sweep=pct_drift(all_means),
        per_sweep_in_band={
            "prevalence": out["prevalence"]["tolerance"]["in_band"],
            "rarefaction": out["rarefaction"]["tolerance"]["in_band"],
            "taxonomy": out["taxonomy"]["tolerance"]["in_band"],
            "samplesize": out["samplesize"]["tolerance"]["in_band"],
        },
        interpretation=(
            "PASS: universal beta stays inside [1.85, 2.05] across all four sweeps"
            if overall["in_band"] else
            "PARTIAL: universal beta exits [1.85, 2.05] in at least one sweep"
        ),
    )

    path = SCRIPTS / "T5_sensitivity_verdict.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"[verdict] {path}")
    print(json.dumps(out["overall"], indent=2))


if __name__ == "__main__":
    main()

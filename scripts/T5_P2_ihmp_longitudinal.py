"""
T5 P2: iHMP HMP_2019_ibdmdb longitudinal per-subject Taylor β stability (2026-04-20).

Input: raw data/curatedmg_HMP_2019_ibdmdb_abund.csv + _meta.csv
Rows = MetaPhlAn taxa (species level), columns = samples.
Meta links sample_id -> subject_id -> visit_num.

Test: do per-subject longitudinal abundance series follow Taylor β ≈ 2?
If yes, strengthens "universal β stable under perturbation/recovery" claim
(Discussion 3.5 future direction).

Method:
    For each subject with >= 5 visits, compute per-taxa mean and variance
    across their longitudinal sample series, fit Taylor log-log.
    Report distribution of β across subjects.

Output:
    scripts/T5_P2_ihmp_longitudinal_results.json
    scripts/T5_P2_ihmp_longitudinal_per_subject.csv
    figures/T5_P2_ihmp_longitudinal_beta.png
"""
from __future__ import annotations
import json, time
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
RAW = ROOT / "raw data"
SCRIPTS = ROOT / "scripts"
FIG = ROOT / "figures"

MIN_PREV = 0.20
MIN_VISITS = 5


def per_subject_taylor(sub_abund: pd.DataFrame) -> dict | None:
    """sub_abund: rows=taxa, cols=visits for a single subject."""
    if sub_abund.shape[1] < MIN_VISITS:
        return None
    # Keep only species-level rows (contain s__)
    mask_sp = sub_abund.index.astype(str).str.contains("s__", regex=False)
    a = sub_abund.loc[mask_sp]
    # Prevalence across visits
    prev = (a > 0).mean(axis=1)
    a = a.loc[prev >= MIN_PREV]
    if a.shape[0] < 20:
        return None
    mean = a.mean(axis=1)
    var = a.var(axis=1, ddof=1)
    d = pd.DataFrame({"mean": mean, "var": var}).dropna()
    d = d[(d["mean"] > 0) & (d["var"] > 0)]
    if len(d) < 15:
        return None
    x = np.log10(d["mean"].values); y = np.log10(d["var"].values)
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    r2 = 1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)
    n = len(x); resid = y - yhat
    s2 = np.sum(resid ** 2) / max(n - 2, 1)
    sx2 = np.sum((x - x.mean()) ** 2)
    beta_se = float(np.sqrt(s2 / sx2))
    return {
        "n_visits": int(sub_abund.shape[1]),
        "n_species_after_filter": int(len(d)),
        "beta": float(slope), "beta_se": beta_se,
        "r2": float(r2), "alpha": float(intercept),
    }


def main():
    abund = pd.read_csv(RAW / "curatedmg_HMP_2019_ibdmdb_abund.csv", index_col=0)
    meta = pd.read_csv(RAW / "curatedmg_HMP_2019_ibdmdb_meta.csv", index_col=0)
    print(f"[P2] abund {abund.shape} meta {meta.shape}", flush=True)
    print(f"[P2] meta cols preview: {list(meta.columns[:20])}", flush=True)

    # Find subject_id column
    subj_col = None
    for c in ["subject_id", "subjectID", "host_subject_id", "subject", "Subject", "participant_id"]:
        if c in meta.columns:
            subj_col = c
            break
    if subj_col is None:
        # Try auto-detect: column with many repeats
        counts = {c: meta[c].nunique() for c in meta.columns if meta[c].dtype == object}
        # Best heuristic: not 1 per sample, reasonable number
        candidates = {c: n for c, n in counts.items() if 20 <= n <= 200}
        if candidates:
            subj_col = min(candidates, key=candidates.get)
            print(f"[P2] auto-picked subject col: {subj_col} (n_unique={counts[subj_col]})", flush=True)
    if subj_col is None:
        print("[P2] No subject_id column found. Trying 'subjectID'", flush=True)
        return

    print(f"[P2] using subject column '{subj_col}', {meta[subj_col].nunique()} unique subjects", flush=True)

    # Align abund samples with meta
    shared = meta.index.intersection(abund.columns)
    print(f"[P2] shared samples: {len(shared)}", flush=True)
    meta = meta.loc[shared]
    abund = abund[shared]

    # Per-subject visit count
    subj_visits = meta[subj_col].value_counts()
    elig = subj_visits[subj_visits >= MIN_VISITS]
    print(f"[P2] subjects with >={MIN_VISITS} visits: {len(elig)}", flush=True)

    results = []
    for subj in elig.index:
        samples = meta[meta[subj_col] == subj].index.tolist()
        if len(samples) < MIN_VISITS:
            continue
        sub_abund = abund[samples]
        r = per_subject_taylor(sub_abund)
        if r is None:
            continue
        r["subject"] = str(subj)
        results.append(r)

    df = pd.DataFrame(results)
    df.to_csv(SCRIPTS / "T5_P2_ihmp_longitudinal_per_subject.csv", index=False)
    if df.empty:
        print("[P2] No per-subject fits succeeded.", flush=True)
        return

    print(f"\n[P2] per-subject Taylor fits: n={len(df)}", flush=True)
    print(f"  β distribution: mean={df['beta'].mean():.3f} median={df['beta'].median():.3f} "
          f"SD={df['beta'].std():.3f}  range=[{df['beta'].min():.3f},{df['beta'].max():.3f}]", flush=True)
    print(f"  R² distribution: mean={df['r2'].mean():.3f} median={df['r2'].median():.3f}", flush=True)
    n_in_band = int(df["beta"].between(1.5, 2.5).sum())
    print(f"  β in [1.5, 2.5]: {n_in_band}/{len(df)} ({100*n_in_band/len(df):.1f}%)", flush=True)

    # Plot distribution
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    ax = axes[0]
    ax.hist(df["beta"], bins=30, color="#1f77b4", alpha=0.7, edgecolor="white")
    ax.axvline(df["beta"].median(), color="#d62728", lw=1.5, label=f"median={df['beta'].median():.3f}")
    ax.axvline(2.0, color="#2ca02c", lw=1.0, ls="--", label="Grilli 2.0")
    ax.axvline(1.966, color="#888", lw=0.8, ls=":", label="EMP 1.966")
    ax.set_xlabel("Per-subject Taylor β")
    ax.set_ylabel("Subject count")
    ax.set_title(f"T5 P2: iHMP IBDMDB longitudinal β (n={len(df)} subjects ≥{MIN_VISITS} visits)")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.scatter(df["n_visits"], df["beta"], alpha=0.5, color="#1f77b4", s=30)
    ax.axhline(2.0, color="#2ca02c", lw=0.8, ls="--")
    ax.axhline(1.966, color="#888", lw=0.5, ls=":")
    ax.set_xlabel("Number of visits per subject")
    ax.set_ylabel("Taylor β")
    ax.set_title("Per-subject β vs sample count")

    fig.tight_layout()
    fig.savefig(FIG / "T5_P2_ihmp_longitudinal_beta.png", dpi=180)

    emp_ref = 1.966
    summary = {
        "executed": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "curatedMG HMP_2019_ibdmdb (iHMP IBDMDB)",
        "n_subjects_tested": int(len(df)),
        "min_visits_per_subject": MIN_VISITS,
        "beta_mean": float(df["beta"].mean()),
        "beta_median": float(df["beta"].median()),
        "beta_sd": float(df["beta"].std()),
        "beta_ci_lo_95": float(df["beta"].quantile(0.025)),
        "beta_ci_hi_95": float(df["beta"].quantile(0.975)),
        "r2_median": float(df["r2"].median()),
        "n_subjects_beta_in_1_5_2_5": n_in_band,
        "frac_in_pre_reg_band": float(n_in_band / len(df)),
        "verdict": ("Longitudinal per-subject β distribution centred near 2, "
                    "supporting Grilli's prediction that Taylor exponent is stable "
                    "across perturbation/recovery windows.") if abs(df["beta"].median() - 2) < 0.3
                   else ("Longitudinal β differs from 2, indicating subject-specific deviations."),
    }
    (SCRIPTS / "T5_P2_ihmp_longitudinal_results.json").write_text(
        json.dumps(summary, indent=2, default=str))
    print(f"\n[P2] verdict: median β={summary['beta_median']:.3f}", flush=True)


if __name__ == "__main__":
    main()

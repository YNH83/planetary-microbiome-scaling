"""
T5 P0: Tara Oceans miTAG 16S Taylor's law holdout (2026-04-20).

Input: raw data/tara_oceans/miTAG.taxonomic.profiles.release.tsv.gz
Rows = OTUs (Domain/Phylum/Class/Order/Family/Genus/OTU.rep + sample columns).
Columns = Tara sample names like TARA_018_DCM_0.22-1.6.

Compute Taylor beta per ocean layer (SRF surface, DCM deep chlorophyll max, MES mesopelagic),
and globally.

Output:
    scripts/T5_P0_tara_taxonomic_results.json
    scripts/T5_P0_tara_taxonomic_taylor.csv
    figures/T5_P0_tara_taxonomic_taylor.png
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
TARA = ROOT / "raw data" / "tara_oceans"
SCRIPTS = ROOT / "scripts"
FIG = ROOT / "figures"

MIN_PREV = 0.20  # prevalence filter matched to T5 main pipeline


def taylor_fit(df_counts: pd.DataFrame, label: str) -> dict:
    """df_counts: rows=taxa, cols=samples. Apply prevalence filter + OLS Taylor."""
    if df_counts.shape[1] < 10:
        return {"label": label, "n_samples": df_counts.shape[1], "skip": True}
    # Relative abundance per sample
    sums = df_counts.sum(axis=0)
    sums = sums.replace(0, np.nan)
    relab = df_counts.div(sums, axis=1)
    # Prevalence filter
    prev = (relab > 0).mean(axis=1)
    keep = prev >= MIN_PREV
    relab = relab.loc[keep]
    if relab.shape[0] < 30:
        return {"label": label, "n_samples": df_counts.shape[1], "skip": True,
                "n_otus_after_filter": int(relab.shape[0])}
    mean = relab.mean(axis=1).replace(0, np.nan)
    var = relab.var(axis=1, ddof=1).replace(0, np.nan)
    d = pd.DataFrame({"mean": mean, "var": var}).dropna()
    d = d[(d["mean"] > 0) & (d["var"] > 0)]
    if len(d) < 20:
        return {"label": label, "n_samples": df_counts.shape[1], "skip": True}
    x = np.log10(d["mean"].values); y = np.log10(d["var"].values)
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    ss_res = np.sum((y - yhat) ** 2); ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    # SE of slope via OLS standard
    n = len(x); resid = y - yhat
    s2 = np.sum(resid ** 2) / max(n - 2, 1)
    sx2 = np.sum((x - x.mean()) ** 2)
    beta_se = float(np.sqrt(s2 / sx2))
    from scipy.stats import t as student_t
    tval = student_t.ppf(0.975, n - 2)
    return {
        "label": label,
        "n_samples": int(df_counts.shape[1]),
        "n_otus_after_filter": int(len(d)),
        "beta": float(slope),
        "beta_se": beta_se,
        "beta_ci_lo": float(slope - tval * beta_se),
        "beta_ci_hi": float(slope + tval * beta_se),
        "alpha": float(intercept),
        "r2": float(r2),
    }


def main():
    p = TARA / "miTAG.taxonomic.profiles.release.tsv.gz"
    print(f"[P0] loading {p.name} ...", flush=True)
    df = pd.read_csv(p, sep="\t", compression="gzip", low_memory=False)
    print(f"[P0] shape {df.shape}, cols preview: {list(df.columns[:10])}", flush=True)

    tax_cols = [c for c in df.columns if c in ["Domain", "Phylum", "Class", "Order", "Family", "Genus", "OTU.rep"]]
    sample_cols = [c for c in df.columns if c not in tax_cols]
    print(f"[P0] {len(tax_cols)} tax columns, {len(sample_cols)} samples", flush=True)

    # Drop rows where all sample values are "unclassified" or non-numeric
    counts = df[sample_cols].copy()
    counts = counts.apply(pd.to_numeric, errors="coerce")
    counts = counts.dropna(how="all")
    print(f"[P0] {counts.shape[0]} OTUs with any numeric data", flush=True)

    # Infer ocean layer from sample names (SRF/DCM/MES)
    def layer_of(s: str) -> str:
        s = str(s)
        for lyr in ["SRF", "DCM", "MES", "MIX", "FSW", "ZZZ"]:
            if f"_{lyr}_" in s or s.endswith(f"_{lyr}"):
                return lyr
        return "OTHER"
    layers = pd.Series([layer_of(s) for s in counts.columns], index=counts.columns)
    layer_counts = layers.value_counts()
    print(f"[P0] layer counts: {layer_counts.to_dict()}", flush=True)

    results = []
    # Global
    results.append(taylor_fit(counts, "global_all_layers"))
    # Per layer
    for lyr, n in layer_counts.items():
        if n < 10:
            continue
        sub = counts.loc[:, layers == lyr]
        results.append(taylor_fit(sub, f"layer_{lyr}"))

    df_out = pd.DataFrame(results)
    df_out.to_csv(SCRIPTS / "T5_P0_tara_taxonomic_taylor.csv", index=False)

    print(f"\n[P0] Taylor fits:", flush=True)
    for r in results:
        if r.get("skip"):
            print(f"  {r['label']:30s}  SKIP (n={r['n_samples']}, otus={r.get('n_otus_after_filter', '-')})", flush=True)
        else:
            print(f"  {r['label']:30s}  n={r['n_samples']:3d} OTUs={r['n_otus_after_filter']:5d}  "
                  f"beta={r['beta']:.3f}  CI=[{r['beta_ci_lo']:.3f},{r['beta_ci_hi']:.3f}]  R2={r['r2']:.3f}",
                  flush=True)

    # Plot global + layers
    fig, ax = plt.subplots(figsize=(7, 5))
    valid = [r for r in results if not r.get("skip")]
    names = [r["label"] for r in valid]
    betas = [r["beta"] for r in valid]
    lo = [r["beta"] - r["beta_ci_lo"] for r in valid]  # half-width
    hi = [r["beta_ci_hi"] - r["beta"] for r in valid]
    y = np.arange(len(names))
    ax.errorbar(betas, y, xerr=[lo, hi], fmt="o", color="#1f77b4", markersize=8, capsize=4)
    ax.axvline(1.966, color="#d62728", lw=1.5, label="EMP reference β=1.966")
    ax.axvline(2.0, color="#2ca02c", lw=0.8, ls="--", label="Grilli 2020 theoretical")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Taylor's law β", fontsize=10)
    ax.set_title("T5 P0: Tara Oceans miTAG Taylor holdout", fontsize=11)
    ax.legend(fontsize=8)
    ax.set_xlim(1.5, 2.3)
    fig.tight_layout()
    fig.savefig(FIG / "T5_P0_tara_taxonomic_taylor.png", dpi=180)

    # Verdict
    global_r = next((r for r in results if r["label"] == "global_all_layers" and not r.get("skip")), None)
    emp_ref = 1.966
    verdict = {}
    if global_r:
        dev_pct = abs(global_r["beta"] - emp_ref) / emp_ref * 100
        verdict = {
            "global_beta": global_r["beta"],
            "deviation_pct_vs_EMP": round(dev_pct, 2),
            "within_15pct": dev_pct < 15,
            "within_10pct": dev_pct < 10,
            "CI_contains_EMP": global_r["beta_ci_lo"] <= emp_ref <= global_r["beta_ci_hi"],
        }
    summary = {
        "executed": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "Sunagawa 2015 Tara Oceans miTAG",
        "n_samples_total": int(len(sample_cols)),
        "n_otus_raw": int(counts.shape[0]),
        "per_fit": results,
        "verdict": verdict,
    }
    (SCRIPTS / "T5_P0_tara_taxonomic_results.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[P0] verdict: {verdict}", flush=True)


if __name__ == "__main__":
    main()

"""
T5 P1: Tara KEGG KO functional-layer Taylor's law (2026-04-20).

Input: raw data/tara_oceans/TARA243.KO.profile.release.gz
Rows = KEGG Orthology IDs (K-numbers).
Columns = 243 Tara samples.

Test: does Taylor β on the functional (KO) profile match the taxonomic β ≈ 2?
If yes, the macroecological law extends from taxa to function -- a major
theoretical claim (currently untested in literature).

Output:
    scripts/T5_P1_tara_kegg_results.json
    scripts/T5_P1_tara_kegg_taylor.csv
    figures/T5_P1_tara_kegg_taylor.png
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

MIN_PREV = 0.20


def taylor_fit(df_counts: pd.DataFrame, label: str) -> dict:
    if df_counts.shape[1] < 10:
        return {"label": label, "n_samples": df_counts.shape[1], "skip": True}
    sums = df_counts.sum(axis=0).replace(0, np.nan)
    relab = df_counts.div(sums, axis=1)
    prev = (relab > 0).mean(axis=1)
    keep = prev >= MIN_PREV
    relab = relab.loc[keep]
    if relab.shape[0] < 30:
        return {"label": label, "n_samples": df_counts.shape[1], "skip": True,
                "n_features_after_filter": int(relab.shape[0])}
    mean = relab.mean(axis=1).replace(0, np.nan)
    var = relab.var(axis=1, ddof=1).replace(0, np.nan)
    d = pd.DataFrame({"mean": mean, "var": var}).dropna()
    d = d[(d["mean"] > 0) & (d["var"] > 0)]
    if len(d) < 20:
        return {"label": label, "n_samples": df_counts.shape[1], "skip": True}
    x = np.log10(d["mean"].values); y = np.log10(d["var"].values)
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    r2 = 1 - np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2)
    n = len(x); resid = y - yhat
    s2 = np.sum(resid ** 2) / max(n - 2, 1)
    sx2 = np.sum((x - x.mean()) ** 2)
    beta_se = float(np.sqrt(s2 / sx2))
    from scipy.stats import t as student_t
    tval = student_t.ppf(0.975, n - 2)
    return {
        "label": label,
        "n_samples": int(df_counts.shape[1]),
        "n_features_after_filter": int(len(d)),
        "beta": float(slope), "beta_se": beta_se,
        "beta_ci_lo": float(slope - tval * beta_se),
        "beta_ci_hi": float(slope + tval * beta_se),
        "alpha": float(intercept), "r2": float(r2),
    }


def main():
    p = TARA / "TARA243.KO.profile.release.gz"
    print(f"[P1] loading {p.name} ({p.stat().st_size/1e6:.1f} MB) ...", flush=True)
    df = pd.read_csv(p, sep="\t", compression="gzip", low_memory=False)
    print(f"[P1] shape {df.shape}", flush=True)

    # First column is 'ko' (K-number). Others are samples.
    id_col = df.columns[0]
    sample_cols = [c for c in df.columns if c != id_col]
    print(f"[P1] {len(sample_cols)} TARA samples, {df.shape[0]} KO/rows", flush=True)

    df = df.set_index(id_col)
    # Keep only actual KO rows (start with 'K'), drop summary rows like 'sum_not_annotated'
    keep_rows = df.index.astype(str).str.startswith("K")
    df = df.loc[keep_rows]
    print(f"[P1] after dropping summary rows: {df.shape[0]} KO", flush=True)

    df = df.apply(pd.to_numeric, errors="coerce").fillna(0)

    # Layer labels from sample names
    def layer_of(s: str) -> str:
        s = str(s)
        for lyr in ["SRF", "DCM", "MES", "MIX", "FSW"]:
            if f"_{lyr}_" in s or s.endswith(f"_{lyr}"):
                return lyr
        return "OTHER"
    layers = pd.Series([layer_of(c) for c in sample_cols], index=sample_cols)
    print(f"[P1] layer counts: {layers.value_counts().to_dict()}", flush=True)

    results = []
    results.append(taylor_fit(df, "global_KO_all_layers"))
    for lyr, n in layers.value_counts().items():
        if n < 10:
            continue
        sub = df.loc[:, layers == lyr]
        results.append(taylor_fit(sub, f"KO_layer_{lyr}"))

    pd.DataFrame(results).to_csv(SCRIPTS / "T5_P1_tara_kegg_taylor.csv", index=False)

    print(f"\n[P1] Functional Taylor fits:", flush=True)
    for r in results:
        if r.get("skip"):
            print(f"  {r['label']:30s}  SKIP", flush=True)
        else:
            print(f"  {r['label']:30s}  n={r['n_samples']:3d} KO={r['n_features_after_filter']:5d}  "
                  f"beta={r['beta']:.3f}  CI=[{r['beta_ci_lo']:.3f},{r['beta_ci_hi']:.3f}]  R2={r['r2']:.3f}",
                  flush=True)

    # Plot
    fig, ax = plt.subplots(figsize=(7, 4.5))
    valid = [r for r in results if not r.get("skip")]
    names = [r["label"] for r in valid]
    betas = [r["beta"] for r in valid]
    lo = [r["beta"] - r["beta_ci_lo"] for r in valid]
    hi = [r["beta_ci_hi"] - r["beta"] for r in valid]
    y = np.arange(len(names))
    ax.errorbar(betas, y, xerr=[lo, hi], fmt="o", color="#2ca02c", markersize=8, capsize=4)
    ax.axvline(1.966, color="#d62728", lw=1.5, label="EMP 16S β=1.966")
    ax.axvline(2.0, color="#888", lw=0.8, ls="--", label="Grilli 2.0")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Taylor's law β (KEGG KO functional profile)", fontsize=10)
    ax.set_title("T5 P1: Tara Oceans KEGG-orthology Taylor (functional layer)", fontsize=11)
    ax.legend(fontsize=8)
    ax.set_xlim(1.2, 2.5)
    fig.tight_layout()
    fig.savefig(FIG / "T5_P1_tara_kegg_taylor.png", dpi=180)

    global_r = next((r for r in results if r["label"] == "global_KO_all_layers" and not r.get("skip")), None)
    summary = {
        "executed": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "Sunagawa 2015 Tara Oceans TARA243 KEGG KO profile",
        "n_samples": len(sample_cols),
        "n_KO_raw": int(df.shape[0]),
        "per_fit": results,
        "interpretation": (
            "If KO β ≈ 2, macroecological law extends from taxa to function, major novelty. "
            "If KO β distinctly < 2 (e.g., 1.2-1.5), function differs fundamentally from taxa."
        ),
    }
    if global_r:
        dev_taxa_pct = abs(global_r["beta"] - 1.966) / 1.966 * 100
        summary["global_KO_beta"] = global_r["beta"]
        summary["deviation_vs_taxonomic_EMP_pct"] = round(dev_taxa_pct, 2)
        summary["within_15pct_of_taxa_beta"] = dev_taxa_pct < 15
    (SCRIPTS / "T5_P1_tara_kegg_results.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\n[P1] global KO β = {summary.get('global_KO_beta', 'N/A')}", flush=True)


if __name__ == "__main__":
    main()

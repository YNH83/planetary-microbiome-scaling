"""
T5 x Akbari bridge (2026-04-20).

Tests whether M1-selected (Holocene-selected) microbiome QTLs are
concentrated on gut-associated taxa as predicted by T5's "host influence
enters via alpha, not beta" framework.

Approach:
1. Map 131 MiBioGen genera to a biome-preference label
   (gut-exclusive vs gut+environmental vs environmental-only) based on
   MiBioGen taxonomy prefix (all MiBioGen is gut, so the partition uses
   the T5 per-biome Taylor output as a reference for biome-diversity
   breadth).
2. Compute for each of 211 MiBioGen taxa:
   (a) M1 per-taxon OR_full (already in M1_per_genus_enrichment_results.csv)
   (b) biome-breadth proxy: number of T5 biomes where genus-equivalent ASVs
       are present (estimated from typical microbiome biogeography)
3. Test: is high M1 OR_full associated with being gut-exclusive (narrow
   biome breadth)?

Since direct per-genus biome presence/absence at T5 ASV resolution is not
trivially available without the BIOM-level merge, we run a simpler
proxy: compare M1 atlas OR between three fermentation-gut-typical orders
(Bifidobacteriales, Lactobacillales, Bacteroidales) and
environmental-candidate groups as a coarse bridge.

Writes:
    scripts/T5_akbari_bridge_results.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path("/Users/ynh83/Desktop/Epi-Protocols/04152026 Microbiome-Epi Protocols")
SCRIPTS = ROOT / "scripts"


# Coarse biome-breadth proxy based on known microbiome biogeography
# (references: Lloyd-Price 2017 Nat Microbiol, Thompson 2017 Nature)
GUT_TYPICAL_ORDERS = [
    "Bifidobacteriales", "Lactobacillales", "Bacteroidales",
    "Clostridiales", "Coriobacteriales", "Selenomonadales",
    "Verrucomicrobiales",
]
ENV_BROAD_ORDERS = [
    "Burkholderiales", "Rhizobiales", "Sphingomonadales",
    "Pseudomonadales", "Flavobacteriales", "Actinomycetales",
    "Xanthomonadales",
]


def main():
    m1 = pd.read_csv(SCRIPTS / "M1_per_genus_enrichment_results.csv")
    # Parse rank from taxon
    m1["rank"] = m1["taxon"].str.split(".").str[0]
    m1["short"] = m1["taxon"].str.split(".").str[1]
    orders = m1[m1["rank"] == "order"].copy()
    print(f"[T5b] {len(orders)} orders in M1", flush=True)

    gut_hit = orders[orders["short"].isin(GUT_TYPICAL_ORDERS)]
    env_hit = orders[orders["short"].isin(ENV_BROAD_ORDERS)]
    print(f"[T5b] gut-typical orders matched: {len(gut_hit)} / {len(GUT_TYPICAL_ORDERS)}", flush=True)
    print(f"[T5b] env-broad orders matched: {len(env_hit)} / {len(ENV_BROAD_ORDERS)}", flush=True)

    # Show the matches
    print(f"\n[T5b] gut-typical OR distribution:", flush=True)
    for _, r in gut_hit.iterrows():
        print(f"  {r['short']:25s}  OR_full={r['OR_full']:8.2f}  OR_no_LCT={r['OR_no_lct']:8.2f}  q={r['q_bh']:.2e}",
              flush=True)
    print(f"\n[T5b] env-broad OR distribution:", flush=True)
    for _, r in env_hit.iterrows():
        print(f"  {r['short']:25s}  OR_full={r['OR_full']:8.2f}  OR_no_LCT={r['OR_no_lct']:8.2f}  q={r['q_bh']:.2e}",
              flush=True)

    # Compare: gut-typical vs env-broad OR
    if len(gut_hit) >= 2 and len(env_hit) >= 2:
        u, p = stats.mannwhitneyu(gut_hit["OR_full"], env_hit["OR_full"], alternative="greater")
        u_nolct, p_nolct = stats.mannwhitneyu(gut_hit["OR_no_lct"], env_hit["OR_no_lct"],
                                               alternative="greater")
        print(f"\n[T5b] Mann-Whitney OR_full gut>env: U={u:.1f}, p={p:.4f}", flush=True)
        print(f"[T5b] Mann-Whitney OR_no_LCT gut>env: U={u_nolct:.1f}, p={p_nolct:.4f}", flush=True)
    else:
        u = p = u_nolct = p_nolct = None

    # Count proportion of robust hits (q<0.05) in each group
    gut_sig = int((gut_hit["q_bh"] < 0.05).sum())
    env_sig = int((env_hit["q_bh"] < 0.05).sum())
    print(f"\n[T5b] gut-typical q<0.05: {gut_sig}/{len(gut_hit)}", flush=True)
    print(f"[T5b] env-broad q<0.05: {env_sig}/{len(env_hit)}", flush=True)

    # Load T5 Taylor results
    try:
        t5 = pd.read_csv(SCRIPTS / "T5_empo3_real_taylor.csv")
        print(f"\n[T5b] T5 per-biome Taylor: {len(t5)} biomes; universal beta mean {t5['beta'].mean():.3f}",
              flush=True)
        t5_summary = {
            "n_biomes": len(t5),
            "universal_beta": float(t5["beta"].mean()),
            "beta_min": float(t5["beta"].min()),
            "beta_max": float(t5["beta"].max()),
            "host_associated_biomes": t5[t5["biome"].str.contains("Animal|Plant|Human", case=False, na=False)][
                "biome"].tolist(),
        }
    except Exception as e:
        t5_summary = {"error": str(e)}

    out = {
        "executed": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pre_reg_bridge_claim": "M1 atlas signal concentrates in gut-typical fermentation orders; "
                                  "environment-broad orders do not show enrichment. "
                                  "Consistent with T5 'host influence enters via alpha'.",
        "gut_typical_orders": {
            "n_tested": int(len(gut_hit)),
            "n_q05": gut_sig,
            "median_OR_full": float(gut_hit["OR_full"].median()) if len(gut_hit) else None,
            "median_OR_no_lct": float(gut_hit["OR_no_lct"].median()) if len(gut_hit) else None,
            "hits": gut_hit[["short", "n_instruments", "OR_full", "OR_no_lct", "q_bh"]].to_dict(orient="records"),
        },
        "env_broad_orders": {
            "n_tested": int(len(env_hit)),
            "n_q05": env_sig,
            "median_OR_full": float(env_hit["OR_full"].median()) if len(env_hit) else None,
            "median_OR_no_lct": float(env_hit["OR_no_lct"].median()) if len(env_hit) else None,
            "hits": env_hit[["short", "n_instruments", "OR_full", "OR_no_lct", "q_bh"]].to_dict(orient="records"),
        },
        "gut_vs_env_mw": {"OR_full_p_gt": p, "OR_nolct_p_gt": p_nolct},
        "t5_context": t5_summary,
    }
    (SCRIPTS / "T5_akbari_bridge_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\n[T5b] done -> {SCRIPTS}/T5_akbari_bridge_results.json", flush=True)


if __name__ == "__main__":
    main()

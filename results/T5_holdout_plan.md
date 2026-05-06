# T5 Hold-out and Replication Plan

**Date:** 2026-04-17
**Status:** 1 robustness check completed, 2 external hold-outs blocked, 1 available offline.

## Completed: EMP 150 bp read-length robustness check

Pipeline `scripts/T5_empo3_real.py` applied to independently reprocessed
EMP deblur table at 150 bp (file `raw data/emp/emp_deblur_150bp.subset_2k.rare_5000.biom`,
39 MB, 975 samples, 91,364 taxa, 9 scorable EMPO-3 biomes after rarefaction
cutoff). Result:

| Metric | 90 bp canonical | 150 bp robustness |
|---|---|---|
| Biomes passing (R^2 >= 0.8, beta in [1.5, 2.5]) | 15 / 15 | 9 / 9 |
| Universal Taylor beta | 1.966 | 1.947 |
| beta offset from Grilli 2.0 | 1.7 % | 2.6 % |
| Gamma AFD > exponential fraction | 0.95 | 0.95 |
| Universal vs biome-specific \|Delta BIC\| | 25.7 (decisive) | 5.0 (inconclusive, smaller n) |
| n_points for BIC | 12,610 | 3,170 |

**Interpretation.** Read length and deblur re-processing do not change the
universal Taylor exponent (beta_150bp - beta_90bp = 0.019, well within the
0.15 sampling spread across biomes). Gamma AFD dominance is identical.
Universal-vs-biome-specific BIC flips to inconclusive only because the
subsample has 4x fewer OTU-biome data points, consistent with the sample
size expectation (|Delta BIC| scales with n at fixed effect size).

Outputs: `scripts/T5_empo3_150bp_{taylor,bic,afd}.{csv,json}`,
`figures/T5_empo3_150bp_taylor.png`.

## Attempted: external independent hold-outs

All three probed on 2026-04-17.

| Source | URL | HTTP status | Verdict |
|---|---|---|---|
| Tara Oceans miTAG profiles (Sunagawa 2015, EBI BioStudies) | `www.ebi.ac.uk/biostudies/files/S-BSST297/...miTAG.taxonomic.profiles.release.tar.gz` | 200 with content-length: 0 | needs alternative mirror |
| Tara Oceans PANGAEA direct | `store.pangaea.de/Publications/Sunagawa_et_al_2015/...` | 404 | URL changed post-publication |
| MetaSUB CSD17 metadata | `github.com/MetaSUB/MetaSUB-metadata` | 302 chain, Git LFS required for OTU | LFS credentials needed |
| HMP 16S v35 (hmpdacc.org) | `hmpdacc.org/HMQCP/all/otu_table_psn_v35.biom.gz` | 404 | HMP DACC retired the static path |

## Next-step hold-out path (user terminal)

1. **Tara Oceans v9 rRNA** via ENA project PRJEB4352 sample table, download
   OTU from EBI MGnify study `MGYS00002008`. Expected ~120 MB.
3. **HMP1 v13 OTU** via HMP2 DCC successor `portal.hmpdacc.org` (new
   search API).

Each takes <1 hour to fetch-and-run once authenticated. Pipeline accepts
either BIOM or TSV via `python3 scripts/T5_empo3_real.py <path>`.

## Scientific framing

The 150 bp read-length robustness check is reported as Methods-level
robustness, not as independent hold-out. The external hold-outs (Tara,
the universal Taylor law generalises beyond the EMP consortium. Target
for v0.2 draft: add one external hold-out before submission.

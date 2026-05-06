# T5 Macroecology

**One macroecological scaling regime governs planetary microbiomes with
habitat-specific carrying capacities.**

This repository contains the analysis pipeline, manuscript build
scripts, and processed analytic outputs for the T5 Macroecology study,
which tests whether host-associated and free-living microbiomes share a
common Taylor-scaling regime across all 15 EMPO-3 biomes of the Earth
Microbiome Project.

## Citation

Huang Y-N, Su P-H, Huang C-C. One macroecological scaling regime governs
planetary microbiomes with habitat-specific carrying capacities. (2026)
Submitted to *Nature Ecology and Evolution*.

Pre-registration: Open Science Framework, T5 Macroecology v0.2; locked
2026-05-07.

## Repository layout

```
T5_Macroecology/
├── README.md
├── LICENSE
├── requirements.txt
├── .gitignore
├── scripts/
│   ├── T5_empo3_real.py             primary per-biome OLS Taylor fit
│   ├── T5_bayesian_hierarchical.py  Bayesian partial-pooling (PyMC NUTS)
│   ├── T5_alt_nulls.py              Hubbell / Fisher / Preston / Shoemaker null generators
│   ├── T5_hubbell_null.py           dedicated Hubbell neutral simulation
│   ├── T5_curatedmg_taylor_v2.py    shotgun replication on curatedMG cohorts
│   ├── T5_longitudinal_taylor.py    iHMP IBDMDB longitudinal Taylor
│   ├── T5_disease_detection.py      HMP IBDMDB disease-state K shift
│   ├── T5_loo_biome.py              leave-one-biome-out sensitivity
│   ├── T5_sens_*.py                 prevalence / rarefaction / sample size / taxonomy sweeps
│   ├── T5_k_distribution.py         per-biome K-distribution tests
│   ├── T5_P0_tara_taxonomic.py      Tara Oceans taxonomic holdout
│   ├── T5_P1_tara_kegg.py           Tara Oceans functional KEGG holdout
│   ├── T5_P2_ihmp_longitudinal.py   iHMP IBDMDB extension
│   ├── T5_fig5_leverage.py          Fig 5 (K leverage) build
│   ├── T5_graphical_abstract.py     Fig GA build
│   └── manuscript_builders/         build_NEE_*.py and modify_* utilities
├── results/                         processed analytic outputs (CSV + JSON)
└── (figures/, raw_data/, manuscript .docx are intentionally not committed)
```

## Datasets (download separately)

All input datasets are publicly available; the repository deliberately
does not include raw inputs. Download as follows:

| Dataset | Source |
|---|---|
| Earth Microbiome Project release 1 (deblur table) | https://earthmicrobiome.org |
| curatedMetagenomicData (9 cohorts, 4,702 stool samples) | Bioconductor / ExperimentHub |
| iHMP IBDMDB | https://ibdmdb.org |
| Tara Oceans P0 / P1 | https://tara-oceans.mio.osupytheas.fr / Ocean Gene Atlas |

Each analysis script declares its expected input path at the top
(`ROOT = ...`); adjust to your local layout before running.

## Quick start

```bash
git clone https://github.com/YNH83/T5-Macroecology
cd T5-Macroecology
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Re-run the primary per-biome Taylor fit
python scripts/T5_empo3_real.py

# Re-run Bayesian hierarchical fit (NUTS sampler; ~5 minutes)
python scripts/T5_bayesian_hierarchical.py

# Re-run null falsification (4 generators, 90 replicates each)
python scripts/T5_alt_nulls.py
python scripts/T5_hubbell_null.py
```

## Pre-registered hypothesis decisions (H1-H7)

All seven primary hypotheses are pre-registered on OSF and pass without
amendment; thresholds are listed in the manuscript Methods. The
companion `results/` folder contains the verdict JSONs used in the
manuscript.

## License

MIT (see LICENSE).

## Contact

- Yu-Nan Huang (lead author)
- Pen-Hua Su (corresponding) ,  ninaphsu@gmail.com
- Chieh-Chen Huang (corresponding) ,  cchuang@dragon.nchu.edu.tw

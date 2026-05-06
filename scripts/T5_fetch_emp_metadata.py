"""
T5: fetch EMP (Earth Microbiome Project) metadata from public GitHub.

The full BIOM abundance tables live on ftp.microbio.me which is not in the
sandbox network allowlist; run this script in an unrestricted terminal
(or adjust sandbox) to materialise the real dataset.

This script only targets small text files from github.com/biocore/emp so
it works inside the sandbox for metadata-only prototyping.

After running, the per-sample metadata is cached under
../raw data/emp/emp_qiime_mapping_release1.tsv  (if available on raw).
"""

from pathlib import Path
import urllib.request
import sys

_HERE = Path(__file__).resolve().parent
PROJECT = _HERE.parent
RAW = PROJECT / "raw data" / "emp"
RAW.mkdir(parents=True, exist_ok=True)

# biocore/emp GitHub repo (metadata + scripts only; BIOM tables on FTP)
# Raw-readable paths to try:
CANDIDATES = [
    ("https://raw.githubusercontent.com/biocore/emp/master/data/mapping-files/emp_qiime_mapping_release1.tsv",
     "emp_qiime_mapping_release1.tsv"),
    ("https://raw.githubusercontent.com/biocore/emp/master/data/metadata-refine/emp_qiime_mapping_release1.tsv",
     "emp_qiime_mapping_release1_refined.tsv"),
    ("https://raw.githubusercontent.com/biocore/emp/master/data/empo/empo.tsv",
     "empo.tsv"),
    # Thompson 2017 Nature supplementary study list
    ("https://raw.githubusercontent.com/biocore/emp/master/data/emp-studies.tsv",
     "emp_studies.tsv"),
]


def try_fetch(url, out_name):
    target = RAW / out_name
    if target.exists() and target.stat().st_size > 0:
        print(f"[skip] exists: {target}")
        return True
    try:
        print(f"[get ] {url}")
        urllib.request.urlretrieve(url, target)
        size = target.stat().st_size
        print(f"       -> {target}  ({size} bytes)")
        return True
    except Exception as e:
        print(f"       FAILED: {e}")
        if target.exists():
            target.unlink()
        return False


def main():
    print(f"EMP metadata target dir: {RAW}")
    results = [try_fetch(url, name) for url, name in CANDIDATES]
    ok = sum(results)
    print(f"\nFetched {ok}/{len(CANDIDATES)} metadata files.")
    if ok == 0:
        print("\nNothing fetched. Likely causes: (1) sandbox blocked GitHub raw, ")
        print("(2) EMP repo re-organised paths. Fallback: git clone the repo")
        print("    git clone https://github.com/biocore/emp.git ~/Desktop/emp_repo")
        sys.exit(1)

    # Minimal inspection
    mapping = RAW / "emp_qiime_mapping_release1.tsv"
    if mapping.exists():
        import csv
        with mapping.open() as f:
            reader = csv.reader(f, delimiter="\t")
            header = next(reader, [])
            rows = list(reader)
        print(f"\nMapping file: {len(rows)} samples, {len(header)} columns.")
        # print first few EMPO categories
        empo_idx = next((i for i, h in enumerate(header) if h.lower().startswith("empo")), None)
        if empo_idx is not None:
            from collections import Counter
            counts = Counter(r[empo_idx] for r in rows if len(r) > empo_idx)
            print("\nEMPO category counts:")
            for k, v in counts.most_common(20):
                print(f"  {v:>6}  {k}")

    # Next steps printed
    print("\nNext steps (unsandboxed shell):")
    print("  1. Download BIOM tables via:")
    print("     curl -O ftp://ftp.microbio.me/emp/release1/otu_tables/closed_ref_silva/emp_cr_silva_16S_90.subset_2k.rare_5000.biom")
    print("  2. Convert BIOM to TSV:")
    print("     biom convert -i <biom> -o <tsv> --to-tsv")
    print("  3. Feed into T5_realdata_taylor.py (to be written) which reuses the")
    print("     taylor_fit / gamma_afd_fit / BIC logic from T5_pilot_simulation.py.")


if __name__ == "__main__":
    main()

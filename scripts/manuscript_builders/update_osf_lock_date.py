"""
Replace 'locked 2026-04-20' (and the bare date 2026-04-20 used in OSF
preregistration context) with 'locked 2026-05-07' across:
  - the main Taylor links biomes.docx
  - the 5 standalone NEE docx
  - the matching build scripts
"""
import re
import glob
from docx import Document

OLD = "2026-04-20"
NEW = "2026-05-07"
ROOT = "/Users/ynh83/Desktop/T5_Macroecology"
MAIN = "/Users/ynh83/Desktop/05062026 Taylor links biomes.docx"


def replace_in_paragraph(p, old, new):
    full = "".join(r.text for r in p.runs)
    if old not in full:
        return False
    cursor = 0
    target_done = False
    start = full.index(old)
    end = start + len(old)
    for r in p.runs:
        rlen = len(r.text)
        run_start = cursor
        run_end = cursor + rlen
        cursor = run_end
        if run_end <= start or run_start >= end:
            continue
        local_old_start = max(0, start - run_start)
        local_old_end = min(rlen, end - run_start)
        if not target_done:
            r.text = (r.text[:local_old_start] + new + r.text[local_old_end:])
            target_done = True
        else:
            r.text = r.text[:local_old_start] + r.text[local_old_end:]
    return True


# ---- Update docx ----
files = [MAIN] + sorted(glob.glob(f"{ROOT}/T5_*_NEE_2026-05-06.docx"))
print("=== docx ===")
for f in files:
    doc = Document(f)
    changed = 0
    for p in doc.paragraphs:
        if replace_in_paragraph(p, OLD, NEW):
            changed += 1
    if changed:
        doc.save(f)
    print(f"  {f.split('/')[-1]}: {changed} paragraph(s) changed")

# ---- Update build scripts (so future rebuilds use the right date) ----
scripts = sorted(glob.glob(f"{ROOT}/build_NEE_*.py")
                 + glob.glob(f"{ROOT}/insert_*.py")
                 + glob.glob(f"{ROOT}/modify_*.py"))
print("\n=== scripts ===")
for s in scripts:
    with open(s) as fh:
        src = fh.read()
    new_src = src.replace(OLD, NEW)
    if new_src != src:
        with open(s, "w") as fh:
            fh.write(new_src)
        print(f"  {s.split('/')[-1]}: updated")
    else:
        print(f"  {s.split('/')[-1]}: no change")

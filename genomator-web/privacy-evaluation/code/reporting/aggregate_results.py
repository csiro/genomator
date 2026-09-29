#!/usr/bin/env python3

import glob
import json
import os
import re
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # repo root
SYN = os.path.join(ROOT, "data", "synthetic_data")

TAG_RE = re.compile(r"^N(?P<N>[\d.]+)_Z(?P<Z>[\d.]+)_L(?P<L>[\d.]+)(?P<nb>_nb)?$")


def parse_tag(tag):
    m = TAG_RE.match(tag)
    if not m:
        return None
    return {
        "N": float(m.group("N")),
        "Z": float(m.group("Z")),
        "L": float(m.group("L")),
        "no_biasing": bool(m.group("nb")),
    }


def mean(xs):
    return st.mean(xs) if xs else None


def median(xs):
    return st.median(xs) if xs else None


def sd(xs):
    return st.stdev(xs) if len(xs) > 1 else 0.0


rows = []
cells = sorted(d for d in os.listdir(SYN) if os.path.isdir(os.path.join(SYN, d)))
for cell in cells:
    parsed = parse_tag(cell)
    if parsed is None:
        continue
    cell_dir = os.path.join(SYN, cell)
    dcr_files = sorted(glob.glob(os.path.join(cell_dir, "dcr_*.json")))
    util_files = sorted(glob.glob(os.path.join(cell_dir, "util_*.json")))
    if not dcr_files or not util_files:
        continue  # incomplete cell (e.g. placeholder dir), skip

    dcr_ratio_medians, nndr_medians, flag1, flag5 = [], [], [], []
    for fp in dcr_files:
        with open(fp) as f:
            d = json.load(f)
        s = d["summary"]
        dcr_ratio_medians.append(s["dcr_ratio_median"])
        nndr_medians.append(s["nndr_train_median"])
        flag1.append(s["flagged_fraction_1pct"])
        flag5.append(s["flagged_fraction_5pct"])

    maf_r, ld_r2 = [], []
    for fp in util_files:
        with open(fp) as f:
            u = json.load(f)
        maf_r.append(u["maf_pearson_r"])
        if "ld" in u and u["ld"] is not None:
            ld_r2.append(u["ld"]["ld_r2_pearson_r"])

    row = {
        "cell": cell,
        **parsed,
        "n_replicates": len(dcr_files),
        "dcr_ratio_median_mean": mean(dcr_ratio_medians),
        "dcr_ratio_median_sd": sd(dcr_ratio_medians),
        "nndr_median_mean": mean(nndr_medians),
        "nndr_median_sd": sd(nndr_medians),
        "flagged_1pct_mean": mean(flag1),
        "flagged_5pct_mean": mean(flag5),
        "maf_pearson_r_mean": mean(maf_r),
        "maf_pearson_r_sd": sd(maf_r),
        "ld_r2_pearson_r_mean": mean(ld_r2) if ld_r2 else None,
        "ld_r2_pearson_r_sd": sd(ld_r2) if ld_r2 else None,
    }

    rows.append(row)

rows.sort(key=lambda r: (r["N"], r["Z"], r["L"]))

out_json = os.path.join(ROOT, "data", "results_summary.json")
with open(out_json, "w") as f:
    json.dump(rows, f, indent=2)

out_csv = os.path.join(ROOT, "data", "results_summary.csv")
cols = list(rows[0].keys())
with open(out_csv, "w") as f:
    f.write(",".join(cols) + "\n")
    for r in rows:
        f.write(",".join("" if r[c] is None else str(r[c]) for c in cols) + "\n")

print(f"{len(rows)} cells aggregated -> {out_json}, {out_csv}")

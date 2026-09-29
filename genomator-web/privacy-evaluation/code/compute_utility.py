#!/usr/bin/env python3
import argparse
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "dcr-nndr"))  # holds compute_dcr_scores.py
from compute_dcr_scores import load_vcf_dosage


def maf_vector(G):
    """Per-SNP minor-allele frequency from a dosage matrix (N_samples, N_snps)."""
    p = G.mean(axis=0) / 2.0            # alt-allele frequency
    return np.minimum(p, 1.0 - p)       # fold to minor allele


def _pearson(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    a, b = a[m], b[m]
    if a.size < 3 or a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def ld_r2_sample(G, pairs):
    """r^2 for a fixed array of SNP index pairs (P, 2), from dosage matrix G."""
    Gc = G - G.mean(axis=0, keepdims=True)
    sd = Gc.std(axis=0)
    out = np.full(pairs.shape[0], np.nan)
    for k, (i, j) in enumerate(pairs):
        if sd[i] == 0 or sd[j] == 0:
            continue
        r = np.mean(Gc[:, i] * Gc[:, j]) / (sd[i] * sd[j])
        out[k] = r * r
    return out


def compute(train_vcf, syn_vcf, do_ld=False, ld_pairs=20000, seed=0):
    _, G_tr = load_vcf_dosage(train_vcf)
    _, G_syn = load_vcf_dosage(syn_vcf)
    if G_tr.shape[1] != G_syn.shape[1]:
        raise SystemExit(f"SNP count mismatch: train {G_tr.shape[1]} vs synthetic {G_syn.shape[1]}")
    for name, G in (("train", G_tr), ("synthetic", G_syn)):
        if np.isnan(G).any():
            raise SystemExit(f"{name}: missing genotypes (NaN) -- resolve before scoring")

    maf_tr, maf_syn = maf_vector(G_tr), maf_vector(G_syn)
    dmaf = maf_syn - maf_tr
    res = {
        "n_train": int(G_tr.shape[0]),
        "n_synthetic": int(G_syn.shape[0]),
        "n_snps": int(G_tr.shape[1]),
        "maf_pearson_r": _pearson(maf_tr, maf_syn),
        "maf_mean_abs_diff": float(np.mean(np.abs(dmaf))),
        "maf_rmse": float(np.sqrt(np.mean(dmaf ** 2))),
        "maf_max_abs_diff": float(np.max(np.abs(dmaf))),
        "ld": None,
    }
    if do_ld:
        rng = np.random.default_rng(seed)
        nsnp = G_tr.shape[1]
        npair = min(ld_pairs, nsnp * (nsnp - 1) // 2)
        pairs = np.empty((npair, 2), dtype=int)
        seen = set()
        filled = 0
        while filled < npair:
            i, j = sorted(rng.integers(0, nsnp, size=2))
            if i == j or (i, j) in seen:
                continue
            seen.add((i, j))
            pairs[filled] = (i, j)
            filled += 1
        r2_tr = ld_r2_sample(G_tr, pairs)
        r2_syn = ld_r2_sample(G_syn, pairs)
        res["ld"] = {
            "n_pairs": int(npair),
            "ld_r2_pearson_r": _pearson(r2_tr, r2_syn),
            "ld_r2_mean_abs_diff": float(np.nanmean(np.abs(r2_syn - r2_tr))),
        }
    return res


# ---------------------------------------------------------------------------

def _aggregate(pattern, group_by):
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f"no files match {pattern!r}")
    groups = {}
    for f in files:
        with open(f) as fh:
            d = json.load(fh)
        key = d.get(group_by) or d.get("run_config", {}).get(group_by) or "all"
        groups.setdefault(key, []).append(d)

    cols = ["group", "n", "maf_r_mean", "maf_r_sd", "maf_rmse_mean",
            "maf_mean_abs_diff_mean", "ld_r2_r_mean", "ld_r2_r_sd"]
    print(",".join(cols))
    for key, ds in groups.items():
        mr = np.array([x["maf_pearson_r"] for x in ds], float)
        rmse = np.array([x["maf_rmse"] for x in ds], float)
        mad = np.array([x["maf_mean_abs_diff"] for x in ds], float)
        ldr = np.array([x["ld"]["ld_r2_pearson_r"] for x in ds if x.get("ld")], float)
        row = [key, len(ds),
               f"{np.nanmean(mr):.4f}", f"{np.nanstd(mr, ddof=1) if mr.size > 1 else float('nan'):.4f}",
               f"{np.nanmean(rmse):.4f}", f"{np.nanmean(mad):.4f}",
               f"{np.nanmean(ldr):.4f}" if ldr.size else "",
               f"{np.nanstd(ldr, ddof=1):.4f}" if ldr.size > 1 else ""]
        print(",".join(str(x) for x in row))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train")
    ap.add_argument("--synthetic")
    ap.add_argument("--out")
    ap.add_argument("--ld", action="store_true", help="also compute LD r^2 correlation")
    ap.add_argument("--ld-pairs", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--paramtag", default=None)
    ap.add_argument("--split-seed", dest="split_seed", default=None)
    ap.add_argument("--gen-seed", dest="gen_seed", default=None)
    ap.add_argument("--aggregate", default=None, help="glob of util_*.json to summarise")
    ap.add_argument("--group-by", dest="group_by", default="paramtag")
    args = ap.parse_args()

    if args.aggregate:
        _aggregate(args.aggregate, args.group_by)
        return

    if not (args.train and args.synthetic and args.out):
        sys.exit("need --train, --synthetic, --out  (or --aggregate)")

    res = compute(args.train, args.synthetic, args.ld, args.ld_pairs, args.seed)
    if args.paramtag:
        res["paramtag"] = args.paramtag
    if args.split_seed is not None:
        res["split_seed"] = int(args.split_seed)
    if args.gen_seed is not None:
        res["gen_seed"] = int(args.gen_seed)
    with open(args.out, "w") as f:
        json.dump(res, f, indent=2)
    print(f"MAF r = {res['maf_pearson_r']:.4f}  RMSE = {res['maf_rmse']:.4f}"
          + (f"  LD r2 r = {res['ld']['ld_r2_pearson_r']:.4f}" if res["ld"] else "")
          + f"  -> {args.out}")


if __name__ == "__main__":
    main()

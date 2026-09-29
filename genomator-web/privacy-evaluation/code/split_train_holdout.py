#!/usr/bin/env python3

import argparse
import json

import numpy as np


def split_vcf(input_vcf, train_frac, seed, out_train, out_holdout, out_audit_json):
    with open(input_vcf) as f:
        lines = f.readlines()

    header_lines = [l for l in lines if l.startswith("##")]
    chrom_line = next(l for l in lines if l.startswith("#CHROM"))
    data_lines = [l for l in lines if not l.startswith("#")]

    chrom_fields = chrom_line.rstrip("\n").split("\t")
    fixed_cols, samples = chrom_fields[:9], chrom_fields[9:]
    n = len(samples)

    rng = np.random.RandomState(seed)
    idx = np.arange(n)
    rng.shuffle(idx)
    cut = int(n * train_frac)
    tr_idx, ho_idx = sorted(idx[:cut].tolist()), sorted(idx[cut:].tolist())

    assert len(set(tr_idx) & set(ho_idx)) == 0
    assert sorted(tr_idx + ho_idx) == list(range(n))

    def write_subset(path, keep_idx):
        with open(path, "w") as f:
            f.writelines(header_lines)
            f.write("\t".join(fixed_cols + [samples[i] for i in keep_idx]) + "\n")
            for line in data_lines:
                fields = line.rstrip("\n").split("\t")
                fixed, genos = fields[:9], fields[9:]
                f.write("\t".join(fixed + [genos[i] for i in keep_idx]) + "\n")

    write_subset(out_train, tr_idx)
    write_subset(out_holdout, ho_idx)

    audit = {
        "input_vcf": input_vcf,
        "seed": seed,
        "train_frac": train_frac,
        "n_total": n,
        "n_train": len(tr_idx),
        "n_holdout": len(ho_idx),
        "train_samples": [samples[i] for i in tr_idx],
        "holdout_samples": [samples[i] for i in ho_idx],
    }
    with open(out_audit_json, "w") as f:
        json.dump(audit, f, indent=2)

    print(f"n_total={n} n_train={len(tr_idx)} n_holdout={len(ho_idx)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input_vcf")
    p.add_argument("--train_frac", type=float, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out_train", required=True)
    p.add_argument("--out_holdout", required=True)
    p.add_argument("--out_audit_json", required=True)
    args = p.parse_args()
    split_vcf(args.input_vcf, args.train_frac, args.seed, args.out_train, args.out_holdout, args.out_audit_json)

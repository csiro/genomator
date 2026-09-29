#!/usr/bin/env python3

import gzip
import json
import sys

import numpy as np

PERCENTILE_CUTOFFS = (1, 5)
CHUNK = 100


def _open_text(path):
    if path.endswith(".gz") or path.endswith(".bgz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def load_vcf_dosage(path):
    """(samples, G) with G an (N_samples, N_variants) dosage matrix."""
    samples, cols = [], []
    with _open_text(path) as f:
        for line in f:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                samples = line.rstrip("\n").split("\t")[9:]
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 10:
                continue
            genos = parts[9:]
            dos = []
            for g in genos:
                gt = g.split(":", 1)[0]
                if gt in ("./.", ".|."):
                    dos.append(np.nan)
                else:
                    alleles = gt.replace("|", "/").split("/")
                    try:
                        dos.append(sum(int(a) for a in alleles))
                    except ValueError:
                        dos.append(np.nan)
            cols.append(np.asarray(dos, dtype=float))
    G = np.vstack(cols).T if cols else np.empty((len(samples), 0))
    return samples, G


def pairwise_mismatch(A, B, chunk=CHUNK):
    """(N_A, N_B) categorical mismatch-count matrix (dosage values compared as
    categories, not subtracted numerically)."""
    out = np.empty((A.shape[0], B.shape[0]), dtype=np.float64)
    for i in range(0, A.shape[0], chunk):
        block = A[i:i + chunk]
        out[i:i + chunk] = (block[:, None, :] != B[None, :, :]).sum(axis=2)
    return out


def leave_one_out_nn_distances(G, chunk=CHUNK):
    """Per individual in G, distance to the nearest *other* individual in G (self excluded)."""
    N = G.shape[0]
    mins = np.full(N, np.inf)
    for i in range(0, N, chunk):
        block = G[i:i + chunk]
        d = (block[:, None, :] != G[None, :, :]).sum(axis=2).astype(np.float64)
        for k in range(d.shape[0]):
            d[k, i + k] = np.inf  # exclude self-match
        mins[i:i + chunk] = d.min(axis=1)
    return mins


def closest_two(D):
    """Per row: (d1, idx1, d2) -- distance/index of the closest column and distance of the
    second-closest column."""
    idx1 = np.argmin(D, axis=1)
    d1 = D[np.arange(D.shape[0]), idx1]
    D2 = D.copy()
    D2[np.arange(D.shape[0]), idx1] = np.inf
    d2 = D2.min(axis=1)
    return d1, idx1, d2


def main():
    split_dir = sys.argv[1].rstrip("/")
    synthetic_vcf_name = sys.argv[2] if len(sys.argv) > 2 else "genomator_synthetic_N150_Z1.5_L0.99.vcf"
    results_json_name = sys.argv[3] if len(sys.argv) > 3 else "dcr_results.json"

    tr_samples, G_tr = load_vcf_dosage(f"{split_dir}/train.vcf")
    ho_samples, G_ho = load_vcf_dosage(f"{split_dir}/holdout.vcf")
    syn_samples, G_syn = load_vcf_dosage(f"{split_dir}/{synthetic_vcf_name}")

    for name, G in [("train", G_tr), ("holdout", G_ho), (synthetic_vcf_name, G_syn)]:
        if np.isnan(G).any():
            raise ValueError(f"{name}: missing genotypes (NaN) found -- resolve before scoring")
    if not (G_tr.shape[1] == G_ho.shape[1] == G_syn.shape[1]):
        raise ValueError(
            f"variant count mismatch: train={G_tr.shape[1]} holdout={G_ho.shape[1]} "
            f"synthetic={G_syn.shape[1]} -- these VCFs must share the same panel/column order"
        )

    print(f"G_tr={G_tr.shape} G_ho={G_ho.shape} G_syn={G_syn.shape}")

    print("computing train-train leave-one-out NN distances (reference scale)...")
    train_nn_dist = leave_one_out_nn_distances(G_tr)
    thresholds = {p: float(np.percentile(train_nn_dist, p)) for p in PERCENTILE_CUTOFFS}

    print("computing synthetic-to-train / synthetic-to-holdout distances...")
    D_syn_tr = pairwise_mismatch(G_syn, G_tr)
    D_syn_ho = pairwise_mismatch(G_syn, G_ho)

    dcr_train, idx_train, d2_train = closest_two(D_syn_tr)
    idx_holdout = D_syn_ho.argmin(axis=1)
    dcr_holdout = D_syn_ho[np.arange(D_syn_ho.shape[0]), idx_holdout]

    with np.errstate(divide="ignore", invalid="ignore"):
        dcr_ratio = dcr_train / dcr_holdout
        nndr_train = dcr_train / d2_train

    flagged = {p: (dcr_train < thresholds[p]) for p in PERCENTILE_CUTOFFS}
    n_syn = G_syn.shape[0]

    per_sample = [
        {
            "synthetic_sample": syn_samples[i],
            "dcr_train": float(dcr_train[i]),
            "dcr_holdout": float(dcr_holdout[i]),
            "dcr_ratio": float(dcr_ratio[i]) if np.isfinite(dcr_ratio[i]) else None,
            "nndr_train": float(nndr_train[i]) if np.isfinite(nndr_train[i]) else None,
            "nearest_train_sample": tr_samples[idx_train[i]],
            "nearest_holdout_sample": ho_samples[idx_holdout[i]],
            "flagged_1pct": bool(flagged[1][i]),
            "flagged_5pct": bool(flagged[5][i]),
        }
        for i in range(n_syn)
    ]
    per_sample.sort(key=lambda r: r["dcr_train"])  # most suspicious (closest to train) first

    def _nanstat(fn, arr):
        return float(fn(arr)) if not np.all(np.isnan(arr)) else None

    out = {
        "split_dir": split_dir,
        "synthetic_vcf_name": synthetic_vcf_name,
        "n_train": int(G_tr.shape[0]),
        "n_holdout": int(G_ho.shape[0]),
        "n_synthetic": n_syn,
        "n_variants": int(G_tr.shape[1]),
        "params": {
            "distance": "categorical_mismatch_count (dosage 0/1/2)",
            "percentile_cutoffs": list(PERCENTILE_CUTOFFS),
        },
        "reference_scale": {
            "description": "real train-train leave-one-out 1-NN distance distribution, computed "
                            "fresh from this split_dir's own train.vcf -- never pooled across "
                            "splits, never touching holdout or synthetic",
            "train_train_nn_dist_min": float(train_nn_dist.min()),
            "train_train_nn_dist_median": float(np.median(train_nn_dist)),
            "train_train_nn_dist_max": float(train_nn_dist.max()),
            "percentile_thresholds": thresholds,
        },
        "summary": {
            "flagged_count_1pct": int(flagged[1].sum()),
            "flagged_fraction_1pct": float(flagged[1].mean()),
            "flagged_count_5pct": int(flagged[5].sum()),
            "flagged_fraction_5pct": float(flagged[5].mean()),
            "dcr_train_min": float(dcr_train.min()),
            "dcr_train_median": float(np.median(dcr_train)),
            "dcr_train_max": float(dcr_train.max()),
            "dcr_ratio_min": _nanstat(np.nanmin, dcr_ratio),
            "dcr_ratio_median": _nanstat(np.nanmedian, dcr_ratio),
            "dcr_ratio_max": _nanstat(np.nanmax, dcr_ratio),
            "nndr_train_min": _nanstat(np.nanmin, nndr_train),
            "nndr_train_median": _nanstat(np.nanmedian, nndr_train),
            "nndr_train_max": _nanstat(np.nanmax, nndr_train),
        },
        "per_sample": per_sample,
    }

    with open(f"{split_dir}/{results_json_name}", "w") as f:
        json.dump(out, f, indent=2)

    print(f"reference thresholds: 1pct={thresholds[1]:.1f}  5pct={thresholds[5]:.1f}")
    print(
        f"flagged: {out['summary']['flagged_count_1pct']}/{n_syn} at 1pct "
        f"({out['summary']['flagged_fraction_1pct']:.1%}), "
        f"{out['summary']['flagged_count_5pct']}/{n_syn} at 5pct "
        f"({out['summary']['flagged_fraction_5pct']:.1%})"
    )
    print(
        f"DCR_train: min={out['summary']['dcr_train_min']:.1f} "
        f"median={out['summary']['dcr_train_median']:.1f} "
        f"max={out['summary']['dcr_train_max']:.1f}"
    )
    print(f"Wrote {split_dir}/{results_json_name}")


if __name__ == "__main__":
    main()

# Genomator privacy evaluation

We evaluate [Genomator](https://github.com/aehrc/genomator)'s privacy performance
across a sweep of `(N, Z, L)` parameter settings, using DCR/NNDR (distance-to-closest-record
/ nearest-neighbor distance ratio) as the privacy metric, plus MAF/LD fidelity metrics.

**What's in this folder vs. what you need to add.** Only `code/` and `env/`
(the evaluation scripts and their pinned dependency lists) are checked into
this repo. The `data/` (real source VCF, train/holdout splits, generated
synthetic VCFs) and `library/` (a vendored `genomator` clone) directories the
rest of this README describes are **not** included here — set them up
yourself following "Environment setup" and "Generating reproducible
synthetic genome data" below, using your own real cohort. Note in particular
that `library/genomator` needs the `--seed` patch described below applied to
a clone of [aehrc/genomator](https://github.com/aehrc/genomator); that patch
itself isn't included here either, only the evaluation code that assumes
it's present.

This is a heavier, research-grade evaluation pipeline than the Calculate
tab's previous "In-Depth Privacy Metric" (now archived at
`genomator-web/archived-privacy-metric/`) — two separate conda environments,
an external cloned dependency, and no single one-command "just run it" path.

## Repository structure

```
data/
  805_SNP_1000G_real.vcf        real source cohort: 805 SNPs, 1000 Genomes samples
  splits/
    split_101/ ... split_105/   5 train/holdout splits (seeds 101-105), shared
                                 by every (N, Z, L) cell
  synthetic_data/
    N150_Z1.5_L0.99_nb/         one directory per (N, Z, L) "cell" -- see Data layout below

code/
  split_train_holdout.py        train/holdout VCF split
  compute_utility.py            MAF / LD fidelity: single-replicate compute + --aggregate
  dcr-nndr/
    score_one_dcr.py            single replicate: split -> Genomator generate -> DCR/NNDR score
    compute_dcr_scores.py       DCR/NNDR/flagging metric engine (dependency of score_one_dcr.py)
    run_cell_sweep.py           all 25 replicates of one cell, parallel driver around score_one_dcr.py
  reporting/
    aggregate_results.py        builds data/results_summary.{json,csv} from DCR/NNDR + utility per-cell outputs
    make_plots_dcr_nndr.py      create plots (dcr/nndr)

env/
  requirements-genomator.txt
  requirements-metrics.txt

library/
  genomator/                    cloned copy of genomator (pip-installable, see below)
```

- **genomator** -- [github.com/aehrc/genomator](https://github.com/aehrc/genomator), cloned into
  `library/genomator/`, installed with `pip install library/genomator/genomator`.

The clone has its own nested `.git/` stripped -- it's a plain vendored source snapshot
checked into this repo, not a live checkout.

## Environment setup

```bash
# only needed if library/ is missing or you want to refresh it from upstream -- a fresh clone of
# this repo already has library/genomator/ checked in, so normally skip straight
# to the conda/pip steps below
git clone https://github.com/aehrc/genomator.git library/genomator

conda create -n genomator python=3.12 -y && conda activate genomator
pip install -r env/requirements-genomator.txt
pip install library/genomator/genomator
conda deactivate

conda create -n metrics python=3.12 -y && conda activate metrics
pip install -r env/requirements-metrics.txt
conda deactivate

export PY=$(conda run -n metrics which python)
export GENOMATOR_BIN=$(conda run -n genomator which genomator)
```

## Generating reproducible synthetic genome data

Genomator ([full docs](https://github.com/aehrc/genomator/blob/main/genomator/README.md)) formulates cohort generation as a
SAT problem: it produces synthetic individuals that are constrained to differ from the real
dataset (and from each other) by a minimum Hamming distance, while a phase-biasing step
(`sample_group_size`/`exception_space`/`looseness`) steers the SAT solver to reproduce the input's
SNP-frequency structure.

This repo parametrizes a Genomator run by three swept values plus two seeds, forming one
**paramtag**: `N<N>_Z<Z>_L<L>[_nb]`. Reproducibility comes from two independent RNG seeds:

- **`split_seed`** (101-105 in this repo) -- seeds `split_train_holdout.py`'s `RandomState`, fixing
  which real samples land in train vs. holdout. Every swept cell shares the same 5 splits, so
  results line up by `(paramtag, split_seed, gen_seed)`.
- **`gen_seed`** -- passed to Genomator as `--seed`, fixing the SAT solver's synthetic draw for
  that split's train set. `--tasks=1` is always passed alongside it and is required for this to
  actually be reproducible -- Genomator seeds Python's global `random`/`numpy.random` state once,
  at the top of generation, and every genome in the batch draws from that one shared stream in a
  single process.

  **This `--seed` option does not exist upstream.** Genomator's public source
  ([github.com/aehrc/genomator](https://github.com/aehrc/genomator)) has no seeding in its
  generation path. `library/genomator/` in this repo is patched (`genomator/generate.py` +
  `scripts/genomator`) to add real `--seed` support.

Example to generate (and score) one replicate end-to-end with `(N=150, Z=1.5, L=0.99, no-biasing)`, split_seed=101, gen_seed=201:

```bash
conda activate metrics
python code/dcr-nndr/score_one_dcr.py \
  --N 150 --Z 1.5 --L 0.99 --no-biasing \
  --split-seed 101 --gen-seed 201 \
  --source data/805_SNP_1000G_real.vcf \
  --outdir data/synthetic_data/N150_Z1.5_L0.99_nb \
  --splits-dir data/splits \
  --keep-synth
```

To build a full sweep, loop this call over every `(N, Z, L)` combination you want and all 5
`split_seed` x 5 `gen_seed` pairs (25 replicates per cell in the existing `data/synthetic_data/`).

## Privacy evaluation: DCR / NNDR

Reads the synthetic VCFs (`data/synthetic_data/<cell>/syn/*.vcf`) and the 5 train/holdout splits.

**DCR / NNDR** (`code/dcr-nndr/`, own metric code, no external package) -- for every synthetic
individual, computes Distance to Closest Record (Hamming/mismatch-count distance)
to the nearest **train** sample and to the nearest **holdout** sample, plus the Nearest-Neighbor
Distance Ratio (NNDR, closest / second-closest train distance). `DCR_ratio = dcr_train /
dcr_holdout` near 1 means a synthetic sample sits equally close to train and holdout (no
train-set memorization); values well below 1, or samples falling under the 1st/5th percentile
of the real train-train leave-one-out distance distribution, get **flagged** as
too-close-to-train.

## Utility / fidelity metrics

Computed by `code/compute_utility.py`, synthetic vs. the same split's real train set:

- **MAF fidelity** -- Pearson r between per-SNP minor allele frequency in synthetic vs. train
  (`maf_pearson_r`), plus mean absolute difference, RMSE, and max absolute difference.
- **LD fidelity** (`--ld`) -- Pearson r between pairwise SNP linkage-disequilibrium r² in
  synthetic vs. train, sampled over `--ld-pairs` (default 20000) random SNP pairs.

High fidelity (r close to 1) and low privacy leakage are in tension by construction (a cohort
statistically identical to the real one is, definitionally, easy to link back to it) -- reporting
both sides for the same cell is the point of this repo's layout.

## DCR and NNDR

### Per-replicate compute (one `(paramtag, split_seed, gen_seed)`)

```bash
# DCR / NNDR
python code/dcr-nndr/score_one_dcr.py \
  --N 150 --Z 1.5 --L 0.99 --no-biasing --split-seed 101 --gen-seed 201 \
  --outdir data/synthetic_data/N150_Z1.5_L0.99_nb --splits-dir data/splits --keep-synth

# MAF / LD utility, same replicate
python code/compute_utility.py \
  --train data/splits/split_101/train.vcf \
  --synthetic data/synthetic_data/N150_Z1.5_L0.99_nb/syn/syn_N150_Z1.5_L0.99_nb_split101_gen201.vcf \
  --ld --paramtag N150_Z1.5_L0.99_nb --split-seed 101 --gen-seed 201 \
  --out data/synthetic_data/N150_Z1.5_L0.99_nb/util_N150_Z1.5_L0.99_nb_split101_gen201.json
```

### Calling `compute_dcr_scores.py` directly (e.g. for re-scoring an existing synthetic VCF without regenerating it)

`compute_dcr_scores.py` scores three **already-existing** VCFs that must all sit in one directory:
`train.vcf`, `holdout.vcf`, and a `synthetic VCF`.

```bash
conda activate metrics

job=$(mktemp -d)
ln -s "$PWD/data/splits/split_101/train.vcf" "$job/train.vcf"
ln -s "$PWD/data/splits/split_101/holdout.vcf" "$job/holdout.vcf"
ln -s "$PWD/data/synthetic_data/N150_Z1.5_L0.99_nb/syn/syn_N150_Z1.5_L0.99_nb_split101_gen201.vcf" \
      "$job/synthetic.vcf"

python code/dcr-nndr/compute_dcr_scores.py "$job" synthetic.vcf result.json

cat "$job/result.json"
rm -rf "$job"
```

### Per-cell compute (one `(paramtag)`)

`run_cell_sweep.py` is a thin parallel driver around `score_one_dcr.py` -- it loops the same
per-replicate call above over this repo's standard grid (5 `split_seed`s x 5 `gen_seed`s = 25
replicates), via a `ProcessPoolExecutor`.

```bash
python code/dcr-nndr/run_cell_sweep.py --N 150 --Z 1.5 --L 0.99 --no-biasing --workers 6
# -> data/synthetic_data/N150_Z1.5_L0.99_nb/dcr_*.json            (25 files)
# -> data/synthetic_data/N150_Z1.5_L0.99_nb/syn/*.vcf             (25 files -- always passes --keep-synth)
```

Same `PY`/`GENOMATOR_BIN` resolution as `score_one_dcr.py` (env var, or `--py`/`--genomator-bin`).
`--outdir` defaults to `data/synthetic_data/<paramtag>`, matching the standard layout; `--workers`
defaults to 6. Any replicate whose result JSON already exists is skipped (same idempotency as
`score_one_dcr.py`), so re-running after a partial failure only redoes what's missing.

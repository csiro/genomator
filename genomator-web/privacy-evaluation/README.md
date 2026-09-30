# Genomator privacy evaluation

We evaluate [Genomator](../../genomator)'s privacy performance
across a sweep of `(N, Z, L)` parameter settings, using DCR/NNDR (distance-to-closest-record
/ nearest-neighbor distance ratio) as the privacy metric, plus MAF/LD fidelity metrics.

**What's in this folder vs. what you need to add.** Only `code/` and `env/`
(the evaluation scripts and their pinned dependency lists) are checked into
this repo. The `data/` directory (real source VCF, train/holdout splits,
generated synthetic VCFs) this README describes is **not** included here —
set it up yourself following "Environment setup" and "Generating
reproducible synthetic genome data" below, using your own real cohort.
Genomator itself needs no separate setup: `code/dcr-nndr/score_one_dcr.py`
imports it directly from `genomator/` at the root of this same repo (see
"Generating reproducible synthetic genome data" below) — no external clone,
no patch to apply, no PyPI package to install.

This is a heavier, research-grade evaluation pipeline than the Calculate
tab's previous "In-Depth Privacy Metric" (now archived at
`genomator-web/archived-privacy-metric/`) — two separate conda environments
and no single one-command "just run it" path.

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
    score_one_dcr.py            single replicate: split -> generate (locally, or --synthetic-vcf
                                 from the web Generate tab) -> DCR/NNDR score
    compute_dcr_scores.py       DCR/NNDR/flagging metric engine (dependency of score_one_dcr.py)
    run_cell_sweep.py           all 25 replicates of one cell, parallel driver around score_one_dcr.py
  reporting/
    aggregate_results.py        builds data/results_summary.{json,csv} from DCR/NNDR + utility per-cell outputs
    make_plots_dcr_nndr.py      create plots (dcr/nndr)

env/
  requirements-genomator.txt
  requirements-metrics.txt
```

Genomator itself is not vendored anywhere under this folder -- `score_one_dcr.py` imports
it directly from `genomator/` at the repo root (a sibling of `genomator-web/`), the same
source the rest of this repo (and the Calculate tab's Generate/Accuracy/Privacy metrics)
uses. See "Generating reproducible synthetic genome data" below for how that import works
and why reproducibility doesn't need any change to genomator's own code.

## Environment setup

Two conda environments, split by which scripts actually import what:

- **`genomator`** -- runs `score_one_dcr.py`/`run_cell_sweep.py` themselves. These import
  `genomator` (needing `cyvcf2`, `python-sat`, `vcfpy`, `click`, `tqdm`, `stopit`) directly,
  in-process, to generate synthetic data -- see `env/requirements-genomator.txt`.
- **`metrics`** -- used only for the actual scoring scripts (`compute_dcr_scores.py`,
  `compute_utility.py`; numpy/scipy/scikit-learn) -- see `env/requirements-metrics.txt`.
  `score_one_dcr.py` launches these as a separate subprocess under this environment's own
  interpreter, so it can stay a distinct environment from `genomator` above even though
  `score_one_dcr.py` itself now runs under `genomator`.

```bash
conda create -n genomator python=3.12 -y && conda activate genomator
pip install -r env/requirements-genomator.txt
conda deactivate

conda create -n metrics python=3.12 -y && conda activate metrics
pip install -r env/requirements-metrics.txt
conda deactivate

export GENOMATOR_PY=$(conda run -n genomator which python)
export PY=$(conda run -n metrics which python)
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
- **`gen_seed`** -- fixes the SAT solver's synthetic draw for that split's train set.

  Genomator's own CLI (`genomator/scripts/genomator`) has no `--seed` option, and we didn't
  want to add one there or maintain a patched fork just for this. Instead, `score_one_dcr.py`
  imports `genomator` directly (`from genomator import generate_genomes, ...`, with
  `genomator/` — the repo root's own copy — added to `sys.path`) and calls
  `random.seed(gen_seed)` / `np.random.seed(gen_seed)` itself, once, immediately before that
  one call. `generate_genomes()` reads both as plain global state throughout generation (this
  was confirmed by reading `genomator/genomator/generate.py`, not assumed), so seeding them in
  the caller is enough — nothing about genomator's own code changes. `tasks=1` is passed
  alongside for the same reason it always was: `tasks>1` spreads generation over a
  multiprocessing pool, whose worker processes don't inherit a coordinated sub-seed from this
  one, so anything above 1 would silently break the reproducibility this depends on.

  Verified directly, not just argued for: running the same `(paramtag, split_seed, gen_seed)`
  twice produces byte-identical synthetic VCFs (same SHA-256), and changing just `gen_seed`
  changes the output.

  A few generation parameters this repo has never overridden (`indexation_bits`,
  `difference_samples`, `solver_name`, `no_smart_clustering`, `cluster_information_file`,
  `max_restarts`, `del_info_field`) used to fall through to `scripts/genomator`'s own Click
  option defaults, which for a couple of these differ from `generate_genomes()`'s own
  Python-level defaults (e.g. `indexation_bits` is 8 at the CLI layer vs. 12 as the function's
  own default). Rather than pick a number and duplicate it here, `score_one_dcr.py` reads
  these straight from `scripts/genomator`'s registered Click defaults at run time (see
  `_genomator_cli_defaults()`), so this stays in sync automatically if those defaults ever
  change instead of silently drifting from what the CLI would have used. Every replicate's
  result JSON records the actual values used, under `run_config.genomator`, for exactly this
  reason.

  If you need to point at a different `genomator/` checkout entirely (not the one at this
  repo's root), set `GENOMATOR_SRC` or pass `--genomator-src`.

Example to generate (and score) one replicate end-to-end with `(N=150, Z=1.5, L=0.99, no-biasing)`, split_seed=101, gen_seed=201:

```bash
conda activate genomator
python code/dcr-nndr/score_one_dcr.py \
  --N 150 --Z 1.5 --L 0.99 --no-biasing \
  --split-seed 101 --gen-seed 201 \
  --source data/805_SNP_1000G_real.vcf \
  --outdir data/synthetic_data/N150_Z1.5_L0.99_nb \
  --splits-dir data/splits \
  --py "$PY" \
  --keep-synth
```

To build a full sweep, loop this call over every `(N, Z, L)` combination you want and all 5
`split_seed` x 5 `gen_seed` pairs (25 replicates per cell in the existing `data/synthetic_data/`).

## Using synthetic data from the web Generate tab

Generation above happens locally, driven by this repo's own code. If you'd rather generate
synthetic data the same way the Genomator website's Generate tab does — using it directly,
in your browser, no local Python environment needed for that step — `score_one_dcr.py` can
score a VCF you already made that way instead of generating one itself. The one thing that
has to line up: **the synthetic data must have been generated from this split's `train.vcf`
only, never the full real cohort** — DCR/NNDR's whole premise is comparing distance-to-train
against distance-to-a-holdout-set the generator never saw, and that comparison stops meaning
anything if "holdout" wasn't actually held out from generation.

1. **Produce the split first**, before generating anything — `score_one_dcr.py` would do
   this for you locally, but here it needs to happen up front so you have a `train.vcf` to
   feed the Generate tab. This is the same `split_train_holdout.py` used internally, run
   directly (already a standalone CLI, no changes needed):

   ```bash
   mkdir -p data/splits/split_101
   python code/split_train_holdout.py data/805_SNP_1000G_real.vcf \
     --train_frac 0.5 --seed 101 \
     --out_train data/splits/split_101/train.vcf \
     --out_holdout data/splits/split_101/holdout.vcf \
     --out_audit_json data/splits/split_101/split_audit.json
   ```

   Use the exact `--train_frac`/`--seed` (matching `--split-seed` below) you intend to score
   with — `score_one_dcr.py` will detect this split already exists and reuse it rather than
   building its own.

2. **Upload `data/splits/split_101/train.vcf`** to the Generate tab (never the full cohort
   or the holdout half). Set whatever generation profile you want to evaluate — the Generate
   tab's own field names map onto this repo's `N`/`Z`/`L` as: "Choose a Cluster Group Size
   (ie. N)" → `N`, "How much should rare pairs be attenuated? (ie. Z...)" → `Z`, "How much
   looseness should the process involve?" → `L`, "How many Synthetic Data Points?" → however
   many synthetic samples you want scored. Generate, then download the resulting VCF.

3. **Score it**, pointing `--synthetic-vcf` at the downloaded file. `--N`/`--Z`/`--L`/
   `--no-biasing` here are no longer instructions (nothing gets generated) — they're just a
   label recording what you actually used on the Generate tab, so it's worth setting them to
   match for your own records. `--gen-seed` is similarly just a label in this mode (there's no
   generation seed to speak of, since you already generated it) — use it to tell apart
   multiple web-generated files scored against the same split, e.g. by download order.

   ```bash
   conda activate genomator
   python code/dcr-nndr/score_one_dcr.py \
     --N 20 --Z 0.5 --L 0.6 \
     --split-seed 101 --gen-seed 1 \
     --source data/805_SNP_1000G_real.vcf \
     --splits-dir data/splits \
     --outdir data/synthetic_data/webgen_N20_Z0.5_L0.6 \
     --synthetic-vcf ~/Downloads/your_generate_tab_output.vcf \
     --py "$PY" --keep-synth
   ```

   The result JSON's `run_config.genomator` records `"source": "external (not generated by
   this script)"` and the path you supplied, so it's never confused with a locally-generated
   replicate later.

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
# DCR / NNDR -- run under the genomator env; --py points it at metrics for scoring
conda activate genomator
python code/dcr-nndr/score_one_dcr.py \
  --N 150 --Z 1.5 --L 0.99 --no-biasing --split-seed 101 --gen-seed 201 \
  --outdir data/synthetic_data/N150_Z1.5_L0.99_nb --splits-dir data/splits \
  --py "$PY" --keep-synth

# MAF / LD utility, same replicate
python code/compute_utility.py \
  --train data/splits/split_101/train.vcf \
  --synthetic data/synthetic_data/N150_Z1.5_L0.99_nb/syn/syn_N150_Z1.5_L0.99_nb_split101_gen201.vcf \
  --ld --paramtag N150_Z1.5_L0.99_nb --split-seed 101 --gen-seed 201 \
  --out data/synthetic_data/N150_Z1.5_L0.99_nb/util_N150_Z1.5_L0.99_nb_split101_gen201.json
```

### Calling `compute_dcr_scores.py` directly (e.g. for re-scoring an existing synthetic VCF without regenerating it)

For scoring a synthetic VCF you already have — e.g. from the web Generate tab — prefer
`score_one_dcr.py --synthetic-vcf` (see "Using synthetic data from the web Generate tab"
above): same scoring, plus `run_config` annotation and the standard output layout. The
lower-level path below is what it calls internally, useful if you want to skip all of that
and just score three files sitting in a folder directly.

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

`run_cell_sweep.py` itself needs no special environment (it only launches subprocesses),
but launches each replicate's `score_one_dcr.py` under `$GENOMATOR_PY`/`--genomator-py`
(default: whatever interpreter you ran `run_cell_sweep.py` with), passing along
`$PY`/`--py` for that replicate's own scoring step, and `--genomator-src` if you set one.
`--outdir` defaults to `data/synthetic_data/<paramtag>`, matching the standard layout; `--workers`
defaults to 6. Any replicate whose result JSON already exists is skipped (same idempotency as
`score_one_dcr.py`), so re-running after a partial failure only redoes what's missing.

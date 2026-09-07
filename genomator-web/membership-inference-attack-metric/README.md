# In-Depth Privacy Metric — local runner

Runs the same split-cohort / regenerate / compare privacy check as the
Calculate tab's "In-Depth Privacy Metric", outside the browser
(`run_indepth_locally.py`, Genomator only), plus a multi-tool variant that
compares Genomator against baseline generators from the original paper
(`run_comparative_privacy_experiment.py`, see below).

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` covers `run_indepth_locally.py` and the `genomator`/
`markov` tools of `run_comparative_privacy_experiment.py`. The `crbm`/`wgan`/
`rbm` tools also need PyTorch — install it separately (CPU-only wheel is
smaller/faster than the default PyPI build):

```bash
pip install -r requirements-torch.txt --index-url https://download.pytorch.org/whl/cpu
```

## Run

```bash
python3 run_indepth_locally.py --input your_real_data.vcf --number-of-genomes 10 --preset balanced
```

`--preset` sets the same N/L/Z values as the Calculate tab's generation
profile buttons (`balanced`, `high-accuracy`, `high-privacy`); pass
`--cluster-group-size`/`--exception-space`/`--looseness` to override any of
them individually, or use `--preset` as a base and override just one.
`--seed` fixes which two halves the real cohort is split into, for a
reproducible comparison across runs; omit it for a fresh random split each
time. Run `python3 run_indepth_locally.py --help` for the full option list.

The real cohort is split in half automatically — you only ever pass one
input VCF, never a pre-generated synthetic file, since this method generates
its own synthetic data internally (twice, once per half).

Output is the same `score±uncertainty` format shown on the Calculate tab: 1
means no detectable membership leakage between the two halves.

## Comparative privacy experiment

`run_comparative_privacy_experiment.py` runs the same split-cohort idea but
across multiple synthetic-data generators side by side, replicating how the
original Genomator paper demonstrated its privacy advantage by comparing
against baseline generators (CRBM, WGAN, RBM, Markov chain) rather than
reporting Genomator in isolation.

```bash
python3 run_comparative_privacy_experiment.py --input your_real_data.vcf \
    --number-of-genomes 10 --tools genomator,markov,crbm,wgan,rbm --seed 42
```

`--tools` is a comma-separated subset of `genomator`, `markov`, `crbm`,
`wgan`, `rbm`. `genomator` and `markov` need only `requirements.txt`; `crbm`,
`wgan` and `rbm` also need PyTorch (`pip install -r requirements-torch.txt`,
see below) — a tool whose dependencies aren't installed is skipped with a
message rather than crashing the run. `--seed`/`--preset`/`--markov-window`
work the same as `run_indepth_locally.py`. Output is a table of own-half vs.
other-half nearest-neighbor distance stats (mean and median) per tool — see
`mean_median_attack.py` for exactly what each column means.

**Reduced-epoch caveat:** `crbm`/`wgan`/`rbm` are trained for far fewer
epochs here than the paper's original HPC-scale runs (hundreds vs. tens of
thousands), so a laptop CPU finishes in minutes instead of hours or days —
see the epoch-count comments in `providers.py` for the specifics and
measured per-tool timings. That means these three baselines are much less
converged here than in the paper: an undertrained generator can produce
noisier — or, just as easily, blander/more-random — output than a fully
trained one, which can swing the membership-inference stat in either
direction. In our own test run, WGAN's own-vs-other distance came out
essentially identical (ratio ≈ 1.0), which looks like a strong privacy
result but is more likely just an undertrained generator producing
output uncorrelated with any individual real sample, real or synthetic. Read
results from this tool as illustrating the *comparison methodology*, not as
a reproduction of the paper's published numbers.
`--tools`/`--seed`/etc. don't expose per-tool epoch counts as CLI flags;
call `providers.crbm_generate`/`wgan_generate`/`rbm_generate` directly (or
edit the `kwargs` dict in `run_comparative_privacy_experiment.py`) with
`ep_max` (crbm/rbm) or `epochs` (wgan) set higher for closer-to-paper-scale
runs.

## Files

- `run_indepth_locally.py` — single-tool (Genomator-only) CLI entry point,
  described above.
- `run_comparative_privacy_experiment.py` — multi-tool CLI entry point,
  described above.
- `providers.py` — registry of generators (`genomator`, `markov`, `crbm`,
  `wgan`, `rbm`) that `run_comparative_privacy_experiment.py` can run; each
  entry's `generate()`/`is_available()` pair is what to look at for a given
  tool's reduced-scale defaults and why they were chosen.
- `mean_median_attack.py` — the own-half/other-half nearest-neighbor
  distance statistic used to compare tools.
- `baseline_vcf_io.py` — cyvcf2-free VCF genome-string load/save used by
  `MARK_run.py`/`CRBM_run.py`/`WGAN_run.py`/`RBM_run.py`.
- `MARK_run.py`, `CRBM_run.py`, `WGAN_run.py`, `RBM_run.py` — the paper's
  baseline generators, ported from `experiment/experiment_tools/tools/`
  (import line and pickle→VCF glue only; model/training code unchanged —
  see each file's header comment).
- `genomator_mini.py`, `vcf_parsing.py` — copied unchanged from
  `genomator-web/frontend/src/assets/` (the first renamed from
  `genomator_mini` so Python can import it). If you update the web version,
  re-copy these two to keep this runner in sync.
- `indepth_privacy_metric_pyodide.py` — the split-cohort / nearest-neighbor
  distance logic both runners are built on. It used to also power a "run in
  the browser" mode on the Calculate tab; that mode has been retired in
  favour of the comparison above, so this file is now maintained here
  directly rather than copied from a browser asset.

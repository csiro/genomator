#!/usr/bin/env python3

import argparse
import importlib.machinery
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

import click

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)  # code/ -- holds split_train_holdout.py
REPO_ROOT = os.path.dirname(CODE_DIR)  # this package's own root -- holds data/

sys.path.insert(0, HERE)
sys.path.insert(0, CODE_DIR)
from split_train_holdout import split_vcf

# The real genomator/ package is a sibling top-level folder in this same
# monorepo, not a separate project -- adding it to sys.path lets this script
# import generate_genomes() directly instead of shelling out to an installed
# "genomator" CLI binary. Reproducibility then just means seeding Python's
# random and numpy.random state once, in this process, before calling it --
# generate.py reads both as plain global state (confirmed by reading it), so
# nothing about genomator itself needs to change. Override with GENOMATOR_SRC
# if this code is ever run outside this monorepo's layout.
_MONOREPO_ROOT = os.path.dirname(os.path.dirname(REPO_ROOT))  # .../genomator-web/privacy-evaluation -> repo root
GENOMATOR_SRC_DEFAULT = os.path.join(_MONOREPO_ROOT, "genomator")

_cli_defaults_cache = {}


def _genomator_lib(genomator_src):
    """Import generate_genomes() and its VCF I/O straight from the in-repo genomator/ package."""
    if genomator_src not in sys.path:
        sys.path.insert(0, genomator_src)
    from genomator import generate_genomes, parse_genome_strings_to_VCF, parse_VCF_to_genome_strings
    return parse_VCF_to_genome_strings, parse_genome_strings_to_VCF, generate_genomes


def _genomator_cli_defaults(genomator_src):
    """Read scripts/genomator's own Click option defaults, without running its CLI.

    This script used to go through that CLI (via subprocess), which sets
    indexation_bits/difference_samples/solver_name/etc. to values that can
    differ from generate_genomes()'s own Python-level defaults (confirmed:
    indexation_bits is 8 there vs. 12 here; difference_samples is 10000 vs.
    100). Calling generate_genomes() directly means picking one set
    explicitly; reading them from the CLI script itself -- rather than
    copying the numbers here -- keeps this in sync with scripts/genomator
    automatically if its defaults ever change, instead of silently drifting.

    Deliberately uses Parameter.get_default(ctx) rather than each Parameter's
    raw .default attribute: for an is_flag=True option with no explicit
    default=, this Click version reports the raw attribute as a Sentinel.UNSET
    marker, not False -- get_default() is what actually resolves that down to
    the real effective value (confirmed by checking both directly).
    """
    if genomator_src in _cli_defaults_cache:
        return _cli_defaults_cache[genomator_src]
    if genomator_src not in sys.path:  # scripts/genomator does `from genomator import *` on load
        sys.path.insert(0, genomator_src)
    cli_path = os.path.join(genomator_src, "scripts", "genomator")
    loader = importlib.machinery.SourceFileLoader("genomator_cli", cli_path)
    spec = importlib.util.spec_from_loader("genomator_cli", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)  # module.__name__ == "genomator_cli", not "__main__" -- never invokes the CLI
    ctx = click.Context(module.Genomator)
    defaults = {p.name: p.get_default(ctx) for p in module.Genomator.params}
    _cli_defaults_cache[genomator_src] = defaults
    return defaults


def _count_samples(vcf_path):
    """Number of sample columns on the #CHROM header line (NF - 9)."""
    with open(vcf_path) as f:
        for line in f:
            if line.startswith("#CHROM"):
                return len(line.rstrip("\n").split("\t")) - 9
    raise ValueError(f"no #CHROM header line in {vcf_path}")


def _link_or_copy(src, dst):
    if os.path.lexists(dst):
        os.remove(dst)
    try:
        os.symlink(os.path.abspath(src), dst)
    except OSError:
        shutil.copyfile(src, dst)


def score_one(
    *,
    split_seed,
    gen_seed,
    source=None,
    N=150,
    Z=1.5,
    L=0.99,
    no_biasing=False,
    train_frac=0.5,
    outdir=None,
    n_synth=None,
    splits_dir=None,
    keep_synth=False,
    quiet=False,
    py=None,
    genomator_src=None,
):
    """Run one replicate and return (result_json_path, tsv_summary_line)."""
    source = source or os.path.join(REPO_ROOT, "data", "805_SNP_1000G_real.vcf")
    py = py or os.environ.get("PY") or sys.executable
    genomator_src = genomator_src or os.environ.get("GENOMATOR_SRC") or GENOMATOR_SRC_DEFAULT

    if not os.path.isfile(source):
        raise SystemExit(f"source VCF not found: {source}")

    nb = "_nb" if no_biasing else ""

    paramtag = f"N{N}_Z{Z}_L{L}{nb}"

    outdir = outdir or os.path.join(REPO_ROOT, "data", "synthetic_data", paramtag)
    splits_dir = splits_dir or os.path.join(REPO_ROOT, "data", "splits")
    os.makedirs(outdir, exist_ok=True)
    os.makedirs(splits_dir, exist_ok=True)

    def say(*msg):
        if not quiet:
            print(f"[score_one {paramtag} s{split_seed} g{gen_seed}]", *msg, file=sys.stderr)

    result = os.path.join(outdir, f"dcr_{paramtag}_split{split_seed}_gen{gen_seed}.json")
    if os.path.isfile(result) and os.path.getsize(result) > 0:
        say(f"result exists, skipping -> {result}")
        return result, _summary_line(result, paramtag, split_seed, gen_seed)

    # ---- 1. split (mkdir-lock so concurrent jobs sharing a split seed don't race) ----
    sd = os.path.join(splits_dir, f"split_{split_seed}")
    train_vcf = os.path.join(sd, "train.vcf")
    holdout_vcf = os.path.join(sd, "holdout.vcf")

    def _split_ready():
        return (
            os.path.isfile(train_vcf) and os.path.getsize(train_vcf) > 0
            and os.path.isfile(holdout_vcf) and os.path.getsize(holdout_vcf) > 0
        )

    if not _split_ready():
        os.makedirs(sd, exist_ok=True)
        lock = os.path.join(sd, ".mklock")
        try:
            os.mkdir(lock)
            have_lock = True
        except FileExistsError:
            have_lock = False
        if have_lock:
            try:
                say(f"building split (seed {split_seed}, train_frac {train_frac})")
                split_vcf(
                    source,
                    train_frac,
                    int(split_seed),
                    train_vcf,
                    holdout_vcf,
                    os.path.join(sd, "split_audit.json"),
                )
            finally:
                os.rmdir(lock)
        else:
            say(f"another job is building split {split_seed}; waiting")
            while not _split_ready():
                time.sleep(2)

    ns = int(n_synth) if n_synth is not None else _count_samples(train_vcf)

    # ---- 2. generate (skip if a synthetic VCF for these exact params is already on disk --
    #         e.g. the result JSON was deleted/never written but --keep-synth preserved the VCF
    #         from an earlier run; re-generating would just waste a SAT solve to reproduce it) ----
    z_arg = "0" if float(Z) == 0 else f"-{Z}"
    job = tempfile.mkdtemp(prefix=f".job_{paramtag}_s{split_seed}_g{gen_seed}_", dir=outdir)
    syn_dir = os.path.join(outdir, "syn")
    os.makedirs(syn_dir, exist_ok=True)
    syn = os.path.join(syn_dir, f"syn_{paramtag}_split{split_seed}_gen{gen_seed}.vcf")
    generated_now = False
    # computed unconditionally (cheap, cached after the first call) so it's available for
    # run_config annotation below even on a skip-generation ("already exists") run
    cli_defaults = _genomator_cli_defaults(genomator_src)
    try:
        if os.path.isfile(syn) and os.path.getsize(syn) > 0:
            say(f"synthetic VCF already exists, skipping generation -> {syn}")
        else:
            generated_now = True
            say(f"generating up to {ns} genomes  (N={N} Z={z_arg} L={L}{' no_biasing' if nb else ''})  seed {gen_seed}")

            parse_VCF_to_genome_strings, parse_genome_strings_to_VCF, generate_genomes = _genomator_lib(genomator_src)

            # Seeding both here, once, right before the one generate_genomes() call this
            # replicate makes, is what makes it reproducible -- generate.py draws from
            # these same two global streams throughout, in this one process (tasks=1
            # below is required for that: >1 spreads work over an mp.Pool, whose workers
            # don't inherit a coordinated sub-seed from this one).
            random.seed(int(gen_seed))
            np.random.seed(int(gen_seed))

            train_genomes, ploidy = parse_VCF_to_genome_strings(train_vcf)
            new_genomes = generate_genomes(
                train_genomes,
                int(N),  # argparse leaves --N as a string; Click used to coerce this for us
                None,
                ns,
                1,  # diversity_requirement -- this script has always fixed this at 1
                1,  # generated_diversity_requirement -- ditto
                exception_space=float(z_arg),
                looseness=float(L),
                biasing=not no_biasing,
                tasks=1,  # required for the seeding above to govern generation -- see comment above
                dump_all_generated=True,
                # Below: everything this script has never overridden, so the CLI's own
                # default silently applied before -- read straight from scripts/genomator
                # rather than duplicating the numbers here (see _genomator_cli_defaults).
                solver_name=cli_defaults["solver_name"],
                indexation_bits=cli_defaults["indexation_bits"],
                no_smart_clustering=cli_defaults["no_smart_clustering"],
                cluster_information_file=cli_defaults["cluster_information_file"],
                difference_samples=cli_defaults["difference_samples"],
                max_restarts=cli_defaults["max_restarts"],
            )
            if new_genomes:
                parse_genome_strings_to_VCF(
                    new_genomes, train_vcf, syn, ploidy, cli_defaults["del_info_field"]
                )

            if not (os.path.isfile(syn) and os.path.getsize(syn) > 0):
                raise SystemExit(
                    f"generate_genomes produced no synthetic VCF at {syn} -- it likely produced "
                    f"zero usable genomes for these params (N={N} Z={z_arg} L={L}); check the "
                    f"stderr output above for '... solutions generated' vs no output, and consider "
                    f"whether sample_group_size={N} is feasible for this diversity requirement "
                    f"(genomator's own README: \"you need ~>16 genomes to be able to meaningfully "
                    f"diversify on random data\")"
                )

        # ---- 3. score (compute_dcr_scores.py needs all three VCFs in one dir) ----
        _link_or_copy(train_vcf, os.path.join(job, "train.vcf"))
        _link_or_copy(holdout_vcf, os.path.join(job, "holdout.vcf"))
        _link_or_copy(syn, os.path.join(job, "synthetic.vcf"))
        say("computing DCR / NNDR")
        subprocess.run(
            [py, os.path.join(HERE, "compute_dcr_scores.py"), job, "synthetic.vcf", "result.json"],
            check=True,
            stdout=sys.stderr,
        )
        shutil.move(os.path.join(job, "result.json"), result)
    finally:
        shutil.rmtree(job, ignore_errors=True)
    # only clean up a VCF we generated ourselves this run -- never delete one we found and reused,
    # regardless of this invocation's --keep-synth (a prior run may have deliberately kept it)
    # if generated_now and not keep_synth:
    #     try:
    #         os.remove(syn)
    #     except FileNotFoundError:
    #         pass

    # ---- annotate with run_config ----
    _annotate(result, N, Z, L, no_biasing, split_seed, gen_seed, train_frac, source, ns, cli_defaults)
    say(f"wrote {result}")

    return result, _summary_line(result, paramtag, split_seed, gen_seed)


def _annotate(result, N, Z, L, no_biasing, split_seed, gen_seed, train_frac, source, ns, cli_defaults):
    with open(result) as f:
        d = json.load(f)
    actual_n_synthetic = d.get("n_synthetic", ns)
    d["run_config"] = {
        "genomator": {
            "N": int(N), "Z": float(Z), "L": float(L),
            "no_biasing": bool(no_biasing), "tasks": 1, "dump_all_generated": True,
            "exception_space_sign": (
                "negative (randomized branch)" if float(Z) != 0 else "0 (skip exceptions)"
            ),
            # everything else generate_genomes() was called with, read from
            # scripts/genomator's own Click defaults at run time rather than fixed
            # here -- recorded so a later change to those defaults doesn't quietly
            # make this result incomparable to a new one without a trace of why
            "solver_name": cli_defaults["solver_name"],
            "indexation_bits": cli_defaults["indexation_bits"],
            "no_smart_clustering": cli_defaults["no_smart_clustering"],
            "difference_samples": cli_defaults["difference_samples"],
            "max_restarts": cli_defaults["max_restarts"],
        },
        "split_seed": int(split_seed), "gen_seed": int(gen_seed),
        "train_frac": float(train_frac), "source_vcf": source,
        "n_synthetic_requested": int(ns),
        "n_synthetic": int(actual_n_synthetic),
        "rng": "split: np.random.RandomState(split_seed); generation: random.seed(gen_seed) + "
               "np.random.seed(gen_seed), then genomator.generate_genomes(..., tasks=1, "
               "dump_all_generated=True) called directly in-process (see score_one_dcr.py)",
    }
    with open(result, "w") as f:
        json.dump(d, f, indent=2)


def _summary_line(result, paramtag, split_seed, gen_seed):
    with open(result) as f:
        d = json.load(f)
    s = d["summary"]
    return "\t".join(str(x) for x in [
        paramtag, split_seed, gen_seed,
        s["flagged_count_1pct"], s["flagged_count_5pct"], d["n_synthetic"],
        round(s["dcr_ratio_median"], 6), round(s["nndr_train_median"], 6),
        result,
    ])


def main(argv=None):
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--source", default=None,
                   help="source real VCF (default: data/805_SNP_1000G_real.vcf)")
    p.add_argument("--N", default=150)
    p.add_argument("--Z", default=1.5)
    p.add_argument("--L", default=0.99)
    p.add_argument("--no-biasing", dest="no_biasing", action="store_true")
    p.add_argument("--split-seed", dest="split_seed", required=True)
    p.add_argument("--gen-seed", dest="gen_seed", required=True)
    p.add_argument("--train-frac", dest="train_frac", type=float, default=0.5)
    p.add_argument("--outdir", default=None)
    p.add_argument("--n-synth", dest="n_synth", default=None)
    p.add_argument("--splits-dir", dest="splits_dir", default=None)
    p.add_argument("--keep-synth", dest="keep_synth", action="store_true")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--py", default=None, help="python with numpy+scipy (default: this interpreter)")
    p.add_argument("--genomator-src", dest="genomator_src", default=None,
                   help="path to the genomator/ package (default: the sibling top-level "
                        "genomator/ folder in this repo)")
    args = p.parse_args(argv)

    _, line = score_one(
        split_seed=args.split_seed,
        gen_seed=args.gen_seed,
        source=args.source,
        N=args.N, Z=args.Z, L=args.L,
        no_biasing=args.no_biasing,
        train_frac=args.train_frac,
        outdir=args.outdir,
        n_synth=args.n_synth,
        splits_dir=args.splits_dir,
        keep_synth=args.keep_synth,
        quiet=args.quiet,
        py=args.py,
        genomator_src=args.genomator_src,
    )
    print(line)


if __name__ == "__main__":
    main()

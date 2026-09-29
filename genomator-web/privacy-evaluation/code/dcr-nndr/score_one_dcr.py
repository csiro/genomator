#!/usr/bin/env python3

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)  # code/ -- holds split_train_holdout.py
REPO_ROOT = os.path.dirname(CODE_DIR)  # repo root -- holds data/

sys.path.insert(0, HERE)
sys.path.insert(0, CODE_DIR)
from split_train_holdout import split_vcf 


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
    genomator_bin=None,
    gen_timeout=None,
):
    """Run one replicate and return (result_json_path, tsv_summary_line)."""
    source = source or os.path.join(REPO_ROOT, "data", "805_SNP_1000G_real.vcf")
    py = py or os.environ.get("PY") or sys.executable
    genomator_bin = genomator_bin or os.environ.get("GENOMATOR_BIN", "genomator")

    if not os.path.isfile(source):
        raise SystemExit(f"source VCF not found: {source}")

    nb = "_nb" if no_biasing else ""
    bias_arg = ["--no_biasing"] if no_biasing else []

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
    try:
        if os.path.isfile(syn) and os.path.getsize(syn) > 0:
            say(f"synthetic VCF already exists, skipping generation -> {syn}")
        else:
            if shutil.which(genomator_bin) is None and not os.path.isfile(genomator_bin):
                raise SystemExit("genomator not found (set GENOMATOR_BIN)")
            generated_now = True
            say(f"generating up to {ns} genomes  (N={N} Z={z_arg} L={L}{' no_biasing' if nb else ''})  seed {gen_seed}")
            subprocess.run(
                [
                    genomator_bin, train_vcf, syn, str(ns), "1", "1",
                    f"--sample_group_size={N}",
                    f"--exception_space={z_arg}",
                    f"--looseness={L}",
                    *bias_arg,
                    f"--seed={gen_seed}",
                    "--tasks=1",
                    "--dump_all_generated",
                ],
                check=True,
                stdout=sys.stderr,
                timeout=gen_timeout,
            )

            if not (os.path.isfile(syn) and os.path.getsize(syn) > 0):
                raise SystemExit(
                    f"genomator exited 0 but wrote no synthetic VCF at {syn} -- it likely produced "
                    f"zero usable genomes for these params (N={N} Z={z_arg} L={L}); check its own "
                    f"stderr output above for '... solutions generated' vs 'no genomes outputted', "
                    f"and consider whether sample_group_size={N} is feasible for this diversity "
                    f"requirement (genomator's own README: \"you need ~>16 genomes to be able to "
                    f"meaningfully diversify on random data\")"
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
    _annotate(result, N, Z, L, no_biasing, split_seed, gen_seed, train_frac, source, ns)
    say(f"wrote {result}")

    return result, _summary_line(result, paramtag, split_seed, gen_seed)


def _annotate(result, N, Z, L, no_biasing, split_seed, gen_seed, train_frac, source, ns):
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
        },
        "split_seed": int(split_seed), "gen_seed": int(gen_seed),
        "train_frac": float(train_frac), "source_vcf": source,
        "n_synthetic_requested": int(ns),
        "n_synthetic": int(actual_n_synthetic),
        "rng": "split: np.random.RandomState(split_seed); generation: genomator --seed gen_seed "
               "--tasks=1 --dump_all_generated",
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
    p.add_argument("--genomator-bin", dest="genomator_bin", default=None,
                   help="genomator CLI (default: genomator on PATH)")
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
        genomator_bin=args.genomator_bin,
    )
    print(line)


if __name__ == "__main__":
    main()

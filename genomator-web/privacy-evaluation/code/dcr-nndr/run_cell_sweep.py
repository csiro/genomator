#!/usr/bin/env python3
"""Generate + score all 25 replicates of one (N, Z, L) cell, in parallel."""
import argparse
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = os.path.dirname(HERE)  # code/
REPO_ROOT = os.path.dirname(CODE_DIR)  # repo root -- holds data/
SCORE_SCRIPT = os.path.join(HERE, "score_one_dcr.py")

SPLIT_SEEDS = [101, 102, 103, 104, 105]
GEN_SEEDS = [201, 202, 203, 204, 205]


def run_one(py, genomator_bin, N, Z, L, no_biasing, outdir, splits_dir, split_seed, gen_seed):
    cmd = [
        py, SCORE_SCRIPT,
        "--N", str(N), "--Z", str(Z), "--L", str(L),
        "--split-seed", str(split_seed), "--gen-seed", str(gen_seed),
        "--outdir", outdir,
        "--splits-dir", splits_dir,
        "--keep-synth", "--quiet",
    ]
    if no_biasing:
        cmd.append("--no-biasing")
    env = dict(os.environ)
    env["PY"] = py
    env["GENOMATOR_BIN"] = genomator_bin
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return split_seed, gen_seed, r.returncode, r.stdout, r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--N", required=True)
    ap.add_argument("--Z", required=True)
    ap.add_argument("--L", required=True)
    ap.add_argument("--no-biasing", dest="no_biasing", action="store_true")
    ap.add_argument(
        "--outdir", default=None,
        help=f"default: {os.path.join(REPO_ROOT, 'data', 'synthetic_data', '<paramtag>')}",
    )
    DEFAULT_SPLITS_DIR = os.path.join(REPO_ROOT, "data", "splits")
    ap.add_argument(
        "--splits-dir", dest="splits_dir", default=DEFAULT_SPLITS_DIR,
        help=f"default: {DEFAULT_SPLITS_DIR} (shared across every cell)",
    )
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--py", default=None, help="python with numpy+scipy (default: $PY or this interpreter)")
    ap.add_argument("--genomator-bin", dest="genomator_bin", default=None,
                     help="genomator CLI (default: $GENOMATOR_BIN or genomator on PATH)")
    args = ap.parse_args(argv)

    py = args.py or os.environ.get("PY") or sys.executable
    genomator_bin = args.genomator_bin or os.environ.get("GENOMATOR_BIN", "genomator")
    splits_dir = args.splits_dir  # argparse default is already the real path (see add_argument above)

    nb = "_nb" if args.no_biasing else ""
    paramtag = f"N{args.N}_Z{args.Z}_L{args.L}{nb}"
    outdir = args.outdir or os.path.join(REPO_ROOT, "data", "synthetic_data", paramtag)
    os.makedirs(outdir, exist_ok=True)

    jobs = [(s, g) for s in SPLIT_SEEDS for g in GEN_SEEDS]
    print(f"{paramtag}: running {len(jobs)} replicates -> {outdir}")

    failures = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {
            ex.submit(
                run_one, py, genomator_bin, args.N, args.Z, args.L, args.no_biasing,
                outdir, splits_dir, s, g,
            ): (s, g)
            for s, g in jobs
        }
        for fut in as_completed(futs):
            s, g, rc, out, err = fut.result()
            done += 1
            if rc != 0:
                failures.append((s, g, err[-3000:]))
                print(f"[{done}/{len(jobs)}] FAILED split{s} gen{g} (rc={rc})", file=sys.stderr)
            else:
                print(f"[{done}/{len(jobs)}] ok split{s} gen{g}")

    print(f"\ndone: {done - len(failures)}/{len(jobs)} succeeded, {len(failures)} failed")
    if failures:
        print("\n=== FAILURES ===")
        for s, g, err in failures:
            print(f"--- split{s} gen{g} ---")
            print(err)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

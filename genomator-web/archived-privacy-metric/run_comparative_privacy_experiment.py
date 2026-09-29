#!/usr/bin/env python3

# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation
# (CSIRO) ABN 41 687 119 230.
#
# This source code is licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Comparative membership-inference privacy experiment: splits a real cohort
# in half, generates synthetic data from each half with one or more tools
# (Genomator, plus the paper's Markov/CRBM/WGAN/RBM baselines where their
# dependencies are installed), and reports the same own-half vs. other-half
# nearest-neighbor distance statistics the original paper used to show
# Genomator's privacy relative to those baselines - not just in isolation.
#
# This is the local, multi-tool replacement for the Calculate tab's old
# in-browser "In-Depth Privacy Metric": only Genomator is light enough to
# run inside a browser tab, so a fair comparison against the other methods
# has to happen here instead.

import asyncio
import os

import click

import genomator_mini
import indepth_privacy_metric_pyodide as indepth
from mean_median_attack import compute_mean_median_stats, format_comparison_table
from providers import PROVIDERS

# indepth_privacy_metric_pyodide.split_vcf_by_sample is reused as-is for the
# cohort split; it doesn't call Genomator_exec itself, but keep parity with
# run_indepth_locally.py's injection in case that changes.
indepth.Genomator_exec = genomator_mini.Genomator_exec

HALF_A_FILE = "compare_half_a.vcf"
HALF_B_FILE = "compare_half_b.vcf"


@click.command()
@click.option(
    "--input", "-i", "input_vcf_file",
    required=True, type=click.types.Path(exists=True),
    help="Original (real) input VCF file.",
)
@click.option(
    "--number-of-genomes", "-n", "number_of_genomes",
    type=click.types.INT, default=10, show_default=True,
    help="Synthetic samples to generate per cohort half, per tool.",
)
@click.option(
    "--tools", "tools",
    default="genomator,markov", show_default=True,
    help="Comma-separated list of tools to run: " + ", ".join(PROVIDERS),
)
@click.option(
    "--seed", "-s", "seed",
    type=click.types.INT, default=None,
    help="Random seed for the real-cohort split. Omit for a fresh random split each run.",
)
@click.option(
    "--preset", "preset",
    type=click.Choice(sorted(["balanced", "high-accuracy", "high-privacy"])),
    default="balanced", show_default=True,
    help="Genomator generation profile (N/L/Z).",
)
@click.option(
    "--markov-window", "markov_window",
    type=click.types.INT, default=10, show_default=True,
    help="Markov chain window length (only used by the markov tool).",
)
@click.option(
    "--keep-files", is_flag=True, default=False,
    help="Keep the intermediate half/synthetic VCFs instead of deleting them when done.",
)
def run(input_vcf_file, number_of_genomes, tools, seed, preset, markov_window, keep_files):
    requested = [t.strip() for t in tools.split(",") if t.strip()]
    for tool in requested:
        if tool not in PROVIDERS:
            raise click.BadParameter(f"unknown tool '{tool}', choose from: {', '.join(PROVIDERS)}")

    print("Splitting real cohort into two halves...")
    size_a, size_b = asyncio.run(
        indepth.split_vcf_by_sample(input_vcf_file, HALF_A_FILE, HALF_B_FILE, seed)
    )
    print(f"Cohort A: {size_a} samples, cohort B: {size_b} samples")

    kwargs = {"preset": preset, "markov_window": markov_window}
    written_files = []
    results = {}

    for tool in requested:
        provider = PROVIDERS[tool]
        available, reason = provider["is_available"]()
        if not available:
            print(f"Skipping {tool}: {reason}")
            continue

        print(f"Running {tool} on cohort A and B...")
        synth_a_file = f"compare_synth_a_{tool}.vcf"
        synth_b_file = f"compare_synth_b_{tool}.vcf"
        try:
            provider["generate"](HALF_A_FILE, synth_a_file, number_of_genomes, **kwargs)
            provider["generate"](HALF_B_FILE, synth_b_file, number_of_genomes, **kwargs)
        except NotImplementedError as e:
            print(f"Skipping {tool}: {e}")
            continue
        written_files += [synth_a_file, synth_b_file]

        results[tool] = compute_mean_median_stats(HALF_A_FILE, HALF_B_FILE, synth_a_file, synth_b_file)

    if not keep_files:
        for f in written_files + [HALF_A_FILE, HALF_B_FILE]:
            if os.path.exists(f):
                os.remove(f)

    if not results:
        print("No tools produced results.")
        return

    print()
    print(format_comparison_table(results))


if __name__ == "__main__":
    run()

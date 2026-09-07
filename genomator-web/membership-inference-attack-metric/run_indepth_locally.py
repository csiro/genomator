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

# Local (non-browser) driver for the in-depth privacy metric.
#
# indepth_privacy_metric_pyodide.py calls Genomator_exec() unqualified: in the
# browser, PyodideService loads genomator_mini and this script into one shared
# namespace, so it's already there by the time InDepth_privacy_metric_exec()
# runs. Run as a normal Python import instead, that name is never defined -
# so this driver imports genomator_mini itself and injects its Genomator_exec
# into the metric module before calling it, matching what the browser does.

import asyncio

import click

import genomator_mini
import indepth_privacy_metric_pyodide as indepth

indepth.Genomator_exec = genomator_mini.Genomator_exec

# N / L / Z presets, matching the Calculate tab's "In-Depth Privacy Metric"
# generation profile buttons.
PRESETS = {
    "balanced": {"cluster_group_size": 5, "exception_space": 0.5, "looseness": 0.5},
    "high-accuracy": {"cluster_group_size": 5, "exception_space": 0, "looseness": 0},
    "high-privacy": {"cluster_group_size": 10, "exception_space": 1, "looseness": 0.99},
}


@click.command()
@click.option(
    "--input", "-i", "input_vcf_file",
    required=True, type=click.types.Path(exists=True),
    help="Original (real) input VCF file.",
)
@click.option(
    "--number-of-genomes", "-n", "number_of_genomes",
    type=click.types.INT, default=10, show_default=True,
    help="Synthetic samples to generate per cohort half.",
)
@click.option(
    "--preset", "preset",
    type=click.Choice(sorted(PRESETS)), default="balanced", show_default=True,
    help="Generation profile (N/L/Z), matching the Calculate tab's presets.",
)
@click.option(
    "--cluster-group-size", "-c", "cluster_group_size",
    type=click.types.INT, default=None,
    help="N: overrides --preset.",
)
@click.option(
    "--exception-space", "-z", "exception_space",
    type=click.types.FLOAT, default=None,
    help="Z: overrides --preset.",
)
@click.option(
    "--looseness", "-l", "looseness",
    type=click.types.FLOAT, default=None,
    help="L: overrides --preset. Pass --looseness=-1 to tune it automatically instead.",
)
@click.option(
    "--seed", "-s", "seed",
    type=click.types.INT, default=None,
    help="Random seed for the real-cohort split. Omit for a fresh random split each run.",
)
def run(
    input_vcf_file,
    number_of_genomes,
    preset,
    cluster_group_size,
    exception_space,
    looseness,
    seed,
):
    values = dict(PRESETS[preset])
    if cluster_group_size is not None:
        values["cluster_group_size"] = cluster_group_size
    if exception_space is not None:
        values["exception_space"] = exception_space
    if looseness is not None:
        values["looseness"] = None if looseness < 0 else looseness

    result = asyncio.run(
        indepth.InDepth_privacy_metric_exec(
            input_vcf_file,
            number_of_genomes,
            values["exception_space"],
            values["cluster_group_size"],
            values["looseness"],
            seed,
        )
    )
    print(result)


if __name__ == "__main__":
    run()

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

# Ports experiment/experiment_tools/tools/attribute_inference_experiment.py's
# statistic (per real individual: nearest-neighbor distance to their own
# half's synthetic data, normalized by genome length, vs. to the other
# half's) to work directly off VCF files, reusing the same fast matmul-based
# Hamming distance code already validated for the in-depth privacy metric
# (indepth_privacy_metric_pyodide.nearest_neighbor_min_distance), instead of
# the original's per-individual Python loop + multiprocessing pool.
#
# The original script reports both mean and median of the own-distance,
# other-distance, their ratio and their difference; the paper's own
# comparison figure (experiment/experiment/attribute_scripts/process.py)
# plots the median. This module reports both, so a comparison across
# generators can be read either way.

import asyncio

import numpy as np

from vcf_parsing import parse_vcf_to_genotype_matrix
from indepth_privacy_metric_pyodide import nearest_neighbor_min_distance


def compute_mean_median_stats(real_a_vcf, real_b_vcf, synth_a_vcf, synth_b_vcf):
    """Own-half vs. other-half nearest-neighbor distance stats for one generator.

    real_a_vcf/real_b_vcf: the two real cohort halves.
    synth_a_vcf/synth_b_vcf: synthetic data generated from each half by the
    same generator, at matched sample counts.
    """
    real_a = asyncio.run(parse_vcf_to_genotype_matrix(real_a_vcf))
    real_b = asyncio.run(parse_vcf_to_genotype_matrix(real_b_vcf))
    synth_a = asyncio.run(parse_vcf_to_genotype_matrix(synth_a_vcf))
    synth_b = asyncio.run(parse_vcf_to_genotype_matrix(synth_b_vcf))

    assert (
        real_a.shape[1] == real_b.shape[1] == synth_a.shape[1] == synth_b.shape[1]
    ), "Real cohort halves and their synthetic outputs should encode the same number of variant/haplotype dimensions"
    length = real_a.shape[1]

    in_dist_a = asyncio.run(nearest_neighbor_min_distance(real_a, synth_a)) / length
    out_dist_a = asyncio.run(nearest_neighbor_min_distance(real_a, synth_b)) / length
    in_dist_b = asyncio.run(nearest_neighbor_min_distance(real_b, synth_b)) / length
    out_dist_b = asyncio.run(nearest_neighbor_min_distance(real_b, synth_a)) / length

    x = np.concatenate([in_dist_a, in_dist_b])
    y = np.concatenate([out_dist_a, out_dist_b])
    ratio = np.where(x > 0, y / np.where(x > 0, x, 1), 9999.0)
    difference = y - x

    return {
        "n": int(len(x)),
        "mean_own": float(np.mean(x)),
        "median_own": float(np.median(x)),
        "mean_other": float(np.mean(y)),
        "median_other": float(np.median(y)),
        "mean_ratio": float(np.mean(ratio)),
        "median_ratio": float(np.median(ratio)),
        "mean_difference": float(np.mean(difference)),
        "median_difference": float(np.median(difference)),
    }


STAT_COLUMNS = [
    ("mean_own", "mean own-dist"),
    ("median_own", "median own-dist"),
    ("mean_other", "mean other-dist"),
    ("median_other", "median other-dist"),
    ("mean_difference", "mean (other-own)"),
    ("median_difference", "median (other-own)"),
    ("mean_ratio", "mean ratio"),
    ("median_ratio", "median ratio"),
]


def format_comparison_table(results):
    """results: dict of {tool_name: stats dict from compute_mean_median_stats}."""
    headers = ["tool"] + [label for _, label in STAT_COLUMNS]
    rows = [headers]
    for tool, stats in results.items():
        row = [tool] + [f"{stats[key]:.4f}" for key, _ in STAT_COLUMNS]
        rows.append(row)
    widths = [max(len(row[i]) for row in rows) for i in range(len(headers))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * widths[i] for i in range(len(headers))))
    lines.append("")
    lines.append(
        "Own-distance smaller than other-distance (positive 'other-own' difference, "
        "ratio above 1) means a real individual's own half's synthetic data sits "
        "closer than the other half's - i.e. detectable membership signal. Larger "
        "gaps between tools here are the same comparison the original paper made "
        "across generation methods."
    )
    return "\n".join(lines)

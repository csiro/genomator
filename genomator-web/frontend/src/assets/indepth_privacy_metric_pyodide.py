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

# In-browser (Pyodide) "in-depth" privacy evaluation: a split-half nearest-neighbor
# membership test, ported from experiment/experiment_tools/tools/attribute_inference_experiment.py.
#
# The input cohort is split into two disjoint sample halves; Genomator generates
# synthetic data from each half independently (reusing Genomator_exec, already
# loaded); a real individual is then checked for whether they sit closer to the
# synthetic data generated from their OWN half ("in-distance") than to the
# synthetic data generated from the OTHER half ("out-distance"). Systematically
# smaller in-distance than out-distance indicates membership leakage.
#
# Depends on Genomator_exec (genomator_mini) and parse_vcf_to_genotype_matrix
# (accuracy_metric_pyodide.py), both loaded earlier in the same Pyodide session
# by PyodideService.

from asyncio import sleep
from copy import deepcopy
import math

import numpy as np
import vcfpy


async def split_vcf_by_sample(input_vcf_file, out_a, out_b, seed=None):
    reader = vcfpy.Reader.from_path(input_vcf_file)
    samples = list(reader.header.samples.names)
    num_samples = len(samples)
    assert num_samples >= 4, (
        "Need at least 4 samples in the input VCF to perform a split-half privacy evaluation"
    )
    rng = np.random.default_rng(seed)
    order = rng.permutation(num_samples)
    half = num_samples // 2
    idx_a = sorted(order[:half].tolist())
    idx_b = sorted(order[half:].tolist())

    header_a = deepcopy(reader.header)
    header_a.samples = vcfpy.SamplesInfos([samples[i] for i in idx_a])
    header_b = deepcopy(reader.header)
    header_b.samples = vcfpy.SamplesInfos([samples[i] for i in idx_b])

    writer_a = vcfpy.Writer.from_path(out_a, header_a)
    writer_b = vcfpy.Writer.from_path(out_b, header_b)

    for record in reader:
        calls_a = [deepcopy(record.calls[i]) for i in idx_a]
        calls_b = [deepcopy(record.calls[i]) for i in idx_b]

        record.calls = calls_a
        record.update_calls(record.calls)
        writer_a.write_record(record)

        record.calls = calls_b
        record.update_calls(record.calls)
        writer_b.write_record(record)

    reader.close()
    writer_a.close()
    writer_b.close()
    return len(idx_a), len(idx_b)


def pairwise_hamming(A, B):
    A = A.astype(np.float32)
    B = B.astype(np.float32)
    sum_a = np.sum(A, axis=1, keepdims=True)
    sum_b = np.sum(B, axis=1, keepdims=True).T
    dot = A @ B.T
    return np.clip(sum_a + sum_b - 2 * dot, 0, None)


def nearest_neighbor_min_distance(A, B):
    return np.min(pairwise_hamming(A, B), axis=1)


def format_with_uncertainty(val, uncertainty):
    if uncertainty <= 0:
        return str(val)
    else:
        decimal_places = math.ceil(-math.log10(uncertainty))
        first_digit = int(uncertainty * (10**decimal_places))
        if first_digit == 1:
            decimal_places += 1
        rounded_uncertainty = round(uncertainty, decimal_places)
        format_decimal_places = max(decimal_places, 0)
        return f"{round(val, decimal_places):.{format_decimal_places}f}±{rounded_uncertainty:.{format_decimal_places}f}"


async def InDepth_privacy_metric_exec(
    input_vcf_file,
    number_of_genomes,
    exception_space=0,
    cluster_group_size=10,
    looseness=None,
    seed=None,
):
    print("indepth stage 0/4: splitting cohort into two halves")
    await sleep(0)
    size_a, size_b = await split_vcf_by_sample(
        input_vcf_file, "indepth_half_a.vcf", "indepth_half_b.vcf", seed
    )
    print(f"split into cohort A ({size_a} samples) and cohort B ({size_b} samples)")
    await sleep(0)

    print("indepth stage 1/4: generating synthetic data for cohort A")
    await sleep(0)
    await Genomator_exec(
        "indepth_half_a.vcf",
        "indepth_synth_a.vcf",
        number_of_genomes,
        exception_space,
        cluster_group_size,
        looseness,
    )

    print("indepth stage 2/4: generating synthetic data for cohort B")
    await sleep(0)
    await Genomator_exec(
        "indepth_half_b.vcf",
        "indepth_synth_b.vcf",
        number_of_genomes,
        exception_space,
        cluster_group_size,
        looseness,
    )

    print("indepth stage 3/4: computing nearest-neighbor distances")
    await sleep(0)
    real_a = await parse_vcf_to_genotype_matrix("indepth_half_a.vcf")
    real_b = await parse_vcf_to_genotype_matrix("indepth_half_b.vcf")
    synth_a = await parse_vcf_to_genotype_matrix("indepth_synth_a.vcf")
    synth_b = await parse_vcf_to_genotype_matrix("indepth_synth_b.vcf")

    assert (
        real_a.shape[1] == real_b.shape[1] == synth_a.shape[1] == synth_b.shape[1]
    ), "Split cohorts and their synthetic outputs should encode the same number of variant/haplotype dimensions"

    in_dist_a = nearest_neighbor_min_distance(real_a, synth_a)
    out_dist_a = nearest_neighbor_min_distance(real_a, synth_b)
    in_dist_b = nearest_neighbor_min_distance(real_b, synth_b)
    out_dist_b = nearest_neighbor_min_distance(real_b, synth_a)

    in_distances = np.concatenate([in_dist_a, in_dist_b])
    out_distances = np.concatenate([out_dist_a, out_dist_b])
    delta = out_distances - in_distances

    mean_in = float(np.mean(in_distances))
    mean_out = float(np.mean(out_distances))
    se_delta = (
        float(np.std(delta, ddof=1) / np.sqrt(len(delta))) if len(delta) > 1 else 0.0
    )

    score = 1.0 if mean_out == 0 else min(1.0, mean_in / mean_out)
    uncertainty = 0.0 if mean_out == 0 else se_delta / mean_out

    result = format_with_uncertainty(score, uncertainty)
    print("indepth stage 4/4: done")
    print(f"RESULT:{result}")
    await sleep(0)
    return result

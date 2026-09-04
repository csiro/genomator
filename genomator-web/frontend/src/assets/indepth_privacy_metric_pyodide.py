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
# Depends on Genomator_exec (genomator_mini), loaded earlier in the same
# Pyodide session by PyodideService.  Genotypes are read through vcf_parsing.
# Splitting the cohort is a matter of copying header lines through unchanged
# and re-joining each data line's fixed columns with a sample-index subset of
# its calls, so it is done the same way vcf_parsing reads: straight off the
# raw bytes, not through vcfpy.  vcfpy allocates a Record and a Call per
# sample per row, which is the same cost that made it too slow to read with,
# and here it was worse: run with no `await sleep(0)` in the per-record loop
# at all, so splitting a 780 sample exome VCF froze the tab for minutes.

from asyncio import sleep
import math

import numpy as np

from vcf_parsing import open_vcf, parse_vcf_to_genotype_matrix, PROGRESS_INTERVAL_RECORDS


async def split_vcf_by_sample(input_vcf_file, out_a, out_b, seed=None):
    """Split a VCF's samples into two random disjoint halves, by column.

    Reads and writes raw bytes line by line: header lines are copied through
    unchanged, and each data line's 9 fixed columns are re-joined with a
    sample-index subset of its calls.  No genotype decoding is needed for
    this, so it stays well clear of vcf_parsing's fixed-width fast path.
    """
    idx_a = idx_b = None
    num_records = 0
    with open_vcf(input_vcf_file) as handle, open(out_a, "wb") as fa, open(out_b, "wb") as fb:
        for line in handle:
            if not line.strip():
                continue
            if line.startswith(b"##"):
                fa.write(line)
                fb.write(line)
                continue
            fields = line.rstrip(b"\r\n").split(b"\t")
            prefix, calls = fields[:9], fields[9:]
            if line.startswith(b"#CHROM"):
                num_samples = len(calls)
                assert num_samples >= 4, (
                    "Need at least 4 samples in the input VCF to perform a split-half privacy evaluation"
                )
                rng = np.random.default_rng(seed)
                order = rng.permutation(num_samples)
                half = num_samples // 2
                idx_a = sorted(order[:half].tolist())
                idx_b = sorted(order[half:].tolist())
            else:
                assert idx_a is not None, "VCF file has no #CHROM header line"
                num_records += 1
            fa.write(b"\t".join(prefix + [calls[i] for i in idx_a]) + b"\n")
            fb.write(b"\t".join(prefix + [calls[i] for i in idx_b]) + b"\n")
            if num_records % PROGRESS_INTERVAL_RECORDS == 0:
                await sleep(0)
    assert idx_a is not None, "VCF file has no #CHROM header line"
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
    n = len(in_distances)

    print(
        f"mean own-group distance: {float(np.mean(in_distances)):.1f}, "
        f"mean other-group distance: {float(np.mean(out_distances)):.1f} "
        f"(out of {real_a.shape[1]} positions)"
    )

    # Privacy score, matching the quadruplet metric's exact convention: for
    # each real individual, does their own half's synthetic data sit closer
    # ("in") or the other half's ("out")?  advantage = TPR - FPR of that one
    # bit of evidence; a generator with no membership signal gives advantage
    # 0 (score 1), one that always gives the real individual away gives
    # advantage 1 (score 0).  Not clamped, for the same reason the quadruplet
    # metric doesn't clamp: a small negative advantage from sampling noise is
    # more honest than hiding it at the 1.0 ceiling.
    p_in_closer = float(np.count_nonzero(in_distances < out_distances)) / n
    p_out_closer = float(np.count_nonzero(out_distances < in_distances)) / n
    advantage = p_in_closer - p_out_closer
    advantage_variance = ((p_in_closer + p_out_closer) - advantage**2) / n
    uncertainty = advantage_variance**0.5

    result = format_with_uncertainty(1 - advantage, uncertainty)

    # Plain-language context for the score above: pool the two "guess which
    # half this person came from" attacks (against synth_a and against
    # synth_b) into one membership-inference attack accuracy. This is not
    # part of the score itself, just an explanation of it.
    member_scores = np.concatenate([in_dist_a, in_dist_b])
    nonmember_scores = np.concatenate([out_dist_b, out_dist_a])
    correct = np.count_nonzero(member_scores[:, None] < nonmember_scores[None, :])
    tied = np.count_nonzero(member_scores[:, None] == nonmember_scores[None, :])
    attack_accuracy = (correct + 0.5 * tied) / (len(member_scores) * len(nonmember_scores))
    print(
        f"For context: guessing which half a person belonged to by "
        f"nearest-neighbor distance alone would be correct about "
        f"{attack_accuracy * 100:.0f}% of the time (50% = no better than a coin flip)."
    )

    print("indepth stage 4/4: done")
    print(f"RESULT:{result}")
    await sleep(0)
    return result

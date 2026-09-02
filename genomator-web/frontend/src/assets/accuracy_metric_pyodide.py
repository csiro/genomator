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

# In-browser (Pyodide) accuracy metric evaluation.
#
# This mirrors assets/accuracy_metric.py, but parses VCFs with vcfpy (already
# loaded into the Pyodide runtime for genome generation) instead of cyvcf2,
# and reimplements POT's sliced_wasserstein_distance/wasserstein_1d in plain
# numpy, since POT ships compiled extensions with no WASM/Emscripten build.

from asyncio import sleep
import math

import numpy as np
import vcfpy

ACCURACY_TRIALS_DEFAULT = 50
ACCURACY_SLICES_DEFAULT = 300


async def accuracy_metric_progress(itera, start_message, label, skip=0):
    itera = list(itera)
    print(start_message)
    await sleep(0)
    l = len(itera)
    for ii, i in enumerate(itera):
        if ii & ((2**skip) - 1) == 0:
            print(f"{label} {ii}/{l}")
            await sleep(0)
        yield i
    print(f"{label} {l}/{l}")
    await sleep(0)


async def parse_vcf_to_genotype_matrix(vcf_file):
    print(f"loading VCF file: {vcf_file}")
    await sleep(0)
    reader = vcfpy.Reader.from_path(vcf_file)
    num_samples = len(reader.header.samples.names)
    assert num_samples > 0, "VCF file does not contain any samples"
    columns = []
    num_records = 0
    for j, record in enumerate(reader):
        ploidy = None
        haplotype_columns = None
        for call in record.calls:
            if ploidy is None:
                ploidy = call.ploidy
                haplotype_columns = [[] for _ in range(ploidy)]
            assert call.ploidy == ploidy, "genome ploidies must be identical"
            alleles = call.gt_alleles
            for h in range(ploidy):
                allele = alleles[h]
                assert allele is not None, "cannot currently work with missing data"
                haplotype_columns[h].append(int(allele))
        if haplotype_columns is not None:
            columns.extend(haplotype_columns)
        num_records += 1
        if j & 63 == 0:
            print(f"loaded variants {j}")
            await sleep(0)
    reader.close()
    print(f"loaded variants {num_records}/{num_records}")
    await sleep(0)
    if not columns:
        return np.zeros((num_samples, 0))
    genotypes_array = np.array(columns, dtype=np.uint8).T
    return genotypes_array


def get_random_projections(d, n_projections, rng):
    projections = rng.standard_normal((d, n_projections))
    projections = projections / np.sqrt(np.sum(projections**2, axis=0, keepdims=True))
    return projections


def quantile_function(qs, cws, xs):
    n = xs.shape[0]
    idx = np.empty(qs.shape, dtype=np.intp)
    for k in range(qs.shape[1]):
        idx[:, k] = np.searchsorted(cws[:, k], qs[:, k])
    idx = np.clip(idx, 0, n - 1)
    return np.take_along_axis(xs, idx, axis=0)


def wasserstein_1d(u_values, v_values, u_weights, v_weights, p=2):
    u_sorter = np.argsort(u_values, axis=0)
    u_values = np.take_along_axis(u_values, u_sorter, axis=0)
    u_weights = np.take_along_axis(u_weights, u_sorter, axis=0)

    v_sorter = np.argsort(v_values, axis=0)
    v_values = np.take_along_axis(v_values, v_sorter, axis=0)
    v_weights = np.take_along_axis(v_weights, v_sorter, axis=0)

    u_cumweights = np.cumsum(u_weights, axis=0)
    v_cumweights = np.cumsum(v_weights, axis=0)

    qs = np.sort(np.concatenate((u_cumweights, v_cumweights), axis=0), axis=0)
    u_quantiles = quantile_function(qs, u_cumweights, u_values)
    v_quantiles = quantile_function(qs, v_cumweights, v_values)
    qs = np.pad(qs, [(1, 0), (0, 0)])
    delta = qs[1:, :] - qs[:-1, :]
    diff_quantiles = np.abs(u_quantiles - v_quantiles)
    return np.sum(delta * np.power(diff_quantiles, p), axis=0)


def sliced_wasserstein_distance(X_s, X_t, a, b, n_projections, p, rng):
    d = X_s.shape[1]
    projections = get_random_projections(d, n_projections, rng)
    X_s_projections = X_s @ projections
    X_t_projections = X_t @ projections
    a_full = np.repeat(a[:, None], n_projections, axis=1)
    b_full = np.repeat(b[:, None], n_projections, axis=1)
    projected_emd = wasserstein_1d(X_s_projections, X_t_projections, a_full, b_full, p=p)
    return (np.sum(projected_emd) / n_projections) ** (1.0 / p)


async def wasserstein_analyse(genotypes1, genotypes2, trials, slices):
    num_samples1 = genotypes1.shape[0]
    num_samples2 = genotypes2.shape[0]
    a = np.full(num_samples1, 1 / num_samples1)
    b = np.full(num_samples2, 1 / num_samples2)
    rng = np.random.default_rng()
    distances = []
    async for _ in accuracy_metric_progress(
        range(trials), "Computing sliced Wasserstein distance", "accuracy trial"
    ):
        distances.append(
            sliced_wasserstein_distance(genotypes1, genotypes2, a, b, slices, 2, rng)
        )
    distance_mean = np.mean(distances)
    distance_std_dev = np.std(distances, ddof=1) if trials > 1 else 0.0
    return distance_mean, distance_std_dev


def format_with_uncertainty(val, uncertainty):
    if uncertainty == 0:
        return str(val)
    else:
        decimal_places = math.ceil(-math.log10(uncertainty))
        first_digit = int(uncertainty * (10**decimal_places))
        if first_digit == 1:
            decimal_places += 1
        rounded_uncertainty = round(uncertainty, decimal_places)
        format_decimal_places = max(decimal_places, 0)
        return f"{round(val, decimal_places):.{format_decimal_places}f}±{rounded_uncertainty:.{format_decimal_places}f}"


async def Accuracy_metric_exec(
    input_vcf_file,
    generated_vcf_file,
    trials=ACCURACY_TRIALS_DEFAULT,
    slices=ACCURACY_SLICES_DEFAULT,
):
    genotypes1 = await parse_vcf_to_genotype_matrix(input_vcf_file)
    genotypes2 = await parse_vcf_to_genotype_matrix(generated_vcf_file)
    assert genotypes1.shape[1] == genotypes2.shape[1], (
        "Input and generated VCFs should have the same number of SNPs"
    )
    mean, std_dev = await wasserstein_analyse(genotypes1, genotypes2, trials, slices)
    result = format_with_uncertainty(1 - mean, std_dev)
    print(f"RESULT:{result}")
    await sleep(0)
    return result

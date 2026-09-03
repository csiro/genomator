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
# This mirrors assets/accuracy_metric.py, but reimplements POT's
# sliced_wasserstein_distance/wasserstein_1d in plain numpy, since POT ships
# compiled extensions with no WASM/Emscripten build.
#
# The rest of the file is shaped by Pyodide running single threaded, on the
# browser's UI thread, with a much tighter memory budget than native CPython:
#
#   * Genotypes are read by vcf_parsing, which goes straight at the raw VCF
#     bytes with numpy rather than using vcfpy.  vcfpy allocates a Python object
#     per record and per call, costing over five minutes for a 780 sample exome
#     VCF here.
#   * Random projections are applied one SNP block at a time in float32, so we
#     never build the (num_snps x slices) float64 projection matrix or a
#     float64 copy of the genotypes (~500MB each at exome scale).  Small blocks
#     also keep the working set in cache and let the event loop run part way
#     through a trial, so the tab stays responsive.
#   * Genotype matrices are mostly reference alleles, so when scipy is present
#     the blocks are held as sparse matrices, which makes the projections
#     roughly ten times cheaper.  Without scipy the dense path is used instead
#     and the results are unchanged.

from asyncio import sleep
import math

import numpy as np

from vcf_parsing import parse_vcf_to_genotype_matrix

try:
    from scipy import sparse
    print("scipy available: accuracy metric will use sparse genotype blocks")
except ImportError:  # scipy is optional; the dense path gives the same answers
    sparse = None
    print("scipy not available: accuracy metric will use dense genotype blocks")

ACCURACY_TRIALS_DEFAULT = 50
ACCURACY_SLICES_DEFAULT = 300

# SNPs per block when applying random projections.  Blocks this small keep the
# gaussian block and the float32 genotype copy in cache, which measurably beats
# projecting the whole SNP axis in one multiply under WASM.
PROJECTION_BLOCK_SNPS = 256

# Only hold genotypes sparsely while they are mostly zeros; past this a sparse
# copy costs both more time and more memory than the dense matrix.
SPARSE_DENSITY_LIMIT = 0.5


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


def build_projection_blocks(genotypes):
    """Split genotypes along the SNP axis into blocks ready to be projected."""
    num_snps = genotypes.shape[1]
    blocks = [
        genotypes[:, start : start + PROJECTION_BLOCK_SNPS]
        for start in range(0, num_snps, PROJECTION_BLOCK_SNPS)
    ]
    if (
        sparse is not None
        and genotypes.size > 0
        and np.count_nonzero(genotypes) <= SPARSE_DENSITY_LIMIT * genotypes.size
    ):
        return [sparse.csr_matrix(block, dtype=np.float32) for block in blocks]
    return blocks


def project_block(block, gaussian):
    if sparse is not None and sparse.issparse(block):
        return block @ gaussian
    return block.astype(np.float32) @ gaussian


async def project_onto_unit_directions(blocks1, blocks2, shape1, shape2, n_projections, rng):
    """Project both genotype sets onto the same random unit length directions.

    Identical to drawing a (num_snps, n_projections) gaussian matrix, scaling
    each of its columns to unit length and multiplying, except that the SNP
    axis is walked one block at a time.  Scaling each column by its length is
    deferred to the end, which is exact: every column of the projected result
    is linear in that one gaussian column.
    """
    projected1 = np.zeros((shape1, n_projections))
    projected2 = np.zeros((shape2, n_projections))
    sum_squares = np.zeros(n_projections)
    for block_index, (block1, block2) in enumerate(zip(blocks1, blocks2)):
        gaussian = rng.standard_normal(
            (block1.shape[1], n_projections), dtype=np.float32
        )
        sum_squares += np.einsum("ij,ij->j", gaussian, gaussian, dtype=np.float64)
        projected1 += project_block(block1, gaussian)
        projected2 += project_block(block2, gaussian)
        if block_index & 63 == 0:
            await sleep(0)
    lengths = np.sqrt(sum_squares)
    return projected1 / lengths, projected2 / lengths


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


async def sliced_wasserstein_distance(blocks1, blocks2, a, b, n_projections, p, rng):
    X_s_projections, X_t_projections = await project_onto_unit_directions(
        blocks1, blocks2, a.shape[0], b.shape[0], n_projections, rng
    )
    a_full = np.repeat(a[:, None], n_projections, axis=1)
    b_full = np.repeat(b[:, None], n_projections, axis=1)
    projected_emd = wasserstein_1d(X_s_projections, X_t_projections, a_full, b_full, p=p)
    return (np.sum(projected_emd) / n_projections) ** (1.0 / p)


async def wasserstein_analyse(genotypes1, genotypes2, trials, slices):
    num_samples1 = genotypes1.shape[0]
    num_samples2 = genotypes2.shape[0]
    a = np.full(num_samples1, 1 / num_samples1)
    b = np.full(num_samples2, 1 / num_samples2)
    blocks1 = build_projection_blocks(genotypes1)
    blocks2 = build_projection_blocks(genotypes2)
    rng = np.random.default_rng()
    distances = []
    async for _ in accuracy_metric_progress(
        range(trials), "Computing sliced Wasserstein distance", "accuracy trial"
    ):
        distances.append(
            await sliced_wasserstein_distance(blocks1, blocks2, a, b, slices, 2, rng)
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
    print(f"loading VCF file: {input_vcf_file}")
    genotypes1 = await parse_vcf_to_genotype_matrix(input_vcf_file)
    print(f"loading VCF file: {generated_vcf_file}")
    genotypes2 = await parse_vcf_to_genotype_matrix(generated_vcf_file)
    assert genotypes1.shape[1] == genotypes2.shape[1], (
        "Input and generated VCFs should have the same number of SNPs"
    )
    print("finished loading")
    mean, std_dev = await wasserstein_analyse(genotypes1, genotypes2, trials, slices)
    result = format_with_uncertainty(1 - mean, std_dev)
    print(f"RESULT:{result}")
    await sleep(0)
    return result


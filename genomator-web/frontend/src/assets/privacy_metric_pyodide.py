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

# In-browser (Pyodide) privacy metric evaluation.
#
# This mirrors assets/privacy_metric.py, but reads genotypes through
# vcf_parsing instead of cyvcf2, since cyvcf2 has no WASM/Emscripten build
# available.

from asyncio import sleep
from collections import Counter
from functools import reduce
import math

import numpy as np

from vcf_parsing import parse_vcf_to_record_columns

PRIVACY_TRIALS_DEFAULT = 100000
PRIVACY_DEGREE_DEFAULT = 4

rng = np.random.default_rng()


async def privacy_metric_progress(itera, start_message, label, skip=0):
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


# count how many unique SNP combinations from a appear in b
def count_uniques_from_a_in_b(a, set_b):
    uniques = set(combo for combo, count in Counter(a).items() if count == 1)
    if not uniques:
        return 0, 0
    return len(uniques), len(uniques & set_b)


def multiply_size(previous, collection):
    return previous * len(collection)


def count_absent_from_a_in_b(a, set_b):
    all_possible = reduce(multiply_size, (set(alleles) for alleles in zip(*a)), 1)
    set_a = set(a)
    absent = all_possible - len(set_a)
    return absent, len(set_b - set_a)


async def get_unique_reproduction_rate(input_records, generated_records, degree, trials):
    num_snps = len(input_records)
    assert len(generated_records) == num_snps, (
        "Input and generated VCFs should have the same number of SNPs"
    )
    assert degree <= num_snps, (
        f"Cannot test {degree}-SNP combinations when VCF only contains {num_snps} SNPs"
    )
    total_absent = 0
    total_absent_represented = 0
    total_uniques = 0
    total_reproduced = 0
    skip = max(0, (trials // 300).bit_length())
    async for _ in privacy_metric_progress(
        range(trials), f"Sampling SNP combinations for unique {degree}-SNP combinations",
        "privacy trial", skip
    ):
        snp_indices = rng.choice(num_snps, degree, replace=False, shuffle=False)
        input_sample_combinations = list(zip(*[input_records[i] for i in snp_indices]))
        generated_combinations_set = set(
            zip(*[generated_records[i] for i in snp_indices])
        )
        input_uniques, reproduced_uniques = count_uniques_from_a_in_b(
            input_sample_combinations, generated_combinations_set
        )
        absent, absent_represented = count_absent_from_a_in_b(
            input_sample_combinations, generated_combinations_set
        )
        total_absent += absent
        total_absent_represented += absent_represented
        total_uniques += input_uniques
        total_reproduced += reproduced_uniques
    if total_uniques == 0:
        print(f"Input data contains no unique {degree}-SNP combinations")
        return 0, 0
    absent_represented_rate = (
        total_absent_represented / total_absent if total_absent > 0 else 0
    )
    return total_reproduced / total_uniques, absent_represented_rate


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


async def Privacy_metric_exec(
    input_vcf_file,
    generated_vcf_file,
    trials=PRIVACY_TRIALS_DEFAULT,
    degree=PRIVACY_DEGREE_DEFAULT,
):
    print(f"loading VCF file: {input_vcf_file}")
    input_records = await parse_vcf_to_record_columns(input_vcf_file)
    print(f"loading VCF file: {generated_vcf_file}")
    generated_records = await parse_vcf_to_record_columns(generated_vcf_file)
    unique_reproduction_rate, absent_represented_rate = await get_unique_reproduction_rate(
        input_records, generated_records, degree, trials
    )
    unique_reproduction_rate_variance = (
        unique_reproduction_rate * (1 - unique_reproduction_rate) / (trials + 1)
    )
    absent_represented_rate_variance = (
        absent_represented_rate * (1 - absent_represented_rate) / (trials + 1)
    )
    advantage = unique_reproduction_rate - absent_represented_rate
    advantage_std_dev = (
        unique_reproduction_rate_variance + absent_represented_rate_variance
    ) ** 0.5
    result = format_with_uncertainty(1 - advantage, advantage_std_dev)
    print(f"RESULT:{result}")
    await sleep(0)
    return result

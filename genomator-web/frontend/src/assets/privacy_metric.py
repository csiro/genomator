#!/usr/bin/env python3
from collections import Counter
import itertools
import sys

import click
import cyvcf2
import numpy as np
from tqdm import tqdm

TRIALS_DEFAULT = 100000
DEGREE_DEFAULT = 4


rng = np.random.default_rng()


def log(message):
    print(message, file=sys.stderr)


def get_unique_reproduction_rate(input_records, generated_records, degree, trials):
    num_snps = len(input_records)
    assert (
        len(generated_records) == num_snps
    ), "Input and generated VCFs should have the same number of SNPs"
    assert (
        degree <= num_snps
    ), f"Cannot test {degree}-SNP combinations when VCF only contains {num_snps} SNPs"
    total_uniques = 0
    total_reproduced = 0
    log(f"Sampling SNP combinations for unique {degree}-SNP combinations")
    for _ in tqdm(range(trials)):
        snp_indices = rng.choice(num_snps, degree, replace=False, shuffle=False)
        input_sample_combinations = zip(*[input_records[i] for i in snp_indices])
        generated_sample_combinations = zip(
            *[generated_records[i] for i in snp_indices]
        )
        input_uniques, reproduced_uniques = count_uniques_from_a_in_b(
            input_sample_combinations, generated_sample_combinations
        )
        total_uniques += input_uniques
        total_reproduced += reproduced_uniques
    if total_uniques == 0:
        log("Input data contains no unique {degree}-SNP combinations")
        return 0
    return total_reproduced / total_uniques


def parse_vcf_to_record_strings(vcf_file):
    log(f"loading VCF file: {vcf_file}")
    reader = cyvcf2.VCF(vcf_file)
    try:
        first_line = next(reader)
    except StopIteration:
        log("VCF file contains no records")
        return []
    try:
        ploidy = len(first_line.genotypes[0]) - 1
    except (IndexError, TypeError):
        log("VCF records do not contain genotypes")
        return []
    records = [
        bytes(
            haplotype
            for genotype in record.genotypes
            for haplotype in genotype[:ploidy]
        )
        for record in tqdm(itertools.chain([first_line], reader))
    ]
    return records


def load_file(filename):
    try:
        return parse_vcf_to_record_strings(filename)
    except Exception as e:
        log(f"Failed to load file {filename}")
        raise e


# count how many unique SNP combinations from a appear in b
def count_uniques_from_a_in_b(a, b):
    uniques = set(combo for combo, count in Counter(a).items() if count == 1)
    if not uniques:
        return 0, 0
    return len(uniques), len(uniques & set(b))


def score_privacy(
    input_vcf_file, generated_vcf_file, trials=TRIALS_DEFAULT, degree=DEGREE_DEFAULT
) -> float:
    input_records = load_file(input_vcf_file)
    generated_records = load_file(generated_vcf_file)
    unique_reproduction_rate = get_unique_reproduction_rate(
        input_records, generated_records, degree, trials
    )
    return 1 - unique_reproduction_rate


@click.command()
@click.option("--input", "-i", "input_vcf_file", required=True, type=click.types.Path())
@click.option(
    "--generated", "-g", "generated_vcf_file", required=True, type=click.types.Path()
)
@click.option("--trials", "-t", type=click.types.INT, default=TRIALS_DEFAULT)
@click.option("--degree", "-d", type=click.types.INT, default=DEGREE_DEFAULT)
def run(input_vcf_file, generated_vcf_file, trials, degree):
    print(score_privacy(input_vcf_file, generated_vcf_file, trials, degree))


if __name__ == "__main__":
    run()

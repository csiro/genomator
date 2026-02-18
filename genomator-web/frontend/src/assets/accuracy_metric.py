#!/usr/bin/env python3
import itertools
import math
import sys

import click
import cyvcf2
import numpy as np
import ot
from tqdm import tqdm

TRIALS_DEFAULT = 50
SLICES_DEFAULT = 300


def log(message):
    print(message, file=sys.stderr)


def parse_vcf_to_genomes_array(vcf_file):
    log(f"loading VCF file: {vcf_file}")
    reader = cyvcf2.VCF(vcf_file)
    try:
        first_line = next(reader)
    except StopIteration:
        log("VCF file contains no records")
        return np.array([])
    try:
        num_samples = len(first_line.genotypes)
    except TypeError:
        log("VCF records do not contain genotypes")
        return np.array([])
    all_genotypes = bytes(
        genotype[haplotype]
        for record in tqdm(itertools.chain([first_line], reader))
        for haplotype in range(len(record.genotypes[0]) - 1)
        for genotype in record.genotypes
    )
    genotypes_array = (
        np.frombuffer(all_genotypes, dtype=np.uint8).reshape(-1, num_samples).T
    )
    return genotypes_array


def load_file(filename):
    try:
        return parse_vcf_to_genomes_array(filename)
    except Exception as e:
        log(f"Failed to load file {filename}")
        raise e


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


def wasserstein_analyse(input_vcf_file1, input_vcf_file2, trials, slices):
    genotypes1 = load_file(input_vcf_file1)
    num_samples1 = genotypes1.shape[0]
    genotypes2 = load_file(input_vcf_file2)
    num_samples2 = genotypes2.shape[0]

    genotypes1_balance = np.full(num_samples1, 1 / num_samples1)
    genotypes2_balance = np.full(num_samples2, 1 / num_samples2)

    distances = [
        ot.sliced_wasserstein_distance(
            genotypes1, genotypes2, genotypes1_balance, genotypes2_balance, slices
        )
        for _ in tqdm(range(trials))
    ]
    distance_mean = np.mean(distances)
    distance_std_dev = np.std(distances, ddof=1)
    return distance_mean, distance_std_dev


def score_accuracy(
    input_vcf_file, generated_vcf_file, trials=TRIALS_DEFAULT, slices=SLICES_DEFAULT
):
    mean, std_dev = wasserstein_analyse(
        input_vcf_file, generated_vcf_file, trials, slices
    )
    return format_with_uncertainty(1 - mean, std_dev)


@click.command()
@click.option("--input", "-i", "input_vcf_file", required=True, type=click.types.Path())
@click.option(
    "--generated", "-g", "generated_vcf_file", required=True, type=click.types.Path()
)
@click.option("--trials", "-t", type=click.types.INT, default=TRIALS_DEFAULT)
@click.option("--slices", type=click.INT, default=SLICES_DEFAULT)
def run(input_vcf_file, generated_vcf_file, trials, slices):
    print(score_accuracy(input_vcf_file, generated_vcf_file, trials, slices))


if __name__ == "__main__":
    run()

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

from random import randint, random, sample, shuffle, choice
from asyncio import sleep, run
from collections import defaultdict
from operator import itemgetter
from copy import deepcopy as copy
from itertools import islice
from math import comb
import time

from pysat.solvers import Solver
import vcfpy

from vcf_parsing import open_vcf, parse_vcf_to_sample_strings
import click
import numpy as np

MAX_TUNING_SAMPLE_SIZE = 200
TARGET_SUCCESS_RATE = 0.05
LOOSENESS_DP = 2
LOOSENESS_SHORT_CIRCUIT_PVALUE = 0.05
silent = False

async def progress(itera, start_message, label, skip=0):
    itera = list(itera)
    if not silent:
        print(start_message)
        await sleep(0)
        l = len(itera)
    for ii,i in enumerate(itera):
        if not silent and (ii&((2**skip)-1)==0):
            print(f"{label} {ii}/{l}")
            await sleep(0)
        yield i
    if not silent:
        print(f"{label} {l}/{l}")
        await sleep(0)

async def async_print(*args):
    if not silent:
        print(*args)
    await sleep(0)

# parse_VCF_to_genome_strings(): parse a VCF file into an array of sample data, where
# phased and unphased data get flattened into sequences of bytes objects
async def parse_VCF_to_genome_strings(input_vcf_file, number_of_genomes):
    # Size limits are checked up front, before anything large gets allocated,
    # so a file that would blow the WASM address space is rejected rather than
    # half loaded.  Streaming the count keeps this pass itself cheap.
    version_lines = []
    num_samples = 0
    num_records = 0
    with open_vcf(input_vcf_file) as f:
        for line in f:
            if line.startswith(b"##fileformat="):
                version_lines.append(line.decode().strip())
            if line[0:1] == b"#":
                continue
            if num_records == 0:
                num_samples = len(line.rstrip(b"\r\n").split(b"\t")) - 9
            num_records += 1
    assert len(version_lines) == 1, "VCF file is missing version information, please ensure the file starts with a line like '##fileformat=VCFv4.2'"
    assert version_lines[0] in ["##fileformat=VCFv4.2","##fileformat=VCFv4.3"], "VCF file version not recognised, please ensure the file starts with a line like '##fileformat=VCFv4.2' or '##fileformat=VCFv4.3'"
    assert num_records <= 100_000, "VCF file contains more than 100,000 variants, please reduce the size for processing."
    assert num_records * num_samples <= 10**8, "VCF file contains more than 100 million data points, please reduce the size for processing. WASM address space is limited and this is to prevent memory overflow."
    assert num_records * number_of_genomes <= 10**8, "Output VCF file contains more than 100 million data points, please reduce the size for processing. WASM address space is limited and this is to prevent memory overflow."

    await async_print("Beginning VCF file loading")

    async def progress(num_loaded, total):
        await async_print(f"loaded variants {num_loaded}/{num_records}")

    genomes, ploidy = await parse_vcf_to_sample_strings(
        input_vcf_file, progress=progress, require_uniform_phase=True
    )
    await async_print("Finished VCF file loading")
    return genomes,ploidy

# parse_genome_strings_to_VCF(): output an array of bytes objects of flattened genome sample data
# into a VCF file, with header information and structure reflective of an input VCF file
async def parse_genome_strings_to_VCF(s, input_vcf_file, output_vcf_file, ploidy):
    await async_print("Beginning VCF file output preparation")
    number_of_genomes = len(s)
    number_of_records = len(s[0])//ploidy
    reader = vcfpy.Reader.from_path(input_vcf_file)
    output_header = copy(reader.header)
    output_header.samples = vcfpy.SamplesInfos(["GENERATEDSAMPLE{}".format(i) for i in range(number_of_genomes)])
    writer = vcfpy.Writer.from_path(output_vcf_file, output_header)
    recordset = None
    await async_print("Beginning VCF file output")
    for i,record in enumerate(reader):
        if recordset is None:
            recordset = [copy(record.calls[0]) for genome_number in range(number_of_genomes)]
        record.calls = recordset
        for genome_number in range(number_of_genomes):
            record.calls[genome_number].sample = "GENERATEDSAMPLE{}".format(genome_number)
            genome_fragment = [s[genome_number][i*ploidy+k] for k in range(ploidy)]
            record.calls[genome_number].set_genotype(record.calls[genome_number].gt_phase_char.join([str(ff) for ff in genome_fragment]))
        record.update_calls(record.calls)
        writer.write_record(record)
        if i&31==0:
            await async_print(f"output records {i}/{number_of_records}")
    await async_print(f"output records {number_of_records}/{number_of_records}")
    await async_print("VCF file output complete")



# get_approximate_distance_between_data(): sample approximate the hamming distances between different all the different genomes
async def get_approximate_distance_between_data_binary(reference_genomes, difference_samples):
    await async_print("preparing for clustering distance calculation process...")
    length = len(reference_genomes)
    difference_samples = min(len(reference_genomes[0]),difference_samples)
    distances = [[0]*length for j in range(length)]
    indices = sample(list(range(len(reference_genomes[0]))), difference_samples)
    reference_genomes_np = [np.array(bytearray([r[i] for i in indices]),dtype=np.int8) for r in reference_genomes]
    async for i in progress(range(len(reference_genomes_np)),"Clustering data points","cluster distance iteration",4):
        for j in range(i+1,len(reference_genomes_np)):
            distances[i][j] = np.linalg.norm(reference_genomes_np[i]-reference_genomes_np[j])**2
            distances[j][i] = distances[i][j]
    return distances

# custer_setup(): break the data into non-intersecting clusters of similar points, equally sized and approximately of size <size>,
# returning the indices of which data belongs in these clusters.
# repeating this process <custering> times to get a range of overlapping clusters of similar data points so that all points are equally
# sampled across the clusters
async def cluster_setup_binary(reference_genomes, size, clustering=30,difference_samples=10000):
    await async_print("preparing for clustering process...")
    length = len(reference_genomes)
    distances = await get_approximate_distance_between_data_binary(reference_genomes, difference_samples)
    sorted_distances = [sorted(list(enumerate(d)), key=itemgetter(1)) for d in distances]
    sorted_distance_indices = [[i for i,d in dd] for dd in sorted_distances]
    partitions = length // size
    refactor_size = length // partitions if partitions!= 0 else length
    undershoot = length - refactor_size*partitions
    index_sets = []
    async for re_run in progress(range(clustering),"breaking into clusters","cluster re run"):
        used_set = []
        last_new_set = None
        for i in range(partitions-1):
            new_set = []
            focus = last_new_set[-1] if last_new_set is not None else choice(list(range(length)))
            ii = 0
            while len(new_set)< (refactor_size + (i<undershoot)):
                if sorted_distance_indices[focus][ii] not in used_set:
                    used_set.append(sorted_distance_indices[focus][ii])
                    new_set.append(sorted_distance_indices[focus][ii])
                ii += 1
            index_sets.append(new_set)
            last_new_set = new_set
        index_sets.append(list(set(range(length)).difference(set(used_set))))
    return index_sets

# convert_to_binary(): convert an array of truth values into an integer
convert_to_binary = lambda x:sum([1<<i for i,xx in enumerate(x) if xx])

# wrap_values(): return i-th integer in a sawtooth function of integers with absolute value N
wrap_values = lambda x,N: (x+N)%(2*N+1)-N

# generate_genomes(): generate <number_of_genomes> synthetic data from <reference_genomes>
# employing a clustering the <reference_genomes> into similar points of size <sample_group_size>
# The process repeatedly chooses a cluster randomly, and the SAT solver to ensures that any pair of properties (optionally but for some fraction <looseness>) that the cluster posesses (at a rate determined by <exception_space>) must also be true of the synthetic data point generated
# <looseness> is a simple probability filter on what pairs of properties are constraining on the synthetic data output
# <exception_space> is by default zero, where it only eliminates pairs of qualities not present in the source data from appearing in the output, or it can be positive (1,2,3) where it eliminates pairs of properties appearing a number of times or less in the input from appearing in the output; or it can be negative (-1,-1.5,-4 etc) for softer effect (attenuating properties that appear less than a random number less than its positive value)
async def generate_genomes(reference_genomes, sample_group_size, number_of_genomes, exception_space, looseness=None):
    genome_solutions = []
    cluster_info = await cluster_setup_binary(reference_genomes, sample_group_size)
    if looseness is None:
        automatic_looseness = True
        tuning = True
        looseness = 0
        await async_print(f"Trying L={looseness}")
    else:
        automatic_looseness = False
        tuning = False

    # repeat till we generate <number_of_genomes> synthetic data points
    await async_print("Beginning Synthetic Data generation main loop.")
    successes = 0
    low_looseness = (0,  0)
    high_looseness = (1, 1)
    attempts = 0
    while len(genome_solutions) < number_of_genomes:
        if not tuning:
            await async_print(f"Completed {len(genome_solutions)}/{number_of_genomes}")
        # select a cluster and shuffle
        genomes = [reference_genomes[ii] for ii in choice(cluster_info)]
        shuffle(genomes)
        queries = set()
        clauses = set()
        query_mapping = defaultdict(dict)

        initial_t = time.time()
        # for each unique data column
        for t in set(map(tuple, zip(*genomes))):
            values = sorted(list(set(t))) # get the list of unique ascending values in the column
            presence_list = [tuple([tt==value for tt in t]) for value in values]
            absence_list  = [tuple([tt!=value for tt in t]) for value in values]
            # collect novel T/F array
            queries.update(presence_list)
            queries.update(absence_list)
            # collect information for reverse translation
            query_mapping[t] = {q:values[i].to_bytes(1,"big") for i,q in enumerate(absence_list)}
            clauses.add(frozenset(absence_list))
        await async_print(f'collected queries in {time.time()-initial_t}')

        # collect T/F arrays, assign unique variables to each (or negated variables for opposite arrays)
        queries = sorted(list(queries))
        variables = len(queries)//2
        index = {v:wrap_values(i+1,variables) for i,v in enumerate(queries)}

        # convert T/F arrays to big-integers and index of thoes integers to variables
        query_mapping = {t:{index[a]:b for a,b in q.items()} for t,q in query_mapping.items()}
        binary_queries = [convert_to_binary(q) for q in queries]
        query_index_to_variable = [wrap_values(i+1,variables) for i in range(len(binary_queries))]

        # instantiate a SAT solver, and add all relevant constraints
        solver = Solver('minicard')
        mask = convert_to_binary([True]*len(queries[0]))
        initial_t = time.time()
        for i,k1 in enumerate(binary_queries):
            for j in range(i,len(binary_queries)):
                e_space = int(random()*(exception_space+1)) if (exception_space >= 0) else abs(exception_space)
                if (((k1|binary_queries[j])^mask).bit_count() <= e_space) and (random()>=looseness):
                    solver.add_clause([ -query_index_to_variable[i],-query_index_to_variable[j] ])
        for c in clauses: solver.add_clause([index[cc] for cc in c])
        await async_print(f'added clauses in {time.time()-initial_t}')

        # randomise the SAT solver, solve the SAT problem and extract the solution, deleting the SAT solver instance
        initial_t = time.time()
        solver.set_phases([(i+1) * (2*randint(0,1)-1) for i in range(variables)])
        solved = solver.solve()
        if tuning:
            attempts += 1
            successes += 1 if solved else 0
            chance_given_target = (TARGET_SUCCESS_RATE**successes)*((1-TARGET_SUCCESS_RATE)**(attempts-successes))*comb(attempts,successes)
            if chance_given_target <= LOOSENESS_SHORT_CIRCUIT_PVALUE or attempts >= MAX_TUNING_SAMPLE_SIZE:
                success_rate = round(successes/attempts, LOOSENESS_DP+1)
                if success_rate > TARGET_SUCCESS_RATE:
                    await async_print(f'L={looseness} is too high, found success rate {success_rate} ({successes}/{attempts})')
                    high_looseness = (looseness, success_rate)
                elif success_rate < TARGET_SUCCESS_RATE:
                    await async_print(f'L={looseness} is too low, found success rate {success_rate} ({successes}/{attempts})')
                    low_looseness = (looseness, success_rate)
                else:
                    await async_print(f'L={looseness} is good, found success rate {success_rate} ({successes}/{attempts})')
                    tuning = False
                attempts = 0
                successes = 0
                if round(high_looseness[0] - low_looseness[0], LOOSENESS_DP) <= 10**(-LOOSENESS_DP):
                    looseness = low_looseness[0] if low_looseness[1] and (TARGET_SUCCESS_RATE - low_looseness[1] <= high_looseness[1] - TARGET_SUCCESS_RATE) else high_looseness[0] 
                    tuning = False
                if tuning:
                    looseness = round((low_looseness[0] + high_looseness[0])/2, LOOSENESS_DP)
                    await async_print(f"Trying L={looseness}")
                else:
                    await async_print(f"Finished tuning, setting L={looseness}")
            continue
        if not solved:
            await async_print('SAT problem insoluble, if this repeats too many times without making progress please loosen parameters to make problem tractable.')
            continue
        solution = solver.get_model()
        solver.delete()
        await async_print(f'SAT solving complete in {time.time()-initial_t}')

        # parse the output of the SAT solver back into sensible output data
        initial_t = time.time()
        genome_solutions.append(b"".join([[b for a,b in query_mapping[z].items() if a in set(solution)][0] for z in map(tuple, zip(*genomes)) ]))
        await async_print(f'processed output in {time.time()-initial_t}')
    await async_print(f"Completed {len(genome_solutions)}/{number_of_genomes}")
    await async_print('finished Synthetic Data generation loop')
    return genome_solutions, looseness

# Genomator_exec(): from an <input_vcf_file> generate <number_of_genomes> synthetic data and export to <output_vcf_file>
# the process involving clustering the <input_vcf_file> data into clusters of size <sample_group_size>
# and <exception_space> and <looseness> parameters informing the process
async def Genomator_exec(input_vcf_file, output_vcf_file, number_of_genomes, exception_space=0, sample_group_size=10, looseness=None):
    await async_print('Beginning Genomator Genomic generation')
    genomes, ploidy = await parse_VCF_to_genome_strings(input_vcf_file, number_of_genomes)
    s, looseness = await generate_genomes(genomes, sample_group_size, number_of_genomes, exception_space, looseness)
    await parse_genome_strings_to_VCF(s, input_vcf_file, output_vcf_file, ploidy)
    print(f"Finished Genomator Genomic generation with N={sample_group_size}, L={looseness}, Z={exception_space}")

@click.command()
@click.argument('input_vcf_file', type=click.types.Path())
@click.argument('output_vcf_file', type=click.types.Path())
@click.argument('number_of_genomes', type=click.INT, default=1)
@click.option('--exception_space', type=click.FLOAT, default=0)
@click.option('--sample_group_size', type=click.INT, default=10)
@click.option('--looseness', type=click.FLOAT, default=None)
def Genomator_mini(input_vcf_file, output_vcf_file, number_of_genomes, exception_space, sample_group_size, looseness):
    run(Genomator_exec(input_vcf_file, output_vcf_file, number_of_genomes, exception_space, sample_group_size, looseness))

if __name__ == '__main__':
	Genomator_mini()

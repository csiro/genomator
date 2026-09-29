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

# Drop-in replacement for experiment_tools.vcf_loading's
# parse_VCF_to_genome_strings/parse_genome_strings_to_VCF, used by the ported
# baseline generator scripts (MARK_run.py, CRBM_run.py, WGAN_run.py,
# RBM_run.py). The original loader reads through cyvcf2, a compiled
# C-extension that's an awkward extra install for a script meant to just run
# on someone's laptop; vcf_parsing.parse_vcf_to_sample_strings already returns
# the exact same (list of per-sample genome bytes, ploidy) shape using pure
# Python + numpy, so loading goes through that instead. Writing already only
# needed vcfpy, so parse_genome_strings_to_VCF is copied through unchanged.

import asyncio
from copy import deepcopy as copy

import vcfpy

from vcf_parsing import parse_vcf_to_sample_strings


def parse_VCF_to_genome_strings(input_vcf_file, snp_load_limit=None, silent=False):
    """Genotypes as (list of per-sample genome bytes, ploidy).

    snp_load_limit truncates each genome to its first snp_load_limit*ploidy
    alleles; kept for signature compatibility with the original loader, but
    none of the ported generator scripts actually pass it.
    """
    samples, ploidy = asyncio.run(parse_vcf_to_sample_strings(input_vcf_file))
    if snp_load_limit is not None and ploidy > 0:
        cutoff = snp_load_limit * ploidy
        samples = [s[:cutoff] for s in samples]
    return samples, ploidy


def parse_genome_strings_to_VCF(s, input_vcf_file, output_vcf_file, ploidy, del_info_field=False, silent=False):
    """Write genome bytes (as produced by a generator) out as a VCF.

    Copied from experiment/experiment_tools/experiment_tools/vcf_loading.py
    unchanged: it only ever used vcfpy, reading input_vcf_file purely as a
    header template to copy the record/contig structure from.
    """
    number_of_genomes = len(s)
    reader = vcfpy.Reader.from_path(input_vcf_file)
    output_header = copy(reader.header)
    output_header.samples = vcfpy.SamplesInfos(["GENERATEDSAMPLE{}".format(i) for i in range(number_of_genomes)])
    writer = vcfpy.Writer.from_path(output_vcf_file, output_header)
    recordset = None
    for i, record in enumerate(reader):
        if recordset is None:
            recordset = [copy(record.calls[0]) for _ in range(number_of_genomes)]
        record.calls = recordset
        if del_info_field:
            record.INFO.clear()
        for genome_number in range(number_of_genomes):
            record.calls[genome_number].sample = "GENERATEDSAMPLE{}".format(genome_number)
            genome_fragment = [s[genome_number][i * ploidy + k] for k in range(ploidy)]
            record.calls[genome_number].set_genotype(
                record.calls[genome_number].gt_phase_char.join([str(ff) for ff in genome_fragment])
            )
        record.update_calls(record.calls)
        writer.write_record(record)
    reader.close()
    writer.close()

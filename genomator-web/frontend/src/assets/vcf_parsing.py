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

# Shared VCF genotype parsing for the in-browser (Pyodide) scripts.
#
# Every Pyodide entry point wants the same thing out of a VCF: the allele index
# of each haplotype of each sample, for each record.  They only differ in the
# shape they want it in, so the parsing happens once in
# parse_vcf_haplotype_columns() and the parse_vcf_to_* wrappers reshape it:
#
#   parse_vcf_to_genotype_matrix   a (num_samples, num_records * ploidy) array
#                                  of allele indices  (accuracy, in-depth privacy)
#   parse_vcf_to_record_columns    one bytes object per record per haplotype,
#                                  each num_samples long  (privacy)
#   parse_vcf_to_sample_strings    one bytes object per sample, each
#                                  num_records * ploidy long  (genomator_mini)
#
# vcfpy is deliberately not used here.  It builds a Python object per record and
# per call, which costs over five minutes for a 780 sample exome VCF under
# Pyodide, whereas reading the genotype fields straight out of the raw bytes
# with numpy does the same job in under two seconds.  vcfpy remains the right
# tool for *writing* VCFs, so the callers that emit VCFs still import it.

from asyncio import sleep
import gzip

import numpy as np

# Records between progress callbacks.  Parsing is fast enough that reporting
# more often costs more than it tells the user.
PROGRESS_INTERVAL_RECORDS = 4096

# Byte values used by the fixed width genotype fast path ("0/0", "0|1", ...).
_TAB = ord("\t")
_DOT = ord(".")
_ZERO = ord("0")
_NINE = ord("9")
_SLASH = ord("/")
_PIPE = ord("|")


async def print_progress(num_loaded, num_records):
    """Default progress hook, matching what the metric scripts have always printed."""
    if num_records is None:
        print(f"loaded variants {num_loaded}")
    else:
        print(f"loaded variants {num_loaded}/{num_records}")
    await sleep(0)


def open_vcf(vcf_file):
    """Open a VCF as raw bytes, transparently decompressing gzipped input.

    Sniffs the gzip magic number rather than trusting the file name, since the
    upload form only accepts a .vcf extension.  BGZF (what bgzip and htslib
    write) is a sequence of gzip members, which gzip.open reads as one stream.
    """
    handle = open(vcf_file, "rb")
    if handle.read(2) == b"\x1f\x8b":
        handle.close()
        return gzip.open(vcf_file, "rb")
    handle.seek(0)
    return handle


def parse_fixed_width_calls(call_block, num_samples):
    """Vectorised parse of a "0/0\tor 0|1\t..." block of diploid calls.

    Returns (haplotype columns, whether the record used a single phase
    character), or None if the block is not made purely of single digit diploid
    calls, in which case the caller falls back to the general parser.
    """
    if len(call_block) != 4 * num_samples - 1:
        return None
    raw = np.frombuffer(call_block, dtype=np.uint8)
    separators = raw[1::4]
    if not np.all((separators == _SLASH) | (separators == _PIPE)):
        return None
    if not np.all(raw[3::4] == _TAB):
        return None
    haplotype_columns = [raw[0::4], raw[2::4]]
    for column in haplotype_columns:
        assert not np.any(column == _DOT), "cannot currently work with missing data"
        if np.any((column < _ZERO) | (column > _NINE)):
            return None
    uniform_phase = bool(np.all(separators == separators[0]))
    return [column - _ZERO for column in haplotype_columns], uniform_phase


def parse_calls(call_block, num_samples):
    """General parse of one record's calls, for anything the fast path rejects."""
    fields = call_block.split(b"\t")
    assert len(fields) == num_samples, "VCF record has the wrong number of samples"
    haplotype_columns = None
    separators = set()
    for sample_index, field in enumerate(fields):
        genotype = field.split(b":", 1)[0]
        if b"|" in genotype:
            separators.add(b"|")
        if b"/" in genotype:
            separators.add(b"/")
        alleles = genotype.replace(b"|", b"/").split(b"/")
        if haplotype_columns is None:
            haplotype_columns = [
                np.empty(num_samples, dtype=np.uint8) for _ in alleles
            ]
        assert len(alleles) == len(haplotype_columns), (
            "genome ploidies must be identical"
        )
        for haplotype, allele in enumerate(alleles):
            assert allele != b".", "cannot currently work with missing data"
            haplotype_columns[haplotype][sample_index] = int(allele)
    return haplotype_columns, len(separators) <= 1


async def parse_vcf_haplotype_columns(
    vcf_file, progress=print_progress, require_uniform_phase=False
):
    """Parse a VCF's genotypes into one uint8 column per record per haplotype.

    Returns (columns, num_samples, ploidy, num_records).  Each column holds the
    allele indices of one haplotype across all samples, and the columns run in
    record order, haplotype-major within a record.  progress, if given, is
    awaited every PROGRESS_INTERVAL_RECORDS records with (records so far, None)
    and once at the end with (num_records, num_records).
    """
    num_samples = None
    ploidy = None
    columns = []
    num_records = 0
    with open_vcf(vcf_file) as handle:
        for line in handle:
            if line.startswith(b"#"):
                if line.startswith(b"#CHROM"):
                    num_samples = line.rstrip(b"\r\n").count(b"\t") - 8
                    assert num_samples > 0, "VCF file does not contain any samples"
                continue
            assert num_samples is not None, "VCF file has no #CHROM header line"
            fields = line.rstrip(b"\r\n").split(b"\t", 9)
            assert len(fields) == 10, "VCF record does not contain any calls"
            parsed = None
            if fields[8] == b"GT":
                parsed = parse_fixed_width_calls(fields[9], num_samples)
            if parsed is None:
                parsed = parse_calls(fields[9], num_samples)
            haplotype_columns, uniform_phase = parsed
            if require_uniform_phase:
                assert uniform_phase, (
                    "cannot currently work with mixed phases per vcf row"
                )
            if ploidy is None:
                ploidy = len(haplotype_columns)
            assert len(haplotype_columns) == ploidy, (
                "genome ploidies must be identical"
            )
            columns.extend(haplotype_columns)
            num_records += 1
            if progress is not None and num_records % PROGRESS_INTERVAL_RECORDS == 0:
                await progress(num_records, None)
    assert num_samples is not None, "VCF file has no #CHROM header line"
    if progress is not None:
        await progress(num_records, num_records)
    return columns, num_samples, ploidy, num_records


async def parse_vcf_to_genotype_matrix(vcf_file, progress=print_progress):
    """Genotypes as a (num_samples, num_records * ploidy) array of allele indices."""
    columns, num_samples, _, _ = await parse_vcf_haplotype_columns(vcf_file, progress)
    if not columns:
        return np.zeros((num_samples, 0), dtype=np.uint8)
    return np.array(columns, dtype=np.uint8).T


async def parse_vcf_to_record_columns(vcf_file, progress=print_progress):
    """Genotypes as one num_samples long bytes object per record per haplotype."""
    columns, _, _, _ = await parse_vcf_haplotype_columns(vcf_file, progress)
    return [column.tobytes() for column in columns]


async def parse_vcf_to_sample_strings(
    vcf_file, progress=print_progress, require_uniform_phase=False
):
    """Genotypes as one bytes object per sample, alleles in record order.

    Returns (sample strings, ploidy).
    """
    columns, num_samples, ploidy, _ = await parse_vcf_haplotype_columns(
        vcf_file, progress, require_uniform_phase=require_uniform_phase
    )
    if not columns:
        return [b"" for _ in range(num_samples)], ploidy
    per_sample = np.ascontiguousarray(np.array(columns, dtype=np.uint8).T)
    return [row.tobytes() for row in per_sample], ploidy

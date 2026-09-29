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

# Registry of synthetic-data generators the comparative privacy experiment
# (run_comparative_privacy_experiment.py) can run side by side, replicating
# the original paper's comparison of Genomator against CRBM/WGAN/RBM/Markov
# baselines (experiment/experiment/attribute_experiment*.py), but locally and
# at parameters chosen to actually finish on a laptop.
#
# Every provider's generate(input_vcf, output_vcf, number_of_genomes, **kwargs)
# writes number_of_genomes synthetic samples to output_vcf; is_available()
# returns (True, None) or (False, reason) so the parent script can skip a
# tool cleanly (e.g. when PyTorch isn't installed) instead of crashing the
# whole run. Unrecognised kwargs should be ignored (**_ignored) so the same
# kwargs dict can be handed to every provider uniformly.

import asyncio
import glob
import os
import pickle

import genomator_mini
import MARK_run
from baseline_vcf_io import parse_VCF_to_genome_strings, parse_genome_strings_to_VCF

# N / L / Z presets, matching the Calculate tab's (former) "In-Depth Privacy
# Metric" generation profile buttons and run_indepth_locally.py.
GENOMATOR_PRESETS = {
    "balanced": {"cluster_group_size": 5, "exception_space": 0.5, "looseness": 0.5},
    "high-accuracy": {"cluster_group_size": 5, "exception_space": 0, "looseness": 0},
    "high-privacy": {"cluster_group_size": 10, "exception_space": 1, "looseness": 0.99},
}


def genomator_available():
    return True, None


def genomator_generate(input_vcf, output_vcf, number_of_genomes, preset="balanced", **_ignored):
    values = dict(GENOMATOR_PRESETS[preset])
    asyncio.run(genomator_mini.Genomator_exec(
        input_vcf, output_vcf, number_of_genomes,
        values["exception_space"], values["cluster_group_size"], values["looseness"],
    ))


def markov_available():
    return True, None


def markov_generate(input_vcf, output_vcf, number_of_genomes, markov_window=10, **_ignored):
    s, ploidy = parse_VCF_to_genome_strings(input_vcf)
    ss = MARK_run.main_MARK(s, number_of_genomes, markov_window)
    parse_genome_strings_to_VCF(ss, input_vcf, output_vcf, ploidy)


def _torch_unavailable_reason():
    try:
        import torch  # noqa: F401
    except ImportError:
        return "requires PyTorch (`pip install torch`) - see README for CPU-only install notes"
    return None


# CRBM/WGAN/RBM (ported from experiment/experiment_tools/tools/*_run.py, see
# each file's own header comment) don't write VCF directly despite their
# output_vcf_file parameter name: their fit()/training loop dumps pickled
# genome-string lists at "{output_vcf_file}{epoch}.pickle" checkpoints. The
# two helpers below find the highest-epoch checkpoint and convert it to a
# real VCF, replicating experiment/experiment_tools/tools/pickle_to_vcf.py -
# shared by all three providers since they all follow this same convention.
def _highest_epoch_checkpoint(output_prefix):
    candidates = glob.glob(f"{output_prefix}*.pickle")
    if not candidates:
        raise RuntimeError(
            f"no checkpoint pickle found matching '{output_prefix}*.pickle' - "
            "training may not have reached a dump_output_interval-aligned epoch"
        )

    def epoch_of(path):
        return int(path[len(output_prefix):-len(".pickle")])

    return max(candidates, key=epoch_of)


def _checkpoint_to_vcf(output_prefix, input_vcf, output_vcf, ploidy, truncate_width=None):
    latest = _highest_epoch_checkpoint(output_prefix)
    with open(latest, "rb") as f:
        ss = pickle.load(f)
    if truncate_width is not None:
        ss = [genome[:truncate_width] for genome in ss]
    parse_genome_strings_to_VCF(ss, input_vcf, output_vcf, ploidy)
    for leftover in glob.glob(f"{output_prefix}*.pickle"):
        os.remove(leftover)


# WGAN_run.py's conv architecture hardcodes latent_depth_factor=14 (see that
# file's header comment): its discriminator/generator layers are only
# shape-consistent when Nv (variant_count*ploidy) is EXACTLY
# latent_size*16384 - 1 for some positive integer latent_size - not just
# "large enough". The paper's own comment ("16383 zero padded SNP data")
# confirms zero-padding to the nearest such width was the original authors'
# own workaround for datasets that don't naturally land on one; wgan_generate
# below does the same, padding genome strings with zero bytes before
# training and truncating the generated output back to the real width
# afterwards - I/O plumbing around the fixed architecture, not a change to it.
#
# latent_size also can't be too small: empirically, latent_size=1 crashes
# with "Expected more than 1 spatial element when training" from an
# InstanceNorm1d deep in the discriminator once the repeated stride-2
# downsampling collapses that layer's width to 1; latent_size=2 is the
# smallest value confirmed to work (the paper's own comment says
# latent_depth_factor=14 was tuned for latent_size=4/Nv=65535, but 2 also
# runs fine and is meaningfully cheaper - see wgan_generate's comment on
# batch_size for why per-step cost matters so much here).
_WGAN_WIDTH_MODULUS = 16384  # = 2**14, from WGAN_run.py's fixed latent_depth_factor
_WGAN_MIN_LATENT_SIZE = 2  # smallest latent_size confirmed not to crash InstanceNorm1d


def _wgan_padded_width(actual_width):
    needed_latent = -(-(actual_width + 1) // _WGAN_WIDTH_MODULUS)  # ceil div
    latent_size = max(_WGAN_MIN_LATENT_SIZE, needed_latent)
    return latent_size * _WGAN_WIDTH_MODULUS - 1


# CAVEAT (applies to crbm/wgan/rbm below): the epoch counts here are cut down
# by two to three orders of magnitude from the original paper's HPC-scale
# runs (see each function's comment for specifics) so a comparison finishes
# in minutes on a laptop CPU instead of hours/days on a GPU cluster. That
# means these three generators are far less converged here than in the
# paper - undertrained models can produce noisier or more/less realistic
# output than a fully trained one, which can swing the membership-inference
# stat in either direction. Treat results from this tool as illustrating the
# *comparison methodology* (how Genomator stacks up against these baselines
# on the same footing), not as a reproduction of the paper's published
# numbers. Pass the epoch kwargs below to get closer to paper-scale fidelity.


def crbm_available():
    reason = _torch_unavailable_reason()
    return reason is None, reason


def crbm_generate(
    input_vcf, output_vcf, number_of_genomes,
    ep_max=150, dump_output_interval=None, it_mcmc=20, nh=100, fixnodes=0,
    **_ignored,
):
    # ep_max=150 vs. the paper's default of 20001: CRBM's per-epoch cost is
    # dominated by hardcoded (non-overridable) internals - 50 Gibbs steps and
    # a 1252-wide minibatch inside main_CRBM. Measured ~0.4s/epoch (~60s
    # total) on the 805-SNP/40-sample test VCF with nh=100; a much bigger
    # input will take proportionally longer (roughly linear in
    # variant_count*ploidy), so scale ep_max down for large VCFs if needed.
    #
    # dump_output_interval=None -> ep_max-1. main_CRBM only dumps a
    # checkpoint when self.ep_tot lands in
    # np.arange(1, ep_max+2, dump_output_interval); with the default fq_msr
    # that only ever hits epoch 1 (the barely-trained start), never the
    # final epoch. Setting the interval to ep_max-1 makes that arange
    # exactly [1, ep_max], so the fully-trained epoch actually gets dumped
    # (confirmed empirically - see indepth_local README).
    #
    # fixnodes=0 overrides the original default of 5000. CRBM.Sampling()
    # clamps the first `fixnodes` visible units to their initial random
    # value on every Gibbs step - a partial-conditioning feature from the
    # paper's HPC runs where Nv (variant_count*ploidy) was in the tens of
    # thousands. On our much smaller test VCFs, FixNodes=5000 exceeds Nv, so
    # ALL visible units would stay frozen to random noise for the whole
    # sampling chain - i.e. the "generated" output would just be the initial
    # random Bernoulli noise, not anything the model learned. fixnodes=0
    # disables that clamp entirely.
    import CRBM_run

    s, ploidy = parse_VCF_to_genome_strings(input_vcf)
    if dump_output_interval is None:
        dump_output_interval = max(1, ep_max - 1)
    output_prefix = output_vcf + ".crbm_ckpt"
    CRBM_run.main_CRBM(
        s, number_of_genomes,
        ep_max=ep_max, it_mcmc=it_mcmc, dump_output_interval=dump_output_interval,
        output_vcf_file=output_prefix, Nh=nh, FixNodes=fixnodes,
    )
    _checkpoint_to_vcf(output_prefix, input_vcf, output_vcf, ploidy)


def wgan_available():
    reason = _torch_unavailable_reason()
    return reason is None, reason


def wgan_generate(input_vcf, output_vcf, number_of_genomes, epochs=3, batch_size=4, **_ignored):
    # epochs=3 vs. the paper's default of 10001: each WGAN epoch trains the
    # critic critic_iter=10 times (hardcoded, not exposed) plus the
    # generator once - the heaviest per-epoch cost of the three baselines,
    # made worse by gradient_penalty's double-backward (create_graph=True).
    # That cost is wildly batch-size sensitive: measured ~258s/epoch at
    # batch_size=16 vs. ~13s/epoch at batch_size=4 (both at the padded
    # latent_size=2 width) - so batch_size=4 is the single biggest lever for
    # keeping this runnable on a laptop, well beyond just "smaller is a bit
    # faster". epochs is also cut far more aggressively than CRBM/RBM as a
    # result.
    #
    # dump_output_interval is left at main_WGAN's own default (-1): that
    # dumps exactly one checkpoint, at the final epoch, so there's no
    # equivalent of CRBM's "epoch 1 only" pitfall to route around here.
    import WGAN_run

    s, ploidy = parse_VCF_to_genome_strings(input_vcf)
    actual_width = len(s[0])
    padded_width = _wgan_padded_width(actual_width)
    if padded_width != actual_width:
        pad = bytes(padded_width - actual_width)  # zero bytes; see _wgan_padded_width
        s = [genome + pad for genome in s]

    output_prefix = output_vcf + ".wgan_ckpt"
    WGAN_run.main_WGAN(
        s, number_of_genomes,
        epochs=epochs, batch_size=batch_size, dump_output_interval=-1,
        ploidy=ploidy, output_vcf_file=output_prefix, input_vcf_file=input_vcf,
    )
    truncate_width = actual_width if padded_width != actual_width else None
    _checkpoint_to_vcf(output_prefix, input_vcf, output_vcf, ploidy, truncate_width=truncate_width)


def rbm_available():
    reason = _torch_unavailable_reason()
    return reason is None, reason


def rbm_generate(
    input_vcf, output_vcf, number_of_genomes,
    ep_max=250, dump_output_interval=None, it_mcmc=20, nh=100,
    **_ignored,
):
    # ep_max=250 vs. the paper's default of 2001: same hardcoded-internals
    # situation as CRBM (50 Gibbs steps, 500-wide minibatch inside
    # main_RBM), but RBM has no FixNodes clamp to worry about, so its
    # defaults only need to shrink ep_max/nh, not add an override. Measured
    # ~0.2s/epoch (~50s total) on the 805-SNP/40-sample test VCF with
    # nh=100; scale ep_max down for much larger inputs if needed.
    #
    # dump_output_interval=None -> ep_max-1, for the same reason as
    # crbm_generate: main_RBM's list_save_rbm = arange(1, ep_max+2,
    # dump_output_interval), and only ep_max-1 guarantees the final,
    # fully-trained epoch is among the dumped checkpoints instead of just
    # epoch 1.
    import RBM_run

    s, ploidy = parse_VCF_to_genome_strings(input_vcf)
    if dump_output_interval is None:
        dump_output_interval = max(1, ep_max - 1)
    output_prefix = output_vcf + ".rbm_ckpt"
    RBM_run.main_RBM(
        s, number_of_genomes,
        ep_max=ep_max, it_mcmc=it_mcmc, dump_output_interval=dump_output_interval,
        output_vcf_file=output_prefix, Nh=nh,
    )
    _checkpoint_to_vcf(output_prefix, input_vcf, output_vcf, ploidy)


PROVIDERS = {
    "genomator": {"generate": genomator_generate, "is_available": genomator_available},
    "markov": {"generate": markov_generate, "is_available": markov_available},
    "crbm": {"generate": crbm_generate, "is_available": crbm_available},
    "wgan": {"generate": wgan_generate, "is_available": wgan_available},
    "rbm": {"generate": rbm_generate, "is_available": rbm_available},
}

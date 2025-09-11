#!/usr/bin/env python3
from random import randint, random, sample, shuffle, choice
from asyncio import sleep, run
from operator import itemgetter
from pysat.solvers import Solver
import click
import numpy as np
import csv
import time
import math

silent = True

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

# parse_CSV(): parse an input csv file specifying input synthetic data
# with boolean flags detailing whether the csv has a header row at the top
# and whether it has a supbeader row, with details of the column type
async def parse_CSV(input_csv_file, header, header_types):
    data = None
    await async_print("loading CSV information...")
    with open(input_csv_file,'r') as f:
        data = [[l.strip() for l in line.split(",")] for line in f.readlines()]
        f.seek(0)
        assert len(set([len(d) for d in data]))==1, "CSV contains inconsistent use of delimiter ','"
    ret_header = None
    if header:
        assert len(data)!=0,"CSV needs header line, if header flag set"
        ret_header = data[0]
        data = data[1:]
    ret_types = None
    if header_types:
        assert len(data)!=0,f"CSV needs config line, if config flag set, {header} {header_types}"
        ret_types = data[0]
        data = data[1:]
    return ret_header, ret_types, data

# output_CSV(): parse a list of row tuples into a CSV output file 
# with an optional header and types subheader
async def output_CSV(data, header, types, output_csv_file):
    await async_print("writing CSV information...")
    lines = []
    if header:
        lines.append(",".join([str(a) for a in header]))
    if types:
        lines.append(",".join([str(a) for a in types]))
    for d in data:
        lines.append(",".join([str(a) for a in d]))
    with open(output_csv_file,'w') as f:
        f.write("\n".join(lines))

# get_approximate_distance_between_data(): sample approximate the manhattan/hamming distances between different all the different rows of data
# where categorical/discrete data contribute a distance of 1 if different, otherwise sum of continuous valud differences
async def get_approximate_distance_between_data(reference_data, reference_data_types, difference_samples):
    await async_print("preparing for clustering distance calculation process...")
    length = len(reference_data)
    difference_samples = min(len(reference_data[0]),difference_samples) #take a random sample of <difference_sample> columns
    distances = [[0]*length for j in range(length)]
    indices = sample(list(range(len(reference_data[0]))), difference_samples)
    discrete_values = [list(set([r[i] for r in reference_data])) if reference_data_types[i]=='D' else None for i in indices]
    reference_data_np_discrete   = [np.array([discrete_values[ii].index(r[i]) for ii,i in enumerate(indices) if reference_data_types[i]=='D']) for r in reference_data]
    reference_data_np_continuous = [np.array([r[i]*reference_data_types[i] for i in indices if reference_data_types[i]!='D']) for r in reference_data]
    async for i in progress(range(length),"Clustering data points","cluster distance iteration",4):
        for j in range(i+1,length):
            distances[i][j] = (   np.linalg.norm(reference_data_np_continuous[i]-reference_data_np_continuous[j])**2
                                + np.linalg.norm(  reference_data_np_discrete[i]-  reference_data_np_discrete[j]  ,ord=0) )
            distances[j][i] = distances[i][j]
    return distances

# custer_setup(): break the data into non-intersecting clusters of similar points, equally sized and approximately of size <size>,
# returning the indices of which data belongs in these clusters.
# repeating this process <custering> times to get a range of overlapping clusters of similar data points so that all points are equally
# sampled across the clusters
async def cluster_setup(reference_data, reference_data_types, size, clustering=30,difference_samples=10000):
    await async_print("preparing for clustering process...")
    assert size>0, "please ensure cluster_group_size is integer > 0"
    length = len(reference_data)
    distances = await get_approximate_distance_between_data(reference_data, reference_data_types, difference_samples)
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
wrap_values = lambda i,N: (i+N)%(2*N+1)-N

# generate_tabular_data(): generate <number_of_data> synthetic data from <reference_data> with colum types <reference_data_types>
# employing a clustering the <reference_data> into similar points of size <cluster_size>
# The process repeatedly chooses a cluster randomly, and the SAT solver to ensures that any pair of properties the cluster posesses
# must also be true of the synthetic data point generated
async def generate_tabular_data(reference_data, reference_data_types, cluster_size, number_of_data):
    output_data = []
    assert number_of_data>=0, "please ensure number_of_data is integer >= 0"
    assert len(reference_data)>0, "input dataset need to contain some data points"
    cluster_info = await cluster_setup(reference_data, reference_data_types, cluster_size)

    import pdb
    pdb.set_trace()

    # repeat till we generate <number_of_data> synthetic data points
    await async_print("Beginning Synthetic Data generation main loop.")
    restarts = 0
    while len(output_data) < number_of_data:
        await async_print(f"Completed {len(output_data)}/{number_of_data}")
        # select a cluster and shuffle
        data = [reference_data[ii] for ii in choice(cluster_info)]
        shuffle(data)
        queries = set()
        clauses = set()

        initial_t = time.time()
        # for each unique data column
        for t in set(map(tuple, zip(*([reference_data_types]+data)))):
            tt = t[1:]
            values = sorted(list(set(tt))) # get the list of unique ascending values in the column
            if t[0]=='D': # if column is categorical data
                presence_list = [tuple([ttt==value for ttt in tt]) for value in values]
                absence_list  = [tuple([ttt!=value for ttt in tt]) for value in values]
                clauses.add(frozenset(absence_list))
            else: # else column is continuous valued data
                presence_list = [tuple([ttt>value for ttt in tt]) for value in values[1:]]
                absence_list  = [tuple([not p for p in presence]) for presence in presence_list]
            # collect novel T/F array
            queries.update(presence_list)
            queries.update(absence_list)
        await async_print(f'collected queries in {time.time()-initial_t}')

        # collect T/F arrays, assign unique variables to each (or negated variables for opposite arrays)
        queries = sorted(list(queries))
        variables = len(queries)//2
        index = {v:wrap_values(i+1,variables) for i,v in enumerate(queries)}

        # convert T/F arrays to big-integers and index of thoes integers to variables
        binary_queries = [convert_to_binary(q) for q in queries]
        query_index_to_variable = [wrap_values(i+1,variables) for i in range(len(binary_queries))]

        # instantiate a SAT solver, and make constraints where where one-or-both of any two features are present across the data
        # then one-or-both of thoes features must be present for the synthetic data
        solver = Solver('minicard')
        mask = convert_to_binary([True]*len(queries[0]))
        initial_t = time.time()
        for i,k1 in enumerate(binary_queries):
            for j in range(i,len(binary_queries)):
                if ((k1|binary_queries[j])^mask).bit_count() <= 0:
                    solver.add_clause([ -query_index_to_variable[i],-query_index_to_variable[j] ])
        for c in clauses: solver.add_clause([index[cc] for cc in c])
        await async_print(f'added clauses in {time.time()-initial_t}')

        # randomise the SAT solver, solve the SAT problem and extract the solution, deleting the SAT solver instance
        initial_t = time.time()
        solver.set_phases([(i+1) * (2*randint(0,1)-1) for i in range(variables)])
        if solver.solve() != True:
            await async_print('SAT problem insoluble, if this repeats please loosen parameters to make problem tractable.')
            restarts += 1
            if restarts>10:
                raise Exception("SAT problem insouble, too many restarts")
            continue
        solution = set(solver.get_model())
        solver.delete()
        await async_print(f'SAT solving complete in {time.time()-initial_t}')

        # parse the output of the SAT solver back into sensible output data
        output = []
        initial_t = time.time()
        for t in map(tuple, zip(*([reference_data_types]+data))): # for each data column
            tt = t[1:]
            values = sorted(list(set(tt))) # for each data value in that column
            if t[0]=='D': # if categorical data,
                for value in values:
                    # if the variable associated with that T/F array is true
                    if index[tuple([ttt==value for ttt in tt])] not in solution:
                        # add the value to the output
                        output.append(value)
                        break
            else: # if continous data
                for i,value in enumerate(values):
                    # for the first less-than-or-equal-to T/F array with coresponding variable not in the solution
                    if i>0 and index[tuple([ttt<=value for ttt in tt])] not in solution:
                        # add the value in that range to the output
                        output.append(random()*(value-values[i-1])+values[i-1])
                        break
        await async_print(f'processed output in {time.time()-initial_t}')

        output_data.append(output)
    await async_print('finished Synthetic Data generation loop')
    return output_data

# tries to convert a input value to a floating point number, otherwise returns as is
def convert_to_float(value):
    try:
        f = float(value)
        if not math.isnan(f) and not math.isinf(f):
            return f
        else:
            return value
    except ValueError:
        return value

# parse_csv_dataset(): for array of row data tuples, and optional type specification <types>
# try to detect the <type> if not specified.
# ensure all continous data columns are float specified, and categorical columns are strings
async def parse_csv_dataset(data,types=None):
    await async_print('Parsing CSV dataset')
    if types is not None:
        await async_print('Parsing CSV types header')
        if len(data)>0:
            assert len(types)==len(data[0]), "type specification needs to be same dimension as data"
        try:
            types = [float(tt) if tt!='D' else tt for tt in types]
        except ValueError as e:
            raise Exception("Config line has invalid specification") from e
        for t in types:
            if t!='D':
                assert not math.isnan(t) and not math.isinf(t), "Continuous columns must have real importance score"
    else:
        await async_print('Auto Parsing CSV types header')
        types = []
        for column in map(tuple, zip(*data)):
            column = [convert_to_float(cc) for cc in column]
            if str in set([type(v) for v in column]):
                types.append("D")
            else:
                types.append(1.0)
    await async_print('rectifying CSV data columns')
    data = list(map(tuple, zip(*data))) # transpose data into columns
    for i in range(len(data)):
        if types[i]=='D': # if categorical data, ensure all values are strings
            data[i] = [str(dd) for dd in data[i]]
        else: # if continous data, ensure all values are floats
            data[i] = [float(dd) for dd in data[i]]
    data = list(map(tuple, zip(*data))) # transpose data back into rows
    return data,types

# Genomator_tabular_exec(): from an <input_csv_file> generate <number_of_data> synthetic data and export to <output_csv_file>
# the process involving clustering the <input_csv_file> data into clusters of size <cluster_size>, and informing whether the
# <input_csv_file> has a <header> row of column names, or subheader <header_types> row of column type information.
async def Genomator_tabular_exec(input_csv_file, output_csv_file, number_of_data, cluster_size=10, header=True, header_types=True):
    await async_print('Beginning Genomator Tabular generation')
    header, types, data = await parse_CSV(input_csv_file, header, header_types)
    data, types = await parse_csv_dataset(data, types)
    s = await generate_tabular_data(data, types, cluster_size, number_of_data)
    await output_CSV(s, header, types, output_csv_file)

@click.command()
@click.argument('input_csv_file', type=click.types.Path())
@click.argument('output_csv_file', type=click.types.Path())
@click.argument('number_of_data', type=click.INT, default=1)
@click.option('--cluster_size', type=click.INT, default=10)
@click.option('--header/--no-header', default=True, help='CSV input file contains a header line of column names')
@click.option('--header_types/--no-header_types', default=True, help='CSV file contains a supheader line of values specifying column type ["D","C"] for discrete/continuous')
def Genomator_tabular_mini(input_csv_file, output_csv_file, number_of_data, cluster_size, header, header_types):
    run(Genomator_tabular_exec(input_csv_file, output_csv_file, number_of_data, cluster_size, header, header_types))

if __name__ == '__main__':
    Genomator_tabular_mini()

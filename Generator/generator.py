#!/home/hecher/miniconda3/bin/python3
##/usr/bin/env python3
# -*- coding: future_fstrings -*-
import logging
import sys
import subprocess
import argparse
import os
import time
import random
import copy

from future_fstrings import StreamReader

from common import *
import signal
import time
import networkx as nx
from random import randint, random, seed

logger = logging.getLogger("generator")


class MyFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


_LOG_LEVEL_STRINGS = ["DEBUG_SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_METHOD_STRINGS = ["DENSE_SPARSE"]


def setup_arg_parser(usage):
    parser = argparse.ArgumentParser(
        usage="%(prog)s [general options] -f output-file ",
        formatter_class=MyFormatter)

    parser.add_argument("-f", "--file", dest="file", help="Output file", required=True)

    # general options
    gen_opts = parser.add_argument_group("general options", "General options")
    # gen_opts.add_argument("-t", dest="type", help="type of the cluster run", default="")
    gen_opts.add_argument("--cyclelength", dest="cyclelength", help="should be even", default=6, type=int)
    gen_opts.add_argument("--minchildren", dest="minchildren", help="minimum number of children each level", default=1, type=int)
    gen_opts.add_argument("--maxchildren", dest="maxchildren", help="maximum number of children each level", default=2, type=int)
    gen_opts.add_argument("--numdense", dest="numdense", help="number of dense components", default=1, type=int)
    gen_opts.add_argument("--numsparse", dest="numsparse", help="number of sparse components", default=1, type=int)
    gen_opts.add_argument("--levels", dest="levels", help="Number of levels", default=3, type=int)
    gen_opts.add_argument("--problevels", dest="problevels", help="Probability of an attack of next level", default=0.1,
                          type=float)
    gen_opts.add_argument("--seed", dest="seed", help="Random seed", default=0, type=int)
    # gen_opts.add_argument("--config", help="Config file", default="config.json")
    gen_opts.add_argument("--log-level", dest="log_level", help="Log level", choices=_LOG_LEVEL_STRINGS, default="INFO")
    # gen_opts.add_argument("--td-file", dest="td_file", help="Store TreeDecomposition file (htd Output)")
    # gen_opts.add_argument("--gr-file", dest="gr_file", help="Store Graph file (htd Input)")
    # gen_opts.add_argument("--cnf-file", dest="cnf_file", help="Store cnf file (and stop)")
    # gen_opts.add_argument("--faster", dest="faster", help="Store less information in database", action="store_true")
    # gen_opts.add_argument("--parallel-setup", dest="parallel_setup", help="Perform setup in parallel",
    #                       action="store_true")
    # gen_opts.add_argument("--btw-method", dest="btw_method", choices=_BTW_METHOD_STRINGS,
    #                       help="Method of backdoor treewidth computation", default="ARG_BD_SAT")
    # gen_opts.add_argument("--argument", dest="argument", help="Argument for credulous or sketpical reasoning")
    # gen_opts.add_argument("--bd-timeout", dest="bd_timeout", help="Timeout in seconds for calculating the backdoor",
    #                       type=int, default=20)
    # gen_opts.add_argument("--task", dest="task", help="Argumention task as TASK-SEMANTICS", choices=_TASKS_STRINGS,
    #                       default="CE-ST")

    return parser


def parse_args(parser):
    args = parser.parse_args()

    if args.log_level:
        if args.log_level == "DEBUG_SQL":
            log_level = DEBUG_SQL
        else:
            log_level = getattr(logging, args.log_level)

    logging.basicConfig(format='[%(levelname)s] %(name)s: %(message)s', level=log_level)

    return args


def setup_logging(level="INFO"):
    logging.basicConfig(format='[%(levelname)s] %(name)s: %(message)s', level=level)


######################################################################################

def write_af(graph, file):
    f = ""
    for n in graph.nodes:
        f += f"arg({n}).\n"

    for e in graph.edges:
        f += f"att({e[0]},{e[1]}).\n"

    w = open(file, "w")
    w.write(f)
    w.close()


def create_cycle_spikes(graph, args):
    cycle_length = args.cyclelength
    levels = args.levels
    s = args.seed
    seed(s)
    prob_att_next_level = args.problevels
    min_children = args.minchildren
    max_children = args.maxchildren

    level_nodes = {}

    offset = len(graph.nodes)

    # create main cycle
    for i in range(1 + offset, cycle_length + offset):
        graph.add_edge("c" + str(i), "c" + str(i + 1))
        if 0 not in level_nodes.keys():
            level_nodes[0] = ["c" + str(i), "c" + str(i + 1)]
        else:
            level_nodes[0].append("c" + str(i + 1))
    graph.add_edge("c" + str(offset + cycle_length), "c" + str(1 + offset))

    # generate children
    for l in range(1, levels + 1):
        for b in level_nodes[l - 1]:
            n = len(graph.nodes)
            c_n = randint(min_children, max_children)
            for c in range(n + 1, n + c_n + 1):
                n = len(graph.nodes)
                t = "a" + str(l) + "_" + str(n+1)
                if l not in level_nodes.keys():
                    level_nodes[l] = [t]
                else:
                    level_nodes[l].append(t)
                graph.add_edge(b, t)

    # make random connections in children
    for l in range(0, levels):
        for b in level_nodes[l]:

            t_l = l + 1

            for t in level_nodes[t_l]:
                if random() >= prob_att_next_level:
                    graph.add_edge(b, t)


def create_tree(graph, args):
    cycle_length = args.cyclelength
    levels = args.levels
    s = args.seed
    seed(s)
    prob_att_next_level = args.problevels
    min_children = args.minchildren
    max_children = args.maxchildren

    level_nodes = {}

    first = "a"+str(len(graph.nodes))
    level_nodes[1] = [first]
    graph.add_node(first)

    # generate children
    for l in range(2, cycle_length + 1):
        for b in level_nodes[l - 1]:
            n = len(graph.nodes)
            c_n = randint(min_children, max_children)
            for c in range(n + 1, n + c_n + 1):
                n = len(graph.nodes)
                t = "a" + str(l) + "_" + str(n+1)
                if l not in level_nodes.keys():
                    level_nodes[l] = [t]
                else:
                    level_nodes[l].append(t)
                graph.add_edge(b, t)
                if l % 2 == 0:
                    graph.add_edge(t, t)

    # close cycle for some
    for b in level_nodes[cycle_length]:
        prob = prob_att_next_level * prob_att_next_level
        if random() >= prob:
            graph.add_edge(b, first)


def main():
    global cfg
    # handle arguments
    arg_parser = setup_arg_parser("%(prog)s [general options] -f input-file")
    arg_parser.add_argument("--no-cache", dest="no_cache", help="Disable cache", action="store_true")
    args = parse_args(arg_parser)

    graph = nx.DiGraph()

    create_cycle_spikes(graph, args)
    create_cycle_spikes(graph, args)
    create_cycle_spikes(graph, args)
    create_tree(graph, args)

    write_af(graph, args.file)


if __name__ == "__main__":
    main()

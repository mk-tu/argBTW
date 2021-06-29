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
from audioop import add
from turtledemo.chaos import f

import dpdb.problems as problems
from dpdb.db import BlockingThreadedConnectionPool, DEBUG_SQL, setup_debug_sql, DBAdmin
from dpdb.problems import Sat
from dpdb.reader import TdReader, Reader
from dpdb.writer import StreamWriter, FileWriter
from dpdb.treedecomp import TreeDecomp
from dpdb.problem import args
from arg_util import read_af, reverse_dict
from nesthdb import main_btw, Graph

logger = logging.getLogger("argbtw")

tmp = "/tmp/{}_{}".format(time.time(), random.random())


class MyFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


_LOG_LEVEL_STRINGS = ["DEBUG_SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_BTW_METHOD_STRINGS = ["ARG_BD_SAT", "ARG_BD_ONLY", "ARG_TW_ONLY", "SAT_ENCODING"]
_TASKS_STRINGS = ["CE-ST"]  # , "CE-ADM", "CE-CO"]


def setup_arg_parser(usage):
    parser = argparse.ArgumentParser(
        usage="%(prog)s [general options] -f input-file ",
        formatter_class=MyFormatter)

    parser.add_argument("-f", "--file", dest="file", help="Input file for the problem to solve", required=True)

    # general options
    gen_opts = parser.add_argument_group("general options", "General options")
    gen_opts.add_argument("-t", dest="type", help="type of the cluster run", default="")
    gen_opts.add_argument("--runid", dest="runid", help="runid of the cluster run", default=0, type=int)
    gen_opts.add_argument("--config", help="Config file", default="config.json")
    gen_opts.add_argument("--log-level", dest="log_level", help="Log level", choices=_LOG_LEVEL_STRINGS, default="INFO")
    gen_opts.add_argument("--td-file", dest="td_file", help="Store TreeDecomposition file (htd Output)")
    gen_opts.add_argument("--gr-file", dest="gr_file", help="Store Graph file (htd Input)")
    gen_opts.add_argument("--cnf-file", dest="cnf_file", help="Store cnf file (and stop)")
    gen_opts.add_argument("--faster", dest="faster", help="Store less information in database", action="store_true")
    gen_opts.add_argument("--parallel-setup", dest="parallel_setup", help="Perform setup in parallel",
                          action="store_true")
    gen_opts.add_argument("--btw-method", dest="btw_method", choices=_BTW_METHOD_STRINGS,
                          help="Method of backdoor treewidth computation", default="ARG_BD_SAT")
    gen_opts.add_argument("--argument", dest="argument", help="Argument for credulous or sketpical reasoning")
    gen_opts.add_argument("--bd-timeout", dest="bd_timeout", help="Timeout in seconds for calculating the backdoor",
                          type=int, default=20)
    gen_opts.add_argument("--task", dest="task", help="Argumention task as TASK-SEMANTICS", choices=_TASKS_STRINGS,
                          default="CE-ST")

    return parser


# class NE_graph:
#     edges = []
#     num_vertices = 0
#     vertices = []
#
#     def __init__(self, file):
#         self.edges = []
#         self.num_vertices = 0
#         self.vertices = []
#
#         f = open(file, "r")
#         line = f.readline()
#         while (line):
#             line = line.replace(").", "")
#             line = line.strip()
#             if (line.startswith("backdoor")):
#                 line = line.replace("backdoor(", "")
#                 self.num_vertices += 1
#                 self.vertices.append(line)
#
#             elif (line.startswith("torsoEdge")):
#                 line = line.replace("torsoEdge(", "")
#                 a = line.split(",")[0]
#                 b = line.split(",")[1]
#                 self.edges.append((a, b))
#
#             line = f.readline()
#
#         f.close()


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


def arg_to_backdoor(af, file, bd_timeout, **kwargs):
    global tmp
    # clingo --out-atomf=%s. -V0 --quiet=1 minimumAcycBackdoor.asp <input> --time-limit=100 |head -n 1 > bd.out
    p = subprocess.Popen(
        [cfg["clingo"]["path"], "--out-atomf=%s.", "-V0", "--quiet=1",
         os.path.dirname(os.path.realpath(__file__)) + "/ASP/minimumAcycBackdoor.asp", tmp + "af.apx",
         "--time-limit=" + str(bd_timeout)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    bd = p.stdout.read()
    bd = str(bd.splitlines()[0])
    bd = bd.replace("b'", "").replace("'", "")
    p.stdin.close()
    p.wait()
    if (bd == "UNKNOWN"):  # clingo timeout, make all arguments backdoor args
        bd = ""
        for a in af.values():
            bd += "backdoor(" + str(a.atom) + "). "
        bd += "backdoorsize(" + str(len(af)) + ")."

    f = open(tmp + "bd.out", "w")  # os.path.dirname(os.path.realpath(__file__)) + "/bd.out", "w")
    f.write(bd)
    f.close()


# def torso_format(file):
#     #
#     p = subprocess.Popen(
#         [cfg["clingo"]["path"], "--out-atomf=%s.", "-V0", "--quiet=1", "ASP/TorsotoGraph.lp", file, "torso.out"],
#         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
#     bd = p.stdout.read()
#     bd = str(bd.splitlines()[0])
#     bd = bd.replace("b'", "").replace("'", "")
#     p.stdin.close()
#     p.wait()
#
#     f = open("torso.torso", "w")
#
#     f.write(bd)
#     f.close()


def compute_torso():
    # clingo --out-atomf=%s. -V0 --quiet=1 minimumAcycBackdoor.asp <input> --time-limit=100 |head -n 1 > bd.out
    bd_file = tmp + "bd.out"
    p = subprocess.Popen(
        [cfg["clingo"]["path"], "--out-atomf=%s.", "-V0", "--quiet=1",
         os.path.dirname(os.path.realpath(__file__)) + "/ASP/torso.asp", tmp + "af.apx", bd_file],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    bd_file = p.stdout.read()
    bd_file = str(bd_file.splitlines()[0])
    bd_file = bd_file.replace("b'", "").replace("'", "")
    p.stdin.close()
    p.wait()
    # f = open(os.path.dirname(os.path.realpath(__file__)) + "/torso.out", "w")
    f = open(tmp + "torso.out", "w")
    logger.debug("Torso saved to " + tmp + "torso.out")
    bd_file = bd_file.replace(" ", "\n")
    f.write(bd_file)
    f.close()


def find_last_node(tdr, af, bd):  # traverse the TD in preorder and find out last(a) for all a
    td = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, copy.deepcopy(tdr.bags),
                    tdr.adjacency_list,
                    None)  # just to traverse tdr easier (deep copy so that the vertices lists are not updated)
    d_number = len(af) + 1

    nodes = [td.root]
    visited = []

    ds = []

    while nodes:
        node = nodes.pop()
        for v in node.vertices:  # and v not in ds:
            if v in bd:  # add arguments d only if the argument is a backdoor arg
                a = reverse_dict[v]
                a.ds[node.id] = d_number
                ds.append(d_number)
                tdr.bags[node.id].append(d_number)
                tdr.num_orig_vertices += 1

                if node.parent and v in node.parent.vertices:
                    tdr.bags[node.parent.id].append(d_number)

                d_number += 1

            if (v not in visited):
                visited.append(v)
                a = reverse_dict[v]
                a.last_node = node.id

        for c in node.children:
            nodes.insert(0, c)

    return d_number - 1, ds


def decomp_guided_reduction_1(af, td, cnf, clauses, debug_cnf, bd):
    # dta -> V dta v V a
    # dta <- V dta v V a

    nodes = [td.root]

    while (len(nodes) > 0):
        node = nodes.pop()
        for v in set(node.vertices).intersection(bd):
            a = reverse_dict[v]
            if (a.atom not in bd):  # does probably not work for adm TODO
                continue
            # <->
            dta = str(a.ds[node.id])
            right_arrow = ""
            right_arrow += "-" + dta + " "
            for at in a.attacked_by():
                # if node not in at.ds.keys():
                #     continue
                if at not in node.all_vertices:
                    continue
                right_arrow += str(at) + " "
                cnf += dta + " -" + str(at) + " 0\n"
                clauses += 1
                if debug_cnf:
                    cnf += "c\t (1) <= attacker)\n"

            for c in node.children:
                if c.id in a.ds.keys():
                    right_arrow += str(a.ds[c.id]) + " "
                    cnf += dta + " -" + str(a.ds[c.id]) + " 0\n"
                    clauses += 1
                    if debug_cnf:
                        cnf += "c\t (1) <= dta child)\n"

            right_arrow += "0\n"
            cnf += right_arrow
            clauses += 1
            if debug_cnf:
                cnf += "c\t (1) =>\n"

        # node.vertices = [int(x) for x in node.vertices]
        for c in node.children:
            nodes.insert(0, c)

    return clauses, cnf


def decomp_guided_reduction_2(af, td, cnf, clauses, debug_cnf):
    # conf_R
    for arg in af.values():

        for at in arg.attacked_by():
            cnf += "-" + str(arg.atom) + " -" + str(at) + " 0\n"
            if debug_cnf:
                cnf += "c\t (2) conf_R (attack: " + str(at) + " attacks " + str(arg.atom) + ")\n"
            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_3(af, td, cnf, clauses, debug_cnf, bd):
    # a OR d_a^last(a)
    for arg in af.values():
        if (arg.atom in bd):
            # a OR d_a^last(a)
            cnf += str(arg.atom) + " " + str(arg.ds[arg.last_node]) + " 0\n"
            clauses += 1
            if debug_cnf:
                cnf += "c\t (3)\n"

        else:  # stable combination of (1) and (3) for non bd variables
            cnf += str(arg.atom) + " "
            for b in arg.attacked_by():
                cnf += str(b) + " "

            cnf += "0\n"
            if debug_cnf:
                cnf += "c\t (3) alternative for non bd\n"
            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_4(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        for b in arg.attackedBy:  # for each attack (b,arg)
            cnf += "-" + str(b.n) + " -" + str(arg.atom) + " 0\n"
            if debug_cnf:
                cnf += "c\t (4)\n"

            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_5(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "" + str(arg.atom) + " " + str(arg.n) + " " + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (5)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_6(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "-" + str(arg.n) + " -" + str(arg.atom) + " 0\n"
        if debug_cnf:
            cnf += "c\t (6)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_7(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "-" + str(arg.n) + " -" + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (7)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_8(af, td, cnf, clauses, debug_cnf):
    nodes = [td.root]

    while nodes:
        node = nodes.pop()
        for v in node.vertices:
            # <->
            ota = str(af[v].os[node])
            right_arrow = ""
            right_arrow += "-" + ota + " "
            for at in af[v].attackedBy:
                if node not in at.os.keys():
                    continue
                right_arrow += str(at.os[at.last_node]) + " "
                cnf += ota + " -" + str(at.os[at.last_node]) + " 0\n"
                clauses += 1
                if debug_cnf:
                    cnf += "c\t (8) <= attacker: " + at.name + " attacks " + v + "\n"

            for c in node.children:
                if c in af[v].os.keys():
                    right_arrow += str(af[v].os[c]) + " "
                    cnf += ota + " -" + str(af[v].os[c]) + " 0\n"
                    clauses += 1
                    if debug_cnf:
                        cnf += "c\t (8) <= ota child " + str(v) + "  " + str(af[v].os[node]) + "\n"

            right_arrow += "0\n"
            cnf += right_arrow
            clauses += 1
            if debug_cnf:
                cnf += "c\t (8) =>\n"

        # node.vertices = [int(x) for x in node.vertices]
        for c in node.children:
            nodes.insert(0, c)

    return clauses, cnf


def decomp_guided_reduction_9(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        for b in arg.attackedBy:  # for each attack (b,arg)
            cnf += "-" + str(b.atom) + " -" + str(arg.os[arg.last_node]) + " 0\n"
            if debug_cnf:
                cnf += "c\t (9)\n"

            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_10(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        for b in arg.attackedBy:  # for each attack (b,arg)
            cnf += "-" + str(arg.atom) + " -" + str(b.os[b.last_node]) + " 0\n"
            if debug_cnf:
                cnf += "c\t (10)\n"

            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_11(af, td, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "" + str(arg.atom) + " " + str(arg.os[arg.last_node]) + " " + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (11)\n"

        clauses += 1
    return clauses, cnf


def add_n(af, variables):  # adds a prop var n for each argument
    for arg in af.values():
        variables += 1
        arg.n = variables

    return variables


def add_o(af, td, variables):
    nodes = [td.root]
    o_number = variables + 1

    while nodes:
        node = nodes.pop()
        for v in node.vertices:
            af[v].os[node] = o_number
            o_number += 1

        for c in node.children:
            nodes.insert(0, c)

    return o_number - 1


def decomp_guided_reduction(af, td, semantics, bd, variables, store_cnf):
    cnf = ""
    # find last(a)
    debug_cnf = False

    clauses = 0

    if semantics.lower() == "st":
        clauses, cnf = decomp_guided_reduction_1(af, td, cnf, clauses, debug_cnf, bd)
        clauses, cnf = decomp_guided_reduction_2(af, td, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_3(af, td, cnf, clauses, debug_cnf, bd)

    else:
        logger.error("Unknown semantics")
        exit(1)

    # f = open(os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", "w")

    if store_cnf is not None:
        logger.info(f"Saved cnf as {store_cnf}.")
        f = open(store_cnf, "w")
        f.write(cnf)
        f.close()
        exit(0)

    f = open(tmp + "argSat.cnf", "w")
    cnf = "p cnf " + str(variables) + " " + str(clauses) + "\n" + cnf
    f.write(cnf)
    f.close()


def compute_torso_graph(af):
    def add_edge(v1, v2, adj, edges):
        if v1 == v2:
            return

        if v1 in adj:
            adj[v1].add(v2)
        else:
            adj[v1] = set([v2])
        if v1 < v2:
            edges.add((v1, v2))

    nodes = []
    edges = set([])
    adj = {}
    num_vertices = 0

    # f = open(os.path.dirname(os.path.realpath(__file__)) + "/torso.out", "r")
    f = open(tmp + "torso.out", "r")
    line = f.readline()
    while line:
        line = line.replace(").", "")
        line = line.strip()
        if (line.startswith("backdoor")):
            line = line.replace("backdoor(", "")
            num_vertices += 1
            nodes.append(int(line))

        elif (line.startswith("torsoEdge")):
            line = line.replace("torsoEdge(", "")
            a = int(line.split(",")[0])
            b = int(line.split(",")[1])

            add_edge(a, b, adj, edges)
            add_edge(b, a, adj, edges)

        line = f.readline()

    f.close()
    logger.info("Backdoor size: " + str(len(nodes)))
    torso = Graph(nodes, edges, adj)
    return torso


def decompose_torso(kwargs, af):
    # torso_format(file)
    torso = compute_torso_graph(af)
    p = subprocess.Popen([cfg["htd"]["path"], "--seed", str(kwargs["runid"]), *cfg["htd"]["parameters"]],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    logger.info("Normalize torso")
    # torso = NE_graph("torso.out")
    torso.normalize()
    StreamWriter(p.stdin).write_gr(len(torso.nodes), torso.edges_normalized)

    p.stdin.close()
    logger.info("Running htd")
    tdr = TdReader.from_stream(p.stdout)
    p.wait()

    logger.info("De-normalize torso")
    # de-normalize
    tdr.bags = {k: [torso._node_rev_map[vv] for vv in v] for k, v in tdr.bags.items()}
    return tdr, torso


def add_remaining(tdr, bd, af):  # adds the remaining adjacent arguments to the respective bags
    # f = open(os.path.dirname(os.path.realpath(__file__)) + "/torso.out", "r")
    f = open(tmp + "torso.out", "r")
    line = f.readline()

    adj = {}

    # get which backdoor variables each remaining argument is adjacent to

    while line:
        line = line.replace(").", "")
        line = line.strip()
        if (line.startswith("adjacenttoBackdoor")):
            line = line.replace("adjacenttoBackdoor(", "")
            a = int(line.split(",")[0])
            b = int(line.split(",")[1])
            if a in adj:
                adj[a].add(b)
            else:
                adj[a] = {b}

        line = f.readline()

    f.close()
    if len(adj) < len(af) - len(
            bd):  # not all arguments are adjacent to a backdoor -> add remaining to root bag

        atoms = {a.atom for a in af.values()}
        rems = atoms - set(bd) - set(adj.keys())
        logger.debug(f"Adding {len(rems)} arguments not adjacent to backdoor in root bag")

        tdr.bags[tdr.root].extend(list(rems))
        tdr.num_orig_vertices += len(rems)

    # add remaining argument to the first bag that contains all its adjacent backdoor arguments
    for a in adj.keys():
        for bag in tdr.bags.keys():
            if (adj[a].issubset(tdr.bags[bag])):
                tdr.bags[bag].append(a)
                tdr.num_orig_vertices += 1
                break


def add_ns_to_td(tdr, af, td):
    # adds the additional n vars to their respective nodes
    for a in af.values():
        # a.last_node.vertices.append(a.n)
        # tdr.num_orig_vertices += 1

        nodes = [td.root]

        while (nodes):
            n = nodes.pop()
            n.vertices.append(a.n)

            for c in n.children:
                nodes.insert(0, c)

        # tdr.num_orig_vertices += 1
        # for n in a.ds.keys():
        #     n.vertices.append(a.n)


def add_os_to_td(tdr, af):
    # adds the additional o vars to their respective nodes and their parents
    for a in af.values():
        for n in a.os.keys():
            n.vertices.append(a.os[n])
            tdr.num_orig_vertices += 1
            if (n.parent):
                n.parent.vertices.append(a.os[n])


def exchange_names(tdr, af):
    for b in tdr.bags:
        bag = tdr.bags[b]
        nums = []
        for a in bag:
            if isinstance(a, str):
                nums.append(af[a].atom)
            else:
                nums.append(a)

        tdr.bags[b] = nums


def calc_adj(af, graph):
    adj = {}
    for a_arg in af.values():
        for d in a_arg.ds.values():
            graph.add_node(d)
            graph.add_edge(d, a_arg.atom)

        a = a_arg.atom
        for b in a_arg.attacked_by():
            if a in adj:
                adj[a].add(b)
            else:
                adj[a] = {b}
            if b in adj:
                adj[b].add(a)
            else:
                adj[b] = {a}

        for d in a_arg.ds.values():
            if a in adj:
                adj[a].add(d)
            else:
                adj[a] = {d}
            adj[d] = {a}

    return adj


def arg_bd_sat(af, graph, file, cnf_file, **kwargs):
    global tmp
    # computes a backdoor set, a TD of its torso and performs a TD reduction
    semantics = kwargs["task"][3:]

    logger.debug("Computing backdoor")
    arg_to_backdoor(af, file, **kwargs)
    logger.debug("Computing torso")
    compute_torso()  # os.path.dirname(os.path.realpath(__file__)) + "/bd.out")
    logger.debug("Torso tree decomposition")
    tdr, torso = decompose_torso(kwargs, af)
    bd = torso.nodes
    logger.info("Torso decomposed: Backdoor-treewidth: " + str(tdr.tree_width) + ", #bags: " + str(tdr.num_bags))
    logger.debug("Perform decomposition guided reduction")

    variables, ds = find_last_node(tdr, af, bd)

    logger.debug("Add remaining (i.e. not backdoor) arguments to tree decomposition")

    # add_remaining(tdr, bd, af)

    d_graph = copy.deepcopy(graph)

    adj = calc_adj(af, d_graph)

    af_graph = Graph(d_graph.nodes, d_graph.edges, adj)  # af with d adjacent to their arguments

    non_nested = bd + ds

    af_graph.abstract(non_nested)

    af_graph.tree_decomp = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, tdr.bags,
                                      tdr.adjacency_list,
                                      af_graph.mg)

    # print_variables(af, bd, af_graph)
    decomp_guided_reduction(af, af_graph.tree_decomp, semantics, bd, variables, cnf_file)

    # atoms = {a.atom for a in af.values()}
    # nested = atoms - set(bd)

    #
    # set minor variables

    logger.debug("CNF saved as: " + tmp + "argSat.cnf")

    # main_btw(cfg, os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", torso.tree_decomp, torso, bd_z, **kwargs)
    main_btw(cfg, tmp + "argSat.cnf", True, af_graph, bd, **kwargs)


def arg_bd_only(af, graph, file, cnf_file, **kwargs):
    # like arg_bd_sat, but puts everything in one bag
    global tmp
    # computes a backdoor set, a TD of its torso and performs a TD reduction
    semantics = kwargs["task"][3:]

    logger.debug("Computing backdoor")
    arg_to_backdoor(af, file, **kwargs)

    # dummy tree decomposition with just one bag

    torso = graph.to_undirected()

    bd = [x for x in torso.nodes]

    tdr = TdReader()
    tdr.bags = {1: [x for x in bd]}
    tdr.num_bags = 1
    tdr.tree_width = len(bd) - 1
    tdr.num_orig_vertices = len(bd)
    tdr.root = 1

    logger.info("Torso decomposed: Backdoor-treewidth: " + str(tdr.tree_width) + ", #bags: " + str(tdr.num_bags))
    logger.debug("Perform decomposition guided reduction")

    variables, ds = find_last_node(tdr, af, bd)

    d_graph = copy.deepcopy(graph)

    adj = calc_adj(af, d_graph)

    af_graph = Graph(d_graph.nodes, d_graph.edges, adj)  # af with d adjacent to their arguments

    non_nested = bd + ds

    af_graph.abstract(non_nested)

    af_graph.tree_decomp = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, tdr.bags,
                                      tdr.adjacency_list,
                                      af_graph.mg)

    # print_variables(af, bd, af_graph)
    decomp_guided_reduction(af, af_graph.tree_decomp, semantics, bd, variables, cnf_file)

    # atoms = {a.atom for a in af.values()}
    # nested = atoms - set(bd)

    #
    # set minor variables

    logger.debug("CNF saved as: " + tmp + "argSat.cnf")

    # main_btw(cfg, os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", torso.tree_decomp, torso, bd_z, **kwargs)
    main_btw(cfg, tmp + "argSat.cnf", True, af_graph, bd, **kwargs)


def arg_tw_only(af, graph, file, cnf_file, **kwargs):
    global tmp
    # computes a backdoor set, a TD of its torso and performs a TD reduction
    semantics = kwargs["task"][3:]

    bd = ""
    for a in af.values():
        bd += "backdoor(" + str(a.atom) + "). "
    bd += "backdoorsize(" + str(len(af)) + ")."

    f = open(tmp + "bd.out", "w")  # os.path.dirname(os.path.realpath(__file__)) + "/bd.out", "w")
    f.write(bd)
    f.close()

    logger.debug("Computing torso")
    compute_torso()  # os.path.dirname(os.path.realpath(__file__)) + "/bd.out")
    logger.debug("Torso tree decomposition")
    tdr, torso = decompose_torso(kwargs, af)
    bd = torso.nodes
    logger.info("Torso decomposed: Backdoor-treewidth: " + str(tdr.tree_width) + ", #bags: " + str(tdr.num_bags))
    logger.debug("Perform decomposition guided reduction")

    variables, ds = find_last_node(tdr, af, bd)

    d_graph = copy.deepcopy(graph)

    adj = calc_adj(af, d_graph)

    af_graph = Graph(d_graph.nodes, d_graph.edges, adj)  # af with d adjacent to their arguments

    non_nested = bd + ds

    af_graph.abstract(non_nested)

    af_graph.tree_decomp = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, tdr.bags,
                                      tdr.adjacency_list,
                                      af_graph.mg)

    # print_variables(af, bd, af_graph)
    decomp_guided_reduction(af, af_graph.tree_decomp, semantics, bd, variables, cnf_file)

    # atoms = {a.atom for a in af.values()}
    # nested = atoms - set(bd)

    #
    # set minor variables

    logger.debug("CNF saved as: " + tmp + "argSat.cnf")

    # main_btw(cfg, os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", torso.tree_decomp, torso, bd_z, **kwargs)
    main_btw(cfg, tmp + "argSat.cnf", True, af_graph, bd, **kwargs)


def print_variables(af, bd, af_graph):
    for node in af_graph.tree_decomp.nodes:  # todo
        print("NODE: " + str(node.id))
        print(node.parent)
        print(node.vertices)
        print(node.minor_vertices)
        print(node.all_vertices)
        print("----------")
    print("Backdoor:")
    print(bd)

    for arg in af.values():
        a = ""
        a = a + (arg.name + " " + str(arg.atom) + "\tds: ")
        for d in arg.ds.keys():
            a = a + str(d) + "=" + str(arg.ds[d]) + "\t"
        print(a)


def sat_encoding(af, graph, file, cnf_file, **kwargs):
    if cnf_file is None:
        logger.error("No cnf file set in SAT-ENCODING mode")
        exit(1)

    semantics = kwargs["task"][3:]
    if semantics.lower() != "st":
        logger.error("Unknown semantics")
        exit(1)

    cnf = ""
    clauses = 0
    for a in graph.nodes():
        right = "-" + str(a) + " "
        for b in graph.predecessors(a):
            right += "-" + str(b) + " "
            cnf += str(b) + " " + str(a) + " 0\n"
            clauses += 1
        right += "0\n"
        cnf += right
        clauses += 1

    variables = len(graph.nodes())

    cnf = "p cnf " + str(variables) + " " + str(clauses) + "\n" + cnf

    f = open(cnf_file, "w")
    f.write(cnf)
    f.close()

    logger.info(f"cnf saved to {cnf_file}")


def solve(af, graph, btw_method, **kwargs):
    logger.info(f"Method: {btw_method}")
    if (btw_method.lower() == "arg_bd_sat"):
        arg_bd_sat(af, graph, **kwargs)
    elif (btw_method.lower() == "arg_bd_only"):
        arg_bd_only(af, graph, **kwargs)
    elif (btw_method.lower() == "arg_tw_only"):
        arg_tw_only(af, graph, **kwargs)
    elif (btw_method.lower() == "sat_encoding"):
        sat_encoding(af, graph, **kwargs)
    else:
        logger.error("Unknown method")
        exit(1)


def main():
    global cfg
    # handle arguments
    arg_parser = setup_arg_parser("%(prog)s [general options] -f input-file")
    arg_parser.add_argument("--no-cache", dest="no_cache", help="Disable cache", action="store_true")
    args = parse_args(arg_parser)
    cfg = read_cfg(args.config)

    # read AF
    logger.info("Reading AF")
    af, num_args, num_atts, graph = read_af(tmp, **vars(args))

    logger.debug(f"AF saved to {tmp}af.apx")
    logger.info(f"Argumentation Framework with {num_args} arguments and {num_atts} attacks read")
    solve(af, graph, **vars(args))


if __name__ == "__main__":
    main()

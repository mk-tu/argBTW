#!/usr/bin/env python3
# -*- coding: future_fstrings -*-
import logging
import sys
import subprocess
import argparse
import os

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
from arg_util import *
from nesthdb import main_btw, Graph

logger = logging.getLogger("argbtw")


class MyFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


_LOG_LEVEL_STRINGS = ["DEBUG_SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
_BTW_METHOD_STRINGS = ["ARG_BD_SAT", "SAT_DP_ONLY"]
_TASKS_STRINGS = ["CE-ST", "CE-ADM", "CE-CO"]


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
    gen_opts.add_argument("--faster", dest="faster", help="Store less information in database", action="store_true")
    gen_opts.add_argument("--parallel-setup", dest="parallel_setup", help="Perform setup in parallel",
                          action="store_true")
    gen_opts.add_argument("--btw-method", dest="btw_method", choices=_BTW_METHOD_STRINGS,
                          help="Method of backdoor treewidth computation", default="ARG_BD_SAT")
    gen_opts.add_argument("--argument", dest="argument", help="Argument for credulous or sketpical reasoning")
    gen_opts.add_argument("--bd-timeout", dest="bd_timeout", help="Timeout in seconds for calculating the backdoor", type=int, default=20)
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


def arg_to_backdoor(file, bd_timeout, **kwargs):
    # clingo --out-atomf=%s. -V0 --quiet=1 minimumAcycBackdoor.asp <input> --time-limit=100 |head -n 1 > bd.out
    p = subprocess.Popen(
        [cfg["clingo"]["path"], "--out-atomf=%s.", "-V0", "--quiet=1", os.path.dirname(os.path.realpath(__file__)) + "/ASP/minimumAcycBackdoor.asp", file,
         "--time-limit="+str(bd_timeout)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    bd = p.stdout.read()
    bd = str(bd.splitlines()[0])
    bd = bd.replace("b'", "").replace("'", "")
    p.stdin.close()
    p.wait()

    f = open(os.path.dirname(os.path.realpath(__file__)) + "/bd.out", "w")

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


def compute_torso(file, bd):
    # clingo --out-atomf=%s. -V0 --quiet=1 minimumAcycBackdoor.asp <input> --time-limit=100 |head -n 1 > bd.out
    p = subprocess.Popen(
        [cfg["clingo"]["path"], "--out-atomf=%s.", "-V0", "--quiet=1", os.path.dirname(os.path.realpath(__file__)) + "/ASP/torso.asp", file, bd],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    bd = p.stdout.read()
    bd = str(bd.splitlines()[0])
    bd = bd.replace("b'", "").replace("'", "")
    p.stdin.close()
    p.wait()

    f = open(os.path.dirname(os.path.realpath(__file__)) + "/torso.out", "w")
    bd = bd.replace(" ", "\n")
    f.write(bd)
    f.close()


def sat_dp_only(af, file, argument, **kwargs):
    # computes a cnf, calls nesthdb projected to all variables (just normal DP)
    # build cnf
    # conflict free property
    arguments = af
    cnf = ""
    clauses = 0
    for a in arguments.values():
        if a.selfAttacking:
            cnf = cnf + "-" + str(a.thisArgument) + " 0\n"
            clauses += 1
        else:
            for b in a.attackedBy:
                if b.selfAttacking:
                    continue
                cnf += "-" + str(a.thisArgument) + " -" + str(b.thisArgument) + " 0\n"
                clauses += 1
    # stable property
    for a in arguments.values():
        cnf += str(a.thisArgument) + " "
        for b in a.attackedBy:
            cnf += str(b.thisArgument) + " "
        cnf += "0\n"
        clauses += 1

    # reasoning
    if argument:
        cnf += str(arguments[argument].thisArgument) + " 0\n"
        clauses += 1
        cnf = "c IS THE ARGUMENT " + argument + " (" + str(
            arguments[
                argument].thisArgument) + ") CREDULOUSLY ACCEPTED IN THE AF " + file + " W.R.T. STABLE SEMANTICS\n" + "p cnf " + str(
            Argument.maxArgument) + " " + str(clauses) + "\n" + cnf
    else:
        cnf = "c STABLE EXTENSIONS OF THE AF " + file + "\n" + "p cnf " + str(
            Argument.maxArgument) + " " + str(clauses) + "\n" + cnf

    # save in "argSat.cnf"
    ff = open(os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", "w")
    ff.write(cnf)
    ff.close()
    main_btw(cfg, os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", None, None, **kwargs)


def find_last_node(td, af, tdr):  # traverse the TD in preorder and find out last(a) for all a
    nodes = [td.root]
    visited = []
    d_number = len(af) + 1

    while nodes:
        node = nodes.pop()
        for v in node.vertices:
            af[v].ds[node] = d_number
            d_number += 1

            # rint(str(v)+"\tin node \t"+str(node.id)+"\td\t"+str(d_number-1))

            # tdr.bags[node.id].append(d_number)
            # if(node.parent):
            #     tdr.bags[node.parend.id].append(d_number)

            if (v not in visited):
                visited.append(v)
                af[v].last_node = node

        for c in node.children:
            nodes.insert(0, c)

    return d_number - 1


def decomp_guided_reduction_1(af, td, tdr, cnf, clauses, debug_cnf):
    # dta -> V dta v V a
    # dta <- V dta v V a
    nodes = [td.root]

    while (len(nodes) > 0):
        node = nodes.pop()
        for v in node.vertices:
            # <->
            dta = str(af[v].ds[node])
            right_arrow = ""
            right_arrow += "-" + dta + " "
            for at in af[v].attackedBy:
                if node not in at.ds.keys():
                    continue
                right_arrow += str(at.thisArgument) + " "
                cnf += dta + " -" + str(at.thisArgument) + " 0\n"
                clauses += 1
                if debug_cnf:
                    cnf += "c\t (1) <= attacker)\n"

            for c in node.children:
                if c in af[v].ds.keys():
                    right_arrow += str(af[v].ds[c]) + " "
                    cnf += dta + " -" + str(af[v].ds[c]) + " 0\n"
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


def decomp_guided_reduction_2(af, td, tdr, cnf, clauses, debug_cnf):
    # conf_R
    for arg in af.values():

        for at in arg.attackedBy:
            cnf += "-" + str(arg.thisArgument) + " -" + str(at.thisArgument) + " 0\n"
            if debug_cnf:
                cnf += "c\t (2) conf_R (attack: " + str(at.thisArgument) + " attacks " + str(arg.thisArgument) + ")\n"
            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_3(af, td, tdr, cnf, clauses, debug_cnf):
    # a OR d_a^last(a)
    for arg in af.values():
        # a OR d_a^last(a)
        cnf += str(arg.thisArgument) + " " + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (3)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_4(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        for b in arg.attackedBy:  # for each attack (b,arg)
            cnf += "-" + str(b.n) + " -" + str(arg.thisArgument) + " 0\n"
            if debug_cnf:
                cnf += "c\t (4)\n"

            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_5(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "" + str(arg.thisArgument) + " " + str(arg.n) + " " + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (5)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_6(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "-" + str(arg.n) + " -" + str(arg.thisArgument) + " 0\n"
        if debug_cnf:
            cnf += "c\t (6)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_7(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "-" + str(arg.n) + " -" + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (7)\n"

        clauses += 1
    return clauses, cnf


def decomp_guided_reduction_8(af, td, tdr, cnf, clauses, debug_cnf):
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


def decomp_guided_reduction_9(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        for b in arg.attackedBy:  # for each attack (b,arg)
            cnf += "-" + str(b.thisArgument) + " -" + str(arg.os[arg.last_node]) + " 0\n"
            if debug_cnf:
                cnf += "c\t (9)\n"

            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_10(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        for b in arg.attackedBy:  # for each attack (b,arg)
            cnf += "-" + str(arg.thisArgument) + " -" + str(b.os[b.last_node]) + " 0\n"
            if debug_cnf:
                cnf += "c\t (10)\n"

            clauses += 1
    return clauses, cnf


def decomp_guided_reduction_11(af, td, tdr, cnf, clauses, debug_cnf):
    for arg in af.values():
        cnf += "" + str(arg.thisArgument) + " " + str(arg.os[arg.last_node]) + " " + str(arg.ds[arg.last_node]) + " 0\n"
        if debug_cnf:
            cnf += "c\t (11)\n"

        clauses += 1
    return clauses, cnf


def add_n(af, variables):  # adds a prop var n for each argument
    for arg in af.values():
        variables += 1
        arg.n = variables

    return variables


def add_o(af, td, tdr, variables):
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


def decomp_guided_reduction(af, td, tdr, semantics):
    cnf = ""
    # find last(a)
    debug_cnf = False
    variables = find_last_node(td, af, tdr)
    clauses = 0

    if semantics.lower() == "st":
        clauses, cnf = decomp_guided_reduction_1(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_2(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_3(af, td, tdr, cnf, clauses, debug_cnf)
    elif semantics.lower() == "adm":
        variables = add_n(af, variables)
        clauses, cnf = decomp_guided_reduction_1(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_2(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_4(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_5(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_6(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_7(af, td, tdr, cnf, clauses, debug_cnf)
    elif semantics.lower() == "co":
        variables = add_o(af, td, tdr, variables)
        clauses, cnf = decomp_guided_reduction_1(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_2(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_8(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_9(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_10(af, td, tdr, cnf, clauses, debug_cnf)
        clauses, cnf = decomp_guided_reduction_11(af, td, tdr, cnf, clauses, debug_cnf)
    else:
        logger.error("Unknown semantics")
        exit(1)

    f = open(os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", "w")
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

    f = open(os.path.dirname(os.path.realpath(__file__)) + "/torso.out", "r")
    line = f.readline()
    while line:
        line = line.replace(").", "")
        line = line.strip()
        if (line.startswith("backdoor")):
            line = line.replace("backdoor(", "")
            num_vertices += 1
            nodes.append(line)

        elif (line.startswith("torsoEdge")):
            line = line.replace("torsoEdge(", "")
            a = line.split(",")[0]
            b = line.split(",")[1]

            add_edge(a, b, adj, edges)
            add_edge(b, a, adj, edges)

        line = f.readline()

    f.close()
    logger.info("Backdoor size: " + str(len(nodes)))
    torso = Graph(nodes, edges, adj)
    return torso


def decompose_torso(file, kwargs, af):
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


def add_remaining(tdr, torso, af):  # adds the remaining adjacent arguments to the respective bags
    f = open(os.path.dirname(os.path.realpath(__file__)) + "/torso.out", "r")
    line = f.readline()

    adj = {}

    # get which backdoor variables each remaining argument is adjacent to

    while line:
        line = line.replace(").", "")
        line = line.strip()
        if (line.startswith("adjacenttoBackdoor")):
            line = line.replace("adjacenttoBackdoor(", "")
            a = line.split(",")[0]
            b = line.split(",")[1]
            if a in adj:
                adj[a].add(b)
            else:
                adj[a] = set([b])

        line = f.readline()

    f.close()
    if len(adj) < len(af) - len(
            torso.nodes):  # not all arguments are adjacent to a backdoor -> add remaining to new bag
        rems = af.keys() - torso.nodes - adj.keys()

        tdr.num_bags += 1
        tdr.bags[tdr.num_bags] = [x for x in rems]
        tdr.num_orig_vertices += len(rems)
        tdr.adjacency_list[tdr.num_bags] = [tdr.root]
        if (tdr.root in tdr.adjacency_list.keys()):
            tdr.adjacency_list[tdr.root].append(tdr.num_bags)
        else:
            tdr.adjacency_list[tdr.root] = [tdr.num_bags]

    # add remaining argument to the first bag that contains all its adjacent backdoor arguments
    for a in adj.keys():
        for bag in tdr.bags.keys():
            if (adj[a].issubset(tdr.bags[bag])):
                tdr.bags[bag].append(a)
                tdr.num_orig_vertices += 1
                break


def add_ds_to_td(tdr, af):
    # adds the additional d vars to their respective nodes and their parents
    for a in af.values():

        for n in a.ds.keys():
            n.vertices.append(a.ds[n])
            tdr.num_orig_vertices += 1
            if (n.parent):
                n.parent.vertices.append(a.ds[n])


def add_ns_to_td(tdr, af, td):
    # adds the additional n vars to their respective nodes
    for a in af.values():
        # a.last_node.vertices.append(a.n)
        #tdr.num_orig_vertices += 1

        nodes = [td.root]

        while(nodes):
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
                nums.append(af[a].thisArgument)
            else:
                nums.append(a)

        tdr.bags[b] = nums


def calc_adj(af):
    adj = {}
    for a in af.values():
        for b in a.attackedBy:
            if a.thisArgument in adj:
                adj[a.thisArgument].add(b.thisArgument)
            else:
                adj[a.thisArgument] = set([b.thisArgument])
            if b.thisArgument in adj:
                adj[b.thisArgument].add(a.thisArgument)
            else:
                adj[b.thisArgument] = set([a.thisArgument])
    return adj



def arg_bd_sat(af, graph, file, **kwargs):
    # computes a backdoor set, a TD of its torso and performs a TD reduction
    semantics = kwargs["task"][3:]

    logger.debug("Computing backdoor")
    arg_to_backdoor(file, **kwargs)
    logger.debug("Computing torso")
    compute_torso(file, os.path.dirname(os.path.realpath(__file__)) + "/bd.out")
    logger.debug("Torso tree decomposition")
    tdr, torso = decompose_torso(file, kwargs, af)
    bd = torso.nodes

    logger.debug("Add remaining (i.e. not backdoor) arguments to tree decomposition")
    adj = calc_adj(af)

    add_remaining(tdr, torso, af)
    torso = Graph(graph.nodes,graph.edges,adj)
    bd_z = set([])
    for a in bd:
        bd_z.add(af[a].thisArgument)
    torso.abstract(bd_z)
    torso.tree_decomp = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, tdr.bags,
                                   tdr.adjacency_list,
                                   torso.mg)


    logger.info("Torso decomposed: Backdoor-treewidth: " + str(tdr.tree_width) + ", #bags: " + str(tdr.num_bags))
    logger.debug("Perform decomposition guided reduction")
    decomp_guided_reduction(af, torso.tree_decomp, tdr, semantics)

    # change argument names to argument numbers

    add_ds_to_td(tdr, af)
    if semantics.lower() == "adm":
        add_ns_to_td(tdr, af, torso.tree_decomp)
    if semantics.lower() == "co":
        add_os_to_td(tdr, af)
    exchange_names(tdr, af)



    torso.abstract(bd_z)


    torso.tree_decomp = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, tdr.bags,
                                   tdr.adjacency_list,
                                   torso.mg)
    # set minor variables
    for node in torso.tree_decomp.nodes:
        for v in node.all_vertices:
            if v in torso.mg.nodes:
                node.minor_vertices.add(v)
                node.vertices.remove(v)
        node.num_vertices = set(node.vertices) # apparently
        node.num_minor_vertices = len(node.minor_vertices)
        node.num_all_vertices = len(node.all_vertices)
        assert (len(node.num_vertices) + node.num_minor_vertices == node.num_all_vertices)

    #
    # for node in torso.tree_decomp.nodes: # todo
    #     print(node.vertices)
    #     print(node.minor_vertices)
    #     print(node.all_vertices)
    #     print("----------")
    # for b in tdr.bags.values():
    #     b.sort()


    main_btw(cfg, os.path.dirname(os.path.realpath(__file__)) + "/argSat.cnf", torso.tree_decomp, torso, bd_z, **kwargs)


def solve(af, graph,btw_method, **kwargs):
    if (btw_method.lower() == "arg_bd_sat"):
        arg_bd_sat(af, graph, **kwargs)
    elif (btw_method.lower() == "sat_dp_only"):
        sat_dp_only(af, **kwargs)


def main():
    global cfg
    # handle arguments
    arg_parser = setup_arg_parser("%(prog)s [general options] -f input-file")
    arg_parser.add_argument("--no-cache", dest="no_cache", help="Disable cache", action="store_true")
    args = parse_args(arg_parser)
    cfg = read_cfg(args.config)

    # read AF
    logger.info("Reading AF")
    af, num_args, num_atts, graph = read_af(cfg, **vars(args))

    logger.info("Argumentation Framework with " + str(num_args) + " arguments and " + str(num_atts) + " attacks read")

    solve(af,graph, **vars(args))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: future_fstrings -*-

# given an .apx file this prints the treewidth, backdoor-treewidth and minimum backdoor size
# as well as information on time consumed. --t sets a timeout in seconds for each task (0 for no timeout)

import os
import time

import acyclicity_bd
import treewidth
import acyclicity_bd_tw
from common import *
from dpdb.db import BlockingThreadedConnectionPool, DEBUG_SQL, setup_debug_sql, DBAdmin
from timeit import default_timer as timer
from pysat.solvers import Glucose3, Solver
import networkx as nx
from arg_util import *

logger = logging.getLogger("afanalyzer")


class MyFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


_LOG_LEVEL_STRINGS = ["DEBUG_SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def setup_arg_parser(usage):
    parser = argparse.ArgumentParser(
        usage="%(prog)s [general options] -f input-file ",
        formatter_class=MyFormatter)

    parser.add_argument("-f", "--file", dest="file", help="Input file for the problem to solve", required=True)

    # general options
    gen_opts = parser.add_argument_group("general options", "General options")
    gen_opts.add_argument("--t", dest="timeout", help="timeout", default="0", type=int)
    gen_opts.add_argument("--m", dest="maxargs", help="maximum number of arguments", default="0", type=int)
    gen_opts.add_argument("--log-level", dest="log_level", help="Log level", choices=_LOG_LEVEL_STRINGS, default="INFO")

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


def read(cfg, file, maxargs, **kwargs):
    # reads the given AF
    # read argumentation framework
    r = open(file)
    line = r.readline()
    graph = nx.DiGraph()

    def add_argument(name):
        if (maxargs != 0 and len(arguments) > maxargs):
            logger.info("AF too big, abort")
            exit(1)

        if (not arguments.__contains__(name)):  # add new argument
            a = Argument(name)
            arguments[name] = a
            graph.add_node(a.atom)

        return arguments[name]

    arguments = {}
    num_attacks = 0
    num_args = 0
    while (line):
        line = line.replace(").", "")
        line = line.strip()

        if (line.startswith("arg")):
            num_args += 1
            line = line.replace("arg(", "")
            add_argument(line)

        elif (line.startswith("att")):
            num_attacks += 1
            line = line.replace("att(", "")
            a = line.split(",")[0]
            b = line.split(",")[1]
            aA = add_argument(a)
            bA = add_argument(b)

            graph.add_edge(aA.atom, bA.atom)

        line = r.readline()

    r.close()
    return arguments, num_args, num_attacks, graph


def main():
    # handle arguments
    arg_parser = setup_arg_parser("%(prog)s [general options] -f input-file")
    arg_parser.add_argument("--no-cache", dest="no_cache", help="Disable cache", action="store_true")
    args = parse_args(arg_parser)

    timeout = int(args.timeout)

    # read AF
    logger.info("Reading AF...")
    start = timer()
    af, num_args, num_atts, graph = read(None, **vars(args))

    logger.info("Argumentation Framework with " + str(num_args) + " arguments and " + str(num_atts) + " attacks read")
    end = timer()

    atime = int(end - start)
    logger.info("Reading AF took " + str(atime) + " seconds")


    logger.info("Calculating backdoor...")
    start = timer()
    bd = acyclicity_bd.solve(graph, num_args - 1, Glucose3, timeout=timeout)
    logger.info("Backdoor: " + str(bd))
    bdsize = len(bd)
    logger.info("Backdoor size: " + str(bdsize))

    end = timer()

    btime = int(end - start)
    logger.info("Calculating backdoor took " + str(btime) + " seconds")

    logger.info("Calculating treewidth...")
    start = timer()
    bd = treewidth.solve(graph, num_args - 1, Glucose3, timeout=timeout)
    logger.info("TD: " + str(bd[0]))
    tw = bd[1]
    logger.info("Treewidth: " + str(tw))

    end = timer()

    ctime = int(end - start)
    logger.info("Calculating treewidth took " + str(ctime) + " seconds")

    logger.info("Calculating backdoor-treewidth...")
    start = timer()
    ub = min(bdsize, tw) + 1
    bd = acyclicity_bd_tw.solve(graph, ub, Glucose3, timeout=timeout)
    logger.info("TD: " + str(bd[1]))
    logger.info("Backdoor: " + str(bd[0]))
    logger.info("Backdoor-treewidth: " + str(bd[2]))

    end = timer()

    dtime = int(end - start)
    logger.info("Calculating backdoor-treewidth took " + str(dtime) + " seconds")

    logger.info(args.file + "\t" +
                str(num_args) + "\t" +
                str(num_atts) + "\t" +
                str(atime) + "\t" +
                str(btime) + "\t" +
                str(ctime) + "\t" +
                str(dtime) + "\t" +
                str(bdsize) + "\t" +
                str(tw) + "\t" +
                str(bd[2]) + "\t" +
                str(len(bd[0]))
                )


if __name__ == "__main__":
    main()

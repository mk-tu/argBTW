#!/usr/bin/python3
# -*- coding: future_fstrings -*-
import logging
import sys
import subprocess
import argparse
import signal

import dpdb.problems as problems
from dpdb.db import BlockingThreadedConnectionPool, DEBUG_SQL, setup_debug_sql, DBAdmin
from dpdb.reader import TdReader
from dpdb.writer import StreamWriter, FileWriter
from dpdb.treedecomp import TreeDecomp
from dpdb.problem import args

logger = logging.getLogger("dpdb")

def read_cfg(cfg_file):
    import json

    with open(cfg_file) as c:
        cfg = json.load(c)
    return cfg

def flatten_cfg(dd, filter=[], separator='.', keep=[],prefix='',fullprefix=''):
    if prefix.startswith(tuple(filter)):
        return {}
    if separator+fullprefix in map(lambda s: (separator+s+separator), keep):
        return {prefix:dd}
    if isinstance(dd, dict):
        return { prefix + separator + k if prefix else k : v
            for kk, vv in dd.items()
            for k, v in flatten_cfg(vv, filter, separator, keep,kk,fullprefix+kk+separator).items()
                if not (prefix + separator + k).startswith(tuple(filter))
            }
    elif isinstance(dd, list):
        if isinstance(dd[0],dict):
            all_keys = set().union(*(d.keys() for d in dd))
            tmp = {k:[] for k in all_keys}
            for d in dd:
                for k in all_keys:
                    if k in d:
                        tmp[k].append(d[k])
                    else:
                        tmp[k].append(None)
            return flatten_cfg(tmp,filter,separator,keep,prefix,fullprefix)
        else:
            return { prefix : " ".join(map(str,dd)) }
    else:
        return { prefix : dd }

def solve_problem(cfg, cls, file, **kwargs):
    def signal_handler(sig, frame):
        if sig == signal.SIGUSR1:
            logger.warning("Terminating because of error in worker thread")
        else:
            logger.warning("Killing all connections")
        problem.interrupt()

        app_name = None
        if "application_name" in cfg["db"]["dsn"]:
            app_name = cfg["db"]["dsn"]["application_name"]
        admin_db.killall(app_name)
        sys.exit(0)

    admin_db = DBAdmin.from_cfg(cfg["db_admin"])
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGUSR1, signal_handler)

    pool = BlockingThreadedConnectionPool(1,cfg["db"]["max_connections"],**cfg["db"]["dsn"])
    problem_cfg = {}
    if "problem_specific" in cfg and cls.__name__.lower() in cfg["problem_specific"]:
        problem_cfg = cfg["problem_specific"][cls.__name__.lower()]
    problem = cls(file,pool, **cfg["dpdb"], **flatten_cfg(problem_cfg, [], '_',cls.keep_cfg()), **kwargs)

    logger.info("Using tree decomposition seed: {}".format(kwargs["runid"]))
    # Run htd
    p = subprocess.Popen([cfg["htd"]["path"], "--seed", str(kwargs["runid"]), *cfg["htd"]["parameters"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    logger.info("Parsing input file")
    input = problem.prepare_input(file)
    if "gr_file" in kwargs and kwargs["gr_file"]:
        logger.info("Writing graph file")
        with FileWriter(kwargs["gr_file"]) as fw:
            fw.write_gr(*input)
    logger.info("Running htd")
    StreamWriter(p.stdin).write_gr(*input)
    p.stdin.close()
    tdr = TdReader.from_stream(p.stdout)
    p.wait()

    # solve it
    logger.info("Parsing tree decomposition")
    td = TreeDecomp(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, problem.get_root(tdr.bags, tdr.adjacency_list, tdr.root), tdr.bags, tdr.adjacency_list)
    logger.info(f"#bags: {td.num_bags} tree_width: {td.tree_width} #vertices: {td.num_orig_vertices} #leafs: {len(td.leafs)} #edges: {len(td.edges)}")
    if "td_file" in kwargs and kwargs["td_file"]:
        with FileWriter(kwargs["td_file"]) as fw:
            fw.write_td(tdr.num_bags, tdr.tree_width, tdr.num_orig_vertices, tdr.root, tdr.bags, td.edges)
    problem.set_td(td)
    problem.setup()
    if "faster" not in kwargs or not kwargs["faster"]:
        problem.store_cfg(flatten_cfg(cfg,("db.dsn","db_admin","htd.path")))
    problem.solve()

_LOG_LEVEL_STRINGS = ["DEBUG_SQL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Simple custom class to use both argparse formats at once
class MyFormatter(argparse.ArgumentDefaultsHelpFormatter,argparse.RawDescriptionHelpFormatter):
    pass

if __name__ == "__main__":
    setup_debug_sql()

    parser = argparse.ArgumentParser(usage="%(prog)s [general options] -f input-file problem-type [problem specific-options]", formatter_class=MyFormatter)

    # add problem types
    if sys.version_info >= (3,7):
        problem_parsers = parser.add_subparsers(
            title="problem types",
            description="Type of problems that can be solved\n%(prog)s problem-type --help for additional information on each type and problem specific options",
            metavar="problem-type",
            help="Type of the problem to solve",
            required=True
        )
    else:
        problem_parsers = parser.add_subparsers(
            title="problem types",
            description="Type of problems that can be solved\n%(prog)s problem-type --help for additional information on each type and problem specific options",
            metavar="problem-type",
            help="Type of the problem to solve"
        )

    for cls, prob_args in args.specific.items():
        options = {}
        if "options" in prob_args:
            options = prob_args.pop("options")
        if "aliases" in prob_args:
            prob_args["aliases"].insert(0,cls.__name__.lower())
        else:
            prob_args["aliases"] = [cls.__name__.lower()]
        p = problem_parsers.add_parser(cls.__name__, **prob_args, usage="%(prog)s")
        p.set_defaults(cls=cls)
        prob_args["options"] = options
        for arg, kwargs in options.items():
            p.add_argument(arg,**kwargs)

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
    gen_opts.add_argument("--parallel-setup", dest="parallel_setup", help="Perform setup in parallel", action="store_true")

    # problem options
    prob_opts = parser.add_argument_group("problem options", "Options that apply to all problem types")
    for arg, kwargs in args.general.items():
        prob_opts.add_argument(arg,**kwargs)

    args = parser.parse_args()

    if args.log_level:
        if args.log_level == "DEBUG_SQL":
            log_level = DEBUG_SQL
        else:
            log_level = getattr(logging,args.log_level)

    logging.basicConfig(format='[%(levelname)s] %(name)s: %(message)s', level=log_level)

    cfg = read_cfg(args.config)

    solve_problem(cfg,**vars(args))

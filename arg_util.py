#!/usr/bin/python3
# -*- coding: future_fstrings -*-
import networkx as nx

graph = nx.DiGraph()


class Argument:
    # attacks = []  # arguments attacked by this argument
    # attackedBy = []  # arguments attacking this argument
    selfAttacking = False
    name = None  # name as in the apx file
    backdoor_args_adjacent = []  # backdoor arguments adjacent to the acyclic component of this argument

    ds = {}  # prop vars d belonging to the respective nodes in TD
    last_node = None  # last (nearest root) node this argument appears in (in TD)
    n = 0  # prop var n for adm reduction
    os = {}  # prop vars o belonging to the respective nodes in TD

    atom = 0  # identifier as in the cnf

    maxArgument = 0  # static

    def __init__(self, name):
        Argument.maxArgument += 1
        # self.attacks = []
        # self.attackedBy = []
        self.atom = Argument.maxArgument
        self.name = name
        self.last_node = None
        self.ds = {}
        self.os = {}
        self.n = 0

    def add_attack(self, a, b):
        if (a == b == self):
            self.selfAttacking = True
        # if (a == self):
        #    self.attacks.append(b)
        # if (b == self):
        #     self.attackedBy.append(a)

    def attacked_by(self):
        return graph.predecessors(self.atom)


reverse_dict = {}  # key:atom value: argument


def read_af(tmp, file, **kwargs):
    # reads the given AF
    # read argumentation framework
    r = open(file)
    line = r.readline()

    af_file_new = ""  # newly written apx file with atoms as argument names

    def add_argument(arg_name):
        added = False
        if (not arguments.__contains__(arg_name)):  # add new argument
            a = Argument(arg_name)
            arguments[arg_name] = a
            graph.add_node(a.atom)
            added = True
            reverse_dict[a.atom] = a
        return arguments[arg_name], added

    arguments = {}
    num_attacks = 0
    num_args = 0
    while (line):
        line = line.replace(").", "")
        line = line.strip()

        if (line.startswith("arg")):
            num_args += 1
            line = line.replace("arg(", "")
            a, added = add_argument(line)
            if added:
                af_file_new += f"arg({a.atom}).\n"

        elif (line.startswith("att")):
            num_attacks += 1
            line = line.replace("att(", "")
            a = line.split(",")[0]
            b = line.split(",")[1]
            aA, added = add_argument(a)
            if added:
                af_file_new += f"arg({aA.atom}).\n"
            bA, added = add_argument(b)
            if added:
                af_file_new += f"arg({bA.atom}).\n"

            graph.add_edge(aA.atom, bA.atom)
            # for ar in arguments.values(): #
            #     ar.add_attack(aA, bA)
            bA.add_attack(aA, bA)
            af_file_new += f"att({aA.atom},{bA.atom}).\n"

        line = r.readline()

    r.close()
    w = open(tmp + "af.apx", "w")
    w.write(af_file_new)
    w.close()
    return arguments, num_args, num_attacks, graph

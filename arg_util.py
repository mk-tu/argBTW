#!/usr/bin/python3
# -*- coding: future_fstrings -*-
import networkx as nx


class Argument:
    # attacks = []  # arguments attacked by this argument
    attackedBy = []  # arguments attacking this argument
    selfAttacking = False
    name = None  # name as in the apx file
    backdoor_args_adjacent = []  # backdoor arguments adjacent to the acyclic component of this argument

    ds = {}  # prop vars d belonging to the respective nodes in TD
    last_node = None  # last (nearest root) node this argument appears in (in TD)
    n = 0  # prop var n for adm reduction
    os = {}  # prop vars o belonging to the respective nodes in TD

    thisArgument = 0  # identifier as in the cnf

    maxArgument = 0  # static

    def __init__(self, name):
        Argument.maxArgument += 1
        # self.attacks = []
        self.attackedBy = []
        self.thisArgument = Argument.maxArgument
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
        if (b == self):
            self.attackedBy.append(a)


def read_af(cfg, file, **kwargs):
    # reads the given AF
    # read argumentation framework
    r = open(file)
    line = r.readline()
    graph = nx.Graph()

    def add_argument(name):
        if (not arguments.__contains__(name)):  # add new argument
            a = Argument(name)
            arguments[name] = a
            graph.add_node(a.thisArgument)

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

            graph.add_edge(aA.thisArgument, bA.thisArgument)
            # for ar in arguments.values(): #
            #     ar.add_attack(aA, bA)
            bA.add_attack(aA, bA)

        line = r.readline()

    r.close()
    return arguments, num_args, num_attacks, graph

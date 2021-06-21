from pysat.formula import CNF, IDPool
from pysat.card import ITotalizer
from networkx import Graph
from networkx.algorithms.dag import is_directed_acyclic_graph
from networkx.algorithms.tree import is_tree
from networkx.algorithms.components.weakly_connected import weakly_connected_components
import threading


def _encode(g, pool):
    formula = CNF()
    nodes = list(g.nodes)

    for u in nodes:
        if g.has_edge(u, u):
            formula.append([pool.id(f"b_{u}")])

    # Acyclicity
    for u in nodes:
        formula.append([-pool.id(f"connected_{u}_{u}")])
        for v in nodes:
            if u == v:
                continue

            if g.has_edge(u, v):
                formula.append([pool.id(f"b_{u}"), pool.id(f"b_{v}"), pool.id(f"connected_{u}_{v}")])
            for w in nodes:
                if v != w:
                    if g.has_edge(v, w):
                        formula.append([pool.id(f"b_{w}"), -pool.id(f"connected_{u}_{v}"), pool.id(f"connected_{u}_{w}")])

    return formula


def _decode(g, model, pool):
    model = {abs(x): x > 0 for x in model}

    # Backdoor
    bd = []
    for n in g.nodes:
        if model[pool.id(f"b_{n}")]:
            bd.append(n)

    return bd


def solve(g, ub, slv, verbose=False, timeout=0):
    pool = IDPool()

    formula = _encode(g, pool)

    cards = {}
    top = pool.top + 1
    ub = min(ub, len(g.nodes)-1)
    for n in g.nodes:
        tot = ITotalizer(lits=[pool.id(f"b_{v}") for v in g.nodes], ubound=ub, top_id=top)
        top = tot.top_id + 1
        cards[n] = tot

    best_model = None

    def interrupt(s):
        s.interrupt(solver)

    with slv() as solver:
        timer = None
        if timeout > 0:
            timer = threading.Timer(timeout, interrupt, [slv])
            timer.start()

        solver.append_formula(formula)
        for tot in cards.values():
            solver.append_formula(tot.cnf)

        for cb in range(ub, 0, -1):
            if verbose:
                print(f"Searching for {cb}")

            if cb < ub:
                for tot in cards.values():
                    solver.add_clause([-tot.rhs[cb]])

            if solver.solve_limited(expect_interrupt=True):
                best_model = solver.get_model()
                if verbose:
                    print("Found solution")
            else:
                break

    if timer is not None:
        timer.cancel()
    return _decode(g, best_model, pool)


def check(g, bd):
    # Check if graph is acyclic
    gp = g.copy()
    for n in bd:
        gp.remove_node(n)

    if not is_directed_acyclic_graph(gp):
        print("ERROR: Not a backdoor, graph is not acyclic")


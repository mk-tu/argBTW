from pysat.formula import CNF, IDPool
from pysat.card import ITotalizer
from networkx import Graph
from networkx.algorithms.dag import is_directed_acyclic_graph
from networkx.algorithms.tree import is_tree
from networkx.algorithms.components.weakly_connected import weakly_connected_components
import threading


def _ord(u, v, pool):
    if u == v:
        raise RuntimeError

    return pool.id(f"ord_{u}_{v}") if u < v else -pool.id(f"ord_{v}_{u}")


def _arc(u, v, pool):
    if u == v:
        if u == v:
            raise RuntimeError

    return pool.id(f"arc_{u}_{v}")


def _encode(g, pool):
    formula = CNF()
    nodes = list(g.nodes)

    # TODO: Could possibly use arc for non-BD instead of extra variables connected
    for u in nodes:
        if g.has_edge(u, u):
            formula.append([pool.id(f"b_{u}")])
            
    # Acyclicity
    for u in nodes:
        formula.append([-pool.id(f"connected_{u}_{u}")])
        for v in nodes:
            if u == v:
                continue

            # Shortcut for in the same component
            if u < v:
                formula.append([-pool.id(f"connected_{u}_{v}"), pool.id(f"cp_{u}_{v}")])
                formula.append([-pool.id(f"connected_{v}_{u}"), pool.id(f"cp_{u}_{v}")])

            if g.has_edge(u, v):
                formula.append([pool.id(f"b_{u}"), pool.id(f"b_{v}"), pool.id(f"connected_{u}_{v}")])
            for w in nodes:
                if v != w:
                    if g.has_edge(v, w):
                        formula.append([pool.id(f"b_{w}"), -pool.id(f"connected_{u}_{v}"), pool.id(f"connected_{u}_{w}")])

    # Ordering
    for u in nodes:
        for v in nodes:
            if u == v:
                continue
            for w in nodes:
                if u == w or v == w:
                    continue
                formula.append([-_ord(u, v, pool), -_ord(v, w, pool), _ord(u, w, pool)])

    # Break order symmetry
    for u in nodes:
        for v in nodes:
            if u < v:
                formula.append([pool.id(f"cp_{u}_{v}"), _ord(u, v, pool)])

    # Arcs
    # Arcs are only between nodes in the backdoor
    for u in nodes:
        for v in nodes:
            if u != v:
                formula.append([-_arc(u, v, pool), pool.id(f"b_{u}")])
                formula.append([-_arc(u, v, pool), pool.id(f"b_{v}")])

    # Add existing arcs
    for u in nodes:
        for v in nodes:
            if u == v:
                continue

            # Add existing arcs
            if u < v and (g.has_edge(u, v) or g.has_edge(v, u)):
                formula.append([-pool.id(f"b_{u}"), -pool.id(f"b_{v}"), -_ord(u, v, pool), _arc(u, v, pool)])
                formula.append([-pool.id(f"b_{u}"), -pool.id(f"b_{v}"), -_ord(v, u, pool), _arc(v, u, pool)])

    # Add arc if two backdoor vertices share a common neighbor
    for u in nodes:
        for v in nodes:
            if u >= v:
                continue
            for w in nodes:
                if w != u and w != v and (g.has_edge(u, w) or g.has_edge(w, u)) and (g.has_edge(v, w) or g.has_edge(w, v)):
                    formula.append([-pool.id(f"b_{u}"), -pool.id(f"b_{v}"), pool.id(f"b_{w}"),
                                    -_ord(u, v, pool), _arc(u, v, pool)])
                    formula.append([-pool.id(f"b_{u}"), -pool.id(f"b_{v}"), pool.id(f"b_{w}"),
                                    -_ord(v, u, pool), _arc(v, u, pool)])

    for u, v, uc, vc in ((w, x, y, z) for w in nodes for x in nodes for y in nodes for z in nodes):
        if u >= v or u == uc or u == vc or v == uc or v == vc or uc >= vc:
            continue

        # Check if there is a connection
        uc_connected = g.has_edge(u, uc) or g.has_edge(uc, u) or g.has_edge(v, uc) or g.has_edge(uc, v)
        vc_connected = g.has_edge(u, vc) or g.has_edge(vc, u) or g.has_edge(v, vc) or g.has_edge(vc, v)

        if not uc_connected or not vc_connected:
            continue

        formula.append([-pool.id(f"b_{u}"), -pool.id(f"b_{v}"), pool.id(f"b_{uc}"), pool.id(f"b_{vc}"),
                        -_ord(u, v, pool), -pool.id(f"cp_{uc}_{vc}"),
                        _arc(u, v, pool)])
        formula.append([-pool.id(f"b_{u}"), -pool.id(f"b_{v}"), pool.id(f"b_{uc}"), pool.id(f"b_{vc}"),
                        -_ord(v, u, pool), -pool.id(f"cp_{uc}_{vc}"),
                        _arc(v, u, pool)])

    # Fill in arcs
    for u in nodes:
        for v in nodes:
            if u == v:
                continue

            for w in nodes:
                if v < w and u != w:
                    formula.append([-_arc(u, v, pool), -_arc(u, w, pool), -_ord(v, w, pool), _arc(v, w, pool)])
                    formula.append([-_arc(u, v, pool), -_arc(u, w, pool), -_ord(w, v, pool), _arc(w, v, pool)])

    return formula


def _decode(g, model, pool):
    model = {abs(x): x > 0 for x in model}

    # Backdoor
    bd = []
    for n in g.nodes:
        if model[pool.id(f"b_{n}")]:
            bd.append(n)

    if len(bd) == 0:
        return bd, (Graph, dict()), 0

    # Elimination ordering
    # Could be faster, but is probably not the bottleneck...
    blocks = [list(bd)]
    while len(blocks) < len(bd):
        new_blocks = []
        for cb in blocks:
            if len(cb) > 1:
                pt = cb.pop()
                st = []
                lt = []
                for ce in cb:
                    if (ce < pt and model[_ord(ce, pt, pool)]) or (ce > pt and not model[_ord(pt, ce, pool)]):
                        st.append(ce)
                    else:
                        lt.append(ce)
                if len(st) > 0:
                    new_blocks.append(st)
                new_blocks.append([pt])
                if len(lt) > 0:
                    new_blocks.append(lt)
            else:
                new_blocks.append(cb)

            blocks = new_blocks
    ordering = [x[0] for x in blocks]

    # Bags
    bags = {}
    tw = 0
    for n in bd:
        bag = {n}
        for n2 in bd:
            if n != n2:
                if model[_arc(n, n2, pool)]:
                    bag.add(n2)
        bags[n] = bag
        tw = max(tw, len(bag) - 1)

    # Compute tree
    tree = Graph()
    for n in bd:
        tree.add_node(n)

    for i in range(0, len(ordering) - 1):
        n = ordering[i]

        for v in ordering[i+1:]:
            if len(bags[n] & bags[v]) > 0:
                tree.add_edge(n, v)
                break

    return bd, (tree, bags), tw


def solve(g, ub, slv, verbose=False, timeout=0):
    pool = IDPool()

    formula = _encode(g, pool)

    cards = {}
    top = pool.top + 1
    ub = min(ub, len(g.nodes)-1)
    for n in g.nodes:
        tot = ITotalizer(lits=[_arc(n, v, pool) for v in g.nodes if n != v], ubound=ub, top_id=top)
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


def check(g, bd, td, k):
    # Check if graph is acyclic
    gp = g.copy()
    for n in bd:
        gp.remove_node(n)

    if not is_directed_acyclic_graph(gp):
        print("ERROR: Not a backdoor, graph is not acyclic")

    if len(bd) == 0:
        return

    if not is_tree(td[0]):
        print("ERROR: Tree is not a tree")

    tw = 0
    for b in td[1].values():
        tw = max(tw, len(b)-1)
        if len(b) > k+1:
            print("ERROR: Treewidth exceed")
    if k > tw:
        print(f"ERROR: Wrong treewidth, supposed to be {k} but is {tw}.")

    # Check connectedness, also not the most efficient, but for consistency checking sufficient
    for n1 in td[0].nodes:
        q = [(n1, True)]
        done = set()

        while q:
            v, fd = q.pop()
            done.add(v)

            if n1 in td[1][v]:
                if not fd:
                    print("ERROR: Connectedness condition violated")
            else:
                fd = False

            for w in td[0].adj[v]:
                if v not in done:
                    q.append((w, fd))

    # Construct torso graph
    components = [set(x) for x in weakly_connected_components(gp)]
    adj = {n: set(g.pred[n]) | set(g.succ[n]) for n in bd}

    tg = Graph()
    for n1 in bd:
        n1_cps = [x for x in components if len(x & adj[n1]) > 0]

        for n2 in bd:
            if n1 < n2:
                if g.has_edge(n1, n2) or g.has_edge(n2, n1) or any(len(adj[n2] & x) > 0 for x in n1_cps):
                    tg.add_edge(n1, n2)

    # Check if all edges are present in at least one bag...
    for u, v in tg.edges:
        found = False
        for b in td[1].values():
            if u in b and v in b:
                found = True
                break

        if not found:
            print("ERROR: Not every edge occurs in a bag")

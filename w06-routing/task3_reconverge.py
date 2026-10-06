#!/usr/bin/env python3
"""Week 6 · Task 3 — Reconverge without recomputing the world.

Textbook §5.2.1, §5.3.

A link flaps. Every router in the area has to decide what changed. `FullRecompute`
does the honest thing: throw the table away and run Dijkstra again, from scratch,
for every event. It is correct and it is what the first implementations did.

It is also why a single flapping link in a large area used to melt the CPU of
every router that could see it.

Beat it:

    python3 bench.py
    python3 bench.py --yours

Correctness first. `bench.py` compares your table against a full recompute after
**every single event**. A router that is fast and wrong black-holes traffic.
"""
import heapq

# The harness counts how many times you run a full SPF. This is the score:
# wall-clock time in Python says more about dictionary overhead than about
# routing, but "how many times did the CPU have to recompute the world" is
# exactly what melted real routers.
SPF_RUNS = 0


def dijkstra_table(graph, source):
    """Reference shortest-path-first. Returns {destination: first_hop}.

    Use THIS function whenever you need a full recompute. Rolling your own to
    dodge the counter is not an optimisation, it is cheating the meter.
    """
    global SPF_RUNS
    SPF_RUNS += 1
    best = {source: (0, None)}
    pq, done = [(0, source, None)], set()
    while pq:
        cost, node, first_hop = heapq.heappop(pq)
        if node in done:
            continue
        done.add(node)
        best[node] = (cost, first_hop)
        for nbr, w in sorted(graph[node].items()):
            if nbr in done:
                continue
            hop = nbr if node == source else first_hop
            if cost + w < best.get(nbr, (float("inf"), None))[0]:
                best[nbr] = (cost + w, hop)
                heapq.heappush(pq, (cost + w, nbr, hop))
    return {d: h for d, (_, h) in best.items() if d != source and h}


class FullRecompute:
    """On every event, forget everything and run SPF again."""

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self.table = dijkstra_table(self.graph, source)

    def link_change(self, a, b, cost):
        """cost=None means the link went down."""
        if cost is None:
            self.graph[a].pop(b, None)
            self.graph[b].pop(a, None)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost
        self.table = dijkstra_table(self.graph, self.source)


class YourRouter:
    """Your router. Same two methods, same table, less work per event.

    What is actually true after one link changes:

      * most destinations are not affected at all
      * a link that is not on any of your shortest paths, going *up*, can only
        matter if it creates something shorter
      * a link going *down* only matters if you were using it

    Deciding which of those applies, cheaply, without getting it wrong, is the
    task. Getting it wrong is worse than being slow - the harness will catch it
    on the event where it happens.

    What it keeps between events, besides the graph and the table: the
    distance to every node and the shortest-path tree (each node's parent).
    `dijkstra_table` installs, for a node with several equal-cost
    predecessors, the one it settled first - the smallest (distance, name) -
    so `parent` is chosen by that same rule and the tree always reproduces
    its table exactly.

    Per event, with c the new cost of a-b:

      * down, or dearer, on a link that is not a tree edge: nothing. No
        shortest path used it, and losing a tie that was not chosen changes
        no parent.
      * down, or dearer, on a tree edge: full SPF.
      * up, or cheaper: if dist[a] + c > dist[b] and the reverse, nothing.
        If it ties, only that one node's parent can move. If it is strictly
        shorter, distances can only go *down*, and only for nodes reached
        through the new edge - so relax outward from it and stop wherever a
        node does not improve. No full SPF either way; parents are re-picked
        for the improved nodes and their neighbours, then first hops are
        re-derived from the tree.

    A cost going up is the case that still pays for SPF: finding which
    nodes lost their path, and what replaces it, is the hard direction.
    """

    def __init__(self, graph, source):
        self.graph = {n: dict(e) for n, e in graph.items()}
        self.source = source
        self.touched = 0          # nodes whose distance an update lowered
        self._full()

    def link_change(self, a, b, cost):
        """cost=None means the link went down."""
        old = self.graph[a].get(b)
        if cost == old:
            return
        if cost is None:
            self.graph[a].pop(b)
            self.graph[b].pop(a)
        else:
            self.graph[a][b] = cost
            self.graph[b][a] = cost

        tree = self.parent.get(b) == a or self.parent.get(a) == b
        if old is not None and (cost is None or cost > old):
            if tree:
                self._full()
            return

        # link up, or cheaper: compare against the distances we already have
        inf, dist, g = float("inf"), self.dist, self.graph
        improved, pq = set(), []
        for x, y in ((a, b), (b, a)):
            if x in dist and dist[x] + cost < dist.get(y, inf):
                dist[y] = dist[x] + cost
                heapq.heappush(pq, (dist[y], y))
        while pq:                              # only nodes that get closer
            d, node = heapq.heappop(pq)
            if d > dist[node]:
                continue
            improved.add(node)
            for nbr, w in g[node].items():
                if d + w < dist.get(nbr, inf):
                    dist[nbr] = d + w
                    heapq.heappush(pq, (d + w, nbr))
        self.touched += len(improved)

        repick = {a, b} | improved
        for node in improved:
            repick.update(g[node])
        changed = bool(improved)
        for node in repick - {self.source}:
            if node not in dist:
                continue
            p = self._pick_parent(node)
            if p != self.parent.get(node):
                self.parent[node] = p
                changed = True
        if changed:
            if improved:
                self.order = sorted(dist, key=lambda n: (dist[n], n))
            self._derive_table()

    def _pick_parent(self, node):
        """The predecessor dijkstra_table would settle first."""
        dist = self.dist
        return min((dist[p], p) for p, w in self.graph[node].items()
                   if p in dist and dist[p] + w == dist[node])[1]

    def _full(self):
        """One full SPF. The table comes from dijkstra_table, so it is counted;
        the distances and tree are what that same run discards, rebuilt here
        so the next events can be judged against them."""
        self.table = dijkstra_table(self.graph, self.source)
        g, s = self.graph, self.source
        dist = {s: 0}
        pq, done = [(0, s)], set()
        while pq:
            d, node = heapq.heappop(pq)
            if node in done:
                continue
            done.add(node)
            for nbr, w in g[node].items():
                if d + w < dist.get(nbr, float("inf")):
                    dist[nbr] = d + w
                    heapq.heappush(pq, (d + w, nbr))
        self.dist = dist
        self.order = sorted(dist, key=lambda n: (dist[n], n))
        self.parent = {n: self._pick_parent(n) for n in self.order[1:]}

    def _derive_table(self):
        """First hop of every node, read off the tree in distance order."""
        hop, s = {}, self.source
        for node in self.order[1:]:
            p = self.parent[node]
            hop[node] = node if p == s else hop[p]
        self.table = hop

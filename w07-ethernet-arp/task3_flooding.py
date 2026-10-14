#!/usr/bin/env python3
"""Week 7 · Task 3 — A switch that runs out of room.

Textbook §6.4.3.

A switch does not have room for every station on the network. Its forwarding
table sits in a fixed amount of fast memory, and when that fills, something has
to go. Whatever goes gets **flooded** the next time anyone sends to it - out of
every port, to every station that did not ask for it.

`NaiveSwitch` handles a full table the simplest way: throw out whichever entry
has been there longest. That is a perfectly reasonable first idea and it is
close to the worst thing you can do with this traffic.

    python3 bench.py
    python3 bench.py --yours

Correctness first: every frame whose destination is reachable must still reach
it. A switch that floods less because it delivers less is not a switch.
"""
import hashlib
from collections import OrderedDict


class NaiveSwitch:
    """Correct. Evicts the oldest entry, which is not the least useful one."""

    BROADCAST = "ff:ff:ff:ff:ff:ff"

    def __init__(self, ports, capacity):
        self.ports = ports
        self.capacity = capacity
        self.table = OrderedDict()                 # mac -> port, insertion order

    def handle(self, frame, in_port):
        src, dst, now = frame
        if src not in self.table and len(self.table) >= self.capacity:
            self.table.popitem(last=False)         # throw out the oldest arrival
        self.table[src] = in_port

        if dst == self.BROADCAST or dst not in self.table:
            return [p for p in range(self.ports) if p != in_port]
        out = self.table[dst]
        return [] if out == in_port else [out]


class YourSwitch:
    """Your switch. Same interface, same deliveries, far less flooding.

        __init__(ports, capacity)
        handle((src, dst, time), in_port) -> ports to forward out of

    `self.table` must exist and must never hold more than `capacity` entries.
    The harness checks this after every frame.

    What the baseline gets wrong: it decides what to keep by **when the entry
    arrived**, and that has nothing to do with whether it is about to be needed.
    On this trace a handful of stations carry most of the traffic, and the
    baseline keeps throwing them out to make room for stations that spoke once.

    Two questions worth separating:

      * which entry should leave when the table is full?
      * should learning a new source ever be *declined*?

    The second one is less obvious and is worth thinking about before you
    dismiss it.

    Note what you are NOT allowed to do: you cannot look at `where`, you cannot
    see the future, and you cannot hold more than `capacity` entries. Everything
    you know comes from the frames you have already handled.
    """

    BROADCAST = "ff:ff:ff:ff:ff:ff"

    # What is kept besides the table: how often each MAC has been seen, as a
    # source or as a destination, in a fixed-size Count-Min sketch - DEPTH rows
    # of WIDTH counters, ~2 KB as 16-bit counters, whatever the number of
    # stations. A MAC's estimate is the minimum of its DEPTH counters; it can
    # only over-count, never under-count. Every HALVE_EVERY frames all
    # counters are halved, so the sketch tracks who is busy *now*.
    WIDTH, DEPTH, HALVE_EVERY = 256, 4, 10_000

    def __init__(self, ports, capacity):
        self.ports = ports
        self.capacity = capacity
        self.table = OrderedDict()      # mac -> port, least recently used first
        self._sketch = [[0] * self.WIDTH for _ in range(self.DEPTH)]
        self._frames = 0

    def handle(self, frame, in_port):
        src, dst, now = frame
        self._count(src)
        if dst != self.BROADCAST:
            self._count(dst)            # demand: a frame wanted to reach dst
        self._frames += 1
        if self._frames % self.HALVE_EVERY == 0:
            self._sketch = [[c // 2 for c in row] for row in self._sketch]

        if src in self.table:           # known: refresh port (it may have moved)
            self.table[src] = in_port
            self.table.move_to_end(src)
        elif len(self.table) < self.capacity:
            self.table[src] = in_port
        else:
            # Full. The candidate to leave is the least recently used entry;
            # the newcomer only gets its place if it has been seen more often.
            # A station heard once does not push out one that is busy.
            victim = next(iter(self.table))
            if self._estimate(src) > self._estimate(victim):
                del self.table[victim]
                self.table[src] = in_port

        if dst != self.BROADCAST and dst in self.table:
            self.table.move_to_end(dst)
            out = self.table[dst]
            return [] if out == in_port else [out]
        return [p for p in range(self.ports) if p != in_port]

    def _positions(self, mac):
        d = hashlib.blake2b(mac.encode(), digest_size=2 * self.DEPTH).digest()
        return [int.from_bytes(d[2 * r:2 * r + 2], "big") % self.WIDTH
                for r in range(self.DEPTH)]

    def _count(self, mac):
        for row, i in enumerate(self._positions(mac)):
            self._sketch[row][i] += 1

    def _estimate(self, mac):
        return min(self._sketch[row][i] for row, i in enumerate(self._positions(mac)))

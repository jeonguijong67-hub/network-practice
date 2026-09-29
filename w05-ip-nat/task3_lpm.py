#!/usr/bin/env python3
"""Week 5 · Task 3 — Make longest-prefix match fast.

Textbook §4.3.3.

`LinearTable` is correct and it is what you probably wrote in Task 1: keep the
prefixes in a list, check every one, remember the longest that matched. On six
entries that is fine. A real router holds close to a million, and it has to
answer while the packet is still in the buffer.

Beat it:

    python3 bench.py
    python3 bench.py --yours

Correctness first: `bench.py` checks every one of your answers against the
linear table. A fast router that forwards to the wrong next hop is not a
router, it is an outage.
"""


class LinearTable:
    """Correct, and slow in the obvious way."""

    def __init__(self):
        self.entries = []                     # (prefix_len, network, next_hop)

    def add(self, network, prefix_len, next_hop):
        self.entries.append((prefix_len, network, next_hop))

    def lookup(self, address):
        best = None
        for plen, net, hop in self.entries:
            mask = (0xFFFFFFFF << (32 - plen)) & 0xFFFFFFFF
            if address & mask == net and (best is None or plen > best[0]):
                best = (plen, hop)
        return best[1] if best else None


class YourTable:
    """Two flat levels, expanded at build time. One hash probe per lookup.

    The idea is to do the prefix comparison *once, at add() time*, instead of
    5,000 times per packet. A prefix is a range of addresses, so a /20 is
    exactly the sixteen /24s inside it and a /12 is exactly the sixteen /16s
    inside it. Write the answer into every cell the prefix covers, letting a
    longer prefix overwrite a shorter one, and the lookup stops being a search:
    it is a single indexed read.

    Doing that all the way down to /32 would need 2^32 cells, so the table is
    cut at the two granularities that matter:

      top  a 65,536-entry list, indexed by address >> 16.
           Holds every prefix of length 0-16, the default route included.
      mid  a dict, keyed by address >> 8.
           Holds every prefix of length 17-24.
      deep a per-length dict, used only if a prefix longer than /24 is ever
           added. The benchmark's table has none, so it stays empty and the
           compiled lookup below leaves the branch out entirely.

    The split is what makes it affordable. Expanding a /8 to /24s would cost
    65,536 cells; expanding it to /16s costs 256. Expanding a /20 to /24s costs
    16. The blow-up only ever happens at the level where the prefix is short,
    and short prefixes are expanded coarsely.

    The tiers cannot disagree, which is why one probe is enough: everything in
    `mid` is at least /17 and everything in `top` is at most /16, so any `mid`
    hit is automatically the longer match. Try `mid` first, fall back to `top`,
    and the answer is the longest-prefix answer by construction.

    Ties inside a tier are resolved while building: a cell is overwritten only
    by a strictly longer prefix (`*_len` below remembers what wrote it), so
    add() order does not matter.
    """

    TOP_BITS = 16                             # address >> 16  ->  top index
    MID_BITS = 8                              # address >> 8   ->  mid key

    def __init__(self):
        self.top = [None] * (1 << self.TOP_BITS)      # plen 0-16, expanded to /16
        self.top_len = [-1] * (1 << self.TOP_BITS)
        self.mid = {}                                 # plen 17-24, expanded to /24
        self.mid_len = {}
        self.deep = []                                # [(plen, mask, dict)] desc
        self._compile()

    # ------------------------------------------------------------- building
    def add(self, network, prefix_len, next_hop):
        if prefix_len <= self.TOP_BITS:
            # Covers 2^(16-plen) consecutive /16s. A /0 covers all 65,536.
            shift = 32 - self.TOP_BITS
            start = network >> shift
            span = 1 << (self.TOP_BITS - prefix_len)
            top, top_len = self.top, self.top_len
            for i in range(start, start + span):
                if prefix_len > top_len[i]:
                    top_len[i] = prefix_len
                    top[i] = next_hop

        elif prefix_len <= 32 - self.MID_BITS:
            # Covers 2^(24-plen) consecutive /24s. A /24 covers exactly one.
            shift = self.MID_BITS
            start = network >> shift
            span = 1 << ((32 - self.MID_BITS) - prefix_len)
            mid, mid_len = self.mid, self.mid_len
            for k in range(start, start + span):
                if prefix_len > mid_len.get(k, -1):
                    mid_len[k] = prefix_len
                    mid[k] = next_hop

        else:
            # /25 and longer. Too fine to expand, so these keep the classic
            # "one hash per distinct length, longest length first" shape.
            for plen, _mask, table in self.deep:
                if plen == prefix_len:
                    table[network] = next_hop
                    break
            else:
                mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
                self.deep.append((prefix_len, mask, {network: next_hop}))
                self.deep.sort(key=lambda e: -e[0])

        self._compile()

    def _compile(self):
        """Bind the lookup path into a closure over the two containers.

        Nothing about the algorithm changes here - this only removes the
        `self.` attribute loads from the inner loop, which in CPython are a
        real fraction of a lookup this short. The variant of the table that
        keeps the plain method is in observation.md with its number.
        """
        mid_get = self.mid.get
        top = self.top

        if not self.deep:                     # the ordinary case, and the fast one
            def lookup(address):
                hop = mid_get(address >> 8)
                return top[address >> 16] if hop is None else hop
        else:
            deep = self.deep
            def lookup(address):
                for _plen, mask, table in deep:
                    hop = table.get(address & mask)
                    if hop is not None:
                        return hop
                hop = mid_get(address >> 8)
                return top[address >> 16] if hop is None else hop

        self.lookup = lookup                  # shadows the method below

    # ------------------------------------------------------------- lookup
    def lookup(self, address):
        """Replaced per instance by _compile(). Kept so the class is readable
        and so an un-built table still answers correctly."""
        for _plen, mask, table in self.deep:
            hop = table.get(address & mask)
            if hop is not None:
                return hop
        hop = self.mid.get(address >> 8)
        return self.top[address >> 16] if hop is None else hop

    # ------------------------------------------------------------- reporting
    def cost(self):
        """Cells actually occupied - the memory half of R5."""
        import sys
        return {
            "top cells": len(self.top),
            "top occupied": sum(1 for v in self.top if v is not None),
            "mid entries": len(self.mid),
            "deep lengths": len(self.deep),
            "deep entries": sum(len(t) for _p, _m, t in self.deep),
            "bytes": (sys.getsizeof(self.top) + sys.getsizeof(self.top_len)
                      + sys.getsizeof(self.mid) + sys.getsizeof(self.mid_len)),
        }

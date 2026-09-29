#!/usr/bin/env python3
"""Week 5 · Task 1 — Subnets and longest-prefix match.

Textbook §4.3.2 (IPv4 addressing, CIDR) and §4.3.3 (forwarding).

Two things a router does with every packet: work out which prefixes the
destination falls inside, and pick the longest one. The second is the whole
of "longest prefix match", and it is the reason the internet's routing table
can hold a million entries and still be answerable.

You build both, from integers up. No `ipaddress` module - that library is
exactly the thing you are supposed to understand this week.

    python3 task1_forward.py --verify
    python3 task1_forward.py --selftest    # R1/R2 rejections and the /31, /32 edges
"""
import argparse

BITS = 32
ALL_ONES = 0xFFFFFFFF


def mask_of(prefix_len):
    """Prefix length -> 32-bit mask. /0 has to be spelled out: shifting a
    32-bit word by 32 is undefined in C, and Python would happily shift the
    sign bit off into a 33rd column instead of giving 0."""
    if prefix_len == 0:
        return 0
    return (ALL_ONES << (BITS - prefix_len)) & ALL_ONES


def parse_ipv4(text):
    """'163.152.6.0' -> 32-bit int. Dotted quad only, strictly four octets."""
    parts = text.split(".")
    if len(parts) != 4:
        raise ValueError("not a dotted quad: %r" % text)
    value = 0
    for part in parts:
        if not part or not part.isdigit():
            raise ValueError("octet is not a decimal number: %r" % text)
        if len(part) > 1 and part[0] == "0":
            # 010 is 8 in some parsers and 10 in others. Refuse to guess.
            raise ValueError("octet has a leading zero: %r" % text)
        octet = int(part)
        if octet > 255:
            raise ValueError("octet out of range: %r" % text)
        value = (value << 8) | octet
    return value


def format_ipv4(value):
    """32-bit int -> dotted quad."""
    if not 0 <= value <= ALL_ONES:
        raise ValueError("not a 32-bit address: %d" % value)
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def parse_cidr(cidr):
    """'163.152.6.0/24' -> (network as int, prefix length).

    R1  a prefix length outside 0-32 is rejected.
    R2  an address with host bits set is rejected. 163.152.6.5/24 is how you
        write a host together with its mask; it is not a network, and a
        forwarding table that silently masks the host bits off hides the
        mistake instead of reporting it.
    """
    if cidr.count("/") != 1:
        raise ValueError("not a CIDR block: %r" % cidr)
    addr_text, len_text = cidr.split("/")
    if not len_text.isdigit():
        # isdigit() is False for "", "-1" and "1 ", so R1's lower edge is here
        raise ValueError("prefix length is not a number 0-32: %r" % cidr)
    prefix_len = int(len_text)
    if prefix_len > BITS:
        raise ValueError("prefix length outside 0-32: %r" % cidr)

    address = parse_ipv4(addr_text)
    host_bits = address & ~mask_of(prefix_len) & ALL_ONES
    if host_bits:
        raise ValueError(
            "host bits set: %r is a host, its network is %s/%d"
            % (cidr, format_ipv4(address & mask_of(prefix_len)), prefix_len))
    return address, prefix_len


def network_range(cidr):
    """'163.152.6.0/24' -> (first usable, last usable, broadcast) as strings.

    The ordinary case, /0 to /30, is the textbook one: the all-zeros host is
    the network identifier and the all-ones host is the directed broadcast, so
    the usable range is everything strictly between them.

    The two edges have no "between", and what to return is a choice:

      /31  RFC 3021. A point-to-point link has exactly two ends and no need to
           broadcast to them, so both addresses are usable hosts and there is
           no broadcast address at all.  ->  (net, net+1, None)
      /32  A single host - a host route, a loopback, a /32 a router advertises
           for itself. One usable address, no broadcast.  ->  (addr, addr, None)

    None, not a string, because "there is no broadcast address" is a different
    statement from "the broadcast address is x.x.x.255", and a caller that
    forgets the difference should fail loudly rather than print something false.
    """
    network, prefix_len = parse_cidr(cidr)
    size = 1 << (BITS - prefix_len)            # 2^(32-n) addresses in the block
    last = network + size - 1

    if prefix_len == BITS:                     # /32 - one address, it is the host
        return format_ipv4(network), format_ipv4(network), None
    if prefix_len == BITS - 1:                 # /31 - RFC 3021, both ends usable
        return format_ipv4(network), format_ipv4(last), None
    return format_ipv4(network + 1), format_ipv4(last - 1), format_ipv4(last)


class ForwardingTable:
    """Longest-prefix-match forwarding.

    add(cidr, next_hop)  ·  lookup(address) -> next_hop or None

    R5  0.0.0.0/0 matches everything and is the shortest prefix, so it loses to
        any other match. Nothing special-cases it: its mask is 0, so the test
        `address & 0 == 0` is true for every address, and "longest wins" does
        the rest.

    Ties: two entries can only tie if they match the same address at the same
    prefix length, and two prefixes of equal length are either disjoint or the
    same prefix. So the only table that can tie is one holding the same prefix
    twice with different next hops. That is a malformed table, and this one
    refuses it at add() time rather than inventing a winner at lookup time.
    Re-adding the same prefix with the same next hop is idempotent.
    """

    def __init__(self):
        self.entries = {}                      # (network, prefix_len) -> next_hop

    def add(self, cidr, next_hop):
        key = parse_cidr(cidr)
        existing = self.entries.get(key)
        if existing is not None and existing != next_hop:
            raise ValueError(
                "duplicate prefix %s with two next hops: %r and %r"
                % (cidr, existing, next_hop))
        self.entries[key] = next_hop

    def lookup(self, address):
        """Which entries does this address fall inside, and which is longest."""
        value = parse_ipv4(address) if isinstance(address, str) else address
        best_len, best_hop = -1, None
        for (network, prefix_len), next_hop in self.entries.items():
            if prefix_len > best_len and value & mask_of(prefix_len) == network:
                best_len, best_hop = prefix_len, next_hop
        return best_hop

    def matches(self, address):
        """Every entry the address falls inside, longest first. --verify does
        not need it; it is how observation.md lists the four 10.20.30.70 hits."""
        value = parse_ipv4(address) if isinstance(address, str) else address
        hits = [(prefix_len, format_ipv4(network), next_hop)
                for (network, prefix_len), next_hop in self.entries.items()
                if value & mask_of(prefix_len) == network]
        return sorted(hits, reverse=True)


# ------------------------------------------------------------------- harness
RANGE_CASES = [
    ("192.168.0.0/24",  "192.168.0.1",   "192.168.0.254",  "192.168.0.255"),
    ("10.0.0.0/8",      "10.0.0.1",      "10.255.255.254", "10.255.255.255"),
    ("172.16.32.0/20",  "172.16.32.1",   "172.16.47.254",  "172.16.47.255"),
    ("203.0.113.64/26", "203.0.113.65",  "203.0.113.126",  "203.0.113.127"),
]

TABLE = [
    ("0.0.0.0/0",       "default-gw"),
    ("10.0.0.0/8",      "campus"),
    ("10.20.0.0/16",    "eng-building"),
    ("10.20.30.0/24",   "lab-floor"),
    ("10.20.30.64/26",  "lab-rack-2"),
    ("192.168.1.0/24",  "home"),
]

LOOKUP_CASES = [
    ("10.20.30.70",   "lab-rack-2"),     # inside all four 10.x entries
    ("10.20.30.10",   "lab-floor"),
    ("10.20.99.1",    "eng-building"),
    ("10.99.0.1",     "campus"),
    ("8.8.8.8",       "default-gw"),
    ("192.168.1.77",  "home"),
]


def verify():
    fails = 0
    for cidr, first, last, bcast in RANGE_CASES:
        try:
            got = network_range(cidr)
        except NotImplementedError:
            print("  network_range is still a stub"); return 1
        except Exception as e:
            print(f"  FAIL  {cidr:<18} raised {e!r}"); fails += 1; continue
        ok = tuple(got) == (first, last, bcast)
        print(f"  {'ok  ' if ok else 'FAIL'}  {cidr:<18} {got}")
        fails += not ok

    t = ForwardingTable()
    try:
        for cidr, hop in TABLE:
            t.add(cidr, hop)
    except NotImplementedError:
        print("  ForwardingTable is still a stub"); return 1

    for addr, expect in LOOKUP_CASES:
        got = t.lookup(addr)
        ok = got == expect
        print(f"  {'ok  ' if ok else 'FAIL'}  {addr:<16} -> {got}  (want {expect})")
        fails += not ok

    print(f"\n  {len(RANGE_CASES) + len(LOOKUP_CASES) - fails}"
          f"/{len(RANGE_CASES) + len(LOOKUP_CASES)} ok")
    return 1 if fails else 0


# --------------------------------------------------------- extra self-checks
# --verify is the pass condition and its ten cases are left exactly as given.
# These are the requirements those ten cases never reach: the R1/R2 rejections,
# the /31 and /32 edges, and the tie rule.
REJECT_CASES = [
    ("163.152.6.5/24",   "R2 host bits set"),
    ("10.0.0.0/33",      "R1 prefix length above 32"),
    ("10.0.0.0/-1",      "R1 negative prefix length"),
    ("10.0.0.0",         "no prefix length at all"),
    ("10.0.0.0/8/8",     "two slashes"),
    ("10.0.0.256/24",    "octet above 255"),
    ("10.0.0/24",        "three octets"),
    ("10.0.0.010/24",    "leading zero is ambiguous"),
    ("10.0.0.0/",        "empty prefix length"),
]

EDGE_CASES = [
    ("203.0.113.0/31",   ("203.0.113.0",  "203.0.113.1",  None)),
    ("203.0.113.7/32",   ("203.0.113.7",  "203.0.113.7",  None)),
    ("203.0.113.0/30",   ("203.0.113.1",  "203.0.113.2",  "203.0.113.3")),
    ("0.0.0.0/0",        ("0.0.0.1", "255.255.255.254", "255.255.255.255")),
]


def selftest():
    fails = 0
    print("\n  rejections (R1, R2)")
    for cidr, why in REJECT_CASES:
        try:
            parse_cidr(cidr)
        except ValueError:
            print(f"    ok    {cidr:<18} rejected - {why}")
        else:
            print(f"    FAIL  {cidr:<18} accepted, should not be - {why}")
            fails += 1

    print("\n  edges (/31, /32, /30, /0)")
    for cidr, want in EDGE_CASES:
        got = network_range(cidr)
        ok = got == want
        print(f"    {'ok  ' if ok else 'FAIL'}  {cidr:<18} {got}")
        fails += not ok

    # task1.md says 10.20.30.70 "sits inside four different entries". That is
    # the four 10.x entries; the default route matches it too, so the honest
    # count is five. The extra one is exactly the entry R5 says must lose.
    print("\n  every prefix 10.20.30.70 falls inside")
    t = ForwardingTable()
    for cidr, hop in TABLE:
        t.add(cidr, hop)
    hits = t.matches("10.20.30.70")
    for plen, net, hop in hits:
        print(f"    /{plen:<4}{net:<16} {hop}")
    non_default = [h for h in hits if h[0] != 0]
    ok = (len(hits) == 5 and len(non_default) == 4
          and hits[0][2] == "lab-rack-2" and hits[-1][2] == "default-gw")
    print(f"    {'ok  ' if ok else 'FAIL'}  4 specific + the default route, "
          f"longest (/26) wins")
    fails += not ok

    print("\n  tie rule")
    t2 = ForwardingTable()
    t2.add("10.20.30.0/24", "lab-floor")
    t2.add("10.20.30.0/24", "lab-floor")            # idempotent, must be fine
    try:
        t2.add("10.20.30.0/24", "somewhere-else")
    except ValueError:
        print("    ok    same prefix, two next hops -> rejected at add()")
    else:
        print("    FAIL  same prefix, two next hops -> accepted")
        fails += 1

    print("\n  %s\n" % ("selftest ok" if not fails else "%d failed" % fails))
    return 1 if fails else 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--selftest", action="store_true",
                   help="R1/R2 rejections, the /31 and /32 edges, the tie rule")
    a = p.parse_args()
    if a.verify:
        raise SystemExit(verify())
    if a.selftest:
        raise SystemExit(selftest())
    raise SystemExit(p.print_help())

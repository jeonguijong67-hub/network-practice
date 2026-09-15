#!/usr/bin/env python3
"""Week 3 · Task 1 — Build your own iterative resolver.

Textbook §2.4.2 - §2.4.3.

`dig +trace` walks root -> TLD -> authoritative for you. In this task you do
that walk yourself: start at a root server, read the delegation it returns,
ask the next server, and keep going until somebody answers authoritatively.

You may shell out to `dig` for the transport, or use a DNS library
(`dnspython` is in the container). Either is fine - what matters is that
*you* follow the delegations rather than letting a tool do it.

    python3 task1_resolve.py www.korea.ac.kr
    python3 task1_resolve.py --verify        # check yourself against dig

Pass condition
--------------
`--verify` resolves five names with your resolver and with `dig`, and the
addresses must agree. A name behind a CDN may legitimately return a different
address each time; the harness compares the *set of authoritative nameservers*
you ended at for those, not the address.
"""
import argparse, ipaddress, subprocess, sys

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.rdatatype

# Root servers. Everything starts here; there is no earlier step.
ROOT_SERVERS = [
    "198.41.0.4",       # a.root-servers.net
    "199.9.14.201",     # b.root-servers.net
    "192.33.4.12",      # c.root-servers.net
]

# (name, kind).  "stable" names must match dig exactly.  "cdn" names are served
# from many replicas and may legitimately give you a different address than dig
# got a second earlier - for those we only require that you reached an answer.
VERIFY_NAMES = [
    ("www.korea.ac.kr", "stable"),
    ("dns.google", "stable"),
    ("en.wikipedia.org", "stable"),
    ("www.stanford.edu", "stable"),
    ("www.microsoft.com", "cdn"),
]


class Resolver:
    """Your iterative resolver.

    The whole point is that you never ask a server to recurse for you.
    You ask one server, it says "not mine, ask over there", and you go there.

    Suggested shape - but it is yours to design:

        resolve(name) -> (address, path)
            address : the A record you ended up with, as a string
            path    : the servers you asked, in order, so you can show your work

    Things you will hit, in roughly this order:

    1.  A delegation gives you NS *names*, sometimes with glue A records and
        sometimes without. No glue means you have to resolve that nameserver's
        name first - which is another walk. Decide what you do there.
    2.  A server may not answer. Try the next one rather than giving up.
    3.  CNAMEs. The answer you get back may be a different name than the one
        you asked for, and you have to start again with that name.
    4.  Loops. Cap your depth.

    If you shell out to dig, the flag you want is `+norecurse`, so that the
    server you ask replies with a delegation instead of doing the work:

        dig @198.41.0.4 www.korea.ac.kr +norecurse
    """

    MAX_DEPTH = 30
    TIMEOUT = 2.0

    def resolve(self, name):
        """Resolve one IPv4 address without asking another server to recurse.

        ``_walk`` is also used to resolve an NS hostname when a delegation has
        no glue.  One shared ``path`` therefore records *every* server queried,
        including failed candidates and the auxiliary NS lookup.
        """
        self.no_glue_delegations = 0
        self.auxiliary_lookups = 0
        path = []
        address = self._walk(name.rstrip("."), path, 0, set())
        return address, path

    def _query(self, server, name):
        query = dns.message.make_query(name, dns.rdatatype.A)
        # make_query sets RD by default.  Clearing it is the essential part of
        # an iterative resolver: each server may answer only from its own data.
        query.flags &= ~dns.flags.RD
        response = dns.query.udp(query, server, timeout=self.TIMEOUT)
        if response.flags & dns.flags.TC:
            response = dns.query.tcp(query, server, timeout=self.TIMEOUT)
        return response

    @staticmethod
    def _answer_value(response, name):
        """Return (A address, CNAME target), either of which may be None."""
        wanted = name.rstrip(".").lower()
        cname = None
        any_address = None
        for rrset in response.answer:
            owner = rrset.name.to_text().rstrip(".").lower()
            if rrset.rdtype == dns.rdatatype.CNAME and owner == wanted:
                cname = next(iter(rrset)).target.to_text().rstrip(".")
            elif rrset.rdtype == dns.rdatatype.A:
                value = next(iter(rrset)).address
                any_address = any_address or value
                if owner == wanted:
                    return value, cname
        # Some authoritative replies include the CNAME target's A record in
        # the same answer.  It is safe to use that record after following the
        # CNAME contained in this response.
        return any_address if cname else None, cname

    @staticmethod
    def _delegation(response):
        names = []
        for rrset in response.authority:
            if rrset.rdtype == dns.rdatatype.NS:
                names.extend(r.target.to_text().rstrip(".") for r in rrset)
        return names

    @staticmethod
    def _glue(response):
        glue = {}
        for rrset in response.additional:
            if rrset.rdtype != dns.rdatatype.A:
                continue
            owner = rrset.name.to_text().rstrip(".").lower()
            glue.setdefault(owner, []).extend(r.address for r in rrset)
        return glue

    def _walk(self, name, path, depth, resolving_ns):
        if depth >= self.MAX_DEPTH:
            raise RuntimeError(f"maximum DNS walk depth exceeded for {name}")

        servers = list(ROOT_SERVERS)
        for _ in range(self.MAX_DEPTH - depth):
            response = None
            last_error = None
            for server in servers:
                # Reject malformed glue before it reaches the network API.
                try:
                    ipaddress.ip_address(server)
                except ValueError:
                    continue
                path.append(server)
                try:
                    candidate = self._query(server, name)
                    if candidate.rcode() in (dns.rcode.NOERROR, dns.rcode.NXDOMAIN):
                        response = candidate
                        break
                except (dns.exception.Timeout, OSError, EOFError) as exc:
                    last_error = exc

            if response is None:
                raise RuntimeError(f"no DNS server answered for {name}: {last_error}")
            if response.rcode() == dns.rcode.NXDOMAIN:
                raise LookupError(f"{name} does not exist (NXDOMAIN)")

            address, cname = self._answer_value(response, name)
            if address:
                return address
            if cname:
                return self._walk(cname, path, depth + 1, resolving_ns)

            ns_names = self._delegation(response)
            if not ns_names:
                raise LookupError(f"no A answer or NS delegation for {name}")

            glue = self._glue(response)
            next_servers = []
            for ns_name in ns_names:
                next_servers.extend(glue.get(ns_name.lower(), []))

            # Out-of-bailiwick NS names often have no glue.  Resolve them by
            # beginning a separate iterative walk at the roots.
            if not next_servers:
                self.no_glue_delegations += 1
                for ns_name in ns_names:
                    key = ns_name.lower()
                    if key in resolving_ns:
                        continue
                    resolving_ns.add(key)
                    try:
                        self.auxiliary_lookups += 1
                        next_servers.append(
                            self._walk(ns_name, path, depth + 1, resolving_ns))
                    except (LookupError, RuntimeError):
                        pass
                    finally:
                        resolving_ns.discard(key)

            if not next_servers:
                raise RuntimeError(f"could not resolve delegated nameservers for {name}")
            # Preserve order while removing duplicate glue addresses.
            servers = list(dict.fromkeys(next_servers))

        raise RuntimeError(f"maximum DNS walk depth exceeded for {name}")


# ------------------------------------------------------------------- harness
def dig_answer(name):
    """What the system resolver says, for comparison."""
    out = subprocess.run(["dig", "+short", name, "A"],
                         capture_output=True, text=True).stdout
    return [l for l in out.split() if l and l[0].isdigit()]


def verify():
    r, failures = Resolver(), 0
    for name, kind in VERIFY_NAMES:
        try:
            addr, path = r.resolve(name)
        except NotImplementedError:
            print("Nothing implemented yet - write Resolver.resolve first.")
            return 1
        except Exception as e:
            print(f"  FAIL  {name:<22} your resolver raised {e!r}")
            failures += 1
            continue
        expected = dig_answer(name)
        if addr in expected:
            note = ""
        elif kind == "cdn":
            note = "  <- differs, but this name is CDN-hosted. Explain it."
        else:
            note = "  <- should have matched"
            failures += 1
        print(f"  {'FAIL' if note.endswith('matched') else 'ok  '}  {name:<22} "
              f"you={addr:<16} dig={','.join(expected) or '-'}   "
              f"hops={len(path)}{note}")
    print(f"\n  {len(VERIFY_NAMES) - failures}/{len(VERIFY_NAMES)} ok")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("name", nargs="?", default="www.korea.ac.kr")
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()

    if a.verify:
        sys.exit(verify())

    addr, path = Resolver().resolve(a.name)
    for i, server in enumerate(path, 1):
        print(f"  {i}. asked {server}")
    print(f"\n  {a.name} -> {addr}")


if __name__ == "__main__":
    main()

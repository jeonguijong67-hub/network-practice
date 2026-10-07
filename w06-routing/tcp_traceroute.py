#!/usr/bin/env python3
"""Week 6 Part A - Paris-style TCP traceroute on Windows without admin rights.

Windows tracert probes with ICMP echo. From this desktop the hops past the campus
border never answer those, so the trace goes dark after hop 4. They do answer TCP
SYNs to port 443. Windows will not let an ordinary user read ICMP from a socket,
but tshark (Npcap) can capture it, so:

  1. tshark captures ICMP time-exceeded/unreachable and TCP to/from the target
  2. one SYN per TTL to target:443 with IP_TTL set, one after another, **all from
     the same source port** - the 5-tuple routers hash for ECMP stays the same,
     so every TTL of a round follows one path (Paris traceroute). Giving each TTL
     its own port, as a first version did, mixed several equal-cost paths into
     one trace (lax1 -> sea1 -> pdx1).
  3. an ICMP time-exceeded quotes the expired packet's IP header, and its IP ID
     is unique per packet sent (retransmissions included); the captured
     outgoing SYN with that ID gives the TTL and the send time, so RTT =
     reply - send, both from the capture. (Not the TCP sequence number: several
     routers quote only the first 8 bytes of TCP, and tshark then shows ports
     but no sequence number.)
  4. a SYN-ACK (ack = seq + 1) marks the TTL that reached the target
  Each round uses a new source port, i.e. a new flow, so rounds may differ -
  that is ECMP showing itself, and it is reported per round.

    python tcp_traceroute.py stanford.edu 1.1.1.1 --rounds 3
"""
import argparse, concurrent.futures as cf, os, select, shutil, socket, subprocess, threading, time

TSHARK = shutil.which("tshark") or r"C:\Program Files\Wireshark\tshark.exe"
FIELDS = ["frame.time_epoch", "ip.src", "ip.ttl", "ip.id", "icmp.type", "tcp.srcport",
          "tcp.dstport", "tcp.flags", "tcp.seq_raw", "tcp.ack_raw"]


def rdns(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


def probe_round(ip, port, maxttl, wait):
    """SYN with TTL 1, 2, ... from one source port until the target answers."""
    for ttl in range(1, maxttl + 1):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
        s.setblocking(False)
        s.bind(("0.0.0.0", port))
        s.connect_ex((ip, 443))
        _, w, _ = select.select([], [s], [s], wait)
        reached = bool(w) and s.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0
        s.close()
        if reached:
            return ttl
    return None


def trace(host, iface, maxttl, rounds, wait, base):
    ip = socket.gethostbyname(host)
    cap = subprocess.Popen(
        [TSHARK, "-i", iface, "-l", "-T", "fields", "-E", "separator=|",
         "-f", f"icmp[0]=11 or icmp[0]=3 or (tcp port 443 and host {ip})"]
        + sum((["-e", f] for f in FIELDS), []),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    for line in cap.stderr:                      # wait until it is really capturing
        if "Capturing on" in line:
            break
    got = []                                     # drain stdout as it comes, or tshark
    reader = threading.Thread(target=lambda: got.extend(cap.stdout), daemon=True)
    reader.start()                               # blocks once the pipe buffer fills
    ports = [base + r for r in range(rounds)]
    for port in ports:
        probe_round(ip, port, maxttl, wait)
    time.sleep(1)
    cap.terminate()
    reader.join(5)
    out = "".join(got)

    by_id = {}                                   # IP ID -> (port, ttl, send time)
    by_seq = {}                                  # TCP seq -> (port, ttl, first send)
    replies = []                                 # (time, router, quoted IP ID)
    synack = []                                  # (time, ack)
    for line in out.splitlines():
        f = dict(zip(FIELDS, (line.split("|") + [""] * len(FIELDS))[:len(FIELDS)]))
        t = float(f["frame.time_epoch"])
        src = f["ip.src"].split(",")[0]
        ipid = f["ip.id"].split(",")[-1]
        if f["icmp.type"]:
            if f["tcp.dstport"].split(",")[-1] == "443" and ipid:
                replies.append((t, src, int(ipid, 16)))
            continue
        flags = int(f["tcp.flags"] or "0", 16)
        if src != ip and flags & 0x12 == 0x02:
            hop = (int(f["tcp.srcport"]), int(f["ip.ttl"]), t)
            by_id[int(ipid, 16)] = hop
            by_seq.setdefault(int(f["tcp.seq_raw"]), hop)
        elif src == ip and flags & 0x12 == 0x12 and f["tcp.ack_raw"].isdigit():
            synack.append((t, int(f["tcp.ack_raw"])))

    per_round = {p: {} for p in ports}           # port -> ttl -> (router, rtt)
    for t, router, ipid in replies:
        if ipid in by_id:
            port, ttl, t0 = by_id[ipid]
            old = per_round[port].get(ttl)
            if old is None or t - t0 < old[1]:
                per_round[port][ttl] = (router, t - t0)
    for t, ack in synack:
        hop = by_seq.get((ack - 1) % 2**32)
        if hop:
            port, ttl, t0 = hop
            old = per_round[port].get(ttl)
            if old is None or old[0] != "TARGET" or t - t0 < old[1]:
                per_round[port][ttl] = ("TARGET", t - t0)

    routers = {r for d in per_round.values() for r, _ in d.values() if r != "TARGET"}
    with cf.ThreadPoolExecutor(16) as ex:
        names = dict(zip(routers, ex.map(rdns, routers)))
    names["TARGET"] = ""

    lines = [f"tcp traceroute to {host} ({ip}) port 443 · Paris-style, one source "
             f"port per round · {rounds} rounds · * = no reply within {wait:.1f} s"]
    for n, port in enumerate(ports, 1):
        d = per_round[port]
        last = max(d) if d else 0
        lines.append(f"\n  round {n} (source port {port})")
        for ttl in range(1, last + 1):
            if ttl not in d:
                lines.append(f"  {ttl:>3}        *")
                continue
            r, rtt = d[ttl]
            if r == "TARGET":
                lines.append(f"  {ttl:>3} {rtt * 1000:8.1f} ms  {ip:<16} SYN-ACK - target reached")
                break
            lines.append(f"  {ttl:>3} {rtt * 1000:8.1f} ms  {r:<16} {names[r]}")
        if not d or "TARGET" not in [r for r, _ in d.values()]:
            lines.append(f"       (target not reached by TTL {maxttl})")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("hosts", nargs="+")
    p.add_argument("--iface", default="이더넷")
    p.add_argument("--maxttl", type=int, default=25)
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--wait", type=float, default=1.0)
    a = p.parse_args()
    base = 40000 + os.getpid() % 100 * 200
    for i, h in enumerate(a.hosts):
        print(trace(h, a.iface, a.maxttl, a.rounds, a.wait, base + i * 10))
        print()


if __name__ == "__main__":
    main()

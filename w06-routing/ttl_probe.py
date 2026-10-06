import socket, sys, time
def probe(host, ttl, port=443, timeout=1.5):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
    s.settimeout(timeout)
    t = time.perf_counter()
    try:
        s.connect((host, port)); return (time.perf_counter() - t) * 1000
    except OSError as e:
        return None
    finally:
        s.close()
for host in sys.argv[1:]:
    ip = socket.gethostbyname(host)
    res = [probe(ip, ttl) for ttl in range(1, 31)]
    first = next((i + 1 for i, r in enumerate(res) if r is not None), None)
    print(host, ip, "first TTL that connects:", first, [None if r is None else round(r,1) for r in res[:first or 30]])

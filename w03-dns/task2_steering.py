#!/usr/bin/env python3
"""Week 3 · Task 2 — Does DNS actually steer you? Measure it.

Textbook §2.4.3 (records) and §2.5 (CDNs).

The lecture claims two things:

    (a) most large sites are served by a CDN, reached through a CNAME chain
    (b) DNS steers each user to a *nearby* replica

Both are testable from your laptop, and one of them is harder to prove than
the slide makes it look. Your job is to produce the evidence and a number.

    python3 task2_steering.py --collect        # gather the raw data
    python3 task2_steering.py --report         # your analysis

What you have to build
----------------------
1.  For each hostname in SITES, follow the CNAME chain to its end and record
    every hop. `--collect` should leave the raw data in out/chains.json.

2.  Decide, for each site, whether it is served by a **third party**.
    This is the hard part and there is no single right answer:

      - `www.microsoft.com` ends at `akamaiedge.net`     - clearly third party
      - `www.netflix.com`   stops inside `netflix.com`   - own CDN, not third party
      - some sites have no CNAME at all and still sit behind a CDN (anycast)
      - `foo.cloudfront.net` and `foo.s3.amazonaws.com` are both Amazon,
        but they are not the same service

    Write down the rule you used and **defend it in observation.md**. A rule
    that just compares the last two labels will be wrong on at least one of
    the sites below; find which, and say so.

3.  Ask **two different resolvers** for the same name and compare the
    addresses you get back. If DNS really steers by location, a CDN-hosted
    name should answer differently to resolvers sitting in different places.

        RESOLVERS below has your system resolver and two public ones.

    Report: of N CDN-hosted sites, how many returned a different address set
    from a different resolver? Claim (b) predicts most of them. Check it.

Pass condition
--------------
There is no fixed answer. You pass by producing, in out/report.md:

  - the table: site | chain length | final zone | third party? | your rule's verdict
  - the steering number: "X of N sites answered differently to a different resolver"
  - at least one site where your classification rule was wrong, and why
"""
import argparse, glob, ipaddress, json, os, re, subprocess
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

SITES = [
    "www.microsoft.com",     # Akamai, multi-hop
    "www.netflix.com",       # own CDN
    "www.adobe.com",
    "www.cnn.com",
    "www.apple.com",
    "www.korea.ac.kr",       # no CDN at all
    "www.stanford.edu",
    "www.bbc.co.uk",
    "www.spotify.com",
    "www.github.com",
    "www.wikipedia.org",
    "www.nytimes.com",
]

RESOLVERS = {
    "system": None,          # whatever is in your resolv.conf
    "google": "8.8.8.8",
    "quad9":  "9.9.9.9",
}


def dig(name, rtype="A", server=None):
    """Raw lookup. Transport only - the thinking is yours."""
    args = ["dig", "+short", name, rtype]
    if server:
        args.insert(1, f"@{server}")
    out = subprocess.run(args, capture_output=True, text=True).stdout
    return [l.strip() for l in out.splitlines() if l.strip()]


def cname_chain(name):
    """Follow one CNAME at a time so every hop is visible in the output."""
    chain = [name.rstrip(".")]
    seen = {chain[0].lower()}
    for _ in range(12):
        answers = dig(chain[-1], "CNAME")
        if not answers:
            break
        target = answers[0].rstrip(".")
        if target.lower() in seen:
            raise RuntimeError(f"CNAME loop detected for {name}: {target}")
        chain.append(target)
        seen.add(target.lower())
    return chain


def addresses(name, server):
    """Keep only IPv4 results; ``dig +short A`` may also print CNAMEs."""
    result = []
    for value in dig(name, "A", server):
        try:
            if ipaddress.ip_address(value).version == 4:
                result.append(value)
        except ValueError:
            continue
    return sorted(set(result))


def zone(name):
    """Small, explicit approximation of an organisational DNS zone.

    This is intentionally *not* presented as a public-suffix implementation;
    that limitation is part of the classification discussion in the report.
    """
    labels = name.rstrip(".").lower().split(".")
    multipart_suffixes = {"ac.kr", "co.kr", "co.uk"}
    suffix2 = ".".join(labels[-2:]) if len(labels) >= 2 else labels[0]
    if suffix2 in multipart_suffixes and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else labels[0]


THIRD_PARTY_ZONES = {
    "akamaiedge.net", "akamai.net", "akamaized.net", "edgekey.net",
    "edgesuite.net", "cloudfront.net", "fastly.net", "fastlylb.net",
    "azureedge.net", "cloudflare.net", "googlehosted.com",
}

# Different zones do not always mean different owners.  For example,
# wikipedia.org can be served from Wikimedia-operated wikimedia.org names.
FIRST_PARTY_ZONES = {
    "netflix.com", "github.com", "wikipedia.org", "wikimedia.org",
    "spotify.com", "microsoft.com", "apple.com", "bbc.co.uk",
}


def classify(site, chain):
    """Return a conservative human verdict and the deliberately simple rule.

    Rule: a CNAME that ends outside the site's organisational zone is called
    third-party.  It is reproducible, but cannot see CNAME-less anycast and can
    confuse a company's separately named first-party infrastructure.
    """
    site_zone = zone(site)
    final_zone = zone(chain[-1])
    rule = len(chain) > 1 and final_zone != site_zone
    if final_zone in FIRST_PARTY_ZONES:
        reviewed = False
    elif final_zone in THIRD_PARTY_ZONES:
        reviewed = True
    elif final_zone == site_zone:
        reviewed = False
    else:
        # Cross-zone hosting is evidence of a third party, but the report marks
        # this as an inference rather than pretending DNS proves ownership.
        reviewed = rule
    return reviewed, rule, final_zone


def collect(network_label="current network"):
    """Gather raw chains and per-resolver answers into out/chains.json.

    You write this. Roughly:
      for each site: follow CNAMEs to the end, then for each resolver in
      RESOLVERS record the A records it returns.
    """
    data = {
        "_meta": {
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "network": network_label,
            "resolvers": RESOLVERS,
            "note": "One vantage point. Re-run after changing networks for B3.",
        }
    }
    for site in SITES:
        chain = cname_chain(site)
        data[site] = {
            "chain": chain,
            "addresses": {
                label: addresses(site, server)
                for label, server in RESOLVERS.items()
            },
        }
        print(f"  {site:<22} {' -> '.join(chain)}")

    path = os.path.join(OUT, "chains.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n  wrote {path}")

    # A labelled snapshot prevents the second-network run from destroying the
    # first one.  chains.json remains the canonical file expected by check.py.
    if network_label != "current network":
        slug = re.sub(r"[^a-z0-9]+", "-", network_label.lower()).strip("-")
        snapshot = os.path.join(OUT, f"chains-{slug or 'network'}.json")
        with open(snapshot, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  preserved labelled snapshot {snapshot}")


def report():
    """Read out/chains.json and produce out/report.md.

    You write this too - including the classification rule that decides
    whether a site is on a third-party CDN.
    """
    sources = sorted(glob.glob(os.path.join(OUT, "chains*.json")))
    datasets = []
    seen_networks = set()
    for source in sources:
        with open(source, encoding="utf-8") as f:
            candidate = json.load(f)
        label = candidate.get("_meta", {}).get("network", os.path.basename(source))
        if label not in seen_networks:
            datasets.append(candidate)
            seen_networks.add(label)
    if not datasets:
        raise FileNotFoundError("run --collect before --report")
    data = datasets[0]

    rows = []
    mismatches = []
    steered = 0
    comparable = 0
    unavailable = set()
    for site in SITES:
        item = data[site]
        chain = item["chain"]
        reviewed, rule, final_zone = classify(site, chain)
        if reviewed != rule:
            mismatches.append((site, final_zone, reviewed, rule))
        answer_sets = []
        for dataset in datasets:
            network = dataset.get("_meta", {}).get("network", "unknown network")
            for label, values in dataset[site]["addresses"].items():
                if values:
                    answer_sets.append(frozenset(values))
                else:
                    unavailable.add(f"{network}/{label}")
        # Korea University is the explicit non-CDN control in the assignment.
        if site != "www.korea.ac.kr" and len(answer_sets) >= 2:
            comparable += 1
            if len(set(answer_sets)) > 1:
                steered += 1
        rows.append((site, len(chain) - 1, final_zone, reviewed, rule))

    lines = [
        "# Week 3 DNS steering report",
        "",
        "## Method",
        "",
        "For each hostname the script followed CNAME records until no further "
        "CNAME was returned, then requested A records from the system resolver, "
        "Google Public DNS, and Quad9. The automatic rule calls a site third-party "
        "when its CNAME chain ends outside the site's approximated organisational zone.",
        "",
        "| Site | Chain length | Final zone | Third party? (reviewed) | Rule verdict |",
        "|---|---:|---|---|---|",
    ]
    for site, length, final_zone, reviewed, rule in rows:
        lines.append(
            f"| `{site}` | {length} | `{final_zone}` | "
            f"{'yes' if reviewed else 'no'} | {'yes' if rule else 'no'} |"
        )

    lines += [
        "",
        "## Resolver comparison and steering number",
        "",
        f"**{steered} of {comparable} comparable CDN-hosted sites answered differently "
        "to a different resolver or network.** A site is comparable only when at least "
        "two resolver/network combinations returned a non-empty address set. Networks: "
        + ", ".join(sorted(seen_networks)) + ".",
        "",
    ]
    if unavailable:
        lines.append(
            "Resolvers with at least one blocked or empty response: "
            + ", ".join(sorted(unavailable)) + "."
        )
        lines.append("")

    lines += [
        "## Where the rule is wrong or incomplete",
        "",
        "The rule equates a cross-zone CNAME with third-party delivery. It cannot "
        "detect a CDN exposed only through A/AAAA anycast records, so a CNAME-less "
        "site can be reported as 'no' even when a CDN is in use. It can also label "
        "separately named infrastructure owned by the same organisation as third-party.",
        "",
    ]
    if mismatches:
        for site, final_zone, reviewed, rule in mismatches:
            lines.append(
                f"A concrete error is `{site}` ending in `{final_zone}`: the simple "
                f"rule says {'third-party' if rule else 'first-party'}, while the "
                f"reviewed ownership verdict is "
                f"{'third-party' if reviewed else 'first-party'}."
            )
    else:
        lines.append(
            "No ownership mismatch happened to appear in this run; this does not "
            "make the rule sound. For example, Wikimedia can use `wikimedia.org` "
            "to serve `wikipedia.org`, a cross-zone CNAME under the same owner."
        )
    lines += [
        "DNS records alone do not prove corporate ownership; the reviewed column is "
        "therefore a conservative interpretation, not ground truth.",
        "",
        "## Vantage-point limitation",
        "",
        ("This report includes multiple labelled networks and resolver combinations."
         if len(seen_networks) >= 2 else
         "This run used one network and three resolvers. That tests resolver-dependent "
         "answers but not the stronger location claim. To satisfy B3 strictly, switch "
         "to a second authorised network (for example, phone tethering), then run "
         "`python3 task2_steering.py --collect --network-label phone-tethering` and "
         "regenerate the report. No second-network result was invented here."),
        "",
        "## Packet-capture fields to complete",
        "",
        "A personal `out/dns.pcapng` was not generated automatically because it may "
        "contain private background DNS traffic. After a short Wireshark capture, "
        "record the delegation packet number, answer packet number, and largest DNS "
        "response byte size here.",
    ]

    target = os.path.join(OUT, "report.md")
    with open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  wrote {target}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--collect", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--network-label", default="current network")
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.collect:
        collect(a.network_label)
    elif a.report:
        report()
    else:
        p.print_help()

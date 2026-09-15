# Week 3 DNS steering report

## Method

For each hostname the script followed CNAME records until no further CNAME was returned, then requested A records from the system resolver, Google Public DNS, and Quad9. The automatic rule calls a site third-party when its CNAME chain ends outside the site's approximated organisational zone.

| Site | Chain length | Final zone | Third party? (reviewed) | Rule verdict |
|---|---:|---|---|---|
| `www.microsoft.com` | 2 | `akamaiedge.net` | yes | yes |
| `www.netflix.com` | 1 | `netflix.com` | no | no |
| `www.adobe.com` | 2 | `akamai.net` | yes | yes |
| `www.cnn.com` | 1 | `fastly.net` | yes | yes |
| `www.apple.com` | 3 | `akamaiedge.net` | yes | yes |
| `www.korea.ac.kr` | 0 | `korea.ac.kr` | no | no |
| `www.stanford.edu` | 1 | `netlifyglobalcdn.com` | yes | yes |
| `www.bbc.co.uk` | 2 | `fastly.net` | yes | yes |
| `www.spotify.com` | 1 | `fastly.net` | yes | yes |
| `www.github.com` | 1 | `github.com` | no | no |
| `www.wikipedia.org` | 1 | `wikimedia.org` | no | yes |
| `www.nytimes.com` | 3 | `fastly.net` | yes | yes |

## Resolver comparison and steering number

**4 of 11 comparable CDN-hosted sites answered differently to a different resolver or network.** A site is comparable only when at least two resolver/network combinations returned a non-empty address set. Networks: remote session (single vantage point).

## Where the rule is wrong or incomplete

The rule equates a cross-zone CNAME with third-party delivery. It cannot detect a CDN exposed only through A/AAAA anycast records, so a CNAME-less site can be reported as 'no' even when a CDN is in use. It can also label separately named infrastructure owned by the same organisation as third-party.

A concrete error is `www.wikipedia.org` ending in `wikimedia.org`: the simple rule says third-party, while the reviewed ownership verdict is first-party.
DNS records alone do not prove corporate ownership; the reviewed column is therefore a conservative interpretation, not ground truth.

## Vantage-point limitation

This run used one network and three resolvers. That tests resolver-dependent answers but not the stronger location claim. To satisfy B3 strictly, switch to a second authorised network (for example, phone tethering), then run `python3 task2_steering.py --collect --network-label phone-tethering` and regenerate the report. No second-network result was invented here.

## Packet-capture fields to complete

A personal `out/dns.pcapng` was not generated automatically because it may contain private background DNS traffic. After a short Wireshark capture, record the delegation packet number, answer packet number, and largest DNS response byte size here.

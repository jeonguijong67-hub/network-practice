# Week 3 DNS steering report

## Method

For each hostname the script followed CNAME records until no further CNAME was returned, then requested A records from each resolver in `system` (this machine's configured resolver), `google` (8.8.8.8), `quad9` (9.9.9.9), `kt-kr` (168.126.63.1). The automatic rule calls a site third-party when its CNAME chain ends outside the site's approximated organisational zone.

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

**8 of 11 comparable CDN-hosted sites answered differently to a different resolver or network.** A site is comparable only when at least two resolver/network combinations returned a non-empty address set. Networks: ku-campus-ethernet.

## Where the rule is wrong or incomplete

The rule equates a cross-zone CNAME with third-party delivery. It cannot detect a CDN exposed only through A/AAAA anycast records, so a CNAME-less site can be reported as 'no' even when a CDN is in use. It can also label separately named infrastructure owned by the same organisation as third-party.

A concrete error is `www.wikipedia.org` ending in `wikimedia.org`: the simple rule says third-party, while the reviewed ownership verdict is first-party.
DNS records alone do not prove corporate ownership; the reviewed column is therefore a conservative interpretation, not ground truth.

## Vantage-point limitation

Only one network is available from this machine, so B3 is answered by task2.md's path (B): compare resolvers at very different distances instead of two networks. `kt-kr` (168.126.63.1, Korea Telecom) is the near one and `google` / `quad9` are US anycast. Note that `system` cannot add anything here - this machine is configured with 8.8.8.8, so `system` and `google` are the same server and agree by construction.

What this weakens: a resolver-dependent answer shows that the CDN varies its reply by *who asks*, which is claim (a) plus resolver steering. It does not establish claim (b), that you are steered to a replica near *where you are*, because every query in this report leaves the same location. Two networks in different places would be needed for that, and none was invented here.

## Packet-capture fields (Part A)

`out/dns.pcapng`, captured on this host with capture filter `port 53 and not host 8.8.8.8 and not host 8.8.4.4` while running `task1_resolve.py www.korea.ac.kr`. This machine's configured resolver is 8.8.8.8/8.8.4.4, so excluding it drops every background application's DNS and leaves only this resolver's direct-to-authoritative queries. The file is exactly 6 packets: three queries and three responses, no third-party traffic.

| Field | Value |
|---|---|
| A2 · query and matching response | packets 5 and 6, transaction ID `0xb696` on both |
| A3 · delegation (0 answers, NS in authority) | **packet 2**, from root server 198.41.0.4 - 0 answers, 6 authority NS, 10 additional glue |
| A3 · second delegation | packet 4, from the `.kr` server 210.101.61.1 - 0 answers, 2 authority NS, 2 glue |
| A3 · answer (A in answer section) | **packet 6**, from `korea.ac.kr`'s server 163.152.1.1 - 1 answer, type A, `163.152.6.10` |
| A4 · largest DNS response | **packet 2, 383 bytes on the wire** |

A4: the largest response is the root's referral, not the answer. A referral has to hand back the whole next zone - 6 NS records for `.kr` plus 10 glue records (A and AAAA for those name servers), 16 resource records in one datagram. The response that actually answers the question carries a single A record and is 91 bytes, about a quarter the size. The referral pays for the glue so the resolver does not have to stop and resolve each name server's own name first.

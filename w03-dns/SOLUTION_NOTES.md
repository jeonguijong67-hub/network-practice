# Week 3 구현 설명과 재현 가이드

## Task 1 — 반복적 DNS resolver

`Resolver.resolve()`은 루트 서버에서 출발합니다. 질의의 RD(recursion desired) 비트를
끄고 A 레코드를 요청하므로, 각 서버는 최종 주소 대신 다음 단계의 NS delegation을 줄 수
있습니다. 코드는 authority 영역의 NS와 additional 영역의 glue A를 읽어 다음 서버로
이동합니다.

glue가 없으면 해당 NS 이름도 루트부터 별도의 반복 질의로 해석합니다. 서버 timeout은
다음 후보 서버로 넘어가며, CNAME이면 대상 이름으로 루트부터 다시 시작합니다. malformed
zone이나 CNAME/NS 순환으로 멈추지 않도록 전체 깊이에 상한을 둡니다. 반환되는 `path`에는
실패한 후보와 glue 보조 해석을 포함해 실제 질의한 서버가 순서대로 기록됩니다.

```bash
python3 task1_resolve.py www.korea.ac.kr
python3 task1_resolve.py --verify
```

## Task 2 — CNAME과 resolver별 주소 비교

`--collect`는 각 사이트의 CNAME을 한 단계씩 따라가고, system/Google/Quad9 resolver의
A 레코드 집합을 `out/chains.json`에 저장합니다. `--report`는 JSON을 읽어 표, resolver별
차이 수, 분류 규칙의 한계가 포함된 `out/report.md`를 만듭니다.

자동 규칙은 "CNAME의 마지막 조직 도메인이 원래 사이트와 다르면 third-party"입니다.
단순하고 재현 가능하지만 public suffix 전체를 구현하지 않았고, CNAME 없는 anycast CDN을
못 찾으며, `wikipedia.org`와 `wikimedia.org`처럼 소유자가 같고 이름만 다른 경우를 틀릴 수
있습니다. 따라서 보고서의 reviewed 값도 DNS만으로 증명된 사실이 아니라 보수적 해석입니다.

한 네트워크에서 세 resolver를 비교하는 것만으로 사용자 위치에 따른 steering을 완전히
입증할 수 없습니다. 휴대전화 테더링 등 두 번째로 사용 권한이 있는 네트워크로 전환한 뒤
`--collect`를 다시 실행하고, 기존 `chains.json`을 먼저 별도 이름으로 보관해 비교해야 합니다.

개인 패킷 캡처 절차:

1. 다른 브라우저와 백그라운드 앱을 가능한 한 닫습니다.
2. Wireshark에서 실제 사용 인터페이스를 선택하고 capture filter를 `port 53`으로 둡니다.
3. 짧게 캡처하면서 `python3 task1_resolve.py www.korea.ac.kr`를 실행합니다.
4. 캡처를 멈추고 다른 사람의 정보나 무관한 도메인이 없는지 확인합니다.
5. 안전한 경우에만 `out/dns.pcapng`로 저장합니다.
6. delegation 응답, 최종 A 응답의 패킷 번호와 가장 큰 DNS 응답 크기를 보고서에 적습니다.

## Task 3 — TTL-aware 캐시

baseline은 리스트를 선형 탐색하고 모든 레코드를 60초 동안 보관합니다. 선형 탐색은
성능 문제이고, 권한 서버가 준 실제 TTL을 버리는 것은 정확성 문제입니다. TTL이 20초인
레코드는 최대 40초 동안 만료된 값을 반환할 수 있고, TTL이 긴 레코드는 불필요하게 다시
질의합니다.

개선 구현은 dict에 `(address, expires_at)`을 저장합니다. `now < expires_at`인 경우만 hit로
처리하고, TTL이 끝났으면 다음 요청에서 즉시 upstream을 조회합니다. 이 workload에서 가능한
최소 upstream 수는 이 방식의 측정값과 같습니다. 각 이름의 첫 요청과, 그 후 이전 조회 TTL이
끝난 뒤 처음 도착하는 요청은 어떤 올바른 캐시도 upstream 조회 없이 답할 수 없기 때문입니다.

```bash
python3 bench.py --yours
python3 test_tasks.py --task 3
```

## 결과 파일을 다시 만드는 법

```bash
mkdir -p out
python3 task2_steering.py --collect
python3 task2_steering.py --report
python3 bench.py --yours | tee out/bench.txt
python3 test_tasks.py
python3 ../check.py w03
```

`bench.py`와 `test_tasks.py`는 강의 원본 그대로 유지합니다. 과제 조건을 우회하려고 harness를
수정하면 안 됩니다.


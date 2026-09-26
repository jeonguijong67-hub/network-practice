# 실습 노트 (3주차 · 4주차)

두 주차 모두 제출 가능한 상태입니다. 남은 작업 없음.

## 상태

| | Task 1 | Task 2 | Task 3 |
|---|---|---|---|
| w03 DNS | resolver 5/5 | 캡처 6패킷 · steering report | upstream 275 · stale 0 → good |
| w04 TCP | 10개 seed 전부 IDENTICAL | 2개 라벨 × 5회 · handshake 캡처 | goodput 98.7% · 큐 0.7 → **strong** |

`test_tasks.py`: w04는 8 pass / 0 fail. w03은 아래 "알려진 환경 차이" 항목 하나만 FAIL로 뜹니다.

## 제출 URL (주차별)

- 3주차 <https://github.com/jeonguijong67-hub/network-practice/tree/main/w03-dns>
- 4주차 <https://github.com/jeonguijong67-hub/network-practice/tree/main/w04-tcp>

## 알려진 환경 차이

호스트 tshark는 4.6.6이라 boolean 필드를 `True/False`로 출력하는데
`w03-dns/test_tasks.py`는 `0/1`을 기대합니다. 그래서 캡처가 정상인데도
"0 queries, 0 responses"로 FAIL이 뜹니다. 컨테이너(Ubuntu 24.04, tshark 4.2)에서는
`0/1`이라 통과합니다. 캡처 자체는 질의 3 · 응답 3으로 정상입니다.

w03 Task 1의 "resolver vs dig"는 호스트에 `dig`가 없어 skip됩니다. 컨테이너에는
`dnsutils`가 들어 있으므로 `docker compose run --rm lab bash -lc "cd w03-dns && python3 test_tasks.py"`
로 돌리면 이 항목까지 실행됩니다.

리졸버를 호스트에서 직접 돌리려고 `dnspython`을 호스트 Python에 설치했습니다
(패킷이 호스트 NIC에 잡히려면 컨테이너가 아니라 호스트에서 질의해야 하기 때문).

## 캡처 파일

`.pcapng`는 `.gitignore`로 커밋되지 않습니다(개인정보 보호). `check.py`도 optional로
처리하므로 제출에 영향 없습니다. 분석 결과는 report.md와 observation.md에 들어가 있습니다.

두 캡처 모두 필터를 좁혀서 본인이 만든 트래픽만 담았습니다.

- `w04-tcp/out/tcp.pcapng` — `tcp port 443 and host <speed.cloudflare.com>`
- `w03-dns/out/dns.pcapng` — `port 53 and not host 8.8.8.8 and not host 8.8.4.4`
  (시스템 resolver를 제외해 배경 앱의 DNS가 들어가지 않음, 총 6패킷)

## Task 2 측정 경로에 대한 메모

쓸 수 있는 네트워크가 유선 이더넷 하나뿐이라 `task2.md`의 path (B)를 썼습니다.
평일(화 13:18)과 주말(토 16:38) 두 번 측정했고, 그것이 무엇을 약화시키는지는
`w04-tcp/out/observation.md` Part B 마지막 문단에 적었습니다.
RTT가 실제로 다른 두 번째 링크(폰 테더링 등)를 쓸 수 있게 되면
`python task2_measure.py --label "tethering"` 한 줄로 더 강한 근거를 추가할 수 있습니다.

# 실습 노트 (3주차 · 4주차 · 5주차 · 6주차)

네 주차 모두 제출 가능한 상태입니다. 6주차 Part A는 아래 "6주차" 항목의 한계가 있습니다.

## 상태

| | Task 1 | Task 2 | Task 3 |
|---|---|---|---|
| w03 DNS | resolver 5/5 | 캡처 6패킷 · steering report | upstream 275 · stale 0 → good |
| w04 TCP | 10개 seed 전부 IDENTICAL | 2개 라벨 × 5회 · handshake 캡처 | goodput 98.7% · 큐 0.7 → **strong** |
| w05 IP/NAT | 10/10 | 2개 라벨(캠퍼스 유선 · KT Wi-Fi) · DORA 캡처 | 오답 0 · 약 3000배 → **strong** |
| w06 Routing | verify all ok | traceroute 5개 목적지 · OSPF 3대 장애·복구 각 3회, 비용 변경 왕복 | 오답 0 · SPF 79% 회피 → **strong** |

`test_tasks.py`: w04 · w05는 8 pass / 0 fail, w06은 9 pass / 0 fail / 1 skip(R5는 사람 채점). w03은 아래 "알려진 환경 차이" 항목 하나만 FAIL로 뜹니다.

## 제출 URL (주차별)

- 3주차 <https://github.com/jeonguijong67-hub/network-practice/tree/main/w03-dns>
- 4주차 <https://github.com/jeonguijong67-hub/network-practice/tree/main/w04-tcp>
- 5주차 <https://github.com/jeonguijong67-hub/network-practice/tree/main/w05-ip-nat>
- 6주차 <https://github.com/jeonguijong67-hub/network-practice/tree/main/w06-routing>

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

`.gitignore`는 `*.pcapng`를 기본으로 제외하지만, 아래 세 개는 **예외로 커밋**했습니다.
모두 캡처 필터를 좁혀서 잡았고, 커밋 전에 내용을 확인했습니다.

**`w03-dns/out/dns.pcapng`** (1.6 KB, 6패킷)
필터 `port 53 and not host 8.8.8.8 and not host 8.8.4.4`. 이 기계의 시스템 resolver를
제외했으므로 배경 앱의 DNS는 한 건도 들어가지 않습니다. 확인 결과 등장하는 주소는
이 기계 · 루트(198.41.0.4) · `.kr`(210.101.61.1) · `korea.ac.kr`(163.152.1.1) 넷뿐이고,
질의된 이름은 `www.korea.ac.kr` 하나뿐입니다.

**`w04-tcp/out/tcp.pcapng`** (502 KB, 4,117패킷)
필터 `tcp port 443 and host <speed.cloudflare.com>`. 등장하는 주소는 이 기계와
172.66.0.218 둘뿐입니다. 원본은 10.7 MB였고 저장소에 넣기 위해 두 번 줄였습니다.

- `tshark -Y "tcp.stream==0"` — 분석 대상인 첫 연결만 남김
- `editcap -s 96` — 각 패킷을 96바이트로 잘라 **payload를 버리고 헤더만** 남김

**payload가 없는 것은 의도된 것입니다.** 원래 프레임 길이는 파일에 기록되므로
A2~A5에 필요한 값은 전부 그대로 읽힙니다 — 확인했습니다: ISN 2851709068 / 2408489946,
MSS 1460 / 1400, window scale 8 / 13, SACK permitted, 스케일 적용 광고 윈도우
12,678,400바이트, 최대 bytes in flight 16,060, TCP payload 합계 5,015,780바이트.

**`w05-ip-nat/out/dhcp.pcapng`** (2.9 KB, 5패킷)
노트북 Wi-Fi(KT 공유기, WPA2-Personal)에서 필터 `port 67 or port 68`로 받으면서
`ipconfig /release` → `/renew`를 실행했습니다. Release 1개와 DORA 4개이고, 5개 모두 DHCP
`chaddr`이 이 노트북의 MAC이라 다른 기기의 DHCP는 없습니다. 식별 정보는 이 노트북의
호스트 이름과 MAC뿐입니다. 캠퍼스 유선(데스크톱)은 고정 주소라 DHCP가 일어나지 않아
노트북에서 잡았습니다.

`check.py`는 캡처를 optional로 처리하므로 이 파일들이 없어도 제출 형식에는 문제가
없지만, 넣어 두면 A1("본인 기계에서 잡은 본인 트래픽")을 직접 보일 수 있습니다.

## Task 2 측정 경로에 대한 메모

**공통** — 쓸 수 있는 네트워크가 유선 이더넷 하나뿐이라 두 주차 모두 `task2.md`의
path (B)를 썼습니다. 폰 테더링이 가능해지면 두 주차 모두 한 줄씩으로 더 강한 근거를
추가할 수 있고, 기존 결과를 지우지 않고 덧붙는 구조입니다.

**w03** — path (B)가 지정한 "거리가 크게 다른 resolver 비교"를 택했습니다.
`kt-kr`(168.126.63.1, KT) 대 `google`/`quad9`(미국 anycast). 이 기계의 설정 resolver가
8.8.8.8이라 `system`과 `google`은 같은 서버여서 정의상 일치하므로, 그 둘만으로는
비교가 성립하지 않았습니다. 추가하려면:
`python task2_steering.py --collect --network-label tethering` 후 `--report`.

**w04** — 평일(화 13:18)과 주말(토 16:38) 두 시점. 추가하려면:
`python task2_measure.py --label "tethering"`.

## 6주차

**FRR 이미지.** `compose.yml`이 지정한 `frrouting/frr:v9.1.0`은 Docker Hub에 없습니다
(FRR 공식 이미지는 quay.io에 있음). 강의 파일은 그대로 두고 로컬에서 이름만 맞췄습니다.

```bash
docker pull quay.io/frrouting/frr:9.1.0
docker tag quay.io/frrouting/frr:9.1.0 frrouting/frr:v9.1.0
```

**줄바꿈.** Windows(`core.autocrlf=true`)에서 체크아웃하면 `topology/r*/daemons`가 CRLF가
되어 `-A 127.0.0.1`로 읽히고 ospfd가 `getaddrinfo failed`로 뜨지 않습니다.
`.gitattributes`로 `*.sh`와 `w06-routing/topology/**`를 LF로 고정했습니다. 이미 받아 둔
작업본은 `git rm --cached -r w06-routing/topology && git checkout -- w06-routing/topology`
또는 `sed -i 's/$//'`로 한 번 바꿔야 합니다.

**재수렴 측정.** `scenario.sh cut`의 "N 초"는 정수 초 · 1초 폴링 · uptime 열 비교라서
측정이 아닙니다. `w06-routing/measure.sh`가 세 라우터의 `ip -ts monitor route`로 커널 FIB
변경 시각을 µs 단위로 받습니다. 원자료는 `w06-routing/out/measure/`.

**Part A 한계.** 데스크톱의 캠퍼스 유선은 경계(4홉 `163.152.205.254`) 너머 ICMP를 걸러서
tracert가 5홉부터 거의 비고, 해저 구간 홉의 이름(A3의 케이블)을 볼 수 없습니다. 홉 수는
`w06-routing/ttl_probe.py`(TCP 443 TTL 스윕)로 보완했습니다. 노트북에서 KUWIFI로 잰
traceroute(서울→홍콩→도쿄→시애틀→팰로앨토가 보였던 것)는 노트북에서 push되지 않아
여기 없습니다. 노트북의 `out/traceroute.txt`를 `traceroute-kuwifi.txt`로 추가하면 A2·A3를
호스트 이름으로 답할 수 있습니다.

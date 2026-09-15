# Computer Networks — Week 3 DNS Lab

고려대학교 세종캠퍼스 컴퓨터네트워크 2026-2 Week 3 실습 저장소입니다. 강의 원본의
`w03-dns` 과제를 옮기고, 실행 코드와 재현 절차를 함께 정리했습니다.

- 강의 원본: <https://github.com/codingchild2424/2026-lecture-network-practice>
- 주제: DNS 계층 구조, DNS 레코드, CDN과 DNS steering, TTL 캐시
- 제출 대상: `w03-dns/`의 코드와 `w03-dns/out/`의 결과물

## 빠른 실행

Docker Desktop이 실행 중인 상태에서 저장소 루트에서 다음 명령을 실행합니다.

```bash
docker compose build
docker compose run --rm lab
```

컨테이너 안에서:

```bash
cd w03-dns
python3 task1_resolve.py --verify
python3 task2_steering.py --collect --network-label first-network
python3 task2_steering.py --report
python3 bench.py --yours | tee out/bench.txt
python3 test_tasks.py
python3 ../check.py w03
```

> Task 2의 두 번째 네트워크 측정과 개인 DNS 패킷 캡처는 본인이 직접 해야 합니다.
> `port 53` 캡처에는 방문한 도메인이 포함될 수 있으므로 제출 전에 반드시 검토하세요.
> 원격 작업 후 데스크톱에서 이어가는 정확한 순서는 `CONTINUE_ON_DESKTOP.md`에 있습니다.

## 파일 구조

```text
.
├── README.md                 전체 실행 순서
├── Dockerfile               Ubuntu 24.04 실습 환경
├── compose.yml              Docker 실행 설정
├── check.py                 제출 형식 검사기
└── w03-dns/
    ├── README.md             강의 과제 개요
    ├── task1.md              반복적 resolver 요구사항
    ├── task1_resolve.py      구현 및 검증 CLI
    ├── task2.md              steering/캡처 요구사항
    ├── task2_steering.py     수집 및 보고서 생성 CLI
    ├── task3.md              TTL 캐시 요구사항
    ├── task3_cache.py        baseline과 개선 캐시
    ├── bench.py              수정 금지 성능 측정기
    ├── test_tasks.py         주차 테스트
    ├── SOLUTION_NOTES.md     구현 원리와 남은 수동 작업
    └── out/                  측정·보고 결과
```

## 제출 전 체크리스트

- [ ] `task1_resolve.py --verify`의 다섯 이름이 모두 통과한다.
- [ ] `out/chains.json`과 `out/report.md`가 현재 측정 결과로 생성됐다.
- [ ] 다른 허가된 네트워크에서도 Task 2를 실행하고 두 결과를 비교했다.
- [ ] 본인이 캡처한 `out/dns.pcapng`를 개인정보 관점에서 검토했다.
- [ ] `out/report.md`에 delegation/answer 패킷 번호와 최대 응답 크기를 기록했다.
- [ ] `bench.txt`에서 개선 캐시의 stale 값이 0이다.
- [ ] `test_tasks.py`와 `../check.py w03` 결과를 확인했다.

## 주의

DNS 서버에 보내는 질의는 모두 재귀 요청 없이 진행하며, 측정 대상은 과제에 명시된
공개 사이트와 본인이 사용할 권한이 있는 네트워크로 제한합니다. 자동 생성된 보고서는
DNS 관측만으로 소유 관계를 단정하지 않으며, 한 개 네트워크에서 얻은 결과를 두 개의
vantage point 결과처럼 표현하지 않습니다.

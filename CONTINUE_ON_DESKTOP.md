# 데스크톱에서 이어서 진행하기

현재 원격 세션에서 코드 구현과 자동 실행은 끝났습니다. 실제 장비가 필요한 두 항목만
의도적으로 남겨 두었습니다.

## 현재 완료 상태

- Task 1 반복적 resolver: 5개 도메인 **5/5 통과**
- Task 2 첫 번째 vantage point: 12개 사이트 × system/Google/Quad9 수집 완료
- Task 2 현재 결과: CDN-hosted 비교 대상 **11개 중 4개**가 다른 주소 집합 반환
- Task 3: baseline 325회/266 stale → 개선 캐시 **275회/0 stale**
- 제출 형식 검사: 통과
- 전체 자동 테스트: 11 pass, 1 fail, 3 human-check skip
- 유일한 fail: 본인 장비의 `out/dns.pcapng`가 아직 없음

## 1. 저장소 받기와 환경 확인

```powershell
git clone https://github.com/jeonguijong67-hub/network-practice.git
cd network-practice
docker compose build
```

이미 clone한 폴더라면 `git pull`만 실행하면 됩니다. Docker Desktop과 Wireshark를 먼저
실행하세요.

## 2. 본인 DNS 패킷 캡처

1. 개인정보 노출을 줄이기 위해 브라우저와 불필요한 백그라운드 앱을 닫습니다.
2. Wireshark에서 현재 인터넷을 사용하는 인터페이스를 선택합니다.
3. capture filter를 `port 53`으로 입력하고 캡처를 시작합니다.
4. 별도 PowerShell에서 아래 명령을 한 번 실행합니다.

```powershell
docker compose run --rm lab bash -lc "cd w03-dns && python3 task1_resolve.py www.korea.ac.kr"
```

5. 바로 캡처를 중지하고, 무관한 도메인이나 개인 정보가 없는지 직접 확인합니다.
6. 안전할 때만 `w03-dns/out/dns.pcapng`로 저장합니다.
7. Wireshark display filter에 `dns`를 적용해 다음 값을 찾습니다.

   - delegation 응답: answer count 0, authority 영역에 NS가 있는 패킷 번호
   - 최종 answer 응답: answer 영역에 A가 있는 패킷 번호
   - 가장 큰 DNS response의 frame length와 커진 이유

8. 위 세 값을 `w03-dns/out/report.md`의 **Packet-capture fields to complete** 절에 적습니다.

> `.pcapng`는 방문 도메인을 포함할 수 있어 기본적으로 Git에서 제외됩니다. 강의 제출
> 시스템이 별도 파일 업로드를 요구할 때만, 내용을 검토한 후 그곳에 직접 제출하세요.

## 3. 두 번째 네트워크 측정

현재 원격 세션의 첫 결과는 `chains-remote-session.json`에 보존되어 있습니다. 데스크톱을
휴대전화 테더링처럼 본인이 사용할 권한이 있는 다른 네트워크에 연결한 뒤 실행합니다.

```powershell
docker compose run --rm lab bash -lc "cd w03-dns && python3 task2_steering.py --collect --network-label phone-tethering"
docker compose run --rm lab bash -lc "cd w03-dns && python3 task2_steering.py --report"
```

`--network-label`을 쓰면 canonical `chains.json`과 별도로
`chains-phone-tethering.json`이 자동 보존됩니다. 보고서 생성기는 모든 `chains*.json`을
읽어 네트워크와 resolver 조합을 함께 비교합니다. 실제 사용한 네트워크 이름에 맞게 label을
바꿔도 됩니다.

## 4. 최종 검사

```powershell
docker compose run --rm lab bash -lc "cd w03-dns && python3 bench.py --yours"
docker compose run --rm lab bash -lc "cd w03-dns && python3 test_tasks.py"
docker compose run --rm lab bash -lc "python3 check.py w03"
```

기대 결과:

- `test_tasks.py`: pcap을 저장했다면 자동 검사 항목이 모두 PASS 또는 human-check SKIP
- `check.py w03`: `Format check passed`
- cache: `upstream 275`, `stale 0`

## 5. GitHub 반영

텍스트·코드 변경만 올립니다. pcap은 개인정보 검토 전에는 강제로 추가하지 마세요.

```powershell
git add .
git status
git commit -m "Complete week 3 DNS lab"
git push origin main
```


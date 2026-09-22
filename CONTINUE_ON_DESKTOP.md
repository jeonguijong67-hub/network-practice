# 남은 작업

3주차·4주차 모두 코드와 분석은 끝났습니다. 남은 것은 **한 가지**입니다.

## 남은 것 · 야간 throughput 재측정 (w04 Task 2 Part B)

쓸 수 있는 네트워크가 유선 이더넷 하나뿐이라 `task2.md`의 path (B)
"두 개의 매우 다른 시간대에 측정한다"를 택했습니다.
낮 측정(`ethernet-afternoon`, 2026-09-22 13:18)은 이미 들어가 있으므로,
**밤(22시 이후 권장)에 아래 한 줄만** 실행하면 됩니다.

```powershell
cd C:\Users\정의종\Documents\2026-2\컴퓨터네트워크\my-repo\w04-tcp
python task2_measure.py --label "ethernet-night"
```

그 다음 `w04-tcp/out/observation.md`의 Part B 표에서 `ethernet-night` 행
(측정 시각 / median / min·max / spread / handshake median)을 채우고,
낮과 밤의 차이를 B4·B5 문단에 한두 줄 반영하면 끝입니다.
숫자는 실행 직후 터미널에 그대로 출력되고 `out/throughput.json`에도 누적됩니다.

검사:

```powershell
python test_tasks.py
python ..\check.py w04
```

## 참고 · 이미 끝난 것

- w03: iterative resolver 5/5, steering report, 캐시 275회/stale 0,
  `out/dns.pcapng` 캡처(6패킷, 배경 트래픽 없음)와 report.md의 packet 필드까지 완료
- w04 Task 1: 슬라이딩 윈도우, seed 246·999 포함 10개 seed 전부 IDENTICAL
- w04 Task 2 Part A: handshake 캡처 완료, A2~A5 전부 실측값으로 작성
- w04 Task 3: window가 BDP(20)로 수렴, goodput 98.7% / 손실 2.4% / 큐 0.7 → **strong**

## 알려진 환경 차이

호스트 tshark는 4.6.6이라 boolean 필드를 `True/False`로 출력하는데,
`w03-dns/test_tasks.py`는 `0/1`을 기대합니다. 그래서 캡처가 정상인데도
"0 queries, 0 responses"로 FAIL이 뜹니다. 컨테이너(Ubuntu 24.04, tshark 4.2)에서는
`0/1`이라 통과합니다. 캡처 자체는 질의 3 · 응답 3으로 정상입니다.

## 캡처 파일

`.pcapng`는 `.gitignore`로 커밋되지 않습니다(개인정보 보호). `check.py`도 optional로
처리하므로 제출에는 문제가 없습니다. 분석 결과는 report.md와 observation.md에 들어가 있습니다.

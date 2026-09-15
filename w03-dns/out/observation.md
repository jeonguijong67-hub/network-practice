# Week 3 observations

## Task 1

루트 서버는 `www.korea.ac.kr`의 A 레코드에 대한 권한이 없으므로 주소 대신 `.kr` 쪽 NS delegation을 반환했다. 일반 노트북은 재귀 resolver에 한 번 묻지만, 직접 구현한 resolver는 이 이름에 루트→TLD→권한 서버의 3개 서버를 질의했다.
이번 5개 검증 이름에서는 glue 없는 delegation이 관측되지 않아 추가 lookup은 0회였다. 구현은 glue가 전혀 없을 때 NS 이름을 루트부터 별도 반복 해석하고 그 보조 질의도 `path`에 기록하며, 5개 이름 검증은 5/5 통과했다.

## Task 2

규칙은 CNAME의 최종 조직 도메인이 원래 사이트와 다르면 third-party로 분류하는 것이다. `www.wikipedia.org`가 `wikimedia.org`로 끝나는 경우는 서로 다른 도메인이지만 같은 Wikimedia 조직이므로 이 규칙의 구체적인 false positive였다.
원격 세션의 한 네트워크에서 system/Google/Quad9을 비교했을 때 CDN-hosted 비교 대상 11개 중 4개가 resolver에 따라 다른 주소 집합을 반환했다. 이는 resolver별 steering 증거이지만 두 번째 네트워크를 쓰지 않았으므로 위치 기반 steering 자체를 강하게 입증하지는 못한다.

## Task 3

baseline은 리스트 선형 탐색으로 느리고, 모든 레코드에 고정 60초를 써서 실제 TTL을 무시하므로 만료 응답을 반환한다. 특히 TTL 20초인 `www.microsoft.com`은 각 조회 후 최대 40초 동안 stale 상태가 될 수 있어 가장 나쁘다.
개선 캐시는 dict와 권한 서버 TTL을 사용해 stale 0, upstream 275회를 기록했다. 275회가 이 workload의 정확한 캐시 하한인 이유는 각 이름의 최초 요청과 이전 조회의 TTL 만료 후 첫 요청은 어떤 올바른 캐시도 upstream에서 새 레코드를 받지 않고 답할 수 없기 때문이다.

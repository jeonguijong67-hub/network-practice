#!/usr/bin/env bash
# 6주차 Task 2 - 재수렴 시간을 커널 경로 이벤트로 잰다
#
#   bash w06-routing/measure.sh NAME WAIT 'r1 에서 실행할 명령'
#
# scenario.sh cut 은 `show ip route ospf` 출력을 1초마다 통째로 비교하는데,
# 그 출력에는 경로 uptime(00:00:29)이 들어 있어 아무 일이 없어도 1초 뒤에
# "바뀌었다"고 판단한다. 그래서 여기서는 세 라우터 모두에서
# `ip -ts monitor route` 를 띄워 zebra 가 커널 FIB 를 고친 순간을 µs 단위로 받는다.
# 세 컨테이너는 같은 커널(Docker VM)의 시계를 쓰므로 시각을 그대로 비교할 수 있다.
#
# T0 는 r1 이 명령 직전에 넣는 표식 경로(192.0.2.x, 문서용 주소)의 이벤트다.
# 결과: out/measure/NAME.{before,after,log}.txt
set -u
cd "$(dirname "$0")/.." || exit 1
OUT="w06-routing/out/measure"; mkdir -p "$OUT"
DC="docker compose --profile routing"
NAME=$1 WAIT=$2 ACTION=$3
MARK="192.0.2.$((RANDOM % 250 + 1))/32"

tables() {
  for r in r1 r2 r3; do
    echo "===== $r"
    $DC exec -T $r vtysh -c "show ip route ospf" 2>/dev/null \
      | grep -E '^[ OCK>*]+[0-9]|^ +\*? +via' \
      | sed -E 's/, ([0-9]{2}:){2}[0-9]{2}$//; s/, [0-9]+[wdh][0-9a-z]+$//'
  done
}

tables > "$OUT/$NAME.before.txt"
for r in r1 r2 r3; do
  $DC exec -T $r sh -c 'pkill -f "ip -t[s] monitor" 2>/dev/null; true'
  $DC exec -d $r sh -c 'exec ip -ts monitor route > /tmp/mon.log 2>&1'
done
sleep 1

$DC exec -T r1 sh -c "ip route add blackhole $MARK && $ACTION"
sleep "$WAIT"

tables > "$OUT/$NAME.after.txt"
: > "$OUT/$NAME.log.txt"
for r in r1 r2 r3; do
  $DC exec -T $r sh -c 'pkill -f "ip -t[s] monitor"; cat /tmp/mon.log' \
    | sed "s/^/$r /" >> "$OUT/$NAME.log.txt"
done
$DC exec -T r1 ip route del blackhole "$MARK" 2>/dev/null

if python3 -c '' 2>/dev/null; then PY=python3; else PY=python; fi
$PY - "$OUT/$NAME.log.txt" "$MARK" "$NAME" <<'EOF'
import re, sys
from datetime import datetime
path, mark, name = sys.argv[1], sys.argv[2].split("/")[0], sys.argv[3]
events, t0 = [], None
for line in open(path, encoding="utf-8"):
    m = re.match(r"(r\d) \[([\d\-T:.]+)\] ?(.*)", line.rstrip())
    if not m:
        continue
    r, ts, what = m.groups()
    t = datetime.fromisoformat(ts).timestamp()
    if mark in what:
        t0 = t0 or t
        continue
    events.append((t, r, what))
if t0 is None:
    sys.exit("no marker event")
print(f"== {name}  (T0 = marker on r1)")
last = {}
for t, r, what in sorted(events):
    print(f"  +{t - t0:7.3f}s  {r}  {what[:90]}")
    last[r] = t - t0
for r in ("r1", "r2", "r3"):
    print(f"  {r} last route change: " + (f"+{last[r]:.3f}s" if r in last else "none"))
if last:
    print(f"  converged (last change anywhere): +{max(last.values()):.3f}s")
EOF

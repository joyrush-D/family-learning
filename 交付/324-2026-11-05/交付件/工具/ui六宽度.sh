#!/bin/bash
# 315 网页新 UI 六宽度证据：隔离快照数据 + 补虚构任务到 5 张今天卡 + 无头 Playwright 量测
set -u
here=$(cd "$(dirname "$0")" && pwd)
DEL=$(cd "$here/.." && pwd)
NUMBER=${FAMILY_REBUILD_NUMBER:-319}
REPO=${FAMILY_LEARNING_REPO:-/Users/joyrush/.local/share/family-learning/public-integration-20260926}
SNAP="$DEL/演示数据/十八渠道快照"
OUT="$DEL/证据/screens-${NUMBER}/六宽度"
LOG=${UI_LOG:-/dev/null}
PLAYWRIGHT_MODULE=${PLAYWRIGHT_MODULE:-/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright}
NODE=${NODE:-/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}
DAY=${FAMILY_TODAY:-}
TMP=$(mktemp -d /tmp/ui315.XXXXXX)
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
PID=""
cleanup() {
  [ -n "$PID" ] && kill "$PID" 2>/dev/null || true
  sleep 0.4
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM
rm -rf "$OUT"; mkdir -p "$OUT"
: > "$LOG"
say() { printf '%s\n' "$*" | tee -a "$LOG"; }
say "六宽度证据（REPO 网页资源，隔离快照数据，不打开 App）"
say "运行时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "REPO: $REPO"
say "快照: ${SNAP}（隔离副本，不改快照、不改 REPO）"
say "临时目录: $TMP  端口: $PORT  固定日: ${DAY:-（真实今天）}"
rsync -a --exclude .git --exclude private --exclude __pycache__ "$REPO/" "$TMP/repo/" || { say 'rsync 失败'; exit 1; }
mkdir -p "$TMP/data"
cp -R "$SNAP/data/." "$TMP/data/"
cp "$SNAP/家庭运行规则.md" "$TMP/repo/家庭运行规则.md"
# 仅临时副本：把 app.py 的"今天"固定到 FAMILY_TODAY（产品源码不改）
if [ -n "$DAY" ]; then
  python3 - "$TMP/repo/app.py" "$DAY" <<'PYPATCH'
import sys
p, day = sys.argv[1], sys.argv[2]
s = open(p, encoding='utf-8').read()
old = "today=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()"
new = "today=os.environ.get('FAMILY_TODAY') or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat()"
assert s.count(old) >= 2, s.count(old)
open(p, 'w', encoding='utf-8').write(s.replace(old, new))
print('已给临时 app.py 加 FAMILY_TODAY 固定日', day)
PYPATCH
fi
( cd "$TMP/repo" && exec env FAMILY_DATA="$TMP/data" ${DAY:+FAMILY_TODAY="$DAY"} PORT=$PORT python3 -B app.py ) > "$TMP/server.log" 2>&1 &
PID=$!
ready=0
for _ in $(seq 1 100); do
  if curl -fsS "http://127.0.0.1:$PORT/api/state" > "$TMP/state.json" 2>/dev/null; then ready=1; break; fi
  sleep 0.15
done
[ "$ready" = 1 ] || { say '后台未就绪'; cat "$TMP/server.log" | tee -a "$LOG"; exit 1; }
say "后台就绪 http://127.0.0.1:$PORT"
python3 - "$PORT" "$TMP/seed.json" <<'PY' | tee -a "$LOG"
import json, os, sys, urllib.request
BASE = 'http://127.0.0.1:' + sys.argv[1]
OUT = sys.argv[2]
def req(path, data=None, token=None):
    r = urllib.request.Request(BASE + path)
    if data is not None:
        r.data = json.dumps(data, ensure_ascii=False).encode()
        r.add_header('Content-Type', 'application/json'); r.method = 'POST'
    if token: r.add_header('X-Family-Token', token)
    with urllib.request.urlopen(r) as resp: return json.load(resp)
st = req('/api/state')
tok = st['token']; today = st['today']; child = st['children'][0]
def today_count(cid):
    d = req('/api/day?child_id=' + cid)
    n = 0; rows = []
    for g in (d.get('groups') or []) + (d.get('undated') or []):
        for it in g['items']:
            rows.append(it)
            if it.get('today'): n += 1
    return n, rows
n, rows = today_count(child['id'])
print('初始 today 项:%d（%s / %s）' % (n, child['id'], child['name']))
TARGET = int(os.environ.get('FAMILY_SHOT_TARGET', '5'))
if os.environ.get('FAMILY_SHOT_NO_SEED') == '1': TARGET = n
fictional = [
  ('语文：完成《识字小卡》练习', '今天完成，不用抄写。'),
  ('英语：跟读Unit 7第3—10个单词', '跟读Unit 7第3—10个单词，每词3遍，不用抄写。'),
  ('语文：背诵《风经过小巷》最后一段', '背诵最后一段，请家长听一遍。'),
  ('数学：完成《每日练习》第27页第4—6题', '写出计算过程，今天完成。'),
]
made = []
i = 0
while n < TARGET and i < len(fictional):
    title, action = fictional[i]; i += 1
    out = req('/api/task/new', dict(child=child['name'], title=title, due=today, action=action), tok)
    made.append(out['task']['id']); n += 1
    print('补入虚构任务:', out['task']['title'])
n2, rows2 = today_count(child['id'])
print('seed 后 today 项:%d' % n2)
print('today 标题:', ' / '.join(r['title'] for r in rows2 if r.get('today')))
json.dump({'base': BASE, 'today': today, 'child': child, 'added': made, 'today_count': n2, 'titles': [r['title'] for r in rows2 if r.get('today')]}, open(OUT, 'w'), ensure_ascii=False, indent=1)
assert n2 == TARGET, ('today', n2, TARGET)
PY
seed_rc=$?
say "播种退出码: $seed_rc"
[ "$seed_rc" = 0 ] || exit 1
set +e
PLAYWRIGHT_MODULE="$PLAYWRIGHT_MODULE" OUT="$OUT" BASE="http://127.0.0.1:${PORT}/?child_id=child-1" "$NODE" "$here/ui七宽度.cjs" >> "$LOG" 2>&1
rc=$?
set -e
say "量测退出码: $rc"
if [ -f "$OUT/metrics.json" ]; then python3 - "$OUT/metrics.json" <<'PYF'
import json,sys
d=json.load(open(sys.argv[1]))
print("failures:", json.dumps(d.get("failures"), ensure_ascii=False))
PYF
fi
exit "$rc"

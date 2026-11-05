#!/bin/bash
# Build 322 深链接六宽度证据：隔离快照数据（固定日 2026-11-04）+ 无头 Playwright，不打开 App
set -u
here=$(cd "$(dirname "$0")" && pwd)
DEL=$(cd "$here/.." && pwd)
REPO=${FAMILY_LEARNING_REPO:-/Users/joyrush/.local/share/family-learning/public-integration-20260926}
SNAP="$DEL/演示数据/十八渠道快照"
OUT="$DEL/证据/screens-322/深链接"
LOG=${UI_LOG:-/dev/null}
PLAYWRIGHT_MODULE=${PLAYWRIGHT_MODULE:-/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright}
NODE=${NODE:-/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node}
DAY=${FAMILY_TODAY:-2026-11-04}
TASK_ID=${TASK_ID:-AGENT-5d27ac7f28c9ee5d2ed99634}
TMP=$(mktemp -d /tmp/deep322.XXXXXX)
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
PID=""
cleanup() { [ -n "$PID" ] && kill "$PID" 2>/dev/null || true; sleep 0.4; rm -rf "$TMP"; }
trap cleanup EXIT INT TERM
rm -rf "$OUT"; mkdir -p "$OUT"; : > "$LOG"
say() { printf '%s\n' "$*" | tee -a "$LOG"; }
say "Build 322 深链接六宽度证据（隔离快照，不打开 App）"
say "运行时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "REPO: $REPO"; say "快照: ${SNAP}（隔离副本）"; say "固定日: ${DAY}  任务: ${TASK_ID}  端口: ${PORT}"
rsync -a --exclude .git --exclude private --exclude __pycache__ "$REPO/" "$TMP/repo/" || { say 'rsync 失败'; exit 1; }
mkdir -p "$TMP/data"; cp -R "$SNAP/data/." "$TMP/data/"
cp "$SNAP/家庭运行规则.md" "$TMP/repo/家庭运行规则.md"
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
( cd "$TMP/repo" && exec env FAMILY_DATA="$TMP/data" FAMILY_TODAY="$DAY" PORT=$PORT python3 -B app.py ) > "$TMP/server.log" 2>&1 &
PID=$!
ready=0
for _ in $(seq 1 120); do curl -fsS "http://127.0.0.1:$PORT/api/state" > "$TMP/state.json" 2>/dev/null && { ready=1; break; }; sleep 0.15; done
[ "$ready" = 1 ] || { say '后台未就绪'; cat "$TMP/server.log" | tee -a "$LOG"; exit 1; }
say "后台就绪 http://127.0.0.1:${PORT}"
set +e
PLAYWRIGHT_MODULE="$PLAYWRIGHT_MODULE" OUT="$OUT" BASE="http://127.0.0.1:${PORT}/" TASK_ID="$TASK_ID" CHILD_ID=child-1 DAY="$DAY" "$NODE" "$here/深链接量测.cjs" >> "$LOG" 2>&1
rc=$?
set -e
say "深链接量测退出码: $rc"
[ -f "$OUT/metrics.json" ] && python3 - "$OUT/metrics.json" <<'PYF'
import json,sys
d=json.load(open(sys.argv[1]))
print("failures:", json.dumps(d.get("failures"), ensure_ascii=False))
PYF
exit "$rc"

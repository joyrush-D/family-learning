#!/bin/bash
set -u
NUMBER=${FAMILY_REBUILD_NUMBER:-315}
DEL=/Users/joyrush/Documents/deepseek-harness/default-workspace/work/deliverable
REPO=/Users/joyrush/.local/share/family-learning/public-integration-20260926
SNAP="$DEL/演示数据/十八渠道快照"
OUT="$DEL/证据/原生标记完成-契约-${NUMBER}.txt"
TMP=$(mktemp -d /tmp/contract315.XXXXXX)
PORT=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')
PID=""
cleanup(){ [ -n "$PID" ] && kill "$PID" 2>/dev/null || true; sleep 0.3; rm -rf "$TMP"; }
trap cleanup EXIT
rsync -a --exclude .git --exclude private --exclude __pycache__ "$REPO/" "$TMP/repo/"
mkdir -p "$TMP/data"; cp -R "$SNAP/data/." "$TMP/data/"; cp "$SNAP/家庭运行规则.md" "$TMP/repo/家庭运行规则.md"
( cd "$TMP/repo" && FAMILY_DATA="$TMP/data" PORT=$PORT exec python3 -B app.py ) > "$TMP/server.log" 2>&1 &
PID=$!
for _ in $(seq 1 100); do curl -fsS "http://127.0.0.1:$PORT/api/state" -o "$TMP/state.json" 2>/dev/null && break; sleep 0.15; done
python3 - "$PORT" > "$TMP/result.txt" 2>&1 <<'PY'
import json,sys,urllib.request
BASE='http://127.0.0.1:'+sys.argv[1]
def req(path,data=None,token=None):
    r=urllib.request.Request(BASE+path)
    if data is not None:
        r.data=json.dumps(data,ensure_ascii=False).encode(); r.add_header('Content-Type','application/json'); r.method='POST'
    if token: r.add_header('X-Family-Token',token)
    with urllib.request.urlopen(r) as resp: return json.load(resp)
st=req('/api/state'); tok=st['token']; print('GET /api/state -> children:', [c['name'] for c in st['children']], 'token ok')
child=st['children'][0]
d=req('/api/day?child_id='+child['id']+'&day=2026-11-04')
def rows(d):
    out=[]
    for g in (d.get('groups') or []):
        for it in g.get('items') or []:
            out.append((g.get('subject'),it))
    for g in (d.get('undated') or []):
        for it in g.get('items') or []: out.append(('日期未定',it))
    return out
before=d['counts'].copy()
print('GET /api/day?day=2026-11-04 -> counts:', json.dumps(before,ensure_ascii=False))
target=None
for subj,it in rows(d):
    tid=it.get('task_id') or it.get('id')
    if it.get('kind')=='task' and tid and not it.get('done'):
        target=(subj,it,tid); break
assert target, 'no task item'
subj,it,tid=target
print('待标记项: subject=%s kind=%s task_id=%s title=%s' % (subj,it.get('kind'),tid,it.get('title')))
print('   item keys:', ','.join(sorted(it.keys())))
body={'id':tid,'status':'已完成','note':'家长通过清单勾选确认此事项已完成。'}
print('POST /api/task body:', json.dumps(body,ensure_ascii=False))
resp=req('/api/task',body,tok)
print('POST /api/task ->', json.dumps(resp,ensure_ascii=False)[:500])
d2=req('/api/day?child_id='+child['id']+'&day=2026-11-04')
after=d2['counts'].copy()
print('GET /api/day after -> counts:', json.dumps(after,ensure_ascii=False))
titles=[it.get('title') for _,it in rows(d2)]
print('列表是否仍含该项:', it.get('title') in titles)
print('counts.closed 变化: %s -> %s (+%s)' % (before.get('closed'), after.get('closed'), (after.get('closed') or 0)-(before.get('closed') or 0)))
print('counts.open 变化: %s -> %s' % (before.get('open'), after.get('open')))
assert it.get('title') not in titles, 'item still visible'
assert (after.get('closed') or 0)==(before.get('closed') or 0)+1, 'closed not +1'
print('RESULT: OK（服务端契约通过：POST /api/task 后该项从清单消失、closed +1）')
PY
{
 echo "原生「标记完成」服务端契约证据（Build 315）"
 echo "记录时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
 echo "隔离方式: REPO 工作区 rsync 到临时目录（排除 .git/private/__pycache__），快照 data/ 与 家庭运行规则.md 拷入临时目录；未写 REPO、未打开 App。"
 echo "临时端口: $PORT"
 echo "接口: GET /api/state 取 token → GET /api/day?child_id=child-1&day=2026-11-04 → POST /api/task {\"id\":<task_id>,\"status\":\"已完成\",\"note\":...}（X-Family-Token）→ 再 GET /api/day"
 echo "----"
 cat "$TMP/result.txt"
 echo "----"
 echo "服务端日志末尾:"
 tail -3 "$TMP/server.log"
} > "$OUT" 2>&1
echo "wrote $OUT"

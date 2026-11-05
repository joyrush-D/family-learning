#!/bin/sh
# 复现自检：起服务 → curl /api/day → 断言 8 行 / 5 个 today 任务 / 2 个明天带物 / 1 张取消卡 / 8 组各 1 行
# 用法：PRODUCT=<产品源码目录> ./verify-demo.sh
set -e
PRODUCT=${PRODUCT:-/Users/joyrush/.local/share/family-learning/public-integration-20260926}
SNAP=${SNAP:-$(cd "$(dirname "$0")" && pwd)/demo-snapshot}
PORT=${PORT:-8799}
# app.py 只从自己所在目录读 家庭运行规则.md；快照里的是全虚构两行，产品 .gitignore 已忽略该文件
cp "$SNAP/家庭运行规则.md" "$PRODUCT/家庭运行规则.md"
cleanup() { kill "$SERVER" 2>/dev/null || true; rm -f "$PRODUCT/家庭运行规则.md"; }
FAMILY_DATA="$SNAP/data" PORT="$PORT" python3 -B "$PRODUCT/app.py" >/tmp/merge18-demo.log 2>&1 &
SERVER=$!
trap cleanup EXIT INT TERM
sleep 2
python3 - "$PORT" <<'PY'
import json,sys,urllib.request
port=sys.argv[1]
days={c:json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/api/day?child_id='+c+'&day=2026-11-04'))
      for c in ('child-1','child-2')}
def rows(d):
    out=[]
    for group in (d.get('groups') or [])+(d.get('undated') or []): out+=group['items']
    return out+list(d.get('upcoming') or [])
allrows=[r for d in days.values() for r in rows(d)]
assert len(allrows)==8,('rows',len(allrows),[(r['title'],r.get('day')) for r in allrows])
today=[r for r in allrows if r.get('today')]
assert len(today)==5,('today',[r['title'] for r in today])
for word in ('朗读','第26页','英语','识字小卡','计算小卡'):
    assert sum(word in str(r['title']) for r in today)==1,(word,[r['title'] for r in today])
future=[r for r in allrows if r.get('day')=='2026-11-05']
assert len(future)==2 and {str(r['title']) for r in future}=={'明天带一盒彩笔','带一张一寸证件照交班主任'},('future',[r['title'] for r in future])
cancelled=[r for r in allrows if '取消' in str(r.get('title') or '')]
assert len(cancelled)==1,('cancelled',[r['title'] for r in cancelled])
# 8 组同事项各一行：清单共 8 行且标题唯一；每出一条消息只落一行（m04 以“后到原文”注记在数学任务来源中，不占引用）
def row_of(ref):
    hits=[r for r in allrows if any(p['ref'].endswith(':'+ref) for p in (r.get('publications') or []))]
    assert len(hits)==1,(ref,[r['title'] for r in hits])
    return hits[0]['title']
assert len({r['title'] for r in allrows})==8
for group in ({'h18-m01','h18-m09'},{'h18-m02','h18-m18','h18-m10'},{'h18-m05','h18-m13'},
              {'h18-m07','h18-m12'},{'h18-m03','h18-m16','h18-m11'},{'h18-m08','h18-m15'}):
    titles={row_of(ref) for ref in group}
    assert len(titles)==1,(group,titles)
# 明天才带的两项走 upcoming 卡片（/api/day 的 upcoming 项不含 publications），已由上面的标题断言覆盖
print('OK rows=%d today=%d future=%d cancelled=%d matters=8/8' % (len(allrows),len(today),len(future),len(cancelled)))
print('today:', ' / '.join(r['title'] for r in today))
PY

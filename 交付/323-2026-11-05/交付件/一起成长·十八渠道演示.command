#!/bin/bash
# 一起成长 · 十八渠道演示（macOS 双击运行）
# ---------------------------------------------------------------------------
# 这是一个「静态数据回放」演示，不是实时抽取：
#   work/merge18 曾用真模型（doubao-seed-evolving）把 18 条多渠道虚构消息跑过产品自己的
#   ingest → Agent 抽取 → 待核对 → 接受任务 通路，产物冻结为 演示数据/十八渠道快照/。
#   本脚本只回放那份快照（sqlite3 + 附件），**不会调用任何模型、不会联网外发**。
#
# 双击后它会：
#   1. 把产品源码只读复制到系统临时目录（不改 REPO 任何文件），把快照的 data/ 与
#      家庭运行规则.md 放进临时树（app.py 只从自己所在目录读这个档案文件）；
#   2. 在 127.0.0.1 的自由端口起 python3 -B app.py（FAMILY_DATA 指向临时副本）；
#   3. 在 ./.support-十八渠道/desktop.json 写本次演示专用的 service_origin，
#      再用 open --env FAMILY_DESKTOP_SUPPORT_DIR 交给 App —— 不覆盖家长真实的 App 配置；
#   4. 启动同目录下的「一起成长.app」（客户端 App，连到本机这份虚构快照）。
#
# 预期画面（day=2026-11-04）：
#   child-1 示例甲：3 条今天必做 + 1 张「美术：带两片落叶（已取消）」待核卡；
#   child-2 示例乙：2 条今天必做 + 2 条「即将/以后安排」的明天带物；
#   合计 8 行 = 5 个今天必做 + 2 个明天带物 + 1 张取消卡；8 组同事项各合 1 行，0 重复卡。
#
# 停止后台（任选一种）：
#   * 双击本文件前先在终端执行：  ./一起成长·十八渠道演示.command --stop
#   * 或者：                      kill "$(cat .runtime-十八渠道/demo.pid)"
#   * 回放数据在临时目录里，后台停止后整份删除；不会碰任何真实家庭数据。
#
# 自检（不启动 App，跑完断言后干净退出；退出码 0 才算通过）：
#   sh 一起成长·十八渠道演示.command --check      # 等价别名：--no-launch
#
# 只起后台供其他脚本截图/取证（不打开 App，后台保留到 --stop）：
#   sh 一起成长·十八渠道演示.command --serve
# ---------------------------------------------------------------------------
set -u
set -o pipefail

here=$(cd "$(dirname "$0")" && pwd)
cd "$here" || exit 1

APP="$here/一起成长.app"
SNAP="$here/演示数据/十八渠道快照"
SUPPORT="$here/.support-十八渠道"
RUNTIME="$here/.runtime-十八渠道"
EVIDENCE="$here/证据"
DAY=2026-11-04
FIXED_PORT="${FAMILY_CHANNEL_DEMO_PORT:-}"
PY="${FAMILY_CHANNEL_DEMO_PYTHON:-python3}"
PIDFILE="$RUNTIME/demo.pid"
DEMO_LOG="$RUNTIME/demo.log"
SERVER_FILE="$RUNTIME/server-dir"
DATA_FILE="$RUNTIME/data-dir"
PORT_FILE="$RUNTIME/port"

PORT=""
ORIGIN=""
SERVER=""
DATA=""
DEMO_PID=""
cleanup_after=0

say() { printf '%s\n' "$*"; }
say_err() { printf '%s\n' "$*" >&2; }
die() { say_err "错误：$*"; exit 1; }

usage() {
    cat <<'USAGE'
一起成长 · 十八渠道演示

  ./一起成长·十八渠道演示.command              回放 18 条渠道快照、打开 App
  ./一起成长·十八渠道演示.command --check      只跑后台+断言，不打开 App（退出码 0 通过）
  ./一起成长·十八渠道演示.command --no-launch  同 --check
  ./一起成长·十八渠道演示.command --serve      只起后台并保留（不打开 App），供截图/取证
  ./一起成长·十八渠道演示.command --stop       停止本演示启动的虚构后台
  ./一起成长·十八渠道演示.command --help       显示本说明

可用环境变量：FAMILY_LEARNING_REPO（REPO 路径）、FAMILY_CHANNEL_DEMO_PORT（默认自动选自由端口）、
              FAMILY_CHANNEL_DEMO_PYTHON（默认 python3）。
USAGE
}

mode=launch
for argument in "$@"; do
    case "$argument" in
        --check|--no-launch) mode=check ;;
        --serve) mode=serve ;;
        --stop) mode=stop ;;
        -h|--help|help) mode=help ;;
        *) say_err "未知参数：$argument"; usage; exit 2 ;;
    esac
done

if [ "$mode" = help ]; then
    usage
    exit 0
fi

# REPO：优先环境变量，其次本机公开源码默认位置（$HOME 相对，不写死别人的 home），再找演示包旁的副本。
find_repo() {
    local candidate
    for candidate in "${FAMILY_LEARNING_REPO:-}" \
                     "$HOME/.local/share/family-learning/public-integration-20260926" \
                     "$here/repo" "$here/../public-integration-20260926"; do
        if [ -n "$candidate" ] && [ -f "$candidate/app.py" ] && [ -d "$candidate/packaging/macos" ]; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

port_free() {
    local port="$1"
    "$PY" - "$port" <<'PYCODE' >/dev/null 2>&1
import socket, sys
sock = socket.socket()
try:
    sock.bind(('127.0.0.1', int(sys.argv[1])))
finally:
    sock.close()
PYCODE
}

pick_port() {
    if [ -n "$FIXED_PORT" ]; then
        port_free "$FIXED_PORT" || die "FAMILY_CHANNEL_DEMO_PORT=$FIXED_PORT 已被其他程序占用；换一个端口或清空该变量让脚本自动选。"
        PORT="$FIXED_PORT"
        return 0
    fi
    local candidate
    for candidate in $(seq 8782 8809); do
        if port_free "$candidate"; then
            PORT="$candidate"
            return 0
        fi
    done
    die "8782-8809 没有空闲端口；可用 FAMILY_CHANNEL_DEMO_PORT 指定其他端口。"
}

stop_backend_by_pid() {
    local pid="$1" attempt command
    case "$pid" in
        ''|*[!0-9]*) return 0 ;;
    esac
    kill -0 "$pid" 2>/dev/null || return 0
    command=$(ps -o command= -p "$pid" 2>/dev/null || true)
    case "$command" in
        *app.py*) ;;
        *) say_err "跳过：PID $pid 已不是本演示的 app.py（当前命令：${command}）"; return 0 ;;
    esac
    kill "$pid" 2>/dev/null || true
    attempt=0
    while kill -0 "$pid" 2>/dev/null && [ "$attempt" -lt 40 ]; do
        sleep 0.1
        attempt=$((attempt + 1))
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
    say "已停止十八渠道演示后台（PID ${pid}）。"
}

remove_temp_tree() {
    local server data
    server=$(cat "$SERVER_FILE" 2>/dev/null || true)
    data=$(cat "$DATA_FILE" 2>/dev/null || true)
    case "$server" in
        "${TMPDIR:-/tmp}"/*|/tmp/*|/private/var/folders/*) rm -rf "$server" ;;
    esac
    case "$data" in
        "${TMPDIR:-/tmp}"/*|/tmp/*|/private/var/folders/*) rm -rf "$data" ;;
    esac
    rm -f "$SERVER_FILE" "$DATA_FILE" "$PORT_FILE" "$PIDFILE"
}

stop_demo() {
    local pid
    pid=$(cat "$PIDFILE" 2>/dev/null || true)
    if [ -n "$pid" ]; then
        stop_backend_by_pid "$pid"
    fi
    remove_temp_tree
    DEMO_PID=""
}

on_exit() {
    if [ "$cleanup_after" = 1 ]; then
        stop_demo
    fi
}
trap on_exit EXIT

if [ "$mode" = stop ]; then
    stop_demo
    exit 0
fi

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
[ -d "$SNAP/data" ] || die "找不到演示快照：$SNAP/data（本交付包内的 演示数据/十八渠道快照/ 应包含 data/ 与 家庭运行规则.md）"
[ -f "$SNAP/家庭运行规则.md" ] || die "演示快照缺少 家庭运行规则.md：$SNAP"
[ -f "$SNAP/data/family.sqlite3" ] || die "演示快照缺少 data/family.sqlite3：$SNAP"
if [ "$mode" != "check" ] && [ ! -d "$APP" ]; then
    die "找不到 App：${APP}（请保持 App 与本 .command 在同一目录）"
fi

REPO=$(find_repo) || die "找不到公开源码 REPO（需要 app.py 与 packaging/macos）；可用 FAMILY_LEARNING_REPO 指定路径。"
[ -f "$REPO/app.py" ] || die "REPO 缺少 app.py：$REPO"
"$PY" -c 'import sys' >/dev/null 2>&1 || die "找不到可用的 Python：${PY}（可用 FAMILY_CHANNEL_DEMO_PYTHON 指定）"

# 已在跑就先停掉旧的（只停本脚本记录的 PID），避免端口/临时目录混乱。
old_pid=$(cat "$PIDFILE" 2>/dev/null || true)
if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    say "发现上次演示后台还在运行（PID ${old_pid}），先停止。"
    stop_demo
fi
mkdir -p "$RUNTIME" "$EVIDENCE"
chmod 700 "$RUNTIME" 2>/dev/null || true

pick_port
ORIGIN="http://127.0.0.1:$PORT"

# ---------------------------------------------------------------------------
# 准备临时树：产品源码只读副本 + 快照数据副本（不写 REPO）
# ---------------------------------------------------------------------------
TMPROOT=$(mktemp -d "${TMPDIR:-/tmp}/yiqichengzhang-18.XXXXXX") || die "无法创建临时目录"
SERVER="$TMPROOT/server"
DATA="$TMPROOT/data"
mkdir -p "$SERVER" "$DATA" || die "无法创建临时目录：$TMPROOT"
printf '%s\n' "$SERVER" > "$SERVER_FILE"
printf '%s\n' "$DATA" > "$DATA_FILE"
printf '%s\n' "$PORT" > "$PORT_FILE"
chmod 600 "$SERVER_FILE" "$DATA_FILE" "$PORT_FILE" 2>/dev/null || true

say "REPO  : $REPO"
say "快照  : $SNAP"
say "端口  : $PORT"
say "数据来源：2026-11-04 的真模型运行（doubao-seed-evolving，8 次模型调用）——本次是回放，不再调用模型。"

rsync -a --exclude '.git' --exclude 'private' --exclude '__pycache__' --exclude '.DS_Store' "$REPO/" "$SERVER/" \
    || die "只读复制产品源码到临时目录失败"
cp -Rp "$SNAP/data/." "$DATA/" || die "复制快照 data/ 到临时目录失败"
cp -p "$SNAP/家庭运行规则.md" "$SERVER/家庭运行规则.md" || die "把虚构档案放进临时源码树失败"
[ -f "$DATA/family.sqlite3" ] || die "临时数据目录缺少 family.sqlite3"

# ---------------------------------------------------------------------------
# 起后台
# ---------------------------------------------------------------------------
start_backend() {
    local started
    started=$(date +%s)
    ( cd "$SERVER" && exec env FAMILY_DATA="$DATA" PORT="$PORT" "$PY" -B app.py ) > "$DEMO_LOG" 2>&1 &
    DEMO_PID=$!
    printf '%s\n' "$DEMO_PID" > "$PIDFILE"
    disown "$DEMO_PID" 2>/dev/null || true
    case "$DEMO_PID" in
        ''|*[!0-9]*) die "后台进程没有正常启动（看日志：${DEMO_LOG}）" ;;
    esac
    local attempt=0
    while [ "$attempt" -lt 200 ]; do
        if curl -sf "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
            START_SECONDS=$(python3 -c "import time;print(round(time.time()-$started,2))" 2>/dev/null || echo '?')
            return 0
        fi
        if ! kill -0 "$DEMO_PID" 2>/dev/null; then
            say_err "后台进程提前退出，日志如下："
            tail -20 "$DEMO_LOG" >&2 || true
            die "十八渠道演示后台启动失败"
        fi
        sleep 0.15
        attempt=$((attempt + 1))
    done
    die "等待后台就绪超时（30 秒）；日志：$DEMO_LOG"
}

wait_space() {
    # 端口占用的进程可能不是我们起的：给出可读提示，保持静默失败。
    local attempt=0
    while [ "$attempt" -lt 20 ]; do
        if curl -sf "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
        attempt=$((attempt + 1))
    done
    return 1
}

# ---------------------------------------------------------------------------
# --check 断言（纯 Python 标准库；只读 GET + 只读 sqlite）
# ---------------------------------------------------------------------------
run_check() {
    "$PY" - "$PORT" "$DATA/family.sqlite3" "$DAY" "$START_SECONDS" <<'PYCODE'
import json
import sqlite3
import sys
import urllib.request

port, db_path, day, start_seconds = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
base = 'http://127.0.0.1:%s' % port


def get(path):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return json.load(response)


def rows_of(payload):
    rows = []
    for group in (payload.get('groups') or []) + (payload.get('undated') or []):
        rows += group['items']
    rows += list(payload.get('upcoming') or [])
    return rows


def fail(message):
    print('断言失败：' + message)
    sys.exit(1)


state = get('/api/state')
children = state.get('children') or []
if len(children) != 2:
    fail('期望 2 个孩子，实际 %r' % [c.get('name') for c in children])

days = {}
all_rows = []
for child in children:
    payload = get('/api/day?child_id=%s&day=%s' % (child['id'], day))
    days[child['id']] = payload
    for row in rows_of(payload):
        row['_child'] = child['name']
        all_rows.append(row)

if len(all_rows) != 8:
    fail('清单应为 8 行（7 活跃 + 1 取消），实际 %d 行：%r' % (len(all_rows), [r.get('title') for r in all_rows]))

today_rows = [r for r in all_rows if r.get('today')]
if len(today_rows) != 5:
    fail('今天必做应为 5 条，实际 %d：%r' % (len(today_rows), [r.get('title') for r in today_rows]))

future_rows = [r for r in all_rows if str(r.get('day') or '') == '2026-11-05']
if len(future_rows) != 2:
    fail('明天（2026-11-05）带物应为 2 条，实际 %d：%r' % (len(future_rows), [r.get('title') for r in future_rows]))
future_titles = {str(r.get('title')) for r in future_rows}
if future_titles != {'明天带一盒彩笔', '带一张一寸证件照交班主任'}:
    fail('明天带物标题不符：%r' % sorted(future_titles))

cancelled = [r for r in all_rows if '取消' in str(r.get('title') or '')]
if len(cancelled) != 1:
    fail('已取消待核卡应为 1 张，实际 %d：%r' % (len(cancelled), [r.get('title') for r in cancelled]))

titles = [str(r.get('title') or '') for r in all_rows]
if len(set(titles)) != 8:
    fail('8 张卡标题应唯一，实际 %d 个不同标题：%r' % (len(set(titles)), titles))

# 同事项归并：18 条消息的引用应各落到唯一一张卡（8 组各 1 卡）。
ref_to_title = {}
for row in all_rows:
    for publication in row.get('publications') or []:
        ref = str(publication.get('ref') or '')
        if ':' in ref:
            ref = ref.rsplit(':', 1)[1]
        ref_to_title.setdefault(ref, set()).add(str(row.get('title') or ''))

# 明天带物两张卡没有 publications 字段（回放数据里是「即将」条目）：
# 消息落点以产品数据库 manual_tasks.source 的引用行为准（真实通路写入的原文引用）。
import re as _re

connection = sqlite3.connect('file:%s?mode=ro' % db_path, uri=True)
try:
    messages = connection.execute('select count(*) from agent_messages').fetchone()[0]
    tasks = connection.execute('select count(*) from manual_tasks').fetchone()[0]
    source_rows = connection.execute('select title, source from manual_tasks').fetchall()
finally:
    connection.close()

db_refs = {}
for title, source in source_rows:
    for ref in _re.findall(r'h18-m\d\d', source or ''):
        db_refs.setdefault(ref, set()).add(str(title))
for ref, titles in db_refs.items():
    if ref not in ref_to_title:
        ref_to_title[ref] = set(titles)

expected_groups = [
    {'h18-m01', 'h18-m09'},
    {'h18-m02', 'h18-m18', 'h18-m10'},
    {'h18-m05', 'h18-m13'},
    {'h18-m07', 'h18-m12'},
    {'h18-m03', 'h18-m16', 'h18-m11'},
    {'h18-m08', 'h18-m15'},
    {'h18-m06', 'h18-m14'},
    {'h18-m17'},
]
if messages != 18:
    fail('快照应含 18 条渠道消息，实际 %d' % messages)
if tasks != 7:
    fail('快照应含 7 条任务，实际 %d' % tasks)
all_refs = {'h18-m%02d' % number for number in range(1, 19)}
if set(ref_to_title) != all_refs:
    missing = sorted(all_refs - set(ref_to_title))
    extra = sorted(set(ref_to_title) - all_refs)
    fail('18/18 消息落点不完整：缺 %r，多 %r' % (missing, extra))
for group in expected_groups:
    found = set()
    for ref in group:
        found |= ref_to_title[ref]
    if len(found) != 1:
        fail('同事项分组未合并到同一行：%r → %r' % (sorted(group), sorted(found)))
landed = len(ref_to_title)
if landed != 18:
    fail('18 条消息应全部有落点，实际 %d' % landed)
m04 = 1 if 'h18-m04' in db_refs else 0
if m04 < 1:
    fail('m04 的「后到更正原文」应写进数学任务来源，实际没找到')

try:
    startup = float(start_seconds)
except (TypeError, ValueError):
    startup = -1.0
if startup >= 0 and startup > 5.0:
    fail('启动耗时 %.2f 秒，超过 5 秒要求' % startup)

print()
print('=== 清单（8 行 = 7 条活跃 + 1 张已取消待核）===')
for row in all_rows:
    label = '今天必做' if row.get('today') else ('已取消待核' if '取消' in str(row.get('title') or '') else '明天/以后')
    print('  [%-6s] %-6s %s' % (row.get('_child') or '', label, row.get('title') or ''))

print()
print('=== 今天必做（5 条）===')
for row in today_rows:
    print('  - ' + str(row.get('title') or ''))
print()
print('=== 同事项归并（8 组，各 1 行；0 重复卡、0 孤儿卡）===')
for group in expected_groups:
    sample = sorted(group)[0]
    print('  %-24s → %s' % ('/'.join(sorted(group)), sorted(ref_to_title[sample])[0]))
print()
print('=== 消息落点 ===')
print('  18/18：17 条渠道消息以引用计入清单；m04 以「后到更正原文」写进数学任务来源（不重复成卡）')
print('  快照：%d 条消息、%d 条任务；清单 8 行、今日 %d、明天带物 %d、取消 %d' % (messages, tasks, len(today_rows), len(future_rows), len(cancelled)))
print()
print('=== 结论 ===')
if startup >= 0:
    print('  启动耗时：%.2f 秒（要求 < 5 秒）' % startup)
print('  断言：通过（8 行 / 今日 5 / 明天带物 2 / 取消 1 / 8 组各 1 行 / 18 条消息全部落点）')
PYCODE
}

prepare_support() {
    mkdir -p "$SUPPORT" || die "无法创建演示配置目录：$SUPPORT"
    chmod 700 "$SUPPORT" 2>/dev/null || true
    printf '{"service_origin":"%s"}\n' "$ORIGIN" > "$SUPPORT/desktop.json" || die "写入桌面配置失败"
    chmod 600 "$SUPPORT/desktop.json" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# 分支
# ---------------------------------------------------------------------------
case "$mode" in
    check|serve)
        start_backend
        say "后台已就绪：${ORIGIN}（启动 ${START_SECONDS} 秒，日志：${DEMO_LOG}）"
        if [ "$mode" = check ]; then
            cleanup_after=1
            run_check > "$EVIDENCE/十八渠道自检-输出.txt" 2>&1
            rc=$?
            cat "$EVIDENCE/十八渠道自检-输出.txt"
            if [ "$rc" -ne 0 ]; then
                say_err "自检未通过（退出码 ${rc}）；后台与临时数据即将清理。"
                exit "$rc"
            fi
            say ""
            say "自检模式：未打开 App。正在停止十八渠道演示后台，临时数据随之清除。"
            exit 0
        fi
        say "演示后台保持运行中（PID ${DEMO_PID}）；打开 App 或用其他脚本截图。"
        say "  停止：sh 一起成长·十八渠道演示.command --stop"
        cleanup_after=0
        exit 0
        ;;
    launch)
            prepare_support
        start_backend
        say "后台已就绪：${ORIGIN}（启动 ${START_SECONDS} 秒）"
        if [ ! -d "$APP" ]; then
            cleanup_after=1
            die "找不到 App：$APP"
        fi
        open -n --env "FAMILY_DESKTOP_SUPPORT_DIR=$SUPPORT" "$APP" || die "启动 App 失败"
        cleanup_after=0
        say ""
        say "已打开「一起成长」；它读取的是本次演示专用配置：$SUPPORT/desktop.json"
        say "（不覆盖家长真实配置 ~/Library/Application Support/local.yiqichengzhang.desktop/desktop.json）"
        say ""
        say "看什么："
        say "  * 顶部可切换孩子：示例甲 / 示例乙；"
        say "  * 示例甲：3 条今天必做 + 1 张「美术：带两片落叶（已取消）」待核卡；"
        say "  * 示例乙：2 条今天必做 + 2 条明天带物（「即将/以后安排」）；"
        say "  * 合计 8 行 = 5 个今天必做 + 2 个明天带物 + 1 张取消卡，同事项各合 1 行。"
        say ""
        say "停止后台：sh 一起成长·十八渠道演示.command --stop"
        say "证据与快照：$EVIDENCE/、$SNAP"
        ;;
esac

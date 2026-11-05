#!/bin/bash
# 一起成长 · 虚构一日演示（macOS 双击运行）
# ---------------------------------------------------------------------------
# 双击后它会：
#   1. 在 127.0.0.1:8766 启动 REPO/demo.py（全虚构演示后台，数据只写系统临时目录）；
#   2. 用 Python 通过公开 API POST /api/task/new 播种「完整一天」的虚构事项；
#   3. 在 ./.support/ 写一个只属于本次演示的 desktop.json（service_origin 指向 8766），
#      再用 open --env FAMILY_DESKTOP_SUPPORT_DIR 把这份独立配置交给 App —— 不覆盖家长真实的 App 配置；
#   4. 启动同目录下的「一起成长.app」（客户端 App，连到本机这个虚构后台）。
#
# 停止后台（任选一种）：
#   * 双击本文件前先在终端执行：  ./一起成长·虚构一日演示.command --stop
#   * 或者：                      kill "$(cat .runtime/demo.pid)"
#   * 后台的演示数据在它自己的临时目录里（REPO/demo.py:12-13 的 tempfile.TemporaryDirectory），
#     进程一停就整份清除；不会留下、也不会碰任何真实家庭数据。
#
# 自检（不启动 App，跑完后端+播种+断言后干净退出）：
#   sh 一起成长·虚构一日演示.command --check      # 等价别名：--no-launch
#
# 只起后台供其他脚本取证/截图（不打开 App，后台保留到 --stop）：
#   sh 一起成长·虚构一日演示.command --serve
# ---------------------------------------------------------------------------
set -u
set -o pipefail

here=$(cd "$(dirname "$0")" && pwd)
cd "$here" || exit 1

APP="$here/一起成长.app"
SEED="$here/演示数据/seed.py"
SUPPORT="$here/.support"
RUNTIME="$here/.runtime"
EVIDENCE="$here/证据"
PORT="${FAMILY_DEMO_PORT:-8766}"
ORIGIN="http://127.0.0.1:$PORT"
PY="${FAMILY_DEMO_PYTHON:-python3}"
# 可选：播种真模型抽取产物（默认仍用 seed.py 内置的 7 条手写故事）。
#   FAMILY_SEED_FROM_REAL_RUN=1         → 用交付包内的 演示数据/real-model-run.json
#   FAMILY_SEED_FROM_REAL_RUN=/path.json → 用指定文件
REAL_RUN="${FAMILY_SEED_FROM_REAL_RUN:-}"
case "$REAL_RUN" in
    1|true|TRUE|yes) REAL_RUN="$here/演示数据/real-model-run.json" ;;
    0|false|FALSE|off|"") REAL_RUN="" ;;
esac
PIDFILE="$RUNTIME/demo.pid"
DEMO_LOG="$RUNTIME/demo.log"

say() { printf '%s\n' "$*"; }
say_err() { printf '%s\n' "$*" >&2; }
die() { say_err "错误：$*"; exit 1; }

# 退出时清理：自检模式（以及启动失败时）自动停掉本次拉起的虚构后台；
# 双击启动成功后置 0，后台留给 App 使用，由 --stop 或 .runtime/demo.pid 停止。
cleanup_after=0
on_exit() { if [ "$cleanup_after" = 1 ]; then stop_demo; fi; }
trap on_exit EXIT

usage() {
    cat <<'USAGE'
一起成长 · 虚构一日演示

  ./一起成长·虚构一日演示.command              启动虚构后台、播种、打开 App
  ./一起成长·虚构一日演示.command --check      只跑后台+播种+自检，不打开 App
  ./一起成长·虚构一日演示.command --no-launch  同 --check
  ./一起成长·虚构一日演示.command --serve      只起后台+播种并保留（不打开 App），供截图/取证
  ./一起成长·虚构一日演示.command --stop       停止本演示启动的虚构后台
  ./一起成长·虚构一日演示.command --help       显示本说明

可用环境变量：FAMILY_LEARNING_REPO（REPO 路径）、FAMILY_DEMO_PORT（默认 8766）、
              FAMILY_DEMO_PYTHON（默认 python3）、FAMILY_DEMO_CHILD（播种给哪个孩子）、
            FAMILY_SEED_FROM_REAL_RUN（=1 用交付包内真模型抽取结果播种；默认用内置故事）。
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

# REPO：优先环境变量，其次本机公开源码的默认位置（$HOME 相对，不写死别人的 home），再找演示包旁的副本。
find_repo() {
    local candidate
    for candidate in "${FAMILY_LEARNING_REPO:-}" \
                     "$HOME/.local/share/family-learning/public-integration-20260926" \
                     "$here/repo" "$here/../public-integration-20260926"; do
        if [ -n "$candidate" ] && [ -f "$candidate/demo.py" ] && [ -d "$candidate/packaging/macos" ]; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

port_free() {
    "$PY" - "$PORT" <<'PYCODE' >/dev/null 2>&1
import socket, sys
sock = socket.socket()
try:
    sock.bind(('127.0.0.1', int(sys.argv[1])))
finally:
    sock.close()
PYCODE
}

stop_demo() {
    [ -f "$PIDFILE" ] || return 0
    local pid command attempt
    pid=$(cat "$PIDFILE" 2>/dev/null || true)
    case "$pid" in
        ''|*[!0-9]*) rm -f "$PIDFILE"; return 0 ;;
    esac
    if kill -0 "$pid" 2>/dev/null; then
        command=$(ps -o command= -p "$pid" 2>/dev/null || true)
        case "$command" in
            *demo.py*)
                kill "$pid" 2>/dev/null || true
                attempt=0
                while [ "$attempt" -lt 25 ] && kill -0 "$pid" 2>/dev/null; do
                    attempt=$((attempt + 1)); sleep 0.2
                done
                kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
                ;;
            *)
                say_err "提示：.runtime/demo.pid 指向的进程不是本演示的 demo.py，未动它。"
                ;;
        esac
    fi
    rm -f "$PIDFILE"
}

wait_ready() {
    local attempt=0
    while [ "$attempt" -lt 120 ]; do
        if curl -fsS -m 1 "$ORIGIN/api/state" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 0.25
    done
    return 1
}

prepare_support() {
    mkdir -p "$SUPPORT" || return 1
    chmod 700 "$SUPPORT" 2>/dev/null || true
    umask 077
    printf '{"service_origin":"%s"}\n' "$ORIGIN" >"$SUPPORT/desktop.json" || return 1
    chmod 600 "$SUPPORT/desktop.json" 2>/dev/null || true
}

start_demo() {
    mkdir -p "$RUNTIME" "$EVIDENCE" || return 1
    : >"$DEMO_LOG"
    (
        cd "$REPO" || exit 1
        nohup "$PY" -B demo.py --port "$PORT" >>"$DEMO_LOG" 2>&1 &
        echo $! >"$PIDFILE"
    ) || return 1
    [ -s "$PIDFILE" ] || return 1
    wait_ready
}

# ---------------------------------------------------------------------------
if [ "$mode" = help ]; then
    usage
    exit 0
fi

if [ "$mode" = stop ]; then
    stop_demo
    say "演示后台已停止；它的全虚构数据（临时目录）也随之清除。"
    say "如需一并清理演示包留下的独立配置：rm -rf \"$SUPPORT\" \"$RUNTIME\""
    exit 0
fi

command -v "$PY" >/dev/null 2>&1 || die "找不到 Python 3（${PY}）。REPO/demo.py 需要 python3 才能启动演示后台。"
[ -f "$SEED" ] || die "缺少播种脚本：$SEED"
[ -d "$APP" ] || die "缺少 App：${APP}（应先用 重建.sh 或 REPO/packaging/macos/build.sh 构建，当前版本 313）"
REPO=$(find_repo) || die "找不到公开源码 REPO。可用 FAMILY_LEARNING_REPO=/path/to/public-integration-20260926 指定。"

# 先收掉上一次双击留下的演示后台（只认我们自己记下的 pid + demo.py 命令行）。
stop_demo
if ! port_free; then
    die "端口 $PORT 已被其他程序占用。请先停止占用它的程序（或设置 FAMILY_DEMO_PORT 换一个端口）后再双击。"
fi

say "REPO  : $REPO"
say "后台  : ${ORIGIN}（全虚构，临时目录，退出即清除）"
say "配置  : $SUPPORT/desktop.json（本次演示专用，不覆盖真实 App 配置）"
say ""

prepare_support || die "无法准备本次演示的独立配置目录：$SUPPORT"
cleanup_after=1
say "正在启动虚构演示后台…"
start_demo || { say_err "---- demo.log 末尾 ----"; tail -n 20 "$DEMO_LOG" >&2 2>/dev/null || true; die "虚构后台没有在 $ORIGIN 就绪"; }

{
    echo "=== demo.py 启动 $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo "REPO=$REPO"
    echo "PORT=$PORT PID=$(cat "$PIDFILE" 2>/dev/null || true)"
    echo "--- 启动输出（demo.py stdout）---"
    cat "$DEMO_LOG"
} >"$EVIDENCE/demo.py-启动输出.txt" 2>&1
say "后台已就绪：$(grep -F '虚构演示' "$DEMO_LOG" | head -n 1 || echo "$ORIGIN")"
say ""

SEED_ARGS=(--base-url "$ORIGIN" --snapshot "$EVIDENCE/api-day.json")
if [ -n "$REAL_RUN" ]; then
    [ -f "$REAL_RUN" ] || die "FAMILY_SEED_FROM_REAL_RUN 指向的文件不存在：$REAL_RUN"
    SEED_ARGS+=(--from-real-run "$REAL_RUN")
    say "正在通过公开 API 播种「真模型抽取产物」：$REAL_RUN"
else
    say "正在通过公开 API 播种全虚构的「完整一天」（内置 7 条故事）…"
fi
if [ -n "${FAMILY_DEMO_CHILD:-}" ]; then
    SEED_ARGS+=(--child "$FAMILY_DEMO_CHILD")
fi
if ! "$PY" -B "$SEED" "${SEED_ARGS[@]}" 2>&1 | tee "$EVIDENCE/播种输出.txt"; then
    die "播种或 /api/day 断言失败，已停止演示后台"
fi

if [ "$mode" = check ]; then
    say ""
    say "自检模式：未打开 App。正在停止演示后台，演示数据随之清除。"
    exit 0
fi

if [ "$mode" = serve ]; then
    # 供 重建.sh 截图/取证：后台保留，不打开 App；由调用方用 --stop 收尾。
    cleanup_after=0
    say ""
    say "取证模式：未打开 App，虚构后台继续运行在 ${ORIGIN}。"
    say "  停止后台：./一起成长·虚构一日演示.command --stop"
    exit 0
fi

say ""
say "正在打开「一起成长.app」（使用本次演示的独立配置目录）…"
open -n --env "FAMILY_DESKTOP_SUPPORT_DIR=$SUPPORT" "$APP" || die "App 启动失败"
# App 已带着本次演示配置启动：后台继续运行，退出时不再自动停止。
cleanup_after=0
say ""
say "演示已就绪：App 会连到 $ORIGIN 的全虚构后台。"
if [ -n "$REAL_RUN" ]; then
    say "  清单：真模型抽取的 6 项（今天 1 项、以后安排 5 项）。"
else
    say "  看今天 5 项与明天 2 项：App 左侧清单（「以后安排」里是明天的事）。"
fi
say "  换数据源：默认=内置 7 条故事；设 FAMILY_SEED_FROM_REAL_RUN=1 改用真模型抽取的 6 条。"
say "  关闭窗口：正常按 ⌘W / ⌘Q 关闭，不要强退。"
say "  停止后台：./一起成长·虚构一日演示.command --stop"
say "  证据快照：$EVIDENCE/api-day.json"
exit 0

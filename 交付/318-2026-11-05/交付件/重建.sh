#!/bin/bash
# 一键盘点重建（构建号默认 318）：源码快照 → 构建 App → 签名/plist 校验 → 二进制字符串证据
# → 起全虚构后台 + 播种 + /api/day 快照 → 可选网页截图。全程不弹原生窗口、不写真实家庭目录。
#
# 用法：
#   ./重建.sh                    # 用默认 REPO 与构建号 313
#   FAMILY_LEARNING_REPO=/path ./重建.sh
#   FAMILY_RECORDED_HEAD=<sha1> ./重建.sh   # 记录 lead 给定的冻结 sha1，并核对 HEAD 是否一致
#   FAMILY_REBUILD_NUMBER=310 FAMILY_REBUILD_APP_NAME=一起成长-预演.app ./重建.sh   # 预演，不覆盖正式 App
#   SKIP_UI_SHOTS=1 ./重建.sh    # 跳过网页截图
#
# 产物：
#   <交付目录>/一起成长.app                     构建号 313、ad-hoc 签名
#   <交付目录>/证据/fix.patch-313               当前工作区相对 HEAD 的完整补丁（含被忽略的新文件）
#   <交付目录>/证据/git-status-313.txt          git status --porcelain 原样存档
#   <交付目录>/证据/源码版本-313.txt            HEAD sha1、各改动文件 sha1、构建号
#   <交付目录>/证据/App构建与签名校验-313.txt   构建日志、codesign、plutil、otool
#   <交付目录>/证据/二进制修复字符串-313.txt     「家庭安排」等修复字符串在二进制/源码里的证据
#   <交付目录>/证据/自检输出-313.txt            --check 完整终端输出（默认 7 条故事，非 8766 端口）
#   <交付目录>/证据/api-day-修复后-313.json     默认故事播种后的 /api/day（含 plan_lines、lines 去重）
#   <交付目录>/证据/真模型播种输出-313.txt      --from-real-run 播种自检输出（模型 6 条 → 6 件）
#   <交付目录>/证据/api-day-真模型-313.json     真模型抽取数据播种后的 /api/day
#   <交付目录>/证据/screens-313/                网页 360/1440 截图与 DOM 断言（surface 的 assert_plan_lines_ui.cjs）
#   <交付目录>/证据/演示数据核对-313.txt        默认故事逐卡文本核对
set -u
set -o pipefail

here=$(cd "$(dirname "$0")" && pwd)
REPO=${FAMILY_LEARNING_REPO:-"$HOME/.local/share/family-learning/public-integration-20260926"}
# 构建源与证据源可分离：318 起按「主仓库 rsync → 副本排 .git → 副本构建」流程，
# 构建源是副本（REPO），git 证据来自主仓库（GIT）。
GIT=${FAMILY_GIT_REPO:-"$REPO"}
NUMBER=${FAMILY_REBUILD_NUMBER:-318}
APP_NAME=${FAMILY_REBUILD_APP_NAME:-一起成长.app}
APP="$here/$APP_NAME"
EVID="$here/证据"
LOG="$EVID/重建日志-${NUMBER}.txt"
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

mkdir -p "$EVID"
: > "$LOG"
say() { printf '%s\n' "$*" | tee -a "$LOG"; }
step() { say ""; say "=== $* ==="; }
die() { say "重建失败：$*"; exit 1; }
count() { if [ -n "$1" ]; then printf '%s\n' "$1" | wc -l | tr -d ' '; else echo 0; fi; }

say "重建开始 $STAMP"
say "交付目录: $here"
say "REPO     : $REPO"
say "GIT      : $GIT"
say "构建号   : $NUMBER"
say "目标 App : $APP"

[ -d "$REPO" ] || die "找不到 REPO：${REPO}（可用 FAMILY_LEARNING_REPO=... 指定）"
[ -f "$REPO/packaging/macos/build.sh" ] || die "REPO 里没有 packaging/macos/build.sh"
[ -f "$REPO/demo.py" ] || die "REPO 里没有 demo.py"
command -v python3 >/dev/null 2>&1 || die "找不到 python3"

# ---------------------------------------------------------------- 1. 源码快照
step "1/8 记录源码版本与补丁"
HEAD=$(git -C "$GIT" rev-parse HEAD) || die "读不到 REPO 的 git HEAD"
HEAD_SHORT=$(git -C "$GIT" rev-parse --short HEAD)
git -C "$GIT" status --porcelain > "$EVID/git-status-${NUMBER}.txt" || die "git status 失败"
git -C "$GIT" diff > "$EVID/fix.patch-${NUMBER}" || die "git diff 失败"
# 未跟踪的新文件也要进补丁（评审可能新增测试文件）；用只读的 git diff --no-index 追加。
# 新测试文件可能被 .gitignore 的根通配规则忽略（test_daily_list_expression.py、test_school_fold_visibility.py 均如此），
# 这类文件不会出现在 git status / ls-files --others 里，显式补入（存在才加，可用
# FAMILY_REBUILD_EXTRA_NEW_FILES="a.py b.py" 覆盖）。
untracked=$(git -C "$GIT" ls-files --others --exclude-standard)
EXTRA_NEW=${FAMILY_REBUILD_EXTRA_NEW_FILES:-test_daily_list_expression.py test_school_fold_visibility.py}
extra_new=""
for rel in $EXTRA_NEW; do
    [ -f "$REPO/$rel" ] || continue
    if ! printf '%s\n' "$untracked" | grep -qx "$rel"; then
        if [ -z "$extra_new" ]; then
            extra_new="$rel"
        else
            extra_new="$extra_new $rel"
        fi
    fi
done
# 注意：extra_new 是空格分隔的多文件名，不能整体塞进一行再 read（否则多个新文件
# 会被拼成一个不存在的路径，git diff --no-index 静默失败、补丁漏文件）。
append_new_file() {
    local rel
    rel=$(printf '%s' "$1" | sed 's/^[[:space:]]*//')
    [ -n "$rel" ] || return 0
    git -C "$GIT" diff --no-index -- /dev/null "$rel" >> "$EVID/fix.patch-${NUMBER}" 2>/dev/null || true
}
if [ -n "$untracked" ]; then
    while IFS= read -r rel; do
        append_new_file "$rel"
    done <<< "$untracked"
fi
for rel in $extra_new; do
    append_new_file "$rel"
done
git -C "$GIT" diff --stat > "$EVID/diff-stat-${NUMBER}.txt" || true
if [ -n "$extra_new" ]; then
    {
        echo "# 被 .gitignore 忽略的新文件（不在 git status --porcelain 中，仍补入 fix.patch）"
        for rel in $extra_new; do
            printf ' %s | %s ++\n' "$rel" "$(wc -l < "$REPO/$rel" | tr -d ' ')"
        done
    } >> "$EVID/diff-stat-${NUMBER}.txt"
    {
        echo ""
        echo "# 被 .gitignore 忽略的新文件（不在上面 porcelain 输出里，仍已写入 fix.patch）"
        for rel in $extra_new; do
            printf '  %s  %s\n' "$(shasum -a 1 "$REPO/$rel" | cut -d' ' -f1)" "$rel"
        done
    } >> "$EVID/git-status-${NUMBER}.txt"
fi

changed=$(git -C "$GIT" status --porcelain | sed 's/^...//' | sed 's/^.* -> //')
{
    echo "记录时间: $STAMP"
    echo "REPO: $REPO"
    echo "HEAD: $HEAD"
    if [ -n "${FAMILY_RECORDED_HEAD:-}" ]; then
        echo "lead 冻结 sha1: $FAMILY_RECORDED_HEAD"
        echo "HEAD 与冻结 sha1: $([ "${FAMILY_RECORDED_HEAD}" = "$HEAD" ] && echo 一致 || echo 不一致（HEAD 已前移，请确认）)"
    fi
    echo "构建号: $NUMBER"
    echo "工作区改动文件（git status --porcelain）:"
    git -C "$GIT" status --porcelain | sed 's/^/  /'
    echo "改动文件 sha1:"
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        if [ -f "$REPO/$rel" ]; then
            printf '  %s  %s\n' "$(shasum -a 1 "$REPO/$rel" | cut -d' ' -f1)" "$rel"
        fi
    done <<< "$changed"
    if [ -n "$extra_new" ]; then
        echo "被 .gitignore 忽略的新文件 sha1:"
        for rel in $extra_new; do
            printf '  %s  %s\n' "$(shasum -a 1 "$REPO/$rel" | cut -d' ' -f1)" "$rel"
        done
    fi
    echo "fix.patch sha1: $(shasum -a 1 "$EVID/fix.patch-${NUMBER}" | cut -d' ' -f1)"
    echo "fix.patch 字节数: $(wc -c < "$EVID/fix.patch-${NUMBER}" | tr -d ' ')"
} > "$EVID/源码版本-${NUMBER}.txt"
say "HEAD=$HEAD"
say "改动文件数: $(count "$changed")"
say "补丁: $EVID/fix.patch-${NUMBER}（$(wc -c < "$EVID/fix.patch-${NUMBER}" | tr -d ' ') 字节）"

# ---------------------------------------------------------------- 2. 构建 App
step "2/8 构建 App（构建号 ${NUMBER}）"
rm -rf "$here/build"
cd "$REPO/packaging/macos" || die "进不去 $REPO/packaging/macos"
FAMILY_MAC_BUILD_NUMBER=$NUMBER ./build.sh "$here/build" > "$EVID/build-${NUMBER}.log" 2>&1
rc=$?
if [ $rc -ne 0 ]; then
    tail -20 "$EVID/build-${NUMBER}.log" | tee -a "$LOG"
    die "build.sh 退出码 ${rc}（日志 $EVID/build-${NUMBER}.log）"
fi
[ -d "$here/build/一起成长.app" ] || die "build.sh 没有产出 一起成长.app"
# 旧 App 只在新的构建成功后才替换；旧版 sha1 记录到日志，方便回溯。
if [ -d "$APP" ]; then
    say "替换旧 App（旧二进制 sha1: $(shasum -a 1 "$APP/Contents/MacOS/YiqiChengzhang" | cut -d' ' -f1)）"
    rm -rf "$APP"
fi
mv "$here/build/一起成长.app" "$APP"
rmdir "$here/build" 2>/dev/null || true
say "产物: $APP"
say "二进制 sha1: $(shasum -a 1 "$APP/Contents/MacOS/YiqiChengzhang" | cut -d' ' -f1)"

# ---------------------------------------------------------------- 3. 签名/plist 校验
step "3/8 签名与 Info.plist 校验"
VERIFY="$EVID/App构建与签名校验-${NUMBER}.txt"
{
    echo "记录时间: $STAMP"
    echo "构建号: $NUMBER"
    echo "HEAD: $HEAD"
    echo
    echo "### codesign --verify --deep --strict --verbose=2"
    codesign --verify --deep --strict --verbose=2 "$APP" 2>&1
    echo "verify 退出码: $?"
    echo
    echo "### codesign -dv"
    codesign -dv "$APP" 2>&1
    echo
    echo "### plutil -p Contents/Info.plist"
    plutil -p "$APP/Contents/Info.plist"
    echo
    echo "### 断言 CFBundleVersion=$NUMBER"
    actual=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP/Contents/Info.plist" 2>/dev/null || echo '')
    if [ "$actual" = "$NUMBER" ]; then echo "通过：CFBundleVersion=$actual"; else echo "失败：CFBundleVersion=$actual"; fi
    echo
    echo "### file / lipo"
    file "$APP/Contents/MacOS/YiqiChengzhang"
    lipo -info "$APP/Contents/MacOS/YiqiChengzhang" 2>&1
    echo
    echo "### otool -L（应只依赖 /System 与 /usr/lib）"
    otool -L "$APP/Contents/MacOS/YiqiChengzhang"
} > "$VERIFY" 2>&1
codesign --verify --deep --strict --verbose=2 "$APP" >/dev/null 2>&1 || die "codesign 校验失败（见 ${VERIFY}）"
actual=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP/Contents/Info.plist" 2>/dev/null || echo '')
[ "$actual" = "$NUMBER" ] || die "CFBundleVersion 应为 ${NUMBER}，实际 $actual"
say "codesign --verify --deep --strict 通过；CFBundleVersion=$actual"

# ---------------------------------------------------------------- 4. 二进制修复字符串
step "4/8 二进制里的修复字符串"
BIN="$APP/Contents/MacOS/YiqiChengzhang"
STRINGS="$EVID/二进制修复字符串-${NUMBER}.txt"
{
    echo "记录时间: $STAMP"
    echo "二进制: $BIN"
    echo "二进制 sha1: $(shasum -a 1 "$BIN" | cut -d' ' -f1)"
    echo
    echo "### 先说明：BSD strings 只输出可打印 ASCII，会把 UTF-8 中文丢掉，所以它统计中文必然为 0；"
    echo "### 中文按 UTF-8 字节在二进制里直接统计（Python，与 strings 等价但保留非 ASCII）。"
    echo
    echo "### strings -a | grep -c 家庭安排（BSD strings 不保留中文，预期 0）"
    strings -a "$BIN" | grep -c '家庭安排' || true
    echo
    echo "### Python UTF-8 字节计数（真实证据）"
    python3 - "$BIN" <<'PY'
import sys
data = open(sys.argv[1], 'rb').read()
for word in ['家庭安排', '家庭安排：', 'row-plan-', 'plan_lines', '连接本机一起成长服务',
             'FAMILY_DESKTOP_SUPPORT_DIR', '一起成长']:
    print('%-28s %d' % (word, data.count(word.encode('utf-8'))))
PY
    echo
    echo "### 源码里的行号"
    grep -n '家庭安排' "$REPO/packaging/macos/Sources/Workspace.swift" | head -8
    echo
    echo "### WorkspaceAPI 里的 plan_lines 解码角色"
    grep -n 'plan_lines\|planLines' "$REPO/packaging/macos/Sources/WorkspaceAPI.swift" "$REPO/packaging/macos/Sources/Workspace.swift" | head -8

    echo
    echo "### 原生渲染：DayFollowUp 类型符号"
    echo "### surface 用 DayFollowUp 类型 + follow_ups 解码；Swift -O 会池化中文字符串，不能靠中文 grep，故查类型名符号。"
    echo "nm -a | grep -c DayFollowUp:"
    nm -a "$BIN" 2>/dev/null | grep -c 'DayFollowUp' || true
    echo "nm -a | grep DayFollowUp（前 10 行）:"
    nm -a "$BIN" 2>/dev/null | grep 'DayFollowUp' | head -10
    echo "strings -a | grep -c DayFollowUp（类型名为 ASCII，可作兜底）:"
    strings -a "$BIN" | grep -c 'DayFollowUp' || true
    echo
    echo "### WorkspaceAPI.swift 里 DayFollowUp / follow_ups 的行号"
    grep -n 'DayFollowUp\|follow_ups' "$REPO/packaging/macos/Sources/WorkspaceAPI.swift" | head -8
} > "$STRINGS" 2>&1
count_plan=$(python3 - "$BIN" <<'PY'
import sys
print(open(sys.argv[1], 'rb').read().count('家庭安排'.encode('utf-8')))
PY
)
say "二进制含「家庭安排」$count_plan 处（UTF-8 字节计数）"
[ "${count_plan:-0}" -gt 0 ] || die "二进制里没有「家庭安排」，可能是构建源码不对（见 ${STRINGS}）"
day_follow_up=$(nm -a "$BIN" 2>/dev/null | grep -c 'DayFollowUp' || true)
say "二进制含 DayFollowUp 符号 ${day_follow_up} 处"
[ "${day_follow_up:-0}" -gt 0 ] || say "警告：未检出 DayFollowUp 符号，请核对 WorkspaceAPI.swift 是否已更新"

# ---------------------------------------------------------------- 5. 自检 + /api/day 快照
step "5/8 启动全虚构后台 + 播种 + /api/day 断言（不用 8766）"
PORT=${FAMILY_REBUILD_PORT:-}
if [ -z "$PORT" ]; then
    PORT=$(python3 - <<'PY'
import socket
for port in range(8771, 8790):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        print(port)
        break
    except OSError:
        continue
    finally:
        s.close()
else:
    print('')
PY
)
fi
[ -n "$PORT" ] || die "8771-8789 没有空闲端口，请用 FAMILY_REBUILD_PORT=... 指定"
say "自检端口: $PORT"
FAMILY_DEMO_PORT=$PORT bash "$here/一起成长·虚构一日演示.command" --check > "$EVID/自检输出-${NUMBER}.txt" 2>&1
check_rc=$?
tail -8 "$EVID/自检输出-${NUMBER}.txt" | sed 's/^/  /' | tee -a "$LOG" >/dev/null
if [ $check_rc -ne 0 ]; then
    say "自检输出（末尾）:"
    tail -25 "$EVID/自检输出-${NUMBER}.txt" | tee -a "$LOG"
    die "--check 退出码 ${check_rc}（完整输出 $EVID/自检输出-${NUMBER}.txt）"
fi
[ -f "$EVID/api-day.json" ] || die "--check 没有写出 证据/api-day.json"
cp "$EVID/api-day.json" "$EVID/api-day-修复后-${NUMBER}.json"
cp "$EVID/api-day.json" "$EVID/api-day-修复后.json"
say "自检通过（退出码 0）；快照已存 证据/api-day-修复后-${NUMBER}.json"

# 逐卡文本核对：seed 的 7 条事项 → /api/day 实际显示（供报告直接引用）
python3 - "$EVID/api-day-修复后-${NUMBER}.json" > "$EVID/演示数据核对-${NUMBER}.txt" <<'PYGEN'
import json, sys

d = json.load(open(sys.argv[1], encoding='utf-8'))
seed = d.get('_seed') or {}
counts = d.get('counts') or {}
print('演示数据核对：/api/day 实际显示内容')
print('孩子: %s（%s）  演示日期: %s  计数: %s' % (d.get('child_name'), d.get('child_id'), d.get('today'),
      ', '.join('%s=%s' % (k, counts[k]) for k in sorted(counts))))
print('投影模式: %s  堆叠要求样式: %s  已标记完成: %s' % (
      seed.get('projection'), seed.get('daily_style'), '、'.join(seed.get('marked_done') or [])))
print()

def walk():
    for group in d.get('groups') or []:
        for item in group.get('items') or []:
            yield group, item

def show(group, item):
    print('[%s] %s' % (group.get('subject') or '?', item.get('title')))
    print('   when=%s  subject=%s' % (item.get('when'), item.get('subject')))
    for fact in item.get('facts') or []:
        print('   fact: %s=%s (kind=%s, state=%s, known=%s)' % (
              fact.get('label'), fact.get('value'), fact.get('kind'), fact.get('state'), fact.get('known')))
    lines = item.get('lines') or []
    print('   lines(%d):' % len(lines))
    for line in lines:
        print('     - %s' % line)
    plan = item.get('plan_lines') or []
    if plan:
        print('   plan_lines(%d):' % len(plan))
        for line in plan:
            print('     * %s' % line)
    print()

by_when = {}
for group, item in walk():
    by_when.setdefault(item.get('when') or '?', []).append((group, item))

print('=== 今天（when=today） ===')
for group, item in by_when.get('today', []):
    show(group, item)
print('=== 以后安排（when=later） ===')
for group, item in by_when.get('later', []):
    show(group, item)
print('=== 其他未写日期（when=unknown/其他） ===')
for when in sorted(by_when):
    if when in ('today', 'later'):
        continue
    for group, item in by_when[when]:
        show(group, item)

seen = {item.get('title') for _, item in walk()}
expected = [t.get('title') for t in (seed.get('seeded') or [])]
missing = [t for t in expected if t not in seen]
print('=== 播种的 %d 条事项是否都在 /api/day 里 ===' % len(expected))
for title in expected:
    print('  %s %s' % ('OK  ' if title in seen else '缺失', title))
print('结论: %s' % ('全部可见' if not missing else '缺少: ' + '、'.join(missing)))
if missing:
    sys.exit(1)
PYGEN
cp "$EVID/演示数据核对-${NUMBER}.txt" "$EVID/演示数据核对.txt"
say "逐卡核对已存 证据/演示数据核对-${NUMBER}.txt"

# 5b. 真模型抽取播种自检（交付包带 演示数据/real-model-run.json 时才跑；只在额外证据里记，
#     不改默认故事。这一步证明「真模型 6 条消息 → 6 件事」的体验版数据通路可用。）
REALRUN="$here/演示数据/real-model-run.json"
REAL_EVID="$EVID/真模型播种输出-${NUMBER}.txt"
REAL_SNAP="$EVID/api-day-真模型-${NUMBER}.json"
REAL_RC=skip
if [ -f "$REALRUN" ]; then
    REAL_PORT=$(python3 - <<'PYPORT'
import socket
for port in range(8841, 8861):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        print(port)
        break
    except OSError:
        continue
    finally:
        s.close()
PYPORT
)
    [ -n "$REAL_PORT" ] || REAL_PORT=$PORT
    cp "$EVID/api-day.json" "$EVID/.default-api-day.$$" 2>/dev/null || true
    cp "$EVID/播种输出.txt" "$EVID/.default-seed-out.$$" 2>/dev/null || true
    FAMILY_DEMO_PORT=$REAL_PORT FAMILY_SEED_FROM_REAL_RUN="$REALRUN" \
        bash "$here/一起成长·虚构一日演示.command" --check > "$REAL_EVID" 2>&1
    REAL_RC=$?
    if [ -f "$EVID/api-day.json" ]; then cp "$EVID/api-day.json" "$REAL_SNAP"; fi
    [ -f "$EVID/.default-api-day.$$" ] && cp "$EVID/.default-api-day.$$" "$EVID/api-day.json"
    [ -f "$EVID/.default-seed-out.$$" ] && cp "$EVID/.default-seed-out.$$" "$EVID/播种输出.txt"
    rm -f "$EVID/.default-api-day.$$" "$EVID/.default-seed-out.$$"
    if [ $REAL_RC -eq 0 ]; then
        REAL_ITEMS=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1],encoding='utf-8'));print(len((d.get('_seed') or {}).get('seeded') or []))" "$REAL_SNAP" 2>/dev/null || echo '?')
        say "真模型播种自检通过（退出码 0，模型事项 ${REAL_ITEMS} 条；证据 证据/真模型播种输出-${NUMBER}.txt）"
    else
        say "真模型播种自检退出码 ${REAL_RC}（如实记录；见 证据/真模型播种输出-${NUMBER}.txt）"
    fi
else
    say "未找到 演示数据/real-model-run.json，跳过真模型播种自检"
fi

# 5c. 十八渠道演示自检（交付包带 一起成长·十八渠道演示.command 与快照时才跑）
#     证明「18 条多渠道虚构消息 → 8 张卡、今天 5 件、18/18 落点」在交付包里可双击复现。
CHANNEL_CMD="$here/一起成长·十八渠道演示.command"
CHANNEL_SNAP="$here/演示数据/十八渠道快照"
CHANNEL_EVID="$EVID/十八渠道自检-输出-${NUMBER}.txt"
CHANNEL_RC=skip
if [ -x "$CHANNEL_CMD" ] && [ -d "$CHANNEL_SNAP" ]; then
    CHANNEL_TMP=$(mktemp /tmp/channel-check.XXXXXX)
    bash "$CHANNEL_CMD" --check > "$CHANNEL_TMP" 2>&1
    CHANNEL_RC=$?
    {
        echo "记录时间: $STAMP"
        echo "命令: bash 一起成长·十八渠道演示.command --check"
        echo "退出码: $CHANNEL_RC"
        echo
        echo "### 命令行输出"
        cat "$CHANNEL_TMP" 2>/dev/null || true
        echo
        echo "### 证据/十八渠道自检-输出.txt（脚本自带证据）"
        cat "$EVID/十八渠道自检-输出.txt" 2>/dev/null || true
    } > "$CHANNEL_EVID"
    rm -f "$CHANNEL_TMP"
    if [ $CHANNEL_RC -eq 0 ]; then
        say "十八渠道自检通过（退出码 0；证据 证据/十八渠道自检-输出-${NUMBER}.txt）"
    else
        say "十八渠道自检退出码 ${CHANNEL_RC}（如实记录；见 证据/十八渠道自检-输出-${NUMBER}.txt）"
    fi
else
    say "未找到十八渠道演示命令或快照，跳过十八渠道自检"
fi

# ---------------------------------------------------------------- 6. 网页截图与家庭安排块 DOM 断言
step "6/8 网页新 UI 六宽度截图 + 量数 + 断言（360/390/768/1024/1200/1440；失败不阻断但如实记入）"
WIDTH_EVID="$EVID/网页六宽度-${NUMBER}.txt"
if [ "${SKIP_UI_SHOTS:-0}" = "1" ]; then
    say "SKIP_UI_SHOTS=1，跳过六宽度证据。"
else
    WEB_RC=0
    FAMILY_REBUILD_NUMBER="$NUMBER" FAMILY_TODAY=2026-11-04 bash "$here/工具/ui六宽度.sh" > "$WIDTH_EVID" 2>&1 || WEB_RC=$?
    if [ "$WEB_RC" -eq 0 ]; then
        say "六宽度断言通过（failures: []，nonGet: []）；证据 证据/网页六宽度-${NUMBER}.txt、截图 证据/screens-${NUMBER}/六宽度/"
    else
        say "六宽度断言退出码 ${WEB_RC}（如实记录；见 证据/网页六宽度-${NUMBER}.txt）"
    fi
fi

step "6b/8 十八渠道 360/1440 UI 断言与截图（失败不阻断，如实记入证据）"
UI_SCRIPT="${SURFACE_UI_SCRIPT:-/Users/joyrush/Documents/deepseek-harness/default-workspace/work/surface-evidence/assert_plan_lines_ui.cjs}"
CH_UI_EVID="$EVID/十八渠道UI断言-${NUMBER}.txt"
G4_SCRIPT="$here/工具/g4_children.cjs"
CH_SHOTS="$EVID/screens-${NUMBER}/十八渠道"
if [ "${SKIP_UI_SHOTS:-0}" = "1" ]; then
    say "SKIP_UI_SHOTS=1，跳过十八渠道 UI 断言"
elif [ ! -x "$CHANNEL_CMD" ] || [ ! -d "$CHANNEL_SNAP" ]; then
    say "没有十八渠道命令/快照，跳过"
elif [ ! -f "$UI_SCRIPT" ] || [ ! -f "$G4_SCRIPT" ] || ! command -v node >/dev/null 2>&1; then
    say "缺少 surface 断言脚本 / 工具/g4_children.cjs / node，跳过"
else
    CH_PORT=$(python3 - <<'PYPORT'
import socket
for port in range(8833, 8853):
    s = socket.socket()
    try:
        s.bind(('127.0.0.1', port))
        print(port)
        break
    except OSError:
        continue
    finally:
        s.close()
PYPORT
)
    [ -n "$CH_PORT" ] || CH_PORT=8844
    mkdir -p "$CH_SHOTS/surface-assert"
    say "起十八渠道后台（--serve，不打开 App，端口 ${CH_PORT}）…"
    if FAMILY_CHANNEL_DEMO_PORT=$CH_PORT bash "$CHANNEL_CMD" --serve > "$EVID/十八渠道截图后台-${NUMBER}.txt" 2>&1; then
        CH_ASSERT_TMP=$(mktemp /tmp/ch-assert.XXXXXX)
        CH_G4_TMP=$(mktemp /tmp/ch-g4.XXXXXX)
        ( cd "$(dirname "$UI_SCRIPT")" && \
            PLAYWRIGHT_MODULE="${PLAYWRIGHT_MODULE:-/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright}" \
            PLAYWRIGHT_CHANNEL="${PLAYWRIGHT_CHANNEL:-chrome}" \
            SURFACE_BASE="http://127.0.0.1:$CH_PORT" SURFACE_OUT="$CH_SHOTS/surface-assert" \
            node "$(basename "$UI_SCRIPT")" > "$CH_ASSERT_TMP" 2>&1 )
        ch_assert_rc=$?
        ( PLAYWRIGHT_MODULE="${PLAYWRIGHT_MODULE:-/Users/joyrush/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright}" \
            PLAYWRIGHT_CHANNEL="${PLAYWRIGHT_CHANNEL:-chrome}" \
            SURFACE_BASE="http://127.0.0.1:$CH_PORT" SURFACE_OUT="$CH_SHOTS" SURFACE_DAY=2026-11-04 \
            node "$G4_SCRIPT" > "$CH_G4_TMP" 2>&1 )
        ch_g4_rc=$?
        bash "$CHANNEL_CMD" --stop >> "$EVID/十八渠道截图后台-${NUMBER}.txt" 2>&1 || true
        {
            echo "记录时间: $STAMP"
            echo "十八渠道后台: http://127.0.0.1:${CH_PORT}（--serve，不打开 App）"
            echo
            echo "### 一、surface assert_plan_lines_ui.cjs（退出码 ${ch_assert_rc}）"
            echo "说明：本快照没有 plan_lines 事项，该脚本的「必须存在 plan_lines」门槛预期不满足；其余 360/1440 断言应通过。"
            echo "命令: PLAYWRIGHT_CHANNEL=chrome SURFACE_BASE=http://127.0.0.1:${CH_PORT} SURFACE_OUT=${CH_SHOTS}/surface-assert node assert_plan_lines_ui.cjs"
            cat "$CH_ASSERT_TMP" 2>/dev/null || true
            echo
            if [ -f "$CH_SHOTS/surface-assert/assertions.json" ]; then
                echo "### assertions.json"; cat "$CH_SHOTS/surface-assert/assertions.json"
            fi
            echo
            echo "### 二、G4 量测工具（工具/g4_children.cjs，退出码 ${ch_g4_rc}）"
            echo "十八渠道快照冻结在 2026-11-04：脚本先点周条的 11月4日（data-grove-day=2026-11-04）再切孩子，量的是冻结场景。"
            echo "阈值：360 首卡 ≤200px；清单 ≤1.5 屏；无截断/横向溢出/写请求/pageerror。"
            echo "命令: SURFACE_BASE=http://127.0.0.1:${CH_PORT} SURFACE_OUT=${CH_SHOTS} SURFACE_DAY=2026-11-04 node 工具/g4_children.cjs"
            cat "$CH_G4_TMP" 2>/dev/null || true
            echo
            if [ -f "$CH_SHOTS/g4-report.json" ]; then
                echo "### g4-report.json"; cat "$CH_SHOTS/g4-report.json"
            fi
        } > "$CH_UI_EVID" 2>&1
        rm -f "$CH_ASSERT_TMP" "$CH_G4_TMP"
        say "十八渠道 UI 证据: ${CH_UI_EVID}（surface断言rc=${ch_assert_rc}，G4 rc=${ch_g4_rc}）"
    else
        say "十八渠道后台没起来，跳过（详见 证据/十八渠道截图后台-${NUMBER}.txt）"
    fi
fi

# ---------------------------------------------------------------- 7. 汇总
step "8/8 汇总"
{
    echo "重建完成: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "REPO HEAD: $HEAD ($HEAD_SHORT)"
    echo "构建号: $NUMBER"
    echo "App: $APP"
    echo "App 二进制 sha1: $(shasum -a 1 "$BIN" | cut -d' ' -f1)"
    echo "fix.patch: $(wc -c < "$EVID/fix.patch-${NUMBER}" | tr -d ' ') 字节（sha1 $(shasum -a 1 "$EVID/fix.patch-${NUMBER}" | cut -d' ' -f1)）"
    echo "二进制含「家庭安排」: $count_plan 处"
    echo "真模型播种自检: ${REAL_RC}（证据 真模型播种输出-${NUMBER}.txt）"
    echo "--check: 通过（端口 ${PORT}）"
    echo "api-day: $EVID/api-day-修复后-${NUMBER}.json（真模型: $EVID/api-day-真模型-${NUMBER}.json）"
    echo "网页六宽度证据: ${WIDTH_EVID:-未跑}（rc ${WEB_RC:-未跑}）"
    echo "十八渠道自检: ${CHANNEL_RC:-skip}（证据 十八渠道自检-输出-${NUMBER}.txt）"
    echo "十八渠道 UI 断言: ${CH_UI_EVID:-未跑}（surface rc=${ch_assert_rc:-未跑}，G4 rc=${ch_g4_rc:-未跑}）"
} | tee "$EVID/重建摘要-${NUMBER}.txt" | tee -a "$LOG"
say "重建成功。"

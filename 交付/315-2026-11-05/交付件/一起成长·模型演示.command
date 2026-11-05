#!/bin/bash
# 一起成长 · 模型演示（可双击）
# ---------------------------------------------------------------------------
# 与「一起成长·虚构一日演示.command」完全相同，唯一区别：播种数据换成真模型
# （doubao-seed-evolving）从 6 条虚构老师消息抽取的 6 件事（work/realrun/real-model-run.json）。
# 双击后同样会：起 127.0.0.1 的全虚构后台 → 按模型产物播种 → 用独立 support dir 打开 App。
#
# 停止后台：./一起成长·虚构一日演示.command --stop
# 只自检不打开 App：sh 一起成长·模型演示.command --check
# ---------------------------------------------------------------------------
set -u
here=$(cd "$(dirname "$0")" && pwd)
export FAMILY_SEED_FROM_REAL_RUN=1
exec "$here/一起成长·虚构一日演示.command" "$@"

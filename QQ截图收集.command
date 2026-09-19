#!/bin/zsh
set -eu
ROOT="$(cd "$(dirname "$0")" && pwd)"
echo '请框选 QQ 消息，包含群名标题；截图后由一起成长 Agent 整理。'
/usr/bin/open -a QQ
sleep 0.5
exec python3 "$ROOT/family_qq_inbox.py" --data "$ROOT/private"

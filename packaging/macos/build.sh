#!/bin/sh
# 一起成长.app 内部候选：系统 swiftc/AppKit/WebKit 构建原生入口；给出已核对的运行时材料时，同时打入 Python 运行环境、
# 离线依赖与当前已提交的程序，成为可在新 Mac 上由家长点击安装后台的完整包。本机 ad-hoc 签名（不是 Developer ID，未公证）。
# 用法：packaging/macos/build.sh [输出目录]；默认 packaging/macos/build（Git 忽略）。
#   FAMILY_MAC_MATERIALS  含 CPython 压缩包、runtime-notices/ 与 MATERIAL-MANIFEST.json 的目录
#   FAMILY_MAC_WHEELS     含 runtime.lock.json 所列 wheel 的目录；两者都给才打完整包，否则只构建连接入口
#   FAMILY_MAC_BUILD_NUMBER  安装包构建号（默认 1；更新只接受更大的构建号）
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/build"}
app="$out/一起成长.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$here/Info.plist" "$app/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion ${FAMILY_MAC_BUILD_NUMBER:-1}" "$app/Contents/Info.plist"
xcrun swiftc -O -swift-version 5 -target arm64-apple-macos13.0 -framework AppKit -framework WebKit \
  "$here/Sources/DesktopPolicy.swift" "$here/Sources/SelfTest.swift" "$here/Sources/main.swift" \
  -o "$app/Contents/MacOS/YiqiChengzhang"
if [ -n "${FAMILY_MAC_MATERIALS:-}" ] && [ -n "${FAMILY_MAC_WHEELS:-}" ]; then
  /usr/bin/python3 -I "$here/build_bundle.py" --resources "$app/Contents/Resources" --materials "$FAMILY_MAC_MATERIALS" \
    --wheels "$FAMILY_MAC_WHEELS" --repo "$here/../.." --build "${FAMILY_MAC_BUILD_NUMBER:-1}" \
    --version "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$here/Info.plist")" >&2
fi
codesign --force --sign - "$app" >/dev/null
echo "$app"

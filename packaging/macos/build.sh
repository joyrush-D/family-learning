#!/bin/sh
# 内部桌面候选：只用系统 swiftc/AppKit/WebKit 构建，本机 ad-hoc 签名（不是 Developer ID，未公证）。
# 用法：packaging/macos/build.sh [输出目录]；默认 packaging/macos/build（Git 忽略）。
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=${1:-"$here/build"}
app="$out/一起成长.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$here/Info.plist" "$app/Contents/Info.plist"
xcrun swiftc -O -swift-version 5 -target arm64-apple-macos13.0 -framework AppKit -framework WebKit \
  "$here/Sources/DesktopPolicy.swift" "$here/Sources/SelfTest.swift" "$here/Sources/main.swift" \
  -o "$app/Contents/MacOS/YiqiChengzhang"
codesign --force --sign - "$app" >/dev/null
echo "$app"

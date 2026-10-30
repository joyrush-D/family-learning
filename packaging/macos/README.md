# 一起成长桌面入口（内部候选）

AppKit + WKWebView 薄壳：只打开家长已配置的本机原服务，业务界面和数据仍由现有 `app.py` 与网页负责。这是 Mac App 目标的第一份内部里程碑，**不是**独立安装包：不内置 Python 或服务，不安装、启动、停止或改动任何 launchd 服务、配置或业务游标；未做 Developer ID 签名和公证。

- 构建：`packaging/macos/build.sh [输出目录]`，只用系统 `swiftc` 和 AppKit/WebKit，产物做本机 ad-hoc 签名。默认输出到 `packaging/macos/build/`（Git 忽略）。
- 配置：首次打开显示一个原生小表单，预填默认本机地址 `http://127.0.0.1:8765`，可改成本机其他端口；只有确认该地址上确是一起成长网页后才保存并直接打开原清单。地址不合规、不是本服务或服务不在时说明原因、不保存；已保存的地址失效时可在失败状态点“更改地址”或菜单“更改本机服务地址…”纠正。家长不需要编辑文件；地址保存在本用户 Application Support 下桌面入口自己的目录（仅本用户可读写：目录 0700、`desktop.json` 0600），外链白名单默认为空、只能手工加入，更正地址时原样保留。登录态保存在本用户的 WebKit 数据目录，包内没有家庭数据、密钥或配置。
- 行为：
  - 按解析后的 scheme/host/port 完全相等限定同源，阻止 file/data/其他端口/带账号密码/其他程序的导航；
  - 证书错误不忽略；麦克风只在原服务主页面实际请求时交系统询问，其他媒体拒绝；
  - 第二次打开只聚焦原窗口；关窗、退出和“更改本机服务地址…”都先按页面原有 beforeunload 确认，默认“继续编辑”，保留原画面、草稿和原地址；明确放弃后才显示地址表单，新地址确认后才重新载入；
  - 服务不在时有界重试，绝不改用其他端口或自行启动服务。
- 来源：生命周期设计参考了 margrop/wrong-notebook 03153ef7 的 `packaging/desktop/main.js`（MIT，wttwins 2025、margrop 2026），但没有复制任何代码，也不使用其 Electron/Node 服务管理。
- 测试模式：`--smoke-test` 只用于虚构 demo，必须另给 `FAMILY_DESKTOP_SUPPORT_DIR`（不能是默认目录）和受信虚构 `FAMILY_DESKTOP_TEST_ORIGIN`，否则以退出码 2 拒绝。测试时 WebKit 数据不落盘、不保存窗口位置，不读写本用户默认会话；选文件改回测试声明的虚构文件，麦克风一律拒绝（不触发系统权限询问），网页确认框选“取消”。每步网页操作由原生一侧限时并逐步输出结果，超时或异常如实回执。测试操作只由原生一侧在隔离脚本世界执行，网页仍没有任何原生桥接。
- 验收：`node test_mac_desktop.cjs`（虚构 demo，真实 WKWebView 窗口；可选 `FAMILY_DESKTOP_EVIDENCE_DIR` 保存行日志与截图，可选 Playwright Chrome 基线）。

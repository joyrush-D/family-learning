# 交付 313（2026-11-05）

这个目录放在 **`delivery/313-2026-11-05` 分支**上，`main` 只放源码（避免以后每次 clone 都拖 45MB 截图和二进制）。

## 交付件/

双击就能用的东西（全虚构数据，不连真实家庭环境）：

| 文件 | 用途 |
|---|---|
| `一起成长.app` | Build 313 原生 App（ad-hoc 签名，CFBundleVersion=313，binary sha1 `697e79203d3dcf308dad7be7309799dc583dbd84`） |
| `一起成长·虚构一日演示.command` | 默认 7 件事：起后台 + 打开 App |
| `一起成长·模型演示.command` | 真模型从 6 条老师消息整理出的 6 件事 |
| `一起成长·十八渠道演示.command` | 18 条消息（4 群 + 家长手写）→ 8 件事，冻结在 2026-11-04 |
| `重建.sh` | 一键重建（默认 313，幂等） |
| `交付说明.md` | 14 节完整说明：双击试用、后台与 App 的关系、边界与已知失败、证据索引、复现命令、卸载清理 |
| `演示数据/` | seed.py、真模型产物、十八渠道快照 |
| `证据/` | 构建签名校验、测试基线、`--check` 输出、修复前后 `/api/day`、360/1440 截图 |

## 过程证据/

| 目录 | 内容 |
|---|---|
| `reviewer-evidence/` | 独立审查：属性测试、r1–r4 审计（RED → BLOCK → GREEN） |
| `projection-evidence/` | 显示层投影：去重契约、`plan_lines` / `follow_ups` 前后样本 |
| `surface-evidence/` | 网页 + 原生渲染：宽度截图、DOM 断言、回归日志 |
| `merge18/` | 18 条多渠道消息真跑：报告、demo 快照、`verify-demo.sh` |
| `loopcheck/` | 反馈 → 错题 → 订正 → 知识点 → 复习 五步链证据 |
| `redesign/` | UI 重设计稿（HTML + 截图） |
| `realrun/` | 真模型首跑（6 条消息 → 6 件事）的原始 JSON |
| `LEAD-ACCEPTANCE.md` | 我（Lead）定的六道关 |
| `LEAD-FINAL-REPORT-313.md` | 313 的验收报告：六关状态、我自己复核的数字、已知边界 |

## 怎么在自己机器上跑

```bash
# 只需要 Python 3（产品是标准库 http.server，无第三方依赖）
sh 交付件/一起成长·虚构一日演示.command            # 起后台 + 打开 App
sh 交付件/一起成长·虚构一日演示.command --check    # 只自检，不开窗口
sh 交付件/一起成长·虚构一日演示.command --stop     # 停后台
```

App 本身不含 Python 运行时（“连接入口”客户端），后台由 `.command` 起；家庭正式环境要用带内置运行时的完整包（见 `打包/packaging/macos/README.md`）。

## 数据声明

本目录所有消息、孩子、老师、附件、截图均为**全虚构**（示例甲/示例乙、虚构四年级A班）。没有真实家庭数据、配置、日志、Cookie 或截图。

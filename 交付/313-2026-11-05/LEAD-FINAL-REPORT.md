# 一起成长 · 本轮交付记录（Lead 验收）

时间：2026-11-04 16:10（Asia/Shanghai）
交付目录：`work/deliverable/`（已冻结，不再改动）
说明文档：`work/deliverable/交付说明.md`

## 一、结论

本轮把「完整一天清单」的**重复表达**从服务端投影到网页/原生三处修掉，并产出一个**可直接双击试用**的独立 macOS 客户端交付件（构建号 308）。
独立审查（reviewer）终审结论 **GREEN（可交付）**；Lead 已独立复核哈希、测试、启动器自检、补丁可应用性。

## 二、冻结的源码快照（REPO `/Users/joyrush/.local/share/family-learning/public-integration-20260926`，HEAD 58973a6 + 未提交工作区修复）

| 文件 | sha1 |
| --- | --- |
| family_agenda.py | 8348a71661cc22860eb40423224c576bba1109a6 |
| test_daily_list_expression.py（新增） | 625a74f3459412e502d3bd86ca71fb7a6ff57432 |
| test_school_completion_today.py | 504afb2283139bb51d882b9445db25da0d46bbe8 |
| app.js | 4c17738bb0917e0eee4c098214502ddbc363b333 |
| calendar.js | fdd6189afae4e811856d73b5e3ff2d294df786d3 |
| packaging/macos/Sources/Workspace.swift | f36453b251f540f2e9665a3353c93a1101df5843 |
| packaging/macos/Sources/WorkspaceAPI.swift | 2d43a51173500c2d09e2b14fb59c21d86a46bb57 |

完整补丁：`work/deliverable/证据/fix.patch`（66437 B，sha1 46bcb127…，7 files +591/−36，可 `git apply` 到 HEAD 58973a6）。
App 二进制：`work/deliverable/一起成长.app/Contents/MacOS/YiqiChengzhang`，sha1 `1befa315bc4103bf37d3dbcb65e4a6d498d35867`（Swift 未变 → 与上一轮重建逐字节相同，确定性构建）。

## 三、改了什么（只动展示层）

1. **服务端投影**（family_agenda.py）
   - `action_lines`：按「完全相等/连续子串」判重（不使用相似度阈值）；去「提交要求/补充要求/补充说明/正文」标签；标题复述句被标题 token 覆盖时才整行省略；标签行只允许「以上一行最后一个子句为前缀」的追加式折叠（禁止句中新插入）；否定句永不被同形句吞掉。
   - `day_view`：把「家庭安排（计划 …）：…」从要求行拆成独立字段 `plan_lines`（纯正文，类别标签由客户端按 `facts` 里的 `role=scheduled` 拼日期）。
2. **网页**（calendar.js / app.js）：日清单卡逐句成行（不再 `join('；')`，消除「。；」「；；」），家庭安排在清单卡和详情页各自独立成块/小节。
3. **原生**（Workspace.swift / WorkspaceAPI.swift）：`plan_lines` 解码；列表卡独立一行「家庭安排（计划 日期）：…」，详情页独立小节。
4. **测试**：新增 `test_daily_list_expression.py`（33 条，含 C1–C8 契约、三条虚构卡 golden、plan_lines、F1/N1/N2 回归）；`test_school_completion_today.py` 只把「标签类」期望改成「标签去掉但内容仍读到」，全部旧守卫（bare/join-back/朗读第20页）已恢复。

## 四、Lead 独立复核（自己跑的，不是采信队友汇报）

- 七文件 sha1 与冻结值**逐一对上**。
- 套件：`test_daily_list_expression` OK(33) / `test_daily_list_whole_day` OK(19) / `test_school_same_ready_notice` OK(30) / `test_agenda` OK(26) / `test_school_completion_today` Ran 55 **FAILED(failures=3)**——三条与 HEAD 基线逐名相同（`ConfirmedSchoolHandbackCorrectionTests` 两条 + `OrdinaryOwnedTimeTests.test_unknown_changed_cancelled_conflicting_or_borrowed_days_stay_unknown`），属既有失败。
- 启动器独立自检：`FAMILY_DEMO_PORT=8772 ./一起成长·虚构一日演示.command --check` → **RC=0**，today=5 later=2 open=7 closed=1 undated=1 upcoming=0，卡片文本有独立「[家庭安排]」行、无「提交要求/补充要求」字样。
- 补丁可应用性：`git worktree add /tmp/applycheck HEAD` + `git apply --check fix.patch` → **PATCH APPLIES CLEANLY TO HEAD**。
- App：`codesign --verify --deep --strict` 通过、`CFBundleVersion=308`、`otool -L` 仅系统库。
- 网页 DOM 断言（surface 的 `assert_plan_lines_ui.cjs`，期望值取自 `/api/day`）：`failures=[]`，360/1440 截图与「家庭安排」小节通过。
- 收尾：本轮所有 `demo.py` 虚构后台进程已停止，8766 端口已释放。

## 五、独立审查时间线（work/reviewer-evidence/）

1. 第一轮：判当前实现 **RED/BLOCK**——相似度去重会吞掉真实信息（「明天不交」被「明天交」吞、丢掉新增题号、折叠产生句中插入的非原文串）。
2. Lead 要求限缩为「相等/连续子串」+ 硬保护，projection 返工（6c1574d7）。
3. 第二轮：复查仍 **BLOCK** 两项窄修（`_whole_title_repeat` 缺 token 守卫、「读一遍/再读一遍」被副词折叠吞）。Lead 在沙箱先验证补丁，再让 projection 落地（8348a716）。
4. 第三轮窄复核：**GREEN（可交付）**。语料 68 组仅 6 处纯重复/纯标签、对抗 18 条 RED=0、无新丢失。

## 六、已知限制（交付前需知晓）

1. 交付件是「**连接入口客户端**」：不含内置 Python 运行时（构建机无 `FAMILY_MAC_MATERIALS`/`FAMILY_MAC_WHEELS`），必须配后台；演示用 `demo.py` 全虚构后台。家庭正式环境需按交付说明第十一节打**完整包**。
2. 演示后台无学校消息采集器/模型，回执的「家庭安排」标签**不带（计划 日期）**（演示数据没有 `facts` 的 `role=scheduled`，带日期形态见 `work/surface-evidence/plan-date/`）。
3. 原生侧只有**编译级**+二进制字节证据，未做可见窗口验收（交接规则：本机静默）；可见原生验收需在家庭 Mac 或允许可见窗口的环境执行。
4. 只差「也/都/还/再」等副词的两行近似重复现在各自保留（宁多勿漏），卡片可能轻微重复。
5. 标题复述句「只要还带新信息就整行保留」与句末分号「今天完成；」属 **HEAD 既有契约/既有观感**，本轮不改（已用 HEAD 侧代码复验同样表现）。
6. 既有失败不属于本轮：`test_school_completion_today.py` 3 条、`test_today_ui.cjs`（作业原件可见性）、`test_daily_list_actual_scope_ui.cjs:52`（旧展示契约）、`test_daily_list_frozen.py` 4 条（均与干净 HEAD 逐名相同）。
7. 未 commit / 未 push：补丁在 `证据/fix.patch`，发布前应先在公开仓库提交并重新正式构建。

## 七、下一步建议

1. 在公开仓库提交本补丁（`fix.patch` 可直接 `git apply`），跑 PR 前全量测试，把 4 类既有失败单独立项。
2. 在家庭 Mac 用完整包构建（`FAMILY_MAC_MATERIALS` + `FAMILY_MAC_WHEELS`）做可见原生验收：单孩子切换、按科目清单、口头补录、文字/照片反馈、错题与订正。
3. 真实家长验收（`真实家长验收=false` 尚未翻转）——这是交接包里的硬门槛。

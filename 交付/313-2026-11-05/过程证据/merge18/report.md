# 18 条多渠道消息 · 真实模型真跑对账报告（merge18）

> 目标：用**真实模型**（火山方舟 `doubao-seed-evolving`）把交接包 `FIXTURE.json` 的 18 条多渠道消息跑过产品自己的通路，逐项对 `ORACLE-EXECUTION.json`，回答「多渠道同件事归并到底通不通，通到几分」。
> 结论一句话：**通路能跑通、单条识别基本正确，但「同一件事从第二个渠道/第二批消息再来时并回同一张卡」这件事只通了一半：8 组同事项里 4 组完全合并、1 组部分合并、3 组失败；严格全对的 matter 3/8。**

跑数时间：2026-11-04 23:03–23:12（本机），模型 8 次调用全部成功，0 失败；18/18 条消息 processed。
产品代码：`/Users/joyrush/.local/share/family-learning/public-integration-20260926`（git HEAD `58973a6`；本报告 §1–§9 是**改前**验证轮、未改产品代码；§10 是随后 owner 修复轮的改后数字，只改了 `family_agent.py`，见 §10.0 的 sha1）。
真值：`…/全虚构验收材料/ORACLE-EXECUTION.json`（未改动）。

---

## 0. 结论数字（先看这行）

| 维度 | 真值 | 产品实际 | 判定 |
|---|---|---|---|
| 8 件事识别 | 8 | 8（都有代表卡/任务） | **8/8 识别** |
| 8 件事「要素+日期+状态+单卡」全对 | 8 | **3**（a-art-cancelled、b-photo、b-math） | 3/8 全对；加「主卡对但多噪音卡」共 **4/8** |
| 18 条消息落点 | 18 条各归其事项 | 13 条干净落点；4 条落成重复待核卡（m04/m10/m13/m18）；1 条被拆成两卡（m17） | **13/18 干净** |
| 同事项 8 组归并 | 8 组各 1 件 | 4 组完全合并、1 组部分（a-math）、2 组失败（a-reading、a-english） | **4/8 完全合并** |
| 跨渠道（QQ↔微信）同事项 | 2 组（a-math、b-math） | a-math 分裂成 2 卡；b-math 合成 1 任务 | **1/2** |
| selected_day_truth：active 7 / cancelled 1 / today_required 5 / future_only 2 | — | 7 件事都在当天清单；取消 1 张「已取消」待核卡（正确）；today_required **成任务 3/5**、第 4 件有待核卡、第 5 件被记成 11-06 截止；future_only 2/2 正确但混排在 11-04 inbox | **取消对；today 3~4/5；future 2/2** |
| 附件 2 份（一读一未读） | 英语附件已读、完整要求落进任务；语文附件未读、不得编造 | 英语：读页成功、三行要求逐条落进任务；语文：已保存未读、卡上写「尚未读取」、未编造内容 | **2/2 正确** |
| 模型调用 | — | 8 次（7×selection + 1×school_task），**全部成功**，合计 192.9s | — |

---

## 1. 怎么跑的（可复现）

### 1.1 来源映射（FIXTURE 5 源 → 产品 6 个 source）

产品 `agent.json` 的 source 只接受 `platform ∈ {wechat, qq}` 且**一个 source 只能绑一个 child_id**；`qa-family-manual` 是 `manual_input`、且同时给两个孩子（m10→child-1、m17→child-2）。因此拆成两个「家庭手记」伪源，这是产品能力边界外的表示映射，对账时按消息级映射回原 source：

| FIXTURE source | 产品 source id | platform | child | 消息 |
|---|---|---|---|---|
| qa-qq-a4 | qa-qq-a4 | qq | child-1（qa-heldout-child-a→child-1） | m01,m02,m05,m07,m09,m12,m13,m18（8 条，产品按 6+2 分两批） |
| qa-wx-a4 | qa-wx-a4 | wechat | child-1 | m04 |
| qa-qq-b2 | qa-qq-b2 | qq | child-2（→child-2） | m03,m06,m08,m14,m15,m16（6 条） |
| qa-wx-b2 | qa-wx-b2 | wechat | child-2 | m11 |
| qa-family-manual | qa-manual-a | wechat | child-1 | m10 |
| qa-family-manual | qa-manual-b | wechat | child-2 | m17 |

`sender_id` 用 FIXTURE 里该渠道的已验证账号 id（如 `qa-qq-a-math` / `qa-wx-a-math` / `qa-parent` / `qa-child-b-speaker`），`sender` 用显示名，`time`=sent_at，`unread=False`。

### 1.2 附件注入（FIXTURE 未提供真实字节）

FIXTURE 的 `attachment_contract` 明确「未提供真实字节，不测解码/读图」。因此：
- **h18-att-english-read（PDF）**：用产品测试 `test_pdf.build_pdf(1)` 生成真 PDF，用产品自己的页读取回执路径 `test_pdf_material.page_model([page])` 注入 FIXTURE 的已读说明文本（`一、看图选词第1—3题。/二、标星单词 under、near 各抄写一遍。/不需要录音。`），即产品 U02 用例同款机制；`save_upload` + `store.message_attachment` 挂到 m05。
- **h18-att-chinese-unread（jpg）**：PIL 生成真 JPEG 挂到 m08；`family_media.prepare_draft` 由测试夹具 patch 成 `dict(used=0,failed=0)`（与家庭环境未启用媒体草稿一致），jpg 保持未读态，符合 FIXTURE 的 `unread / processing_pending`。

产品代码、测试、ORACLE 均未修改；夹具原有 patch（qq_capture / teacher_public / family_media / family_goals / 模型桩）全部保留，只把 `family_llm._chat_json` 的测试桩换成真调用（`run_real_model.py` 同款做法）。

### 1.3 时间线与预算

- `now` 从 `2026-11-04T20:00+08:00` 起，每 tick +7 分钟，共 **7 tick**（20:00→20:42）；产品 `run_once` 每 tick 模型预算 `budget=3`（`family_agent.py:10118`），每 source 每 tick 只取一批并 `break`。
- tick 结果：`created/processed` = 9/8, 9/8, 2/2, 4/2, 0/0, 0/0, 0/0；第 4~6 tick 连续无变化后停止。18/18 processed，0 failed。
- 剩余状态：14 个 school `agent_items`（6 accepted / 8 pending）+ 5 个 goal-* 草稿（学习目标，非事项）；**5 条 manual_tasks**。

### 1.4 模型调用（次数 / 耗时 / 覆盖）

| # | name | 耗时(s) | 覆盖消息 | 备注 |
|---|---|---|---|---|
| 0 | family_agent_selection | 36.91 | qq-a4 第一批 m01,m02,m05,m07,m09,m12 | 6 条一批，36.9s，接近产品 45s 超时 |
| 1 | family_agent_selection | 20.86 | wx-a4 m04 | pending_seen=4、tasks=0 |
| 2 | family_agent_selection | 34.47 | qq-a4 第二批 m13,m18 | pending_seen=4、tasks=1 |
| 3 | family_agent_selection | 22.82 | qq-b2 6 条 m03,m06,m08,m14,m15,m16 | pending_seen=0 |
| 4 | family_agent_selection | 20.73 | wx-b2 m11 | pending_seen=1、tasks=2 |
| 5 | family_agent_selection | 25.45 | manual-a m10 | pending_seen=5、tasks=1 |
| 6 | family_agent_selection | 12.52 | manual-b m17 | pending_seen=1、tasks=2 |
| 7 | family_school_task | 19.13 | m05 的英语卡（→ 任务） | 唯一一次 brief/accept 模型调用 |

**合计 192.89s，均值 24.1s，最长 36.91s；8 次调用 0 失败。**
> 原始请求与完整返回（含每次 evidence refs 与 proposals）留档在 `model-calls.json`（47 KB）。

### 1.5 产物

| 文件 | 内容 |
|---|---|
| `work/merge18/run.json` | 全量真跑数据：fixture、source、payloads、calls 索引、ticks、final（items/tasks/messages/jobs/pdf_material/drafts/day/next_day） |
| `work/merge18/model-calls.json` | 8 次模型调用的**原始请求与原始返回**（未裁剪） |
| `work/merge18/states.json` | 每个 tick 的完整快照（869 KB） |
| `work/merge18/run.log` | tick 日志 + 最终状态打印 |
| `work/merge18/run_merge18.py` | 真跑 harness（可重跑：`python3 run_merge18.py 30`） |
| `work/merge18/compare.py` | 按 ORACLE 五项打印对账（`python3 compare.py`） |
| 本报告 | 人工对账结论 |

---

## 2. matters：8 件事逐项对账

图例：✅ 与 ORACLE 一致；⚠️ 部分/歧义；❌ 明确不一致。

### 2.1 h18-a-math（child-1 数学）— ❌ 未合并 + 丢「今晚完成」
ORACLE：active，「《每日练习》第26页第1—3题」，3 条消息 m01/m04/m09 一件；units=1—3、算式、验算、家长签字、周五交（11-06）；complete_by=11-04；negative=第4题不做。
产品实际 **2 张待核卡、0 任务**：
- `agent-f95d…`（m01+m09）：1—3 ✅、第4题不做 ✅、算式 ✅、验算 ✅、签字 ✅、周五交给周老师（due=2026-11-06，due_kind=deadline）✅；**❌ 无「今晚完成」**：goal/body 均无，agenda `complete_on=''`；虽然 m04 卡上有「今晚做并签字」，但那是另一张卡。state=`review`（reason：「原通知含多个日期，已按原文取 2026-11-06；请核对这一天是否属于本事项。」）→ 未成任务。
- `agent-ed30…`（仅 m04，跨渠道）：范围仍是**已被更正的 1—4 题** ❌；body「今晚做并签字。周五交。」；due=2026-11-06、complete_on 空；state=review。
差异：① 同事项拆 2 卡（m04 未并入）；② m04 卡仍是过期范围，家长会看到 1—4 与 1—3 两张冲突卡；③ 「今晚完成→11-04 完成」丢失，事项被呈现成 11-06 截止（ORACLE 明令不得「把周五交回覆盖今晚完成」）。

### 2.2 h18-a-reading（child-1 语文）— ❌ 3 卡未合并
ORACLE：active；units=第2、3自然段各朗读两遍(paragraphs 2,3/times_each=2)、读给家长听、明早林老师抽听；dates complete_by=11-04 / teacher_check_on=11-05 / family_plan_at 11-04 18:30；negative=不用录音、不用上传、不用背诵。
产品实际：**1 任务 + 2 张待核卡**
- `agent-602b…`（m02，accepted → `AGENT-160c6c9c…`，due=2026-11-04，deadline）：body 原句完整含各两遍 ✅、读给家长听 ✅、不用录音/上传 ✅、明早抽听 ✅；❌ 无 18:30 家长安排（在另一张卡）、无 11-05 教师检查日期字段（仅文字）。
- `agent-fb40…`（m10 家庭手记，pending）：body 有「今天18:30家长来听」✅，但 ORACLE 要求它是**同一事项的家庭安排**，不得成为第二张卡；本卡也缺 11-05 抽听之外的完整度。
- `agent-fc70…`（m18 提醒，pending）：各两遍 ✅、不用背诵 ✅、明早抽听 ✅；❌ 缺「读给家长听」（reminder 未并回原任务，ORACLE 期望合并后补豁免「不用背诵」）。
差异：ORACLE `must_not` 明令「复制成家长安排与老师朗读两项独立作业」——产品正是这样；m18 的 exemption 也没落到原任务。

### 2.3 h18-a-english（child-1 英语）— ⚠️ 要素齐，但多一张重复卡
ORACLE：active；units=看图选词 1—3、under/near 各抄写一遍、做完放英语夹明早带来；negative=不需要录音、不用群里发照片；attachment=已读完整说明。
产品实际：**1 任务 + 1 张待核卡**
- `agent-4a14…`（m05，accepted → `AGENT-e9f38c84…`）：body 含原句+附件三行（1—3 ✅、under/near 各一遍 ✅、不需要录音 ✅、放英语夹/明早带回 ✅）；`school_original_action` 把三行附件要求逐条锚到页 1 与 upload_id，**附件真读了**；due=2026-11-05（deadline）、complete_on=2026-11-04 ✅。
- `agent-e356…`（m13 补充，pending，plan `school_pending_of=agent-4a14…`）：body「完成后放进英语夹，明早带来。不用在群里发照片。」→ 「不用群里发照片」只在这张孤立卡上；❌ 未并回主任务（ORACLE 要求 supplement_same_requirement 合并）。
差异：任务本身完整且附件正确；多出一张与主任务重复的待核卡，且 m13 的否定约束没进任务。

### 2.4 h18-a-art-cancelled（child-1 美术）— ✅ 正确
ORACLE：**cancelled**，当前有效要求为空；history 保留 m07 原要求与 m12 取消；不得出现在今日必须做；不得删原通知。
产品实际：**1 张卡 `agent-0049…`（m07+m12 合并）**：title「美术：带落叶及旧书要求已取消」，body「明天美术课改用教室里的材料。原要求带两片落叶并夹在旧书里，现已取消，不用带叶子和夹叶子的旧书。」；`school_selection_receipt.change='cancel'`、`school_task.state='review'`、purpose=admin、reason「老师已明确取消…不应生成执行任务；保留取消记录。」；无 due、未成任务、不在 today 必须做里。
判定：符合 ORACLE `cancellation_safety`（保同一张明确变更待核卡、不当作有效必须做、不丢历史、不影响乙的彩笔）。

### 2.5 h18-b-math（child-2 数学）— ✅ 跨渠道合并成功（任务级）
ORACLE：active；units=第4页1—6题直接写得数、不用抄题、明天交；negative=不另加题、已做过不用再做一遍；3 条 m03/m11/m16 一件。
产品实际：**1 个任务 `AGENT-45400257…`（due=2026-11-05，handback，complete_on=2026-11-04）**；day inbox 该任务 publications=`m03,m16,m11`（跨 QQ 群 + 微信群 + 同群提醒都并进了同一任务）✅；action 含 1—6、直接写得数、不用抄题、明天交、已做过的不用再做一遍 ✅。
小瑕：`agent-b2a3…`（m11）也以 accepted 身份指向同一 task（plan `school_duplicate_of=agent-8b5a…` + `school_same_receipt`），即同一任务有 2 个 accepted item；m11 的「不另加题」只在这条重复 item 上，未进任务 action（ORACLE negative 少一条）。任务是 1 条，家长看到的是合好的一件事。

### 2.6 h18-b-photo（child-2 班主任通知）— ✅ 正确
ORACLE：active（future_only，11-05 带来）；units=一张一寸证件照交班主任更新学生卡、一张就够、不用重拍、蓝底白底都可；不得猜成作业、不得把今天当今天到期。
产品实际：**1 任务 `AGENT-f8189530…`（m06+m14 合并）**，due=2026-11-05、due_kind=arranged、无 complete_on（不是今天做）✅；goal 含一张就够/不用重新拍/蓝底白底都可以 ✅；subject_state=unknown、category=todo（未猜成作业）✅。

### 2.7 h18-b-chinese-unread（child-2 语文，附件未读）— ⚠️ 内容对，但状态停在待核
ORACLE：**active_with_material_gap**；units=完成附件练习（具体范围待读取）、家长卡片下方签名、明早交郑老师；complete_by=11-04 / hand_back_on=11-05；unknowns=具体题目/页码题号/数量/附件内完成标准；不得编造生字拼音页码、不得让其他孩子/科目待核、不得隐藏该事项、不得说成格式拒绝/已读。
产品实际：**1 张待核卡 `agent-e172…`（m08+m15 合并）**：body/goal「今晚完成附件《识字小卡》上的练习；完成后请家长在卡片下方签名，明早交给语文老师。」✅；reason「…但附件图片中的具体练习内容尚未读取。」✅ 未编造；agenda due_on=2026-11-05 handback、complete_on=2026-11-04 ✅；**❌ 未成任务**（state=review，因为附件未读→不敢 accept），ORACLE 要求它是「active 但有材料缺口」的活跃事项，而不是等家长核对的 review 卡。
另：FIXTURE `reason_code=processing_pending` 在产品卡面上只以散文「尚未读取」出现，没有该代码值（AC04 只要求断言已保存/未读/原因对应，本项目判为可接受，但记录口径差异）。

### 2.8 h18-b-art-oral（child-2 美术，孩子口述）— ⚠️ 主卡对，多一张残片
ORACLE：active；units=明天带一盒彩笔；日期 bring_to_class_on=11-05；attribution：source_kind=child_oral_entry、speaker=孩子乙、recorded_by=家长、teacher_identity_verified=false、group_message_support=false；不得冒充群通知、不得要求先匹配群消息、不得与甲已取消事项合并。
产品实际：**主任务 `AGENT-98b8eead…`（due=2026-11-05，arranged）**：body「明天（2026-11-05）带一盒彩笔。消息中称未在群内看到这条通知。」✅；card goal 明确「该要求来自孩子转述美术老师今天课堂所说，消息中称未在群内看到这条通知」✅ attribution 正确；未与甲事项合并 ✅。
小瑕：**同一条 m17 被拆出第二张卡 `agent-8958…`**，title/body 仅「美术老师今天课上说」、plan `school_split_from`、`school_unadopted_due=2026-11-04` → 一张无内容残片进入 11-04 清单（该卡 status=待核对，会被当成今天的事）。

### 2.9 matters 小结

| # | matter | 识别 | 要素 | 日期 | 状态 | 卡数 | 判定 |
|---|---|---|---|---|---|---|---|
| 1 | a-math | ✅ | 差 complete_by | ❌ 只 11-06 | review | 2 | ❌ |
| 2 | a-reading | ✅ | 主卡齐、m10/m18 未并 | 主卡 11-04 对 | 主卡 task；2 卡 review | 3 | ❌ |
| 3 | a-english | ✅ | 主卡齐（m13 否定未并） | 11-04 完成 + 11-05 交 ✅ | task + 1 review 卡 | 2 | ⚠️ |
| 4 | a-art-cancelled | ✅ | ✅ | 空 ✅ | cancel review ✅ | 1 | ✅ |
| 5 | b-math | ✅ | 差「不另加题」 | ✅ | 1 task（2 accepted item） | 2 | ✅ |
| 6 | b-photo | ✅ | ✅ | ✅ 11-05 arranged | 1 task ✅ | 1 | ✅ |
| 7 | b-chinese-unread | ✅ | ✅（含缺口声明） | ✅ | review 非 task | 1 | ⚠️ |
| 8 | b-art-oral | ✅ | ✅ | ✅ 11-05 | 1 task ✅ | 2（含残片） | ⚠️ |

**严格全对 3/8；把「主卡对、多噪音卡」也算通过则 4/8；要素/日期层面 6/8 基本齐（缺 a-math complete_by、b-math「不另加题」）。**

---

## 3. per_message_destination：18 条消息落点

| 消息 | 内容要点 | ORACLE 期望 | 产品落点 | 判定 |
|---|---|---|---|---|
| m01 | 数学 26页1—4题，今晚完成，签字，周五交 | a-math new | `agent-f95d`（与 m09 合并，1—3） | ✅ |
| m02 | 朗读第2、3段各两遍，读给家长，明早抽听 | a-reading new | `agent-602b` → task `AGENT-160c` | ✅ |
| m03 | 计算小卡第4页1—6题，今晩做完，明天交 | b-math new | `agent-8b5a` → task `AGENT-4540` | ✅ |
| m04 | 再提醒数学《每日练习》26页1—4题，今晚做签字周五交 | a-math cross_channel_reminder | **新卡 `agent-ed30`**（1—4 过期范围，未并入 f95d） | ❌ 重复卡 |
| m05 | 英语《每日练习》见附件，今晚完成，放英语夹明天带 | a-english new+read attachment | `agent-4a14` → task `AGENT-e9f3`（附件三行已读入） | ✅ |
| m06 | 明早带一寸证件照交班主任更新学生卡 | b-photo new | `agent-71f9` → task `AGENT-f818` | ✅ |
| m07 | 明天美术带两片落叶夹旧书 | a-art-cancelled new | `agent-0049`（后被 m12 合并取消） | ✅ |
| m08 | 今晚完成附件《识字小卡》练习，明早交 | b-chinese new+unread attachment | `agent-e172`（与 m15 合并） | ✅ |
| m09 | 更正：26页只做1—3，第4题不做，其余不变 | a-math correction | `agent-f95d`（与 m01 同卡） | ✅ |
| m10 | 林老师那项朗读，今天18:30我来听，仍按两遍 | a-reading parent_family_plan | **新卡 `agent-fb40`**（未并入 task，18:30 未进任务） | ❌ 重复卡 |
| m11 | 计算小卡第4页1—6题再提醒，今晚做完明天交，不另加题 | b-math cross_channel_reminder | `agent-b2a3`，accepted 指向 task `AGENT-4540`（`school_duplicate_of` + `school_same_receipt`） | ✅ |
| m12 | 美术改用教室材料，带落叶那项取消 | a-art-cancelled cancellation | 并入 `agent-0049`，change=cancel | ✅ |
| m13 | 补充英语：放英语夹明早带，不用群里发照片 | a-english supplement | **新卡 `agent-e356`**（plan `school_pending_of=agent-4a14`，未折回） | ❌ 重复卡 |
| m14 | 明早带证件照，一张够，不用重拍，蓝白底都可 | b-photo supplement | 并入 `agent-71f9` | ✅ |
| m15 | 识字小卡完成后家长签名，明早交 | b-chinese supplement | 并入 `agent-e172` | ✅ |
| m16 | 计算小卡还是第4页1—6题，不用抄题，做过的不用再做 | b-math reminder | `agent-8b5a`（与 m03 同卡） | ✅ |
| m17 | 孩子口述：美术老师说明天带一盒彩笔，群里没看到通知 | b-art-oral new_child_oral | 主卡 `agent-ebcd` → task `AGENT-98b8` **+ 残片卡 `agent-8958`** | ⚠️ 拆两卡 |
| m18 | 朗读仍是第2、3段各两遍，不用背诵，明早抽听 | a-reading reminder_and_exemption | **新卡 `agent-fc70`**（due 门槛判 review，未并回 task） | ❌ 重复卡 |

统计：**干净落点 13/18**；落成重复待核卡 4 条（m04、m10、m13、m18）；1 条（m17）主卡正确但额外拆出残片卡。18/18 全部被 ingest 并 processed，无丢消息。

---

## 4. same_matter_groups：8 组同事项归并

| ORACLE 组 | 消息 | 产品结果 | 判定 |
|---|---|---|---|
| a-math | m01,m04,m09 | f95d(m01+m09) + ed30(m04)；m04 范围过期 | ❌ 部分（2 卡） |
| a-reading | m02,m10,m18 | 602b task + fb40(m10) + fc70(m18) | ❌ 3 卡 |
| a-english | m05,m13 | 4a14 task + e356(m13) | ❌ 2 卡 |
| a-art-cancelled | m07,m12 | 0049 单卡，cancel 合并 | ✅ |
| b-math | m03,m11,m16 | 单 task 4540，publications 3 条 | ✅（任务级） |
| b-photo | m06,m14 | 71f9 单任务 | ✅ |
| b-chinese-unread | m08,m15 | e172 单卡（review） | ✅ |
| b-art-oral | m17 | ebcd 单任务 + 8958 残片 | ✅（多残片） |

**完全合并 4/8（50%）**；部分合并 1/8（a-math：m01+m09 合了、m04 没合）；未合并 2/8（a-reading 3 卡、a-english 2 卡）。
跨渠道组：a-math（qq-a4 ↔ wx-a4）失败、b-math（qq-b2 ↔ wx-b2）成功 → **跨渠道 1/2**。
失败模式很一致：**「第一批消息建卡时还是 pending，第二批/另一渠道的消息来了，产品只会给它另建一张 pending 卡并备注关联，不会折回原卡」**；只有目标已经是 accepted 任务、且同发布者/对象/日期门槛全过时，才会走 `school_duplicate_of` 合并（b-math）。跨渠道场景连「同发布者」都过不了（见 bug #1）。

---

## 5. selected_day_truth（2026-11-04）

产品 `calendar_snapshot('2026-11-04','2026-11-04')` 的 inbox：**12 张卡 = 5 task + 7 school 待核卡**；次日 11-05 快照同样是这 12 张（内容完全相同）。

| 真值 | 产品实际 | 判定 |
|---|---|---|
| active_inventory_total=7 | 7 件事都有代表卡/任务（a-math 2、a-reading 3、a-english 2、b-math 2 item/1 task、b-photo 1、b-chinese 1、b-art-oral 2） | 7/7 存在，但有 5 张多余重复卡 |
| cancelled_inventory_total=1（a-art-cancelled） | 1 张「已取消」待核卡，未成任务、不进今日必须做 | ✅ 1/1 |
| today_required=5（a-math,a-reading,a-english,b-math,b-chinese） | 成任务：a-reading ✅、a-english ✅、b-math ✅；b-chinese 有待核卡（complete_on=11-04）但未成任务；a-math 2 张卡 due=11-06、complete_on 空 | **task 层 3/5；卡层 5/5** |
| future_only=2（b-photo,b-art-oral） | 2/2 都成任务，due=2026-11-05、due_kind=arranged、无 complete_on（不是今天做）✅；但两张卡混排在 11-04 inbox（产品没有「今日必须做」计数字段可验证是否被计数），另有残片卡 8958 带 `school_unadopted_due=11-04` | 2/2 日期对，排序/计数有噪音 |
| by_child：child-a today3/future0/cancelled1 | child-1：任务 2（朗读、英语）+ 5 张卡（a-math 2、reading 2、english 1、cancel 1）；a-math 未成任务 → today 2/3 | ⚠️ 差 1（a-math） |
| by_child：child-b today2/future2/cancelled0 | child-2：任务 3（b-math、证件照、彩笔）+ 2 张卡（chinese、残片）；today 任务只有 b-math（chinese 未成任务）→ today 1/2；future 2/2 | ⚠️ 差 1（b-chinese 状态） |
| progress_truth：无任何已完成事实 | 无任务被标完成/已交/已签；`original_status` 全为「待跟进」 | ✅ |
| carry_rule：未完成今晚事项跨天保原 11-04 完成日 | 11-05 快照与 11-04 相同、a-reading complete 字段保持空（due=11-04） | 未见反例，但快照不按日拆分，无法强验证 |

**一天清单的正确率：取消 1/1 对；今天必须做 3/5 成任务（4/5 有卡）；未来 2/2 对；但 5 张重复卡 + 1 张残片把 12 条清单撑到 8 件事之上。**

---

## 6. attachment_truth：两份附件

| 附件 | FIXTURE 真值 | 产品实际 | 判定 |
|---|---|---|---|
| h18-att-english-read（PDF，m05） | 已读、instruction_text_complete=true、read_scope=完整布置说明；units=看图选词1—3 / under,near 各一遍；不得只写「完成附件」 | `agent_pdf_material` 行：`qa-qq-a4 / h18-m05`，`pages=[1]/1`、payload kind=school_material、originals[0].requirements = 三行原文；`agent-4a14` 的 `school_original_action.anchors` 把三行分别锚到页 1 与 upload_id；任务 body 三行逐条落进去 | ✅ 已读 + 要求落地，未遗漏单位 |
| h18-att-chinese-unread（jpg，m08） | 已保存、read=false、reason_code=processing_pending、unknowns=具体题目/页码题号/数量/完成标准；不得从标题猜内容；scope 仅限本附件 | upload 已挂到 m08；`agent_message_drafts` 无行（未读）；`agent-e172` reason 明写「附件图片中的具体练习内容尚未读取」，未出现生字/拼音/页数/题数；只影响本事项，未波及其他孩子/科目 | ✅ 未读态 + 未编造 + 局部化；代码值 `processing_pending` 未出现在产品卡面（散文「尚未读取」），口径差异已记录 |

交叉污染检查：英语附件只出现在英语任务；语文附件只出现在语文卡；无「两个附件都已理解」类断言（AC04 禁止项未触发）。

---

## 7. 发现的产品问题（未改产品代码，附最小复现与行号）

> 以下均已在本轮真跑复现；建议 lead 派单时按「agent 归并/日期」和「selection 批次健壮性」两类拆。

### B1. 跨渠道同一教师无法归一 → 跨渠道提醒不并入（严重）
- 位置：`family_agent.py:1218 _publisher()` = `'publisher:' + _hash([source_id, message['sender_id']])[:20]`；`_school_pending_link()`（`family_agent.py:2651`）要求 `e['publisher']==target['publisher']` 且同一 `source_id`。
- 复现：同一位数学老师的 QQ 群消息 m01（`sender_id=qa-qq-a-math`）与微信群提醒 m04（`qa-wx-a-math`）→ 两个 publisher 哈希不同 → m04 被模型判「发布者不同且题号范围不同，不能直接绑定」（`agent-ed30` 的 `school_selection_receipt.reason` 原文），生成第二张卡，且范围是已更正的 1—4。
- 影响：ORACLE 明确要求 m04 是 `cross_channel_reminder` 并回同一事项；现在家长看到 1—4 与 1—3 两张冲突卡。
- 建议：用渠道账号的 verified 身份（同一 publisher 的 `verified_channel_accounts`）做 `_publisher` 归一，或允许跨 source 的同一人/同一对象链接；不要降低「同对象」门槛。

### B2. 待核事项的后到补充/提醒只挂链接、不折回原卡（严重，主因）
- 位置：`_save` 组装分支 `family_agent.py:8161-8162`：`item['plan']['school_pending_of']=link`；`if brief['state']=='ready': brief['state']='review'`——新卡照样插入；`school_pending_targets`（`:2622`）与 `_school_pending_link`（`:2651`）只产生「关联备注」。`_reconcile_school_same`（`:3320`）只处理**已保存任务**；`_reuse_school`（`:2141`）只匹配 `state IN ('accepted','dismissed')` 且 title/body/due 全等。
- 复现：qq-a4 第一批 m05 → `agent-4a14` pending；第二批 m13 → 新建 `agent-e356`（plan `school_pending_of=agent-4a14`，state review）；随后 4a14 被 accept 成任务，e356 永久留成孤儿重复卡。m18 同理（`agent-fc70`）。
- 影响：同事项多卡（本任务 8 组里 3 组失败、5 张多余卡都由此产生）。
- 建议：pending 目标命中 `school_pending_of` 且证明成立时，把新消息作为**原卡 evidence 追加**（或原卡上的补充行），不新建 item；原卡 accept 后，补充行/否定约束随 task 一起落。

### B3. 无日期提醒被日期门槛推成 review（严重，m18）
- 位置：`family_agent.py:8199`：`if brief.get('change')=='same' and brief['state']=='ready' and (why:=_school_same_due(item['due'],target or {},cited_evidence)): brief.update(state='review', ...)`；`_school_same_due` 在 `:3119`。
- 复现：m18「朗读仍是…不用背诵，明早抽听」无日期；原任务 due=2026-11-04 → 该分支判 review（`agent-fc70` 的 `school_task.reason`：「…截止日期尚无法从原文核对，未采用模型日期；请核对原通知。」），不并回原任务。
- 影响：ORACLE 要求 m18 合并为 reminder + exemption（「不用背诵」应补进原事项）；现在是重复卡。
- 建议：提醒（change=same）无日期时继承目标任务的日期，而不是 review；同时把 exemption 作为 negative_constraint 追加。

### B4. 多日期通知丢「今晚完成」→ complete_by 丢、只留 11-06（严重，a-math）
- 位置：`family_agent.py:8118` `if len(relative)>1 and not owned: ambiguous_due=True`，最终 `due=''`/取 11-06 并 review（`:8199-8215`）；`agenda.complete_on` 因此为空。模型侧 `_select` 返回的 goal 本身也已丢「今晚完成」（f95d `school_selection_receipt.goal` 无「今晚」），产品没有从原文兜底补出 `complete_by`。
- 复现：m01（今晚完成 + 周五交）+ m09（只更正范围）同批 → `agent-f95d` due=2026-11-06、complete_on=''、goal 无今晚；ORACLE 要求 complete_by=2026-11-04 + hand_back_on=2026-11-06。
- 影响：事项在清单上表现为「11-06 截止」，今天的必须做丢失；ORACLE `must_not`「把周五交回覆盖今晚完成」触发。
- 建议：产品 agenda 已有 `complete_on` 与 `due_on` 两字段，日期守卫应把本句「今晚 X」解析到 complete_on、把「周五交」解析到 due_on；模型丢字段时用原文补。

### B5. 一条孩子口述被拆成两张卡（中，b-art-oral）
- 位置：`_save` 的 split 分支 `family_agent.py:8141-8150`（写 `school_split`/`school_split_from`）；本任务里 m17 被拆成 `agent-ebcd`（正确）+ `agent-8958`（残片「美术老师今天课上说」），残片 plan 带 `school_unadopted_due=2026-11-04`。
- 影响：无内容残片进 11-04 待核清单，稀释今日必须做。
- 建议：split 出的子项若 brief 无 requirement/无日期/`state!='ready'`，要么丢弃、要么并回主卡，不单独建卡。

### B6. 同一任务被两个 accepted item 指向（轻，b-math）
- 位置：`apply_school_same`（`family_agent.py:3416-3450`）写 `school_duplicate_of` + `school_same_receipt`，但 duplicate item 也置 `state='accepted'`；`_reuse_school`（`:2141`）对 accepted 重复项保留。任务仍只 1 条（本任务 publications 三条正确），但 item 层重复、且 m11 的「不另加题」只落在 duplicate item 上没进任务 action。
- 建议：duplicate receipt 用独立状态（如 `accepted_receipt`）或把补充约束并进 canonical task。

### B7. selection 批次超时/截断风险（可用性）
- 位置：`family_agent.py:7939` `_chat_json(..., timeout=45)` + `family_llm.py:675` `output_tokens=6000`；重试由 `_job`（`family_agent.py:2343`）管理，`attempts>=MAX_ATTEMPTS(3)` 后不再领取。
- 实测：6 条消息一批 20.86–36.91s（冒烟期另见 44.56s），首轮冒烟 2/4 次失败（`LLMDraftError('模型尚未完成草稿，请缩小本次资料范围后重试')`、`LLMDraftError('模型服务连接失败或超时；原件未改动，请重试或手动记录')`）；若 3 次耗尽，该批消息会永久 `processed=0`（无自动重投）。
- 建议：按消息条数/字节下调批次（如 4 条）、或把 selection timeout 调到 60–90s；给 `processed=0 且 job 已耗尽` 的消息一个重投/告警路径。

### 观察（非 bug，需产品/显示口径确认）
- `calendar_snapshot` 11-04 与 11-05 返回完全相同的 12 张卡，产品没有「今天必须做」的计数/分组字段，ORACLE 的 today / future / carry 区分只能靠 `due_on/complete_on/due_kind` 间接表达；未来项（11-05 证件照/彩笔）与 11-06 的 a-math 都混在 11-04 inbox。该问题偏投影/显示层，建议由 projection/surface 侧确认是否要按日分组与计数。

---

## 8. 口径与限制（对账公平性）

1. **附件**：FIXTURE 未给真实字节，PDF 用产品自己的页读取回执注入 FIXTURE 声明的已读文本（产品 U02 同款机制）；jpg 由夹具 patch 保持未读。因此「英语附件是否被读」测的是产品的**页回执→要求落地**链路，不是 OCR 解码能力。
2. **manual_input 拆分**：产品消息通道无 manual_input，且一 source 一 child；`qa-family-manual` 拆成两个伪源。消息级对账仍按原 source 归属（m10→child-1、m17→child-2），只影响「同一 source 多孩」这一产品能力本身的覆盖（本产品当前不支持）。
3. **review 卡**：产品对不确定项用「待核对」卡表示，不建任务。ORACLE 的 `active` 判定按「事项是否以可执行方式存在/被跟踪」，本项目把「review 卡但日期齐全」记为部分通过，并单列差异。
4. **模型非确定性**：本轮 8 次调用全部成功；同一批 6 条消息在冒烟期曾 2 次超时/未完成草稿，说明结果对批次大小与延迟敏感（见 B7）。重跑方法见 §1.5，原始返回在 `model-calls.json`。
5. 未运行任何真实家庭同步/打印/发布；未触碰私有家庭目录；未修改产品代码、ORACLE 或测试。

---

## 9. 建议 lead 的下一步派单

| 优先级 | 修什么 | 建议 owner |
|---|---|---|
| P0 | B1 跨渠道 publisher 归一 + B2 待核事项后到消息折回（同事项归并主链路，决定「多渠道通不通」） | 新开 agent 归并 owner（family_agent.py 的 `_publisher`/`_school_pending_link`/`_reconcile_school_same`/`_save`）；不适合 surface/delivery |
| P0 | B4 多日期时保 `complete_on`（今晚做 vs 周五交），防止今天必须做丢失 | 同一 owner（日期守卫）或独立日期 owner |
| P1 | B3 无日期提醒继承目标日期（m18 型） | 同一 owner（`_school_same_due`） |
| P1 | B5 split 残片清理 | 同一 owner（`_save` split 分支） |
| P2 | B7 批次大小/超时与重投（可用性） | 模型通路 owner（family_llm/`_select`） |
| P2 | 观察项：11-04/11-05 清单不按日拆分、无今日必须做计数 | projection / surface 确认 |
| P3 | B6 duplicate accepted item 状态 | agent 归并 owner（低） |

修完 P0 后建议用同一 harness 重跑（`python3 run_merge18.py 30`），预期变化：a-math 合 1 卡且 complete_on=2026-11-04、a-reading/a-english 各 1 张卡、m18 并入朗读任务、b-math 单 item、11-04 清单从 12 张降到 8~9 张。


---

# 10. 修复轮（owner 改产品代码，2026-11-04 夜）

> 本节是**改后**数字。改前数字见 §0–§9（基线快照 `run-before-fix.json`），改后为 `run-fix3-1.json` / `run-fix3-2.json`（两次连续 30-tick 真跑数字完全一致）。
> 改的范围：只改 `family_agent.py`；`family_llm.py` 保持 HEAD 无 diff；ORACLE、验收材料、既有测试断言均未动；5 个 Python 套件仍是基线那 3 条失败（名单逐字一致）。私有 `model.json` 未改。

## 10.0 交付 sha1

| 文件 | sha1 | 说明 |
|---|---|---|
| `family_agent.py` | `4cd8383b025bed6047851e838256c5045336bf5b` | 本轮全部修复 |
| `family_llm.py` | `bf2c974be34b6460d980d18b8e2ffc1498611be1` | 与 git HEAD 一致（未改） |

## 10.1 本轮修的 8 处（reviewer F1/F2/F3 + R1 已一并修掉）

| 编号 | 问题 | 位置（family_agent.py） | 改法 |
|---|---|---|---|
| B1 | 同一老师跨 QQ/微信被当成两个 publisher，同事项永不归一 | `_publisher` :1218 → 新增 `_publisher_cross_channel` :1233 | 只对「同孩子 + 不同 platform + 同显示名且显示名像老师（含 老师/教师/班主任/园长）+ 两边都有 sender_id」归一成一个发布者哈希；同源/同平台/无 sender_id 一律保持原生哈希（既有 R16 身份测试全过） |
| B2 | 后到的补充/提醒只挂链接、不折回原卡，留孤儿待核卡 | 新增 `Store._school_fold_pending` :2564（在 `_save` 插入循环里）＋ `_fold_school_follows`（`run_once` 里 `_refresh_school` 前） | 程序已证明同一事项的后续消息：目标卡还在待核 → 合并 body 行与日期、原文进 `plan.school_folded`；目标已成本任务 → 该行 accept 到原任务、正文行并入 `manual_tasks.action`、原文逐字保留在行内；**不改任务 source**（避免 family_agenda 的完成日回退被提醒打乱） |
| B3 | 无日期提醒被日期门槛推成 review | `_school_same_due` :3207 | 提醒自身没给日期且原文没有「改/调/推迟/延后/提前/挪/换/移+到/至/为/在」→ 继承原事项日期并合并；只有真的移动日期才拒 |
| B4 | 多日期通知丢「今晚完成」，agenda.complete_on 为空 | 新增 `_school_role_quote` :4347，`_select` 内 dated_quote 选择处 | 当一条通知含多个相对日、模型给的 `dated_quote` 算不出角色日时，从被引原文里选一条「roles[1]==due 且最早日唯一早于 due」的原文作 `school_date_quote`（必须是原文子串，family_agenda 才能算 complete_on） |
| B5 | split 出一张 body 仅「美术老师今天课上说」的残片卡 | `_SCHOOL_SPLIT_REQUIREMENT` :76、新增 `_SCHOOL_SPLIT_SUBJECT` :78，判定处 :8272 | 只有「无动作词 + 无学科标签（`语文：` 这种标签形式）+ 无《》/数字」的纯引子才丢；其余一律保留落卡（reviewer F2：预习/口算这类 formed 片段不再被吞） |
| F1 | `_SCHOOL_MOVED.search(said)` 崩溃（`_SCHOOL_MOVED` 是 raw string，:3885） | :3209 | 改为 `re.search(_SCHOOL_MOVED,said)`；并全文件 AST 扫过所有 `str` 常量上的 `.search/.match/.fullmatch/.finditer/.sub/.split` 误用，**0 处残留** |
| F3 | 跨渠道折回后 publisher 变成 `''`，该老师后续消息再也折不回 | `school_pending_targets` :2706 | `(source_id,publisher)` 二元组改为：publisher 只按**值**去重、source_id 单独判定 |
| R1 | 两张待核卡同对象（数学/语文各一张《每日练习》）时按顺序取第一张，可能串卡 | `_select` 程序证明分支 | 候选命中 >1 时不自动折回，保持各自待核并保留原文，让家长选 |

## 10.2 改前 → 改后（同一 30-tick harness、同一 18 条、同一真模型）

| 指标 | 改前（`run-before-fix.json`） | 改后（`run-fix3-1/2.json`） |
|---|---|---|
| 8 件事识别 | 8/8 都有代表卡 | 8/8 都有代表卡（每件恰好 1 张，无孤儿卡） |
| 8 件事要素+日期+状态+单卡全对 | 3/8（+主卡对共 4/8） | **5/8**（a-math、a-reading、a-art-cancelled、b-math、b-photo）；余 3 件见 §10.4 |
| 18 条消息落点 | 13/18 干净（4 条重复待核卡、1 条被拆两卡） | **18/18 干净**（0 孤儿、0 重复卡；m04/m13/m10/m18/m11 全部折回各自事项，原文在 `plan.school_folded`） |
| 同事项 8 组归并 | 4/8 完全合并 | **8/8 全部合成 1 张** |
| 跨渠道（QQ↔微信）同事项 | 1/2（a-math 裂成 2 卡） | **2/2**（a-math m01+m09+m04 一任务；b-math m03+m16+m11 一任务） |
| 11-04 清单张数 | 12 张 | **8 张**（≤9 达标；5 任务 + 3 待核/取消卡） |
| selected_day：active/cancelled/today_required/future_only | 7 / 1（正确） / 成任务 3/5 / 成任务 1/2 | 7 / **1 正确（美术带落叶整项取消，不再当要做）** / 成任务 **4/5** / 成任务 1/2 |
| 附件 2 份 | 2/2 | 2/2（英语 PDF 已读、三行要求逐条进任务；语文 jpg 未读、卡上写未读/未知、未编造） |
| 模型调用 | 8 次（7 selection + 1 school_task），**192.9s**，全成功 | 8 次全成功，**约 30.3s**（light reasoning effort=none，见 10.3） |
| 稳定性 | 单次 | **两次连续 30-tick 真跑数字完全一致**（5 task / 16 item / 8 卡 / 18 processed） |

## 10.3 每次 selection 的耗时与 output token（改后第二次跑，`model-calls-fix3-2.json`）

| # | 调用 | 耗时 s | input tokens | output tokens |
|---|---|---|---|---|
| 1 | family_agent_selection（qq-a4 批1 六条） | 5.45 | 5922 | 821 |
| 2 | family_agent_selection（wx-a4 m04） | 3.23 | 5591 | 270 |
| 3 | family_agent_selection（qq-a4 批2 m13,m18） | 5.61 | 6699 | 523 |
| 4 | family_agent_selection（qq-b2 六条） | 4.56 | 5367 | 691 |
| 5 | family_agent_selection（wx-b2 m11） | 2.58 | 5926 | 266 |
| 6 | family_agent_selection（manual-a m10） | 2.51 | 6121 | 274 |
| 7 | family_agent_selection（manual-b m17） | 2.09 | 5953 | 181 |
| 8 | family_school_task（m05 英语 brief/accept） | 4.30 | 6734 | 433 |

- 全部 selection 2.1–5.6s、max output 821 tokens（6000 上限的 14%）：**6000 保留、9000 已回退**，不是用超时换容量。
- timeout=45 未改（test_daily_list_frozen.py:1764 断言）。
- 关键使能项：`FAMILY_LLM_LIGHT_REASONING_EFFORT=none`（lead loopcheck 发现；由 harness `run_merge18.py` 在 exec 前 export，私有 model.json 未改）。

## 10.4 仍未达成 / 出界（不藏）

1. **b-chinese（未读附件）仍是待核卡，未成本任务**：ORACLE 期待 active_with_material_gap 任务。现状卡上有今晚完成/家长签名/明早交、due 11-05、complete_on 11-04、写明附件未读，但不进 `manual_tasks`。→ 属 lead 未授权的 #6（未读附件事项可否带缺口成任务）。
2. **b-art-oral（彩笔）仍是待核卡**：孩子口述经家长补录，产品判 reference/review（不冒充群消息，这一点与 ORACLE 一致），但不进任务；11-04 清单里显示为 todo 待核。→ 同属 #6。
3. **a-english 差一句**：m13 的「不用在群里发照片」未进任务 action（m13 原文已在 `plan.school_folded` 逐字保留；折回发生在该卡 accept 之前，accept 时模型给的 goal 覆盖了已合并的 body 行）。→ #2 残余，可下一轮把 folded 行在 accept 后并入 action。
4. today_required 成任务 **4/5**（第 5 件即 b-chinese 待核卡）。

因此严格全对 5/8 而非 lead 目标 7/8：差的 3 件里 2 件卡在 #6、1 件是 #2 残余。

## 10.5 #7（本轮按要求未改）最小复现与行号

- 现象：模型调用失败（LLMDraftError）→ `Store._fail`（:2596）把 `agent_jobs.attempts+1`、`next_try` 设为 5 分钟后；`MAX_ATTEMPTS=3`（:28）。3 次耗尽后 `_job`（:2392）对同一 fingerprint 永远返回 None（:2399），但该批消息 `processed=0` 留在库里，`_school_pending_batches` 仍把它们取出来，于是每 tick 都重新尝试同一批、永远失败——消息永久 unprocessed，且没有对用户可见的终态。
- 已复现：改前 9000/timeout45 那一轮（`run-after1.json`）m13/m18 两条 unprocessed，`agent_jobs` 行 `attempts=3, done=0, error='模型整理未成功：…自动尝试共3次，达到自动重试上限后需人工重试；原始资料保留。 将按计划自动进行第2次尝试。'`。
- 行号：`MAX_ATTEMPTS` :28；`_job` :2392（耗尽判定 :2399）；`_fail` :2596–2608；`run_once` 的 source 批次循环 :10180 附近；`_school_pending_batches` 只按 `processed=0` 取批（:1292 附近）。
- 建议（不改本轮）：耗尽后给该批一个 terminal 状态（如需人工重试的 job 状态）或对该批消息标记「需人工重试」并跳过，避免同批无限重取；并把错误反映到 source 状态。/§10


# §11 M1–M3（reviewer 第 2 轮 BLOCK 项）+ G1-1/2/3 收尾

## 11.1 本轮代码 sha1 与改动面

| 文件 | sha1 | 说明 |
| --- | --- | --- |
| `family_agent.py` | `1756bf3830261e688d33b2b4105374a5a86330f4` | 本轮唯一产品改动（420+/18−） |
| `family_llm.py` | `bf2c974be34b6460d980d18b8e2ffc1498611be1` | = git HEAD，无 diff（9000 已回退、6000 保留） |
| `test_school_fold_visibility.py` | `3bdfd53a4ab25e90a50ea800b44796f85d90411c` | 新增回归，13 条（M3） |

## 11.2 M1–M3 改了什么（对应 reviewer 根因）

| 项 | 改动 | 位置 |
| --- | --- | --- |
| M1-a | `_school_folded_originals` 新增：把 `plan.school_folded[].originals` 全量取出（ref/text/change），四种 change 都读；`_school_folded_lines` 现在：same 原句、append 前缀「后到补充原文：」、update 前缀「后到更正原文：」、cancel 前缀「取消依据：」，保留句末标点。 | family_agent.py:3214–3252 |
| M1-b | `_school_fold_pending`：body 对四种 change 都调 `_school_folded_body` 合并；due 规则改为 cancel→`''`、update/append→`_school_late_due`（先取 `_school_role_days` 的 hand-back 角色日；只有原文含「交回/交给/上交/带来/带到」才用 deadlines 最大值；发送日与纯「今晚完成」永不成为新截止）。 | :2598–2640、`_school_late_due` :3255 起 |
| M1-c | `_school_accept_fold`：accept 后把 fold 行补进 `manual_tasks.action`；same/append 的 ref+原文按既有格式进 `source`（会被 agenda publications 引用）；update/cancel 以「后到原文（更正/取消依据，不进本事项日期判断）：message:…」进 `source`，**不**以 `message:` 行首出现。 | :3320 起 |
| M1-d | `_fold_school_follows`：后到行携带 change；action 合并 body 行；source 追加原消息；update 更新 `manual_tasks.due`（并同步 item due）；cancel 清空 due。 | :9820 起 |
| M2 | 后到 ref 同时保留在 `plan.school_folded[].refs/originals`，并在 accept 时写进 task.source（同上：same/append 为引用块，update/cancel 为注明行）。 | 同上 |
| M3 | 新回归 `test_school_fold_visibility.py`：4 类 change 的正文行、`_school_folded_body`、`_school_late_due`（改期/同日/无日）、`_school_fold_pending` 的 body/due（含 cancel 清 due）、`_school_accept_fold` 的 action/source/幂等，共 13 条，函数级、不跑模型。 | 新文件 |

设计取舍（reviewer 请重点看）：**为什么 update/cancel 的 ref 进 source 但不作为 `message:` 引用行**——`family_agenda.py:1239` 用 `task['source'].splitlines()` 中所有 `message:` 行重建「本事项的消息集合」，再看一天的角色（`_school_role_days`，:872）。m04 是「1—4题」的旧范围提醒，一旦作为引用行进入 a-math 的 source，`_school_role_days` 返回 None，a-math 的 `complete_on` 会从 2026-11-04 掉回空（本轮已实测复现并回退该做法）。因此更正/取消以注明行保留（人能读到该 ref），但不参与日期角色读取；其正文行已在 action 里逐字可见（M1 可见性不丢）。

## 11.3 G1 验收 8 条逐条证据（run-m2b.json）

1. **11-04 清单 ≤7 张、0 重复 0 孤儿**：inbox 8 行 = **7 张 active**（5 今天必做 + 2 以后）+ **1 张取消卡**（ORACLE 要求保留的同一张取消卡，不计入 active）。active 7 = 目标 7。
2. **today_required 成任务 5/5**：a-math（due 11-06 handback complete 11-04）、a-reading（11-04 deadline）、a-english（11-05 deadline complete 11-04）、b-math（11-05 handback complete 11-04）、b-chinese（11-05 handback complete 11-04）。
3. **future_only 2/2**：证件照（11-05 arranged）、彩笔（11-05 arranged）。
4. **8 组同事项 8/8 合成 1 卡/1 任务**：a-math[m01,m09]+m04 折入；a-reading[m02]+m18+m10 折入；a-english[m05]+m13 折入；b-math[m03,m16]+m11 折入；b-photo[m06,m14]；b-chinese[m08,m15]；a-art-cancel[m07,m12]；b-art-oral[m17]。
5. **18 条仍 18/18 干净**：processed 18/18；verify_g1.py 71 条断言 0 失败（matters 要素/日期/状态、落点、8 组、selected_day、附件、调用）。
6. **a-english 正文含 m13 逐字**：`补充今天英语《每日练习》：完成后放英语夹里明早带来，不用在群里发照片。`（action 末行；source 中 m13 也被引用）。
7. **取消/附件结论不变**：取消卡「美术：带两片落叶（已取消）」，body 写明原要求+取消+不用带；b-chinese 正文「内容待补：附件尚未读取（识字小卡.jpg）；具体题目与要求待读到附件后补充。」，无编造题号；`final.drafts=[]`（jpg 未读）。
8. **5 套件 + 真实单渠道回归**：5 套件 176 tests（含新增 13）仍**只有基线 3 条失败**（名字逐字一致）；`work/realrun` 6 条单渠道 6 task/1 call/0 failed（`FAMILY_LLM_LIGHT_REASONING_EFFORT=none`）。

### G1-2 b-chinese 任务文本（逐字）
- title：`语文：完成《识字小卡》练习`
- action：`完成附件《识字小卡》上的练习。
完成后请家长在卡片下方签名。
明早交给语文老师。
提交要求：明早交给语文老师，卡片下方需家长签名
内容待补：附件尚未读取（识字小卡.jpg）；具体题目与要求待读到附件后补充。`
- due：2026-11-05，agenda：due_kind=handback、complete_on=2026-11-04。

### G1-3 彩笔任务文本（逐字）
- title：`明天带一盒彩笔`；due：2026-11-05（arranged）
- action：`明天（2026-11-05）带一盒彩笔。
来源：孩子口头转述老师要求（口头补录，虚构孩子乙转述）；群内无对应通知，待与老师核实。`

## 11.4 连续两次跑的数字与调用表（run-m2a / run-m2b）

| 指标 | 第一次 | 第二次 |
| --- | --- | --- |
| manual_tasks | 7 | 7 |
| agent_items（school） | 16（15 school + 1 goal 差额见注） | 16 |
| 11-04 inbox 行 | 8（7 active + 1 取消卡） | 8 |
| processed | 18/18 | 18/18 |
| failed | 0 | 0 |
| 模型调用 | 8 全成功 | 8 全成功 |
| 8 组单卡 | 8/8 | 8/8 |
| today / future | 5 / 2 | 5 / 2 |

注：16 个 items = 11 个 school 行 + 5 个 goal-* draft 行（学习目标草稿，非事项）；school 行里 8 accepted（含 3 张已折入同一 task 的重复 accepted 行）+ 1 cancel pending。

| # | 调用 | 第一次耗时/输出 token | 第二次耗时/输出 token |
| --- | --- | --- | --- |
| 1 | selection（qq-a4 6 条） | 5.55s / 827 | 6.42s / 863 |
| 2 | selection（wx-a4 m04） | 2.46s / 263 | 2.77s / 266 |
| 3 | selection（qq-a4 批2 m13,m18） | 5.71s / 505 | 3.90s / 526 |
| 4 | selection（qq-b2 6 条） | 5.57s / 728 | 5.03s / 687 |
| 5 | selection（wx-b2 m11） | 2.51s / 263 | 2.34s / 266 |
| 6 | selection（manual-a m10） | 3.59s / 272 | 3.36s / 279 |
| 7 | selection（manual-b m17） | 2.45s / 187 | 2.19s / 184 |
| 8 | family_school_task（m05） | 4.35s / 439 | 3.33s / 436 |

- 两次的 8 项数值、7 个任务 id/due/complete/publications、inbox 8 行签名全部一致；正文措辞随模型有小抖动（如取消卡标题「带两片落叶（已取消）」的修饰语），不改变任何日期/状态/归并。
- 归档：`run-m2a.json` / `run-m2b.json` / `model-calls-m2a.json` / `model-calls-m2b.json`；verify 输出 `g1-verify.json`（71/71）。

## 11.5 仍未达成（不藏，均属 lead 已声明的不动项或口径差异）

1. 彩笔任务标题为「明天带一盒彩笔」，未强制加「美术：」前缀（模型给的 title 无科目标签；但正文与来源标注口头补录）。ORACLE 标题关键词「带一盒彩笔」「明天」均命中。
2. 取消卡标题/正文措辞每次略有差异（语义不变：已取消、不用带）。
3. `family_agenda.py` 的「今日清单」仍不区分今天必做/以后（本次按 due/complete 口径核；该文件是他人写范围，未动）。
4. reviewer M4（publisher 身份只用显示名+child，建议纳入 sender_id 关系）按 lead 指示本轮不做，记入 313。

## 12. reviewer r3 的 B1–B4（最后一轮）+ demo 快照交付

### 12.1 代码 sha1（本轮）

| 文件 | sha1 | 说明 |
| --- | --- | --- |
| `family_agent.py` | `517b7517f91d9bc0e08e0a0b6b806f50f54e5d77` | B1–B4 + 可见行带发送时刻 |
| `family_llm.py` | `bf2c974be34b6460d980d18b8e2ffc1498611be1` | = git HEAD，无 diff |
| `test_school_fold_visibility.py` | 见文件（21 tests） | 新增/重写，untracked（仓库 .gitignore `/*`） |

### 12.2 B1 多行后到原文逐行可见（原来只取最后一行）

`_school_folded_lines` 现在对每条后到原文先剥掉「来源 · ISO 时间」横幅，再**按 `\n` 逐行**切句、按原顺序加标签去重追加；`_school_accept_fold`（accept 后 action）与 `_school_fold_pending`（待核卡 body）走同一函数。

逐字证据（`_school_folded_lines` 实跑）：

```
原文: 更正：数学《每日练习》第26页只做第1—3题。\n明天早上交回。
输出:
  后到更正原文（2026-11-04 16:00）：更正：数学《每日练习》第26页只做第1—3题。
  后到更正原文（2026-11-04 16:00）：明天早上交回。
```

即「只做第1—3题」与「明天早上交回」都在，顺序保留，不再丢第一行。

### 12.3 B2 改期措辞直接解析成新截止

`_school_late_due(originals)` 去掉死参数 `old_due`；先按 `_school_role_days` 取角色日；否则命中 `_SCHOOL_MOVED_DAY`（改到/改为/改至/改成/推迟到/推迟至/延迟到/延到/延至/顺延到/延后到/挪到/调到/调整到/提前到/提前至）时，取标记后到句末的片段与原文一起跑 `family_agenda.deadlines(...)` 取最大日期；再否则仅在含交回类动词时取 deadlines 最大。

逐字证据（实跑）：

```
改到11月10日交。   -> 2026-11-10
推迟到11月10日交。 -> 2026-11-10
改为11月10日交。   -> 2026-11-10
改到11月10日。     -> 2026-11-10
今晚完成，周五交。 -> 2026-11-06（原行为保持，纯「今晚完成」不当新截止）
```

### 12.4 B3 两条路径统一「非行首 note」引用（complete_on 不再被打空）

- accept 路径与 `_fold_school_follows` 现在共用 `_school_fold_note(...)`：`后到原文（更正/取消依据，不进本事项日期判断）：2026-11-04 16:00（message:…）「原文」`，**不以 `message:` 开头**，因此不进 `family_agenda.py:1239` 的引用集合重建；same/append 仍用 `ref\ntext` 引用（它们本来就是该事项自己的消息）。
- 家长可见性：卡片正文（action）里出现 `后到更正原文（2026-11-04 16:00）：…` 带时间与原文；任务来源里保留整段 note。
- 真跑逐字证据（`run-fix5-1.json`，数学任务）：

```
action 末行：
  后到更正原文（2026-11-04 16:00）：再提醒今天那份数学《每日练习》：第26页1—4题，今晚做、签字，周五交。
source 末行：
  后到原文（更正/取消依据，不进本事项日期判断）：2026-11-04 16:00（message:qa-wx-a4:h18-m04）「再提醒今天那份数学《每日练习》：第26页1—4题，今晚做、签字，周五交。」
publications:
  message:qa-qq-a4:h18-m01, message:qa-qq-a4:h18-m09   （m04 不在引用里）
agenda.complete_on: 2026-11-04（未被 m04 打空）
```

### 12.5 B4 加固

`family_agent.py:5510` 的 `_school_role_reselect` 排除元组加入 `'school_folded'`，避免它重写 body 时绕过 `_school_folded_body`。

### 12.6 回归与两次跑

- 5 套件 + 新 fold 测试：`Ran 184 tests, FAILED (failures=3)`，仍是基线 3 条（`test_a_later_parent_edit_after_the_confirmed_correction_still_comes_first`、`test_a_parent_note_under_an_accepted_duplicate_append_key_is_still_the_parent_choice (use_duplicate_key=False)`、`test_unknown_changed_cancelled_conflicting_or_borrowed_days_stay_unknown`）。日志 `/tmp/suites_fix5.log`。
- 两次连续 30-tick 真跑（`run-fix5-1.json` / `run-fix5-2.json`）：均为 **7 task / 16 item / inbox 8 / 18 processed / 8 calls 全 ok**；7 个任务 id 集完全相同，inbox 行签名一致（仅英文标题措辞抖动「并明天带来」vs「并放入英语夹」，日期/状态/归并不变）。
- 耗时/输出 token（run 1）：5.48/2.71/4.37/4.51/2.99/3.01/2.34s + school_task 4.11s。

### 12.7 demo 快照（lead m00974 A/B）

- 路径：`work/merge18/demo-snapshot/`（`家庭运行规则.md`、`data/agent.json`、`data/family.sqlite3`、`data/uploads/` 2 份附件、`README.txt`、`snapshot-manifest.txt`）。全虚构；不含 model.json/密钥/脚本。
- sha1（manifest 全量）：`data/family.sqlite3 4834d4f36a29c3282c8f6d5e546d79d5177d063b`、`data/agent.json 5ab4a969f93529fe63a7f85c99322560d6ca4f77`、`家庭运行规则.md ae72795cd96bef7ee3ad06bbba01e744e6bb6dfb`、两份附件 `669e9208…`/`e0ce23ea…`、`README.txt ec86b598…`。
- 打开方式与注意事项（app.py 只认 `PORT` 不认 `--port`、只从源码目录读 `家庭运行规则.md`）写在 `README.txt`。
- 自检脚本 `work/merge18/verify-demo.sh`：起服务 → 两个孩子的 `/api/day?day=2026-11-04` → 断言 8 行 / 5 个今天必做 / 2 个明天带物（2026-11-05）/ 1 张取消卡 / 8 组各 1 行 / 每条消息唯一落点。实跑输出：

```
OK rows=8 today=5 future=2 cancelled=1 matters=8/8
today: 英语：完成《每日练习》并明天带来 / 数学：完成《每日练习》第26页第1—3题 / 朗读《风经过小巷》第2、3自然段 / 语文：完成《识字小卡》练习 / 数学：完成《计算小卡》第4页1—6题
```

### 12.8 未动项

#7（attempts 耗尽后消息永久 unprocessed）未改，最小复现与行号见 10.5；ORACLE、验收材料、既有测试断言均未改；`family_agenda.py` / 前端文件未动。

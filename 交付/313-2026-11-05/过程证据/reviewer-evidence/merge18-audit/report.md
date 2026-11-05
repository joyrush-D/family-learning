# merge18 独立代码审计报告

- 审计对象：`family_agent.py` sha1 **`de6859a3454b0ee01bc21b5f7a38c7faf9552d98`**（build 311 快照；`work/deliverable/证据/源码版本-311.txt` 记录，`work/deliverable/证据/fix.patch-311` 可重建）
- 基线 HEAD `58973a6`；重建树 `/tmp/merge18_audit`（`git archive HEAD` + `patch -p1 < fix.patch-311`，EXIT 0，sha1 校验一致）
- 注意：仓库当前磁盘上的 `family_agent.py` 已是更新的 `3118b674…`（+201 行，23:41），**同一下方 L3205 bug 仍在**（行号 +4）。本报告结论针对 de6859a3。
- 方式：只读代码 + 函数级探针（内存 sqlite，全虚构数据，不跑模型、不改产品源码）。
- 探针脚本：`work/reviewer-evidence/merge18-audit/probes.py`；原始输出 `probes-out.txt`（`has_errors` 为空；脚本头部打印被审 sha1）。
- 约束：只评代码正确性，不评 merge18 的 8 件事数字结果。

## 结论：BLOCK

三处必须改（F1 硬崩溃 / F2 静默丢要求 / F3 折叠后 publisher 丢失导致后续无法归并），另 3 条风险（R1 待核卡多卡同对象时选错、R2 折叠后截止日/标题陈旧、R3 跨渠道身份只凭显示名）。

## 一、五处改动语义判定

| 改动 | 判定 | 依据 |
|---|---|---|
| 跨渠道发布者归一 `_publisher_cross_channel` | 方向正确，身份证明偏弱（R3） | 同 child、跨平台、同显示名且对端有 sender_id → `publisher:hash(sender,child,name)`；不再要求 sender_id 相同 |
| 待核补充折回 `_save`/`_school_fold_pending` | 可用但有 R2 | 只追加 body 缺行与 evidence，`due=row['due'] or item['due']`，标题/状态/complete_on 不动 |
| `_reconcile_school_same` 等改用跨渠道 publisher | 正确 | 所有调用点已切换（`_save`/school_targets/school_pending_targets/`_school_late_shared`/`_reconcile_school_same`/`_recheck_school_history`/`_recover_school_pending_relations`/`run_once`） |
| 无日期提醒继承 `_school_same_due` | **F1 崩溃** | L3205 `_SCHOOL_MOVED.search(said)`，而 `_SCHOOL_MOVED` 是 raw string（L3881） |
| `complete_on` 保留 | 未改动即保留 | diff 无 `complete_on` 行；fold 不写该列；`_one_pending_affair` 只把它抄进 `version.previous` |
| split 残片过滤（新） | **F2 静默丢要求** | L8264 词表白名单；formed 提案是唯一载体 |

## 二、必须改（BLOCK）

### F1 `_school_same_due` 把 raw string 当正则用 → AttributeError，整批不存卡

- 输入：`title/due` 卡截止 `2026-11-06`，提醒正文 `明天交`（声明 11-05，且当前时间晚于原截止），或正文 `改到11月10日交`。
- 实际：`AttributeError: 'str' object has no attribute 'search'`（`family_agent.py:3205`）。
- 期望：返回 review 理由（HEAD 版本对这两种输入都返回 `'提醒的日期与原事项不一致…待核对'`），或按 `_SCHOOL_MOVED` 语义给出「改到另一天」理由。
- 影响：`run_once` 只捕获 `(LLMDraftError, AgentError, ValueError)`（L10305），AttributeError 逃逸 → 该批消息**不会落卡**；`_reconcile_school_same` L3459/L3461/L3530 也会被炸。触发面是「同日/跨日用文字改期」这种真实形状（测试夹具里已有 `更正：…改为后天交。`）。
- 修法：`re.search(_SCHOOL_MOVED, said)`；顺带静态扫一遍其它 `_SCHOOL_*` 常量（本文件仅此一处用错，其余都是 `re.search(const, …)`）。

### F2 split 残片白名单把「已形成的独立要求」整条丢掉

- 输入（消息原文）：`数学：口算第12页第1—3题。\n语文：预习《成长手册》第3页。`
- `_school_separate_outcomes` 实际：返回 2 个 proposal，`marks=[1]`（第二个是 formed），formed 的 `title=语文：预习《成长手册》第3页`、`goal` 同文。
- `_SCHOOL_SPLIT_REQUIREMENT.search(title+'\n'+goal)` = None（`预习` 两个字都不在白名单）→ `_select` L8264 `continue` 跳过该卡。
- home 卡 `goal` 仍只有 `完成口算第12页第1—3题。`（该要求已在 L982 从 home 卡剥掉）→ **语文要求整条消失**，无任何卡片承载。
- 期望：formed 片段必须保留（原卡 + 待核或独立卡），不能静默丢。
- 修法：白名单只应拦截「纯引子/纯对象名」片段，不应要求动词命中；改为「片段 title/goal 去掉引子后仍含对象名《…》/数字/时间/否定词之一 → 必须保留」，否则落 review 而不是 `continue`；或对 formed 片段一律保留并在 `_one_pending_affair` 里挂到原卡 notice。

### F3 折叠后 `(source_id,publisher)` 二元组多于一个 → publisher='' → 后续同类通知永远链不上

- 输入：待核卡 evidence = `message:s-wechat:m1` + `message:s-qq:m3`（经跨渠道折叠后必然跨源），再来一条合法后续通知。
- 实际：`school_pending_targets` 里 `publishers` 是 `(source_id, publisher)` 的集合，len==2 → `source,publisher=('','')`；`_school_pending_link` 首行 `not target.get('publisher')` → 返回 `None` → **建重复待核卡**而不是折回。已接受任务侧同理 `append_eligible=bool(publisher) and …` → False，追加被禁用。
- 期望：跨渠道 publisher 本来就与 source 无关，折叠后仍应能归并。
- 修法：`publishers` 只收集 `_publisher_cross_channel` 的值（set 去重后取唯一值）；`source_id` 单独取「首个/最新 evidence 的 source」而非参与唯一性判定。

## 三、风险（建议一并处理）

- **R1 待核卡多卡同对象时选错（串）**：两张 pending 卡（数学/语文《每日练习》）时，`_school_pending_link` 对两条都返回命中；`_select` L8125-8133 取**第一个**命中卡（列表较新者），没有 `_school_same_peer` 式歧义判定，也没有 subject/purpose 比对。建议：要求唯一命中，否则 `review`。
- **R2 折叠后截止日/标题陈旧**：`_school_fold_pending` 用 `row['due'] or item['due']`，`UPDATE` 也不覆盖 title。输入「更正：只做第1—3题，改到11月10日交。」→ body 追加了更正行，但卡 `due` 仍 `2026-11-06`、标题仍「第1—4题」。展示层会读到过期截止日/过期范围。建议：存量值存 `school_unadopted_due`/`school_unadopted_title` 并置 review 理由（同类路径的既有做法），至少别静默保留旧值。
- **R3 跨渠道身份只凭显示名**：同一孩子两个平台上都叫「王老师」但 sender_id 不同 → 仍合并成同一 publisher（hash 只含 sender 名）。若两科老师同姓同显示名且对象重名，存在串卡可能。建议加「同名 + 同平台族签名/同班级」之类的更强证据，或命中时置 review。
- **R4 `_school_same_brief` 新增「同名对象」兜底放宽**（代码阅读，未单独做探针）：`named=_school_named_objects(brief.title+goal) & _school_named_objects(facts)`；当通知原文与卡内对象名无交集时，模型摘要里的《…》也能证明同一对象。同名不同科（数学/语文《每日练习》）时，这层放宽与 R1 的「首个命中」叠加，会放大串卡概率。建议：named 命中仅在有其它独立证据（发布者/日期/学号）时生效。
- **R5 折叠的隐式前提**：`_school_fold_pending` 要求目标卡仍 `state='pending'`；若两条通知之间卡已被接受/转 ready，`_save` 的 fold 返回 False 后走普通路径，可能新建一张同事项卡。是否可接受取决于产品口径，建议 fold 失败时至少留一条 review 理由，避免「静默多一张卡」。

## 四、确认无问题的点

- 跨孩子不串：`_school_fold_pending` 的 SELECT 带 `child_id=?`；publisher hash 含 child；同一显示名在两个孩子下 publisher 不同（P2b PASS）→ 未见跨孩子合并路径。
- 取消通知不会被吃掉：折叠后卡 `state='pending'` 不变，body 保留取消行，`family_agenda._one_pending_affair` 以 `version.previous` 保留原卡 title/lines/due_on/complete_on，并给出「含取消或停止原要求」理由（P6）。
- 同日提醒不误报：`due==old` 时 `_school_same_due` 返回 `''`，不触发 review（P1 的同日分支）。
- 显式改期措辞（改到/推迟到/延后到…）的 review 提示语义正确（修掉 F1 后应当仍返回该理由）。
- `complete_on` 在本次 diff 中未被改动，折叠/分组路径只读不写。

## 五、证据清单（同目录）

- `probes.py` / `probes-out.txt`：P1–P7 全部复现（含每个 case 的 got/expected 与 `[FAIL]`/`[PASS]`）。
- `family_agent.de6859a3.diff`：被审版本的 321 行 diff（20 hunks）。
- 重建：`git archive 58973a6 | tar -x -C /tmp/merge18_audit && patch -p1 < work/deliverable/证据/fix.patch-311`。

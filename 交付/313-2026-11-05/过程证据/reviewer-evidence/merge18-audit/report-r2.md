# merge18 第 2 轮复审：`family_agent.py` sha1 4cd8383b（只审代码，不审数字）

- 复审对象：`/Users/joyrush/.local/share/family-learning/public-integration-20260926/family_agent.py`
  sha1 `4cd8383b025bed6047851e838256c5045336bf5b`（审前=审中工作副本，`family_llm.py` = HEAD `bf2c974b`，未改）。
- 方法：只读；`probes-r2.py`（虚构数据、无模型、无产品库）→ `probes-r2-out.txt`；静态扫描源码；对照上一轮 sha1 `de6859a3` 的 183 行 diff。
- 注意：审后工作副本已被推进到 `c28b93e0`（新增 `_school_folded_lines/_school_folded_body/_school_accept_fold` 等）。第 5 项在 `c28b93e0` 上单独复验：`probes-folded-current.txt`、源码 L3219-3245 / L3298-3306。**本报告的 BLOCK 结论对两个 sha1 都成立**，范围见 M1。

## 一、五项结论

| # | 项目 | 结论 |
|---|---|---|
| 1 | F1：`_SCHOOL_MOVED` raw string 当正则 | **PASS** |
| 2 | F2：split 残片白名单收窄 | **PASS** |
| 3 | F3：跨渠道折叠后 publisher 去重 | **PASS** |
| 4 | R1：多候选歧义不静默并入 | **PASS** |
| 5 | 新增：折叠后到原文的可达性 | **FAIL → BLOCK** |

### 1) F1 PASS
- 4cd8383b 中 `_school_same_due` 的差异日分支已是 `if due and old and due!=old and re.search(_SCHOOL_MOVED,said):`（当前副本 L3212）；`_school_pending_link` 中原有的 `re.search(_SCHOOL_MOVED,said)`（L2772）未受影响。
- 静态扫描：模块内 `_SCHOOL_*` 常量 23 个 compiled + 82 个 raw string；`NAME.search/match/findall/sub/split(` 形式的「raw string 当正则」误用 **0 处**。
- 行为：`_school_same_due('2026-11-05', 卡 due=11-06, ['明天交'])` → `''`（不再抛异常）；`'改到11月10日交'` → `'提醒把原事项改到另一天，是否同一次待核对；原事项和提醒原文都保留。'`；同日 → `''`。

### 2) F2 PASS
- 谓词为三条件：`_SCHOOL_SPLIT_REQUIREMENT`（动作词词表）或 `_SCHOOL_SPLIT_SUBJECT`（行首学科标签）或 `[《》0-9]`；三者全无才 `continue`。
- 边界输入：`语文：生字`→保留（学科标签）、`美术老师今天课上说。`→丢弃（纯引子）、`综合：带跳绳`→保留（动作词/学科）、`数学：第3页第2题`→保留（学科+数字）、`《成长手册》第3页的自我评价`→保留（《》/数字）。
- 端到端：上一轮被吞的 `_school_separate_outcomes` 形成残片 `语文：预习《成长手册》第3页`（旧白名单无「预习」而丢）现在**保留**。F2 修好。

### 3) F3 PASS
- 折叠卡（证据 `message:s-wechat:m1` + `message:s-qq:m3`，同一林老师跨渠道）→ `school_pending_targets` 返回 `publisher='publisher:0fe4951aa5a670…'`、`source_id=''`；第三条通知 `_school_pending_link` → 成功折叠（`{'item_id':'p-folded','change':'same','publisher':'publisher:0fe4951…'}`）。
- 不同发送者（林老师 + 王老师）→ `publisher=''`、`source_id=''`、link `None`：两个不同老师不会被合成一个身份，也不会静默并入。
- 说明：身份仍以「显示名（去空白）+ child_id」为哈希，`sender_id` 不参与；这是上一轮 R3 的既有设计，本轮未变。

### 4) R1 PASS
- 两张待核卡（数学/语文同含《每日练习》）对同一通知 **都** 能证明（`per-card proof: [('pending:p-math', True), ('pending:p-chinese', True)]`）——歧义真实存在。
- 新 guard `hits=[...]; if len(hits)==1: pending_target,pending_link=hits[0]` 命中 2 时保持各自成卡（通知不并卡），不会「先到先得」并入错误卡；模型显式指名 `pending:X` 时仍按证据并入（不会造成新的「永不合并」）。
- 未发现「该省不省」以外的副作用。

### 5) 新增覆盖点 FAIL（BLOCK）
`_school_fold_pending`（4cd8383b；当前副本 L2562-2596）在后到通知折回待核卡时：
- 只把后到正文并入 `body` 当 `link.get('change')=='same'`；`append/update/cancel` 三类 **不并入** `body`。
- `UPDATE agent_items SET body=?,due=?,plan=?,updated=?` 不再写 `evidence`（上一轮是 `old+added`）。
- 后到原文只保存在 `plan.school_folded[].originals`；**4cd8383b 中没有任何读者**（`school_folded` 仅 2 处 writer + 1 处 `_fold_school_follows` writer，`family_agenda.py` 0 处）。
- 后果链：`pend` 态卡面（agenda 读 `body`）看不到后到原文 → 若该条被 accept，`_save` 用 `body` 写 `manual_tasks.action`、用 `evidence` 拼 `source` → 后到原文既不进任务正文也不进来源；`update` 类改期时 `due=row['due'] or item.get('due','')` 仍保留旧截止 → 卡面显示旧日期 + 旧要求。

`c28b93e0` 复验（`probes-folded-current.txt`）：
```
change='same'    folded_lines=['更正：只做第26页第1—3题，改到11月10日交']   body_after='…\n更正：…'
change='append'  folded_lines=[]                                          body_after='完成…第1—4题。'
change='update'  folded_lines=[]                                          body_after='完成…第1—4题。'
change='cancel'  folded_lines=[]                                          body_after='完成…第1—4题。'
```
即 `c28b93e0` 的 `_school_folded_lines` 明确 `if entry.get('change')!='same': continue`，只修了 `same` 一类；`append/update/cancel` 三类仍会丢后到原文（并且 `_school_accept_fold` 同样只读 `same`）。这是**新的信息覆盖点**，且正好落在 lead 让先定位的那一处。

## 二、最小证据（输入 → 实际 → 期望）

1. fold `change='update'`，卡 body `完成《每日练习》第26页第1—4题。`，后到通知 `更正：只做第26页第1—3题，改到11月10日交。`
   - 实际：卡 `body` 不变、`due` 仍 `2026-11-06`、`plan.school_folded[0].originals` 有原文但无人读；accept 后 `manual_tasks.action` 仍是旧要求。
   - 期望：卡面/任务应出现更正后的要求与日期（或至少把增量作为待核行显示）。
2. fold `change='same'`，同上：`c28b93e0` 已把后到行并入 body（PASS）；但 `evidence` 仍不记后到 ref → accept 的 `source = 'Agent建议:…' + evidence 文本` 缺后到原文。
3. `change='cancel'`：卡面仍显示“完成…”，取消语句不可见（`same` 之外全丢）。

## 三、与上一轮（de6859a3）对照
- 上一轮 BLOCK 的 F1（崩溃）/F2（split 残片丢）/F3（折叠后 publisher 丢）**均已修好**，并有探针。
- R1（浅并卡）已加 `len(hits)==1` 门；R2（改期旧 due）/R3（仅显示名身份）本轮未变，R2 在此次 BLOCK 中被再次命中（`update` 折叠不改 due）。
- 新引入的 `_fold_school_follows`（accepted 吸收 pending 通知）探针 PASS：`used=1`，任务 action 追加 `补充：第26页第1—3题拍照。`，行状态 accepted/task AGENT-1。

## 四、结论

**BLOCK**（仅第 5 项；前四项可放行）。必改项：

- **M1（必改）** 折叠后到原文对所有 `change` 类别可见：`_school_fold_pending` 不应只在 `same` 时并入 `body`；`append/update/cancel` 至少应并入正文或在卡面可读处新增“后续通知（更新/取消）”行；`update` 移动截止日时应更新卡 `due`（旧值留在 `originals` 供审计）。若改在渲染层，则 `_school_folded_lines` 不能只认 `change=='same'`。
- **M2（必改）** 后到 ref 落库：`_school_fold_pending` 的 UPDATE 补回 `evidence`（`old+added`，或单独的 `school_later_refs` 并由 accept/`source` 读取），否则 accept 后任务来源缺后到原文。
- **M3（建议）** 加最小回归：`fold(change∈{same,append,update,cancel})` × 断言 {卡 body 可见后到要求；accept 后 action/source 含后到原文；update 后 due 为新日期}。
- **M4（提示，非阻塞）** publisher 身份仅显示名 + child：同名不同老师仍可能合身份（本轮已用 `len(hits)==1` 缓解并入错误卡，但身份证据仍弱，建议后续在 `_publisher_cross_channel` 里纳入 `sender_id` 关系或人工待核标记）。

限制：未验证任何数字/UI 渲染；结论仅针对代码路径与虚构输入。探针脚本与原始输出都在 `work/reviewer-evidence/merge18-audit/`（`probes-r2.py`、`probes-r2-out.txt`、`probes-folded-current.txt`）。

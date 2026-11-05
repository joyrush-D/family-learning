# merge18 第三版独立审查（报告 r3）

审计对象（sha1 已在本机核验，全程只读）：

| 文件 | sha1 |
|---|---|
| `family_agent.py` | `1756bf3830261e688d33b2b4105374a5a86330f4` |
| `family_llm.py` | `bf2c974be34b6460d980d18b8e2ffc1498611be1`（= HEAD，本轮未动） |
| `test_school_fold_visibility.py` | `3bdfd53a4ab25e90a50ea800b44796f85d90411c` |

方法：只读代码 + 函数级/DB 级探针（全虚构数据，不跑模型、不评估任何数字）。证据：

- `probes-r3.py` / `probes-r3-out.txt`：四类折叠 → 卡 body / due；`_school_late_due` 直调；`_school_accept_fold` → `manual_tasks.action/source`；`family_agenda.metadata` 的 `complete_on` 对照。
- `probes-r3b-out.txt`：多行后到原文的 body/lines 逐段对照；`_school_late_due` 反例表；`old_due` 死参数。
- 工作树 sha1 在每轮探针前后一致（1756bf38），未修改产品源码，未 commit。

## 结论：BLOCK

两条会静默丢内容的路径（都已用虚构输入复现），另有一条不一致与两条建议：

| # | 级别 | 问题 | 结果 |
|---|---|---|---|
| B1 | **必须改** | `_school_folded_lines()` 只渲染后到原文的**最后一行**（`text.split('\n')[-1]`），append/update/cancel 三类多行更正的前几行不进卡 body / accept 后 action | 更正的「范围」句可能整句消失，卡片仍显示旧范围 |
| B2 | **必须改** | `_school_late_due()` 只认 交回/交给/交给我/上交/带来/带到；「改到11月10日交」这类**普通“交”**的改期既不走角色日、也过不了兜底动词门 → 保留旧截止 | 更正后的新截止从卡片消失（stale due） |
| B3 | 建议（一致性） | 已接受任务走 `_fold_school_follows` 时，后到 ref 以**行首 `message:`** 进 source（与 `_school_accept_fold` 的 note-only 相反），会把 `complete_on` 重置掉的场景重新引入 | 两条折叠路径行为不一致，且削弱了 lead 第 3 点声明的理由 |
| B4 | 建议（健壮性） | `_school_role_reselect` 的排除列表未含 `school_folded`，其 UPDATE（L9964）重写 body 时不过 `_school_folded_body`；当前因 `origin_basis` 不匹配而不可达 | 后续改动一旦放开 origin 校验就会覆盖折叠行 |

## 1. M1 可见性（四类 × 卡 body / accept action / source / due）

单行后到原文（`probes-r3.py` T1/T3）：

| 变更 | 卡 body | accept action | source | due |
|---|---|---|---|---|
| same | ✅ 原文行直接追加 | ✅ | ✅ 行首 `message:` + 原文 | ✅ 保持 |
| append | ✅ `后到补充原文：…` | ✅ | ✅ 行首 ref + 原文 | ✅ 保持 |
| update | ✅ `后到更正原文：…` | ✅ | ⚠️ 仅 note 行（不含原文），无行首 ref | ❌ 普通“交”改期保留旧值（见 §2） |
| cancel | ✅ `取消依据：…` | ✅ | ⚠️ 仅 note 行 | ✅ 清空 |

**B1（多行原文）**：`_school_folded_lines` 的实现是

```python
text.split('\n')[-1].strip()          # 只取最后一行
for part in _SCHOOL_FOLDED_SPLIT.findall(text):   # 只在最后一行内按 。；; 切
```

`probes-r3b-out.txt` 实测：

| 变更 | 后到原文 | 卡 body 实际 | 丢掉的段落 |
|---|---|---|---|
| update | `更正：数学《每日练习》第26页只做第1—3题。\n明天早上交回。` | `完成…第1—4题。\n后到更正原文：明天早上交回。` | **`更正：…只做第1—3题。`** |
| append | `补充：…还要写算式。\n算式写在练习册上。` | `…\n后到补充原文：算式写在练习册上。` | **`补充：…还要写算式。`** |
| cancel | `刚才带落叶那一项取消。\n不用带叶子和旧书。` | `美术：收集并带两片落叶。\n取消依据：不用带叶子和旧书。` | **`刚才带落叶那一项取消。`** |

- 后果：卡片正文仍是旧范围（第1—4题），更正句“只做第1—3题”不出现；家长只看到“明天早上交回”。accept 后 `manual_tasks.action` 由同一 `_school_folded_lines` 生成，同样只剩最后一行。
- `same` 不受影响：`_school_fold_pending` 的 `change=='same'` 分支逐行原样追加 body（代码与 T1 一致）。
- 修法建议：`_school_folded_lines` 改为对原文**逐行**处理（`text.splitlines()`，空行跳过）再在每行内按 `。；;` 切句；保留 label 前缀与去重；`same` 分支保持现状。补 3 个多行用例（update 范围句、append 要求句、cancel 事实句）。

## 2. due 改法（`_school_late_due`）

`probes-r3b-out.txt` §B（old due = 2026-11-06）：

| 后到原文 | 结果 | 判定 |
|---|---|---|
| `今晚完成，周五交` | `2026-11-06` | ✅ 不误设（纯“今晚完成”不成为截止） |
| `今晚完成` | `''` | ✅ |
| `第12页范围不变。` | `''` | ✅ |
| `改到11月10日` | `''` | ✅（无交的动词，不乱设） |
| `数学作业` | `''` | ✅ |
| `明天数学课带来` | `2026-11-05` | ✅ |
| `改到11月10日交回` | `2026-11-10` | ✅ |
| `11月10日交` | `2026-11-10` | ✅（角色日兜底） |
| `改到11月10日交` | **`''`** | ❌ 旧截止 11-06 保留 |
| `改到11月10日交作业` | **`''`** | ❌ |
| `推迟到11月10日交` | **`''`** | ❌ |
| `改为11月10日交` | **`''`** | ❌ |

原因：`_school_role_days(quoted_text, evidence, [])` 对「改到/推迟到 + 普通交」返回 `None`（既没有完成句也没有角色词），随后兜底只放行 `交回|交给|交给我|上交|带来|带到`，于是日期语句被丢弃。`'11月10日交'`（无改期词）能过，是因为角色日解析出了 `(set(), '2026-11-10')` —— 说明漏的不是日期识别，而是**改期句的动词门**。

另：`_school_late_due(originals, old_due='')` 的 `old_due` 参数从未被读取（§C 两种 old_due 输出完全相同）——死参数，建议删掉或真正用于“只允许往后改”。

修法建议：在兜底门中加入普通提交动词集合（`交|交作业|提交|交上去`），但**必须**同时要求文本含改期标记（`改到|改为|推迟到|延后到|提前到|延期到`）且能解析出完整日期；`今晚完成`/`完成即可` 之类不含提交动词，仍不会设截止。补上表四个反例。

## 3. 透明度声明是否成立

lead 给的声明：update/cancel 的 ref 以 note 行出现而不作行首 `message:`，因为 `family_agenda.py` 会用 source 所有 `message:` 行重建消息集合、影响一天角色，a-math 的 `complete_on` 会掉空。

**机制成立**（`probes-r3.py` T3b，monkeypatch `Store._message_context`，虚构 m04/m05）：

- refs 只有 `[m04]`：`due_on=2026-11-06 complete_on=2026-11-04 due_kind=deadline`。
- refs `[m04, m05]`（m05 文本重复同一 quote）：`complete_on=''`（`own` 变 2），`due_on` 不变。
- 代码依据：`family_agenda.py:1243` 只收行首 `message:`；`L881-884` 的 `complete_on` 要求 `len(own)==1`。

**UI 后果**（本轮同样确认）：`calendar.js:449` / `app.js:138` 的「看原消息」按钮只从行首 `message:` 构造 → update/cancel 的后到消息**没有按钮入口**；`app.js:144` 的 `详情与原通知` 里以纯文本显示 note 行，所以 ref 字面可见、原文不可读（要读原文只能回消息列表）。这与“后到原文仍可读”的声明存在落差：**文本行可见（单行时），原文不可点开**。

**B3 不一致**：`_fold_school_follows`（已接受任务的后续通知）把后到 ref 以 `ref+'\n'+text` 加入 `source`（行首 ref），与 note-only 相反 → 若该文本重复 `date_quote`，`complete_on` 会被重置为空（T3b 同一机制）。建议：`_fold_school_follows` 对 update/cancel 也用 note-only（或至少不把重复 quote 的文本作为行首 ref），并补一条该路径的 `complete_on` 断言。

## 4. 回归文件 `test_school_fold_visibility.py` 覆盖

| 面 | same | append | update | cancel | 备注 |
|---|---|---|---|---|---|
| 卡 body（单行） | ✅ | ✅ | ✅ | ✅ | `FoldedLinesTest` |
| 卡 body（多行） | ❌ | ❌ | ❌ | ❌ | 无多行用例（B1 正好落在这） |
| 卡 due | ✅ | ❌ 无 | ✅ | ✅ | `FoldPendingTest` 无 append；update 只测「due 保持 11-06」，未测改期成功 |
| accept action | ❌ 无 | ❌ 无 | ✅ | ❌ 无 | 只有 update 一条 |
| accept source | ❌ 无 | ❌ 无 | ⚠️ | ❌ 无 | 只断言 `message:fiction-wx:9` 在 source 里，**没有**断言它“不是行首 ref”（设计意图没被锁住） |
| accept 后 due | ❌ | ❌ | ❌ | ❌ | 无断言 |
| `_fold_school_follows` | ❌ | ❌ | ❌ | ❌ | 完全未覆盖 |
| `_school_late_due` 反例 | n/a | n/a | ⚠️ | n/a | 只测交回类；无普通“交”改期 |

结论：DB 断言是有的（不是只测返回值），但覆盖面约为 `4 类 × body`（单行）+ `update × action/source`，其余面缺失；B1/B2 两个缺陷因此没被回归拦住。建议按上表补：多行 3 例、append 的 body/due、same/append/cancel 的 accept action+source、accept 后 due、`_fold_school_follows` 一条、普通“交”改期 4 例。

## 必改清单（BLOCK）

1. **B1**：`_school_folded_lines` 改为逐行渲染（所有非空行），修 `append/update/cancel` 多行原文丢句；补多行回归。
2. **B2**：`_school_late_due` 兜底承认普通提交动词 + 改期标记（且需完整日期），修正「改到11月10日交」保留旧截止；补反例。
3. （建议同批）**B3** 统一 `_fold_school_follows` 与 `_school_accept_fold` 的引用方式，避免 `complete_on` 被后到重复文本重置。
4. （建议）**B4** 把 `school_folded` 加入 `_school_role_reselect` 的排除条件，避免将来重写 body 时覆盖折叠行；删除死的 `old_due` 参数。

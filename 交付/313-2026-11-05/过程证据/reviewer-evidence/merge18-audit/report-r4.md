# merge18 终审（报告 r4）

审计对象（本机 sha1 核验，全程只读，未改产品源码、未 commit）：

| 文件 | sha1 |
|---|---|
| `family_agent.py` | `517b7517f91d9bc0e08e0a0b6b806f50f54e5d77` |
| `family_llm.py` | `bf2c974be34b6460d980d18b8e2ffc1498611be1`（= HEAD） |
| `test_school_fold_visibility.py` | `87bf3d6504ce0d1fa191f6038e608bb11e880486`（21 tests，实跑 OK） |

方法：只读代码 + 函数级/DB 级探针（全虚构数据，不跑模型）；探针前后 `family_agent.py` sha1 未变。
证据：`probes-r4.py` / `probes-r4-out.txt`（RESULT: GREEN）、`probes-r3.py`、`report-r3.md`。

## 结论：GREEN（可发布）

上轮 BLOCK 的四条均已修好，逐条复验：

### 1. B1 多行后到原文（PASS）

`_school_folded_lines` 已改为逐行处理（`for raw in str(text).split('\n')`，每行再按 `。；;` 切、去重），label 带发送时间。DB 实测（`Store._school_fold_pending`，虚构原文 16:00）：

| 变更 | 后到原文 | 卡 body 实际（节选） | due |
|---|---|---|---|
| update | `更正：…只做第1—3题。\n明天早上交回。` | `完成…第1—4题。\n后到更正原文（2026-11-04 16:00）：更正：…只做第1—3题。\n后到更正原文（2026-11-04 16:00）：明天早上交回。` | `2026-11-05` ✅ |
| append | `补充：…还要写算式。\n算式写在练习册上。` | `…\n后到补充原文（2026-11-04 16:00）：补充：…还要写算式。\n后到补充原文（…）：算式写在练习册上。` | 保持 11-06 ✅ |
| cancel | `刚才带落叶那一项取消。\n不用带叶子和旧书。` | `…\n取消依据（2026-11-04 16:00）：刚才带落叶那一项取消。\n取消依据（…）：不用带叶子和旧书。` | `''` ✅ |
| same | 两行提醒 | 两行原样追加（无标签） | 保持 ✅ |

accept 后 `manual_tasks.action` 同样两行逐字在（update/append/cancel/same 四类实测，`missing_parts=[]`）；可见行格式即 lead 要的「后到更正原文（2026-11-04 16:00）：…」。

> 说明（非阻断）：update 的卡 body 首行仍是原卡自己的「第1—4题」，更正行紧随其后。即“原始通知保留 + 带时间戳的更正行”并列，不再出现“更正的改范围句消失、只剩旧范围”的 r3 问题。若产品要求更正后不再显示旧范围，属显示策略调整，不属于本轮数据丢失范畴。

### 2. B2 改期（PASS）

| 后到原文 | 结果 |
|---|---|
| `改到11月10日交。` / `推迟到11月10日交。` / `改为11月10日交。` / `改到11月10日。` / `改到11月10日交作业。` / `改到11月10日交回。` | `2026-11-10` ✅ |
| `今晚完成，周五交给我。` | `2026-11-06` ✅ |
| `今天数学课带来。` / `明天数学课带来。` | `2026-11-04` / `2026-11-05` ✅ |
| `今晚完成。` / `第12页范围不变。` / `数学作业。` / `改到下周。` | `''`（不设截止）✅ |

且经 `_school_fold_pending` 落库：update「更正：只做第26页第1—3题，改到11月10日交。」→ `due=2026-11-10`（`probes-r4-out.txt` B2b）。
实现依据：新增 `_SCHOOL_MOVED_DAY`（改到/改为/推迟到/…）+ 句子尾部日期解析，改期句无需“交回/带来”即可生效；纯“今晚完成”仍不成为截止。

### 3. B3 引用约定（PASS）

- `_school_fold_note(...)` 实测输出：
  `后到原文（更正/取消依据，不进本事项日期判断）：2026-11-04 16:00（message:s-wechat:m05）「更正：只做第1—3题，改到11月10日交。」`
  → 不以 `message:` 开头、带时间与原文、ref 仍在 note 里。
- accept 路径（`_school_accept_fold`）：update/cancel 的 source 行首引用只有首通知 `message:s-wechat:m04`，更正以 note 出现；same/append 仍按行首引用加入（四类均实测）。
- `_fold_school_follows`（已接受任务的后续通知，静态核对 `probes-r4.py` B3b）：`extra`（行首 ref+原文）仅 `change in ('same','append')`；update/cancel 走 `_school_fold_note`，不写行首 `message:`。两条路径约定一致。
- 动机复验（`family_agenda.metadata`，虚构 m04/m05，date_quote 取「今晚完成《每日练习》第26页第1—4题」）：只引用 m04 → `complete_on=2026-11-04`；把 m05 也当行首引用 → `complete_on=''`（`own` 变 2）。说明“note-only 绕过”的理由成立，且新约定下 update/cancel 不会再触发该清空。

### 4. B4（PASS）

`_school_role_reselect` 的早期排除列表已含 `'school_folded'`（`family_agent.py:5510`：`… 'school_split_from','school_folded')):return None`），静态断言 + 行号均已记录。

### 5. 新回归是否真的锁住（抽查，PASS）

`test_school_fold_visibility.py`（21 tests，实跑 `Ran 21 tests … OK`）抽查断言：
- `test_every_line_of_a_multiline_correction_stays_in_order`：两行都在且**顺序**满足；`test_every_line_of_a_multiline_cancellation_stays`；`FoldPendingTest.test_a_multiline_replacement_keeps_both_the_range_and_the_new_day`（DB 断言 body 两行 + `due=2026-11-05`）。
- `test_a_moved_day_counts_without_a_hand_back_verb`：4 种改期措辞逐个断言 `2026-11-10`；`test_a_plain_completion_day_is_never_a_new_deadline`、`test_a_reminder_keeping_the_day_states_the_same_day`。
- `FoldAcceptTest.test_action_source_and_day_after_acceptance`：`assertNotIn('\nmessage:fiction-wx:9', '\n'+source)` **锁住“更正不是行首引用”**；`test_a_reminder_is_still_cited_as_a_message`；`test_the_note_carries_words_and_time_on_both_paths`。
- 多行用例同时出现在 `_school_folded_lines` 与 DB（`_school_fold_pending`）两级，不是只测返回值。

## 残余提示（不影响发布）

1. `_fold_school_follows` 端到端未动态跑（需要 app/配置装配）；其写 source 的两个表达式已静态核对，且 note 由与 accept 路径相同的 `_school_fold_note` 生成。
2. 非作业句「上课时间改到11月10日下午」当前不设本事项截止（更保守）；若产品希望“改期即改截止”，需再加作业对象门。
3. update 后卡面并列保留旧范围原文（见 §1 说明）。

**判定：GREEN（可发布）。**

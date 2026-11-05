# 终审：日清单显示投影（family_agenda.py sha1 6c1574d7）— 独立复核

- 审查对象：`/Users/joyrush/.local/share/family-learning/public-integration-20260926/family_agenda.py`
  sha1 = `6c1574d7cc474542b2656214879c9615c77aebd7`（mtime 2026-11-04 15:55:52，git HEAD 58973a6，未提交）
- 方式：read-only；只写 `work/reviewer-evidence/`；未改产品源码、未 commit、无网络、无 GUI。
- 原始输出：`final-audit-raw.txt`、`diff-audit-r2.txt`、`probes-v4.txt`、`property-report.round2.txt`、`test-runs/*.v4.log`、`family_agenda.reviewed.py`、`family_agenda.diff.v4`。

## 结论：**BLOCK**（必改 2 项 + 补测 1 项，均为窄修，约 10 行内）

理由：ACCEPTANCE 素材（h18 8 个 matter）、仓库内 64 组语料、18 条预登记对抗样例均无信息丢失（见 §1–§3），但本轮新增的风险探针仍能稳定构造出**未被任何测试覆盖的真实丢失**两类（§5）：`_FOLD_CHARS` 折叠掉「再/也」等副词（F1–F4），以及 `_plain` 抹掉数字分隔符后 `_whole_title_repeat` 把不同题号当成同一行（N1/N2）。按产品硬规则「任何漏/编/串都算失败」，判 BLOCK；修好后可转 ACCEPTABLE。

> 给 lead：若走回退方案「只做标签去重 + 不做标题裁剪」，M1（数字分隔符）自动消失，但 **M2（fold 副词）仍必须做**——F1–F4 由 `_covered_by` 的 fold 分支产生，与标题裁剪无关；回退时若保留行级 fold 判重，`读一遍。/再读一遍。` 仍会被吞。

## 1) property_test 重跑（sha1 6c1574d7，原始输出见 `final-audit-raw.txt` §1–§3）

- CORPUS：64 组（AST 扫描仓库 `*.py`）、findings **5**，逐条判定全部为 (a) 纯重复/纯标签/标题已读，无真实丢失：
  - `test_daily_list_expression.py:94` `('语文：A','读第3课，读第3课。')` → `['读第3课。']`（同句重复）
  - `:99` `'读第3课，读第3课，家长签字。'` → `['读第3课，家长签字。']`（重复子句）
  - `:115` `('英语：完成《每日练习》','完成英语《每日练习》。')` → `[]`（标题即 `英语：完成《每日练习》`，正文仅词序不同）
  - `:116` `('英语：完成《每日练习》','补充要求：完成英语《每日练习》。')` → `[]`（同上 + 纯标签）
  - `test_homework_print_change_basis.py:28` → `['11月5日交。']`（标题已读 `完成数学练习三第1至5题`）
- ADVERSARIAL：预登记 18 条硬伤样例，**RED = 0**；FABRICATE / DANGLING / LABEL / EMPTY 错误 0；无乱序（reorders 0）。
- **A5a（否定互换）已修复**：`action_lines('语文：不用抄写，要朗读两遍','要抄写，不用朗读两遍')` = `['要抄写，不用朗读两遍']`（否定词不再被标题吞掉）。

### 5 类硬伤逐条
| 类别 | 结果 | 依据 |
|---|---|---|
| A2e 否定词丢失 | **GREEN** | 18 条对抗样例 RED 0；A5a 已修；§4 NEG1–NEG5 无丢失 |
| A2a–d 丢数字/对象/时间 | **GREEN**（原始 A2a–d 场景） | `今天交/明天交`、`1号本/2号本`、`明天带数学练习册和语文书/英语书` 在最终版均两行全读；corpus FP 0 |
| A1b/A1c 标题裁剪丢新 token | **GREEN**（原始场景） | `完成练习册第20页第1、2题` 保留；`完成练习册第3页第2题` 保留；`第1至3题` vs `第13题` 保留（「至」不是标点）— 但分隔符变体见 §5 N1/N2 = BLOCK |
| A4b 折叠乱序/编造 | **GREEN** | `_label_line` 仅替换上一行最后子句；全部输出 reorders 0、fabricate 0 |
| day_view 未真删 plan 行 | **GREEN** | `arranged=str(((task or {}).get('focus') or {}).get('next_action') or '').strip()`，来源是家长自己的下一步；`_PLAN_LINE` 只匹配 `家庭安排（计划 …）：` 开头的行，命中后 `plan_lines.extend(...)`，其余行全部 `kept` 回 `lines`；`test_daily_list_expression.py` 29 tests OK（含 PlanLineTests/display-only/deepcopy） |

## 2) 新旧差分审计（HEAD 58973a6 vs 6c1574d7，`diff-audit-r2.txt`）

PAIRS 64，`SUMMARY {'same': 52, 'a': 9, 'B': 3}`。3 条 B-LOSS 逐条复核后均判 **(a) 纯标签/纯重复，非信息丢失**：

1. `test_daily_list_expression.py:107`/`:161` `('语文：A','做完放进英语夹里，明天带来。\n做完放进英语夹，明天带来。')`
   → 新版保留更完整的首行；被删片段 `做完放进英语夹明天带来` 是保留行的**保序子序列**（仅多一个「里」）＝同一要求换个说法。
2. `:116` `('英语：完成《每日练习》','补充要求：完成英语《每日练习》。')` → `[]`
   → 删掉的只是标签「补充要求」+ 标题原词（英语/完成/《每日练习》全在标题里显示），无新事实。

其余 9 条 (a)：`:89/:103/:156` 家长签字重复、`:94/:99/:100` 读第3课重复、`:197` 纯标签、`:115` 词序、`test_homework_print_change_basis.py:28` 标题已读。52 组 plain 完全相同。
→ **语料差分结论：0 条 (b) 信息丢失。**

## 3) 测试改动审查（`git diff test_school_completion_today.py` + 新增 test_daily_list_expression.py）

| # | 检查项 | 判定 | 依据 |
|---|---|---|---|
| P1 | 无丢失不变量（join-back）是否被放宽 | **PASS** | `test_school_completion_today.py:1649` `self.assertEqual(''.join(shown), CLEAR_EN_GOAL if '提交要求' in action else action)` 已恢复，无 C4 特例；`:1507`/`:789` 仍在 |
| P2 | 是否删除测试方法/守卫 | **PASS** | 无 `def test_` 被删；`assertTrue(any(startswith('提交要求')))` 改为 `assertFalse(any(label))` **+** `assertTrue(any(kept in x))`（守卫更严，且新增 kept 内容检查） |
| P3 | 期望值是否把「丢信息」写成合法 | **PASS**（2 处需知会） | `('英语：跟读','英语：',[])` 与 `('英语：…','补充要求：完成英语《每日练习》。',[])`：被省掉的是纯标签/标题原词，标题仍显示，不构成丢失；`'数学：完成同步练习第3课'` 用例首行原样保留、仅去标签 |
| P4 | allow-list 是否扩大 | **PASS** | 未见把任意行加入白名单；两处都是显式单例 |
| P5 | 新增测试是否覆盖 BLOCK 两类 | **FAIL（覆盖缺口）** | `grep '再读一遍\|第13题\|第1、2段\|也要交'` → none；F1–F4、N1/N2 无测试 |

## 4) 新增 3 处否定保护的副作用（构造探针，`final-audit-raw.txt` §5）

| 探针 | 输出 | 判定 |
|---|---|---|
| 标题含否定、正文是新增否定：`'数学：第4题不做'` + `'第5题不做'` | `['第5题不做']` | 正常，新增信息读到 |
| 正文重复标题否定 + 新信息：`'第4题不做，改做第5题'` | 整行保留 | 该省不省（标题已显示「第4题不做」），**无丢失**，可接受 |
| 正文是标题否定的具体化：`'不用背诵《课文》，要朗读两遍'` | 整行保留 | 同上，重复但无丢失 |
| 标题否定 + 新行：`'不用录音。明天带练习册'` | `['明天带练习册']` | 正常（标题已读「不用录音」） |
| 标题/正文同否定，正文有裁剪空间：`'不用抄写课文，朗读两遍'` | 整行保留 | 该省不省，无丢失 |

→ 3 处守卫未引入新丢失；副作用只是「标题已说过的词在正文重复一次」，符合「宁多读一句，不漏一句」的取舍，**ACCEPTABLE**。

## 5) BLOCK 证据（真实丢失，均可复现）

```
F1 T='语文：A' A='读一遍。\n再读一遍。'          OUT=['读一遍。']        losses=[('再读一遍。','再读一遍')]
F2 T='语文：A' A='语文要交。\n语文也要交。'        OUT=['语文要交。']      losses=[('语文也要交。','也要交')]
F3 T='语文：A' A='明天带练习册。\n明天再带练习册。' OUT=['明天带练习册。']  losses=[('明天再带练习册。','再带练习册')]
F4 T='语文：A' A='明天不带练习册。\n明天不再带练习册。' OUT=['明天不带练习册。']
N1 T='数学：完成第1—3题' A='完成第13题'          OUT=[]   ← 卡片显示「第1—3题」，而保存的要求是「第13题」
N2 T='语文：朗读第1、2段' A='朗读第12段'          OUT=[]   ← 卡片显示「第1、2段」，保存的要求是「第12段」
```
- F1–F4 机理：`_covered_by` 的 `_fold_key(part)==_fold_key(whole)`，`_FOLD_CHARS='的了着里也都就再还吧呢啊呀哦嘛和与及而'` 把「再/也/还/都/就」删掉后两行相等。**「再读一遍」是增量的第二遍，不是语气助词**；卡片只剩「读一遍」，孩子会少读一遍（真实漏）。
- N1/N2 机理：`_plain` 删除全部 Unicode 标点，「第1—3题」「第1、2段」变成「第13题」「第12段」；`_whole_title_repeat` 没有 `_title_prefix_removed` 已有的 `_tokens(prefix)-_tokens(title)` 守卫，于是整行被省略。**范围题号与单题号语义相反**（1–3 题 vs 第 13 题）。

## 6) 必改项（建议补丁，均只动 family_agenda.py）

- **M1（必改）** `_whole_title_repeat` 补 token 守卫，与 `_title_prefix_removed` 对齐：
  ```python
  def _whole_title_repeat(line, title):
      a, b = _plain(title), _plain(line)
      if not b: return False
      if _tokens(line) - _tokens(title): return False   # 新增：数字/《》/时间/否定不得被整行省略
      if _NEG_RE.search(line) and a != b: return False
      return _covered_by(a, b)
  ```
  验证：N1→`['完成第13题']`、N2→`['朗读第12段']`；仓库语料中标题真的覆盖整行的情况（如 `完成英语《每日练习》。`）token 是子集，仍会被省略，无回归。
- **M2（必改）** `_FOLD_CHARS` 删除承载增量语义的副词：`'的了着里吧呢啊呀哦嘛和与及而'`（去掉 再/还/也/都/就）。
  验证：F1→两行全读、F2/F3/F4 同样保留；英语夹那条真正的助词重复（夹/夹里）仍由「里」折叠，测试不受影响。
- **M3（必改·补测）** 把 F1 与 N1/N2 写成回归断言（例如 `test_daily_list_expression.py` 新增 `FoldSemanticsTests`/`TitleNumberGuardTests`），并保持 4 个套件全绿。
- 可选 M4：`_covered_by` 的 fold 分支加 `_tokens(part)==_tokens(whole)` 前提（与 M1 同源的防御纵深）。

## 7) 交付报告用「风险声明」原文（lead 指定，逐字）

> `_tokens` 只覆盖数字/《》对象/时间/否定字符的存在性，覆盖不了“否定作用域移动”，因此靠 `_NEG_RE` 硬保护封堵；`_FOLD_CHARS` 只含语气/结构助词，不含否定/数字/时间/对象/实词，故“交/不交”“1号/2号”“今天/明天”不会被 fold 判重。剩余已知限制：跨消息的同义重复（如“做完…带来/完成后…带到学校”）按“不丢信息”保留原话；标题覆盖整行时首句可能被省略（标题可见）；fold 只处理助词级差异。

**引用前请注意**：该段与当前代码有出入——`_FOLD_CHARS` 实际含「再/还/也/都/就」五个**副词**，不是「只含语气/结构助词」；实测 F1 `读一遍。/再读一遍。` 会把第二遍吞掉，且 `标题覆盖整行时首句可能被省略` 的机制会扩到「范围题号 vs 单题号」（N1/N2）。应用 M1+M2 后此段才与代码一致（届时 `_FOLD_CHARS` 只剩 `的了着里吧呢啊呀哦嘛和与及而`）；若不修，建议改为「fold 只处理助词与少数副词级差异，已知可能吞掉『再/也』等增量副词」。

## 8) 测试与基线

- 4 套件（sha1 6c1574d7，改前/改后同）：`test_daily_list_whole_day.py` 19 OK；`test_school_completion_today.py` 55 tests，`failures=3`，名称与 HEAD 基线**完全相同**（`test_a_later_parent_edit_after_the_confirmed_correction_still_comes_first`、`test_a_parent_note_under_an_accepted_duplicate_append_key_is_still_the_parent_choice (use_duplicate_key=False)`、`OrdinaryOwnedTimeTests.test_unknown_changed_cancelled_conflicting_or_borrowed_days_stay_unknown`）→ 既有失败，非新增；`test_daily_list_expression.py` 29 OK；`test_school_same_ready_notice.py` 30 OK。
- 基线证据：`/tmp/rv_baseline`（HEAD + 原 HEAD 测试文件）= 55 tests / failures=3，同名单；`work/lead-evidence/BASELINE-TESTS.txt` 一致。

## 9) 窄复核（M1/M2/M3 修复后，sha1 8348a716，mtime 16:00:33；测试文件 sha1 625a74f3）

sha1 在复核前后一致：`8348a71661cc22860eb40423224c576bba1109a6`。原始输出 `final-audit-raw.r3.txt`、`test-runs/*.r3.log`。**结论：GREEN（可交付）**。

- **M1 已修**：`_whole_title_repeat` 现为 `a,b=_plain(title),_plain(line); if not b:return False; if _tokens(line)-_tokens(title):return False; if _NEG_RE.search(line) and a!=b:return False; return _covered_by(a,b)`。
  `('数学：完成第1—3题','完成第13题')` → `['完成第13题']`；`('语文：朗读第1、2段','朗读第12段')` → `['朗读第12段']`。
- **M2 已修**：`_FOLD_CHARS='的了着里吧呢啊呀哦嘛和与及而'`。`读一遍。\n再读一遍。` → 两行全读；`明天带/明天再带`、`语文要交/语文也要交`、`明天不带/明天不再带`、`今天交/今天还要交` 均两行全读。
- **M1/M2 无新丢失、无新回归**：
  - 标题复述仍正常省略：`('英语：完成《每日练习》','完成英语《每日练习》。')` → `[]`；`补充要求：…` → `[]`（token 是子集，守卫不挡）。
  - 标签折叠仍正常：`('语文：A','答案写在练习册上。\n提交要求：答案写在练习册上，明天交。')` → `['答案写在练习册上，明天交。']`；`('数学：A','完成第3题。\n提交要求：完成第3题，家长签字。')` → `['完成第3题，家长签字。']`；`('语文：A','明天交练习册。\n提交要求：明天交练习册和卷子。')` → `['明天交练习册和卷子。']`。
  - 唯一副作用（可接受，非丢失）：只差语气副词的两行现在各自保留 → `('语文：A','今晚完成，明天交。\n今晚也完成，明天交。')` → `['今晚完成，明天交。','今晚也完成。']`；`('语文：A','数学都做。\n数学做。')` → 两行都读。属「宁多一句、不漏一句」。
- **M3 已补测**：`test_daily_list_expression.py` 新增 `FoldSemanticsTests`（L291，样例含 `读一遍。/再读一遍。`、`明天再带练习册。`、`语文也要交。`）与 `TitleNumberGuardTests`（L308，`第1—3题 vs 第13题`、`第1、2段 vs 第12段`）。
- property 重跑：CORPUS **68** 组（我的 AST 口径；projection 报 73，口径差异）、findings **6**，全部为纯重复/纯标签（新增的 `:316` 是同一 fixture 的重复行）；ADVERSARIAL 18 条 **RED=0**；A5a `['要抄写，不用朗读两遍']`。
- 套件：`test_daily_list_whole_day.py` 19 OK；`test_school_completion_today.py` 55 tests、failures=3，名单与 HEAD 基线完全相同；`test_daily_list_expression.py` **33 OK**（上次 29，+4 新测试）；`test_school_same_ready_notice.py` 30 OK。额外跑 `test_daily_list_frozen.py`：96 tests、failures=4 / expected failures=5，与 `/tmp/rv_baseline`（HEAD）**逐名相同** → 既有失败，与本改动无关。
- **§7 风险声明一致性**：M1/M2 修复后该段与代码一致（`_FOLD_CHARS` 已不含 再/还/也/都/就；否定由 `_NEG_RE` 硬保护；fold 只处理助词级差异），可原样引用。建议在交付说明补一句：「整行省略与首句裁剪都受 token 守卫保护，数字/《》对象/时间/否定不会被标题吞掉。」

# 反馈 → 错题本 → 订正 → 知识点 → 复习：端到端链路验证报告

- 验证时间：2026-11-04 23:41–23:43（Asia/Shanghai，本机真实 HTTP + 真实火山方舟模型）
- 被测产品：`/Users/joyrush/.local/share/family-learning/public-integration-20260926`，git HEAD `58973a6`；**本轮未修改、未提交任何产品代码**（工作区现有 9 个未提交修改：app.js、calendar.js、family_agenda.py、family_agent.py、family_llm.py、Workspace.swift、WorkspaceAPI.swift、test_school_completion_today.py、workbench.css——均为之前显示修复或会话期间他人改动，我没有回滚/编辑/提交任何产品文件）。
- 验证数据：全虚构（虚构班级 6 条老师消息、虚构孩子「示例甲」、自绘白底练习册截图）；未触碰私有家庭目录、未做真实家庭同步/打印/发布。
- 结论：**五步全通（5/5）**，链路连续，`record → task → topic_link → diagnosis → calendar review → 复测` 的 id 全程可互链。唯一未完成的是「新题再练」的**判定**：产品私有组件 DeepTutor 未配置，接口返回预期的 503 `deeptutor_unavailable`，不是链路代码断点。

## 0. 速览

| 步 | 结果 | 产品入口 / 关键代码 | 证据 |
|---|---|---|---|
| 1 反馈（部分完成+文字+照片） | 通 | `POST /api/upload`（app.py:2960）、`POST /api/task/feedback`（app.py:3107 → `save_task_feedback` app.py:1877） | `evidence/01-feedback.json` |
| 2 错题（真实模型标注 → 错题记录挂回原事项） | 通 | `POST /api/wrong/annotate`（app.py:3121 → `Store.annotate` family_wrong_review.py:145）、`POST /api/wrong/save`（app.py:3127 → `Store.save` family_wrong_review.py:185） | `evidence/02-wrong.json` |
| 3 订正（待订正 → 已订正，三方互链） | 通 | `POST /api/record`（app.py:3155 → `save_record` app.py:1009）；状态投影 app.py:682 | `evidence/03-correction.json` |
| 4 知识点（链接固定知识包 → 诊断，无重复项） | 通 | `/api/topic/{state,search,link,diagnosis/start,diagnosis/answer}`（app.py:3141 → family_taxonomy.py:463/544/557/567/589） | `evidence/04-topic.json` |
| 5 复习（排期可见 → 到期完成 → 第二轮复测；再练判定） | 通（再练判定 503） | `POST /api/calendar/save`（app.py:3051 → family_calendar.py:267，复习校验收 app.py:555）；`POST /api/record`；`/api/topic/diagnosis/retry`（family_taxonomy.py:845） | `evidence/05-review.json` |

一次整跑总耗时 38.8s（含现场生成当天清单 7.5s、真实模型错题标注 29.8s）。

## 1. 起点：当天清单由真实模型现场生成（非重放）

- 输入：测试夹具里 6 条**虚构**班级消息（语文朗读、数学练习册第12页第2–4题、英语跟读、英语带听写本、出游回执、参考读物），经产品 `family_agent.run_once`（family_agent.py:10147）走真实模型生成当天清单。
- 关键排障：默认配置下 `family_agent_selection` 反复失败——2 次 45.1s 超时（`LLMDraftError: 模型服务连接失败或超时…`，family_llm.py:757）+ 1 次 39.8s「模型尚未完成草稿」（Responses API `status != completed`，family_llm.py:767/781）。根因是产品把 selection 超时写死 45s（family_agent.py:8046）、输出预算 6000 tokens（family_llm.py:693），而 light 模型 `deepseek-v4-1-flash-261017` 继承了 `reasoning_effort=low`，推理输出吃满预算。
- 修复方式：**部署配置**，设 `FAMILY_LLM_LIGHT_REASONING_EFFORT=none`（family_llm.py MODEL_ENV 已支持该键）。探针一次通过：`evidence/pre-run-failures/light-effort-none.json`（selection 6.88s、processed 6、created 16，当时产品 `output_tokens` 仍是 6000）。runner 亦以 `os.environ.setdefault(...)` 固化该配置并注释原因。
- 需并列说明：23:40:45（我的最终整跑前约 30 秒）有**其他队友**在共享工作区把 `family_llm.py` 的 `family_agent_selection` 输出预算从 6000 改到 9000（未提交，不是我的改动）。因此最终整跑同时享有「配置 effort=none + 磁盘上 9000 输出预算」两个变量；**单项证据是那次探针**（6000 token 下 effort=none 已在 6.88s 成功），最终整跑则代表两者叠加后的真实产品行为。
- 最终整跑：`run_once` 首次即成功（selection 7.03s，processed=6，created=16，failed=0，`bootstrap=None` 未使用归档重放）。清单 6 条：

| 事项 id | 标题 | due |
|---|---|---|
| AGENT-8cf20b890ab7c179e47f2704 | 英语：明天英语课听写 | 2026-11-05 |
| AGENT-245cb9e8e5f0ddb0e10a7661 | 语文：朗读《晚照》2遍 | 2026-11-05 |
| AGENT-bb8551dbb459852787fd6bcd | 英语：明天带《单词听写本》 | 2026-11-05 |
| AGENT-1b4daaf39d91304f58931622 | 英语：跟读Unit 7第3至10个单词 | 无明确截止 |
| **AGENT-46d7f691d45e2af7a8132331** | **数学：完成练习册第12页第2至4题** | **2026-11-05** |
| AGENT-b9a8bf8bc153184d26815f36 | 交回《出游回执》（家长勾选签名） | 2026-11-09 |

数学事项由产品 `task_category`（family_agenda.py:689）自动判为 `agenda.category=homework`，这是错题挂原作业的前提（family_wrong_review.py:283 校验）。

## 2. 五步细账

### 步骤 1 · 反馈：通

- 材料：`evidence/fake-homework-page.png`，900×520 白底，文字「数学 · 练习册 第12页（全虚构） / 第2题 2+3=6 / 第3题 5+4=9 / 第4题 3+3=6」，29661 B，sha256 `cddbb626…a05988`。
- 调用：`POST /api/upload`（`X-File-Name` URL 编码、`X-Request-Key`、`Content-Type: image/png`）→ 200，附件 id `08c4bc142f73286b4a7f9470dc6116cd`；随后 `POST /api/task/feedback`，body 含 `task_id=AGENT-46d7…`、`child=示例甲`、`complete=false`、`day=2026-11-04`、`category=学习进展`、`subject=数学`、`completion_note`、`note`（第3、4题完成，第2题 2+3 写成 6）、`attachments=[附件id]`。
- 结果：200，`record_id=1`，`record.source='事项:AGENT-46d7f691d45e2af7a8132331'`，`title='反馈：数学：完成练习册第12页第2至4题'`，`created=2026-11-04T23:41:12`，附件回显在该反馈上；`task.original_status='待跟进'`。
- 模型：**不经过模型**（照片仅存证，不自动识别）。
- 证据：`evidence/01-feedback.json`。

### 步骤 2 · 错题：通（真实模型标注，挂回原事项）

- 标注：`POST /api/wrong/annotate` `{child:'示例甲', subject_hint:'数学', attachments:[附件id]}` → 200。真实模型 `family_wrong_questions_annotate` 成功，耗时 **29.76s**，返回 `pages[0].regions`：1 个 `layout` 卷头（`text='数学·练习册 第12页（全虚构）'`）+ 1 个 `wrong_item`：`label='第2题'`、`text='第2题 2+3=6'`、`answer='2+3=6'`、`correction=''`、`uncertain=true`、`topic_hint='5以内加法计算'`、`error_hint='加法计算结果错误'`；`uncertainties=['第2题无手写批改痕迹，仅依据算式运算结果判定为疑似错误']`。家长核对后补 `correction='2+3=5'`、备注，保留模型给的知识点/错误类型提示。
- 落库：`POST /api/wrong/save`，body 携带 `task_id` + `feedback_record_id=1` + `feedback_created` + `feedback_linked_at` + `request_key` + `items` → 200，`record_id=2`，`title='数学错题：第2题'`，`source='错题照片核对'`，**`related_record_id=1`（反馈）**、**`linked_task_id='AGENT-46d7…'`（原事项）**、`linked_task_at` 有值；note 按产品格式含「题面：第2题 2+3=6 / 学生原答：2+3=6 / 可见订正/正确答案：2+3=5 / 家长备注 / 知识点（家长核对）：5以内加法计算 / 错误类型（家长核对）：加法计算结果错误」+「家长对照原作答记录；这不是掌握程度结论。」
- 互链校验：`/api/day` 的 `learning` 里该错题 `task_id` 即原数学事项、`state='待订正'`，`task_title='数学：完成练习册第12页第2至4题'`；错题不是孤立新记录（`related_record_id=1` 指回同一条反馈）。
- 模型：**1 次**（上表 #2），产品唯一在链路上必经模型的环节。
- 证据：`evidence/02-wrong.json`（含 `annotate_raw`、`item_sent`、DB 行、day 视图）。

### 步骤 3 · 订正：通（状态翻转 + 三方互链）

- 调用：`POST /api/record` `{child:'示例甲', day:'2026-11-04', category:'学习进展', subject:'数学', title:'订正：练习册第12页第2题 2+3', note:'订正：2+3=5，并重算第3、4题。', followup_kind:'订正', related_record_id:2, request_key}`——**不传 `linked_task_id`**。
- 结果：200，`record_id=3`，`related_record_id=2`，`followup_kind='订正'`，且 `linked_task_id` **自动等于 `AGENT-46d7…`**（产品 `_save_record` app.py:1009 附近规则：跟进记录继承原错题的 `linked_task_id`，并 `record_task` 登记）。
- 状态：`/api/day?day=2026-11-04` 的 `learning.subjects[0].evidence` 中记录 2 `state='已订正'`（app.py:682 用 followup 记录投影），`lines=[['原错题','2026-11-04 · 已订正']]`，`task_title` 仍为原数学事项；互链三方 = 错题 2 ↔ 反馈 1 ↔ 事项 AGENT-46d7…，订正 3→2。
- 模型：**不经过模型**。
- 证据：`evidence/03-correction.json`。

### 步骤 4 · 知识点：通（引用固定知识包，不新建重复项）

- 过程：`/api/topic/state`（`pack.installed=true`）→ 模型给的 `topic_hint='5以内加法计算'` 先原样搜（返回 `status=none`，知识包里没有这个粒度），再按 `10以内加法` 搜索得到 `ambiguous` 3 个候选：`cnm_p010 10以内的加法`、`cnm_p031 100以内口算加法`、`cnm_p033 100以内笔算加法`；按 preferred 名单选 `cnm_p010`（一年级上册第2单元）。
- 链接：`/api/topic/link` `{state:'confirmed', request_id, note:'家长确认：错在「10以内的加法」'}` → 200。`topic_links` 仅 **1 行**：`record_id='2'`、`topic_id='cnm_p010'`、`state='confirmed'`、`pack_sha=e0f931ba…`。知识点来自只读知识包，产品不写知识包、**未出现同名重复知识点**。
- 诊断：`/api/topic/diagnosis/start` 200（`opts={'limit':8,'seed':request_id}`）→ 用 `node` 加载**产品自己下发的** `/api/topic/engine.js` 驱动：首题 `cnm_p010_q4` 文本 `A` 判 `wrong`（choice，正确答案 D），第二题 `cnm_p010_q1` 文本 `9` 判 `correct`；两条 `POST /api/topic/diagnosis/answer` 均 200，逐题 session/summary 由产品引擎生成、服务端按 `session.answers[-1]` 与 `len(answers)==seq` 校验通过。
- 结果：diagnosis `state='finished'`，`summary={"asked":2,"finished":true,"shaky":["cnm_p010"],"untested":["cnm_p001","cnm_p004","cnm_p006","cnm_p008"],...,"path":{"cnm_p010":"shaky"}}`；`/api/day` 的 learning `topics=[{topic_id:'cnm_p010', name:'10以内的加法', known:true, basis:'current', state:'diagnosed'}]`，lines 含「知识点诊断 · 答了2题」，next 提示「已有知识点线索，还没有独立再试。」
- 引擎一致性：`GET /api/topic/engine.js` 200、47863 B、sha256 `b4a48814213a5b50a49c86e39afcc6a6c81142cf4a8243cdfdc55dea397a017e`，与本地知识包 `diagnose/engine.js` 完全一致（`identical=true`）。
- 模型：**不经过模型**（诊断由知识包 engine.js 在 node 本地跑；这一步产品只校验与存档）。
- 证据：`evidence/04-topic.json`、`evidence/engine-served.js`、`evidence/4-engine.*.json`。

### 步骤 5 · 复习：通（排期可见 → 到期完成 → 第二轮复测），「再练判定」缺私有组件

- 排期：先取 `record.basis`（64 hex，来自 `family_taxonomy.record_hash` family_taxonomy.py:231），`POST /api/calendar/save` 提交单次复习事件：`id=69ab356f70974b3291b8a411a165b922`、`day='2026-11-05'`、`start_time='19:30'`、`end_time='19:50'`、`category='study'`、`repeat='none'`、`status='confirmed'`、`title='家庭复习：数学练习册第12页第2题'`、`review={child_id:'child-1', record_id:2, topic_id:'cnm_p010', task_id:'AGENT-46d7…', basis:<64hex>}` → 200。
- 到期日可见：
  - `GET /api/calendar?start=2026-11-05&end=2026-11-05` → 该事件，`review.basis_state='current'`、`record_title='数学错题：第2题'`（`calendar_review_check` app.py:555 校验 basis/task/topic 一致后才允许保存与展示）。
  - `GET /api/day?child_id=child-1&day=2026-11-05` → `schedule.plans` 含该复习（19:30–19:50、status confirmed，`review.basis_state='current'`、`review.record_title='数学错题：第2题'`）。产品**没有独立「复习队列/复习页」**，复习就是日历上带 `review` 链接的家庭事件；前端入口在 calendar.js:19/618/635（打开原错题+知识点、回原作业、basis 失效提示）。
- 到期完成：同 `id` 以 `version=1`、`status='completed'`、`note` 再存 → 200（返回 `version=2`），日历读回 `status='completed'`。
- 第二轮（错→订→复习→再练）：`POST /api/record` `followup_kind='复测'`、`day='2026-11-05'`、`related_record_id=2` → record 4，`linked_task_id` 自动=原事项；到期日视图 `state='已复测'`（lines：原错题 2026-11-04 · 已复测；知识点诊断 10以内的加法 · 答了2题）。
- 再练：用 `state.seen_qids` 过滤后由 engine 选出未做过的新题 `cnm_p010_q3`（numeric，prompt「有 4 支铅笔，又放进来 5 支。一共有多少支？计算：4＋5＝？」），`/api/topic/diagnosis/mark {action:'shown', mode:'retry'}` 200；提交 `/api/topic/diagnosis/retry` → **503**
  ```json
  {"error":"新题判定组件未配置，这一步没有保存；原错题和诊断照常保留，配置后可用同一提交重试","code":"deeptutor_unavailable","not_saved":true}
  ```
  原因：`family_deeptutor.py:11/19-21` 需要私有运行时 `private/runtime/deeptutor/bin/python`（本机未部署），产品设计上把「新题判定」当作可选私有能力，未配置时明确 503 且不落伪数据。替代路径 `/api/wrong/remediate`（app.py:3145）可用：200 生成 `guided_sessions` 草稿（session `0d19614bea29d587e8801a65038b2a4e`，`title='订正 · 数学错题：第2题'`、`question_text='第2题 2+3=6'`、`reference_text='2+3=5'`、`related_record_id='2'`、`practice_relation='同一道题或同一片段'`、`reference_checked=0`、`state='draft'`），不经模型、不需 DeepTutor。
- 模型：**不经过模型**（排期、完成、复测记录都是纯产品写入；再练判定组件不是 LLM seam）。
- 证据：`evidence/05-review.json`（`calendar`、`day_view_due.schedule.plans`、`review_completed`、`second_round_record`、`day_view_after`、`retry_probe`、`guided_probe`）。

## 3. 模型调用清单（本次整跑）

| # | seam 名 | 结果 | 耗时 | 路由 | 输入 | 原始返回留档 |
|---|---|---|---|---|---|---|
| 1 | `family_agent_selection` | ok | 7.03s | light 模型 `deepseek-v4-1-flash-261017`，`reasoning_effort=none`（env 配置） | 6 条虚构消息（text） | `00b-model-calls.json`（request_brief: evidence 6 条） |
| 2 | `family_wrong_questions_annotate` | ok | 29.76s | 主模型 `doubao-seed-evolving` | 1 张图片（parts=3、images=1、text_chars=72） | `00b-model-calls.json`、`02-wrong.json.annotate_raw` |
| — | 其余步骤 | 不调用模型 | — | — | 反馈/订正/知识点 link+诊断/复习排期/复测/引导草稿均为确定性产品或本地 engine.js | 见各步证据文件 |

- 链路本体（步骤 1–5）只有 **1 次** 真实模型调用（错题标注）；步骤 1/3/4/5 均不经过产品模型 seam（`family_llm._chat_json`）。标注失败会直接 503/400，不会静默造错题——本跑标注成功。
- 同次会话早前的失败留档：无缓解时 3 次 selection 失败（45.1s×2、39.8s×1）及一次 6.9s 成功探针（`light-effort-none.json`），见 `evidence/pre-run-failures/`。

## 4. 链路图（id 如何一步步传下去）

```
6 条虚构消息
  └─ run_once / family_agent_selection（真实模型，7.03s）
       └─ 事项 AGENT-46d7f691d45e2af7a8132331（数学，due 2026-11-05，agenda=homework）
            │
[1] /api/upload ── 附件 08c4bc14…（sha256 存证）
    /api/task/feedback ── record 1（source=事项:AGENT-46d7…, attachments=[附件]）
            │  task_id + record1.id + record1.created + record1.linked_task_at
            ▼
[2] /api/wrong/annotate（真实模型 29.76s：第2题 2+3=6，answer=2+3=6，topic_hint=5以内加法计算）
    /api/wrong/save ── record 2（related_record_id=1, linked_task_id=AGENT-46d7…）  ← 挂回原事项
            │  record2.id ▶ 订正/复测的 related_record_id
            │  record2.linked_task_id ▶ 自动继承给后续跟进记录
            ▼
[3] /api/record（followup_kind=订正）── record 3（related=2, linked_task=AGENT-46d7… 自动）
    /api/day learning ── 原错题 state: 待订正 → 已订正（app.py:682）
            │  record2.id + record2.basis（64hex，family_taxonomy.record_hash）
            ▼
[4] /api/topic/state/search/link ── topic_links.record_id=2 ↔ topic_id=cnm_p010（知识包只读，无重复）
    /api/topic/diagnosis/start ── diagnosis 1（opts limit=8/seed=request_id）
    node engine.js（产品 /api/topic/engine.js 同源 sha256）── seq1 q4 wrong, seq2 q1 correct
    /api/topic/diagnosis/answer ×2 ── items 1/2，summary finished，path cnm_p010=shaky
            │  record2.id + record2.basis + topic_id + linked_task_id(AGENT-46d7…)
            ▼
[5] /api/calendar/save（review 字段）── 家庭复习事件 69ab356f…（2026-11-05，basis 锁定）
    /api/calendar & /api/day ── 可见（basis_state=current）
    同 id version=1 status=completed ── 到期完成
    /api/record（followup_kind=复测, day=2026-11-05, related=2）── record 4（linked_task 自动）
    /api/day 2026-11-05 ── state: 已订正 → 已复测
    再练：topic retry 新题 cnm_p010_q3 → mark shown 200 → retry 503 deeptutor_unavailable（私有组件缺失）
         替代：/api/wrong/remediate ── 引导草稿（related_record_id=2）
```

## 5. 断点/缺口清单（均不阻塞前五步）

| # | 现象 | 位置 | 性质 | 建议 |
|---|---|---|---|---|
| 1 | 默认配置下当天清单生成 45s 超时（2×45.1s，1×39.8s incomplete） | family_agent.py:8046（timeout=45）、family_llm.py:693（output_tokens）、family_llm.py:117（LIGHT_TASKS 选路） | **部署配置 + 输出预算**，非逻辑 bug | (a) 部署侧：`application/private/model.json` 增 `"light_reasoning_effort": "none"`（或 env `FAMILY_LLM_LIGHT_REASONING_EFFORT=none`），已实测 6.88s 成功；(b) 代码侧已有未提交改动把 selection 输出预算 6000→9000（队友改），方向正确、可保留评审。建议 lead 指派配置负责人落盘，并把该未提交改动纳入评审。 |
| 2 | 「新题再练」提交 503 `deeptutor_unavailable` | family_deeptutor.py:11/19-21，映射见 app.py 异常处理 | **可选私有组件未部署**，产品已明确 not_saved，不造假 | 需要部署 `private/runtime/deeptutor`（或配 `FAMILY_DEEPTUTOR_PYTHON`）。建议派给负责私有运行时的同学；观察到「独立再试」是知识点闭环的最后 1 步。 |
| 3 | 知识点搜索吃自然语言差：`5以内加法计算`→none，`10以内加法`→ambiguous 3 选 1 | family_taxonomy.py:90-158（SEP/STOP/_tier 规则） | 可用性问题，不影响链路（产品返回候选、家长确认） | 若要改，属产品 UX 改进（需 lead 批准）：把搜索词先做同义词/名称归一，或前端给候选卡片。当前不必改。 |
| 4 | 复习无独立队列/页，也没有自动到期推进；完成需家长手动把事件改 completed | family_calendar.py:267、calendar.js:19/618/635 | 产品现状（复习=日历事件） | 若产品目标含复习队列，属新功能，建议单独立项；本次链路用日历入口已可连续走通。 |
| 5 | 复习 basis 锁定：错题更正后旧复习安排会 `review_basis_changed` 拒绝 | app.py:555-563 | 有意的保护逻辑 | 无需改。 |

## 6. 可复现

```bash
cd /Users/joyrush/Documents/deepseek-harness/default-workspace/work/loopcheck
python3 loopcheck_run.py          # 首次运行会先 real_model selection 生成当天清单，再顺序走五步
# 产物：evidence/*.json + evidence/family.sqlite3 + evidence/report-data.json + run-final.out
```

- 脚本只写 `work/loopcheck/`；模型 key 仅从 `application/private/model.json` 读入进程环境，日志与证据中不含 key。
- 知识包从上游 `cn-math-taxonomy@e0f931b` 下载到 `work/loopcheck/knowledge/`，五文件 sha256 与产品 MANIFEST 逐一核对一致；通过 `FAMILY_TAXONOMY_DIR` 指向，不改产品目录。
- 时间说明：真实时钟为 2026-11-04；到期完成与第二轮复测是**用产品 API 把事件改为 completed 并提交 2026-11-05 的复测记录**来模拟到期，不是改系统时钟。到期日视图、basis 校验、状态投影均走真实产品代码路径。

## 7. 证据索引（work/loopcheck/evidence/）

| 文件 | 内容 |
|---|---|
| `00-agent-run.json` | 起点生成 attempts（本次 1 次成功、bootstrap=null） |
| `00b-model-calls.json` | 2 次真实模型调用原始记录（含 result） |
| `00b-tasks.json` | 起点清单事项 |
| `01-feedback.json` | 上传 + 反馈的响应原文 |
| `02-wrong.json` | 标注 raw、保存 body、错题 DB 行、day 视图 |
| `03-correction.json` | 订正记录 + `state=已订正` 证明 |
| `04-topic.json` | 搜索候选、link、engine sha 比对、诊断题与答案、state 终态 |
| `05-review.json` | 日历事件、到期日视图、完成、复测、再练 503、引导草稿 |
| `engine-served.js` / `4-engine.*.json` / `5-retry-item.*.json` | 产品下发引擎与 node 运行输入输出 |
| `fake-homework-page.png` | 全虚构作业图（含 sha256 存证） |
| `family.sqlite3` | 本次运行最终数据库副本 |
| `report-data.json` / `summary-for-report.json` | 全步骤汇总、DB dump、http trace、模型调用 |
| `pre-run-failures/` | 默认配置 selection 失败与 `light_effort=none` 探针成功证据 |

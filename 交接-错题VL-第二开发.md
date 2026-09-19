# 错题线交接：分工与接口（Hermes ↔ Claude）

闭环：错题照片 → ①读准并标注 → ②家长核对入库 → ③按知识点/错误类型诊断 → ④让孩子重做 → ⑤间隔后同类新题复测 → 再诊断。协作规则见 [AGENTS.md](AGENTS.md)，任务状态见[协作看板](协作看板.md)。

## 现状（2026-09-19：r80–r82 已部署家庭实例，真实验收待补）

- ①② Hermes：`family_wrong_questions.py`（视觉模型标注草稿）；`family_wrong_review.py`、`wrong-review.js/css`（“更多 → 试卷错题集”，家长核对后保存为“学习进展”，来源“错题照片核对”）。
- ③④⑤ Claude：`family_diagnosis.py`（诊断、到期复测、后台重诊门槛）；`family_remediation.py`（重做草稿）；`goals.js` 孩子画像“错题诊断”；`family_agent.py` 的到期提醒与后台诊断。
- 发布复核（Codex）：重做草稿只带题面文字，不带可能含答案的原照片。

## Hermes 下一步（①：读准、标全、可诊断）

1. 真实样卷精度：儿童手写、涂改、光线不均、手机倾斜下，框是否贴合、转写是否逐字正确；看不清写入 `uncertain`/`uncertainties`。先用非隐私样卷或家长同意的照片。
2. 手写解答单独出 `handwriting` 框（题面、作答、批改仍在 `wrong_item`）。
3. 密集、多栏、跨页排版不串框；跨页归属不清写入 `uncertainties`。
4. 候选标签：每个 `wrong_item` 可选 `topic_hint`（知识点候选，如“两位数进位加法”）与 `error_hint`（错误类型候选，如“进位漏加”），没把握留空。它们只是草稿提示，不当事实。
5. OpenRouter 免费视觉模型对比，不达标不切换家庭生产模型。

## 接口约定（改动先改本文档，再通知对方）

- `annotate_pages(...)` 返回 `{pages:[{page, regions:[{kind, box, label, text, answer, correction, uncertain, topic_hint?, error_hint?}]}], uncertainties}`。坐标 0..1000、左上原点；`wrong_item`/`handwriting`/`layout` 语义不变。
- ② 保存：记录类别“学习进展”，来源含“错题照片核对”（③ 据此识别错题，④ 只对这类记录生成重做草稿）。note 按行写 `题面：`、`学生原答：`、`可见订正/正确答案：`、`家长备注：`；④ 用 `题面：` 与 `可见订正/正确答案：` 取题目和参考，改前缀须同步。
- 候选标签入库（建议格式，Hermes 实现前可在此提出修改）：家长在核对页确认或改写后保留的标签，在 note 追加 `知识点（家长核对）：…`、`错误类型（家长核对）：…` 两行；未经家长确认的候选不写入。③ 把它们当诊断起点，结论仍只引真实记录。
- 双方共同底线：一切是“待核对草稿，家长保存后才成事实”；不写家庭库之外的地方、不猜答案、不判掌握、不输出其他孩子信息。

# 契约：QQ截图通知挂回的单个PDF原件 · 独立Agent逐批学校资料草稿（R09，后端进度）

范围：只做后端进度与原消息只读view；UI、家长确认、正式要求回写由下一独立任务接。虚构数据验证，未家庭部署。

## 触发与拒绝（代码判定，家长可见原因）
- 仅 QQ 窗口片段通知（`fragment-…`，`family_media._material_kind == school_material`）；排除截图自身上传件（编号与同图重传两条规则沿用 `family_media.draft_input`）。
- 排除后恰好一个同孩 `application/pdf` 才处理。0 个 PDF → 交给既有图片/DOCX草稿；≥2 个 PDF → `pdf_multiple`；PDF 与图片/DOCX 混合 → `pdf_mixed_originals`；均为 `state=unavailable` 且 0 渲染 0 调用，不悄悄跳过。
- 授权：`family_media._authorized`（全局/来源启用、消息未变）+ `Store._message_upload`（原件可用、不跨孩）。

## 数据
- 表 `agent_pdf_material(source_id,message_id,fingerprint,first_page,pages JSON,page_count,payload,updated)`，主键含 fingerprint 与 first_page；一行 = 一个已成功页组。
- fingerprint = sha256([3,'school_material','pdf',source,child,message,[upload_id,mime,pdf_sha256]])；来源/孩子/消息/原件字节任一变化即换指纹，旧页组只隐藏不删。
- payload = `{"kind":"school_material","title","note","uncertainties"}`，保存前后都过 `family_llm.validate_school_material`；无 score/mastery/record 字段。
- 任务：`agent_jobs` key `pdf-material:<sha(source,message)[:40]>`，value `{"pdf_material":fingerprint,"done":[已处理页]}`；同批失败沿用 `Store._job/_fail` 三次退避，新批换 value。

## 执行（`family_pdf_material.prepare(store, now, budget=1)`）
1. budget≤0 或全局停用 → `used=0`，不读 pdfinfo、不渲染、不调用。
2. 选第一条可处理消息：算指纹、读已保存页组；已覆盖全部页 → 跳过（重复完成 0 调用）；否则领取 job。
3. 释放数据库后：首批用 `family_pdf.page_count` 取总页数，之后取已保存 page_count；页组 = 未处理页前 3 页；`family_pdf.render_pages` 渲染 → `family_llm.extract_draft(text, images, school_material=True, target_child=孩子)`，text 含 `source_message/source_name/original_pdf{name,pages,page_count,unprocessed_pages}`。
4. `BEGIN IMMEDIATE` 后重核指纹、job 指纹、page_count 与页组无重叠；家长更正/解除/撤权/原件变化 → 丢弃结果、job 置 done 不留错误；一致才写入页组并完成 job。
5. 每轮最多 1 次模型调用，占用 tick 剩余共享预算（学校消息/计划优先，与视频同位）。

## 只读 view（`family_pdf_material.view(store,c,source,message)` → 消息页 `pdf_material`）
- 0 模型、0 pdfinfo/pdftoppm、0 写入、不建表；儿童端不含此字段。
- `None`：无 PDF 原件。`unavailable{explanation}`。否则 `{state: pending|error|ready, kind, upload_id, name, job_id, page_count|null, processed_pages, pending_pages, complete, batches:[{pages,draft,updated}], explanation}`；`complete` 与页集合由代码计算，首批前 `page_count=null`。
- 草稿不接任何学习记录/任务/成绩/计划消费入口。

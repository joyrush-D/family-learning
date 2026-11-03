// 试卷错题集：拍照/选图 → 模型标注 → 原图同屏核对 → 保存为学习记录。
// 只在家长点击时调用模型；保存前一切都是草稿，刷新不保留。
(() => {
'use strict';
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const uid = () => crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
const KIND_LABEL = {wrong_item: '错题', handwriting: '手写区域', layout: '版面'};
const KIND_COLOR = {wrong_item: '#dc2626', handwriting: '#2563eb', layout: '#16a34a'};
let ctx, root, busy = false;
let state, childID = '';
const drafts = new Map();

// ---- 批量导入照片（PRD 5.1 W1）：当前孩子一次多选 → 原件按原上传守卫保存（逐张派生提交标识）→ 登记批次 →
// 产品后台读图/组卷/检查 → 按科目每卷结果。本页只读取结果，打开/刷新不调用模型。
const BATCH_MAX = 30;
const BATCH_STATE = {queued: '排队中，产品后台会自动处理', running: '正在读取和检查', needs_attention: '部分步骤未完成', done: '已完成'};
const batchStates = new Map();
let pollTimer = 0;

function bstate() {
  if (!batchStates.has(childID)) batchStates.set(childID, {batches: null, error: '', status: '', pending: null, open: '', busy: false, records: new Set()});
  return batchStates.get(childID);
}

function pageNo(batch, page) { return page ? batch.pages.findIndex(p => p.page_id === page.page_id) + 1 : 0; }

function thumb(page) {
  return page ? `<img class="pb-thumb" src="${ctx.endpoint('/upload/')}${encodeURIComponent(page.upload_id)}" alt="" loading="lazy">` : '';
}

function batchHTML() {
  const b = bstate();
  const list = b.batches === null ? '<p class="small muted">正在读取已导入的照片…</p>'
    : b.batches.length ? b.batches.map(batchCardHTML).join('') : '<p class="small muted">还没有导入的照片。</p>';
  return `<section class="card pb-import" data-batch-root>
    <div class="pb-import-head"><div><h2>导入照片</h2>
      <p class="small muted">为${esc(state.child)}一次选最多${BATCH_MAX}张作业/试卷照片，不同科目、乱序或同一份的多页都可以一起选；系统在后台自动分科、分卷、排页和检查，不用先填科目、题号或建作业。</p></div>
      <label class="filebutton pb-pick">选择照片<input type="file" accept="image/jpeg,image/png,image/webp" multiple data-batch-pick ${b.busy ? 'disabled' : ''}></label></div>
    <p class="small ${b.error ? 'error' : 'muted'}" role="status" data-batch-status>${esc(b.error || b.status)}</p>
    ${b.pending && !b.busy ? '<div class="wrong-actions"><button type="button" data-batch-retry>用同一提交标识重试未完成部分</button></div>' : ''}
    <div data-batch-list>${list}</div>
  </section>`;
}

function batchCardHTML(batch) {
  const papers = [...batch.papers].sort((a, b) => a.subject.localeCompare(b.subject, 'zh'));
  const find = id => batch.pages.find(p => p.page_id === id);
  const wait = [...batch.pages.filter(p => ['unreadable', 'unsupported'].includes(p.status)).map(p => [p, p.reason]),
                ...batch.pending.map(p => [find(p.page_id), p.reason])];
  const dup = batch.pages.filter(p => p.status === 'duplicate');
  const progress = batch.state === 'done' ? '' : `（${batch.progress.done}/${batch.progress.total || '…'}步）`;
  return `<article class="pb-batch" data-batch-id="${esc(batch.id)}" data-batch-state="${esc(batch.state)}">
    <header><strong>${esc(batch.created.slice(0, 16).replace('T', ' '))} 导入 · ${batch.pages.length}张</strong><span class="small">${esc(BATCH_STATE[batch.state] || batch.state)}${progress}</span></header>
    ${batch.can_continue ? `<div class="pb-failed"><p class="small error">${batch.progress.failed.map(f => esc(f.error || '处理失败')).join('；')}</p>
      <p class="small muted">已完成的部分保留，只重做未完成的步骤。</p>
      <div class="wrong-actions"><button type="button" data-batch-continue="${esc(batch.id)}" data-batch-version="${batch.version}">继续失败部分</button></div></div>` : ''}
    ${papers.map(p => paperHTML(batch, p)).join('')}
    ${wait.length ? `<div class="pb-wait"><strong>待补的页</strong><ul>${wait.map(([p, r]) => `<li>${thumb(p)}第${pageNo(batch, p)}张：${esc(r || '待补')}</li>`).join('')}</ul></div>` : ''}
    ${dup.length ? `<p class="small muted">${dup.map(p => `第${pageNo(batch, p)}张与第${pageNo(batch, find(p.duplicate_of))}张是同一张照片，只读一次`).join('；')}</p>` : ''}
    ${batch.stale.length ? `<p class="small muted">${batch.stale.map(s => esc(s.subject + ' ' + s.title + '：' + s.reason)).join('；')}</p>` : ''}
  </article>`;
}

function paperHTML(batch, paper) {
  const c = paper.counts, open = bstate().open;
  const counts = paper.checked ? `AI判错${c.wrong}处 · 疑似${c.suspected}处 · 未判定${c.unknown}题 · 与参考一致${c.correct}题` : paper.note ? '' : '检查中';
  return `<section class="pb-paper" data-paper-id="${esc(paper.paper_id)}">
    <h3>${esc(paper.subject)} · ${esc(paper.title || '未识别标题')}</h3>
    <p class="small">${paper.pages.length}页${counts ? ' · ' + counts : ''}${paper.unlocated ? ` · ${paper.unlocated}处未定位到原图题框` : ''}</p>
    ${paper.note ? `<p class="small muted">${esc(paper.note)}</p>` : ''}
    ${paper.coverage ? `<p class="small muted">${esc(paper.coverage)}</p>` : ''}
    ${(paper.segment_coverage || []).filter(s => s.model_coverage).map(s => `<p class="small muted">检查说明（模型自述，未核）：${esc(s.model_coverage)}</p>`).join('')}
    ${paper.unchecked_questions.length ? `<p class="small error" data-paper-unchecked>明确未检查：${esc(paper.unchecked_questions.join('、'))}</p>` : ''}
    ${paper.unchecked_pages.length ? `<p class="small muted">尚未检查：${paper.unchecked_pages.map(id => '第' + pageNo(batch, batch.pages.find(p => p.page_id === id)) + '张').join('、')}</p>` : ''}
    <ul class="pb-questions">${paper.questions.filter(q => q.state !== 'correct').map(q => questionHTML(batch, q, open === q.key)).join('')}</ul>
  </section>`;
}

function questionHTML(batch, q, isOpen) {
  const page = batch.pages.find(p => p.page_id === q.page_id);
  const saved = q.record_id ? `<p class="small">已记入错题${q.chosen ? '（家长选择纳入练习）' : '（AI判断）'}${q.followups.length ? ' · ' + q.followups.map(f => esc((f.followup_kind || '跟进') + ' ' + f.day)).join('、') : ''}</p>
      <div class="wrong-actions"><button type="button" data-followup="${q.record_id}" data-followup-kind="订正">记订正 / 复测</button></div>`
    : q.state === 'suspected' ? `<div class="wrong-actions"><button type="button" data-batch-include="${esc(q.key)}" data-batch-id="${esc(batch.id)}" data-batch-version="${batch.version}">纳入练习</button></div>` : '';
  return `<li class="pb-q" data-state="${esc(q.state)}" data-question-key="${esc(q.key)}">
    <button type="button" class="pb-q-head" data-batch-open="${esc(q.key)}" aria-expanded="${isOpen}"><span class="pb-tag">${esc(q.state_word)}</span>${esc(q.label)}${q.located ? '' : '<span class="small muted">· 未定位</span>'}</button>
    ${isOpen ? `<div class="pb-q-body">
      ${page && q.box ? `<div class="pb-figure"><img src="${ctx.endpoint('/upload/')}${encodeURIComponent(page.upload_id)}" alt="原图第${pageNo(batch, page)}张"><span class="pb-box" data-batch-box style="${boxStyle({...q.box, kind: 'wrong_item'})}"></span></div>`
        : '<p class="small muted">没有可靠对应的原图题框，未定位；原图已关联到这道题。</p>'}
      ${q.question ? `<p><b>题面</b> ${esc(q.question)}</p>` : ''}
      <p><b>原答</b> ${esc(q.student_answer || '未能确认')}</p>
      ${q.answer ? `<p><b>参考</b> ${esc(q.answer)}</p>` : ''}
      ${q.error_reason ? `<p><b>依据</b> ${esc(q.error_reason)}</p>` : ''}
      ${q.uncertainty || q.conflict ? `<p class="small muted">不确定：${esc([q.conflict, q.uncertainty].filter(Boolean).join('；'))}</p>` : ''}
      <p class="small muted">署名：AI判断，未经老师或家长核定；不代表掌握程度。</p>${saved}
    </div>` : ''}
  </li>`;
}

function paintBatch() {
  const el = root?.querySelector('[data-batch-root]');
  if (el) el.outerHTML = batchHTML();
}

function schedulePoll() {
  clearTimeout(pollTimer);
  const b = bstate();
  if (root?.isConnected && (b.batches || []).some(x => ['queued', 'running'].includes(x.state))) pollTimer = setTimeout(loadBatches, 2500);
}

async function loadBatches() {
  const b = bstate(), id = childID;
  if (!id || !root?.isConnected) return;
  try {
    const r = await ctx.apiFetch('/api/photo-batches?child_id=' + encodeURIComponent(id), {headers: {'X-Family-Token': ctx.token}});
    const out = await r.json();
    if (!r.ok) throw new Error(out.error || ('HTTP ' + r.status));
    if (id !== childID) return;
    b.batches = out.batches;
    if (b.error.startsWith('读取导入结果失败')) b.error = '';
    const ids = out.batches.flatMap(x => x.papers.flatMap(p => p.questions.map(q => q.record_id).filter(Boolean)));
    // 已完成（非排队/处理中）批次的已记原错题与逐卷依据版本：编号相同而依据变了（如第1版→第2版）也要读回原记录。
    const prints = {};
    for (const x of out.batches) if (!['queued', 'running'].includes(x.state))
      prints[x.id] = x.papers.flatMap(p => p.questions.filter(q => q.record_id).map(q => `${x.version}|${p.paper_id}|${p.based_on_version ?? 0}|${q.record_id}`)).sort().join(',');
    const fresh = ids.filter(i => !b.records.has(i));
    const changed = Object.entries(prints).some(([k, v]) => v && (b.prints || {})[k] !== v);
    paintBatch();
    // 经原记录读取入口读回一次（原“记订正 / 复测”链与记录卡片的依据都来自它）；读回成功才记已同步，进行中不重入。
    if ((fresh.length || changed) && !b.syncing) {
      b.syncing = true;
      try {
        await ctx.reload?.();
        fresh.forEach(i => b.records.add(i)); b.prints = {...(b.prints || {}), ...prints};
        if (b.error.startsWith('原错题记录暂未读回')) { b.error = ''; paintBatch(); }
      } catch (e) {
        b.error = '原错题记录暂未读回（' + (e.message || '读取失败') + '）；导入结果已保存，稍后回到本页会再读。';
        paintBatch();
      } finally { b.syncing = false; }
    }
  } catch (e) {
    b.error = '读取导入结果失败，可刷新重试：' + (e.message || '网络错误');
    paintBatch();
  }
  schedulePoll();
}

function updateBatch(view) {
  const b = bstate();
  b.batches = [view, ...(b.batches || []).filter(x => x.id !== view.id)].sort((x, y) => y.created.localeCompare(x.created));
}

async function postBatch(path, body) {
  const r = await ctx.apiFetch(path, {method: 'POST', headers: {'X-Family-Token': ctx.token, 'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const out = await r.json();
  if (!r.ok) { const error = new Error(out.error || ('HTTP ' + r.status)); error.refused = true; throw error; }
  return out;
}

async function importPhotos(files) {
  const b = bstate();
  if (files.length > BATCH_MAX) { b.error = `每批最多${BATCH_MAX}张，本次选了${files.length}张；请分批导入。`; return paintBatch(); }
  b.pending = {key: 'pb' + uid(), child: childID, files, uploads: files.map(() => null)};
  return runImport();
}

async function runImport() {
  const b = bstate(), job = b.pending;
  if (!job) return;
  b.busy = true; b.error = '';
  let failed = 0, last = '';
  for (let i = 0; i < job.files.length; i++) {
    if (job.uploads[i]) continue;
    const file = job.files[i];
    b.status = `正在保存原件 ${i + 1}/${job.files.length}…`; paintBatch();
    try {
      if (!file.size || file.size > 20 * 1024 * 1024) throw new Error('为空或超过20MB');
      const r = await ctx.apiFetch('/api/upload', {method: 'POST', headers: {'X-Family-Token': ctx.token, 'X-File-Name': encodeURIComponent(file.name),
        'X-Request-Key': job.key + '-' + String(i + 1).padStart(2, '0'), 'Content-Type': 'application/octet-stream'}, body: file});
      const out = await r.json();
      if (!r.ok) throw new Error(out.error || ('HTTP ' + r.status));
      job.uploads[i] = out.attachment.id;
    } catch (e) { failed++; last = file.name + '：' + (e.message || '上传失败'); }
  }
  if (failed) {
    b.busy = false; b.status = '';
    b.error = `${failed}张照片未保存（${last}）；已保存的原件保留，可用同一提交标识重试。`;
    return paintBatch();
  }
  b.status = '原件已保存，正在登记这一批…'; paintBatch();
  let view = null;
  for (let attempt = 0; attempt < 2 && !view; attempt++) {
    try { view = await postBatch('/api/photo-batch/create', {child_id: job.child, request_key: job.key, uploads: job.uploads}); }
    catch (e) {
      if (e.refused) { b.busy = false; b.status = ''; b.error = e.message; return paintBatch(); }
      b.status = '没有收到登记回执，正在用同一提交标识查询…'; paintBatch();
    }
  }
  b.busy = false;
  if (!view) { b.status = ''; b.error = '没有收到登记回执；原件已保存，可用同一提交标识重试，不会重复建批次。'; return paintBatch(); }
  b.pending = null;
  b.status = view.replayed ? '已找到这一批（同一提交标识），没有重复登记。' : '已登记，产品后台会自动读图、分卷和检查；离开本页也会继续，回来即可看到结果。';
  updateBatch(view);
  paintBatch();
  schedulePoll();
}

async function batchAction(button, path, body) {
  const b = bstate();
  button.disabled = true;
  try { updateBatch(await postBatch(path, body)); b.error = ''; }
  catch (e) { b.error = (e.message || '操作失败') + '；原批次和原图保留，可刷新后重试。'; }
  paintBatch();
  await loadBatches();
}

function freshState() {
  return {child: '', day: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10),
          subject: '', ids: [], draft: null, review: [], error: '', generation: 0,
          saveKey: '', uploadStatus: {type: '', text: ''}};
}

function imageUploads() {
  return (ctx.uploads || []).filter(a => ['image/jpeg', 'image/png', 'image/webp'].includes(a.mime));
}

function html() {
  return `<div class="wrong-wrap">
    <div class="wrong-heading"><div><h1>试卷错题集</h1>
    <p class="muted">当前孩子一次导入一批作业/试卷照片，系统自动分科、分卷、检查，并在原图上标出错题；单张照片逐题核对与手记在下方备用。</p></div></div>
    ${batchHTML()}
    <section class="card wrong-setup">
      <h2 class="pb-manual">单张核对与手记（备用）</h2>
      <p class="small muted">拍照或选择已上传的作业/试卷照片（每次1–3张），模型先框出疑似错题，你在原图上逐题核对、修改后才保存为学习记录。</p>
      <div class="formrow">
        <label>孩子<select data-wrong-child required>${(ctx.children || []).map(c => `<option value="${esc(c.name)}" ${state.child === c.name ? 'selected' : ''}>${esc(c.name)}</option>`).join('')}</select></label>
        <label>发生日期<input data-wrong-day type="date" value="${esc(state.day)}" required></label>
        <label>科目（可选）<input data-wrong-subject maxlength="80" value="${esc(state.subject)}" placeholder="数学、语文…"></label>
      </div>
      <div class="wrong-capture">
        <label class="filebutton">拍试卷<input type="file" accept="image/*" capture="environment" data-wrong-camera ${busy ? 'disabled' : ''}></label>
        <label class="filebutton">从手机相册/电脑选图<input type="file" accept="image/jpeg,image/png,image/webp" multiple data-wrong-pick ${busy ? 'disabled' : ''}></label>
        <p class="small muted">每张最多20MB、本批合计不超过20MB；照片先存为家庭私有原件。</p>
        <p class="small ${state.uploadStatus.type === 'ok' ? 'muted' : (state.uploadStatus.text ? 'error' : 'muted')}" data-wrong-upload-status role="status">${esc(state.uploadStatus.text)}</p>
      </div>
      <div data-wrong-pool></div>
      <div class="wrong-actions">
        <button type="button" class="primary" data-wrong-annotate ${busy ? 'disabled' : ''}>框出疑似错题</button>
      </div>
      <p class="error" data-wrong-error role="alert">${esc(state.error)}</p>
    </section>
    <div data-wrong-result></div>
    <p class="small muted">模型只整理本次所选照片，不读其他原件；框选与转写都可能有误，保存的只是你核对过的错题记录，候选标签不是错因或掌握结论。打开本页不调用模型。</p>
  </div>`;
}

function poolHTML() {
  const all = imageUploads().slice(0, 40);
  if (!all.length) return '<p class="small muted">还没有可用照片，先拍照或选图。</p>';
  return `<p class="small muted">勾选本次要整理的照片（最多3张）：</p><div class="wrong-pool">${all.map(a => `
    <label class="wrong-thumb ${state.ids.includes(a.id) ? 'selected' : ''}">
      <input type="checkbox" value="${esc(a.id)}" ${state.ids.includes(a.id) ? 'checked' : ''}>
      <img src="${ctx.endpoint('/upload/')}${encodeURIComponent(a.id)}" alt="${esc(a.name)}" loading="lazy">
      <span>${esc(a.name)}</span>
    </label>`).join('')}</div>`;
}

function boxStyle(box) {
  return `left:${box.x / 10}%;top:${box.y / 10}%;width:${box.w / 10}%;height:${box.h / 10}%;border-color:${KIND_COLOR[box.kind] || '#888'}`;
}

function resultHTML() {
  const d = state.draft;
  if (!d) return '';
  const othersCount = d.pages.reduce((n, p) => n + p.regions.filter(r => r.kind !== 'wrong_item').length, 0);
  return `<section class="card wrong-review">
    <h2>核对错题（${state.review.length} 处疑似）</h2>
    ${(d.uncertainties || []).length ? `<div class="wrong-uncertain"><strong>模型标注的不确定处：</strong><ul>${d.uncertainties.map(u => `<li>${esc(u)}</li>`).join('')}</ul></div>` : ''}
    ${d.pages.map(p => `
      <figure class="wrong-page">
        <figcaption>第${p.page}页 · ${esc(p.attachment.name)}</figcaption>
        <div class="wrong-canvas"><img src="${ctx.endpoint('/upload/')}${encodeURIComponent(p.attachment.id)}" alt="第${p.page}页试卷原件">
          ${p.regions.map(r => `<span class="wrong-box ${r.uncertain ? 'uncertain' : ''}" style="${boxStyle(r)}" title="${esc(KIND_LABEL[r.kind])} ${esc(r.label || '')}"></span>`).join('')}
        </div>
      </figure>`).join('')}
    <div class="wrong-items">
      ${state.review.map(item => `
        <article class="wrong-item" data-wrong-uid="${esc(item.uid)}">
          <header><label class="wrong-keep"><input type="checkbox" data-wrong-keep ${item.keep ? 'checked' : ''}> 保存这条（第${item.page}页）</label>
            <span class="wrong-badge" style="background:${KIND_COLOR.wrong_item}">疑似错题${item.uncertain ? ' · 待核对' : ''}</span></header>
          <div class="formrow"><label>题号/位置<input data-wrong-field="label" maxlength="80" value="${esc(item.label)}"></label></div>
          <label>题面转写（可改）<textarea data-wrong-field="text" maxlength="2000">${esc(item.text)}</textarea></label>
          <div class="formrow">
            <label>学生原答<input data-wrong-field="answer" maxlength="1000" value="${esc(item.answer)}"></label>
            <label>订正/正确答案<input data-wrong-field="correction" maxlength="1000" value="${esc(item.correction)}"></label>
          </div>
          <div class="formrow">
            <label>知识点候选（可改或清空）<input data-wrong-field="topic_hint" maxlength="60" value="${esc(item.topic_hint)}"></label>
            <label>错误类型候选（可改或清空）<input data-wrong-field="error_hint" maxlength="40" value="${esc(item.error_hint)}"></label>
          </div>
          <p class="small muted">候选仅供后续核对，不是对孩子能力的结论。</p>
          <label>家长备注（可选）<textarea data-wrong-field="note" maxlength="1000" placeholder="例如：让孩子先讲错在哪，不直接判原因。">${esc(item.note)}</textarea></label>
        </article>`).join('') || '<p>这一页没有标出疑似错题；如确认漏标，可直接用上方“记录反馈”手动记。</p>'}
    </div>
    ${othersCount ? `<details class="wrong-others"><summary>模型标出的手写区域与版面块（${othersCount}，仅供对照，不保存）</summary>
      ${d.pages.map(p => `<p class="small">第${p.page}页：${p.regions.filter(r => r.kind !== 'wrong_item').map(r => KIND_LABEL[r.kind] + (r.label ? '·' + r.label : '')).join('，') || '无'}</p>`).join('')}</details>` : ''}
    <p class="error" data-wrong-save-error role="alert"></p>
    <div class="wrong-actions">
      <button type="button" class="primary" data-wrong-save ${state.review.length ? '' : 'disabled'}>保存勾选的错题为学习记录</button>
      <button type="button" data-wrong-discard>放弃这批草稿</button>
    </div>
  </section>`;
}

function findItem(uid) {
  return state.review.find(item => item.uid === uid) || null;
}

function setError(msg) {
  state.error = msg || '';
  root.querySelectorAll('[data-wrong-error], [data-wrong-save-error]').forEach(el => { el.textContent = ''; });
  const el = root.querySelector('[data-wrong-save-error]') || root.querySelector('[data-wrong-error]');
  if (el) el.textContent = state.error;
}

function remember() {
  state.child = root.querySelector('[data-wrong-child]')?.value || '';
  state.day = root.querySelector('[data-wrong-day]')?.value || state.day;
  state.subject = root.querySelector('[data-wrong-subject]')?.value || '';
  state.ids = [...root.querySelectorAll('[data-wrong-pool] input:checked')].map(i => i.value);
  root.querySelectorAll('.wrong-item').forEach(card => {
    const item = findItem(card.dataset.wrongUid);
    if (!item) return;
    card.querySelectorAll('[data-wrong-field]').forEach(inp => { item[inp.dataset.wrongField] = inp.value; });
    item.keep = card.querySelector('[data-wrong-keep]').checked;
  });
}

function rerenderResult() {
  root.querySelector('[data-wrong-result]').innerHTML = resultHTML();
}

async function uploadFiles(files) {
  if (!files || !files.length) return;
  remember();
  busy = true;
  state.uploadStatus = {type: '', text: files.length > 1 ? `正在上传 0/${files.length}…` : '正在上传…'};
  paint();
  const status = root.querySelector('[data-wrong-upload-status]');
  let saved = 0, failed = 0;
  const failedNames = [];
  try {
    for (const file of files) {
      if (file.size > 20 * 1024 * 1024 || !file.size) {
        failed++;
        failedNames.push(file.name + '（为空或超过20MB）');
        state.uploadStatus = {type: 'error', text: '跳过（为空或超过20MB）：' + file.name};
        status.textContent = state.uploadStatus.text;
        status.classList.remove('muted'); status.classList.add('error');
        continue;
      }
      status.textContent = '正在上传：' + file.name;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 120000);
      try {
        const r = await ctx.apiFetch('/api/upload', {signal: controller.signal, method: 'POST',
          headers: {'X-Family-Token': ctx.token, 'X-File-Name': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream'}, body: file});
        const out = await r.json();
        if (!r.ok) throw new Error(out.error || ('上传失败（' + r.status + '）'));
        if (!state.ids.includes(out.attachment.id) && state.ids.length < 3) state.ids.push(out.attachment.id);
        ctx.uploads = ctx.uploads || [];
        if (!ctx.uploads.some(a => a.id === out.attachment.id)) ctx.uploads.unshift(out.attachment);
        saved++;
      } catch (e) {
        failed++;
        const reason = e.name === 'AbortError' ? '上传超时'
          : (e.message || ('上传失败（HTTP）'));
        failedNames.push(file.name + '（' + reason + '）');
        const msg = '上传失败：' + file.name + '（' + reason + '）';
        state.uploadStatus = {type: 'error', text: msg};
        status.textContent = msg;
        status.classList.remove('muted'); status.classList.add('error');
      }
      finally { clearTimeout(timer); }
    }
    if (saved && !failed) {
      state.uploadStatus = {type: 'ok', text: `照片已保存为私有原件（本批 ${saved} 张），请勾选后标注。`};
    } else if (saved) {
      state.uploadStatus = {type: 'error', text: `本批 ${saved} 张已保存为私有原件，${failed} 张失败/跳过：${failedNames.join('，')}；成功的照片已保留，可重新选择失败的照片。`};
    } else {
      state.uploadStatus = {type: 'error', text: `本批 ${failed} 张照片上传失败/跳过：${failedNames.join('，')}；未成功保存的照片不会进入标注，可重新选择后重试。`};
    }
  } finally {
    busy = false;
    paint();
  }
}

async function annotate() {
  if (state.saveKey) return setError('上次保存结果尚未核对，请先用原内容重试保存。');
  remember();
  if (!state.child) return setError('请先选择孩子。');
  if (!state.day) return setError('请填写发生日期。');
  if (!state.ids.length || state.ids.length > 3) return setError('请选择1到3张照片。');
  busy = true; setError('');
  lock();
  const gen = ++state.generation;
  root.querySelector('[data-wrong-annotate]').disabled = true;
  root.querySelector('[data-wrong-result]').innerHTML = '<p class="note">模型正在框选并转写，通常需要半分钟左右，本页会保留…</p>';
  try {
    const r = await ctx.apiFetch('/api/wrong/annotate', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Family-Token': ctx.token},
      body: JSON.stringify({child: state.child, subject_hint: state.subject, attachments: state.ids})});
    const out = await r.json();
    if (!r.ok) throw new Error(out.error || '标注失败');
    if (gen !== state.generation) return;
    // A new annotation draft starts a new idempotency key; an uncertain write of
    // an earlier draft must never be replayed against different model output.
    state.saveKey = '';
    state.draft = out;
    state.review = out.pages.flatMap(p => p.regions.filter(r => r.kind === 'wrong_item')
      .map(r => ({uid: uid(), page: p.page, attachment: p.attachment.id, uncertain: !!r.uncertain, keep: true,
                  label: r.label || '', text: r.text || '', answer: r.answer || '', correction: r.correction || '', note: '',
                  topic_hint: r.topic_hint || '', error_hint: r.error_hint || ''})));
    rerenderResult();
  } catch (e) {
    if (gen === state.generation) root.querySelector('[data-wrong-result]').innerHTML = '';
    setError(e.message || '标注暂不可用，可先用记录反馈手动记。');
  } finally {
    busy = false;
    paint();
  }
}

async function save() {
  remember();
  const items = state.review.filter(item => item.keep)
    .map(item => ({attachment: item.attachment, label: item.label || '', text: item.text || '',
                  answer: item.answer || '', correction: item.correction || '', note: item.note || '',
                  topic_hint: item.topic_hint || '', error_hint: item.error_hint || ''}))
    .filter(r => r.label || r.text || r.answer || r.correction);
  if (!items.length) return setError('没有勾选要保存的错题；可放弃草稿或重新勾选。');
  busy = true; setError('');
  // One key per review draft: failed/aborted POSTs (possibly already written
  // server-side) are retried with the same key so save_record replays instead
  // of duplicating. Cleared only on success, discard or a new annotation.
  if (!state.saveKey) state.saveKey = uid().slice(0, 32);
  lock();
  try {
    const r = await ctx.apiFetch('/api/wrong/save', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Family-Token': ctx.token},
      body: JSON.stringify({child: state.child, day: state.day, subject: state.subject,
                            request_key: state.saveKey, items})});
    const out = await r.json();
    if (!r.ok) {
      if (r.status >= 400 && r.status < 500 && ![401, 403, 408, 409, 429].includes(r.status)) state.saveKey = '';
      throw new Error(out.error || '保存失败');
    }
    state.saveKey = '';
    state.draft = null; state.review = []; state.ids = [];
    paint();
    let refreshed=true;try{await ctx.reload?.()}catch{refreshed=false}
    root.querySelector('[data-wrong-result]').innerHTML =
      `<div class="note wrong-saved">已保存 ${out.count} 条错题学习记录，并关联照片原件。<br>可打开原记录关联任务，继续记订正和复测；记录不代表掌握结论。${refreshed?(out.saved||[]).map(r=>`<button type="button" data-record="${esc(r.id)}">关联任务 / 查看原记录</button>`).join(''):'<p>记录已保存，列表暂未更新；请刷新后查看原记录。</p>'}</div>`;
  } catch (e) { setError(e.message || '保存未完成，草稿仍在，请重试。'); }
  finally { busy = false; lock(); }
}

function lock() {
  root.querySelectorAll('input,select,textarea,button').forEach(el => {
    el.disabled = busy || !!state.saveKey && el.matches('[data-wrong-child],[data-wrong-pick],[data-wrong-camera],[data-wrong-annotate],[data-wrong-discard]') || el.hasAttribute('data-wrong-save') && !state.review.length;
  });
}

function paint() {
  root.innerHTML = html();
  root.querySelector('[data-wrong-pool]').innerHTML = poolHTML();
  if (state.draft) rerenderResult();
  lock();
}

function onClick(e) {
  if (busy) return;
  const t = e.target.closest('button');
  if (!t) return;
  if (t.hasAttribute('data-batch-retry')) return runImport();
  if (t.dataset.batchContinue) return batchAction(t, '/api/photo-batch/continue', {batch_id: t.dataset.batchContinue, version: Number(t.dataset.batchVersion)});
  if (t.dataset.batchInclude) return batchAction(t, '/api/photo-batch/include', {batch_id: t.dataset.batchId, version: Number(t.dataset.batchVersion), question_key: t.dataset.batchInclude});
  if (t.dataset.batchOpen) { const b = bstate(); b.open = b.open === t.dataset.batchOpen ? '' : t.dataset.batchOpen; return paintBatch(); }
  if (t.hasAttribute('data-wrong-annotate')) return annotate();
  if (t.hasAttribute('data-wrong-save')) return save();
  if (t.hasAttribute('data-wrong-discard')) { state.saveKey = ''; state.draft = null; state.review = []; state.generation++; paint(); }
}

function onChange(e) {
  if (busy) return;
  if (e.target.matches('[data-wrong-child]')) {
    const owner = ctx.children.find(c => c.name === e.target.value);
    e.target.value = state.child;
    if (!owner || !canSwitch() || ctx.onChildChanged?.(owner.id) === false) return;
    childID = owner.id;
    state = drafts.get(childID) || freshState();
    drafts.set(childID, state);
    state.child = owner.name;
    paint();
    loadBatches();
    return;
  }
  if (e.target.matches('[data-batch-pick]')) {
    const files = [...(e.target.files || [])];
    e.target.value = '';
    if (files.length && !bstate().busy) importPhotos(files);
    return;
  }
  if (e.target.matches('[data-wrong-camera], [data-wrong-pick]')) {
    const files = [...(e.target.files || [])];
    e.target.value = '';
    if (files.length) uploadFiles(files);
    return;
  }
  if (e.target.closest('[data-wrong-pool]')) {
    remember();
    root.querySelectorAll('.wrong-thumb').forEach(l => {
      const cb = l.querySelector('input');
      l.classList.toggle('selected', cb.checked);
    });
    return;
  }
  if (e.target.matches('[data-wrong-day],[data-wrong-subject]')) remember();
}

function canSwitch() {
  if (busy || state?.saveKey || batchStates.get(childID)?.busy) {
    if (root?.isConnected) setError('请先完成上传、标注或核对上次保存，再切换孩子。');
    return false;
  }
  if (root?.isConnected) remember();
  return true;
}

function mount(options) {
  if (root?.isConnected && !busy) remember();
  let owner = options.children?.find(c => c.id === options.child_id) || options.children?.[0];
  if ((busy || state?.saveKey) && childID && owner?.id !== childID) {
    owner = options.children?.find(c => c.id === childID);
    options.onChildChanged?.(childID);
  }
  ctx = options;
  root = options.root;
  childID = owner?.id || childID;
  state = drafts.get(childID) || freshState();
  drafts.set(childID, state);
  state.child = owner?.name || state.child;
  paint();
  loadBatches();
  root.addEventListener('click', onClick);
  root.addEventListener('change', onChange);
  root.addEventListener('input', e => {
    if (busy) return;
    if (e.target.matches('[data-wrong-field],[data-wrong-keep]')) remember();
  });
}

window.FamilyWrongReview = {mount, canSwitch};
})();

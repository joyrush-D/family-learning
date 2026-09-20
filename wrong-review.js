// 试卷错题集：拍照/选图 → 模型标注 → 原图同屏核对 → 保存为学习记录。
// 只在家长点击时调用模型；保存前一切都是草稿，刷新不保留。
(() => {
'use strict';
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const uid = () => crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
const KIND_LABEL = {wrong_item: '错题', handwriting: '手写区域', layout: '版面'};
const KIND_COLOR = {wrong_item: '#dc2626', handwriting: '#2563eb', layout: '#16a34a'};
let ctx, root, busy = false;
let state;

function freshState() {
  return {child: '', day: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10),
          subject: '', ids: [], draft: null, review: [], error: '', generation: 0,
          uploadStatus: {type: '', text: ''}};
}

function imageUploads() {
  return (ctx.uploads || []).filter(a => ['image/jpeg', 'image/png', 'image/webp'].includes(a.mime));
}

function html() {
  return `<div class="wrong-wrap">
    <div class="wrong-heading"><div><h1>试卷错题集</h1>
    <p class="muted">拍照或选择已上传的作业/试卷照片（每次1–3张），模型先框出疑似错题，你在原图上逐题核对、修改后才保存为学习记录。</p></div></div>
    <section class="card wrong-setup">
      <div class="formrow">
        <label>孩子<select data-wrong-child required>${['<option value="">请选择</option>', ...(ctx.children || []).map(c => `<option value="${esc(c.name)}" ${state.child === c.name ? 'selected' : ''}>${esc(c.name)}</option>`)].join('')}</select></label>
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
      <p class="error" data-wrong-error role="alert"></p>
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
  remember();
  if (!state.child) return setError('请先选择孩子。');
  if (!state.day) return setError('请填写发生日期。');
  if (!state.ids.length || state.ids.length > 3) return setError('请选择1到3张照片。');
  busy = true; setError('');
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
    const b = root.querySelector('[data-wrong-annotate]'); if (b) b.disabled = false;
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
  try {
    const r = await ctx.apiFetch('/api/wrong/save', {method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Family-Token': ctx.token},
      body: JSON.stringify({child: state.child, day: state.day, subject: state.subject,
                            request_key: uid().slice(0, 32), items})});
    const out = await r.json();
    if (!r.ok) throw new Error(out.error || '保存失败');
    state.draft = null; state.review = []; state.ids = [];
    paint();
    let refreshed=true;try{await ctx.reload?.()}catch{refreshed=false}
    root.querySelector('[data-wrong-result]').innerHTML =
      `<div class="note wrong-saved">已保存 ${out.count} 条错题学习记录，并关联照片原件。<br>可打开原记录关联任务，继续记订正和复测；记录不代表掌握结论。${refreshed?(out.saved||[]).map(r=>`<button type="button" data-record="${esc(r.id)}">关联任务 / 查看原记录</button>`).join(''):'<p>记录已保存，列表暂未更新；请刷新后查看原记录。</p>'}</div>`;
  } catch (e) { setError(e.message || '保存未完成，草稿仍在，请重试。'); }
  finally { busy = false; }
}

function paint() {
  root.innerHTML = html();
  root.querySelector('[data-wrong-pool]').innerHTML = poolHTML();
  if (state.draft) rerenderResult();
  if (busy) root.querySelectorAll('input,select,textarea,button').forEach(el => { el.disabled = true; });
}

function onClick(e) {
  if (busy) return;
  const t = e.target.closest('button');
  if (!t) return;
  if (t.hasAttribute('data-wrong-annotate')) return annotate();
  if (t.hasAttribute('data-wrong-save')) return save();
  if (t.hasAttribute('data-wrong-discard')) { state.draft = null; state.review = []; state.generation++; paint(); }
}

function onChange(e) {
  if (busy) return;
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
  if (e.target.matches('[data-wrong-child],[data-wrong-day],[data-wrong-subject]')) remember();
}

function mount(options) {
  ctx = options;
  root = options.root;
  state = freshState();
  if (options.children?.length === 1 && !state.child) state.child = options.children[0].name;
  paint();
  root.addEventListener('click', onClick);
  root.addEventListener('change', onChange);
  root.addEventListener('input', e => {
    if (busy) return;
    if (e.target.matches('[data-wrong-field],[data-wrong-keep]')) remember();
  });
}

window.FamilyWrongReview = {mount};
})();

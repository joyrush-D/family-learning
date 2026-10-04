"""独立 Agent：逐批整理同孩学校通知明确关联的 PDF、单个复杂 DOCX、静态 PPTX 或简单 XLSX 原件。

- 只处理 QQ 窗口片段或原生文字通知；PDF 最多 3 份、合计 20MiB，每份分别整理；其他页路径仍只收一个原件。
  排除截图本身后与图片、其他格式混合时明确拒绝，不合并 PDF 字节。
- DOCX 只在 docx_text 明确报 draft_docx_unsupported（图片、公式、版式等）时进入本路径：纯文字 DOCX 仍走原草稿路径；
  加密/损坏/宏/外部资源的 DOCX 在原路径被拒绝，这里不选入原件，永不转换。
- DOCX 每轮由 family_media.docx_pdf 重新转换（其自身 60 秒上限），转换 PDF 只在内存中探测与渲染，不缓存、不落表；
  原件仍是原 DOCX，指纹取原始 mime/哈希与完整来源、孩子、消息、授权，不取转换 PDF 的易变元数据。
  转换 PDF 总页数与已保存页组不一致时拒绝并记为可重试失败，不把部分/未知当完整。
- 每轮最多渲染 3 页、最多 1 次 family_llm.extract_draft(school_material=True)；每个页组草稿单独持久保存。
- 总页数、已处理页、未处理页与 complete 全由代码按已保存且校验通过的页组计算，不采信模型声称或损坏行。
- 转换、渲染与模型期间不持数据库锁；转换前、转换后、渲染后、模型返回后各重核来源/孩子/消息/授权/原件哈希与本次领取，
  变化即撤销本次领取并丢弃结果；模型调用前发现变化则 0 调用，旧页组按指纹隐藏，恢复后从已保存页组继续。
- pdfinfo 与页渲染共用一个 20 秒渲染截止（转换之后起算）。view 只读：0 模型、0 LibreOffice、0 pdfinfo/pdftoppm、0 写入；
  草稿不进入任务、学习记录、成绩或计划。
"""
import hashlib
import json
import re
import time

import family_media
import family_pdf
from family_media import DOCX_MIME, PPTX_MIME, XLSX_MIME, SCHOOL_MATERIAL, MediaError, _authorized, _material_kind, docx_text, docx_pdf_preflight, pptx_pdf_preflight, xlsx_pdf_preflight, read_file, require

PDF_MIME = 'application/pdf'
BATCH_PAGES = family_pdf.MAX_REQUESTED_PAGES
ROUND_CALLS = 1
MAX_PDF_DOCUMENTS = 3
FINGERPRINT_VERSION = 3
IMAGE_MIMES = ('image/jpeg', 'image/png', 'image/webp')
ORIGINALS = {PDF_MIME: 'pdf', DOCX_MIME: 'docx', PPTX_MIME: 'pptx', XLSX_MIME: 'xlsx'}
CONVERSION = 'Word原件每轮由本机LibreOffice转换为PDF后逐页整理，转换结果不保存；页码为转换后PDF的页码，可能与Word中显示的分页不同。'
PPTX_CONVERSION = '演示文稿每轮由本机LibreOffice转换为PDF后逐页整理；原件及页序保留，动画、声音和备注不作为已读内容。'
XLSX_CONVERSION = '仅结构简单且一个工作表含可见单元格的表格，由本机转换并核对文字与数值是否出现在PDF；原件保留，家长仍须核对版式和含义。'
EXPLANATIONS = {
    'pdf_multiple': '这条通知关联了多个PDF原件，须按明确原件分别读取，不能任择一份代表全部原件。',
    'pdf_too_many_originals': '这条通知关联了超过3份PDF原件，本次未整理；原件保留，可分开关联或手动核对。',
    'pdf_originals_too_large': '这条通知的PDF原件合计超过20MiB，本次未整理；原件保留，可分开关联或手动核对。',
    'pdf_mixed_originals': 'PDF原件与图片或其他格式原件混在同一条通知，本次未整理；请把PDF单独关联，其他格式仍按原方式整理。',
    'docx_multiple': '这条通知关联了多个DOCX原件，含图片或版式的DOCX一次只整理一个明确原件；请只保留本次要整理的DOCX，其余分次关联或手动记录。本次未读取任何原件。',
    'docx_mixed_originals': '含图片或版式的DOCX原件与图片等其他原件混在同一条通知，本次未读取任何原件；请把该DOCX单独关联，图片仍按原方式整理。',
    'draft_docx_rejected': '这个Word原件含有当前不能安全转换的内容；原件仍保留。可核对原件，或从可信文档另存为PDF后重新关联。',
    'draft_pptx_rejected': '这个演示文稿含有当前不能安全完整转换的内容；原件仍保留。可核对原件，或从可信文档另存为PDF后重新关联。',
    'draft_xlsx_rejected': '这个表格当前不能完整安全转换为可核对页；原件仍保留，请下载原件核对或从可信表格另存为PDF后重新关联。',
    'pptx_multiple': '这条通知关联了多个演示文稿，一次只整理一个明确原件；本次未读取任何原件。',
    'pptx_mixed_originals': '演示文稿和其他原件混在同一条通知，本次未读取任何原件；请分次关联或手动记录。',
    'xlsx_multiple': '这条通知关联了多个表格，一次只整理一个明确原件；本次未读取任何原件。',
    'xlsx_mixed_originals': '表格和其他原件混在同一条通知，本次未读取任何原件；请分次关联或手动记录。',
    'media_file_rejected': '原件超过20MiB或无法读取，本次未读取；原件保留，可手动核对。',
    'pdf_invalid': '该文件不是可读取的PDF，本次未读取；原件保留，可手动核对。',
    '': '当前原件或授权无法完整核对，可保留原件并手动记录。',
}
WAITING = '独立Agent将按每轮最多3页逐批整理该PDF；已整理页组先显示，未处理页明确列出，全部页整理完才算完整。结果只供家长核对，不会改动任务或学习记录。'
FAILED = 'PDF页组整理暂未成功；已整理页组保留，未处理页明确列出，可稍后重试或手动记录。'
WAITING_DOCX = ('独立Agent将把该Word原件由本机LibreOffice转换为PDF，再按每轮最多3页逐批整理；已整理页组先显示，未处理页明确列出，'
                '全部页整理完才算完整。页码为转换后PDF页码。结果只供家长核对，不会改动任务或学习记录。')
FAILED_DOCX = 'Word原件转换或页组整理暂未成功；已整理页组保留，未处理页明确列出，可稍后重试或手动记录。'
WAITING_PPTX = '独立Agent将逐页整理演示文稿；原件保留，只有全部页组核对后才算完整。动画、声音和备注尚未读取。'
FAILED_PPTX = '演示文稿转换或页组整理暂未成功；原件和已整理页组保留，可稍后重试或手动记录。'
WAITING_XLSX = '独立Agent将逐页整理这个表格的可见内容；原件保留，家长须核对表格含义与要求，未整理页不算已读。'
FAILED_XLSX = '表格转换或页组整理暂未成功；原件和已整理页组保留，可稍后重试或手动记录。'


def job_key(source, message, upload_id=None):
    identity = [source['id'], message['id']]
    if upload_id is not None:
        identity.append(upload_id)
    return 'pdf-material:' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:40]


def _document_key(source, message, value):
    return job_key(source, message, value['upload_id'] if value['document_count'] > 1 else None)


def _job_value(fingerprint, done):
    return {'pdf_material': fingerprint, 'done': sorted(done), 'requirements': 2}


def pdf_inputs(store, c, source, message):
    """Current same-child page-path originals, in upload-ID order; an empty list when this path does not own the set.
    PDFs are bounded to three and 20MiB together; other formats keep their single-original and mixed-set refusals.

    Reads files only to hash them and check DOCX structure. Never runs LibreOffice, pdfinfo/pdftoppm or a model."""
    from family_agent import _json
    from family_qq_capture import KIND, NOTICE
    screenshot_kind = _material_kind(message)
    if not screenshot_kind and not (source.get('platform') == 'qq' and message.get('kind') == 'text'):
        return []
    screenshot = re.fullmatch(r'fragment-([a-f0-9]{40})', message.get('id', '')) if screenshot_kind else None
    if screenshot_kind and screenshot is None:
        return []
    associated = [r['upload_id'] for r in c.execute(
        'SELECT upload_id FROM agent_message_attachments WHERE source_id=? AND message_id=? ORDER BY upload_id',
        (source['id'], message['id']))]
    links = [ident for ident in associated if screenshot is None or ident != screenshot.group(1)[:32]]
    if not links:
        return []
    _authorized(store, c, source, message)
    rows = [(ident, store._message_upload(c, source['child_id'], ident)) for ident in links]  # Another child's file raises.
    if _material_kind(message, source, (row['mime'] for _, row in rows)) != SCHOOL_MATERIAL:
        return []

    def same_capture(ident, row):  # The capture uploaded again under another ID is still not an original.
        if screenshot is None or row['mime'] not in IMAGE_MIMES:
            return False
        digest = hashlib.sha256(read_file(store.data / 'uploads' / ident)).hexdigest()
        return hashlib.sha256(_json([KIND, source['id'], source['child_id'], message['text'][len(NOTICE) + 1:],
                                     digest]).encode()).hexdigest()[:40] == screenshot.group(1)

    def body_of(ident, row):
        body = read_file(store.data / 'uploads' / ident, family_pdf.MAX_BODY_BYTES)
        require(len(body) == row['size'], 'media_file_changed')
        return body

    pdfs = [(ident, row) for ident, row in rows if row['mime'] == PDF_MIME]
    if pdfs:
        require(len(pdfs) <= MAX_PDF_DOCUMENTS, 'pdf_too_many_originals')
        require(all(row['mime'] == PDF_MIME or same_capture(ident, row) for ident, row in rows), 'pdf_mixed_originals')
        require(all(type(row['size']) is int and row['size'] > 0 for _, row in pdfs)
                and sum(row['size'] for _, row in pdfs) <= family_pdf.MAX_BODY_BYTES, 'pdf_originals_too_large')
        originals = []
        for ident, row in pdfs:
            body = body_of(ident, row)
            require(body.startswith(b'%PDF-'), 'pdf_invalid')
            originals.append((ident, row, body))
    else:
        presentations = [(ident, row) for ident, row in rows if row['mime'] == PPTX_MIME]
        if presentations:
            require(len(presentations) == 1, 'pptx_multiple')
            require(len(rows) == 1 or all(row['mime'] == PPTX_MIME or same_capture(ident, row)
                                          for ident, row in rows), 'pptx_mixed_originals')
            ident, row = presentations[0]
            body = body_of(ident, row)
            expected_pages = pptx_pdf_preflight(body)
        else:
            workbooks = [(ident, row) for ident, row in rows if row['mime'] == XLSX_MIME]
            if workbooks:
                require(len(workbooks) == 1, 'xlsx_multiple')
                require(all(row['mime'] == XLSX_MIME or same_capture(ident, row) for ident, row in rows),
                        'xlsx_mixed_originals')
                ident, row = workbooks[0]
                body = body_of(ident, row)
                xlsx_pdf_preflight(body)
                expected_pages = None
            else:
                # Plain text DOCX keeps the existing draft path; unsafe files are refused before conversion.
                docxs = [(ident, row) for ident, row in rows if row['mime'] == DOCX_MIME]
                layout = []
                for ident, row in docxs:
                    body = body_of(ident, row)
                    try:
                        docx_text(body)
                    except MediaError as error:
                        if error.code == 'draft_docx_unsupported':
                            layout.append((ident, row, body))
                if not layout:
                    return []  # Pictures and plain-text DOCX stay with the existing school-material draft.
                require(len(docxs) == 1, 'docx_multiple')
                require(all(row['mime'] == DOCX_MIME or same_capture(ident, row) for ident, row in rows), 'docx_mixed_originals')
                ident, row, body = layout[0]
                docx_pdf_preflight(body)  # A permanently refused DOCX must not enter the retrying conversion job.
                expected_pages = None
        originals = [(ident, row, body)]
    child = next(p for p in store.profiles(c) if p['id'] == source['child_id'])
    # A multi-PDF document depends on the whole current set. A change in any sibling invalidates every document;
    # single originals retain exactly the legacy fingerprint so their saved page groups are still usable.
    manifest = [associated, [[ident, row['mime'], row['size'], str(row['name'] or ''), hashlib.sha256(body).hexdigest()]
                             for ident, row, body in originals]]
    linked_originals = [dict(upload_id=ident, name=str(row['name'] or ''), mime=row['mime'])
                        for ident, row, _ in originals]
    values = []
    for ident, row, body in originals:
        original = ORIGINALS[row['mime']]
        identity = [FINGERPRINT_VERSION, SCHOOL_MATERIAL, original, source, child, message,
                    [ident, row['mime'], hashlib.sha256(body).hexdigest()]]
        if len(originals) > 1:
            identity.append(['pdf-set-v1', manifest])
        fingerprint = hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        values.append(dict(fingerprint=fingerprint, body=body, upload_id=ident, name=str(row['name'] or ''), child=child['name'],
                           mime=row['mime'], original=original, expected_pages=expected_pages if original != 'pdf' else None,
                           document_count=len(originals), linked_originals=linked_originals,
                           conversion=CONVERSION if original == 'docx' else PPTX_CONVERSION if original == 'pptx' else XLSX_CONVERSION if original == 'xlsx' else ''))
    return values


def pdf_input(store, c, source, message, upload_id=None):
    """Legacy single-original input, or one explicitly selected current document from the fully checked linked set."""
    values = pdf_inputs(store, c, source, message)
    if upload_id is not None:
        return next((value for value in values if value['upload_id'] == upload_id), None)
    require(len(values) <= 1, 'pdf_multiple')
    return values[0] if values else None


def _rows(c, source, message, fingerprint):
    return c.execute('SELECT first_page,pages,page_count,payload,updated FROM agent_pdf_material WHERE source_id=? AND message_id=? '
                     'AND fingerprint=? ORDER BY first_page', (source['id'], message['id'], fingerprint)).fetchall()


def _batches(rows, upload_id):
    """Saved page groups for the current fingerprint; coverage is computed here, never taken from the model or a damaged row."""
    import family_llm
    batches, done, page_count = [], set(), None
    for row in rows:
        try:
            pages = json.loads(row['pages']); draft = json.loads(row['payload']); count = row['page_count']
            require(isinstance(pages, list) and 0 < len(pages) <= BATCH_PAGES and all(type(p) is int for p in pages)
                    and pages == sorted(set(pages)) and pages[0] == row['first_page'], 'pdf_row_invalid')
            require(type(count) is int and 1 <= pages[0] and pages[-1] <= count <= family_pdf.MAX_DOCUMENT_PAGES, 'pdf_row_invalid')
            require(isinstance(draft, dict) and draft.pop('kind', None) == SCHOOL_MATERIAL, 'draft_kind_mismatch')
            draft.pop('previous_group',None)  # Old payload and timestamp remain history, never current action evidence.
            draft = family_llm.validate_school_material(draft,original_ids=[upload_id] if 'originals' in draft else (),
                                                       require_requirements='originals' in draft,allow_page_scope=True)
            for original in draft.get('originals',[]):
                require(all(set(context['pages'])<=set(range(1,count+1))-set(pages)
                            for context in original.get('deferred_contexts',[])), 'pdf_row_invalid')
        except (ValueError, TypeError, MediaError, family_llm.LLMDraftError):
            continue  # A malformed or foreign row is never shown or counted.
        if page_count is None:
            page_count = count
        if count != page_count or done & set(pages):
            continue
        batches.append(dict(pages=pages, draft=draft, updated=row['updated'])); done |= set(pages)
    return batches, done, page_count


def _pending(done, page_count):
    return [] if page_count is None else [p for p in range(1, page_count + 1) if p not in done]


def _needs_requirements_upgrade(batch):
    draft=batch['draft']
    # Old free-form doubts cannot be deleted by wording or by later page coverage.
    # Only undecided originals are re-read into the explicit scope channel; clear
    # structured groups and all parent decisions retain their existing evidence.
    return ('originals' not in draft or bool(draft.get('uncertainties'))
            and any('deferred_contexts' not in original for original in draft['originals']))


def _document_view(c, source, message, value):
    from family_agent import _hash
    batches, done, page_count = _batches(_rows(c, source, message, value['fingerprint']),value['upload_id'])
    pending = _pending(done, page_count); complete = page_count is not None and not pending
    key = _document_key(source, message, value)
    job = c.execute('SELECT * FROM agent_jobs WHERE id=?', (key,)).fetchone()
    requirements_complete=complete and all('originals' in b['draft'] for b in batches)
    structured_done={p for b in batches if 'originals' in b['draft'] for p in b['pages']}
    failed = bool(job and not job['done'] and job['error'] and job['fingerprint'] in
                  {_hash(_job_value(value['fingerprint'], pages)) for pages in (done,structured_done)})
    state = 'error' if failed else 'ready' if complete else 'pending'
    docx = value['original'] == 'docx'; pptx = value['original'] == 'pptx'; xlsx = value['original'] == 'xlsx'
    return dict(state=state, kind=SCHOOL_MATERIAL, upload_id=value['upload_id'], name=value['name'], mime=value['mime'],
                original=value['original'], conversion=value['conversion'], job_id=key,
                page_count=page_count, processed_pages=sorted(done), pending_pages=pending, complete=complete, batches=batches,
                requirements_complete=requirements_complete,
                explanation=(FAILED_DOCX if docx else FAILED_PPTX if pptx else FAILED_XLSX if xlsx else FAILED) if failed else
                '原件页组已保存；完整行动与完成标准仍待整理。' if complete and not requirements_complete else '' if complete else
                (WAITING_DOCX if docx else WAITING_PPTX if pptx else WAITING_XLSX if xlsx else WAITING))


def _aggregate_fingerprint(values):
    return hashlib.sha256(json.dumps(['pdf-set-v1', [value['fingerprint'] for value in values]]).encode()).hexdigest()


def view(store, c, source, message):
    """Read-only progress for each current original; no model, conversion, page probe, render or write."""
    try:
        values = pdf_inputs(store, c, source, message)
        if not values:
            return None
    except Exception as error:
        code = error.code if isinstance(error, MediaError) else ''
        return dict(state='unavailable', kind=SCHOOL_MATERIAL, explanation=EXPLANATIONS.get(code, EXPLANATIONS['']))
    documents = [_document_view(c, source, message, value) for value in values]
    if len(documents) == 1:
        return documents[0]
    complete = all(document['complete'] for document in documents)
    failed = any(document['state'] == 'error' for document in documents)
    partial = any(document['processed_pages'] for document in documents)
    return dict(state='ready' if complete else 'error' if failed else 'partial' if partial else 'pending',
                kind=SCHOOL_MATERIAL, original='pdf', mime=PDF_MIME, complete=complete,
                fingerprint=_aggregate_fingerprint(values), documents=documents,
                explanation='' if complete else FAILED if failed else WAITING)


def complete_evidence(store, c, source, message):
    """Whole-set evidence only when every current original has validated page groups covering all its pages.
    A single original retains the old evidence dictionary; multiple PDFs return separate document evidence.

    None for no page-path original, a refused or unreadable set, revoked authorization, another child's file, or any
    pending/failed/partial/unknown coverage. Reads the file only to hash it; never runs LibreOffice, pdfinfo/pdftoppm,
    a model or a write."""
    try:
        values = pdf_inputs(store, c, source, message)
    except Exception:
        return None
    if not values:
        return None
    documents = []
    for value in values:
        batches, done, page_count = _batches(_rows(c, source, message, value['fingerprint']),value['upload_id'])
        if page_count is None or _pending(done, page_count):
            return None
        documents.append(dict(fingerprint=value['fingerprint'], upload_id=value['upload_id'], name=value['name'], mime=value['mime'],
                              original=value['original'], conversion=value['conversion'], page_count=page_count, batches=batches))
    return documents[0] if len(documents) == 1 else dict(fingerprint=_aggregate_fingerprint(values), documents=documents)


def _decision_scope(store, c, source, message):
    """Whole-message decisions, including current plans/tasks/feedback; a timestamp alone is not a snapshot."""
    from family_agent import _school_original_known, _school_pending_original
    ref='message:'+source['id']+':'+message['id']
    scope,known=_school_original_known(store,c,dict(child_id=source['child_id'],evidence=json.dumps([dict(ref=ref)])))
    return scope,bool(known) and all(_school_pending_original(row) for row in known)


def _claim_intact(store, c, source, message, value, key, fp):
    """True only while the same authorization, source, child, full message, original bytes and job claim are current."""
    try:
        current = pdf_input(store, c, source, message, upload_id=value['upload_id'])
    except Exception:
        return False  # Revoked, unreadable or now another child's: treated as changed.
    job = c.execute('SELECT fingerprint FROM agent_jobs WHERE id=?', (key,)).fetchone()
    return (current is not None and current['fingerprint'] == value['fingerprint'] and job is not None and job['fingerprint'] == fp
            and _decision_scope(store,c,source,message)[0] == value['decision_scope'])


def _void(c, key, fp):
    """Withdraw this claim rather than complete it: a restored or re-linked original continues from its saved page groups."""
    c.execute('DELETE FROM agent_jobs WHERE id=? AND fingerprint=?', (key, fp))


def prepare(store, now, budget=ROUND_CALLS):
    """One page group of one current original per call; separate document jobs retain bounded retries and sibling fairness."""
    import family_llm
    if budget <= 0:
        return dict(used=0, failed=0)
    selected = None
    with store._db() as c:
        config = store._config(c)
        if not config['enabled']:
            return dict(used=0, failed=0)
        sources = {s['id']: s for s in config['sources'] if s['enabled']}
        # ponytail: 500 linked messages cover the current backfill; add an indexed queue if it grows beyond this.
        rows = c.execute("""SELECT m.source_id,m.payload FROM agent_messages m WHERE EXISTS
            (SELECT 1 FROM agent_message_attachments a WHERE a.source_id=m.source_id AND a.message_id=m.id)
            ORDER BY m.rowid DESC LIMIT 500""").fetchall()
    for row in rows:
        source = sources.get(row['source_id'])
        if source is None:
            continue
        message = json.loads(row['payload'])
        try:
            with store._db() as c:
                values = pdf_inputs(store, c, source, message)
                if not values:
                    continue
                candidates = []
                decision_scope,undecided=_decision_scope(store,c,source,message)
                for value in values:
                    batches, done, page_count = _batches(_rows(c, source, message, value['fingerprint']),value['upload_id'])
                    legacy=[b for b in batches if _needs_requirements_upgrade(b)]
                    if legacy:
                        if undecided:
                            done={p for b in batches if not _needs_requirements_upgrade(b) for p in b['pages']}
                            value['upgrade_pages']=legacy[0]['pages']  # Preserve saved boundaries and all other groups.
                        elif page_count is not None and not _pending(done,page_count):continue
                        # A shared legacy group never changes after any decision. Missing groups retain the original
                        # bounded first-read path, which does not replace the already saved legacy groups.
                    value['decision_scope']=decision_scope
                    if page_count is None or _pending(done, page_count):
                        candidates.append((value, done, page_count))
        except Exception:
            continue  # No conversion, render or model for unreadable, unsupported, or foreign originals.
        # Start unprocessed siblings before extending a long document. Each job keeps its own back-off;
        # a failed or exhausted first document cannot prevent a later current document from being claimed.
        for value, done, page_count in sorted(candidates, key=lambda item: (len(item[1]), item[0]['upload_id'])):
            key = _document_key(source, message, value)
            fp = store._job(key, _job_value(value['fingerprint'], done), now, model=True)
            if fp:
                selected = (source, message, value, done, page_count, key, fp)
                break
        # Release the other bounded original bodies before rendering the selected document.
        values = candidates = None
        if selected is not None:
            break
    if selected is None:
        return dict(used=0, failed=0)
    source, message, value, done, page_count, key, fp = selected
    try:  # No database connection is held from here until each re-check.
        with store._db() as c:  # Re-checked before any conversion or probe: a claim taken a moment ago may already be stale.
            if not _claim_intact(store, c, source, message, value, key, fp):
                _void(c, key, fp)  # Revoked, corrected, unlinked, replaced or lost claim: nothing is converted, probed or sent.
                return dict(used=0, failed=0)
        body = value['body']
        if value['original'] == 'docx':
            # Converted again every round within docx_pdf's own 60-second bound (the accepted cost of keeping no cache or
            # table): the PDF lives in memory only, so nothing stale can be served for a changed original.
            body = family_media.docx_pdf(value['body'])
            with store._db() as c:  # Re-checked after conversion: a revoked, corrected, unlinked or replaced original renders nothing.
                if not _claim_intact(store, c, source, message, value, key, fp):
                    _void(c, key, fp)
                    return dict(used=0, failed=0)
        elif value['original'] == 'pptx':
            body = family_media.pptx_pdf(value['body'])
            with store._db() as c:
                if not _claim_intact(store, c, source, message, value, key, fp):
                    _void(c, key, fp)
                    return dict(used=0, failed=0)
        elif value['original'] == 'xlsx':
            body = family_media.xlsx_pdf(value['body'])
            with store._db() as c:
                if not _claim_intact(store, c, source, message, value, key, fp):
                    _void(c, key, fp)
                    return dict(used=0, failed=0)
        started = time.monotonic()

        def deadline():  # pdfinfo and every rendered page share the one 20-second render budget of family_pdf.
            left = family_pdf.DEADLINE_SECONDS - (time.monotonic() - started)
            require(left > 0, 'pdf_render_timeout')
            return left
        if page_count is None:
            page_count = family_pdf.page_count(body, deadline())
        if value['expected_pages'] is not None:
            require(page_count == value['expected_pages'], 'pptx_page_count_changed')
        pages = value.get('upgrade_pages') or _pending(done, page_count)[:BATCH_PAGES]
        require(pages, 'pdf_material_changed')
        rendered = family_pdf.render_pages(body, pages, deadline())
        # A converted DOCX whose page total differs from the saved groups is refused here, before any model call.
        require(rendered['page_count'] == page_count and [p['page'] for p in rendered['pages']] == pages, 'pdf_page_count_changed')
        with store._db() as c:  # Re-checked after rendering: a revoked, corrected, unlinked or replaced original sends nothing out.
            if not _claim_intact(store, c, source, message, value, key, fp):
                _void(c, key, fp)
                return dict(used=0, failed=0)
        left = [p for p in _pending(done, page_count) if p not in pages]
        text = json.dumps(dict(source_message=message, source_name=source['name'],
                               material_scope=dict(current_upload_id=value['upload_id'], linked_originals=value['linked_originals'],
                                                   sent_pages=pages, processed_pages=sorted(done),unprocessed_pages=left, other_originals_sent=False),
                               original_pdf=dict(upload_id=value['upload_id'], name=value['name'], mime=value['mime'], pages=pages, page_count=page_count,
                                                 unprocessed_pages=left, conversion=value['conversion'])), ensure_ascii=False)
        images = [dict(mime='image/png', data=p['data']) for p in rendered['pages']]
        result = family_llm.extract_draft(text, images, target_child=value['child'], timeout=90, data_path=store.data,
                                          school_material=True,original_ids=[value['upload_id']],original_pages=pages,deferred_pages=left)
        result = family_llm.validate_school_material(result,original_ids=[value['upload_id']],require_requirements=True,
                                                     allow_page_scope=True,deferred_pages=left)
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not _claim_intact(store, c, source, message, value, key, fp):
                _void(c, key, fp)  # Changed while the model ran: drop the result, keep nothing, leave no error.
                return dict(used=1, failed=0)
            saved_rows=_rows(c, source, message, value['fingerprint'])
            batches_now, done_now, count_now = _batches(saved_rows,value['upload_id'])
            if value.get('upgrade_pages'):
                old=next((r for r in saved_rows if r['first_page']==pages[0] and json.loads(r['pages'])==pages),None)
                require(old is not None and any(b['pages']==pages and _needs_requirements_upgrade(b) for b in batches_now), 'pdf_material_changed')
                done_now={p for b in batches_now if not _needs_requirements_upgrade(b) for p in b['pages']}
                result['previous_group']=dict(payload=json.loads(old['payload']),updated=old['updated'],pages=json.loads(old['pages']),page_count=old['page_count'])
            require(count_now in (None, page_count) and not (done_now & set(pages)), 'pdf_material_changed')
            c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?) '
                      'ON CONFLICT(source_id,message_id,fingerprint,first_page) DO UPDATE SET '
                      'pages=excluded.pages,page_count=excluded.page_count,payload=excluded.payload,updated=excluded.updated',
                      (source['id'], message['id'], value['fingerprint'], pages[0], json.dumps(pages), page_count,
                       json.dumps(dict(kind=SCHOOL_MATERIAL, **result), ensure_ascii=False), now.isoformat()))
            c.execute("UPDATE agent_jobs SET done=1,error='',next_try='' WHERE id=? AND fingerprint=?", (key, fp))
        return dict(used=1, failed=0)
    except Exception as error:
        store._fail(key, now, fingerprint=fp, reason=error.code if isinstance(error, MediaError) else 'pdf_material_failed')
        return dict(used=1, failed=1)

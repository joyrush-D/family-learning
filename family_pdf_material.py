"""独立 Agent：逐批理解明确挂回 QQ 截图通知的单个 PDF 原件（后端进度，无 UI）。

- 只处理 QQ 窗口片段通知上、排除截图本身后恰好一个同孩 PDF 原件；多个 PDF 或与图片/DOCX 混合时明确拒绝。
- 每轮最多渲染 3 页、最多 1 次 family_llm.extract_draft(school_material=True)；每个页组草稿单独持久保存。
- 总页数、已处理页、未处理页与 complete 全由代码按已保存且校验通过的页组计算，不采信模型声称或损坏行。
- 渲染与模型期间不持数据库锁；渲染后、模型返回后各重核来源/孩子/消息/授权/原件哈希与本次领取，
  变化即撤销本次领取并丢弃结果（渲染后变化则模型 0 调用），旧页组按指纹隐藏，恢复后从已保存页组继续。
- pdfinfo 与页渲染共用一个 20 秒渲染截止。view 只读：0 模型、0 pdfinfo/pdftoppm、0 写入；草稿不进入任务、学习记录、成绩或计划。
"""
import hashlib
import json
import re
import time

import family_pdf
from family_media import SCHOOL_MATERIAL, MediaError, _authorized, _material_kind, read_file, require

PDF_MIME = 'application/pdf'
BATCH_PAGES = family_pdf.MAX_REQUESTED_PAGES
ROUND_CALLS = 1
FINGERPRINT_VERSION = 3
IMAGE_MIMES = ('image/jpeg', 'image/png', 'image/webp')
EXPLANATIONS = {
    'pdf_multiple': '这条通知关联了多个PDF原件，一次只整理一个明确的PDF；请只保留本次要整理的PDF，其余分次关联或手动记录。本次未读取任何原件。',
    'pdf_mixed_originals': 'PDF原件与图片、DOCX原件混在同一条通知，本次未读取任何原件；请把PDF单独关联，图片和DOCX仍按原方式整理。',
    'media_file_rejected': 'PDF超过20MiB或无法读取，本次未读取；原件保留，可手动核对。',
    'pdf_invalid': '该文件不是可读取的PDF，本次未读取；原件保留，可手动核对。',
    '': '当前原件或授权无法完整核对，可保留原件并手动记录。',
}
WAITING = '独立Agent将按每轮最多3页逐批整理该PDF；已整理页组先显示，未处理页明确列出，全部页整理完才算完整。结果只供家长核对，不会改动任务或学习记录。'
FAILED = 'PDF页组整理暂未成功；已整理页组保留，未处理页明确列出，可稍后重试或手动记录。'


def job_key(source, message):
    return 'pdf-material:' + hashlib.sha256(json.dumps([source['id'], message['id']]).encode()).hexdigest()[:40]


def _job_value(fingerprint, done):
    return {'pdf_material': fingerprint, 'done': sorted(done)}


def pdf_input(store, c, source, message):
    """None when the notice has no PDF original; MediaError when the linked set is not exactly one same-child PDF.

    Reads files only to hash them. Never runs pdfinfo/pdftoppm or a model."""
    from family_agent import _json
    from family_qq_capture import KIND, NOTICE
    if _material_kind(message) != SCHOOL_MATERIAL:
        return None
    screenshot = re.fullmatch(r'fragment-([a-f0-9]{40})', message.get('id', ''))
    if screenshot is None:
        return None
    links = [r['upload_id'] for r in c.execute(
        'SELECT upload_id FROM agent_message_attachments WHERE source_id=? AND message_id=? ORDER BY upload_id',
        (source['id'], message['id'])) if r['upload_id'] != screenshot.group(1)[:32]]
    if not links:
        return None
    _authorized(store, c, source, message)
    rows = [(ident, store._message_upload(c, source['child_id'], ident)) for ident in links]  # Another child's file raises.
    pdfs = [(ident, row) for ident, row in rows if row['mime'] == PDF_MIME]
    if not pdfs:
        return None  # Pictures and DOCX stay with the existing school-material draft.
    require(len(pdfs) == 1, 'pdf_multiple')

    def same_capture(ident, row):  # The capture uploaded again under another ID is still not an original.
        if row['mime'] not in IMAGE_MIMES:
            return False
        digest = hashlib.sha256(read_file(store.data / 'uploads' / ident)).hexdigest()
        return hashlib.sha256(_json([KIND, source['id'], source['child_id'], message['text'][len(NOTICE) + 1:],
                                     digest]).encode()).hexdigest()[:40] == screenshot.group(1)
    require(all(row['mime'] == PDF_MIME or same_capture(ident, row) for ident, row in rows), 'pdf_mixed_originals')
    ident, row = pdfs[0]
    body = read_file(store.data / 'uploads' / ident, family_pdf.MAX_BODY_BYTES)
    require(len(body) == row['size'], 'media_file_changed')
    require(body.startswith(b'%PDF-'), 'pdf_invalid')
    child = next(p for p in store.profiles(c) if p['id'] == source['child_id'])
    original = [ident, row['mime'], hashlib.sha256(body).hexdigest()]
    fingerprint = hashlib.sha256(json.dumps([FINGERPRINT_VERSION, SCHOOL_MATERIAL, 'pdf', source, child, message, original],
                                            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return dict(fingerprint=fingerprint, body=body, upload_id=ident, name=str(row['name'] or ''), child=child['name'])


def _rows(c, source, message, fingerprint):
    return c.execute('SELECT first_page,pages,page_count,payload,updated FROM agent_pdf_material WHERE source_id=? AND message_id=? '
                     'AND fingerprint=? ORDER BY first_page', (source['id'], message['id'], fingerprint)).fetchall()


def _batches(rows):
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
            draft = family_llm.validate_school_material(draft)
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


def view(store, c, source, message):
    """Read-only progress for the parent's message page: no model, no pdfinfo/pdftoppm, no write."""
    from family_agent import _hash
    try:
        value = pdf_input(store, c, source, message)
        if value is None:
            return None
    except Exception as error:
        code = error.code if isinstance(error, MediaError) else ''
        return dict(state='unavailable', kind=SCHOOL_MATERIAL, explanation=EXPLANATIONS.get(code, EXPLANATIONS['']))
    batches, done, page_count = _batches(_rows(c, source, message, value['fingerprint']))
    pending = _pending(done, page_count); complete = page_count is not None and not pending
    key = job_key(source, message)
    job = c.execute('SELECT * FROM agent_jobs WHERE id=?', (key,)).fetchone()
    failed = bool(job and not job['done'] and job['error'] and job['fingerprint'] == _hash(_job_value(value['fingerprint'], done)))
    state = 'ready' if complete else 'error' if failed else 'pending'
    return dict(state=state, kind=SCHOOL_MATERIAL, upload_id=value['upload_id'], name=value['name'], job_id=key,
                page_count=page_count, processed_pages=sorted(done), pending_pages=pending, complete=complete,
                batches=batches, explanation='' if complete else FAILED if failed else WAITING)


def _claim_intact(store, c, source, message, value, key, fp):
    """True only while the same authorization, source, child, full message, original bytes and job claim are current."""
    try:
        current = pdf_input(store, c, source, message)
    except Exception:
        return False  # Revoked, unreadable or now another child's: treated as changed.
    job = c.execute('SELECT fingerprint FROM agent_jobs WHERE id=?', (key,)).fetchone()
    return current is not None and current['fingerprint'] == value['fingerprint'] and job is not None and job['fingerprint'] == fp


def _void(c, key, fp):
    """Withdraw this claim rather than complete it: a restored or re-linked PDF continues from its saved page groups."""
    c.execute('DELETE FROM agent_jobs WHERE id=? AND fingerprint=?', (key, fp))


def prepare(store, now, budget=ROUND_CALLS):
    """One page group of one linked PDF per call, at most one model call; existing jobs bound retries."""
    import family_llm
    if budget <= 0:
        return dict(used=0, failed=0)
    selected = None
    with store._db() as c:
        config = store._config(c)
        if not config['enabled']:
            return dict(used=0, failed=0)
        sources = {s['id']: s for s in config['sources'] if s['enabled']}
        # ponytail: inspect at most 200 linked messages, same bound as the picture drafts.
        rows = c.execute("""SELECT m.source_id,m.payload FROM agent_messages m WHERE EXISTS
            (SELECT 1 FROM agent_message_attachments a WHERE a.source_id=m.source_id AND a.message_id=m.id)
            ORDER BY m.rowid DESC LIMIT 200""").fetchall()
    for row in rows:
        source = sources.get(row['source_id'])
        if source is None:
            continue
        message = json.loads(row['payload'])
        try:
            with store._db() as c:
                value = pdf_input(store, c, source, message)
                if not value:
                    continue
                _, done, page_count = _batches(_rows(c, source, message, value['fingerprint']))
        except Exception:
            continue  # No render or model for unreadable, unsupported, or foreign originals.
        if page_count is not None and not _pending(done, page_count):
            continue  # Every page already has a saved group: nothing is rendered or called again.
        key = job_key(source, message)
        fp = store._job(key, _job_value(value['fingerprint'], done), now, model=True)
        if fp:
            selected = (source, message, value, done, page_count, key, fp)
            break
    if selected is None:
        return dict(used=0, failed=0)
    source, message, value, done, page_count, key, fp = selected
    started = time.monotonic()

    def deadline():  # pdfinfo and every rendered page share the one 20-second render budget of family_pdf.
        left = family_pdf.DEADLINE_SECONDS - (time.monotonic() - started)
        require(left > 0, 'pdf_render_timeout')
        return left
    try:  # No database connection is held from here until each re-check.
        if page_count is None:
            page_count = family_pdf.page_count(value['body'], deadline())
        pages = _pending(done, page_count)[:BATCH_PAGES]
        require(pages, 'pdf_material_changed')
        rendered = family_pdf.render_pages(value['body'], pages, deadline())
        require(rendered['page_count'] == page_count and [p['page'] for p in rendered['pages']] == pages, 'pdf_page_count_changed')
        with store._db() as c:  # Re-checked after rendering: a revoked, corrected, unlinked or replaced original sends nothing out.
            if not _claim_intact(store, c, source, message, value, key, fp):
                _void(c, key, fp)
                return dict(used=0, failed=0)
        left = [p for p in _pending(done, page_count) if p not in pages]
        text = json.dumps(dict(source_message=message, source_name=source['name'],
                               original_pdf=dict(name=value['name'], pages=pages, page_count=page_count, unprocessed_pages=left)),
                          ensure_ascii=False)
        images = [dict(mime='image/png', data=p['data']) for p in rendered['pages']]
        result = family_llm.extract_draft(text, images, target_child=value['child'], timeout=45, data_path=store.data,
                                          school_material=True)
        result = family_llm.validate_school_material(result)  # Re-checked: no score, mastery or record field is ever saved.
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            if not _claim_intact(store, c, source, message, value, key, fp):
                _void(c, key, fp)  # Changed while the model ran: drop the result, keep nothing, leave no error.
                return dict(used=1, failed=0)
            _, done_now, count_now = _batches(_rows(c, source, message, value['fingerprint']))
            require(count_now in (None, page_count) and not (done_now & set(pages)), 'pdf_material_changed')
            c.execute('INSERT INTO agent_pdf_material VALUES(?,?,?,?,?,?,?,?)',
                      (source['id'], message['id'], value['fingerprint'], pages[0], json.dumps(pages), page_count,
                       json.dumps(dict(kind=SCHOOL_MATERIAL, **result), ensure_ascii=False), now.isoformat()))
            c.execute("UPDATE agent_jobs SET done=1,error='',next_try='' WHERE id=? AND fingerprint=?", (key, fp))
        return dict(used=1, failed=0)
    except Exception as error:
        store._fail(key, now, fingerprint=fp, reason=error.code if isinstance(error, MediaError) else 'pdf_material_failed')
        return dict(used=1, failed=1)

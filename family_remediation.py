"""④ 引导讲解：从一道已核对的错题，开一个「短引导」草稿，让孩子重做自己的错题。

不新造对话引擎：复用已有的 family_guided（苏格拉底式——先让孩子表达/尝试，再给一小步提示或一个问题，
绝不给可直接抄交的完整答案，也不宣布掌握）。这里只做「播种」：把错题的题面作为题目、可见订正作为家长参考，
关联回原错题，生成一个**草稿**短引导；家长在既有短引导界面核对参考、再分享给孩子。孩子随后在
family_guided 里重做这道错题、按需取一小步提示，是否独立由既有的提示计数/帮助程度体现。

对接层只读错题记录、不改其语义；教学层的实际引导与验证仍由 family_guided（④）与后续 FSRS 复测（⑤）负责。
"""
import re

# 与 Hermes 的错题入库来源标记一致（family_wrong_review.SOURCE）。
WRONG_SOURCE = '错题照片核对'
_QUESTION_PREFIX = '题面：'
_CORRECTION_PREFIX = '可见订正/正确答案：'


class RemediationError(ValueError):
    def __init__(self, message, status=400, code='invalid_remediation'):
        super().__init__(message); self.status = status; self.code = code


def parse_wrong_note(note):
    """Pull 题面 (question) and 订正 (reference) back out of a saved 错题 note; best-effort."""
    question = reference = ''
    for line in (note or '').split('\n'):
        line = line.strip()
        if line.startswith(_QUESTION_PREFIX):
            question = line[len(_QUESTION_PREFIX):].strip()
        elif line.startswith(_CORRECTION_PREFIX):
            reference = line[len(_CORRECTION_PREFIX):].strip()
    return question, reference


def from_wrong_question(app, obj):
    """Seed a guided (短引导) draft from one reviewed 错题 record. Returns the guided result.

    The draft is NOT shared and its reference is NOT marked checked: the parent confirms the
    reference and shares it in the existing 短引导 UI, then the child re-works the mistake there.
    """
    if not isinstance(obj, dict) or set(obj) - {'child_id', 'record_id', 'request_key'}:
        raise RemediationError('错题引导请求字段不正确')
    child_id = obj.get('child_id')
    if not isinstance(child_id, str) or not child_id:
        raise RemediationError('请选择孩子')
    record_id = obj.get('record_id')
    if not isinstance(record_id, int) or record_id <= 0:
        raise RemediationError('错题记录编号不正确')
    request_key = obj.get('request_key')
    if not isinstance(request_key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', request_key):
        raise RemediationError('提交标识不正确')
    with app.connect() as c:
        prof = next((p for p in app.profiles(c) if p['id'] == child_id), None)
        if prof is None:
            raise RemediationError('请选择孩子')
        row = c.execute('SELECT id,child,subject,title,note,source FROM records WHERE id=?', (record_id,)).fetchone()
        if row is None or row['child'] != prof['name']:
            raise RemediationError('错题记录不存在或不属于该孩子', 404, 'not_found')
        if WRONG_SOURCE not in (row['source'] or ''):
            raise RemediationError('只能对错题记录发起引导')
        # One unshared draft per 错题: a second tap (or a reload) reopens it instead of piling up copies.
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='guided_sessions'").fetchone():
            draft = c.execute("""SELECT id FROM guided_sessions WHERE child_id=? AND related_record_id=? AND state='draft'
                                 AND shared=0 AND ever_shared=0 ORDER BY updated DESC,id LIMIT 1""", (child_id, record_id)).fetchone()
            if draft:
                return dict(ok=True, session_id=draft['id'], reused=True)
        note = row['note'] or ''
        subject = row['subject'] or ''
        title = row['title'] or '错题订正'
    question, reference = parse_wrong_note(note)
    material = dict(child_id=child_id, version=0, request_key=request_key,
                    title=('订正 · ' + title)[:200], subject=subject[:80],
                    question_text=(question or title)[:4000],
                    # Reviewed photos may contain answers or other questions; keep them in the parent record.
                    question_attachments=[],
                    reference_text=reference[:4000], reference_checked=False,
                    related_record_id=record_id, practice_relation='同一道题或同一片段', shared=False)
    return app.guided_store().save_material(material)

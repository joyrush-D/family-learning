"""试卷/作业照片的网页错题核对流程（R14/R18）。

``annotate`` 只在家长点击时把**已上传**的图片发给已配置模型，返回待核对草稿，
不预计算、不落库、不因为打开页面调用模型。``save`` 把家长逐题核对后的错题保存为
普通学习记录（category=学习进展、来源“错题照片核对”），关联照片原件；
不判知识点、错因或掌握程度，后续订正/复测沿用既有学习记录链。
"""
import re
import sqlite3

import family_wrong_questions as fwq

HEX32 = re.compile(r'^[a-f0-9]{32}$')
DAY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
BATCH_KEY = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
IMAGE_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
ANNOTATE_TIMEOUT = 150
MAX_SAVE_ITEMS = 30
SOURCE = '错题照片核对'


class WrongReviewError(ValueError):
    def __init__(self, message, status=400, code='invalid_wrong_review'):
        super().__init__(message)
        self.status = status
        self.code = code


def _text(obj, key, limit, *, required=False, name=None):
    value = obj.get(key, '')
    if not isinstance(value, str) or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise WrongReviewError('%s格式不正确' % (name or key))
    value = value.strip()
    if required and not value:
        raise WrongReviewError('请填写%s' % (name or key))
    if len(value) > limit:
        raise WrongReviewError('%s过长，请缩短后重试' % (name or key))
    return value


class Store:
    def __init__(self, app):
        self.app = app

    def _image_row(self, c, ident):
        if not isinstance(ident, str) or not HEX32.fullmatch(ident):
            raise WrongReviewError('原件编号无法核对')
        row = c.execute('SELECT id,name,size,mime FROM uploads WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise WrongReviewError('照片原件不存在，请重新上传：' + ident[:8])
        if row['mime'] not in IMAGE_MIMES:
            raise WrongReviewError('只支持 JPG、PNG 或 WebP 照片：%s' % row['name'])
        path = self.app.DATA / 'uploads' / ident
        if path.is_symlink() or not path.is_file():
            raise WrongReviewError('照片原件文件不可读取：%s' % row['name'])
        return row, path

    def annotate(self, obj):
        """请求级标注：读取已上传照片字节，调用模型并把照片信息挂回每页结果。"""
        if not isinstance(obj, dict):
            raise WrongReviewError('请求格式不正确')
        attachments = obj.get('attachments')
        if not isinstance(attachments, list) or not 1 <= len(attachments) <= fwq.MAX_IMAGES:
            raise WrongReviewError('每次选择1到%d张照片' % fwq.MAX_IMAGES)
        if len(attachments) != len(set(attachments)):
            raise WrongReviewError('同一张照片不要重复选择')
        subject_hint = _text(obj, 'subject_hint', fwq.LIMITS['subject'])
        child = _text(obj, 'child', 100)
        images = []
        metas = []
        with self.app.connect() as c:
            c.row_factory = sqlite3.Row
            if child:
                names = set(self.app.child_names(c).values())
                if child not in names:
                    raise WrongReviewError('请先选择孩子')
            total = 0
            for ident in attachments:
                row, path = self._image_row(c, ident)
                data = path.read_bytes()
                if not data:
                    raise WrongReviewError('照片为空：%s' % row['name'])
                total += len(data)
                if total > self.app.family_llm.MAX_INPUT:
                    raise WrongReviewError('照片合计超过20MiB，请减少张数')
                images.append(dict(data=data, mime=row['mime']))
                metas.append(dict(id=row['id'], name=row['name'],
                                  url='/upload/' + row['id'], mime=row['mime']))
        draft = fwq.annotate_pages(images, subject_hint=subject_hint,
                                   timeout=ANNOTATE_TIMEOUT)
        if len(draft['pages']) != len(metas):
            raise WrongReviewError('标注页数与照片不一致，请重试')
        for page, meta in zip(draft['pages'], metas):
            page['attachment'] = meta
        draft['subject_hint'] = subject_hint
        return draft

    def save(self, obj):
        """保存家长核对后的错题为学习记录；同一批请求重放幂等。"""
        if not isinstance(obj, dict):
            raise WrongReviewError('请求格式不正确')
        child = _text(obj, 'child', 100, required=True, name='孩子')
        day = _text(obj, 'day', 10, required=True, name='日期')
        if not DAY.fullmatch(day):
            raise WrongReviewError('日期格式不正确')
        subject = _text(obj, 'subject', 80, name='科目')
        batch = _text(obj, 'request_key', 64, required=True, name='提交标识')
        if not BATCH_KEY.fullmatch(batch):
            raise WrongReviewError('提交标识格式不正确')
        items = obj.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_SAVE_ITEMS:
            raise WrongReviewError('每次保存1到%d条错题' % MAX_SAVE_ITEMS)

        parsed = []
        with self.app.connect() as c:
            c.row_factory = sqlite3.Row
            names = set(self.app.child_names(c).values())
            if child not in names:
                raise WrongReviewError('请选择孩子')
            for index, item in enumerate(items, 1):
                if not isinstance(item, dict):
                    raise WrongReviewError('第%d条错题格式不正确' % index)
                attachment = item.get('attachment')
                row, _ = self._image_row(c, attachment)
                label = _text(item, 'label', fwq.LIMITS['label'], name='题号')
                text = _text(item, 'text', fwq.LIMITS['text'], name='题面')
                answer = _text(item, 'answer', fwq.LIMITS['answer'], name='原答案')
                correction = _text(item, 'correction', fwq.LIMITS['correction'], name='订正')
                note_extra = _text(item, 'note', 1000, name='备注')
                topic_hint = _text(item, 'topic_hint', fwq.LIMITS['topic_hint'], name='知识点候选')
                error_hint = _text(item, 'error_hint', fwq.LIMITS['error_hint'], name='错误类型候选')
                if not (label or text or answer or correction):
                    raise WrongReviewError('第%d条错题没有可保存的内容' % index)
                parsed.append(dict(attachment=row['id'], label=label, text=text,
                                   answer=answer, correction=correction, note=note_extra,
                                   topic_hint=topic_hint, error_hint=error_hint))

        saved = []
        for index, item in enumerate(parsed, 1):
            heading = (subject + '错题' if subject else '错题') + ('：' + item['label'] if item['label'] else '')
            if not item['label']:
                heading += '（第%d处）' % index
            lines = []
            if item['text']:
                lines.append('题面：' + item['text'])
            if item['answer']:
                lines.append('学生原答：' + item['answer'])
            if item['correction']:
                lines.append('可见订正/正确答案：' + item['correction'])
            if item['note']:
                lines.append('家长备注：' + item['note'])
            if item['topic_hint']:
                lines.append('知识点（家长核对）：' + item['topic_hint'])
            if item['error_hint']:
                lines.append('错误类型（家长核对）：' + item['error_hint'])
            lines.append('由照片标注生成，家长已核对；这不是掌握程度结论。')
            record = dict(
                child=child, day=day, category='学习进展', subject=subject,
                title=heading[:200], note='\n'.join(lines)[:4000], source=SOURCE,
                attachments=[item['attachment']], followup_kind='',
                request_key=('%s-%02d' % (batch, index))[:128],
            )
            result = self.app.save_record(record)
            saved.append(dict(id=result.get('record_id'),
                              existing=bool(result.get('replayed')), title=heading))
        return dict(ok=True, saved=saved, count=len(saved))

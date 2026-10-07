"""R03/R09/R14/R18/S03 归纳与作答检查质量基线：全虚构场景、事先冻结的独立真值和确定评分。

真值由开发者在任何产品模型调用前写定并提交；模型返回的题号清单或摘要不能用来证明无漏项。
school-a/homework-a 可用于归因与修复，school-b/homework-b 是保留变体，不据其结果改提示或真值。
默认只跑离线检查（含固定假HTTP的证据采集检查，不发产品请求）；`--replay 输出目录 结果文件` 用已存解析回执零调用复放。
默认只跑离线检查。`--live 配置目录 输出目录 角色` 才经产品入口发送真实请求：每案每模型一次，失败不重试；
配置只在本进程内存中使用，用量写入输出目录下隔离的 family.sqlite3，不写回配置目录。
"""
import copy
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

AS_OF = '2026-10-07'  # 周三


def _message(case, n, minute, text, sender, publisher, related=()):
    ref = 'message:synthetic-%s:%d' % (case, n)
    return dict(ref=ref, text=text, time='2026-10-07T19:%02d:00+08:00' % minute, kind='text', source='虚构班级群',
                sender=sender, publisher=publisher, content_incomplete=False, attachments=[],
                related_messages=[ref] + ['message:synthetic-%s:%d' % (case, r) for r in related])


SCHOOL_CASES = {
    'school-a': dict(held_out=False, evidence=[
        _message('school-a', 1, 0, '今天语文作业：1. 背诵《秋夜》第2自然段，明天早读抽查；2. 完成练习册第12页第1-5题，本周五交。',
                 '示例语文老师', 'publisher:synthetic-chinese', (6,)),
        _message('school-a', 2, 5, '数学：口算本第8页全部完成，明天交给课代表。', '示例数学老师', 'publisher:synthetic-math'),
        _message('school-a', 3, 10, '各位家长：请打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章。另外周四学校体检，请孩子穿运动服。',
                 '示例班主任', 'publisher:synthetic-head'),
        _message('school-a', 4, 15, '英语：今晚把Unit 3单词每个抄写两遍，明天交；周五听写Unit 3单词。', '示例英语老师', 'publisher:synthetic-english'),
        _message('school-a', 5, 20, '请问练习册第5题必须做吗？', '示例家长甲', 'publisher:synthetic-parent'),
        _message('school-a', 6, 25, '补充：练习册第5题不用做，只做第1-4题。', '示例语文老师', 'publisher:synthetic-chinese', (1,)),
    ], truth=[
        dict(id='背诵', keys=['背诵', '秋夜'], require=[], due='2026-10-08', purpose='learning', refs=[1]),
        dict(id='练习册1-4', keys=['练习册', '12'], require=[r'1\s*[-–—~至到]\s*4'], due='2026-10-09', purpose='learning', refs=[1, 6]),
        dict(id='口算', keys=['口算', '8'], require=[], due='2026-10-08', purpose='learning', refs=[2]),
        dict(id='告知书', keys=['告知书'], require=['打印', '签字'], forbid_stamp=True, due='2026-10-10', purpose='admin', refs=[3]),
        dict(id='运动服', keys=['运动服'], require=[], due='2026-10-08', purpose='admin', refs=[3]),
        dict(id='抄写', keys=['抄写'], require=['两遍|2遍'], due='2026-10-08', purpose='learning', refs=[4]),
        dict(id='听写', keys=['听写'], require=[], due='2026-10-09', purpose='learning', refs=[4]),
    ], reference_only=[5]),
    'school-b': dict(held_out=True, evidence=[
        _message('school-b', 1, 0, '科学：观察豆芽生长，连续记录3天，下周一（10月12日）带记录表到校。', '示例科学老师', 'publisher:synthetic-science'),
        _message('school-b', 2, 5, '请家长10月9日前打印《视力检查回执》，签字后交回；《学籍信息确认表》需要家长单位盖章，下周三前交。',
                 '示例班主任', 'publisher:synthetic-head'),
        _message('school-b', 3, 10, '语文：写日记一篇，不少于200字，后天交。', '示例语文老师', 'publisher:synthetic-chinese'),
        _message('school-b', 4, 15, '数学练习卷答案见群文件，仅供家长参考。', '示例数学老师', 'publisher:synthetic-math', (5,)),
        _message('school-b', 5, 20, '数学：同步练习第3课，周四交。', '示例数学老师', 'publisher:synthetic-math', (4,)),
    ], truth=[
        dict(id='豆芽', keys=['豆芽'], require=['3天|三天'], due='2026-10-12', purpose='learning', refs=[1]),
        dict(id='视力回执', keys=['视力'], require=['打印', '签字'], due='2026-10-09', purpose='admin', refs=[2]),
        dict(id='学籍盖章', keys=['学籍'], require=['盖章'], due='2026-10-14', purpose='admin', refs=[2]),
        dict(id='日记', keys=['日记'], require=['200'], due='2026-10-09', purpose='learning', refs=[3]),
        dict(id='同步练习', keys=['同步练习'], require=['3'], due='2026-10-08', purpose='learning', refs=[5]),
    ], reference_only=[4]),
}

HOMEWORK_CASES = {
    'homework-a': dict(held_out=False, question=dict(name='四年级数学练习-虚构.txt', text='''四年级数学练习（虚构）
1. 36 + 47 = ____
孩子作答：83
2. 9 × 7 = ____
孩子作答：56
3. 一根绳子长12米，剪去5米，还剩几米？
孩子作答：
4. 下面哪个数是偶数？ A. 15  B. 27  C. 34  D. 41
孩子作答：C
5. 100 - 38 = ____
孩子作答：72
6. 用一句话说明：为什么长方形的两组对边相等？
孩子作答：因为它是长方形。
'''), reference=dict(name='教师参考答案-虚构.txt', text='''教师参考答案（虚构）
1. 83
2. 63
3. 7米
4. C
5. 62
6. 长方形两组对边分别平行且相等；答出“对边平行且相等”的性质即可。
'''), truth=[
        dict(section=0, number=1, judgments=['correct'], source='teacher'),
        dict(section=0, number=2, judgments=['incorrect'], source='teacher'),
        dict(section=0, number=3, judgments=['unknown'], source='teacher'),  # 未作答
        dict(section=0, number=4, judgments=['correct'], source='teacher'),
        dict(section=0, number=5, judgments=['incorrect'], source='teacher'),
        dict(section=0, number=6, judgments=['incorrect', 'unknown'], source='teacher'),  # 循环论证，不能判对
    ]),
    'homework-b': dict(held_out=True, question=dict(name='二年级语文小测-虚构.txt', text='''二年级语文小测（虚构）
一、看拼音写词语
1. chūn tiān（    ）
孩子作答：春天
2. huā duǒ（    ）
孩子作答：花朵
3. péng yǒu（    ）
孩子作答：明友
二、选择正确的字填空
1. （  ）天来了。 A. 春  B. 椿
孩子作答：A
2. 小鸟在（  ）上唱歌。 A. 树  B. 竖
孩子作答：B
3. 我们（  ）起读书。 A. 一  B. 衣
孩子作答：
'''), reference=dict(name='语文小测参考-虚构.txt', text='''教师参考（只含第一大题）
一、1. 春天  2. 花朵  3. 朋友
'''), truth=[
        dict(section=1, number=1, judgments=['correct'], source='teacher'),
        dict(section=1, number=2, judgments=['correct'], source='teacher'),
        dict(section=1, number=3, judgments=['incorrect'], source='teacher'),
        dict(section=2, number=1, judgments=['correct'], source='ai'),  # 教师参考未覆盖第二大题
        dict(section=2, number=2, judgments=['incorrect'], source='ai'),
        dict(section=2, number=3, judgments=['unknown'], source='ai'),  # 未作答
    ]),
}

STAMP_EXEMPT = re.compile(r'(不需要|无需|不用|不必|不需|免)盖章')

# 2026-10-07 续接：首轮评分只看关键词、日期和必需引用，未读 plan.school_task 的状态/用途，也不看作答内容，
# 已被独立反证（全部 dismissed、purpose 缺失、外来源引用、否定要求仍得满分）；原8份回执里的旧 score 字段保留但作废。
# 以下判据只依据冻结原件追加，不改上方首轮冻结真值，也不依据任何模型回答。
SCHOOL_CHECKS = {
    'school-a': {'练习册1-4': [r'5题[^。；\n]{0,6}(必须|必做|要做|仍需)'],
                 '告知书': [r'(不|无需|不用|不必|免)(需要)?(打印|签字)']},
    'school-b': {'视力回执': [r'(不|无需|不用|不必|免)(需要)?(打印|签字)'],
                 '学籍盖章': [r'(不|无需|不用|不必|免)(需要)?盖章']},
}
HOMEWORK_CONTENT = {  # 原件中明确的题面、孩子原答与教师参考/简单推导；客观题核完整值，None 表示未作答
    'homework-a': {(0, 1): dict(question=r'36\+47', student=('num', '83'), answer=('num', '83'), kind='objective'),
                   (0, 2): dict(question=r'9[×xX*]7', student=('num', '56'), answer=('num', '63'), kind='objective'),
                   (0, 3): dict(question=r'12米', student=None, answer=('num', '7'), kind='objective'),
                   (0, 4): dict(question=r'偶数', student=('choice', 'C', '34'), answer=('choice', 'C', '34'), kind='objective'),
                   (0, 5): dict(question=r'100-38', student=('num', '72'), answer=('num', '62'), kind='objective'),
                   (0, 6): dict(question=r'长方形', student=('text', '因为它是长方形'), answer=('text', '平行且相等'), kind='subjective')},
    'homework-b': {(1, 1): dict(question=r'chūntiān', student=('word', '春天'), answer=('word', '春天'), kind='objective'),
                   (1, 2): dict(question=r'huāduǒ', student=('word', '花朵'), answer=('word', '花朵'), kind='objective'),
                   (1, 3): dict(question=r'péngyǒu', student=('word', '明友'), answer=('word', '朋友'), kind='objective'),
                   (2, 1): dict(question=r'天来了', student=('choice', 'A', '春'), answer=('choice', 'A', '春'), kind='objective'),
                   (2, 2): dict(question=r'唱歌', student=('choice', 'B', '竖'), answer=('choice', 'A', '树'), kind='objective'),
                   (2, 3): dict(question=r'读书', student=None, answer=('choice', 'A', '一'), kind='objective')},
}


def _value_ok(spec, text):
    """Whole objective value: one final number, one option letter or the exact word; subjective keeps the frozen requirement."""
    kind, value = spec[0], spec[1]
    text = re.sub(r'[。.；;，,]+$', '', re.sub(r'\s+', '', str(text or '')))
    if kind == 'num':
        return re.findall(r'\d+(?:\.\d+)?', text.rsplit('=', 1)[-1]) == [value]
    if kind == 'choice':
        letters = set(re.findall(r'(?<![A-Za-z])[A-H](?![A-Za-z])', text))
        return letters == {value} if letters else text == spec[2]
    if kind == 'word':
        return re.sub(r'[（(][^）)]*[）)]', '', text) == value
    return bool(re.search(value, text))


USABLE = ('ready', 'review')


def school_rows(items, raw=False):
    rows = []
    for item in items or []:
        if raw:
            text = '\n'.join(str(item.get(k, '')) for k in ('task_title', 'task_goal'))
            purpose, state, reason = item.get('task_purpose'), item.get('task_state'), item.get('task_reason', '')
        else:
            task = (item.get('plan') or {}).get('school_task') or {}
            text = '\n'.join(str(item.get(k, '')) for k in ('title', 'body'))
            purpose, state, reason = task.get('purpose'), task.get('state'), task.get('reason', '')
        refs = [e.get('ref') if isinstance(e, dict) else e for e in item.get('evidence') or []]
        rows.append(dict(text=text, due=item.get('due', ''), purpose=purpose, state=state, reason=reason or '', refs=refs))
    return rows


def score_school(name, rows):
    case = SCHOOL_CASES[name]
    prefix = 'message:synthetic-%s:' % name
    publisher = {e['ref']: e['publisher'] for e in case['evidence']}
    reference_refs = {prefix + str(r) for r in case['reference_only']}
    result = dict(missed=[], unusable=[], review=[], due_errors=[], purpose_errors=[], requirement_errors=[],
                  citation_errors=[], reference_errors=[], extra=[], extra_reference=[])
    used = set()
    for truth in case['truth']:
        tag = truth['id']
        n = next((n for n, row in enumerate(rows) if n not in used and all(k in row['text'] for k in truth['keys'])), None)
        if n is None: result['missed'].append(tag); continue
        used.add(n); row = rows[n]
        if row['state'] not in USABLE: result['unusable'].append('%s:%s' % (tag, row['state']))
        elif row['state'] == 'review': result['review'].append('%s:%s' % (tag, row['reason'][-70:]))
        if row['due'] != truth['due']: result['due_errors'].append('%s:%s≠%s' % (tag, row['due'] or '无', truth['due']))
        if row['purpose'] != truth['purpose']: result['purpose_errors'].append('%s:%s≠%s' % (tag, row['purpose'], truth['purpose']))
        if (any(not re.search(p, row['text']) for p in truth['require'])
                or truth.get('forbid_stamp') and '盖章' in STAMP_EXEMPT.sub('', row['text'])
                or any(re.search(p, row['text']) for p in SCHOOL_CHECKS.get(name, {}).get(tag, ()))):
            result['requirement_errors'].append(tag)
        expected = {prefix + str(r) for r in truth['refs']}
        if not expected <= set(row['refs']) or any(publisher.get(r) not in {publisher[x] for x in expected} for r in row['refs']):
            result['citation_errors'].append('%s:%s' % (tag, [r.rsplit(':', 1)[-1] for r in row['refs']]))
    for ref in sorted(reference_refs):
        citing = [n for n, row in enumerate(rows) if ref in row['refs']]
        if not any(rows[n]['state'] == 'reference' for n in citing):
            result['reference_errors'].append(ref.rsplit(':', 1)[-1] + ':未作参考保留')
        for n in citing:
            if n in used: continue
            if rows[n]['state'] == 'reference': used.add(n)
            elif set(rows[n]['refs']) <= reference_refs:
                result['reference_errors'].append(ref.rsplit(':', 1)[-1] + ':成了%s事项' % rows[n]['state']); used.add(n)
    for n, row in enumerate(rows):
        if n not in used:
            result['extra_reference' if row['state'] == 'reference' else 'extra'].append('%s:%s' % (row['state'], row['text'][:30]))
    result['total'] = len(case['truth'])
    result['covered'] = result['total'] - len(result['missed'])
    result['usable'] = result['covered'] - len(result['unusable'])
    result['ready'] = result['usable'] - len(result['review'])
    result['passed'] = not any(result[k] for k in ('missed', 'unusable', 'due_errors', 'purpose_errors', 'requirement_errors',
                                                    'citation_errors', 'reference_errors', 'extra'))
    return result


SECTION = {'一': 1, '二': 2, '三': 3}


def parse_label(label, sectioned):
    numbers = [int(x) for x in re.findall(r'\d+', label)]
    if not sectioned:
        return (0, numbers[0]) if numbers else None
    section = next((SECTION[ch] for ch in ('二', '一', '三') if re.search('第?' + ch + '[、.．大部分题]', label)), None)
    if section is None and len(numbers) >= 2: section, numbers = numbers[0], numbers[1:]
    return (section, numbers[0]) if section and numbers else None


def _flat(value):
    return re.sub(r'\s+', '', str(value or ''))


def score_homework(name, questions):
    case = HOMEWORK_CASES[name]
    sectioned = any(t['section'] for t in case['truth'])
    found, extra = {}, []
    for item in questions or []:
        key = parse_label(str(item.get('label', '')), sectioned)
        if key is None or key in found: extra.append(str(item.get('label', ''))[:40]); continue
        found[key] = item
    result = dict(missed=[], wrong_judgment=[], undetermined=[], source_errors=[], ai_unlabeled=[], content_errors=[],
                  unanswered_kept=[], extra=extra)
    for truth in case['truth']:
        key = (truth['section'], truth['number']); tag = '%s-%s' % key if sectioned else str(truth['number'])
        item = found.pop(key, None)
        if item is None: result['missed'].append(tag); continue
        judgment = item.get('judgment'); answer_text = str(item.get('answer', '')).strip()
        if judgment not in truth['judgments']:
            (result['undetermined'] if judgment == 'unknown' else result['wrong_judgment']).append(
                '%s:%s≠%s' % (tag, judgment, '/'.join(truth['judgments'])))
        if judgment in ('correct', 'incorrect'):
            teacher = answer_text.startswith('教师参考：')
            if teacher != (truth['source'] == 'teacher'): result['source_errors'].append(tag)
            if truth['source'] == 'ai' and not answer_text.startswith('AI自行推导：'): result['ai_unlabeled'].append(tag)
        content = HOMEWORK_CONTENT[name][key]
        question, student = _flat(item.get('question')), _flat(item.get('student_answer')).rstrip('。.；;')
        answer = re.sub(r'^(教师参考|AI自行推导)：', '', answer_text)
        if not question: result['content_errors'].append(tag + ':题面缺失')
        elif not re.search(content['question'], question): result['content_errors'].append(tag + ':题面不符')
        if content['student'] is None:
            if student: result['content_errors'].append(tag + ':未作答却填了原答')
            elif judgment == 'unknown': result['unanswered_kept'].append(tag)
        elif not _value_ok(content['student'], student): result['content_errors'].append(tag + ':原答不符')
        if (judgment in ('correct', 'incorrect') or answer.strip()) and not _value_ok(content['answer'], answer):
            result['content_errors'].append(tag + ':答案不符')
        if item.get('question_kind') in ('objective', 'subjective') and item['question_kind'] != content['kind']:
            result['content_errors'].append(tag + ':题型不符')
    result['extra'] += ['%s-%s' % key for key in found]
    result['total'] = len(case['truth'])
    result['covered'] = result['total'] - len(result['missed'])
    result['passed'] = not any(result[k] for k in ('missed', 'wrong_judgment', 'undetermined', 'source_errors', 'ai_unlabeled',
                                                    'content_errors', 'extra'))
    return result


def run_case(name, data_path):
    import family_agent
    import family_llm
    if name in SCHOOL_CASES:
        return family_agent._select('school', copy.deepcopy(SCHOOL_CASES[name]['evidence']), school_goals=[],
                                    as_of=AS_OF, data_path=data_path)
    case = HOMEWORK_CASES[name]
    return family_llm.homework_reference_draft([], review=True, question_documents=[dict(case['question'])],
                                               reference_documents=[dict(case['reference'])], data_path=data_path)


def score(name, final, raw):
    if name in SCHOOL_CASES:
        return dict(raw=score_school(name, school_rows((raw or {}).get('proposals'), raw=True)) if raw else None,
                    final=score_school(name, school_rows(final)) if final is not None else None)
    return dict(raw=score_homework(name, (raw or {}).get('items')) if raw else None,
                final=score_homework(name, final.get('questions')) if final else None)


def _input_hash(messages, schema, task):
    return hashlib.sha256(json.dumps([messages, schema, task], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class _Recorder:
    """Keeps the exact request body and HTTP response of one explicit run; never headers, key or endpoint."""

    def __init__(self, opener, sink):
        self.opener, self.sink = opener, sink

    def open(self, request, timeout=None):
        import family_llm
        self.sink['request_body'] = json.loads(request.data.decode('utf-8'))
        try:
            response = self.opener.open(request, timeout=timeout)
        except HTTPError as error:
            body = error.read() if error.fp else b''
            self.sink.update(http_status=error.code, response_body=body.decode('utf-8', 'replace'))
            raise HTTPError('', error.code, str(error.msg), error.hdrs, io.BytesIO(body)) from None
        except Exception as error:
            self.sink['transport_failure'] = type(error).__name__
            raise
        with response:
            raw = response.read(family_llm.MAX_RESPONSE + 1)
        self.sink.update(http_status=getattr(response, 'status', None), response_body=raw.decode('utf-8', 'replace'))
        return io.BytesIO(raw)


def _ledger_rows(path):
    if not path.exists(): return [], '未建台账文件：请求未发出'
    with sqlite3.connect(path) as db:
        db.row_factory = sqlite3.Row
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='llm_usage_ledger'").fetchone():
            return [], '无台账表：请求未发出'
        return [dict(r) for r in db.execute('SELECT * FROM llm_usage_ledger ORDER BY id')], ''


def live(config_dir, out_dir, role, names):
    """One request per case for one configured model; failures are kept, never retried or overwritten."""
    import family_llm
    out = Path(out_dir)
    existing = [p.name for n in names for p in (out / (n + '-' + role + '.json'), out / (n + '-' + role + '-data'),
                                                 out / (n + '-' + role + '.started')) if p.exists()]
    if existing:
        raise SystemExit('已有本角色输出或启动标记，未发送任何请求，原证据保留：' + '、'.join(existing))
    config = family_llm.model_values(config_dir)
    model = config['model' if role == 'strong' else 'light_model'].strip()
    out.mkdir(parents=True, exist_ok=True)
    for name in names:
        path = out / (name + '-' + role + '.json')
        record = dict(case=name, role=role, requested_model=model, reasoning_effort=config['reasoning_effort'],
                      held_out=(SCHOOL_CASES.get(name) or HOMEWORK_CASES[name])['held_out'])
        if not model:
            record.update(error='未配置该角色模型，未发送请求')
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1)); continue
        (out / (name + '-' + role + '.started')).write_text(time.strftime('%Y-%m-%dT%H:%M:%S%z'))
        data = out / (name + '-' + role + '-data'); data.mkdir()
        captured, http, final, error = {}, {}, None, ''
        real_chat, real_build = family_llm._chat_json, family_llm.build_opener

        def capture(messages, schema, task, timeout=60, *, data_path=None):
            captured.update(task=task, timeout=timeout, input_sha256=_input_hash(messages, schema, task))
            try:
                draft = real_chat(messages, schema, task, timeout, data_path=data_path)
            except Exception as exc:
                captured['transport_error'] = '%s: %s' % (type(exc).__name__, exc); raise
            captured['raw_model_output'] = copy.deepcopy(draft)
            return draft
        env = {'FAMILY_LLM_BASE_URL': config['base_url'], 'FAMILY_LLM_MODEL': model, 'FAMILY_LLM_LIGHT_MODEL': '',
               'FAMILY_LLM_API_KEY': config['api_key'], 'FAMILY_LLM_REASONING_EFFORT': config['reasoning_effort']}
        started = time.monotonic()
        try:
            with patch.dict(os.environ, env), patch.object(family_llm, '_chat_json', capture), \
                    patch.object(family_llm, 'build_opener', lambda *handlers: _Recorder(real_build(*handlers), http)):
                try:
                    final = run_case(name, str(data))
                except Exception as exc:
                    error = '%s: %s' % (type(exc).__name__, exc)
        finally:
            record['wall_ms'] = round((time.monotonic() - started) * 1000)
            record['ledger'], record['ledger_note'] = _ledger_rows(data / 'family.sqlite3')
            record.update(captured=captured, http=http, final=final, error=error)
            try:
                record['score'] = score(name, final, captured.get('raw_model_output'))
            except Exception as exc:
                record['score_error'] = '%s: %s' % (type(exc).__name__, exc)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str))


def replay(out_dir):
    """Zero-call replay of saved parsed replies through the current program; original records are not touched."""
    import family_llm

    def no_network(*args, **kwargs):
        raise AssertionError('复放不得建立网络连接')
    results = []
    for path in sorted(Path(out_dir).glob('*-*.json')):
        if path.name.startswith('replay'): continue
        record = json.loads(path.read_text())
        raw = (record.get('captured') or {}).get('raw_model_output')
        entry = dict(case=record['case'], role=record['role'], original_error=record.get('error', ''),
                     original_input_sha256=(record.get('captured') or {}).get('input_sha256'))
        if raw is None:
            entry.update(replayed=False, note='原调用没有解析回执，不复放；完整HTTP原体当时未保存'); results.append(entry); continue
        seen = {}

        def fixed(messages, schema, task, timeout=60, *, data_path=None):
            seen['input_sha256'] = _input_hash(messages, schema, task)
            return copy.deepcopy(raw)
        final, error = None, ''
        with patch.object(family_llm, '_chat_json', fixed), patch.object(family_llm, 'build_opener', no_network):
            try:
                final = run_case(record['case'], None)
            except Exception as exc:
                error = '%s: %s' % (type(exc).__name__, exc)
        entry.update(replayed=True, input_sha256=seen.get('input_sha256'),
                     same_input=seen.get('input_sha256') == entry['original_input_sha256'], error=error, final=final,
                     score=score(record['case'], final, raw))
        results.append(entry)
    return results


def replay_ingest(out_dir):
    """Saved school replies through Store.ingest -> run_once with zero model calls; originals stay untouched."""
    import family_llm
    results = []
    for path in sorted(Path(out_dir).glob('school-*-*.json')):
        record = json.loads(path.read_text()); raw = (record.get('captured') or {}).get('raw_model_output')
        entry = dict(case=record['case'], role=record['role'], original_input_sha256=(record.get('captured') or {}).get('input_sha256'))
        if raw is None:
            entry.update(replayed=False, note='原调用没有解析回执，不复放；完整HTTP原体当时未保存'); results.append(entry); continue
        with patch.object(family_llm, 'build_opener', side_effect=AssertionError('复放不得联网')):
            run = ingest_school(record['case'], raw, runs=2)
        entry.update(replayed=True, ref_map=run['ref_map'], calls=run['calls'], counts=run['counts'], results=run['results'],
                     input_changed=[call['input_sha256'] != entry['original_input_sha256'] for call in run['calls']],
                     items=run['items'], score=score_school(record['case'], school_rows(run['items'])))
        results.append(entry)
    return results


def _school_a_reply():
    rows = [('语文：背诵《秋夜》第2自然段', '背诵《秋夜》第2自然段，明天早读抽查。', '2026-10-08', 'learning', '背诵《秋夜》第2自然段，明天早读抽查', [1]),
            ('语文：练习册第12页第1-4题', '完成练习册第12页第1-4题，第5题不用做；本周五交。', '2026-10-09', 'learning', '完成练习册第12页第1-5题，本周五交', [1, 6]),
            ('数学：口算本第8页', '口算本第8页全部完成，明天交给课代表。', '2026-10-08', 'learning', '口算本第8页全部完成，明天交给课代表', [2]),
            ('打印并签字交回秋游安全告知书', '打印《秋游安全告知书》，家长签字后10月10日前交回班主任；不需要盖章。', '2026-10-10', 'admin',
             '请打印《秋游安全告知书》，家长签字后于10月10日前交回班主任，不需要盖章', [3]),
            ('周四体检穿运动服', '周四学校体检，孩子穿运动服。', '2026-10-08', 'admin', '另外周四学校体检，请孩子穿运动服', [3]),
            ('英语：Unit 3单词抄写两遍', '今晚把Unit 3单词每个抄写两遍，明天交。', '2026-10-08', 'learning', '今晚把Unit 3单词每个抄写两遍，明天交', [4]),
            ('英语：周五听写Unit 3单词', '周五听写Unit 3单词。', '2026-10-09', 'learning', '周五听写Unit 3单词', [4]),
            ('家长询问第5题', '家长提问，没有新增要求。', '', 'optional', '请问练习册第5题必须做吗？', [5])]
    return [dict(title_quote=quote, focus='school', due=due, evidence=[dict(ref='message:synthetic-school-a:%d' % r) for r in refs],
                 learning_subject=title.split('：')[0] if purpose == 'learning' else '', learning_goal_id='', task_title=title,
                 task_goal=goal, task_advice='', task_state='reference' if refs == [5] else 'ready', task_reason='原文明确。',
                 task_change='new', task_target_id='', task_purpose=purpose, task_submission='')
            for title, goal, due, purpose, quote, refs in rows]


def _homework_reply(name, wrong=False):
    texts = {'homework-a': [('36 + 47 = ____', '83', '教师参考：83', ''), ('9 × 7 = ____', '56', '教师参考：63', '9×7=63，作答56与教师参考不同'),
                            ('一根绳子长12米，剪去5米，还剩几米？', '', '', ''), ('下面哪个数是偶数？ A. 15  B. 27  C. 34  D. 41', 'C', '教师参考：C', ''),
                            ('100 - 38 = ____', '72', '教师参考：62', '100-38=62，作答72与教师参考不同'),
                            ('用一句话说明：为什么长方形的两组对边相等？', '因为它是长方形。', '教师参考：长方形两组对边分别平行且相等', '只重复“它是长方形”，没有说明对边平行且相等')],
             'homework-b': [('chūn tiān（    ）', '春天', '教师参考：春天', ''), ('huā duǒ（    ）', '花朵', '教师参考：花朵', ''),
                            ('péng yǒu（    ）', '明友', '教师参考：朋友', '“朋”写成了“明”'), ('（  ）天来了。 A. 春  B. 椿', 'A', 'AI自行推导：A（春）', ''),
                            ('小鸟在（  ）上唱歌。 A. 树  B. 竖', 'B', 'AI自行推导：A（树）', '“树”才是树木，选B不对'), ('我们（  ）起读书。 A. 一  B. 衣', '', '', '')]}[name]
    case = HOMEWORK_CASES[name]; sectioned = any(t['section'] for t in case['truth']); labels, items = [], []
    for t, (question, student, answer, reason) in zip(case['truth'], texts):
        label = ('%s、第%d题' % ('一二'[t['section'] - 1], t['number']) if sectioned else '第%d题' % t['number'])
        if wrong: question, student, answer = '错题面', ('错答' if student else ''), (answer[:answer.find('：') + 1] + '错误答案' if answer else '')
        labels.append(label)
        items.append(dict(label=label, question=question, student_answer=student, answer=answer, judgment=t['judgments'][0],
                          error_reason=reason, possible_cause='', steps='', uncertainty='' if student else '未作答，待孩子补做后再核',
                          question_kind=HOMEWORK_CONTENT[name][(t['section'], t['number'])]['kind']))
    return dict(items=items, coverage='已按文字原件核对全部题号。', comparison='', question_labels=labels)


class FrozenTruthTest(unittest.TestCase):
    def test_truth_refs_and_keys_exist_in_material(self):
        for name, case in SCHOOL_CASES.items():
            texts = {int(e['ref'].rsplit(':', 1)[1]): e['text'] for e in case['evidence']}
            for truth in case['truth']:
                self.assertTrue(all(r in texts for r in truth['refs']), truth['id'])
                self.assertTrue(any(k in texts[truth['refs'][0]] for k in truth['keys']), truth['id'])
            self.assertTrue(set(case['reference_only']) <= set(texts))

    def test_perfect_rows_score_clean_and_omissions_are_counted(self):
        for name, case in SCHOOL_CASES.items():
            rows = [dict(text=' '.join(t['keys'] + [p.split('|')[0].replace(r'\s*[-–—~至到]\s*', '-') for p in t['require']]),
                         due=t['due'], purpose=t['purpose'], state='ready',
                         refs=['message:synthetic-%s:%d' % (name, r) for r in t['refs']]) for t in case['truth']]
            result = score_school(name, rows)
            self.assertEqual(result['covered'], result['total'], (name, result))
            self.assertFalse(any(result[k] for k in ('due_errors', 'purpose_errors', 'requirement_errors', 'citation_errors', 'extra')), result)
            self.assertEqual(score_school(name, rows[1:])['missed'], [case['truth'][0]['id']])
        stamped = score_school('school-a', [dict(text='告知书 打印 签字 盖章', due='2026-10-10', purpose='admin', state='ready',
                                                 refs=['message:synthetic-school-a:3'])])
        self.assertEqual(stamped['requirement_errors'], ['告知书'])

    def test_homework_labels_sources_and_unknowns(self):
        for name, case in HOMEWORK_CASES.items():
            sectioned = any(t['section'] for t in case['truth'])
            questions = [dict(label=('第%s大题第%d题' % ('一二'[t['section'] - 1], t['number']) if sectioned else '第%d题' % t['number']),
                              judgment=t['judgments'][0], answer=('教师参考：x' if t['source'] == 'teacher' else 'AI自行推导：x'))
                         for t in case['truth']]
            result = score_homework(name, questions)
            self.assertEqual((result['covered'], result['wrong_judgment'], result['source_errors'], result['extra']),
                             (len(case['truth']), [], [], []), result)
        self.assertEqual(parse_label('二、2', True), (2, 2))
        self.assertEqual(parse_label('第一大题 3', True), (1, 3))
        bad = score_homework('homework-b', [dict(label='二、1', judgment='correct', answer='教师参考：A')])
        self.assertEqual((bad['source_errors'], len(bad['missed'])), (['2-1'], 5))


class ProgramPathTest(unittest.TestCase):
    """A reply that already matches truth must survive validation (separates program from model)."""

    def test_truthful_answer_check_reply_keeps_every_frozen_result(self):
        import family_llm
        for name in HOMEWORK_CASES:
            with patch.object(family_llm, '_chat_json', return_value=_homework_reply(name)):
                result = score_homework(name, run_case(name, None)['questions'])
            self.assertTrue(result['passed'], (name, result))
            self.assertEqual(len(result['unanswered_kept']), 1, result)
            with patch.object(family_llm, '_chat_json', return_value=_homework_reply(name, wrong=True)):
                wrong = score_homework(name, run_case(name, None)['questions'])
            # 首轮判据（题号/判定/来源前缀）对全错内容仍无错；内容判据必须失败。
            self.assertEqual((wrong['covered'], wrong['wrong_judgment'], wrong['source_errors']), (6, [], []))
            self.assertFalse(wrong['passed']); self.assertGreaterEqual(len(wrong['content_errors']), 6, wrong)

    def test_truthful_school_reply_citing_later_same_teacher_change_is_kept(self):
        # school-a: a numbered list, then the same teacher later says question 5 is no longer required.
        texts = {e['ref']: e['text'] for e in SCHOOL_CASES['school-a']['evidence']}
        proposals = _school_a_reply()
        self.assertTrue(all(p['title_quote'] in texts[p['evidence'][0]['ref']] for p in proposals))
        result = score_school('school-a', school_rows(_select_school_a(proposals)))
        self.assertEqual((result['covered'], result['usable'], result['missed']), (7, 7, []), result)
        for key in ('purpose_errors', 'requirement_errors', 'citation_errors', 'reference_errors', 'extra'):
            self.assertEqual(result[key], [], (key, result))
        # 背诵“明天早读抽查”、运动服“周四学校体检”是各项自己的安排日；抄写/听写同条各保本项日期，不因另一项日期转待核对。
        self.assertEqual((result['due_errors'], result['review']), ([], []), result)
        self.assertTrue(result['passed'], result)

    def test_unlocated_outcome_needs_disjoint_literal_quote_from_same_publisher(self):
        import family_agent
        base = _school_a_reply()
        overlap = copy.deepcopy(base); overlap[5]['title_quote'] = '每个抄写两遍，明天交；周五听写Unit 3单词'
        duplicate = copy.deepcopy(base) + [copy.deepcopy(base[5])]
        missing = [p for n, p in enumerate(copy.deepcopy(base)) if n != 6]
        other_teacher = copy.deepcopy(base); other_teacher[5]['evidence'].append(dict(ref='message:synthetic-school-a:2'))
        other_source = copy.deepcopy(base); other_source[5]['evidence'].append(dict(ref='message:synthetic-other:1'))
        foreign = dict(SCHOOL_CASES['school-a']['evidence'][3], ref='message:synthetic-other:1', text='收到。',
                       related_messages=['message:synthetic-other:1'])
        for label, proposals, extra in [('overlap', overlap, ()), ('duplicate', duplicate, ()), ('missing', missing, ()),
                                        ('other_teacher', other_teacher, ()), ('other_source', other_source, (foreign,))]:
            with self.subTest(label), self.assertRaises(family_agent.AgentError):
                _select_school_a(proposals, extra)


def _select_school_a(proposals, extra=(), evidence=None):
    import family_agent
    evidence = copy.deepcopy(evidence or SCHOOL_CASES['school-a']['evidence']) + [copy.deepcopy(e) for e in extra]
    with patch.object(family_agent.family_llm, '_chat_json', return_value=dict(proposals=copy.deepcopy(proposals))):
        return family_agent._select('school', evidence, school_goals=[], as_of=AS_OF)


class NativeLedgerChangeTest(unittest.TestCase):
    """A later change binds only to the one located outcome it names; the list never leaves the ledger."""
    LIST = 'message:synthetic-school-a:1'

    def ledger(self, text, clock='19:25:00', publisher='publisher:synthetic-chinese', source='school-a', base_text=None, key=4, **extra):
        import family_agent
        base = dict(copy.deepcopy(SCHOOL_CASES['school-a']['evidence'][0]), related_messages=[self.LIST])
        if base_text: base['text'] = base_text
        ref = 'message:synthetic-%s:9' % source
        later = dict(ref=ref, text=text, time='2026-10-07T%s+08:00' % clock, kind='text', source='虚构班级群', sender='示例',
                     publisher=publisher, content_incomplete=False, attachments=[], related_messages=[ref])
        later.update(extra)
        return {a['quote'][:key]: [c['ref'][-1] for c in a.get('changes', [])]
                for a in family_agent._school_native_actions([base, later]) if a['ref'] == self.LIST}

    def test_change_binds_only_the_named_outcome(self):
        self.assertEqual(self.ledger('补充：练习册第5题不用做，只做第1-4题。'), {'背诵《秋': [], '完成练习': ['9']})
        self.assertEqual(self.ledger('《秋夜》第2自然段改为朗读两遍。'), {'背诵《秋': ['9'], '完成练习': []})

    def test_unrelated_unverifiable_or_ambiguous_change_binds_nothing(self):
        kept = {'背诵《秋': [], '完成练习': []}
        for label, kwargs in [('unrelated', dict(text='周记本周不用写。')), ('other_date', dict(text='下周一的书法课不用带毛笔。')),
                              ('earlier', dict(text='补充：练习册第5题不用做。', clock='18:30:00')),
                              ('other_person', dict(text='练习册第5题不用做吗？', publisher='publisher:synthetic-parent')),
                              ('incomplete', dict(text='补充：练习册第5题不用做。', content_incomplete=True)),
                              ('other_object', dict(text='补充：作业本第5题不用做。')),
                              ('ambiguous', dict(text='《秋夜》改为朗读，练习册第5题不用做。')),
                              ('other_source', dict(text='补充：练习册第5题不用做。', source='other'))]:
            with self.subTest(label):
                self.assertEqual(self.ledger(**kwargs), kept)


    def test_change_must_match_every_specific_object_it_names(self):
        # 书名/页码/Unit/科目/题号与原项冲突、否定提及或未列对象都不能绑定；未写对象的“第N题”只按唯一可核对对象绑定。
        kept, bound = {'背诵《秋': [], '完成练习': []}, {'背诵《秋': [], '完成练习': ['9']}
        for label, text in [('other_page', '补充：练习册第9页第5题不用做，只做第1-4题。'),
                            ('other_title', '补充：《数学专项》练习册第5题不用做，只做第1-4题。'),
                            ('other_subject', '补充数学练习册：第5题不用做，只做第1-4题。'),
                            ('negated_mention', '补充：不是练习册，是作业本第5题不用做。'),
                            ('question_outside_list', '补充：练习册第8题不用做。'),
                            ('unlisted_object', '补充：周记第5题不用做。')]:
            with self.subTest(label):
                self.assertEqual(self.ledger(text), kept)
        for label, text in [('same_page', '补充：练习册第12页第5题不用做。'), ('same_subject', '补充语文练习册：第5题不用做，只做第1-4题。'),
                            ('unnamed_sole_object', '补充：第5题不用做，只做第1-4题。')]:
            with self.subTest(label):
                self.assertEqual(self.ledger(text), bound)
        unit = '今天英语作业：1. 背诵Unit 3课文第一段；2. 完成Unit 3练习册第1-5题，本周五交。'
        self.assertEqual(self.ledger('补充：Unit 30练习册第5题不用做。', base_text=unit), {'背诵Un': [], '完成Un': []})
        self.assertEqual(self.ledger('补充：Unit 3练习册第5题不用做。', base_text=unit), {'背诵Un': [], '完成Un': ['9']})
        two = '今天语文作业：1. 完成练习册第12页第1-5题；2. 完成练习册第13页第1-5题。'
        self.assertEqual(self.ledger('补充：第5题不用做。', base_text=two, key=9), {'完成练习册第12页': [], '完成练习册第13页': []})
        self.assertEqual(self.ledger('补充：练习册第13页第5题不用做。', base_text=two, key=9), {'完成练习册第12页': [], '完成练习册第13页': ['9']})

    def test_change_within_two_minutes_binds_its_one_outcome_without_releasing_the_list(self):
        self.assertEqual(self.ledger('补充语文练习册：第5题不用做，只做第1-4题。', clock='19:01:00'), {'背诵《秋': [], '完成练习': ['9']})
        self.assertEqual(self.ledger('补充：《数学专项》练习册第5题不用做。', clock='19:01:00'), {'背诵《秋': [], '完成练习': []})


class SiblingCoverageTest(unittest.TestCase):
    def test_unchanged_siblings_stay_exactly_once_with_real_or_frozen_links(self):
        import family_agent
        base = _school_a_reply()
        real = [dict(e, related_messages=[e['ref']]) for e in copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])]
        for links, evidence in (('frozen', None), ('real', real)):
            result = score_school('school-a', school_rows(_select_school_a(base, evidence=evidence)))
            self.assertEqual((result['covered'], result['usable'], result['citation_errors'], result['reference_errors'], result['extra']),
                             (7, 7, [], [], []), (links, result))
            for label, proposals in [('drop_recite', base[1:]), ('drop_mental', base[:2] + base[3:]),
                                     ('dup_recite', base + [copy.deepcopy(base[0])]), ('dup_dictation', base + [copy.deepcopy(base[6])])]:
                with self.subTest(links=links, case=label), self.assertRaises(family_agent.AgentError):
                    _select_school_a(proposals, evidence=evidence)

    def test_unverifiable_or_foreign_change_cannot_release_the_list(self):
        # Real ingest links each message only to itself; an explicitly linked incomplete message keeps the
        # pre-existing original-material-group route and is reported separately.
        import family_agent
        base = _school_a_reply()
        for label, change in [('incomplete', dict(content_incomplete=True)), ('wrong_publisher', dict(publisher='publisher:synthetic-head')),
                              ('other_object', dict(text='补充：作业本第5题不用做，只做第1-4题。'))]:
            evidence = [dict(e, related_messages=[e['ref']]) for e in copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])]
            evidence[5].update(change)
            for proposals in (base, base[1:]):
                with self.subTest(label, proposals=len(proposals)), self.assertRaises(family_agent.AgentError):
                    _select_school_a(proposals, evidence=evidence)


    def test_change_naming_another_page_or_title_rejects_the_reply_citing_it(self):
        import family_agent
        for text in ('补充：练习册第9页第5题不用做，只做第1-4题。', '补充：《数学专项》练习册第5题不用做，只做第1-4题。'):
            evidence = [dict(e, related_messages=[e['ref']]) for e in copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])]
            evidence[5]['text'] = text
            with self.subTest(text), self.assertRaises(family_agent.AgentError):
                _select_school_a(_school_a_reply(), evidence=evidence)

    def test_change_within_two_minutes_keeps_each_unchanged_sibling_exactly_once(self):
        import family_agent
        base = _school_a_reply()
        evidence = [dict(e, related_messages=[e['ref']]) for e in copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])]
        evidence[5].update(text='补充语文练习册：第5题不用做，只做第1-4题。', time='2026-10-07T19:01:00+08:00')
        result = score_school('school-a', school_rows(_select_school_a(base, evidence=evidence)))
        self.assertEqual((result['covered'], result['usable'], result['citation_errors'], result['reference_errors'], result['extra']),
                         (7, 7, [], [], []), result)
        for label, proposals in [('drop_recite', base[1:]), ('dup_recite', base + [copy.deepcopy(base[0])])]:
            with self.subTest(label), self.assertRaises(family_agent.AgentError):
                _select_school_a(proposals, evidence=evidence)

    def test_someone_elses_linked_unread_or_attachment_message_keeps_the_complete_list(self):
        # 原清单完整；家长的关联消息未读/有附件/不完整只保留为可见限制，不让所有已知文字行动可漏。
        import family_agent
        base = _school_a_reply()
        for label, change in [('unread', dict(unread=True)), ('attachment', dict(attachments=[dict(name='全虚构未读取附件', mime='image/png')])),
                              ('incomplete', dict(content_incomplete=True))]:
            evidence = copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])
            evidence[0]['related_messages'] = [evidence[0]['ref'], evidence[4]['ref'], evidence[5]['ref']]
            evidence[4].update(change, related_messages=[evidence[4]['ref'], evidence[0]['ref']])
            with self.subTest(label):
                ledger = {a['quote'][:4]: [c['ref'][-1] for c in a['changes']]
                          for a in family_agent._school_native_actions(copy.deepcopy(evidence)) if a['ref'] == evidence[0]['ref']}
                self.assertEqual(ledger, {'背诵《秋': [], '完成练习': ['6']})
                for proposals in (base[1:], base + [copy.deepcopy(base[0])]):
                    with self.assertRaises(family_agent.AgentError):
                        _select_school_a(proposals, evidence=evidence)

    def test_unverifiable_correction_prefix_does_not_release_the_list(self):
        # 早于原清单、不完整或带未读附件的“更正”无法核对它改哪项：清单保留，漏未变行动仍拒绝。
        import family_agent
        base = _school_a_reply()
        for label, change in [('earlier', dict(text='更正：练习册第5题不用做。', time='2026-10-07T18:30:00+08:00')),
                              ('incomplete', dict(text='更正：练习册第5题不用做。', content_incomplete=True)),
                              ('attachment', dict(text='更正：练习册第5题不用做。', attachments=[dict(name='全虚构未读取附件', mime='image/png')]))]:
            evidence = [dict(e, related_messages=[e['ref']]) for e in copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])]
            evidence[5].update(change)
            with self.subTest(label):
                ledger = [a['quote'][:4] for a in family_agent._school_native_actions(copy.deepcopy(evidence)) if a['ref'] == evidence[0]['ref']]
                self.assertEqual(ledger, ['背诵《秋', '完成练习'])
                with self.assertRaises(family_agent.AgentError):
                    _select_school_a(base[1:], evidence=evidence)


def ingest_school(name, reply, runs=1):
    """Store.ingest → run_once → _select → _save; the model seam returns a saved parsed reply with refs remapped."""
    from contextlib import ExitStack
    import datetime as dt
    import family_agent as agent
    import family_media
    import test_agent as fixtures
    fixture = fixtures.AgentTests(methodName='runTest'); fixture.setUp()
    try:
        fixture.now = dt.datetime(2026, 10, 7, 20, tzinfo=agent.TZ)
        case = SCHOOL_CASES[name]
        payload = fixture.payload(cursor=str(10 + len(case['evidence'])))
        payload['messages'] = [dict(id=str(10 + n), message_order=str(10 + n), time=e['time'], kind='text', sender=e['sender'],
                                    sender_id=e['publisher'].split(':', 1)[1], text=e['text'], unread=False)
                               for n, e in enumerate(case['evidence'], 1)]
        fixture.store.ingest(payload)
        ref_map = {e['ref']: 'message:' + fixture.source['id'] + ':' + m['id'] for e, m in zip(case['evidence'], payload['messages'])}
        reverse = {v: k for k, v in ref_map.items()}
        calls, counts = [], []

        def seam(messages, schema, task, timeout=60, *, data_path=None):
            context = json.loads(messages[-1]['content'])
            calls.append(dict(task=task, input_sha256=_input_hash(messages, schema, task),
                              evidence=[(reverse.get(e['ref'], e['ref']), [reverse.get(r, r) for r in e.get('related_messages', [])])
                                        for e in context['evidence']],
                              native=[(reverse.get(a['ref'], a['ref']), a['quote'], [reverse.get(s['ref'], s['ref']) for s in a.get('changes', [])])
                                      for a in context.get('required_native_actions', [])]))
            text = json.dumps(reply, ensure_ascii=False)
            for old, new in ref_map.items(): text = text.replace('"%s"' % old, '"%s"' % new)
            return json.loads(text)
        with ExitStack() as stack:
            stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
            stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
            stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
            stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
            stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
            stack.enter_context(patch.object(agent.family_llm, '_chat_json', side_effect=seam))
            results = []
            for _ in range(runs):
                results.append(agent.run_once(fixture.app, now=fixture.now))
                with fixture.store._db() as c:
                    counts.append(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0])
        with fixture.store._db() as c:
            rows = [dict(title=r['title'], body=r['body'], due=r['due'], state=r['state'], kind=r['kind'], plan=json.loads(r['plan']),
                         evidence=[dict(e, ref=reverse.get(e.get('ref'), e.get('ref'))) for e in json.loads(r['evidence'])])
                    for r in c.execute('SELECT * FROM agent_items ORDER BY rowid')]
        # Learning-goal rows created alongside school tasks carry no school_task and are not school actions.
        items = [r for r in rows if r['plan'].get('school_task')]
        return dict(results=results, counts=counts, items=items, other_kinds=sorted(r['kind'] for r in rows if r not in items),
                    calls=calls, ref_map=ref_map)
    finally:
        fixture.doCleanups()


def _school_b_reply(wrong_date=False):
    rows = [('科学：观察豆芽连续记录3天', '观察豆芽生长，连续记录3天，下周一（10月12日）带记录表到校。', '2026-10-12', 'learning', '观察豆芽生长，连续记录3天，下周一（10月12日）带记录表到校', [1]),
            ('打印签字交回视力检查回执', '10月9日前打印《视力检查回执》，签字后交回。', '2026-10-09', 'admin', '请家长10月9日前打印《视力检查回执》，签字后交回', [2]),
            ('学籍信息确认表单位盖章', '《学籍信息确认表》需要家长单位盖章，下周三前交。', '2026-10-14', 'admin', '《学籍信息确认表》需要家长单位盖章，下周三前交', [2]),
            ('语文：写日记一篇', '写日记一篇，不少于200字，后天交。', '2026-10-09', 'learning', '写日记一篇，不少于200字，后天交', [3]),
            ('数学练习卷答案仅供家长参考', '答案仅供家长参考，没有新增要求。', '', 'optional', '数学练习卷答案见群文件，仅供家长参考。', [4]),
            ('数学：同步练习第3课', '同步练习第3课，周四交。', '2026-10-09' if wrong_date else '2026-10-08', 'learning', '同步练习第3课，周四交', [5])]
    return [dict(title_quote=quote, focus='school', due=due, evidence=[dict(ref='message:synthetic-school-b:%d' % r) for r in refs],
                 learning_subject=title.split('：')[0] if purpose == 'learning' else '', learning_goal_id='', task_title=title,
                 task_goal=goal, task_advice='', task_state='reference' if refs == [4] else 'ready', task_reason='原文明确。',
                 task_change='new', task_target_id='', task_purpose=purpose, task_submission='')
            for title, goal, due, purpose, quote, refs in rows]


class RealIngestTest(unittest.TestCase):
    """Store.ingest → run_once with saved fictional replies; no product model request, no pre-filled links or tasks."""

    def test_school_a_keeps_actions_reference_and_reruns_without_duplicates(self):
        run = ingest_school('school-a', dict(proposals=_school_a_reply()), runs=2)
        self.assertEqual((len(run['calls']), run['counts'][0] == run['counts'][1], len(run['items'])), (1, True, 8), run['results'])
        self.assertTrue(all(related == [ref] for ref, related in run['calls'][0]['evidence']), run['calls'][0]['evidence'])
        self.assertIn(('message:synthetic-school-a:1', '完成练习册第12页第1-5题，本周五交', ['message:synthetic-school-a:6']), run['calls'][0]['native'])
        result = score_school('school-a', school_rows(run['items']))
        self.assertEqual((result['covered'], result['usable'], result['missed'], result['purpose_errors'], result['requirement_errors'],
                          result['citation_errors'], result['reference_errors'], result['extra']), (7, 7, [], [], [], [], [], []), result)

    def test_school_a_keeps_each_explicit_action_date(self):
        result = score_school('school-a', school_rows(ingest_school('school-a', dict(proposals=_school_a_reply()))['items']))
        self.assertEqual((result['covered'], result['usable'], result['due_errors'], result['review']), (7, 7, [], []), result)

    def test_school_b_wrong_model_date_or_empty_reply_is_not_accepted(self):
        result = score_school('school-b', school_rows(ingest_school('school-b', dict(proposals=_school_b_reply(wrong_date=True)))['items']))
        self.assertIn('同步练习:无≠2026-10-08', result['due_errors'], result)
        self.assertTrue(any(r.startswith('同步练习:') for r in result['review']), result)
        empty = ingest_school('school-b', dict(proposals=[]))
        self.assertEqual((empty['counts'], empty['results'][0]['processed']), ([0], 0), empty['results'])
        self.assertGreaterEqual(empty['results'][0].get('failed', 0), 1, empty['results'])
        # 保留变体：两项行政日期由各自原句明确（10月9日前／下周三前），应各自ready；借另一项日期不得ready。
        good = score_school('school-b', school_rows(ingest_school('school-b', dict(proposals=_school_b_reply()))['items']))
        self.assertEqual((good['covered'], good['usable'], good['due_errors'], good['review']), (5, 5, [], []), good)
        borrowed = _school_b_reply(); borrowed[2]['due'] = '2026-10-09'
        row = next(r for r in school_rows(ingest_school('school-b', dict(proposals=borrowed))['items']) if '学籍' in r['text'])
        self.assertNotEqual(row['due'], '2026-10-09', row); self.assertNotEqual(row['state'], 'ready', row)


class ActionDateTest(unittest.TestCase):
    """本项安排日只来自本项原句；借日期、周期、过去、范围、发送日当截止、无日期补今天和模型编日都不能成为ready日期。"""

    def rows(self, evidence_edit=None, proposal_edit=None):
        evidence = [dict(e, related_messages=[e['ref']]) for e in copy.deepcopy(SCHOOL_CASES['school-a']['evidence'])]
        proposals = _school_a_reply()
        if evidence_edit: evidence_edit(evidence)
        if proposal_edit: proposal_edit(proposals)
        rows = school_rows(_select_school_a(proposals, evidence=evidence))
        return {key: next(r for r in rows if key in r['text']) for key in ('背诵', '运动服', '抄写', '听写', '告知书')}

    def test_each_action_keeps_its_own_arrangement_date(self):
        self.assertEqual({k: (r['due'], r['state']) for k, r in self.rows().items()},
                         {'背诵': ('2026-10-08', 'ready'), '运动服': ('2026-10-08', 'ready'), '抄写': ('2026-10-08', 'ready'),
                          '听写': ('2026-10-09', 'ready'), '告知书': ('2026-10-10', 'ready')})

    def test_borrowed_recurring_past_range_sent_day_or_invented_dates_are_not_ready(self):
        def clause(n, old, new):
            def edit(evidence): evidence[n]['text'] = evidence[n]['text'].replace(old, new)
            return edit

        def quote(n, old, new, due=None):
            def edit(proposals):
                proposals[n]['title_quote'] = proposals[n]['title_quote'].replace(old, new)
                if due is not None: proposals[n]['due'] = due
            return edit

        def due(n, value):
            def edit(proposals): proposals[n]['due'] = value
            return edit
        cases = [('borrow_notice_date', '运动服', '2026-10-10', None, due(4, '2026-10-10')),
                 ('borrow_dictation_date', '抄写', '2026-10-09', None, due(5, '2026-10-09')),
                 ('borrow_other_clause', '告知书', '2026-10-08', None,
                  lambda p: p[3].update(title_quote='另外周四学校体检，请孩子穿运动服', due='2026-10-08')),
                 ('recurring', '运动服', '2026-10-08', clause(2, '另外周四', '另外每周四'), quote(4, '另外周四', '另外每周四')),
                 ('past_week', '运动服', '2026-10-08', clause(2, '另外周四', '另外上周四'), quote(4, '另外周四', '另外上周四')),
                 ('range', '运动服', '2026-10-08', clause(2, '另外周四', '另外周四至周五'), quote(4, '另外周四', '另外周四至周五')),
                 ('past_day', '背诵', '2026-10-08', clause(0, '明天早读', '昨天早读'), quote(0, '明天早读', '昨天早读')),
                 ('sent_day_as_due', '背诵', '2026-10-07', clause(0, '明天早读', '早读'), quote(0, '明天早读', '早读', '2026-10-07')),
                 ('invented_admin', '运动服', '2026-10-09', None, due(4, '2026-10-09')),
                 ('invented_native', '背诵', '2026-10-09', None, due(0, '2026-10-09'))]
        truth = {'背诵': '2026-10-08', '运动服': '2026-10-08', '抄写': '2026-10-08', '告知书': '2026-10-10'}
        for label, key, bad, evidence_edit, proposal_edit in cases:
            with self.subTest(label):
                row = self.rows(evidence_edit, proposal_edit)[key]
                self.assertNotEqual(row['due'], bad, row)
                kept_truth = evidence_edit is None and row['due'] == truth[key]
                self.assertTrue(row['state'] != 'ready' or kept_truth, row)
        # 模型没给日期时不补今天，也不借同条另一项日期。
        row = self.rows(None, due(4, ''))['运动服']
        self.assertEqual(row['due'], '', row)


class UnansweredReasonTest(unittest.TestCase):
    def test_unanswered_unknown_needs_its_own_reason_and_source(self):
        for name, key in (('homework-a', (0, 3)), ('homework-b', (2, 3))):
            truth = HOMEWORK_CASES[name]['truth']
            n = next(i for i, t in enumerate(truth) if (t['section'], t['number']) == key)

            def scored(**edit):
                items = _homework_reply(name)['items']; items[n].update(edit)
                return score_homework(name, items)
            self.assertTrue(scored()['passed'], scored())
            for label, edit in [('no_reason', dict(uncertainty='', error_reason='')),
                                ('only_no_reference', dict(uncertainty='无教师参考，无法判定'))]:
                with self.subTest(name=name, case=label):
                    result = scored(**edit)
                    self.assertFalse(result['passed'], result); self.assertEqual(result['unanswered_kept'], [], result)
            wrong = scored(answer='AI自行推导：7米' if truth[n]['source'] == 'teacher' else '教师参考：A')
            self.assertFalse(wrong['passed'], wrong); self.assertTrue(wrong['source_errors'], wrong)
            # “教师参考未覆盖”只在真值确无教师参考时属实。
            claim = scored(uncertainty='未作答，教师参考未覆盖本题')
            self.assertEqual(claim['passed'], truth[n]['source'] == 'ai', claim)


class ExactAnswerTest(unittest.TestCase):
    def test_objective_answers_need_the_whole_value(self):
        import family_llm
        reply = _homework_reply('homework-a')
        for item, wrong in zip(reply['items'], ['183', '163', None, None, '162', None]):
            if wrong: item['answer'] = '教师参考：' + wrong
        with patch.object(family_llm, '_chat_json', return_value=reply):
            result = score_homework('homework-a', run_case('homework-a', None)['questions'])
        self.assertFalse(result['passed'])
        self.assertEqual(sorted(e for e in result['content_errors'] if e.endswith('答案不符')), ['1:答案不符', '2:答案不符', '5:答案不符'], result)
        for answer, ok in [('教师参考：62', True), ('教师参考：100-38=62', True), ('教师参考：62或72', False), ('教师参考：7米', True)]:
            self.assertEqual(_value_ok(('num', '62' if '7米' not in answer else '7'), re.sub(r'^教师参考：', '', answer)), ok, answer)
        self.assertTrue(_value_ok(('choice', 'C', '34'), 'C. 34')); self.assertFalse(_value_ok(('choice', 'C', '34'), 'C或D'))
        self.assertTrue(_value_ok(('word', '朋友'), '朋友（péng yǒu）')); self.assertFalse(_value_ok(('word', '朋友'), '朋友、明友'))


class ScorerHardeningTest(unittest.TestCase):
    def test_dismissed_negated_and_foreign_rows_fail(self):
        prefix = 'message:synthetic-school-a:'
        items = []
        for truth in SCHOOL_CASES['school-a']['truth']:
            body = ' '.join(truth['keys']) + ' 两遍 1-4' + {'告知书': ' 不打印 不签字', '练习册1-4': ' 第5题仍必须做'}.get(truth['id'], '')
            items.append(dict(title=truth['id'], body=body, due=truth['due'], evidence=[dict(ref=prefix + str(r)) for r in truth['refs'] + [5]],
                              plan=dict(school_task=dict(state='dismissed', purpose=None, reason=''))))
        result = score_school('school-a', school_rows(items))
        self.assertFalse(result['passed'])
        self.assertEqual((len(result['unusable']), len(result['purpose_errors']), len(result['citation_errors'])), (7, 7, 7))
        self.assertTrue({'告知书', '练习册1-4'} <= set(result['requirement_errors']), result)
        self.assertEqual(result['reference_errors'], ['5:未作参考保留'])

    def test_reference_row_is_consumed_and_reference_as_task_fails(self):
        prefix = 'message:synthetic-school-b:'
        rows = [dict(text=' '.join(t['keys'] + [p.split('|')[0] for p in t['require']]), due=t['due'], purpose=t['purpose'],
                     state='ready', reason='', refs=[prefix + str(r) for r in t['refs']]) for t in SCHOOL_CASES['school-b']['truth']]
        reference = dict(text='答案仅供家长参考', due='', purpose='optional', state='reference', reason='', refs=[prefix + '4'])
        good = score_school('school-b', rows + [reference])
        self.assertTrue(good['passed'], good); self.assertEqual(good['extra_reference'], [])
        bad = score_school('school-b', rows + [dict(reference, state='review')])
        self.assertFalse(bad['passed']); self.assertIn('4:成了review事项', bad['reference_errors'])
        late = score_school('school-b', [dict(r, due='', state='review', reason='日期无法核对') if '同步练习' in r['text'] else r
                                         for r in rows] + [reference])
        self.assertFalse(late['passed']); self.assertEqual(len(late['review']), 1)


class _FakeOpener:
    def __init__(self, reply=None, status=None):
        self.reply, self.status, self.calls = reply, status, []

    def open(self, request, timeout=None):
        self.calls.append(dict(request.header_items()))
        if self.status:
            raise HTTPError(request.full_url, self.status, 'fake', None, io.BytesIO(b'{"error":{"message":"fake overload"}}'))
        body = dict(model='fake-strong-reported', usage=dict(prompt_tokens=11, completion_tokens=7, total_tokens=18),
                    choices=[dict(index=0, finish_reason='stop', message=dict(role='assistant', content=json.dumps(self.reply, ensure_ascii=False)))])
        return io.BytesIO(json.dumps(body, ensure_ascii=False).encode())


class LiveEvidenceTest(unittest.TestCase):
    """Fixed fake HTTP only: no product model request is made by these checks."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()); cfg = self.root / 'cfg'; cfg.mkdir()
        (cfg / 'model.json').write_text(json.dumps(dict(base_url='https://fake-endpoint.invalid/v1', model='fake-strong',
                                                       light_model='fake-light', api_key='fake-secret-key', reasoning_effort='low')))
        self.cfg, self.out = str(cfg), self.root / 'out'
        self.env = patch.dict(os.environ); self.env.start()
        for key in ('FAMILY_LLM_BASE_URL', 'FAMILY_LLM_MODEL', 'FAMILY_LLM_LIGHT_MODEL', 'FAMILY_LLM_API_KEY', 'FAMILY_LLM_REASONING_EFFORT'):
            os.environ.pop(key, None)

    def tearDown(self):
        self.env.stop(); shutil.rmtree(self.root)

    def saved(self):
        return '\n'.join(p.read_text(errors='replace') for p in self.out.rglob('*') if p.is_file())

    def test_request_and_response_kept_without_secrets_and_rerun_refused(self):
        import family_llm
        fake = _FakeOpener(_homework_reply('homework-a'))
        with patch.object(family_llm, 'build_opener', lambda *handlers: fake):
            live(self.cfg, self.out, 'strong', ['homework-a'])
        path = self.out / 'homework-a-strong.json'; before = path.read_bytes(); record = json.loads(before)
        self.assertEqual(record['http']['request_body']['model'], 'fake-strong')
        self.assertIn('fake-strong-reported', record['http']['response_body'])
        self.assertEqual((record['ledger'][0]['state'], record['ledger'][0]['reported_model']), ('returned', 'fake-strong-reported'))
        self.assertTrue(record['score']['final']['passed'], record['score'])
        self.assertIn('Authorization', fake.calls[0])
        self.assertNotIn('fake-secret-key', self.saved()); self.assertNotIn('fake-endpoint', self.saved())
        with patch.object(family_llm, 'build_opener', lambda *handlers: fake), self.assertRaises(SystemExit):
            live(self.cfg, self.out, 'strong', ['homework-a'])
        self.assertEqual((len(fake.calls), path.read_bytes()), (1, before))

    def test_http_failure_body_and_status_kept(self):
        import family_llm
        with patch.object(family_llm, 'build_opener', lambda *handlers: _FakeOpener(status=503)):
            live(self.cfg, self.out, 'light', ['school-b'])
        record = json.loads((self.out / 'school-b-light.json').read_text())
        self.assertIn('模型服务未能处理请求', record['error'])
        self.assertEqual((record['http']['http_status'], record['ledger'][0]['state']), (503, 'failed'))
        self.assertIn('fake overload', record['http']['response_body'])
        self.assertEqual(record['http']['request_body']['model'], 'fake-light')

    def test_refusal_before_send_keeps_reason_without_ledger_table(self):
        import family_llm
        with patch.object(family_llm, 'homework_reference_draft', side_effect=family_llm.LLMUnavailable('预检拒绝：未发送')), \
                patch.object(family_llm, 'build_opener', side_effect=AssertionError('不应联网')):
            live(self.cfg, self.out, 'strong', ['homework-b'])
        record = json.loads((self.out / 'homework-b-strong.json').read_text())
        self.assertIn('预检拒绝', record['error']); self.assertEqual((record['ledger'], record['http']), ([], {}))
        self.assertIn('请求未发出', record['ledger_note'])


if __name__ == '__main__':
    if len(sys.argv) >= 5 and sys.argv[1] == '--live':
        live(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:] or list(SCHOOL_CASES) + list(HOMEWORK_CASES))
    elif len(sys.argv) == 4 and sys.argv[1] == '--replay':
        target = Path(sys.argv[3])
        if target.exists(): raise SystemExit('复放结果已存在，未覆盖：' + target.name)
        target.write_text(json.dumps(replay(sys.argv[2]), ensure_ascii=False, indent=1, default=str))
    elif len(sys.argv) == 4 and sys.argv[1] == '--replay-ingest':
        target = Path(sys.argv[3])
        if target.exists(): raise SystemExit('复放结果已存在，未覆盖：' + target.name)
        target.write_text(json.dumps(replay_ingest(sys.argv[2]), ensure_ascii=False, indent=1, default=str))
    else:
        unittest.main()

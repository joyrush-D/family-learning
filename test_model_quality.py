"""R03/R09/R14/R18/S03 归纳与作答检查质量基线：全虚构场景、事先冻结的独立真值和确定评分。

真值由开发者在任何产品模型调用前写定并提交；模型返回的题号清单或摘要不能用来证明无漏项。
school-a/homework-a 可用于归因与修复，school-b/homework-b 是保留变体，不据其结果改提示或真值。
默认只跑离线检查。`--live 配置目录 输出目录 角色` 才经产品入口发送真实请求：每案每模型一次，失败不重试；
配置只在本进程内存中使用，用量写入输出目录下隔离的 family.sqlite3，不写回配置目录。
"""
import copy
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import unittest
from pathlib import Path
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


def school_rows(items, raw=False):
    rows = []
    for item in items or []:
        if raw:
            text = '\n'.join(str(item.get(k, '')) for k in ('task_title', 'task_goal'))
            purpose = item.get('task_purpose', '')
            state = item.get('task_state', '')
        else:
            text = '\n'.join(str(item.get(k, '')) for k in ('title', 'body'))
            purpose = next((item[k] for k in ('purpose', 'task_purpose', 'school_purpose') if isinstance(item.get(k), str)), None)
            state = item.get('state', item.get('task_state', ''))
        refs = [e.get('ref') if isinstance(e, dict) else e for e in item.get('evidence') or []]
        rows.append(dict(text=text, due=item.get('due', ''), purpose=purpose, state=state, refs=refs))
    return rows


def score_school(name, rows):
    case = SCHOOL_CASES[name]
    prefix = 'message:synthetic-%s:' % name
    matched, used, result = {}, set(), dict(missed=[], due_errors=[], purpose_errors=[], requirement_errors=[],
                                             citation_errors=[], extra=[])
    for truth in case['truth']:
        for n, row in enumerate(rows):
            if n not in used and row['state'] != 'reference' and all(k in row['text'] for k in truth['keys']):
                matched[truth['id']] = row; used.add(n); break
        else:
            result['missed'].append(truth['id']); continue
        row = matched[truth['id']]
        if row['due'] != truth['due']: result['due_errors'].append('%s:%s≠%s' % (truth['id'], row['due'] or '无', truth['due']))
        if row['purpose'] is not None and row['purpose'] != truth['purpose']:
            result['purpose_errors'].append('%s:%s≠%s' % (truth['id'], row['purpose'], truth['purpose']))
        if any(not re.search(p, row['text']) for p in truth['require']) or (
                truth.get('forbid_stamp') and '盖章' in STAMP_EXEMPT.sub('', row['text'])):
            result['requirement_errors'].append(truth['id'])
        if any(prefix + str(r) not in row['refs'] for r in truth['refs']):
            result['citation_errors'].append(truth['id'])
    for n, row in enumerate(rows):
        if n not in used and row['state'] != 'reference':
            result['extra'].append(row['text'][:40])
    result['covered'] = len(case['truth']) - len(result['missed'])
    result['total'] = len(case['truth'])
    return result


SECTION = {'一': 1, '二': 2, '三': 3}


def parse_label(label, sectioned):
    numbers = [int(x) for x in re.findall(r'\d+', label)]
    if not sectioned:
        return (0, numbers[0]) if numbers else None
    section = next((SECTION[ch] for ch in ('二', '一', '三') if re.search('第?' + ch + '[、.．大部分题]', label)), None)
    if section is None and len(numbers) >= 2: section, numbers = numbers[0], numbers[1:]
    return (section, numbers[0]) if section and numbers else None


def score_homework(name, questions):
    case = HOMEWORK_CASES[name]
    sectioned = any(t['section'] for t in case['truth'])
    found = {}
    extra = []
    for item in questions or []:
        key = parse_label(str(item.get('label', '')), sectioned)
        if key is None or key in found: extra.append(str(item.get('label', ''))[:40]); continue
        found[key] = item
    result = dict(missed=[], wrong_judgment=[], undetermined=[], source_errors=[], extra=extra)
    for truth in case['truth']:
        key = (truth['section'], truth['number']); tag = '%s-%s' % key if sectioned else str(truth['number'])
        item = found.pop(key, None)
        if item is None: result['missed'].append(tag); continue
        judgment = item.get('judgment')
        if judgment not in truth['judgments']:
            (result['undetermined'] if judgment == 'unknown' else result['wrong_judgment']).append(
                '%s:%s≠%s' % (tag, judgment, '/'.join(truth['judgments'])))
        if judgment in ('correct', 'incorrect'):
            teacher = str(item.get('answer', '')).startswith('教师参考：')
            if teacher != (truth['source'] == 'teacher'): result['source_errors'].append(tag)
    result['extra'] += ['%s-%s' % key for key in found]
    result['covered'] = len(case['truth']) - len(result['missed'])
    result['total'] = len(case['truth'])
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


def live(config_dir, out_dir, role, names):
    """One request per case for one configured model; failures are kept, never retried."""
    import family_llm
    config = family_llm.model_values(config_dir)
    model = config['model' if role == 'strong' else 'light_model'].strip()
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    for name in names:
        record = dict(case=name, role=role, requested_model=model, reasoning_effort=config['reasoning_effort'],
                      held_out=(SCHOOL_CASES.get(name) or HOMEWORK_CASES[name])['held_out'])
        if not model:
            record.update(error='未配置该角色模型，未发送请求'); (out / (name + '-' + role + '.json')).write_text(
                json.dumps(record, ensure_ascii=False, indent=1)); continue
        data = out / (name + '-' + role + '-data'); data.mkdir(exist_ok=True)
        captured, real = {}, family_llm._chat_json

        def capture(messages, schema, task, timeout=60, *, data_path=None):
            captured.update(task=task, timeout=timeout, input_sha256=hashlib.sha256(json.dumps(
                [messages, schema, task], ensure_ascii=False, sort_keys=True).encode()).hexdigest())
            try:
                draft = real(messages, schema, task, timeout, data_path=data_path)
            except Exception as error:
                captured['transport_error'] = '%s: %s' % (type(error).__name__, error); raise
            captured['raw_model_output'] = copy.deepcopy(draft)
            return draft
        env = {'FAMILY_LLM_BASE_URL': config['base_url'], 'FAMILY_LLM_MODEL': model, 'FAMILY_LLM_LIGHT_MODEL': '',
               'FAMILY_LLM_API_KEY': config['api_key'], 'FAMILY_LLM_REASONING_EFFORT': config['reasoning_effort']}
        started = time.monotonic(); final = None; error = ''
        with patch.dict(os.environ, env), patch.object(family_llm, '_chat_json', capture):
            try:
                final = run_case(name, str(data))
            except Exception as exc:
                error = '%s: %s' % (type(exc).__name__, exc)
        record['wall_ms'] = round((time.monotonic() - started) * 1000)
        with sqlite3.connect(data / 'family.sqlite3') as db:
            db.row_factory = sqlite3.Row
            record['ledger'] = [dict(r) for r in db.execute('SELECT * FROM llm_usage_ledger ORDER BY id')]
        record.update(captured=captured, final=final, error=error,
                      score=score(name, final, captured.get('raw_model_output')))
        (out / (name + '-' + role + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=1, default=str))


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
    """A reply that already matches truth must survive validation unchanged (separates program from model)."""

    def test_truthful_answer_check_reply_keeps_every_frozen_result(self):
        import family_llm
        for name, case in HOMEWORK_CASES.items():
            sectioned = any(t['section'] for t in case['truth'])
            labels, items = [], []
            for t in case['truth']:
                label = ('%s、第%d题' % ('一二'[t['section'] - 1], t['number']) if sectioned else '第%d题' % t['number'])
                judged = t['judgments'][0] != 'unknown'
                labels.append(label)
                items.append(dict(label=label, question='题%d' % t['number'], student_answer='作答' if judged else '',
                                  answer=(('教师参考：' if t['source'] == 'teacher' else 'AI自行推导：') + '参考') if judged else '',
                                  judgment=t['judgments'][0], error_reason='与参考不同' if t['judgments'][0] == 'incorrect' else '',
                                  possible_cause='', steps='', uncertainty='' if judged else '未作答，待补看',
                                  question_kind='objective'))
            reply = dict(items=items, coverage='已按文字原件核对全部题号。', comparison='', question_labels=labels)
            with patch.object(family_llm, '_chat_json', return_value=copy.deepcopy(reply)):
                final = run_case(name, None)
            result = score_homework(name, final['questions'])
            self.assertEqual((result['covered'], result['wrong_judgment'], result['undetermined'], result['source_errors']),
                             (len(case['truth']), [], [], []), (name, result))


if __name__ == '__main__':
    if len(sys.argv) >= 5 and sys.argv[1] == '--live':
        live(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:] or list(SCHOOL_CASES) + list(HOMEWORK_CASES))
    else:
        unittest.main()

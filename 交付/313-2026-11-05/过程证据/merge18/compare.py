"""Reconcile the real-model merge18 run against ORACLE-EXECUTION.json.

Reads work/merge18/run.json (final state + calendar snapshots) and the frozen oracle, then prints a
compact, evidence-grounded table for the five acceptance dimensions. No product code, no oracle edits.
"""
import json
import re
from pathlib import Path

BASE = Path('/Users/joyrush/Documents/deepseek-harness/default-workspace')
OUT = BASE / 'work/merge18'
FIXTURE = BASE / 'work/handoff-20261104/extract/DeepSeek-Harness-交接-20261104/附件/全虚构验收材料/FIXTURE.json'
ORACLE = BASE / 'work/handoff-20261104/extract/DeepSeek-Harness-交接-20261104/附件/全虚构验收材料/ORACLE-EXECUTION.json'
DAY = '2026-11-04'

run = json.loads((OUT / 'run.json').read_text())
fixture = json.loads(FIXTURE.read_text())
oracle = json.loads(ORACLE.read_text())
final = run['final']
items = final['items']
tasks = final['tasks']
inbox = final['day']['inbox']
next_inbox = final['next_day']['inbox']
messages = final['messages']

task_by_id = {t['id']: t for t in tasks}
item_plans = {}
for item in items:
    try:
        item_plans[item['id']] = json.loads(item.get('plan') or '{}')
    except json.JSONDecodeError:
        item_plans[item['id']] = {}


def dump(value):
    return json.dumps(value, ensure_ascii=False)


def item_text(item):
    plan = item_plans.get(item['id']) or {}
    task = task_by_id.get(item.get('task_id') or '')
    parts = [item.get('title') or '', item.get('body') or '']
    for key in ('school_selection_receipt', 'school_task'):
        block = plan.get(key) or {}
        for field in ('title', 'goal', 'submission', 'advice', 'reason'):
            if block.get(field):
                parts.append(str(block[field]))
    if task:
        parts.extend([task.get('action') or '', task.get('source') or ''])
    return '\n'.join(parts)


def refs_in_item(item):
    plan = item_plans.get(item['id']) or {}
    refs = []
    try:
        for entry in json.loads(item.get('evidence') or '[]'):
            refs.append(entry.get('ref'))
    except json.JSONDecodeError:
        pass
    for message in plan.get('school_messages') or []:
        refs.append('message:%s:%s' % (message.get('source_id'), message.get('message_id')))
    task = task_by_id.get(item.get('task_id') or '')
    if task:
        refs.extend('message:' + m for m in re.findall(r'message:[\w\-:.]+', task.get('source') or ''))
    seen, ordered = set(), []
    for ref in refs:
        if ref and ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return ordered


def item_digest(item):
    plan = item_plans.get(item['id']) or {}
    task = task_by_id.get(item.get('task_id') or '')
    return dict(id=item['id'], child=item['child_id'], state=item['state'], title=item['title'],
                due=item.get('due') or '', task=item.get('task_id') or '',
                task_title=(task or {}).get('title'), task_due=(task or {}).get('due'),
                refs=refs_in_item(item),
                brief=(plan.get('school_task') or {}).get('state'),
                change=(plan.get('school_task') or {}).get('change'),
                goal=(plan.get('school_task') or {}).get('goal'),
                submission=(plan.get('school_task') or {}).get('submission'))


def find_items(*needles, child=None):
    hits = []
    for item in items:
        if child and item['child_id'] != child:
            continue
        text = item_text(item)
        if all(needle in text for needle in needles):
            hits.append(item)
    return hits


def messages_of(item):
    return [ref.split(':')[-1] for ref in refs_in_item(item)]


MATTERS = [
    dict(id='h18-a-math', child='child-1', match=('每日练习', '26'), group=['h18-m01', 'h18-m04', 'h18-m09'],
         must=['26', '1、2、3', '算式', '验算', '签字', '周五'],
         forbid=['1—4题不做'],
         dates=['2026-11-04', '2026-11-06'],
         note='第4题不做 / 周五交 / 今晚完成'),
    dict(id='h18-a-reading', child='child-1', match=('风经过小巷', '第2、3自然段'), group=['h18-m02', 'h18-m10', 'h18-m18'],
         must=['各', '两遍', '读给家长听', '抽听'],
         forbid=['背诵'],
         dates=['2026-11-04', '2026-11-05'],
         note='家长 18:30 听读是家庭安排不是老师截止'),
    dict(id='h18-a-english', child='child-1', match=('英语', '每日练习'), group=['h18-m05', 'h18-m13'],
         must=['看图选词', '1—3', 'under', 'near', '抄写', '英语夹'],
         forbid=['录音'],
         dates=['2026-11-04', '2026-11-05'],
         note='附件已读要求必须落进任务'),
    dict(id='h18-a-art-cancelled', child='child-1', match=('落叶',), group=['h18-m07', 'h18-m12'],
         must=[], forbid=['两片落叶', '夹在'], dates=[], note='整项取消'),
    dict(id='h18-b-math', child='child-2', match=('计算小卡', '4页'), group=['h18-m03', 'h18-m11', 'h18-m16'],
         must=['1—6', '写得数', '明天交'],
         forbid=['抄题'],
         dates=['2026-11-04', '2026-11-05'],
         note='不另加题 / 做过不用再做'),
    dict(id='h18-b-photo', child='child-2', match=('证件照',), group=['h18-m06', 'h18-m14'],
         must=['一寸', '一张', '班主任'],
         forbid=['重新拍'],
         dates=['2026-11-05'],
         note='11/5 才交，不是 11/4 到期'),
    dict(id='h18-b-chinese-unread', child='child-2', match=('识字小卡',), group=['h18-m08', 'h18-m15'],
         must=['签名', '明早'],
         forbid=['生字', '拼音', '第1题', '第2题'],
         dates=['2026-11-04', '2026-11-05'],
         note='附件未读：内容待补但事项要保留'),
    dict(id='h18-b-art-oral', child='child-2', match=('彩笔',), group=['h18-m17'],
         must=['彩笔', '明天'],
         forbid=['群'],
         dates=['2026-11-05'],
         note='孩子口述经家长补录，不冒充群消息'),
]

print('=' * 100)
print('MATTERS  (oracle 8)')
print('=' * 100)
for matter in MATTERS:
    hits = find_items(*matter['match'], child=matter['child'])
    if not hits:  # loosen: any child, single token
        hits = find_items(matter['match'][0])
    print('\n###', matter['id'], '| child', matter['child'], '| oracle group', matter['group'])
    if not hits:
        print('   !!! no product item matched', matter['match'])
        continue
    for item in hits:
        text = item_text(item)
        digest = item_digest(item)
        missing = [word for word in matter['must'] if word not in text]
        print('   item', digest['id'][:22], digest['state'], '| task', digest['task'][:26] or '-',
              '| due', digest['due'], '| refs', digest['refs'])
        print('        title:', digest['title'])
        print('        goal :', (digest['goal'] or '').replace('\n', ' / ')[:400])
        print('        miss :', missing or 'none', '| forbid-hit:', [w for w in matter['forbid'] if w in text] or 'none')
        print('        dates:', [d for d in matter['dates'] if d in text] or 'none', '| note:', matter['note'])
    covered = {m for item in hits for m in messages_of(item)}
    print('   coverage: oracle msgs', matter['group'], '-> product', sorted(covered),
          '| MULTI-CHANNEL MERGED' if len([h for h in hits if h['state'] in ('accepted', 'pending')]) == 1 else '| SPLIT/EXTRA ITEMS')

print('\n' + '=' * 100)
print('PER MESSAGE DESTINATION')
print('=' * 100)
place = {}
for item in items:
    for message_id in messages_of(item):
        place.setdefault(message_id, []).append((item['id'], item['state'], item['title'][:30]))
processed = {m['message_id']: m['processed'] for m in messages}
for message in fixture['messages']:
    message_id = message['id']
    print(message_id, message['source_id'], 'processed' if processed.get(message_id) else 'UNPROCESSED',
          '->', place.get(message_id) or 'NOT PLACED')

print('\n' + '=' * 100)
print('SELECTED DAY TRUTH  (2026-11-04)')
print('=' * 100)
schools = [i for i in inbox if i['kind'] == 'school']
default_tasks = [i for i in inbox if i['kind'] == 'task']
print('inbox total', len(inbox), '| school', len(schools), '| task', len(default_tasks))
for item in inbox:
    agenda = item.get('agenda') or {}
    print(' -', item['kind'], item['child_ids'], '|', item['title'], '| due_on', agenda.get('due_on'),
          '| kind', agenda.get('due_kind'), '| complete_on', agenda.get('complete_on'),
          '| scheduled_on', agenda.get('scheduled_on'), '| subjects', agenda.get('subjects'),
          '| publications', [p.get('ref') for p in agenda.get('publications') or []])
print('next-day inbox total', len(next_inbox))
for item in next_inbox:
    print('   *', item['kind'], item['child_ids'], '|', item['title'], '| due', (item.get('agenda') or {}).get('due_on'))

print('\n' + '=' * 100)
print('ATTACHMENT TRUTH')
print('=' * 100)
for row in final['pdf_material']:
    try:
        payload = json.loads(row['payload'])
    except (KeyError, TypeError, json.JSONDecodeError):
        payload = row
    print('pdf-material', row['message_id'], '| pages', row.get('pages'), '/', row.get('page_count'),
          '| state', payload.get('state'), '| complete', payload.get('complete'))
    print('   payload:', dump(payload)[:1200])
for row in final['drafts']:
    print('draft', row.get('message_id'), '| state', row.get('state'), '| keys', list(row))
english = find_items('英语', '每日练习', child='child-1')
print('\nenglish items:', [(i['id'][:22], i['state']) for i in english])
for item in english:
    text = item_text(item)
    print('   has 看图选词:', '看图选词' in text, '| has under/near:', 'under' in text and 'near' in text,
          '| has 1—3:', '1—3' in text or '1-3' in text, '| has 抄写:', '抄写' in text)
chinese = find_items('识字小卡', child='child-2')
for item in chinese:
    text = item_text(item)
    print('chinese item', item['id'][:22], item['state'], '| invented:', [w for w in ('生字', '拼音', '第1题', '格式') if w in text],
          '| gap words:', [w for w in ('未读', '待补', '尚未读取', '未知') if w in text])

print('\n' + '=' * 100)
print('CANCELLATION')
print('=' * 100)
for item in items:
    text = item_text(item)
    if '落叶' in text:
        print('item', item['id'][:22], item['state'], '|', item['title'])
        print('   body:', (item['body'] or '').replace('\n', ' / ')[:500])
        print('   plan keys:', list(item_plans.get(item['id']) or {}))
        plan = item_plans.get(item['id']) or {}
        print('   plan:', dump(plan)[:1200])
print('day inbox mentions 落叶:', [i['title'] for i in inbox if '落叶' in (i.get('title') or '')])
print('next-day mentions 落叶:', [i['title'] for i in next_inbox if '落叶' in (i.get('title') or '')])
print('彩笔 items:', [(i['id'][:22], i['child_id'], i['state'], i['title']) for i in items if '彩笔' in item_text(i)])

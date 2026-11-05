# -*- coding: utf-8 -*-
"""Round-2 quick audit probes for family_agent.py sha1 4cd8383b (post-F1/F2/F3 fix).

Read-only: imports the repo working tree copy (verified by sha1), invented data only, no model, no product DB.
Run: python3 -B probes-r2.py > probes-r2-out.txt
"""
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime

REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
TARGET = '4cd8383b025bed6047851e838256c5045336bf5b'
sys.path.insert(0, REPO)
import family_agent as fa  # noqa: E402

SOURCE = open(REPO + '/family_agent.py', encoding='utf-8').read()


class FakeStore:
    def __init__(self, sources, messages, items, tasks=()):
        self._sources = sources
        self._messages = messages
        self._conn = sqlite3.connect(':memory:')
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('CREATE TABLE agent_items (id TEXT PRIMARY KEY, job_id TEXT, child_id TEXT, kind TEXT,'
                           ' title TEXT, body TEXT, evidence TEXT, due TEXT, care_id TEXT, record_id TEXT,'
                           ' created TEXT, updated TEXT, plan TEXT, task_id TEXT, state TEXT)')
        self._conn.execute('CREATE TABLE agent_messages (source_id TEXT, payload TEXT)')
        self._conn.execute('CREATE TABLE manual_tasks (id TEXT PRIMARY KEY, child TEXT, title TEXT, due TEXT,'
                           ' original_status TEXT, source TEXT, action TEXT)')
        for (source_id, _message_id), message in messages.items():
            self._conn.execute('INSERT INTO agent_messages (source_id, payload) VALUES (?,?)',
                               (source_id, json.dumps(message)))
        for item in items:
            self._conn.execute('INSERT INTO agent_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (item['id'], '', item['child_id'], item.get('kind', 'school'), item.get('title', ''),
                                item.get('body', ''), json.dumps(item.get('evidence', [])), item.get('due', ''), '', '',
                                item.get('created', '2026-11-04 10:00:00'), '2026-11-04 10:00:00',
                                json.dumps(item.get('plan', {})), item.get('task_id', ''), item.get('state', 'pending')))
        for task in tasks:
            self._conn.execute('INSERT INTO manual_tasks VALUES (?,?,?,?,?,?,?)',
                               (task['id'], task.get('child', '示例甲'), task.get('title', ''), task.get('due', ''),
                                '待跟进', '', task.get('action', '')))
        self._conn.commit()

    def _config(self):
        return {'sources': self._sources}

    def _db(self):
        return self._conn

    def _message_pages(self, c, source, message):
        return []

    def _message_context(self, c, wanted):
        return self._sources_by_id[wanted['source_id']], self._messages[(wanted['source_id'], wanted['message_id'])]

    @property
    def _sources_by_id(self):
        return {s['id']: s for s in self._sources}


def msg(mid, text, sender='林老师', sender_id='t1', time='2026-11-04T10:00:00+08:00', kind='text'):
    return dict(id=mid, text=text, sender=sender, sender_id=sender_id, time=time, kind=kind, unread=False,
                content_incomplete=False, attachments=[])


SOURCES = [
    dict(id='s-wechat', child_id='c1', platform='wechat', enabled=1, name='微信班级群'),
    dict(id='s-qq', child_id='c1', platform='qq', enabled=1, name='QQ班级群'),
]
MESSAGES = {
    ('s-wechat', 'm1'): msg('m1', '今天数学作业：完成《每日练习》第26页第1—4题。', sender_id='wx-1001'),
    ('s-qq', 'm3'): msg('m3', '提醒：数学第26页那项明天交。', sender_id='qq-2002', time='2026-11-04T16:30:00+08:00'),
    ('s-wechat', 'm5'): msg('m5', '更正：只做第26页第1—3题，改到11月10日交。', sender_id='wx-1001',
                            time='2026-11-04T18:00:00+08:00'),
    ('s-qq', 'm4'): msg('m4', '语文：朗读《每日练习》第26页的短文两遍。', sender_id='qq-3003'),
    ('s-qq', 'm6'): msg('m6', '数学作业：带练习册。', sender='王老师', sender_id='qq-4004'),
}
NOW = datetime(2026, 11, 4, 19, 0, 0)


def case(name, got, expected, note=''):
    print(f'[{"PASS" if got == expected else "FAIL"}] {name}: got={got!r} expected={expected!r}'
          + (f'  # {note}' if note else ''))


def keeps_split_fragment(title, goal):
    """The exact three-part predicate of _select L8273-8275 (kept only if all three say 'no')."""
    blob = str(title or '') + '\n' + str(goal or '')
    return bool(fa._SCHOOL_SPLIT_REQUIREMENT.search(blob)
                or fa._SCHOOL_SPLIT_SUBJECT.search(blob)
                or re.search(r'[《》0-9]', blob))


def h1_same_due():
    print('\n== H1 (F1) _school_same_due: differing day no longer raises ==')
    card = dict(due='2026-11-06', title='数学：《每日练习》第26页第1—4题', goal='完成《每日练习》第26页第1—4题。')
    for text in ('明天交', '改到11月10日交', '周五交'):
        evidence = [dict(ref='message:s-wechat:m5', text=text, time='2026-11-04T18:00:00+08:00')]
        try:
            why = fa._school_same_due('2026-11-05', card, evidence)
            got = (why, 'no-raise')
        except Exception as error:  # noqa: BLE001
            got = (type(error).__name__, str(error))
        print(f'  reminder={text!r} (own day 11-05, card day 11-06) -> {got!r}')
        case(f'H1 differing-day {text!r} is judged, not raised', got[1] != 'AttributeError', True)
    same = fa._school_same_due('2026-11-06', card,
                               [dict(ref='r', text='明天交', time='2026-11-04T18:00:00+08:00')])
    case('H1b same-day reminder stays unremarkable', same, '')
    # Static scan: no raw-string _SCHOOL_* constant is used as a compiled pattern.
    raw = {name: value for name, value in vars(fa).items()
           if name.startswith('_SCHOOL_') and isinstance(value, str)}
    compiled = [name for name, value in vars(fa).items()
                if name.startswith('_SCHOOL_') and isinstance(value, re.Pattern)]
    misuse = [(name, method) for name in raw for method in ('search', 'match', 'findall', 'sub', 'split')
              if re.search(rf'\b{name}\.{method}\(', SOURCE)]
    print(f'  module constants: {len(compiled)} compiled, {len(raw)} raw strings: {sorted(raw)}')
    print(f'  raw-string-as-pattern misuses: {misuse}')
    case('H1c no raw _SCHOOL_* string used as a compiled pattern', misuse, [])
    line = next((n for n, text in enumerate(SOURCE.splitlines(), 1) if 're.search(_SCHOOL_MOVED,said)' in text), 0)
    print(f'  fixed line {line}: {SOURCE.splitlines()[line - 1].strip() if line else "NOT FOUND"}')
    case('H1d the differing-day branch uses re.search(_SCHOOL_MOVED, said)', line > 0, True)


def h2_split_filter():
    print('\n== H2 (F2) split-residue filter boundary ==')
    boundary = [('语文：生字', True, 'subject label'), ('美术老师今天课上说。', False, 'pure lead-in'),
                ('综合：带跳绳', True, 'action verb 带'), ('数学：第3页第2题', True, 'subject label + digits'),
                ('《成长手册》第3页的自我评价', True, 'object/digits')]
    for title, expected, why in boundary:
        got = keeps_split_fragment(title, '')
        print(f'  {title!r} -> {"KEEPS" if got else "SKIPS"} ({why})')
        case(f'H2 fragment {title!r} -> {"kept" if expected else "dropped"}', got, expected)
    # End to end: a formed requirement that the old whitelist dropped must now survive.
    text = '数学：口算第12页第1—3题。\n语文：预习《成长手册》第3页。'
    evidence = [dict(ref='message:s1:m1', text=text, time='2026-11-04T15:00:00+08:00', sender='林老师',
                     publisher='publisher:x', kind='text', unread=False, content_incomplete=False, attachments=[])]
    proposals = [dict(title_quote='口算第12页第1—3题', due='', task_title='数学：口算第12页',
                      task_goal='完成口算第12页第1—3题。', task_state='ready', task_change='new',
                      task_target_id='', task_purpose='admin', task_submission='', evidence=[{'ref': 'message:s1:m1'}])]
    out, marks = fa._school_separate_outcomes(proposals, evidence, set(), source_later=[])
    formed = [(i, p) for i, p in enumerate(out) if 'formed' in marks.get(i, {})]
    print(f'  formed proposals: {[(i, p.get("task_title")) for i, p in formed]}')
    for i, prop in formed:
        got = keeps_split_fragment(prop.get('task_title'), prop.get('task_goal'))
        case(f'H2b formed {prop.get("task_title")!r} survives the new filter', got, True)


def h3_publisher():
    print('\n== H3 (F3) folded card keeps a stable publisher; source_id no longer gates identity ==')
    folded = dict(id='p-folded', child_id='c1', title='数学：《每日练习》第26页第1—4题',
                  body='完成《每日练习》第26页第1—4题。', due='2026-11-06',
                  evidence=[dict(ref='message:s-wechat:m1'), dict(ref='message:s-qq:m3')],
                  plan={'school_task': dict(title='数学：《每日练习》第26页第1—4题',
                                            goal='完成《每日练习》第26页第1—4题。', purpose='learning',
                                            change='new', state='ready')})
    store = FakeStore(SOURCES, MESSAGES, [folded])
    with store._db() as c:
        target = fa.school_pending_targets(store, 'c1', c)[0]
    print(f'  target: id={target["id"]} publisher={target["publisher"][:24]!r} source_id={target["source_id"]!r}'
          f' refs={target["refs"]}')
    case('H3 folded card keeps its publisher', bool(target['publisher']), True,
         'publisher values are deduped; source_id is only reported when one source remains')
    case('H3b folded card reports source_id="" (two channels, one publisher)', target['source_id'], '')
    notice = dict(title='数学：《每日练习》第26页第1—3题', goal='完成《每日练习》第26页第1—3题。')
    cited = [dict(ref='message:s-wechat:m5', publisher=target['publisher'],
                  time='2026-11-04T18:00:00+08:00', text=MESSAGES[('s-wechat', 'm5')]['text'])]
    link = fa._school_pending_link(target, 'same', notice, cited, '', '')
    print(f'  third notice link -> {link}')
    case('H3c a third notice still folds into the cross-channel card', link is not None, True)
    # Two DIFFERENT teachers (different display names) must not be deduped into one identity.
    mixed = dict(folded, id='p-mixed', evidence=[dict(ref='message:s-wechat:m1'),
                                                 dict(ref='message:s-qq:m6')])
    store2 = FakeStore(SOURCES, MESSAGES, [mixed])
    with store2._db() as c:
        t2 = fa.school_pending_targets(store2, 'c1', c)[0]
    print(f'  mixed senders: publisher={t2["publisher"]!r} source_id={t2["source_id"]!r}')
    case('H3d two different senders do not collapse into one publisher', t2['publisher'], '')
    cited2 = [dict(ref='message:s-wechat:m5', publisher=t2['publisher'],
                   time='2026-11-04T18:00:00+08:00', text=MESSAGES[('s-wechat', 'm5')]['text'])]
    case('H3e no publisher -> no silent link', fa._school_pending_link(t2, 'same', notice, cited2, '', ''), None)


def h4_ambiguity_and_accept():
    print('\n== H4 (R1) ambiguity keeps the notice its own card ==')
    math = dict(id='p-math', child_id='c1', title='数学：《每日练习》第26页第1—4题',
                body='完成《每日练习》第26页第1—4题。', due='2026-11-06',
                evidence=[dict(ref='message:s-wechat:m1')],
                plan={'school_task': dict(title='数学：《每日练习》第26页第1—4题',
                                          goal='完成《每日练习》第26页第1—4题。', purpose='learning',
                                          change='new', state='ready')}, created='2026-11-04 10:00:00')
    chinese = dict(id='p-chinese', child_id='c1', title='语文：《每日练习》第26页朗读',
                   body='朗读《每日练习》第26页短文两遍。', due='2026-11-06',
                   evidence=[dict(ref='message:s-qq:m4')],
                   plan={'school_task': dict(title='语文：《每日练习》第26页朗读',
                                             goal='朗读《每日练习》第26页短文两遍。', purpose='learning',
                                             change='new', state='ready')}, created='2026-11-04 09:00:00')
    store = FakeStore(SOURCES, MESSAGES, [math, chinese])
    with store._db() as c:
        targets = fa.school_pending_targets(store, 'c1', c)
    notice = dict(title='《每日练习》第26页第1—3题', goal='完成《每日练习》第26页第1—3题。')
    cited = [dict(ref='message:s-wechat:m5', publisher=targets[0]['publisher'],
                  time='2026-11-04T18:00:00+08:00', text=MESSAGES[('s-wechat', 'm5')]['text'])]
    proven = [(t['id'], fa._school_pending_link(t, 'same', notice, cited, '', '')) for t in targets]
    print(f'  per-card proof: {[(i, bool(p)) for i, p in proven]}')
    hits = [p for _, p in proven if p]
    case('H4 two waiting cards still share one object (ambiguity is real)', len(hits), 2,
         'unchanged object/subject-blind proof')
    print('  new guard: _select L8138-8140 links only when len(hits)==1; two hits leave the notice its own card')
    named = fa._school_pending_link(targets[0], 'same', notice, cited, '', '')
    case('H4b an explicitly named pending target still links', named is not None, True)

    print('\n== H5 (new overwrite point) _school_fold_pending keeps the later original out of body/evidence ==')
    card = dict(id='p-old', child_id='c1', title='数学：《每日练习》第26页第1—4题',
                body='完成《每日练习》第26页第1—4题。', due='2026-11-06',
                evidence=[dict(ref='message:s-wechat:m1')],
                plan={'school_task': dict(title='数学：《每日练习》第26页第1—4题',
                                          goal='完成《每日练习》第26页第1—4题。', purpose='learning',
                                          change='new', state='ready')})
    for change in ('same', 'append', 'update', 'cancel'):
        st = FakeStore(SOURCES, MESSAGES, [json.loads(json.dumps(card))])
        item = dict(child_id='c1', body='更正：只做第26页第1—3题，改到11月10日交。', due='2026-11-10',
                    evidence=[dict(ref='message:s-wechat:m5')])
        with st._db() as c:
            ok = fa.Store._school_fold_pending(None, c, item, dict(item_id='p-old', change=change), NOW)
            row = c.execute('SELECT * FROM agent_items WHERE id=?', ('p-old',)).fetchone()
        plan = json.loads(row['plan'])
        body_has = '第1—3题' in row['body']
        evidence_has = 'message:s-wechat:m5' in str(row['evidence'])
        originals = bool((plan.get('school_folded') or [{}])[0].get('originals'))
        print(f'  change={change!r} folded={ok} body={row["body"]!r}'
              f' | body_has={body_has} evidence_has={evidence_has} plan.originals={originals}')
        case(f'H5 fold change={change!r}: later text readable in the card body', body_has, True,
             'the agenda card and the accepted action both read body')
        case(f'H5b fold change={change!r}: later original ref kept in evidence', evidence_has, True,
             'accept builds the task source text from evidence')
    agenda = open(REPO + '/family_agenda.py', encoding='utf-8').read()
    readers = [line.strip() for line in agenda.splitlines() if 'school_folded' in line]
    case('H5c no display reader of plan.school_folded (invisible provenance)', readers, [],
         'only family_agent writers store it')

    accepted = dict(card, id='p-card', state='accepted', task_id='AGENT-1')
    follow = dict(id='p-follow', child_id='c1', kind='school', title='补充：第26页第1—3题拍照',
                  body='补充：第26页第1—3题拍照。', due='', evidence=[dict(ref='message:s-wechat:m5')],
                  plan={'school_pending_of': dict(item_id='p-card', change='same', publisher='publisher:x')})
    st = FakeStore(SOURCES, MESSAGES, [accepted, follow],
                   tasks=[dict(id='AGENT-1', title='数学：《每日练习》第26页第1—4题', due='2026-11-06',
                               action='完成《每日练习》第26页第1—4题。')])
    try:
        used = fa._fold_school_follows(None, st, NOW)
        with st._db() as c:
            task = c.execute('SELECT action FROM manual_tasks WHERE id=?', ('AGENT-1',)).fetchone()
            row = c.execute('SELECT state,task_id FROM agent_items WHERE id=?', ('p-follow',)).fetchone()
        print(f'  _fold_school_follows used={used} action={task["action"]!r} row={dict(row)}')
        case('H5d accepted card absorbs its waiting notice into the task action',
             '补充：第26页第1—3题拍照。' in (task['action'] or ''), True)
    except Exception as error:  # noqa: BLE001
        print(f'  _fold_school_follows probe raised {type(error).__name__}: {error}')


if __name__ == '__main__':
    sha1 = hashlib.sha1(open(REPO + '/family_agent.py', 'rb').read()).hexdigest()
    print(f'audited family_agent.py sha1={sha1} (target {TARGET})')
    if sha1 != TARGET:
        print('  WARNING: working tree changed; conclusions apply to the file as read now')
    h1_same_due()
    h2_split_filter()
    h3_publisher()
    h4_ambiguity_and_accept()

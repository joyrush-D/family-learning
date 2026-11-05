# -*- coding: utf-8 -*-
"""Round-3 quick audit probes for family_agent.py sha1 1756bf38 (+ regression file 3bdfd53a).

Read-only: imports the repo working tree (sha1 verified in header), invented data only, no model, no database.
Run: python3 -B probes-r3.py > probes-r3-out.txt
"""
import hashlib
import json
import sqlite3
import sys

REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
TARGET = '1756bf3830261e688d33b2b4105374a5a86330f4'
sys.path.insert(0, REPO)
import family_agent as fa  # noqa: E402
import family_agenda as ga  # noqa: E402

NOW = fa.dt.datetime(2026, 11, 4, 20, 0, tzinfo=fa.TZ)


class _DB:
    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self.c

    def __exit__(self, *error):
        return False


class Shim:
    def __init__(self, c):
        self.c = c

    def _db(self):
        return _DB(self.c)


def case(name, got, expected):
    print(f'[{"PASS" if got == expected else "FAIL"}] {name}: got={got!r} expected={expected!r}')


def item_row(c, **kw):
    defaults = dict(id='agent-card', job_id='job', child_id='c1', kind='school', title='待核对：数学',
                    body='完成数学《每日练习》第26页。', evidence='[]', due='2026-11-06',
                    created=NOW.isoformat(), updated=NOW.isoformat(), state='pending', task_id='', plan='{}')
    defaults.update(kw)
    keys = list(defaults)
    c.execute('INSERT INTO agent_items(%s) VALUES(%s)' % (','.join(keys), ','.join('?' * len(keys))),
              [defaults[k] for k in keys])


def folded_plan(change, ref='message:s-wechat:m5', text='更正：只做第26页第1—3题，改到11月10日交。',
                time='2026-11-04T18:00:00+08:00'):
    return dict(school_folded=[dict(refs=[ref], change=change, at=NOW.isoformat(),
                                    originals=[dict(ref=ref, text=text, time=time, sender='林老师',
                                                    publisher='publisher:fiction')])])


def t1_fold_visibility():
    print('\n== T1 fold: four changes -> card body + due ==')
    incoming = {
        'same': '数学《每日练习》第26页，今晚完成。',
        'append': '补充：数学《每日练习》第26页还要写算式。',
        'update': '更正：只做第26页第1—3题，改到11月10日交。',
        'cancel': '刚才带落叶那一项取消，不用带。',
    }
    for change, text in incoming.items():
        c = sqlite3.connect(':memory:')
        c.row_factory = sqlite3.Row
        c.execute('CREATE TABLE agent_items (id TEXT PRIMARY KEY, job_id TEXT, child_id TEXT, kind TEXT, title TEXT,'
                  ' body TEXT, evidence TEXT, due TEXT, created TEXT, updated TEXT, state TEXT, task_id TEXT, plan TEXT)')
        item_row(c, plan=json.dumps(dict(school_task=dict(state='review', goal='完成数学《每日练习》第26页。'))))
        c.commit()
        item = dict(child_id='c1', body=text, due='2026-11-04',
                    evidence=[dict(ref='message:s-wechat:m5', text=text, time='2026-11-04T18:00:00+08:00',
                                   sender='林老师', publisher='publisher:fiction', kind='text',
                                   content_incomplete=False, attachments=[], related_messages=[])])
        ok = fa.Store._school_fold_pending(Shim(c), c, item, dict(item_id='agent-card', change=change), NOW)
        row = c.execute('SELECT * FROM agent_items WHERE id=?', ('agent-card',)).fetchone()
        body, due = row['body'], row['due']
        shown = {'same': '今晚完成', 'append': '后到补充原文：', 'update': '后到更正原文：', 'cancel': '取消依据：'}[change]
        print(f'  change={change:6} body={body!r} due={due!r}')
        case(f'T1 {change}: later text visible in card body', shown in body, True)
        expected_due = {'same': '2026-11-06', 'append': '2026-11-06', 'update': '2026-11-06', 'cancel': ''}[change]
        case(f'T1b {change}: due', due, expected_due)
        c.close()


def t2_late_due():
    print('\n== T2 _school_late_due: handback words only, never a completion evening ==')
    cases = [
        ('今晚完成，周五交', '2026-11-06'),
        ('改到11月10日交', '2026-11-10'),
        ('明天数学课带来', '2026-11-05'),
        ('改为下周一交回。', '2026-11-09'),
        ('今晚完成', ''),
        ('第12页范围不变。', ''),
        ('改到11月10日', ''),
        ('数学作业', ''),
    ]
    for text, expected in cases:
        got = fa._school_late_due([dict(text=text, time='2026-11-04T17:00:00+08:00')], '2026-11-06')
        print(f'  {text!r:24} -> {got!r} (old due 11-06)')
        case(f'T2 {text!r}', got, expected)
    # The declared old_due parameter is never read: prove it cannot change the answer.
    a = fa._school_late_due([dict(text='改到11月10日交', time='2026-11-04T17:00:00+08:00')], '2020-01-01')
    b = fa._school_late_due([dict(text='改到11月10日交', time='2026-11-04T17:00:00+08:00')], '2026-11-06')
    case('T2 old_due has no effect (parameter is dead)', a, b)


def source_ref_lines(source):
    """Mirror of the UI/agenda convention: cite only lines that start with message: (calendar.js:449, app.js:138)."""
    return [x.strip() for x in str(source).splitlines() if x.strip().startswith('message:')]


def t3_source_visibility():
    print('\n== T3 accept: action carries the text, source carries the ref; update/cancel cannot be a cited message ==')
    plan = folded_plan('update', text='更正：只做第26页第1—3题，改到11月10日交。')
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE agent_items(id TEXT PRIMARY KEY, task_id TEXT)')
    c.execute('CREATE TABLE manual_tasks(id TEXT PRIMARY KEY, action TEXT, source TEXT, due TEXT)')
    c.execute("INSERT INTO agent_items(id,task_id) VALUES('agent-card','TASK-1')")
    c.execute("INSERT INTO manual_tasks VALUES('TASK-1',?,?,?)",
              ('完成数学《每日练习》第26页。', 'Agent建议:agent-card\nmessage:s-wechat:m04\n完成《每日练习》第26页第1—4题。',
               '2026-11-06'))
    c.commit()
    fa._school_accept_fold(Shim(c), dict(id='agent-card'), plan)
    task = c.execute("SELECT * FROM manual_tasks WHERE id='TASK-1'").fetchone()
    lines = source_ref_lines(task['source'])
    print(f'  action={task["action"]!r}')
    print(f'  source={task["source"]!r}')
    print(f'  cited message refs (line-start)={lines}')
    case('T3 update: correction text in the action', '第1—3题' in task['action'], True)
    case('T3b update: correction ref NOT a cited message line', 'message:s-wechat:m5' in lines, False)
    case('T3c update: ref still appears in the source note', '后到原文（更正/取消依据，不进本事项日期判断）：message:s-wechat:m5' in task['source'], True)
    case('T3d update: note carries no original text (only the ref)', '第1—3题' in task['source'].split('后到原文')[1], False)
    # same/append stay cited: the message joins the sources as usual.
    for change in ('same', 'append'):
        c2 = sqlite3.connect(':memory:')
        c2.row_factory = sqlite3.Row
        c2.execute('CREATE TABLE agent_items(id TEXT PRIMARY KEY, task_id TEXT)')
        c2.execute('CREATE TABLE manual_tasks(id TEXT PRIMARY KEY, action TEXT, source TEXT, due TEXT)')
        c2.execute("INSERT INTO agent_items(id,task_id) VALUES('agent-card','TASK-1')")
        c2.execute("INSERT INTO manual_tasks VALUES('TASK-1',?,?,?)", ('完成数学《每日练习》第26页。',
                   'Agent建议:agent-card\nmessage:s-wechat:m04\n完成《每日练习》第26页第1—4题。', '2026-11-06'))
        c2.commit()
        fa._school_accept_fold(Shim(c2), dict(id='agent-card'),
                               folded_plan(change, text='数学《每日练习》第26页，今晚完成。'))
        src = c2.execute("SELECT source FROM manual_tasks WHERE id='TASK-1'").fetchone()['source']
        print(f'  change={change}: cited message refs={source_ref_lines(src)}')
        case(f'T3e {change}: later message joins the cited messages', 'message:s-wechat:m5' in source_ref_lines(src), True)
    # UI consequence: the 看原消息 buttons are built only from source_ref_lines, so update/cancel have no button.
    c3 = sqlite3.connect(':memory:')
    c3.row_factory = sqlite3.Row
    c3.execute('CREATE TABLE agent_items(id TEXT PRIMARY KEY, task_id TEXT)')
    c3.execute('CREATE TABLE manual_tasks(id TEXT PRIMARY KEY, action TEXT, source TEXT, due TEXT)')
    c3.execute("INSERT INTO agent_items(id,task_id) VALUES('agent-card','TASK-1')")
    c3.execute("INSERT INTO manual_tasks VALUES('TASK-1',?,?,?)", ('完成数学《每日练习》第26页。',
               'Agent建议:agent-card\nmessage:s-wechat:m04\n完成《每日练习》第26页第1—4题。', '2026-11-06'))
    c3.commit()
    fa._school_accept_fold(Shim(c3), dict(id='agent-card'), folded_plan('cancel', text='刚才带两片落叶那一项取消，不用带叶子和旧书。'))
    src = c3.execute("SELECT source FROM manual_tasks WHERE id='TASK-1'").fetchone()['source']
    print(f'  cancel: cited message refs={source_ref_lines(src)} note={"更正/取消依据" in src}')
    case('T3f cancel: no cited message button for the cancellation', 'message:s-wechat:m5' in source_ref_lines(src), False)


def t3b_agenda_complete_on():
    print('\n== T3b family_agenda.metadata: citing the superseded original (m04) next to the correction (m05) ==')
    messages = {
        'm04': dict(id='m04', text='数学：完成《每日练习》第26页第1—4题，周五交回。', sender='林老师',
                    sender_id='wx-1001', time='2026-11-04T09:00:00+08:00', kind='text',
                    content_incomplete=False, attachments=[]),
        'm05': dict(id='m05', text='更正：只做《每日练习》第26页第1—3题，改到11月10日交。', sender='林老师',
                    sender_id='wx-1001', time='2026-11-04T18:00:00+08:00', kind='text',
                    content_incomplete=False, attachments=[]),
    }
    original = fa.Store._message_context
    fa.Store._message_context = lambda self, c, obj: (
        dict(id='s-wechat', child_id='c1', platform='wechat', name='微信班级群'), messages[obj['message_id']])
    try:
        class App:
            DATA = '/tmp'

            def connect(self):
                return _DB(sqlite3.connect(':memory:'))

            def profiles(self, c):
                return [dict(id='c1', name='示例甲')]
        app = App()
        c = sqlite3.connect(':memory:')
        groups = {
            'without m05 (today)': ['message:s-wechat:m04'],
            'with m05 cited': ['message:s-wechat:m04', 'message:s-wechat:m05'],
        }
        for label, refs in groups.items():
            meta = ga.metadata(app, c, 'c1', '数学：《每日练习》第26页第1—3题', '2026-11-10', refs,
                               dict(category='homework'), purpose='learning',
                               publication_ref='message:s-wechat:m04',
                               date_quote='完成《每日练习》第26页第1—4题', goal='完成《每日练习》第26页第1—3题，改到11月10日交。',
                               date_header='数学：', date_siblings=[], action='完成《每日练习》第26页第1—3题，改到11月10日交。')
            print(f'  {label}: due_on={meta.get("due_on")!r} complete_on={meta.get("complete_on")!r}'
                  f' published_on={meta.get("published_on")!r} due_kind={meta.get("due_kind")!r}')
    finally:
        fa.Store._message_context = original


def t4_test_coverage():
    print('\n== T4 regression file coverage (static) ==')
    import ast
    tree = ast.parse(open(REPO + '/test_school_fold_visibility.py', encoding='utf-8').read())
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith(('Fold', 'Folded')):
            for inner in node.body:
                if isinstance(inner, ast.FunctionDef) and inner.name.startswith('test_'):
                    found.append((node.name, inner.name))
    for cls, name in found:
        print(f'  {cls}.{name}')
    joins = ' '.join(name for _, name in found)
    print('  surfaces:')
    print('   body:', all(token in joins for token in ('body', 'cancellation', 'reminder')))
    print('   action:', 'action' in joins)
    print('   source:', 'source' in joins)
    print('   due:', 'day' in joins or 'due' in joins)
    print('   change classes in FoldPendingTest:',
          [c for c in ('same', 'append', 'update', 'cancel')
           if any(c in name for _, name in found)])
    print('   DB-level assertions:', 'SELECT' in open(REPO + '/test_school_fold_visibility.py', encoding='utf-8').read())


if __name__ == '__main__':
    sha = hashlib.sha1(open(REPO + '/family_agent.py', 'rb').read()).hexdigest()
    tfile = hashlib.sha1(open(REPO + '/test_school_fold_visibility.py', 'rb').read()).hexdigest()
    print(f'audited family_agent.py sha1={sha} (target {TARGET})')
    print(f'audited test_school_fold_visibility.py sha1={tfile}')
    if sha != TARGET:
        print('  WARNING: working tree changed; conclusions apply to the code read now')
    t1_fold_visibility()
    t2_late_due()
    t3_source_visibility()
    t3b_agenda_complete_on()
    t4_test_coverage()

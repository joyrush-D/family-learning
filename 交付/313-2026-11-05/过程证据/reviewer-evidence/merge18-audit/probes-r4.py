"""r4 targeted re-check of the four BLOCK items from report-r3 (read-only, fictional data, no model).

Run: python3 -B probes-r4.py > probes-r4-out.txt
"""
import datetime as dt
import hashlib
import json
import re
import sqlite3
import sys

REPO = '/Users/joyrush/.local/share/family-learning/public-integration-20260926'
sys.path.insert(0, REPO)
import family_agent as agent  # noqa: E402
import family_agenda as agenda  # noqa: E402

NOW = dt.datetime(2026, 11, 4, 20, 0, tzinfo=agent.TZ)
CARD_ID = 'agent-card'
TASK_ID = 'TASK-1'


def sha1(path):
    return hashlib.sha1(open(path, 'rb').read()).hexdigest()


class _DB:
    def __init__(self, conn):
        self.connection = conn

    def __enter__(self):
        return self.connection

    def __exit__(self, *error):
        return False


class Shim:
    def __init__(self, conn):
        self.connection = conn

    def _db(self):
        return _DB(self.connection)


def quote(ref, text, time='2026-11-04T16:00:00+08:00'):
    return dict(ref=ref, text=text, time=time, sender='数学李老师', publisher='publisher:fiction-math',
                kind='text', content_incomplete=False, attachments=[], related_messages=[ref], source='虚构班级')


def folded(change, ref='message:s-wechat:m05', text='数学《每日练习》第26页只做第1—3题。', time='2026-11-04T16:00:00+08:00'):
    return dict(item_id=CARD_ID, refs=[ref], change=change, at=NOW.isoformat(),
                originals=[dict(ref=ref, text=text, time=time)])


def new_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE agent_items(id TEXT PRIMARY KEY, job_id TEXT, child_id TEXT, kind TEXT, title TEXT, '
                 'body TEXT, evidence TEXT, due TEXT, created TEXT, updated TEXT, state TEXT, task_id TEXT, plan TEXT)')
    conn.execute('CREATE TABLE manual_tasks(id TEXT PRIMARY KEY, action TEXT, source TEXT, due TEXT)')
    conn.commit()
    return conn


def fold(conn, change, text, body='完成数学《每日练习》第26页第1—4题。', due='2026-11-06'):
    plan = dict(school_task=dict(state='review', goal=body))
    conn.execute('INSERT OR REPLACE INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,created,updated,state,task_id,plan)'
                 " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (CARD_ID, 'job', 'child-1', 'school', '待核对：数学', body, '[]', due,
                  NOW.isoformat(), NOW.isoformat(), 'pending', '', json.dumps(plan)))
    conn.commit()
    item = dict(child_id='child-1', body=text, due=due, evidence=[quote('message:s-wechat:m05', text)])
    ok = agent.Store._school_fold_pending(Shim(conn), conn, item, dict(item_id=CARD_ID, change=change), NOW)
    return ok, dict(conn.execute('SELECT * FROM agent_items WHERE id=?', (CARD_ID,)).fetchone())


def source_refs(source):
    return [line for line in str(source or '').splitlines() if line.strip().startswith('message:')]


def case(name, got, want):
    verb = 'PASS' if got == want else 'FAIL'
    print(f'  [{verb}] {name}: got={got!r} want={want!r}')
    return got == want


def b1_multiline():
    print('\n== B1 多行后到原文：卡 body（DB 实测） ==')
    cases = [
        ('update', '更正：数学《每日练习》第26页只做第1—3题。\n明天早上交回。', '后到更正原文（2026-11-04 16:00）：', '2026-11-05'),
        ('append', '补充：数学《每日练习》第26页还要写算式。\n算式写在练习册上。', '后到补充原文（2026-11-04 16:00）：', '2026-11-06'),
        ('cancel', '刚才带落叶那一项取消。\n不用带叶子和旧书。', '取消依据（2026-11-04 16:00）：', ''),
        ('same', '数学《每日练习》第26页，今晚完成。\n明天早上交。', '', '2026-11-06'),
    ]
    body_text = {}
    for change, text, label, want_due in cases:
        conn = new_db()
        ok, row = fold(conn, change, text)
        body = row['body']
        body_text[change] = body
        print(f'  [{change}] body={body!r}')
        print(f'    due={row["due"]!r} (want {want_due!r})')
        first_line, second_line = '第1—3题' if change == 'update' else None, None
        if change in ('update', 'append'):
            wants = [line.split('\n')[0].strip('。') for line in text.split('\n')]
            missing = [part for part in wants if part and part.strip('。') not in body]
        elif change == 'cancel':
            missing = [part for part in text.split('\n') if part.strip() and part.strip('。') not in body]
        else:
            missing = [part for part in text.split('\n') if part.strip() and part.strip() not in body]
        print(f'    missing_parts={missing}')
        if label:
            print(f'    label_present={"(" in body and label.split("（")[0] in body}')
        case(f'B1 {change} due', row['due'], want_due)
        case(f'B1 {change} second line in body', text.split('\n')[-1].strip('。') in body, True)
        if change in ('update', 'append'):
            case(f'B1 {change} first line in body', text.split('\n')[0].strip('。') in body, True)
        else:
            case(f'B1 {change} first line in body', text.split('\n')[0].strip('。') in body, True)
        conn.close()
    print('  note: card body 首行仍是原卡自己的第1—4题（原始通知保留，更正在其后带标签行）:',
          body_text.get('update', '').split('\n')[0])
    return body_text


def b1_accept(update_body):
    print('\n== B1b accept 之后 manual_tasks.action（DB 实测） ==')
    ok = True
    for change, text in [
        ('update', '更正：数学《每日练习》第26页只做第1—3题。\n明天早上交回。'),
        ('append', '补充：数学《每日练习》第26页还要写算式。\n算式写在练习册上。'),
        ('cancel', '刚才带落叶那一项取消。\n不用带叶子和旧书。'),
        ('same', '数学《每日练习》第26页，今晚完成。\n明天早上交。'),
    ]:
        conn = new_db()
        fold(conn, change, text)
        conn.execute('UPDATE agent_items SET task_id=? WHERE id=?', (TASK_ID, CARD_ID))
        conn.execute('INSERT INTO manual_tasks(id,action,source,due) VALUES(?,?,?,?)',
                     (TASK_ID, '完成数学《每日练习》第26页。',
                      'Agent建议:agent-card\nmessage:s-wechat:m04\n完成《每日练习》第26页第1—4题。', '2026-11-06'))
        conn.commit()
        plan = json.loads(conn.execute('SELECT plan FROM agent_items WHERE id=?', (CARD_ID,)).fetchone()['plan'])
        agent._school_accept_fold(Shim(conn), dict(id=CARD_ID), plan)
        task = dict(conn.execute('SELECT * FROM manual_tasks WHERE id=?', (TASK_ID,)).fetchone())
        action = task['action']
        parts = [line.strip('。') for line in text.split('\n') if line.strip()]
        missing = [part for part in parts if part.strip('。') not in action]
        print(f'  [{change}] action={action!r}')
        print(f'    source_refs={source_refs(task["source"])} note={"后到原文" in task["source"]}')
        print(f'    missing_parts={missing}')
        ok &= case(f'B1b {change} all lines in action', missing, [])
        if change in ('update', 'cancel'):
            ok &= case(f'B1b {change} correction not a cited message', 'message:s-wechat:m05' in source_refs(task['source']), False)
            ok &= case(f'B1b {change} note carries time+words', ('2026-11-04 16:00' in task['source']) and ('后到原文' in task['source']), True)
        else:
            ok &= case(f'B1b {change} later message cited', 'message:s-wechat:m05' in source_refs(task['source']), True)
        conn.close()
    return ok


def b2_due():
    print('\n== B2 _school_late_due 改期/误设 ==')
    ok = True
    table = [
        ('改到11月10日交。', '2026-11-10'),
        ('推迟到11月10日交。', '2026-11-10'),
        ('改为11月10日交。', '2026-11-10'),
        ('改到11月10日。', '2026-11-10'),
        ('改到11月10日交作业。', '2026-11-10'),
        ('改到11月10日交回。', '2026-11-10'),
        ('今晚完成，周五交给我。', '2026-11-06'),
        ('今天数学课带来。', '2026-11-04'),
        ('明天数学课带来。', '2026-11-05'),
        ('今晚完成。', ''),
        ('第12页范围不变。', ''),
        ('数学作业。', ''),
        ('改到11月10日', '2026-11-10'),
        ('改到下周。', ''),
        ('上课时间改到11月10日下午。', ''),
    ]
    for text, want in table:
        got = agent._school_late_due([dict(text=text, time='2026-11-04T17:00:00+08:00')])
        ok &= case(f'B2 {text}', got, want)
    print('  note: 最后一条是残余提示：非作业句“上课时间改到…”不设本事项截止（更保守）；若产品希望它也改期，需另加作业对象门。')
    return ok


def b3_note_and_complete_on():
    print('\n== B3 引用约定：note 不以行首 message: 开头 + complete_on 机制 ==')
    ok = True
    note = agent._school_fold_note(('message:s-wechat:m05', '更正：只做第1—3题，改到11月10日交。', 'update',
                                    '2026-11-04T16:00:00+08:00'))
    print('  note =', note)
    ok &= case('B3 note starts with the note banner', note.startswith(agent._SCHOOL_FOLD_NOTE), True)
    ok &= case('B3 note is not a cited message line', note.startswith('message:'), False)
    ok &= case('B3 note carries time', '2026-11-04 16:00' in note, True)
    ok &= case('B3 note carries words', '只做第1—3题' in note, True)

    messages = {
        'm04': dict(id='m04', text='今晚完成《每日练习》第26页第1—4题，周五交回。', sender='林老师',
                    sender_id='wx-1001', time='2026-11-04T09:00:00+08:00', kind='text',
                    content_incomplete=False, attachments=[]),
        'm05': dict(id='m05', text='更正：今晚完成《每日练习》第26页第1—4题改为只做第1—3题，改到11月10日交。',
                    sender='林老师', sender_id='wx-1001', time='2026-11-04T16:00:00+08:00', kind='text',
                    content_incomplete=False, attachments=[]),
    }
    original = agent.Store._message_context
    agent.Store._message_context = lambda self, c, obj: (
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
        results = {}
        for label, refs in (('只有 m04（新约定：note 不是行首引用）', ['message:s-wechat:m04']),
                            ('m04+m05 都被当行首引用（旧场景）', ['message:s-wechat:m04', 'message:s-wechat:m05'])):
            meta = agenda.metadata(app, c, 'c1', '数学：《每日练习》第26页第1—3题', '2026-11-10', refs,
                                   date_quote='今晚完成《每日练习》第26页第1—4题')
            results[label] = (meta.get('due_on'), meta.get('complete_on'), meta.get('due_kind'))
            print(f'  {label}: due_on={meta.get("due_on")!r} complete_on={meta.get("complete_on")!r} '
                  f'due_kind={meta.get("due_kind")!r}')
        ok &= case('B3 complete_on kept when only the first notice is cited',
                   results['只有 m04（新约定：note 不是行首引用）'][1], '2026-11-04')
        ok &= case('B3 mechanism: citing the correction drops complete_on (motivation real)',
                   results['m04+m05 都被当行首引用（旧场景）'][1], '')
    finally:
        agent.Store._message_context = original
    return ok


def b4_static():
    print('\n== B4 _school_role_reselect 排除列表 ==')
    src = open(f'{REPO}/family_agent.py', encoding='utf-8').read()
    start = src.index('def _school_role_reselect')
    region = src[start:start + 6000]
    ok = True
    ok &= case("B4 exclusion tuple names 'school_folded'", "'school_folded'" in region, True)
    ok &= case('B4 exclusion is the early any(plan.get(k) for k in (...)) guard',
               bool(re.search(r"if any\(plan\.get\(k\) for k in \(.*?'school_folded'.*?\)\):return None", region, re.S)), True)
    line = src[:start].count('\n') + 1
    for offset, text in enumerate(region.split('\n')):
        if 'school_folded' in text:
            print(f'  family_agent.py:{line + offset}: {text.strip()}')
            break
    return ok


def b2b_fold_due():
    print('\n== B2b 改期经 _school_fold_pending 落库 ==')
    ok = True
    for text in ('更正：只做第26页第1—3题，改到11月10日交。', '推迟到11月10日交。', '改为11月10日交。'):
        conn = new_db()
        ok_fold, row = fold(conn, 'update', text)
        print(f'  [{text}] folded={ok_fold} due={row["due"]!r}')
        ok &= case(f'B2b {text}', row['due'], '2026-11-10')
        conn.close()
    return ok


def b3b_static_citation():
    print('\n== B3b _fold_school_follows 写 source 的引用约定（静态核对） ==')
    src = open(f'{REPO}/family_agent.py', encoding='utf-8').read()
    start = src.index('def _fold_school_follows')
    end = src.index('\ndef ', start + 10)
    region = src[start:end]
    ok = True
    ok &= case('B3b dynamic extra is gated to same/append',
               "if change in ('same','append') and str(e.get('ref')) not in source" in region, True)
    ok &= case('B3b notes use _school_fold_note', '_school_fold_note(' in region, True)
    ok &= case('B3b notes gated to update/cancel', "if change in ('update','cancel')" in region, True)
    ok &= case('B3b no raw ref+text extra for update/cancel',
               "extra=[str(e.get('ref'))+'\\n'+str(e.get('text')).strip() for e in cited" in region, True)
    print('  note: _fold_school_follows 端到端需要 app/配置，本轮未动态跑；其写 source 的两个表达式已静态核对。')
    return ok


def main():
    print('audited family_agent.py sha1 =', sha1(f'{REPO}/family_agent.py'))
    print('audited test_school_fold_visibility.py sha1 =', sha1(f'{REPO}/test_school_fold_visibility.py'))
    print('audited family_llm.py sha1 =', sha1(f'{REPO}/family_llm.py'))
    print('NOW =', NOW.isoformat(), ' TZ =', agent.TZ)
    b1 = b1_multiline()
    ok = b1_accept(b1.get('update', ''))
    ok &= b2_due()
    ok &= b2b_fold_due()
    ok &= b3_note_and_complete_on()
    ok &= b3b_static_citation()
    ok &= b4_static()
    print('\nRESULT:', 'GREEN' if ok else 'RED')
    print('sha after probes =', sha1(f'{REPO}/family_agent.py'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Function-level adversarial probes for merge18 (family_agent.py sha1 de6859a3, build 311).

Read-only: imports the reconstructed build-311 tree at /tmp/merge18_audit (HEAD 58973a6 + fix.patch-311,
verified sha1 de6859a3). All data below is invented/fictional; no model is called and no product DB is touched.
Run: python3 -B probes.py > probes-out.txt
"""
import json
import sqlite3
import sys
from contextlib import nullcontext

sys.path.insert(0, '/tmp/merge18_audit')
import family_agent as fa  # noqa: E402

DE6859A3 = 'de6859a3454b0ee01bc21b5f7a38c7faf9552d98'


class FakeStore:
    """Only the store surface the merge helpers touch."""

    def __init__(self, sources, messages, items, peer_payloads=()):
        self._sources = sources
        self._messages = messages  # (source_id, message_id) -> message dict
        self._conn = sqlite3.connect(':memory:')
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('CREATE TABLE agent_items (id TEXT PRIMARY KEY, job_id TEXT, child_id TEXT, kind TEXT,'
                           ' title TEXT, body TEXT, evidence TEXT, due TEXT, care_id TEXT, record_id TEXT,'
                           ' created TEXT, updated TEXT, plan TEXT, task_id TEXT, state TEXT)')
        self._conn.execute('CREATE TABLE agent_messages (source_id TEXT, payload TEXT)')
        for source_id, payload in peer_payloads:
            self._conn.execute('INSERT INTO agent_messages (source_id, payload) VALUES (?,?)',
                               (source_id, json.dumps(payload)))
        for item in items:
            self._conn.execute('INSERT INTO agent_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (item['id'], '', item['child_id'], 'school', item.get('title', ''), item.get('body', ''),
                                json.dumps(item.get('evidence', [])), item.get('due', ''), '', '',
                                item.get('created', '2026-11-04 10:00:00'), '2026-11-04 10:00:00',
                                json.dumps(item.get('plan', {})), item.get('task_id', ''), item.get('state', 'pending')))
        self._conn.commit()

    def _config(self):
        return {'sources': self._sources}

    def _db(self):
        return self._conn

    def _message_context(self, c, wanted):
        key = (wanted['source_id'], wanted['message_id'])
        return self._sources_by_id[wanted['source_id']], self._messages[key]

    @property
    def _sources_by_id(self):
        return {s['id']: s for s in self._sources}


def msg(mid, text, sender='林老师', sender_id='t1', time='2026-11-04T10:00:00+08:00', kind='text'):
    return dict(id=mid, text=text, sender=sender, sender_id=sender_id, time=time, kind=kind, unread=False,
                content_incomplete=False, attachments=[])


SOURCES = [
    dict(id='s-wechat', child_id='c1', platform='wechat', enabled=1, name='微信班级群'),
    dict(id='s-qq', child_id='c1', platform='qq', enabled=1, name='QQ班级群'),
    dict(id='s-other-child', child_id='c2', platform='wechat', enabled=1, name='二胎的微信班级群'),
]
MESSAGES = {
    ('s-wechat', 'm1'): msg('m1', '今天数学作业：完成《每日练习》第26页第1—4题。', sender_id='wx-1001'),
    ('s-wechat', 'm2'): msg('m2', '数学：完成《每日练习》第26页第1—4题，每题写算式。'),
    ('s-qq', 'm3'): msg('m3', '提醒：数学第26页那项明天交。', sender_id='qq-2002', time='2026-11-04T16:30:00+08:00'),
    ('s-qq', 'm4'): msg('m4', '语文：朗读《每日练习》第26页的短文两遍。', sender_id='qq-3003'),
    ('s-wechat', 'm5'): msg('m5', '补充：数学第26页第1—3题做完拍照。', sender_id='wx-1001',
                            time='2026-11-04T17:00:00+08:00'),
}


def brief(title, goal, change='same', state='ready'):
    return dict(title=title, goal=goal, change=change, state=state)


def role_brief(title, goal):
    return brief(title, goal)


def case(name, got, expected, note=''):
    ok = 'PASS' if got == expected else 'FAIL'
    print(f'[{ok}] {name}: got={got!r} expected={expected!r}' + (f'  # {note}' if note else ''))


def head_same_due(due, target, evidence):
    """The same function as HEAD (git show HEAD:family_agent.py), for contrast."""
    from family_agenda import sent_day
    old = target.get('due') or ''
    days = [sent_day(e.get('time', '')) for e in evidence]
    if due != old and (due or any(fa._SCHOOL_DATE_MENTION.search(e.get('text', '')) for e in evidence)):
        return '提醒的日期与原事项不一致或原事项没有明确截止，是否同一次待核对；原事项和提醒原文都保留。'
    if not all(days) or old and max(days) > old:
        return '提醒的发送日期不明或晚于原事项截止，是否新一轮待核对；原事项和提醒原文都保留。'
    return ''


def probe1_same_due():
    print('\n== P1 _school_same_due: reminder states a different day from the card ==')
    target = dict(due='2026-11-06', title='数学：《每日练习》第26页第1—4题', goal='完成第26页第1—4题')
    print(f'  card due={target["due"]!r}')
    for label, due, text in (
            ('明天交 (no move word)', '2026-11-05', '数学练习册明天交。'),
            ('改到11月10日 (with move word)', '2026-11-10', '数学练习册改到11月10日交。'),
            ('same day 周五', '2026-11-06', '数学练习册周五交。')):
        evidence = [dict(time='2026-11-04T18:30:00+08:00', text=text)]
        try:
            got = fa._school_same_due(due, target, evidence)
            err = None
        except Exception as exc:  # noqa: BLE001 - the point of the probe
            got, err = None, f'{type(exc).__name__}: {exc}'
        print(f'  {label:<28} new -> {got!r}' + (f'  RAISED {err}' if err else ''))
        print(f'  {"":<28} HEAD -> {head_same_due(due, target, evidence)!r}')
        if err:
            print('  ^ _school_same_due L3205 calls _SCHOOL_MOVED.search(said) although _SCHOOL_MOVED is a raw string (L3881):')
            print('    the very branch that judges a differing reminder day raises AttributeError before any review is written.')
    try:
        fa._school_same_due('2026-11-05', target, [dict(time='2026-11-04T18:30:00+08:00', text='明天交。')])
        raised = ()
    except Exception as exc:  # noqa: BLE001
        raised = (type(exc).__name__, str(exc))
    case('P1 differing-day reminder is judged (no exception)', raised, ())
    print('  reachability: _select L8325 (same/ready proposals) and _reconcile_school_same L3459/L3530.')
    print('  run_once catches only (LLMDraftError, AgentError, ValueError) around _select (L10305):')
    print('  an AttributeError escapes, the batch is not saved and its messages get no card.')


def probe2_publisher_collision():
    print('\n== P2 _publisher_cross_channel: display name only identifies the person ==')
    store = FakeStore(SOURCES, MESSAGES, [],
                      peer_payloads=[('s-wechat', MESSAGES[('s-wechat', 'm1')]),
                                     ('s-qq', MESSAGES[('s-qq', 'm3')]),
                                     ('s-qq', msg('p1', '数学第26页那项明天交。', sender='王老师', sender_id='qq-8888'))])
    src_wx = SOURCES[0]
    src_qq = SOURCES[1]
    p_wx = fa._publisher_cross_channel(store, src_wx, MESSAGES[('s-wechat', 'm1')])
    p_qq = fa._publisher_cross_channel(store, src_qq, MESSAGES[('s-qq', 'm3')])
    native_wx = fa._publisher('s-wechat', MESSAGES[('s-wechat', 'm1')])
    print(f'  wechat 王老师 publisher: {p_wx}')
    print(f'  qq     林老师 publisher: {p_qq}   (different display name -> different publisher)')
    fake_qq = msg('mx', '数学第26页那项明天交。', sender='王老师', sender_id='qq-9999',
                  time='2026-11-04T16:30:00+08:00')
    p_other = fa._publisher_cross_channel(store, src_wx, fake_qq)
    p_other_native = fa._publisher('s-wechat', fake_qq)
    print(f'  same child, other platform, same display name 王老师 but sender_id qq-9999: {p_other}')
    print(f'  native per-source publisher would be: {p_other_native}')
    print('  -> one publisher:hash(sender,child,name) for every 王老师 of that child on both platforms')
    case('P2 two different 王老师 accounts of one child read as ONE publisher', p_other != p_other_native, True,
         'publisher is name-only; sender_id is discarded once the peer name matches')
    # cross-child: same name, different child source
    src_other = SOURCES[2]
    p_child2 = fa._publisher_cross_channel(store, src_other,
                                           msg('mz', '数学第26页那项明天交。', sender='王老师', sender_id='wx-7777'))
    print(f'  same display name on the other child c2: {p_child2}  (child in the hash -> no cross-child merge)')
    case('P2b cross-child same-name publisher ids differ', p_child2 != p_other, True)


def folded_item_and_third_notice():
    print('\n== P3 folded card (evidence from two channels) loses its publisher ==')
    targets = None
    item = dict(id='p-folded', child_id='c1', title='数学：《每日练习》第26页第1—4题',
                body='完成《每日练习》第26页第1—4题。\n每题写算式。', due='2026-11-06',
                evidence=[dict(ref='message:s-wechat:m1'), dict(ref='message:s-qq:m3')],
                plan={'school_task': dict(title='数学：《每日练习》第26页第1—4题',
                                          goal='完成《每日练习》第26页第1—4题。\n每题写算式。',
                                          purpose='learning', change='new', state='ready')})
    store = FakeStore(SOURCES, MESSAGES, [item],
                      peer_payloads=[('s-wechat', MESSAGES[('s-wechat', 'm1')]),
                                     ('s-qq', MESSAGES[('s-qq', 'm3')])])
    with store._db() as c:
        targets = fa.school_pending_targets(store, 'c1', c)
    print(f'  school_pending_targets -> {targets}')
    t = targets[0]
    case('P3 folded card target keeps a publisher', bool(t['publisher']), True,
         'len(publishers)==2 because (source_id,publisher) pairs differ -> ("","")')
    cited = [dict(ref='message:s-wechat:m5', publisher=t['publisher'], time='2026-11-04T17:00:00+08:00',
                  text=MESSAGES[('s-wechat', 'm5')]['text'])]
    link = fa._school_pending_link(t, 'same', brief('数学：《每日练习》第26页第1—3题',
                                                    '完成《每日练习》第26页第1—3题'), cited, '', '')
    print(f'  _school_pending_link for a third notice -> {link!r}')
    case('P3b third notice can link to the folded card', link is not None, True,
         'no publisher -> link None -> duplicate pending card instead of folding')
    print('  impact: _save calls _school_fold_pending only when plan.school_pending_of is set at selection;')
    print('  the same publisher=""/append_eligible=False path also blocks a third channel supplement on accepted tasks.')


def two_pending_cards():
    print('\n== P4 two pending cards sharing an object: first match wins ==')
    math = dict(id='p-math', child_id='c1', title='数学：《每日练习》第26页第1—4题',
                body='完成《每日练习》第26页第1—4题。', due='2026-11-06',
                evidence=[dict(ref='message:s-wechat:m1')],
                plan={'school_task': dict(title='数学：《每日练习》第26页第1—4题',
                                          goal='完成《每日练习》第26页第1—4题。', purpose='learning',
                                          change='new', state='ready')},
                created='2026-11-04 10:00:00')
    chinese = dict(id='p-chinese', child_id='c1', title='语文：《每日练习》第26页朗读',
                   body='朗读《每日练习》第26页短文两遍。', due='2026-11-06',
                   evidence=[dict(ref='message:s-qq:m4')],
                   plan={'school_task': dict(title='语文：《每日练习》第26页朗读',
                                             goal='朗读《每日练习》第26页短文两遍。', purpose='learning',
                                             change='new', state='ready')},
                   created='2026-11-04 09:00:00')
    store = FakeStore(SOURCES, MESSAGES, [math, chinese],
                      peer_payloads=[('s-wechat', MESSAGES[('s-wechat', 'm1')]),
                                     ('s-qq', MESSAGES[('s-qq', 'm3')])])
    with store._db() as c:
        targets = fa.school_pending_targets(store, 'c1', c)
    print(f'  pending targets (newest first): {[(t["id"], t["title"], t["publisher"][:16]) for t in targets]}')
    notice = brief('《每日练习》第26页第1—3题', '完成《每日练习》第26页第1—3题。')
    cited = [dict(ref='message:s-wechat:m5', publisher=targets[0]['publisher'],
                  time='2026-11-04T17:00:00+08:00', text=MESSAGES[('s-wechat', 'm5')]['text'])]
    proven = [fa._school_pending_link(t, 'same', notice, cited, '', '') for t in targets]
    print(f'  _school_pending_link per card -> {proven}')
    bound = next(((t, p) for t, p in zip(targets, proven) if p), None)
    print(f'  _select L8125-8133 picks the first proving card -> {bound[0]["id"] if bound else None}')
    subject_of_notice = '数学' if '数学' in MESSAGES[('s-wechat', 'm5')]['text'] else '语文'
    print(f'  the notice itself says {subject_of_notice}; the two cards are 数学/语文; no subject/ambiguity check here')
    case('P4 an ambiguous notice is refused (both cards prove -> no unique link)', sum(1 for p in proven if p) < 2,
         True, 'two independent affairs share 《每日练习》 and the program links to whichever card it listed first')


def fold_keeps_old_day_and_title():
    print('\n== P5 _school_fold_pending keeps the old day and title of a moved/narrowed notice ==')
    old = dict(id='p-old', child_id='c1', title='数学：《每日练习》第26页第1—4题',
               body='完成《每日练习》第26页第1—4题。', due='2026-11-06',
               evidence=[dict(ref='message:s-wechat:m1')],
               plan={'school_task': dict(title='数学：《每日练习》第26页第1—4题',
                                         goal='完成《每日练习》第26页第1—4题。', purpose='learning',
                                         change='new', state='ready')})
    store = FakeStore(SOURCES, MESSAGES, [old], peer_payloads=[])
    now = __import__('datetime').datetime(2026, 11, 4, 18, 0, 0)
    new_item = dict(child_id='c1', body='更正：只做《每日练习》第26页第1—3题，改到11月10日交。', due='2026-11-10',
                    evidence=[dict(ref='message:s-wechat:m5')])
    link = dict(item_id='p-old', change='update', publisher='publisher:x')
    with store._db() as c:
        ok = fa.Store._school_fold_pending(None, c, new_item, link, now)
        row = c.execute('SELECT * FROM agent_items WHERE id=?', ('p-old',)).fetchone()
    plan = json.loads(row['plan'])
    print(f'  folded={ok}; card title={row["title"]!r}; card due={row["due"]!r}; body={row["body"]!r}')
    print(f'  school_folded={plan.get("school_folded")}')
    print(f'  notice own due was 2026-11-10 and it says 改到11月10日交 -> card day still {row["due"]!r}')
    case('P5 the card day follows a notice that moves it', row['due'] == '2026-11-10', True,
         'UPDATE sets due=row["due"] or item due -> the existing day always wins')
    case('P5b the card title keeps a narrowed scope out of its headline',
         '第1—4题' not in row['title'], True, 'title is never updated by the fold')


def cancel_fold():
    print('\n== P6 fold of a cancellation notice: card state/due untouched ==')
    old = dict(id='p-cancel', child_id='c1', title='美术：带两片落叶', body='带两片落叶。', due='2026-11-06',
               evidence=[dict(ref='message:s-wechat:m1')],
               plan={'school_task': dict(title='美术：带两片落叶', goal='带两片落叶。', purpose='admin',
                                         change='new', state='ready')})
    store = FakeStore(SOURCES, MESSAGES, [old], peer_payloads=[])
    now = __import__('datetime').datetime(2026, 11, 4, 19, 0, 0)
    new_item = dict(child_id='c1', body='美术课取消，叶子不用带了。', due='', evidence=[dict(ref='message:s-wechat:m5')])
    with store._db() as c:
        fa.Store._school_fold_pending(None, c, new_item, dict(item_id='p-cancel', change='cancel'), now)
        row = c.execute('SELECT * FROM agent_items WHERE id=?', ('p-cancel',)).fetchone()
    print(f'  card state={row["state"]!r} due={row["due"]!r} body={row["body"]!r}')
    print('  family_agenda _one_pending_affair shows version.reasons 含取消或停止原要求 and keeps the card pending')


def split_allow_list():
    print('\n== P7 formed split residue whose wording has no whitelisted verb ==')
    cases = [
        ('数学：口算第12页第1—3题。\n语文：预习《成长手册》第3页。', '完成口算第12页第1—3题。', '口算第12页第1—3题'),
        ('数学：口算第12页第1—3题。体检表：家长签字后交回。', '完成口算第12页第1—3题。', '口算第12页第1—3题'),
    ]
    for text, goal, quote in cases:
        evidence = [dict(ref='message:s1:m1', text=text, time='2026-11-04T15:00:00+08:00', sender='林老师',
                         publisher='publisher:x', kind='text', unread=False, content_incomplete=False, attachments=[])]
        proposals = [dict(title_quote=quote, due='', task_title='数学：口算第12页', task_goal=goal,
                          task_state='ready', task_change='new', task_target_id='', task_purpose='admin',
                          task_submission='', evidence=[{'ref': 'message:s1:m1'}])]
        out, marks = fa._school_separate_outcomes(proposals, evidence, set(), source_later=[])
        print(f'  message={text!r}')
        print(f'  -> {len(out)} proposals, marks={list(marks)}')
        for i, prop in enumerate(out):
            blob = str(prop.get('task_title') or '') + '\n' + str(prop.get('task_goal') or '')
            keeps = bool(fa._SCHOOL_SPLIT_REQUIREMENT.search(blob))
            print(f'    [{i}] mark={list(marks.get(i, {}).keys())} title={prop.get("task_title")!r}'
                  f' goal={prop.get("task_goal")!r} -> new filter {"KEEPS" if keeps else "SKIPS"}')
        formed_only = [prop for i, prop in enumerate(out) if 'formed' in marks.get(i, {})]
        for prop in formed_only:
            blob = str(prop.get('task_title') or '') + '\n' + str(prop.get('task_goal') or '')
            case(f'P7 formed requirement {prop.get("task_title")!r} survives the split filter',
                 bool(fa._SCHOOL_SPLIT_REQUIREMENT.search(blob)), True,
                 'the formed proposal is the only carrier; _select L8264 continues past it')
    print('  code: _select L8263-8270 `if "formed" in mark and not _SCHOOL_SPLIT_REQUIREMENT.search(...): continue`;')
    print('  _school_separate_outcomes L912-917 builds the formed proposal from the original run text,')
    print('  and L982 already removed the split object lines from the home proposal goal.')


if __name__ == '__main__':
    print(f'family_agent.py recreated build-311 tree; target sha1 {DE6859A3}')
    import hashlib
    print('sha1 of /tmp/merge18_audit/family_agent.py:', hashlib.sha1(
        open('/tmp/merge18_audit/family_agent.py', 'rb').read()).hexdigest())
    probe1_same_due()
    probe2_publisher_collision()
    folded_item_and_third_notice()
    two_pending_cards()
    fold_keeps_old_day_and_title()
    cancel_fold()
    split_allow_list()

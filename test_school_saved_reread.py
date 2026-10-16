"""Controlled reread of a saved school review that the exact old source produced; synthetic replies, no real model.

The seed is made by old commit 632a778's own Store.ingest→run_once→save with the disclosed, explicitly synthetic TB02
reply (that source held the fill-in form as review: policy 10, revision 2, message processed 1, job done 1). The new
source must reread it only through its own natural run_once, inside the original three-call round and retry limits.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import family_agent as agent
import family_media
import family_review

OLD = '632a778237e90d912f3681b3dfdd10b48a669dae'
HERE = Path(__file__).resolve().parent
SOURCE = dict(id='p1-title-boundary-tb02', platform='wechat', child_id='child-1', name='虚构班级', cursor='10', enabled=True)
TEXT = '2026年10月22日前，在《听写背诵订正材料领取登记单》上填写学生姓名和领取份数，家长签字后交回班主任。只办理本次领取登记。'
REF = 'message:p1-title-boundary-tb02:1'
SYNTHETIC = dict(proposals=[dict(  # the disclosed SYNTHETIC-MODEL-REPLY.json; not a model measurement
    title_quote=TEXT, focus='school', due='2026-10-22', evidence=[dict(ref=REF)], learning_subject='', learning_goal_id='',
    task_title='填写《听写背诵订正材料领取登记单》并交回', task_goal=TEXT, task_advice='', task_state='ready',
    task_reason='本项行动和完成标准明确，按冻结虚构标准分类。', task_change='new', task_target_id='', task_purpose='admin',
    task_submission='')])
BRIEF = dict(title='填写《听写背诵订正材料领取登记单》并交回', goal=TEXT, advice='', state='ready',
             reason='synthetic：本项行动和完成标准明确。', change='new', target_id='', purpose='admin', submission='',
             learning_subject='', learning_goal_id='')
SEED = r'''
import datetime as dt, json, sys
from pathlib import Path
from unittest.mock import patch
root = Path(sys.argv[1]); data = root / 'private'; data.mkdir(parents=True)
(root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
source, text, reply = json.loads(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4])
(data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': [source]}))
import family_review, family_agent as agent, family_media
app = family_review.load_app(root, data)
store = agent.Store(app.connect, app.profiles, data, app=app)
now = dt.datetime(2026, 10, 16, 18, 5, tzinfo=agent.TZ)
store.ingest(dict(source_id=source['id'], expected_cursor='10', cursor='11', checked_at=now.isoformat(),
    last_message_time='2026-10-16T18:00:00+08:00', error='', messages=[dict(id='1', message_order='1',
    time='2026-10-16T18:00:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=text, unread=False)]))
with patch('family_qq_capture.run_one', return_value=dict(state='disabled')), \
     patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')), \
     patch.object(family_media, 'run_one', return_value=dict(state='ready')), \
     patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)), \
     patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())), \
     patch.object(agent.family_llm, '_chat_json', return_value=reply) as model:
    result = agent.run_once(app, now)
print(json.dumps(dict(calls=model.call_count, result=result, policy=agent.SCHOOL_TASK_POLICY, revision=agent.SCHOOL_SELECTION_REVISION)))
'''


def seed(root, source=SOURCE, text=TEXT, reply=SYNTHETIC, script=SEED):
    """Exact old source, real ingest/run_once/save; returns the old run's own report."""
    old = root / 'old-source'
    old.mkdir()
    archive = subprocess.run(['git', '-C', str(HERE), 'archive', OLD], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(old)], input=archive, check=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    out = subprocess.run([sys.executable, '-I', '-c', 'import sys;p,s=sys.argv[1:3];del sys.argv[1:3];sys.path.insert(0,p);exec(s)',
                          str(old), script, str(root / 'family'), json.dumps(source), text, json.dumps(reply)],
                         check=True, capture_output=True, text=True, cwd=old, env=env).stdout
    return json.loads(out.strip().splitlines()[-1])


def assert_reread_in_place(case, old, new):
    """Root counter 3: an untouched generated review the batch audit reads again keeps its ID, batch, child and original
    generated snapshot; its new understanding is written once under the same row (never a copy), traceable to the old row."""
    case.assertEqual({k: new[k] for k in ('id', 'job_id', 'child_id', 'kind', 'created')}, {k: old[k] for k in ('id', 'job_id', 'child_id', 'kind', 'created')})
    plan, before = json.loads(new['plan']), json.loads(old['plan'])
    case.assertEqual(plan['school_generated_snapshot'], before['school_generated_snapshot'], 'the original proof stays')
    case.assertEqual(plan['school_batch_reread']['previous'], agent._hash(old), 'traceable to the exact old row')
    case.assertTrue(plan['school_history_job'].startswith('school-history:'))


class SavedSchoolRereadTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-saved-reread-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.old = seed(self.root)
        self.data = self.root / 'family' / 'private'
        self.app = family_review.load_app(self.root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)  # the reread day is not the sending day

    def rows(self):
        with self.app.connect() as c:
            return dict(items=[dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")],
                        jobs={r['id']: dict(r) for r in c.execute('SELECT * FROM agent_jobs')},
                        messages=[dict(r) for r in c.execute('SELECT id,processed,payload FROM agent_messages')],
                        tasks=[dict(r) for r in c.execute('SELECT id,title,due,original_status,action FROM manual_tasks')],
                        cursor=c.execute('SELECT cursor FROM agent_sources').fetchone()[0])

    def run_round(self, reply, at):
        with patch.object(agent.family_llm, '_chat_json', **reply) as model:
            result = agent.run_once(self.app, at)
        return model.call_count, result

    def test_old_seed_is_the_natural_old_review(self):
        self.assertEqual((self.old['calls'], self.old['policy'], self.old['revision']), (1, 10, 2))
        state = self.rows()
        item, = state['items']
        plan = json.loads(item['plan'])
        self.assertEqual((item['state'], plan['school_task']['state'], plan['school_task']['policy']), ('pending', 'review', 10))
        self.assertEqual(plan['school_selection_revision'], 2)
        self.assertEqual(plan['school_generated_snapshot'], agent._school_generated_snapshot(item), 'old output is untouched')
        self.assertEqual(state['tasks'], [])
        self.assertEqual([m['processed'] for m in state['messages']], [1])
        job = state['jobs'][item['job_id']]
        self.assertEqual((job['done'], job['error']), (1, ''))

    def test_untouched_old_review_is_reread_once_into_the_same_item(self):
        before = self.rows()
        old_item, = before['items']
        old_job = before['jobs'][old_item['job_id']]
        calls, _ = self.run_round(dict(return_value=BRIEF), self.now)
        self.assertEqual(calls, 1, 'one call of the original three-call round')
        after = self.rows()
        item, = after['items']
        self.assertEqual(item['id'], old_item['id'])
        self.assertEqual(item['state'], 'accepted')
        self.assertEqual(item['due'], '2026-10-22', 'the original written date, not the reread day')
        plan = json.loads(item['plan'])
        self.assertEqual(plan['school_task']['purpose'], 'admin')
        self.assertNotIn('school_learning', plan)
        self.assertEqual(plan['school_saved_reread']['snapshot'], json.loads(old_item['plan'])['school_generated_snapshot'])
        self.assertEqual(plan['school_generated_snapshot'], json.loads(old_item['plan'])['school_generated_snapshot'])
        task, = after['tasks']
        self.assertEqual((task['id'], task['due']), (item['task_id'], '2026-10-22'))
        self.assertEqual(after['jobs'][old_item['job_id']], old_job, 'the original done receipt is immutable')
        self.assertEqual((after['messages'], after['cursor']), (before['messages'], before['cursor']))
        # Reopen with a new Store and run more natural rounds: no further call, no copy.
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        for minutes in (1, 7, 30):
            calls, _ = self.run_round(dict(side_effect=AssertionError('no second reread')), self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(calls, 0)
        again = self.rows()
        self.assertEqual((again['items'], again['tasks']), (after['items'], after['tasks']))

    def test_parent_decisions_are_never_reread(self):
        # Root route (ROOT-route-decision.json): a parent-decided batch may still be audited once, but the decided row is
        # never rewritten, resurrected or copied. The old "0 calls" expectation predates that route.
        item, = self.rows()['items']
        self.store.act(dict(id=item['id'], action='dismiss'))
        before = self.rows()
        claimed_new = dict(proposals=[dict(SYNTHETIC['proposals'][0], action_quote=TEXT.split('。')[0] + '。', existing_item_id='')])  # SYNTHETIC, one action clause
        calls = [self.run_round(dict(return_value=claimed_new), self.now + dt.timedelta(minutes=41 * i))[0] for i in range(3)]
        self.assertLessEqual(sum(calls), 1, 'at most the one bounded audit call')
        after = self.rows()
        self.assertEqual(after['items'], before['items'], 'the dismissed item stays dismissed and unchanged; no copy')
        self.assertEqual(after['tasks'], [])
        self.assertEqual((after['messages'], after['cursor']), (before['messages'], before['cursor']))
        self.assertEqual(after['jobs'][item['job_id']], before['jobs'][item['job_id']])

    def test_changed_generated_snapshot_fails_closed(self):
        item, = self.rows()['items']
        with self.app.connect() as c:  # a parent-side edit of the saved draft; created/updated are left equal on purpose
            c.execute('UPDATE agent_items SET title=? WHERE id=?', ('家长改过的标题', item['id']))
        before = self.rows()
        # The edited row is never rewritten, but its batch may still be audited once (Root's route): SYNTHETIC
        # history-mode reply mapping the one action onto the edited row.
        reply = dict(proposals=[dict(SYNTHETIC['proposals'][0], action_quote=TEXT.split('。')[0] + '。', existing_item_id=item['id'])])
        calls, _ = self.run_round(dict(return_value=reply), self.now)
        self.assertLessEqual(calls, 1)
        after = self.rows()
        boundary = after['jobs'].pop('school-audit-boundary')  # bookkeeping rows only: boundary, scope mark, audit receipt
        self.assertEqual(boundary['done'], 1)
        added = {k for k in after['jobs'] if k not in before['jobs']}
        self.assertTrue(all(k.startswith(('school-audit-scope:', 'school-history:')) for k in added), added)
        for k in added: after['jobs'].pop(k)
        self.assertEqual(after, before, 'the edited draft, its receipt, messages and cursor are unchanged')

    def test_failures_keep_one_identity_backoff_and_the_three_attempt_limit(self):
        before = self.rows()
        old_item, = before['items']
        at, calls = self.now, []
        for _ in range(6):
            count, _ = self.run_round(dict(side_effect=agent.family_llm.LLMDraftError('synthetic failure')), at)
            calls.append(count)
            at += dt.timedelta(minutes=41)
        self.assertEqual(sum(calls), 3, calls)
        state = self.rows()
        job = state['jobs']['school-task:' + old_item['id']]
        self.assertEqual((job['attempts'], job['done'], job['next_try']), (3, 0, ''))
        self.assertIn('自动尝试共3次', job['error'])
        self.assertEqual(state['items'], before['items'], 'the old review stays exactly as saved')
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        # The existing explicit retry reuses the same identity and the same request.
        self.store.act(dict(action='retry', id='school-task:' + old_item['id']))
        count, _ = self.run_round(dict(return_value=BRIEF), at)
        self.assertEqual(count, 1)
        item, = self.rows()['items']
        self.assertEqual((item['id'], item['state']), (old_item['id'], 'accepted'))
        self.assertEqual(len(self.rows()['tasks']), 1)

    def test_parent_change_while_the_model_runs_rejects_the_late_result(self):
        item, = self.rows()['items']
        def late(*args, **kwargs):
            self.store.act(dict(id=item['id'], action='dismiss'))
            return BRIEF
        calls, _ = self.run_round(dict(side_effect=late), self.now)
        self.assertEqual(calls, 1)
        state = self.rows()
        saved, = state['items']
        self.assertEqual((saved['state'], saved['title'], saved['plan']), ('dismissed', item['title'], item['plan']))
        self.assertEqual(state['tasks'], [])

    # Root's disclosed TB02 counterexamples against 5bf5274 (known-counterexamples.json); synthetic replies only.
    def assert_original_kept(self, old_item):
        state = self.rows()
        item, = state['items']
        self.assertEqual(item['id'], old_item['id'])
        self.assertEqual(item['due'], '2026-10-22')
        for text in [item['body']] + [t['action'] for t in state['tasks']]:
            self.assertNotIn('10月23日', text, 'a reread may not change the original date')
        if item['state'] == 'accepted' or state['tasks']:
            # Saved work keeps the complete original requirements (name, count, signature, hand-back, scope).
            self.assertIn(TEXT, item['body'])
            for task in state['tasks']:
                self.assertIn(TEXT, task['action'])
        else:
            self.assertEqual(state['tasks'], [])
        return state

    def test_reread_cannot_save_a_changed_date(self):
        before = self.rows()
        old_item, = before['items']
        calls, _ = self.run_round(dict(return_value=dict(BRIEF, goal=TEXT.replace('10月22日', '10月23日'))), self.now)
        self.assertEqual(calls, 1)
        state = self.assert_original_kept(old_item)
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        if state['items'][0]['state'] != 'accepted':
            job = state['jobs']['school-task:' + old_item['id']]
            self.assertEqual((job['attempts'], job['done']), (1, 0), 'rejected under the same bounded identity')

    def test_reread_cannot_drop_original_requirements(self):
        old_item, = self.rows()['items']
        calls, _ = self.run_round(dict(return_value=dict(BRIEF, goal='2026年10月22日前，填写材料领取登记单并交回班主任。')), self.now)
        self.assertEqual(calls, 1)
        self.assert_original_kept(old_item)

    def test_renamed_source_does_not_restore_an_exhausted_budget(self):
        old_item, = self.rows()['items']
        key = 'school-task:' + old_item['id']
        at, calls = self.now, []
        for _ in range(4):
            count, _ = self.run_round(dict(side_effect=agent.family_llm.LLMDraftError('synthetic failure')), at)
            calls.append(count)
            at += dt.timedelta(minutes=41)
        self.assertEqual(sum(calls), 3, calls)
        exhausted = self.rows()['jobs'][key]
        self.assertEqual(exhausted['attempts'], 3)
        config = json.loads((self.data / 'agent.json').read_text())  # isolated fictional config file only
        config['sources'][0]['name'] = '虚构班级改名'
        (self.data / 'agent.json').write_text(json.dumps(config))
        for _ in range(3):
            count, _ = self.run_round(dict(side_effect=AssertionError('a display rename must not wash the limit')), at)
            self.assertEqual(count, 0)
            at += dt.timedelta(minutes=41)
        job = self.rows()['jobs'][key]
        self.assertEqual((job['attempts'], job['done'], job['next_try']), (3, 0, ''))
        self.store.act(dict(action='retry', id=key))
        count, _ = self.run_round(dict(return_value=BRIEF), at)
        self.assertEqual(count, 1, 'explicit retry keeps the same identity')
        item, = self.rows()['items']
        self.assertEqual((item['id'], item['state']), (old_item['id'], 'accepted'))
        self.assertEqual(len(self.rows()['tasks']), 1)

    def test_source_revoked_while_the_model_runs_rejects_the_late_result(self):  # SR04
        item, = self.rows()['items']
        def late(*args, **kwargs):
            config = json.loads((self.data / 'agent.json').read_text())  # isolated fictional config file only
            config['sources'][0]['enabled'] = False
            (self.data / 'agent.json').write_text(json.dumps(config))
            return BRIEF
        calls, _ = self.run_round(dict(side_effect=late), self.now)
        self.assertEqual(calls, 1)
        state = self.rows()
        saved, = state['items']
        self.assertEqual((saved['state'], saved['title'], saved['body'], saved['plan']), (item['state'], item['title'], item['body'], item['plan']))
        self.assertEqual(state['tasks'], [])

    def test_a_later_normal_message_still_moves_in_the_reread_round(self):  # SR05
        later = '2026年10月24日前，请在《图书借阅登记表》上填写学生姓名，家长签字后交回班主任。'
        later_ref = 'message:p1-title-boundary-tb02:2'
        self.store.ingest(dict(source_id=SOURCE['id'], expected_cursor='11', cursor='12', checked_at=self.now.isoformat(),
            last_message_time='2026-10-17T02:00:00+08:00', error='', messages=[dict(id='2', message_order='2',
            time='2026-10-17T02:00:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=later, unread=False)]))
        names = []
        def reply(messages, schema, name, **kwargs):  # SYNTHETIC replies for both jobs
            names.append(name)
            if name == 'family_school_task':
                return BRIEF
            return dict(proposals=[dict(SYNTHETIC['proposals'][0], title_quote=later, due='2026-10-24', evidence=[dict(ref=later_ref)],
                                        task_title='填写《图书借阅登记表》并交回', task_goal=later)])
        calls, _ = self.run_round(dict(side_effect=reply), self.now)
        self.assertLessEqual(calls, 3, 'the original three-call round')
        self.assertEqual(names[0], 'family_agent_selection', 'ordinary new work goes first')
        state = self.rows()
        self.assertEqual(sorted(m['processed'] for m in state['messages']), [1, 1])
        self.assertEqual(state['cursor'], '12', 'the cursor only moves by intake')
        self.assertTrue(any(later in i['body'] for i in state['items']))
        self.assertIn('family_school_task', names, 'the saved reread shares the same round after ordinary work')


class TwoFormsInOneMessageTests(unittest.TestCase):
    """Root's static risk: the saved reread compiles all original text into one goal; two dated forms must not merge."""
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round
    SECOND = '2026年10月22日前，请家长在《秋游安全告知书》上签字，由学生交回班主任。'

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-two-forms-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.old = seed(self.root, dict(SOURCE, id='p1-two-forms'), TEXT + self.SECOND,
                        dict(proposals=[dict(SYNTHETIC['proposals'][0], evidence=[dict(ref='message:p1-two-forms:1')])]))
        self.data = self.root / 'family' / 'private'
        self.app = family_review.load_app(self.root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for target in ('family_qq_capture.run_one',):
            self.stack.enter_context(patch(target, return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)

    def test_reread_does_not_merge_two_dated_forms_into_one_task(self):
        before = self.rows()
        for i in range(3):
            self.run_round(dict(return_value=BRIEF), self.now + dt.timedelta(minutes=41 * i))
        state = self.rows()
        for text in [t['action'] for t in state['tasks']] + [i['body'] for i in state['items'] if i['state'] == 'accepted']:
            self.assertFalse('听写背诵订正材料领取登记单' in text and '秋游安全告知书' in text, 'two dated forms merged into one task: ' + text)
        self.assertEqual(state['jobs'][before['items'][0]['job_id']], before['jobs'][before['items'][0]['job_id']])

    def test_two_form_pending_batch_is_audited_into_two_separate_outcomes(self):
        # Root's actual counter: the old source saved one pending review for the first form only; refusing the merge
        # must not leave the second form unread forever. SYNTHETIC history-mode reply: first covered, second independent.
        before = self.rows()
        old_item, = before['items']
        ref = [dict(ref='message:p1-two-forms:1')]
        first = dict(SYNTHETIC['proposals'][0], evidence=ref, action_quote=TEXT.split('。')[0] + '。', existing_item_id=old_item['id'])
        second = dict(first, title_quote=self.SECOND, task_title='家长签《秋游安全告知书》并交回', task_goal=self.SECOND,
                      action_quote=self.SECOND, existing_item_id='')
        calls = [self.run_round(dict(return_value=dict(proposals=[first, second])), self.now + dt.timedelta(minutes=41 * i))[0]
                 for i in range(3)]
        self.assertEqual(sum(calls), 1, 'one bounded audit call for the old batch')
        state = self.rows()
        assert_reread_in_place(self, old_item, next(i for i in state['items'] if i['id'] == old_item['id']))  # was byte-identical (v4)
        found = [i for i in state['items'] if i['id'] != old_item['id'] and '秋游安全告知书' in i['body']]
        self.assertEqual(len(found), 1, 'the second form is its own traceable outcome')
        self.assertNotIn('听写背诵订正材料领取登记单', found[0]['body'])
        self.assertIn('message:p1-two-forms:1', found[0]['evidence'])
        self.assertEqual(found[0]['due'], '2026-10-22')
        for text in [t['action'] for t in state['tasks']] + [i['body'] for i in state['items']]:
            self.assertFalse('听写背诵订正材料领取登记单' in text and '秋游安全告知书' in text, 'merged: ' + text)
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        self.assertEqual((state['messages'], state['cursor']), (before['messages'], before['cursor']))
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        for minutes in (200, 241, 400):
            count, _ = self.run_round(dict(side_effect=AssertionError('the audit is once per old batch')), self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(count, 0)
        self.assertEqual(self.rows()['items'], state['items'])

    def audit_reply(self, old_id):  # SYNTHETIC history-mode reply: first form covered by the old review, second independent
        ref = [dict(ref='message:p1-two-forms:1')]
        first = dict(SYNTHETIC['proposals'][0], evidence=ref, action_quote=TEXT.split('。')[0] + '。', existing_item_id=old_id)
        return dict(proposals=[first, dict(first, title_quote=self.SECOND, task_title='家长签《秋游安全告知书》并交回',
                                           task_goal=self.SECOND, action_quote=self.SECOND, existing_item_id='')])

    def late_change(self, change):
        before = self.rows()
        old_item, = before['items']
        def late(*args, **kwargs):
            change()
            return self.audit_reply(old_item['id'])
        calls, _ = self.run_round(dict(side_effect=late), self.now)
        self.assertEqual(calls, 1)
        state = self.rows()
        self.assertEqual(state['items'], before['items'], 'late audit result rejected: old review kept, nothing added')
        self.assertEqual(state['tasks'], before['tasks'])
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])

    def test_child_reassigned_during_the_audit_rejects_the_late_result(self):  # SR04
        rules = self.root / 'family' / '家庭运行规则.md'
        rules.write_text(rules.read_text() + '| child-2 | 示例乙 | 女 | 9岁 | 三年级 |\n')
        def move():
            config = json.loads((self.data / 'agent.json').read_text())  # isolated fictional config file only
            config['sources'][0]['child_id'] = 'child-2'
            (self.data / 'agent.json').write_text(json.dumps(config))
        self.late_change(move)

    def test_original_changed_during_the_audit_rejects_the_late_result(self):  # SR04
        def edit():
            with self.app.connect() as c:  # race simulation only: the stored original changes while the model runs
                payload = json.loads(c.execute('SELECT payload FROM agent_messages').fetchone()[0])
                payload['text'] = payload['text'].replace('10月22日', '10月23日', 1)
                c.execute('UPDATE agent_messages SET payload=?', (json.dumps(payload, ensure_ascii=False),))
        self.late_change(edit)

    def test_exhausted_audit_is_retried_explicitly_under_the_same_identity(self):  # SR04
        old_item, = self.rows()['items']
        at, calls = self.now, []
        for _ in range(6):
            calls.append(self.run_round(dict(side_effect=agent.family_llm.LLMDraftError('synthetic failure')), at)[0])
            at += dt.timedelta(minutes=41)
        self.assertEqual(sum(calls), 3, calls)
        keys = [k for k in self.rows()['jobs'] if k.startswith('school-history:')]
        self.assertEqual(len(keys), 1)
        self.assertEqual((self.rows()['jobs'][keys[0]]['attempts'], self.rows()['jobs'][keys[0]]['done']), (3, 0))
        self.store.act(dict(action='retry', id=keys[0]))  # the existing explicit retry, same job ID
        count, _ = self.run_round(dict(return_value=self.audit_reply(old_item['id'])), self.now + dt.timedelta(minutes=300))
        self.assertEqual(count, 1)
        state = self.rows()
        self.assertEqual([k for k in state['jobs'] if k.startswith('school-history:')], keys, 'no new identity after retry')
        self.assertEqual(state['jobs'][keys[0]]['done'], 1)
        self.assertEqual(len([i for i in state['items'] if '秋游安全告知书' in i['body']]), 1)
        assert_reread_in_place(self, old_item, next(i for i in state['items'] if i['id'] == old_item['id']))  # was byte-identical (v4)


class OneDeadlineTwoActionsTests(unittest.TestCase):
    """One deadline, two actions: the old single-action review never covered the second clause, so the saved reread
    must not compile it into the same task; the batch audit keeps the two outcomes apart."""
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round
    SECOND = '另请家长在《秋游安全告知书》上签字，一并交回班主任。'

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-one-date-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.old = seed(self.root, dict(SOURCE, id='p1-one-date'), TEXT + self.SECOND,
                        dict(proposals=[dict(SYNTHETIC['proposals'][0], evidence=[dict(ref='message:p1-one-date:1')])]))
        self.data = self.root / 'family' / 'private'
        self.app = family_review.load_app(self.root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)

    def test_one_deadline_two_actions_are_not_merged_by_the_saved_reread(self):
        before = self.rows()
        old_item, = before['items']
        self.assertEqual((old_item['state'], old_item['task_id']), ('pending', ''))
        ref = [dict(ref='message:p1-one-date:1')]
        first = dict(SYNTHETIC['proposals'][0], evidence=ref, action_quote=TEXT.split('。')[0] + '。', existing_item_id=old_item['id'])
        audit = dict(proposals=[first, dict(first, title_quote=self.SECOND, task_title='家长签《秋游安全告知书》并交回',
                                            task_goal=self.SECOND, action_quote=self.SECOND, existing_item_id='')])
        def model(messages, *args, **kwargs):  # SYNTHETIC: the saved reread gets BRIEF, the batch audit the two outcomes
            return audit if 'existing_actions' in json.loads(messages[1]['content']) else BRIEF
        for i in range(3):
            self.run_round(dict(side_effect=model), self.now + dt.timedelta(minutes=41 * i))
        state = self.rows()
        for text in [t['action'] for t in state['tasks']] + [i['body'] for i in state['items']]:
            self.assertFalse('听写背诵订正材料领取登记单' in text and '秋游安全告知书' in text, 'merged: ' + text)
        self.assertEqual(len([i for i in state['items'] if '秋游安全告知书' in i['body']]), 1)
        assert_reread_in_place(self, old_item, next(i for i in state['items'] if i['id'] == old_item['id']))  # was byte-identical (v4)
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])


# SR02: the exact old source auto-accepted the first of two independent actions in one notice and never saw the second.
# Seed probes the old source rejected or held for review (not old-accepted, so not SR02 seeds): two messages with one
# proposal (old integrity guard: 学校消息归纳有遗漏, batch left unprocessed); the TB02 sentence plus a second action, or
# TB02 with a shortened goal (both saved as pending review).
SR02_SOURCE = dict(SOURCE, id='p1-sr02-fictional')
SR02_FIRST = '2026年10月22日前，在《材料领取登记单》上填写学生姓名和领取份数，家长签字后交回班主任。'
SR02_SECOND = '2026年10月22日前，请家长在《秋游安全告知书》上签字，由学生交回班主任。'
SR02_REF = 'message:p1-sr02-fictional:1'
SR02_OLD_REPLY = dict(proposals=[dict(  # SYNTHETIC: covers only the first action
    title_quote=SR02_FIRST, focus='school', due='2026-10-22', evidence=[dict(ref=SR02_REF)], learning_subject='',
    learning_goal_id='', task_title='填写《材料领取登记单》并交回', task_goal=SR02_FIRST, task_advice='', task_state='ready',
    task_reason='synthetic：本项行动和完成标准明确。', task_change='new', task_target_id='', task_purpose='admin', task_submission='')])
SR02_FULL_REPLY = dict(proposals=[SR02_OLD_REPLY['proposals'][0], dict(  # SYNTHETIC: both actions
    SR02_OLD_REPLY['proposals'][0], title_quote=SR02_SECOND, task_title='家长签《秋游安全告知书》并交回', task_goal=SR02_SECOND)])


class AutoAcceptedOldBatchTests(unittest.TestCase):
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-sr02-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.old = seed(self.root, SR02_SOURCE, SR02_FIRST + SR02_SECOND, SR02_OLD_REPLY)
        self.data = self.root / 'family' / 'private'
        self.app = family_review.load_app(self.root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)

    def test_old_seed_is_a_natural_auto_accepted_batch_missing_an_action(self):
        self.assertEqual((self.old['calls'], self.old['policy'], self.old['revision']), (1, 10, 2))
        state = self.rows()
        item, = state['items']
        plan = json.loads(item['plan'])
        self.assertEqual((item['state'], plan['school_task']['state'], plan['school_task'].get('auto_added')), ('accepted', 'ready', True))
        task, = state['tasks']
        self.assertEqual((task['id'], task['action'], task['due']), (item['task_id'], SR02_FIRST, '2026-10-22'))
        saved_work = [item['title'], item['body'], task['title'], task['action']]  # the original payload keeps it, of course
        self.assertFalse([text for text in saved_work if '秋游安全告知书' in text], 'the second action was never saved as work')
        self.assertEqual([m['processed'] for m in state['messages']], [1])
        self.assertEqual(state['jobs'][item['job_id']]['done'], 1)

    def audit_reply(self, old_id):  # SYNTHETIC history-mode reply (existing_actions given): first covered, second independent
        first, second = SR02_FULL_REPLY['proposals']
        return dict(proposals=[dict(first, action_quote=SR02_FIRST, existing_item_id=old_id),
                               dict(second, action_quote=SR02_SECOND, existing_item_id='')])

    def test_reread_finds_the_missing_action_without_copying_the_accepted_one(self):
        before = self.rows()
        old_item, = before['items']
        calls = [self.run_round(dict(return_value=self.audit_reply(old_item['id'])), self.now + dt.timedelta(minutes=41 * i))[0] for i in range(3)]
        self.assertEqual(sum(calls), 1, 'one bounded audit call for the old batch')
        self.assertLessEqual(max(calls), 3)
        state = self.rows()
        kept = next(i for i in state['items'] if i['id'] == old_item['id'])
        self.assertEqual(kept, old_item, 'the accepted item is not overwritten')
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        self.assertEqual((state['messages'], state['cursor']), (before['messages'], before['cursor']))
        found = [i for i in state['items'] if i['id'] != old_item['id'] and SR02_SECOND in i['body']]
        self.assertEqual(len(found), 1, 'one traceable item for the missing action')
        self.assertIn(SR02_REF, found[0]['evidence'])
        self.assertEqual(found[0]['due'], '2026-10-22')
        self.assertEqual([t['action'] for t in state['tasks'] if SR02_FIRST in t['action']], [SR02_FIRST], 'no copy')
        self.assertNotIn(SR02_FIRST, found[0]['body'], 'the missing action is not merged with the covered one')
        # Restart: a new Store and later rounds neither audit again nor copy.
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        for minutes in (200, 241, 400):
            count, _ = self.run_round(dict(side_effect=AssertionError('the audit is once per old batch')), self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(count, 0)
        self.assertEqual(self.rows()['items'], state['items'])

    def test_batches_saved_after_the_boundary_are_not_audited(self):
        # The first permitted round fixes the boundary before its intake; a batch first saved in or after it is not audited.
        old_item, = self.rows()['items']
        later = '2026年10月24日前，请在《图书借阅登记表》上填写学生姓名，家长签字后交回班主任。'
        self.store.ingest(dict(source_id=SR02_SOURCE['id'], expected_cursor='11', cursor='12', checked_at=self.now.isoformat(),
            last_message_time='2026-10-17T02:00:00+08:00', error='', messages=[dict(id='2', message_order='2',
            time='2026-10-17T02:00:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=later, unread=False)]))
        names = []
        def reply(messages, schema, name, **kwargs):  # SYNTHETIC
            names.append((name, 'existing_actions' in json.dumps(messages, ensure_ascii=False)))
            if 'existing_actions' in json.dumps(messages, ensure_ascii=False):
                return self.audit_reply(old_item['id'])
            return dict(proposals=[dict(SR02_OLD_REPLY['proposals'][0], title_quote=later, due='2026-10-24',
                evidence=[dict(ref='message:p1-sr02-fictional:2')], task_title='填写《图书借阅登记表》并交回', task_goal=later)])
        for i in range(4):
            self.run_round(dict(side_effect=reply), self.now + dt.timedelta(minutes=41 * i))
        audits = [n for n in names if n[1]]
        self.assertEqual(len(audits), 1, names)
        self.assertLessEqual(len(names), 3 * 4)

    def test_failed_audit_keeps_one_identity_and_the_three_attempt_limit(self):  # SR04
        before = self.rows()
        at, calls = self.now, []
        for _ in range(6):
            count, _ = self.run_round(dict(side_effect=agent.family_llm.LLMDraftError('synthetic failure')), at)
            calls.append(count)
            at += dt.timedelta(minutes=41)
        self.assertEqual(sum(calls), 3, calls)
        state = self.rows()
        audit = [j for k, j in state['jobs'].items() if k.startswith('school-history:')]
        self.assertEqual([(j['attempts'], j['done']) for j in audit], [(3, 0)])
        self.assertEqual(state['items'], before['items'])
        self.assertEqual(state['tasks'], before['tasks'])

    def test_exhausted_audit_yields_to_a_later_normal_message(self):  # SR05
        old_item, = self.rows()['items']
        at = self.now
        for _ in range(3):
            self.run_round(dict(side_effect=agent.family_llm.LLMDraftError('synthetic failure')), at)
            at += dt.timedelta(minutes=41)
        later = '2026年10月24日前，请在《图书借阅登记表》上填写学生姓名，家长签字后交回班主任。'
        self.store.ingest(dict(source_id=SR02_SOURCE['id'], expected_cursor='11', cursor='12', checked_at=at.isoformat(),
            last_message_time='2026-10-17T05:00:00+08:00', error='', messages=[dict(id='2', message_order='2',
            time='2026-10-17T05:00:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=later, unread=False)]))
        names = []
        def reply(messages, schema, name, **kwargs):  # SYNTHETIC
            names.append('existing_actions' in json.dumps(messages, ensure_ascii=False))
            return dict(proposals=[dict(SR02_OLD_REPLY['proposals'][0], title_quote=later, due='2026-10-24',
                evidence=[dict(ref='message:p1-sr02-fictional:2')], task_title='填写《图书借阅登记表》并交回', task_goal=later)])
        calls, _ = self.run_round(dict(side_effect=reply), at)
        self.assertEqual((calls, names), (1, [False]), 'only the ordinary new batch is called; the exhausted audit yields')
        state = self.rows()
        self.assertEqual(sorted(m['processed'] for m in state['messages']), [1, 1])
        self.assertTrue(any(later in i['body'] for i in state['items']))
        self.assertEqual(next(i for i in state['items'] if i['id'] == old_item['id']), old_item)

    def test_parent_completion_during_the_audit_rejects_the_late_result(self):  # SR03/SR04
        old_item, = self.rows()['items']
        def late(*args, **kwargs):
            with self.app.connect() as c:  # the parent edits the accepted task while the model runs
                c.execute('UPDATE manual_tasks SET title=? WHERE id=?', ('家长改过的任务', old_item['task_id']))
            return self.audit_reply(old_item['id'])
        calls, _ = self.run_round(dict(side_effect=late), self.now)
        self.assertEqual(calls, 1)
        state = self.rows()
        self.assertEqual([i['id'] for i in state['items']], [old_item['id']], 'stale result rejected; nothing added')
        self.assertEqual([t['title'] for t in state['tasks']], ['家长改过的任务'])


SEED_MANY = SEED.replace("source, text, reply = json.loads(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4])\n", "steps = json.loads(sys.argv[2])\n") \
    .replace("[source]}", "[s['source'] for s in steps]}").replace("now = dt.datetime(2026, 10, 16, 18, 5, tzinfo=agent.TZ)\n", "calls = 0\nfor n, step in enumerate(steps):\n  source, text, reply = step['source'], step['text'], step['reply']\n  now = dt.datetime(2026, 10, 16, 18, 5 + 10 * n, tzinfo=agent.TZ)\n") \
    .replace("\nstore.ingest(", "\n  store.ingest(").replace("\nwith patch(", "\n  with patch(").replace("\n    result = agent.run_once(app, now)\n", "\n    result = agent.run_once(app, now)\n  calls += model.call_count\n") \
    .replace("calls=model.call_count", "calls=calls")


class MixedStoreTests(unittest.TestCase):  # SR05: eligible + exhausted + parent-decided old batches + a later normal message
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round
    A, B, C = dict(SOURCE, id='p1-mix-a'), dict(SOURCE, id='p1-mix-b'), dict(SOURCE, id='p1-mix-c')
    LATER = '2026年10月24日前，请在《图书借阅登记表》上填写学生姓名，家长签字后交回班主任。'

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-mixed-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        one = lambda s, p: dict(proposals=[dict(p, evidence=[dict(ref='message:' + s['id'] + ':1')])])
        steps = [dict(source=self.A, text=TEXT + TwoFormsInOneMessageTests.SECOND, reply=one(self.A, SYNTHETIC['proposals'][0])),
                 dict(source=self.B, text=SR02_FIRST + SR02_SECOND, reply=one(self.B, SR02_OLD_REPLY['proposals'][0])),
                 dict(source=self.C, text=TEXT, reply=one(self.C, SYNTHETIC['proposals'][0]))]
        old = root_old = self.root / 'old-source'
        root_old.mkdir()
        archive = subprocess.run(['git', '-C', str(HERE), 'archive', OLD], check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', str(old)], input=archive, check=True)
        subprocess.run([sys.executable, '-I', '-c', 'import sys;p,s=sys.argv[1:3];del sys.argv[1:3];sys.path.insert(0,p);exec(s)',
                        str(old), SEED_MANY, str(self.root / 'family'), json.dumps(steps)],
                       check=True, capture_output=True, text=True, cwd=old, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.data = self.root / 'family' / 'private'
        self.app = family_review.load_app(self.root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)

    def test_mixed_old_batches_and_a_later_message_are_all_served_fairly(self):
        before = self.rows()
        by = {s['id']: [i for i in before['items'] if 'message:' + s['id'] + ':1' in i['evidence']] for s in (self.A, self.B, self.C)}
        self.assertEqual([(len(by[s['id']]), by[s['id']][0]['state']) for s in (self.A, self.B, self.C)],
                         [(1, 'pending'), (1, 'accepted'), (1, 'pending')], 'natural old store: two-form review, auto-accepted, TB02 review')
        self.store.act(dict(action='dismiss', id=by[self.C['id']][0]['id']))  # the parent decides before the new code runs
        decided = self.rows()
        a_old, c_old = by[self.A['id']][0], next(i for i in decided['items'] if i['id'] == by[self.C['id']][0]['id'])
        audit_a = TwoFormsInOneMessageTests.audit_reply(TwoFormsInOneMessageTests, a_old['id'])
        audit_a = dict(proposals=[dict(p, evidence=[dict(ref='message:p1-mix-a:1')]) for p in audit_a['proposals']])
        # The dismissed whole-notice row has no located action, so mapping onto it is refused by the existing guard
        # (observed: 3 failed attempts); this reply claims the action as new, which the audit must not re-offer.
        audit_c = dict(proposals=[dict(SYNTHETIC['proposals'][0], evidence=[dict(ref='message:p1-mix-c:1')],
                                       action_quote=TEXT.split('。')[0] + '。', existing_item_id='')])
        later = dict(proposals=[dict(SYNTHETIC['proposals'][0], title_quote=self.LATER, task_title='填写《图书借阅登记表》并交回',
                                     task_goal=self.LATER, due='2026-10-24', evidence=[dict(ref='message:p1-mix-a:2')])])
        seen = []
        def model(messages, *args, **kwargs):  # SYNTHETIC replies chosen by the batch actually sent; B always fails
            refs = {e['ref'] for e in json.loads(messages[1]['content'])['evidence']}
            seen.append(sorted(refs))
            if refs == {'message:p1-mix-a:2'}: return later
            if refs == {'message:p1-mix-b:1'}: raise agent.family_llm.LLMDraftError('synthetic failure')
            if refs == {'message:p1-mix-a:1'}: return audit_a
            if refs == {'message:p1-mix-c:1'}: return audit_c
            raise AssertionError(refs)
        at, calls = self.now, []
        for n in range(10):  # 40-minute steps keep every round in the shared five-minute history window
            if n == 1:  # a later ordinary message arrives after the boundary was fixed
                self.store.ingest(dict(source_id=self.A['id'], expected_cursor='11', cursor='12', checked_at=at.isoformat(),
                    last_message_time='2026-10-17T03:30:00+08:00', error='', messages=[dict(id='2', message_order='2',
                    time='2026-10-17T03:30:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=self.LATER, unread=False)]))
            count, _ = self.run_round(dict(side_effect=model), at)
            self.assertLessEqual(count, 3)
            calls.append(count)
            at += dt.timedelta(minutes=40)
        state = self.rows()
        self.assertIn(['message:p1-mix-a:2'], seen[:3], 'the later normal message is not starved by the audits')
        self.assertTrue(any(self.LATER in i['body'] for i in state['items']))
        self.assertEqual(seen.count(['message:p1-mix-b:1']), 3, 'the failing audit stops at three attempts')
        self.assertEqual(len([i for i in state['items'] if '秋游安全告知书' in i['body'] and 'p1-mix-a' in i['evidence']]), 1)
        self.assertLessEqual(seen.count(['message:p1-mix-c:1']), 1)
        assert_reread_in_place(self, a_old, next(i for i in state['items'] if i['id'] == a_old['id']))  # untouched review: was byte-identical (v4)
        for old in [c_old, by[self.B['id']][0]]:  # dismissed and auto-accepted rows are never rewritten
            self.assertEqual(next(i for i in state['items'] if i['id'] == old['id']), old, 'old rows kept')
        self.assertFalse([i for i in state['items'] if 'p1-mix-c' in i['evidence'] and i['id'] != c_old['id']], 'dismissed not copied')
        for key, job in before['jobs'].items():
            self.assertEqual(state['jobs'][key], job, key)
        self.assertEqual([m['processed'] for m in state['messages']], [1] * 4)


def natural(case, prefix, source, text, reply, script=SEED):
    """setUp shared by Root's counters: exact old source, real ingest/run_once/save, then the new source's own store."""
    directory = tempfile.TemporaryDirectory(prefix=prefix)
    case.addCleanup(directory.cleanup)
    case.root = Path(directory.name).resolve()
    case.old = seed(case.root, source, text, reply, script)
    case.data = case.root / 'family' / 'private'
    case.app = family_review.load_app(case.root / 'family', case.data)
    case.store = agent.Store(case.app.connect, case.app.profiles, case.data, app=case.app)
    case.stack = ExitStack(); case.addCleanup(case.stack.close)
    case.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
    case.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
    case.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
    case.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
    case.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
    case.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)


# Root counter 1 (ROOT-actual-counterexample.json): one message, one shared header deadline, two independent forms.
SHARED_SOURCE = dict(SOURCE, id='root-shared-forms-A')
SHARED_REF = 'message:root-shared-forms-A:1'
SHARED_FIRST = '在《阅读资料领取登记表》上填写学生姓名和领取份数，家长签字后交回班主任'
SHARED_SECOND = '在《朗读材料预约登记表》上填写学生姓名和预约份数，家长签字后交回班主任'
SHARED_TEXT = '2026年10月22日前，请分别办理以下两项：' + SHARED_FIRST + '；' + SHARED_SECOND + '。'
SHARED_OLD_REPLY = dict(proposals=[dict(  # Root's old_synthetic_first_only_reply (SYNTHETIC), refs unchanged
    due='2026-10-22', evidence=[dict(ref=SHARED_REF)], focus='school', learning_goal_id='', learning_subject='', task_advice='',
    task_change='new', task_goal=SHARED_FIRST + '。完成时间：2026年10月22日前。', task_purpose='admin',
    task_reason='SYNTHETIC：故意只返回第一独立表单；0真实provider，非实际模型准确性样本。', task_state='ready',
    task_submission='家长签字后交回班主任', task_target_id='', task_title='填写签领登记并交回班主任',
    title_quote='2026年10月22日前，请分别办理以下两项：' + SHARED_FIRST)])


def shared_history_reply(old_id):  # Root's case1_frozen_history_reply (SYNTHETIC), both dues 22, own contiguous quotes
    first = dict(SHARED_OLD_REPLY['proposals'][0], action_quote=SHARED_FIRST, existing_item_id=old_id, title_quote=SHARED_FIRST)
    second = dict(first, action_quote=SHARED_SECOND, existing_item_id='', title_quote=SHARED_SECOND,
                  task_goal=SHARED_SECOND + '。完成时间：2026年10月22日前。', task_title='填写预约登记并交回班主任',
                  task_reason='SYNTHETIC：第二独立行政表单，适用原文明确共同截止；0真实provider。')
    return dict(proposals=[first, second])


class SharedDeadlineAcceptedFormTests(unittest.TestCase):
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round

    def setUp(self):
        natural(self, 'synthetic-shared-forms-', SHARED_SOURCE, SHARED_TEXT, SHARED_OLD_REPLY)

    def test_old_seed_is_the_auto_accepted_first_form(self):
        state = self.rows()
        item, = state['items']
        plan = json.loads(item['plan'])
        self.assertEqual((item['state'], plan['school_task'].get('auto_added'), item['due']), ('accepted', True, '2026-10-22'))
        self.assertEqual(SHARED_TEXT.count(item['body']), 0, 'the old body is a normalized goal, not an original substring')
        self.assertEqual(SHARED_TEXT.count(plan['school_date_quote']), 1, 'the saved date quote is one contiguous original span')
        self.assertNotIn('school_action_anchor', plan)
        task, = state['tasks']
        self.assertEqual((task['id'], task['due']), (item['task_id'], '2026-10-22'))

    def test_saved_action_proof_locates_the_old_form_and_the_second_form_is_saved_once(self):
        before = self.rows()
        old_item, = before['items']
        sent = []
        def model(messages, *args, **kwargs):  # SYNTHETIC history-mode reply only
            body = json.loads(messages[1]['content'])
            sent.append(body.get('existing_actions'))
            return shared_history_reply(old_item['id'])
        calls = [self.run_round(dict(side_effect=model), self.now + dt.timedelta(minutes=41 * i))[0] for i in range(3)]
        self.assertEqual(sum(calls), 1, calls)
        self.assertTrue(sent and sent[0] and sent[0][0]['action_anchor'], 'the old form is offered with its located original action')
        state = self.rows()
        audit = [j for k, j in state['jobs'].items() if k.startswith('school-history:')]
        self.assertEqual([(j['done'], j['error']) for j in audit], [(1, '')])
        self.assertEqual(next(i for i in state['items'] if i['id'] == old_item['id']), old_item, 'old accepted row byte-identical')
        self.assertEqual([t for t in state['tasks'] if t['id'] == old_item['task_id']], before['tasks'], 'old task unchanged')
        new = [i for i in state['items'] if i['id'] != old_item['id']]
        self.assertEqual(len(new), 1, new)
        self.assertIn(SHARED_SECOND, new[0]['body'])
        self.assertNotIn('阅读资料领取登记表', new[0]['body'])
        self.assertEqual(new[0]['due'], '2026-10-22', 'the explicit shared header deadline, read from the original')
        self.assertEqual(json.loads(new[0]['plan'])['school_action_anchor'], {SHARED_REF: SHARED_SECOND})
        self.assertIn(SHARED_REF, new[0]['evidence'])
        for text in [t['action'] for t in state['tasks']] + [i['body'] for i in state['items']]:
            self.assertFalse('阅读资料领取登记表' in text and '朗读材料预约登记表' in text, 'merged: ' + text)
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        self.assertEqual((state['messages'], state['cursor']), (before['messages'], before['cursor']))
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        for minutes in (200, 241, 400):
            count, _ = self.run_round(dict(side_effect=AssertionError('once per old batch')), self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(count, 0)
        again = self.rows()
        self.assertEqual((again['items'], again['tasks']), (state['items'], state['tasks']))


class RouteSwitchBudgetTests(unittest.TestCase):  # Root counter 2: one recovery budget per old batch across routes
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round

    def setUp(self):
        natural(self, 'synthetic-route-budget-', SOURCE, TEXT, SYNTHETIC)

    def test_crossing_the_original_due_does_not_refill_the_exhausted_budget(self):
        before = self.rows()
        old_item, = before['items']
        fail = dict(side_effect=agent.family_llm.LLMDraftError('SYNTHETIC：同一旧批次固定失败；0真实provider。'))
        timeline = []
        late = dt.datetime(2026, 10, 23, 18, 0, tzinfo=agent.TZ)  # only the clock passes the original due 2026-10-22
        for at in [self.now + dt.timedelta(minutes=m) for m in (0, 41, 82)] + [late + dt.timedelta(minutes=m) for m in (0, 41, 82)]:
            count, _ = self.run_round(fail, at)
            jobs = self.rows()['jobs']
            timeline.append((at.isoformat(), count, sorted((k.split(':')[0], j['attempts'], j['done']) for k, j in jobs.items()
                                                         if k.startswith(('school-task:', 'school-history:')))))
        self.assertEqual(sum(t[1] for t in timeline), 3, timeline)
        state = self.rows()
        self.assertEqual(state['items'], before['items'])
        self.assertEqual(state['jobs'][old_item['job_id']], before['jobs'][old_item['job_id']])
        self.assertEqual((state['messages'], state['cursor']), (before['messages'], before['cursor']))
        # Only the existing explicit retry of the failed identity renews it.
        self.store.act(dict(action='retry', id='school-task:' + old_item['id']))
        count, _ = self.run_round(fail, late + dt.timedelta(minutes=200))
        self.assertEqual(count, 1)


SEED_PAIR = SEED.replace("messages=[dict(id='1', message_order='1',\n    time='2026-10-16T18:00:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=text, unread=False)]",
                         "messages=[dict(id=str(n + 1), message_order=str(n + 1),\n    time='2026-10-16T18:00:00+08:00', kind='text', sender='示例班主任', sender_id='school', text=t, unread=False) for n, t in enumerate(json.loads(text))]")
SIBLING_SOURCE = dict(SOURCE, id='postcandidate-samebatch-sibling')
SIBLING_MATH = '2026年10月22日前，完成数学《练习册》第18页第1至4题，写清计算过程。'
SIBLING_OLD_REPLY = dict(proposals=[  # Root's old_synthetic_selection_reply (SYNTHETIC)
    dict(SYNTHETIC['proposals'][0], evidence=[dict(ref='message:postcandidate-samebatch-sibling:1')]),
    dict(SYNTHETIC['proposals'][0], title_quote=SIBLING_MATH, evidence=[dict(ref='message:postcandidate-samebatch-sibling:2')],
         task_title='完成数学《练习册》第18页第1至4题', task_goal=SIBLING_MATH, task_state='review', task_purpose='learning',
         task_reason='synthetic：模型谨慎保留复核，本项原文与期限完整。')])


class SiblingNotOwnedTests(unittest.TestCase):  # Root counter 3: one reread row is not the owner of its whole batch
    rows = SavedSchoolRereadTests.rows
    run_round = SavedSchoolRereadTests.run_round

    def setUp(self):
        natural(self, 'synthetic-sibling-', SIBLING_SOURCE, json.dumps([TEXT, SIBLING_MATH], ensure_ascii=False), SIBLING_OLD_REPLY, SEED_PAIR)

    def test_old_seed_is_one_done_batch_with_two_pending_reviews(self):
        state = self.rows()
        self.assertEqual([(i['state'], json.loads(i['plan'])['school_task']['state']) for i in state['items']], [('pending', 'review')] * 2)
        self.assertEqual(len({i['job_id'] for i in state['items']}), 1)
        self.assertEqual((state['tasks'], [m['processed'] for m in state['messages']]), ([], [1, 1]))

    def test_the_sibling_review_is_understood_again_not_left_as_covered(self):
        before = self.rows()
        admin, math = sorted(before['items'], key=lambda i: SIBLING_MATH in i['body'])
        asked = []
        def model(messages, *args, **kwargs):  # SYNTHETIC: the single reread gets BRIEF, a batch audit both actions
            content = messages[1]['content']
            asked.append(content)
            if 'existing_actions' not in json.loads(content):
                return BRIEF
            return dict(proposals=[
                dict(SYNTHETIC['proposals'][0], evidence=[dict(ref='message:postcandidate-samebatch-sibling:1')], action_quote=TEXT,
                     existing_item_id=admin['id']),
                dict(SIBLING_OLD_REPLY['proposals'][1], action_quote=SIBLING_MATH, existing_item_id=math['id'], task_state='ready',
                     task_reason='synthetic：新理解，原文与期限完整。')])
        for i in range(4):
            self.run_round(dict(side_effect=model), self.now + dt.timedelta(minutes=41 * i))
        state = self.rows()
        self.assertTrue([c for c in asked if SIBLING_MATH in c], 'the second message is read again by the model')
        after = next(i for i in state['items'] if i['id'] == math['id'])
        revisions = [i for i in state['items'] if i['id'] not in (admin['id'], math['id'])]
        self.assertTrue(after != math or [i for i in revisions if math['id'] in i['plan']],
                        'the sibling gets its new understanding in place or a traceable same-item revision')
        self.assertFalse([i for i in revisions if '听写背诵订正材料领取登记单' in i['body']], 'no copy of the first action')
        self.assertLessEqual(len([t for t in state['tasks'] if '听写背诵订正材料领取登记单' in t['action']]), 1)
        self.assertEqual(state['jobs'][admin['job_id']], before['jobs'][admin['job_id']])
        self.assertEqual((state['messages'], state['cursor']), (before['messages'], before['cursor']))
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        for minutes in (300, 341, 500):
            count, _ = self.run_round(dict(side_effect=AssertionError('once per old batch')), self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(count, 0)
        again = self.rows()
        self.assertEqual((again['items'], again['tasks']), (state['items'], state['tasks']))


class EmptyInstallTests(unittest.TestCase):
    def test_no_old_batch_means_zero_audit_calls_and_a_fixed_empty_boundary(self):  # SR05 all-empty
        directory = tempfile.TemporaryDirectory(prefix='synthetic-empty-')
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve() / 'family'; data = root / 'private'; data.mkdir(parents=True)
        (root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        (data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': [SOURCE]}))
        app = family_review.load_app(root, data)
        agent.Store(app.connect, app.profiles, data, app=app)
        with ExitStack() as stack:
            stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
            stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
            stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
            stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
            stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
            model = stack.enter_context(patch.object(agent.family_llm, '_chat_json', side_effect=AssertionError('no audit call')))
            for minutes in (0, 41, 82):
                agent.run_once(app, dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ) + dt.timedelta(minutes=minutes))
        self.assertEqual(model.call_count, 0)
        with app.connect() as c:
            rows = [dict(r) for r in c.execute("SELECT id,done,attempts FROM agent_jobs WHERE id LIKE 'school-audit%'")]
        self.assertEqual(rows, [dict(id='school-audit-boundary', done=1, attempts=0)])


def saved_sr02_state(path):
    """The app's own state after the SR02 audit is saved by run_once (synthetic reply), for the Chromium original-entry check."""
    case = AutoAcceptedOldBatchTests('test_reread_finds_the_missing_action_without_copying_the_accepted_one')
    case.setUp()
    try:
        old_item, = case.rows()['items']
        case.run_round(dict(return_value=case.audit_reply(old_item['id'])), case.now)
        state = case.app.snapshot()
        state['saved_calendar'] = case.app.calendar_snapshot('2026-10-17', '2026-10-17')
        state['sr02'] = dict(old_item=old_item['id'], old_task=old_item['task_id'], old_action=SR02_FIRST, second=SR02_SECOND)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, default=str)
    finally:
        case.doCleanups()


if __name__ == '__main__':
    if sys.argv[1:2] == ['--saved-sr02-state']:
        saved_sr02_state(sys.argv[2])
    else:
        unittest.main()

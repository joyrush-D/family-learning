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


def seed(root, source=SOURCE, text=TEXT, reply=SYNTHETIC):
    """Exact old source, real ingest/run_once/save; returns the old run's own report."""
    old = root / 'old-source'
    old.mkdir()
    archive = subprocess.run(['git', '-C', str(HERE), 'archive', OLD], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(old)], input=archive, check=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    out = subprocess.run([sys.executable, '-I', '-c', 'import sys;p,s=sys.argv[1:3];del sys.argv[1:3];sys.path.insert(0,p);exec(s)',
                          str(old), SEED, str(root / 'family'), json.dumps(source), text, json.dumps(reply)],
                         check=True, capture_output=True, text=True, cwd=old, env=env).stdout
    return json.loads(out.strip().splitlines()[-1])


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
        item, = self.rows()['items']
        self.store.act(dict(id=item['id'], action='dismiss'))
        before = self.rows()
        calls, _ = self.run_round(dict(side_effect=AssertionError('decided item must not be reread')), self.now)
        self.assertEqual(calls, 0, 'nothing eligible: zero recovery calls')
        self.assertEqual(self.rows(), before)

    def test_changed_generated_snapshot_fails_closed(self):
        item, = self.rows()['items']
        with self.app.connect() as c:  # a parent-side edit of the saved draft; created/updated are left equal on purpose
            c.execute('UPDATE agent_items SET title=? WHERE id=?', ('家长改过的标题', item['id']))
        before = self.rows()
        calls, _ = self.run_round(dict(side_effect=AssertionError('edited draft must not be reread')), self.now)
        self.assertEqual(calls, 0)
        self.assertEqual(self.rows(), before)

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
        self.assertNotIn('秋游安全告知书', json.dumps(state, ensure_ascii=False), 'the second action was never saved')
        self.assertEqual([m['processed'] for m in state['messages']], [1])
        self.assertEqual(state['jobs'][item['job_id']]['done'], 1)

    @unittest.expectedFailure  # OPEN GAP (SR02 not implemented): auto-accepted batches are not reread yet
    def test_reread_finds_the_missing_action_without_copying_the_accepted_one(self):
        before = self.rows()
        old_item, = before['items']
        calls = [self.run_round(dict(return_value=SR02_FULL_REPLY), self.now + dt.timedelta(minutes=41 * i))[0] for i in range(3)]
        self.assertGreaterEqual(sum(calls), 1)
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


if __name__ == '__main__':
    unittest.main()

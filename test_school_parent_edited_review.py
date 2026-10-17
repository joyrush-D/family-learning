"""SR03: an accepted, parent-edited school action whose original receipt dropped part of its own teacher sentence.

Purely synthetic. The seed is old commit 632a778's own Store.ingest→run_once→save with a disclosed fixed reply; the parent
then accepts with own text, edits the same task and saves feedback through the ordinary public functions. The later reread
returns the same original sentence, ref and existing_item_id. All replies are explicit fixed local program control, not a
model measurement; no real model is called.
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
import family_task_focus
from test_school_saved_reread import SOURCE, seed

HERE = Path(__file__).resolve().parent
R257 = 'da0b7076f5005ecd7dd6967b48e63e9ac06bdb16'
SRC = dict(SOURCE, id='synthetic-sr03-parent-edited')
REF = 'message:synthetic-sr03-parent-edited:1'
TEACHER = '2026年10月22日前，在《听写背诵订正材料领取登记单》上填写学生姓名和领取份数，家长签字后交回班主任。'
SHORT = '2026年10月22日前，在《听写背诵订正材料领取登记单》上填写学生姓名，家长签字后交回班主任。'
TITLE = '填写《听写背诵订正材料领取登记单》并交回'
REASON = 'SYNTHETIC固定回执：本项领取登记，非真实模型测量。'
ACCEPT_BODY = SHORT + '\n家长安排：10月21日晚饭后准备，放入蓝色文件夹。'
EDITED_BODY = ACCEPT_BODY + '\n家长补充安排：先把登记单放在餐桌左侧，装袋前核对姓名。'
EDITED_TITLE = '家长修改：登记单交回安排'


def old_reply(goal):
    return dict(proposals=[dict(
        title_quote=TEACHER, focus='school', due='2026-10-22', evidence=[dict(ref=REF)], learning_subject='', learning_goal_id='',
        task_title=TITLE, task_goal=goal, task_advice='', task_state='ready', task_reason=REASON, task_change='new',
        task_target_id='', task_purpose='admin', task_submission='')])


def reread_reply(existing):
    proposal = dict(old_reply(TEACHER)['proposals'][0], action_quote=TEACHER, existing_item_id=existing)
    return dict(proposals=[proposal])


RUN_AT = r'''
import datetime as dt, json, sys
from pathlib import Path
from unittest.mock import patch
root = Path(sys.argv[1]); data = root / 'private'; reply = json.loads(sys.argv[2])
import family_review, family_agent as agent, family_media
app = family_review.load_app(root, data)
calls = []
def model(messages, schema, name, **kw):
    calls.append(name)
    return reply if name == 'family_agent_selection' else dict(proposal=None)
with patch('family_qq_capture.run_one', return_value=dict(state='disabled')), \
     patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')), \
     patch.object(family_media, 'run_one', return_value=dict(state='ready')), \
     patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)), \
     patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())), \
     patch.object(agent.family_llm, '_chat_json', side_effect=model):
    agent.run_once(app, dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ))
print(json.dumps(dict(calls=calls)))
'''


def run_at_commit(root, commit, reply):
    """The exact public r257 source runs its own natural round on the same sandbox (Git archive from this real repository)."""
    tree = root / ('source-' + commit[:7])
    tree.mkdir()
    archive = subprocess.run(['git', '-C', str(HERE), 'archive', commit], check=True, capture_output=True).stdout
    subprocess.run(['tar', '-x', '-C', str(tree)], input=archive, check=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    out = subprocess.run([sys.executable, '-I', '-c', 'import sys;p,s=sys.argv[1:3];del sys.argv[1:3];sys.path.insert(0,p);exec(s)',
                          str(tree), RUN_AT, str(root / 'family'), json.dumps(reply)],
                         check=True, capture_output=True, text=True, cwd=tree, env=env).stdout
    return json.loads(out.strip().splitlines()[-1])


class ParentEditedReviewTests(unittest.TestCase):
    old_goal = SHORT

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-sr03-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.seeded = seed(self.root, source=SRC, text=TEACHER, reply=old_reply(self.old_goal))
        self.data = self.root / 'family' / 'private'
        self.open()
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('family_goals.Store.run', return_value=dict(used=0, failed=0, created=0, children=set())))
        self.now = dt.datetime(2026, 10, 17, 3, 0, tzinfo=agent.TZ)
        self.item, = self.rows()['items']
        self.parent_edits()

    def open(self):
        self.app = family_review.load_app(self.root / 'family', self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)

    def parent_edits(self):
        result = self.store.act(dict(action='accept', id=self.item['id'], title='家长确认：领取登记单交回', body=ACCEPT_BODY))
        self.task_id = result['task_id']
        family_task_focus.save(self.app, dict(id=self.task_id, version=0, request_key='synthetic-sr03-parent-task-edit', mode='next',
                                              next_action='', waiting_for='', review_on='', scheduled_on='2026-10-21',
                                              title=EDITED_TITLE, goal=EDITED_BODY))
        self.app.save_task(dict(id=self.task_id, status='待跟进', note='虚构家长安排保留，尚未交回。'))
        self.app.save_task_feedback(dict(child='示例甲', day='2026-10-16', note='虚构家长反馈：登记单已找到，尚未填写。',
                                         request_key='synthetic-sr03-parent-feedback', task_id=self.task_id))

    def rows(self):
        with self.app.connect() as c:
            tables = {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            table = lambda name: [dict(r) for r in c.execute('SELECT * FROM ' + name + ' ORDER BY rowid')] if name in tables else []
            return dict(items=[dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY created,id")],
                        jobs={r['id']: dict(r) for r in c.execute('SELECT * FROM agent_jobs')},
                        tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')],
                        focus=table('task_focus'), focus_history=table('task_focus_history'),
                        updates=[dict(r) for r in c.execute('SELECT * FROM task_updates ORDER BY rowid')],
                        records=[dict(r) for r in c.execute('SELECT * FROM records ORDER BY id')],
                        messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages ORDER BY rowid')],
                        sources=[dict(r) for r in c.execute('SELECT * FROM agent_sources ORDER BY id')])

    def round(self, at, reply=None):
        names = []
        def model(messages, schema, name, **kw):
            names.append(name)
            return reply if name == 'family_agent_selection' else dict(proposal=None)
        with patch.object(agent.family_llm, '_chat_json', side_effect=model):
            agent.run_once(self.app, at)
        return names

    def protected(self, before, after):
        original = next(r for r in after['items'] if r['id'] == self.item['id'])
        self.assertEqual(original, next(r for r in before['items'] if r['id'] == self.item['id']), 'original item and receipt kept')
        for key in ('tasks', 'focus', 'focus_history', 'updates', 'records', 'messages', 'sources'):
            self.assertEqual(after[key], before[key], key + ' unchanged until the parent decides')
        old_job = self.item['job_id']
        self.assertEqual(after['jobs'][old_job], before['jobs'][old_job], 'original done batch receipt kept')


class MissingStandardTests(ParentEditedReviewTests):
    def assert_revision(self, before, after):
        self.protected(before, after)
        added = [r for r in after['items'] if r['id'] not in {v['id'] for v in before['items']}]
        self.assertEqual(len(added), 1, 'exactly one traceable revision of the same action')
        revision, = added
        plan = json.loads(revision['plan'])
        self.assertEqual(revision['state'], 'pending', 'never auto-accepted')
        self.assertEqual(plan['school_revision_of'], self.item['id'])
        self.assertEqual((plan['school_task']['change'], plan['school_task']['target_id'], plan['school_task']['state']),
                         ('append', self.task_id, 'review'), 'offered through the existing task correction entry')
        self.assertIn(TEACHER, revision['body'])
        self.assertEqual(plan['school_revision_basis']['previous_goal'], SHORT, 'the retained model receipt it revises')
        self.assertEqual([e['ref'] for e in json.loads(revision['evidence'])], [REF])
        self.assertEqual(revision['child_id'], self.item['child_id'])
        return revision

    def accept_revision(self, revision):
        task = next(t for t in self.app.tasks() if t['id'] == self.task_id)
        with self.app.connect() as c:
            update = c.execute('SELECT updated FROM task_updates WHERE id=?', (self.task_id,)).fetchone()
        return agent.apply_school_change(self.app, self.store, dict(
            action='school_change', id=revision['id'], target_id=self.task_id, change='append', title=task['title'],
            body=revision['body'], due=task['agenda']['due_on'], expected_updated=revision['updated'],
            target_version=task['focus']['version'], target_updated=update['updated'] if update else ''))

    def check_accepted_and_quiet(self, revision, before):
        result = self.accept_revision(revision)
        self.assertEqual(result['task_id'], self.task_id, 'the same original task')
        self.open()
        state = self.rows()
        self.assertEqual([t['id'] for t in state['tasks']], [self.task_id], 'no second independent task')
        task = next(t for t in self.app.tasks() if t['id'] == self.task_id)
        self.assertTrue(task['action'].startswith(EDITED_BODY), 'parent text and arrangement kept')
        self.assertIn(TEACHER, task['action'])
        self.assertEqual(task['title'], EDITED_TITLE)
        self.assertEqual(task['focus']['scheduled_on'], '2026-10-21')
        self.assertEqual(state['records'], before['records'], 'its feedback stays on the original task')
        original = next(r for r in state['items'] if r['id'] == self.item['id'])
        self.assertEqual((original['state'], original['task_id']), ('accepted', self.task_id))
        # Reopened later rounds read nothing again and add nothing.
        for minutes in (1, 42):
            self.open()
            names = self.round(self.now + dt.timedelta(minutes=minutes), reread_reply(self.item['id']))
            self.assertNotIn('family_agent_selection', names)
        self.assertEqual(len(self.rows()['items']), len(state['items']))

    def test_first_reread_keeps_a_checkable_revision_on_the_same_task(self):
        before = self.rows()
        names = self.round(self.now, reread_reply(self.item['id']))
        self.assertEqual(names.count('family_agent_selection'), 1, 'one school call of the original round')
        self.assertLessEqual(len(names), 3)
        after = self.rows()
        revision = self.assert_revision(before, after)
        self.check_accepted_and_quiet(revision, before)

    def test_r257_done_audit_is_recovered_once_after_upgrade(self):
        before = self.rows()
        self.assertEqual(run_at_commit(self.root, R257, reread_reply(self.item['id']))['calls'].count('family_agent_selection'), 1)
        self.open()
        r257 = self.rows()
        self.assertEqual(len(r257['items']), 1, 'r257 dropped the new understanding (the reproduced gap)')
        names = self.round(self.now + dt.timedelta(minutes=10), reread_reply(self.item['id']))  # an even five-minute history window
        self.assertEqual(names.count('family_agent_selection'), 1, 'one bounded recovery call')
        self.assertLessEqual(len(names), 3)
        after = self.rows()
        revision = self.assert_revision(r257, after)
        self.check_accepted_and_quiet(revision, before)

    def test_recovery_failure_keeps_old_values_and_retries_within_the_limit(self):
        run_at_commit(self.root, R257, reread_reply(self.item['id']))
        self.open()
        before = self.rows()
        calls = 0
        for minutes in (10, 70, 310, 910, 2010):  # even five-minute history windows, past each backoff
            names = []
            def model(messages, schema, name, **kw):
                names.append(name)
                if name == 'family_agent_selection': raise agent.family_llm.LLMDraftError('synthetic 503')
                return dict(proposal=None)
            with patch.object(agent.family_llm, '_chat_json', side_effect=model):
                agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))
            calls += names.count('family_agent_selection')
        self.assertLessEqual(calls, agent.MAX_ATTEMPTS, 'the stable retry limit is not refilled')
        after = self.rows()
        self.protected(before, after)
        self.assertEqual(len(after['items']), 1)

    def test_parent_change_during_the_call_is_refused(self):
        def model(messages, schema, name, **kw):
            if name == 'family_agent_selection':
                task = next(t for t in self.app.tasks() if t['id'] == self.task_id)
                family_task_focus.save(self.app, dict(id=self.task_id, version=task['focus']['version'], request_key='synthetic-race',
                    mode='next', next_action='', waiting_for='', review_on='', scheduled_on='2026-10-20', title=EDITED_TITLE, goal=EDITED_BODY))
                return reread_reply(self.item['id'])
            return dict(proposal=None)
        with patch.object(agent.family_llm, '_chat_json', side_effect=model):
            agent.run_once(self.app, self.now)
        state = self.rows()
        self.assertEqual(len(state['items']), 1, 'no revision saved over a changed decision')
        self.assertEqual(state['focus'][-1]['scheduled_on'], '2026-10-20')


class DismissedDecisionTests(ParentEditedReviewTests):
    def parent_edits(self):
        self.store.act(dict(action='dismiss', id=self.item['id']))
        self.task_id = ''

    def test_dismissed_action_is_not_revived(self):
        before = self.rows()
        self.round(self.now, reread_reply(self.item['id']))
        after = self.rows()
        self.assertEqual(after['items'], before['items'], 'a parent decision to drop the action is no new teacher requirement')
        self.assertEqual(after['tasks'], [])


class ParentAlreadyWroteItTests(ParentEditedReviewTests):
    def parent_edits(self):
        result = self.store.act(dict(action='accept', id=self.item['id'], title='家长确认：领取登记单交回', body=ACCEPT_BODY + '\n记得写领取份数。'))
        self.task_id = result['task_id']

    def test_task_that_already_holds_the_part_gets_no_revision(self):
        before = self.rows()
        self.round(self.now, reread_reply(self.item['id']))
        after = self.rows()
        self.protected(before, after)
        self.assertEqual(len(after['items']), 1)


class CompleteReceiptTests(ParentEditedReviewTests):
    old_goal = TEACHER

    def test_same_understanding_is_deduplicated(self):
        before = self.rows()
        names = self.round(self.now, reread_reply(self.item['id']))
        self.assertEqual(names.count('family_agent_selection'), 1)
        after = self.rows()
        self.protected(before, after)
        self.assertEqual(len(after['items']), 1, 'no revision or task for the same understanding')
        for minutes in (1, 42):
            self.open()
            self.assertNotIn('family_agent_selection', self.round(self.now + dt.timedelta(minutes=minutes), reread_reply(self.item['id'])))
        self.assertEqual(len(self.rows()['items']), 1)

    def test_r257_done_complete_receipt_is_not_reread_again(self):
        run_at_commit(self.root, R257, reread_reply(self.item['id']))
        self.open()
        self.assertNotIn('family_agent_selection', self.round(self.now + dt.timedelta(minutes=10), reread_reply(self.item['id'])))
        self.assertEqual(len(self.rows()['items']), 1)


if __name__ == '__main__':
    unittest.main()

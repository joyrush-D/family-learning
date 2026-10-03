"""Synthetic processed-message recovery through the ordinary Agent tick; no real models or collectors."""
from contextlib import ExitStack
import copy
import datetime as dt
import json
import sqlite3
import unittest
from unittest.mock import patch

import family_agent as agent
import family_task_focus
import test_agent as fixtures


class SchoolHistoryTests(unittest.TestCase):
    def setUp(self):
        # Composition keeps unittest from re-running all of AgentTests here.
        self.fixture = fixtures.AgentTests(methodName='runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.app, self.store = self.fixture.app, self.fixture.store
        self.clock = self.fixture.now
        self.groups, self.calls, self.fresh_responses = [], [], {}
        self.history_response = None
        self.sources = [self.fixture.source]
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(agent, '_now', side_effect=lambda value=None: value if value is not None else self.clock))
        self.stack.enter_context(patch.object(agent.family_llm, '_chat_json', side_effect=self._model))
        self.stack.enter_context(patch.object(agent.family_llm, 'extract_draft', side_effect=self._unexpected_external))
        self.stack.enter_context(patch('family_qq_capture.run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_teacher_public, 'run_one', return_value=dict(state='disabled')))
        self.stack.enter_context(patch.object(agent.family_media, 'run_one', return_value=dict(state='ready')))
        self.stack.enter_context(patch.object(agent.family_media, 'prepare_draft', return_value=dict(used=0, failed=0)))
        self.stack.enter_context(patch('subprocess.Popen', side_effect=self._unexpected_external))
        self.stack.enter_context(patch('urllib.request.urlopen', side_effect=self._unexpected_external))
        self.stack.enter_context(patch('socket.socket.connect', side_effect=self._unexpected_external))
        self.stack.enter_context(patch('socket.socket.connect_ex', side_effect=self._unexpected_external))

    def _unexpected_external(self, *args, **kwargs):
        raise AssertionError('Synthetic history tests must not invoke models, collectors, devices or network')

    def _model(self, messages, schema, name, *args, data_path=None, **kwargs):
        self.assertEqual(data_path, self.fixture.data)
        context = json.loads(messages[-1]['content'])
        self.assertEqual(context['as_of'], self.clock.date().isoformat())
        # The actual model boundary must remain outside the save transaction.
        with sqlite3.connect(self.app.DB, timeout=0.1) as c:
            c.execute('BEGIN IMMEDIATE')
            c.rollback()
        self.calls.append(dict(name=name, context=copy.deepcopy(context), schema=copy.deepcopy(schema), at=self.clock.isoformat()))
        if name == 'family_agent_plan':
            return dict(proposal=None)
        self.assertEqual(name, 'family_agent_selection')
        fields = schema['properties']['proposals']['items']
        ordinary = set(agent._school_fields['required'])
        if 'existing_actions' in context:
            self.assertEqual(set(fields['required']), ordinary | {'action_quote', 'existing_item_id'})
            self.assertEqual(set(fields['properties']['existing_item_id']['enum']),
                             {''} | {row['id'] for row in context['existing_actions']})
            self.assertIsNotNone(self.history_response, 'Unexpected history model call')
            response = self.history_response(context) if callable(self.history_response) else self.history_response
        else:
            self.assertEqual(set(fields['required']), ordinary)
            self.assertNotIn('action_quote', fields['properties'])
            self.assertNotIn('existing_item_id', fields['properties'])
            refs = tuple(sorted(e['ref'] for e in context['evidence']))
            self.assertIn(refs, self.fresh_responses, 'Unexpected fresh school scope')
            response = self.fresh_responses[refs]
        return copy.deepcopy(response)

    def _tick(self, minutes):
        self.clock = self.fixture.now + dt.timedelta(minutes=minutes)
        before = len(self.calls)
        result = agent.run_once(self.app, self.clock)
        self.assertLessEqual(len(self.calls) - before, 3, 'All model paths share the original tick budget')
        return result

    def _config(self):
        (self.fixture.data / 'agent.json').write_text(json.dumps(dict(enabled=True, sources=self.sources)))

    def _legacy(self, *, suffix='', ids=('11', '12'), missing=None, tick=0, feedback=False):
        source = self.fixture.source
        first = '2月12日前交《回执A' + suffix + '》。'
        missing = missing or '2月12日前带《材料B' + suffix + '》1份到校。'
        optional = '自愿报名《活动C' + suffix + '》，不参加也无需回复。'
        refs = ['message:' + source['id'] + ':' + ident for ident in ids]
        with self.app.connect() as c:
            saved = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (source['id'],)).fetchone()
        payload = self.fixture.payload(expected=saved['cursor'] if saved else source['cursor'], cursor=ids[-1], offset=tick)
        payload['messages'] = [dict(id=ident, time=payload['checked_at'], kind='text', sender='示例老师',
                                    sender_id='synthetic-teacher', text=text, unread=False)
                               for ident, text in zip(ids, (first + missing, optional))]
        self.store.ingest(payload)
        old = dict(proposals=[
            fixtures.school_proposal(title_quote=first, due='2026-02-12', evidence=[dict(ref=refs[0])],
                task_title='家长事务：交《回执A' + suffix + '》', task_goal=first, task_state='review',
                task_reason='虚构旧归纳，待家长确认。', task_purpose='admin'),
            fixtures.school_proposal(title_quote=optional, evidence=[dict(ref=refs[1])],
                task_title='可选活动C' + suffix, task_goal=optional, task_state='review',
                task_reason='原文明确自愿参加。', task_purpose='optional')])
        self.fresh_responses[tuple(sorted(refs))] = old
        result = self._tick(tick)
        self.assertEqual((result['failed'], result['created']), (0, 2))
        with self.app.connect() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")
                    if {e['ref'] for e in json.loads(r['evidence'])} & set(refs)]
            self.assertEqual(len(rows), 2)
            # Simulate already-saved legacy output; never reset processed or the collection cursor.
            for row in rows:
                plan = json.loads(row['plan'])
                self.assertEqual(plan.pop('school_selection_revision'), agent.SCHOOL_SELECTION_REVISION)
                c.execute('UPDATE agent_items SET plan=? WHERE id=?', (agent._json(plan), row['id']))
        a = next(row for row in rows if row['body'] == first)
        c_item = next(row for row in rows if row['body'] == optional)
        accepted = self.store.act(dict(id=a['id'], action='accept', title='家长确认：交《回执A' + suffix + '》',
                                      body=first + '\n家长安排：放在书包文件夹。'))
        self.store.act(dict(id=c_item['id'], action='dismiss'))
        self.app.save_task(dict(id=accepted['task_id'], status='待跟进', note='虚构家长：原安排保留。'))
        group = dict(refs=refs, first=first, missing=missing, optional=optional, a_id=a['id'], c_id=c_item['id'],
                     task_id=accepted['task_id'], job=a['job_id'], suffix=suffix)
        self.groups.append(group)
        if feedback:
            saved = self.app.save_task_feedback(dict(task_id=group['task_id'], child='示例甲', day='2026-02-10',
                note='虚构家长反馈：回执已放好，尚未交回。', request_key='synthetic-history-feedback-' + suffix))
            group['record_id'] = saved['record_id']
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages WHERE source_id=? AND id=?',
                (source['id'], ids[0])).fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT done FROM agent_jobs WHERE id=?', (group['job'],)).fetchone()[0], 1)
        return group

    def _response(self, group, *, due='2026-02-12', short_old=False):
        a_quote = '交《回执A' + group['suffix'] + '》' if short_old else group['first']
        c_quote = '报名《活动C' + group['suffix'] + '》' if short_old else group['optional']
        def proposal(quote, ref, **fields):
            return fixtures.school_proposal(title_quote=quote, evidence=[dict(ref=ref)],
                action_quote=quote, existing_item_id='', **fields)
        return dict(proposals=[
            proposal(a_quote, group['refs'][0], task_title='模型换题名A', task_goal=group['first'],
                     task_state='ready', task_purpose='admin'),
            proposal(c_quote, group['refs'][1], task_title='模型企图重新报名C', task_goal=group['optional'],
                     task_state='ready', task_purpose='admin'),
            proposal(group['missing'], group['refs'][0], due=due, task_title='携带《材料B' + group['suffix'] + '》1份',
                     task_goal=group['missing'], task_state='ready', task_reason='本项已读、独立且明确。', task_purpose='admin')])

    def _protected(self):
        item_ids = {g[key] for g in self.groups for key in ('a_id', 'c_id')}
        task_ids = {g['task_id'] for g in self.groups}
        old_jobs = {g['job'] for g in self.groups}
        with self.app.connect() as c:
            tables = {r['name'] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            value = {table: [dict(r) for r in c.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                     for table in ('agent_sources', 'agent_messages', 'records', 'task_updates', 'task_history')}
            value['items'] = [dict(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id') if r['id'] in item_ids]
            value['jobs'] = [dict(r) for r in c.execute('SELECT * FROM agent_jobs ORDER BY id') if r['id'] in old_jobs]
            value['tasks'] = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id') if r['id'] in task_ids]
            value['focus'] = [dict(r) for r in c.execute('SELECT * FROM task_focus ORDER BY task_id')
                              if r['task_id'] in task_ids] if 'task_focus' in tables else []
            value['published_at'] = {t['id']: t['agenda']['published_at'] for t in self.app.tasks(c) if t['id'] in task_ids}
        return value

    def _history_rows(self):
        with self.app.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")
                    if json.loads(r['plan']).get('school_history_job')]

    def _history_jobs(self):
        with self.app.connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'school-history:%' ORDER BY id")]

    def _school_task_counts(self):
        with self.app.connect() as c:
            return dict(
                school=c.execute("SELECT COUNT(*) FROM agent_items WHERE kind='school'").fetchone()[0],
                child_school=c.execute("SELECT COUNT(*) FROM agent_items WHERE kind='school' AND child_id='child-1'").fetchone()[0],
                tasks=c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],
                child_tasks=c.execute("SELECT COUNT(*) FROM manual_tasks WHERE child='示例甲'").fetchone()[0])

    def _assert_one_school_task_added(self, before):
        # created counts the candidate and its automatic acceptance separately;
        # persisted identities must still be exactly one new item and one same-child task.
        self.assertEqual(self._school_task_counts(), {key: value + 1 for key, value in before.items()})

    def _assert_zero_new(self, before):
        self.assertEqual(self._protected(), before)
        self.assertEqual(self._history_rows(), [])
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], len(self.groups))
        self.assertTrue(all(not row['done'] for row in self._history_jobs()))

    def test_processed_omission_recovers_once_without_rewriting_parent_decisions_or_sources(self):
        group = self._legacy(feedback=True)
        before = self._protected()
        before_counts = self._school_task_counts()
        self.history_response = self._response(group)
        def inspect(context):
            known = {row['id']: row for row in context['existing_actions']}
            self.assertEqual(known[group['a_id']]['state'], 'accepted')
            self.assertEqual(known[group['c_id']]['state'], 'dismissed')
            self.assertIn('家长安排', known[group['a_id']]['current_task']['action'])
            self.assertIn(group['missing'], context['evidence'][0]['text'])
            return self._response(group)
        self.history_response = inspect
        result = self._tick(10)
        self.assertEqual((result['failed'], result['created']), (0, 2))
        self._assert_one_school_task_added(before_counts)
        rows = self._history_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['state'], row['child_id'], row['due']), ('accepted', 'child-1', '2026-02-12'))
        self.assertEqual(json.loads(row['plan'])['school_action_anchor'], {group['refs'][0]: group['missing']})
        self.assertEqual({e['ref'] for e in json.loads(row['evidence'])}, {group['refs'][0]})
        with self.app.connect() as c:
            task = dict(c.execute('SELECT * FROM manual_tasks WHERE id=?', (row['task_id'],)).fetchone())
            self.assertEqual((task['action'], task['due'], task['original_status']), (group['missing'], '2026-02-12', '待跟进'))
            self.assertNotIn(group['refs'][1], task['source'])
        self.assertEqual(self._protected(), before)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.fixture.data, app=self.app)
        history_calls = sum('existing_actions' in call['context'] for call in self.calls)
        self.store.act(dict(action='retry', id=group['job']))
        self.store.act(dict(action='retry'))
        for minutes in (20, 30, 40):
            self.assertEqual(self._tick(minutes)['created'], 0)
        self.assertEqual(self._history_rows(), rows)
        self.assertEqual(sum('existing_actions' in call['context'] for call in self.calls), history_calls)
        self.assertEqual(self._protected(), before)

    def test_short_old_quotes_do_not_revive_accepted_or_dismissed_actions(self):
        group = self._legacy()
        before = self._protected()
        before_counts = self._school_task_counts()
        self.history_response = self._response(group, short_old=True)
        result = self._tick(10)
        self.assertEqual((result['failed'], result['created']), (0, 2))
        self._assert_one_school_task_added(before_counts)
        self.assertEqual(len(self._history_rows()), 1)
        self.assertIn('材料B', self._history_rows()[0]['title'])
        self.assertEqual(self._protected(), before)

    def _assert_review(self, group, due, minutes):
        before = self._protected()
        self.history_response = self._response(group, due=due)
        result = self._tick(minutes)
        self.assertEqual((result['failed'], result['created']), (0, 1))
        row = self._history_rows()[0]
        self.assertEqual((row['state'], json.loads(row['plan'])['school_task']['state']), ('pending', 'review'))
        self.assertEqual(row['due'], due if due and due < self.clock.date().isoformat() else '')
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 1)
        self.assertEqual(self._protected(), before)
        return row

    def test_old_action_with_unknown_date_stays_review_without_becoming_today(self):
        group = self._legacy(missing='截止日期另行通知：带《材料B》1份到校。')
        row = self._assert_review(group, '', 24 * 60)
        reason = json.loads(row['plan'])['school_task']['reason']
        self.assertIn('早于今天', reason)
        self.assertEqual(row['body'], group['missing'])

    def test_history_action_cannot_borrow_another_actions_deadline(self):
        group = self._legacy(missing='带《材料B》1份到校。')
        row = self._assert_review(group, '2026-02-12', 10)
        self.assertIn('截止日期尚无法', json.loads(row['plan'])['school_task']['reason'])

    def test_expired_history_action_retains_original_date_and_remains_review(self):
        group = self._legacy(missing='2月9日前带《材料B》1份到校。')
        row = self._assert_review(group, '2026-02-09', 10)
        self.assertIn('原截止日期已过', json.loads(row['plan'])['school_task']['reason'])

    def test_wrong_existing_binding_and_broad_old_plus_new_quote_reject_entire_scope(self):
        group = self._legacy()
        before = self._protected()
        for index, kind in enumerate(('wrong_binding', 'broad_quote', 'missing_field')):
            with self.subTest(kind=kind):
                response = self._response(group)
                b = response['proposals'][-1]
                if kind == 'wrong_binding': b['existing_item_id'] = group['a_id']
                elif kind == 'broad_quote': b['action_quote'] = group['first'] + group['missing']
                else: b.pop('action_quote')
                self.history_response = response
                self.store.act(dict(action='retry'))
                self.assertGreaterEqual(self._tick(10 + index * 10)['failed'], 1)
                self._assert_zero_new(before)

    def test_same_literal_missing_action_with_two_titles_rejects_entire_scope(self):
        group = self._legacy()
        before = self._protected()
        response = self._response(group)
        duplicate = dict(response['proposals'][-1], task_title='模型改名的另一个B', task_goal=group['missing'] + ' 模型重复描述。')
        response['proposals'].append(duplicate)
        self.history_response = response
        self.assertGreaterEqual(self._tick(10)['failed'], 1)
        self._assert_zero_new(before)

    def test_two_new_action_sentences_half_clause_and_date_only_anchor_reject_entire_scope(self):
        group = self._legacy(missing='2月13日前带《材料B》1份到校。2月14日前带《物品D》1份到校。')
        before = self._protected()
        quotes = (group['missing'], '带《材料B》1份到校', '2月13日')
        for index, quote in enumerate(quotes):
            with self.subTest(quote=quote):
                response = self._response(group, due='2026-02-13')
                response['proposals'][-1]['action_quote'] = quote
                self.history_response = response
                self.store.act(dict(action='retry'))
                self.assertGreaterEqual(self._tick(10 + index * 10)['failed'], 1)
                self._assert_zero_new(before)

    def test_parent_edit_during_model_discards_result_and_next_tick_uses_current_decision(self):
        group = self._legacy(feedback=True)
        before = self._protected()
        after_edit = []
        def edit(context):
            family_task_focus.save(self.app, dict(id=group['task_id'], version=0,
                request_key='synthetic-history-parent-edit', mode='next', next_action='', waiting_for='', review_on='',
                title='家长重新确认的回执A', goal='家长更正：只带回执，等老师答复再交。'))
            after_edit.append(self._protected())
            return self._response(group)
        self.history_response = edit
        self.assertGreaterEqual(self._tick(10)['failed'], 1)
        self.assertEqual(self._history_rows(), [])
        self.assertEqual(self._protected(), after_edit[0])
        self.assertEqual(after_edit[0]['tasks'], before['tasks'])
        self.assertEqual(after_edit[0]['items'], before['items'])
        self.assertEqual(after_edit[0]['records'], before['records'])
        self.history_response = self._response(group)
        self.assertEqual((self._tick(20)['failed'], len(self._history_rows())), (0, 1))
        self.assertEqual(self._protected(), after_edit[0])

    def test_source_pause_during_model_saves_nothing_and_resumes_without_cursor_reset(self):
        group = self._legacy()
        before = self._protected()
        before_counts = self._school_task_counts()
        def pause(context):
            self.fixture.source['enabled'] = False
            self._config()
            return self._response(group)
        self.history_response = pause
        self.assertGreaterEqual(self._tick(10)['failed'], 1)
        self._assert_zero_new(before)
        count = len(self.calls)
        self.assertEqual(self._tick(20)['created'], 0)
        self.assertEqual(len(self.calls), count)
        self.fixture.source['enabled'] = True
        self._config()
        self.history_response = self._response(group)
        result = self._tick(30)
        self.assertEqual((result['failed'], result['created']), (0, 2))
        self._assert_one_school_task_added(before_counts)
        self.assertEqual(self._protected(), before)

    def test_history_backoff_three_attempts_allow_later_scope_and_manual_retry_recovers_once(self):
        good = self._legacy()
        bad = self._legacy(suffix='2', ids=('21', '22'), tick=5)
        before = self._protected()
        before_counts = self._school_task_counts()
        bad_calls = []
        failing = [True]
        def response(context):
            refs = {e['ref'] for e in context['evidence']}
            group = bad if bad['refs'][0] in refs else good
            if group is bad and failing[0]:
                bad_calls.append(self.clock.isoformat())
                raise agent.family_llm.LLMDraftError('虚构后台暂时不可用')
            return self._response(group)
        self.history_response = response
        self.assertEqual(self._tick(10)['failed'], 1)
        job = self._history_jobs()[0]
        self.assertEqual((job['attempts'], job['done']), (1, 0))
        self.assertEqual(job['next_try'], (self.fixture.now + dt.timedelta(minutes=15)).isoformat())
        result = self._tick(12)
        self.assertEqual((result['failed'], result['created']), (0, 2), 'A waiting failed scope must not block the next group')
        self._assert_one_school_task_added(before_counts)
        self.assertEqual(len(bad_calls), 1)
        self.assertEqual(self._tick(20)['failed'], 1)
        bad_job = next(row for row in self._history_jobs() if not row['done'])
        self.assertEqual(bad_job['next_try'], (self.fixture.now + dt.timedelta(minutes=30)).isoformat())
        self.assertEqual(self._tick(22)['created'], 0)
        self.assertEqual(len(bad_calls), 2)
        self.assertEqual(self._tick(30)['failed'], 1)
        bad_job = next(row for row in self._history_jobs() if not row['done'])
        self.assertEqual((bad_job['attempts'], bad_job['next_try']), (3, ''))
        self.assertIn('3次', bad_job['error'])
        count = len(self.calls)
        self.assertEqual(self._tick(40)['created'], 0)
        self.assertEqual(len(self.calls), count)
        failing[0] = False
        self.store.act(dict(action='retry', id=bad_job['id']))
        before_counts = self._school_task_counts()
        self.assertEqual(self._tick(50)['created'], 2)
        self._assert_one_school_task_added(before_counts)
        self.assertEqual(len(self._history_rows()), 2)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.fixture.data, app=self.app)
        count = len(self.calls)
        self.assertEqual(self._tick(60)['created'], 0)
        self.assertEqual(len(self.calls), count)
        self.assertTrue(all(row['done'] for row in self._history_jobs()))
        self.assertEqual(self._protected(), before)

    def test_fresh_history_and_feedback_share_three_calls_and_leave_next_source_for_next_tick(self):
        group = self._legacy(feedback=True)
        self.history_response = self._response(group)
        for index in (1, 2):
            source = dict(self.fixture.source, id='synthetic-fresh-' + str(index), name='虚构新来源' + str(index))
            self.sources.append(source)
            self._config()
            text = '2月12日前带《物品D' + str(index) + '》1份到校。'
            ref = 'message:' + source['id'] + ':11'
            payload = dict(self.fixture.payload(), source_id=source['id'])
            payload['messages'][0].update(text=text, sender_id='synthetic-fresh-teacher-' + str(index))
            self.store.ingest(payload)
            self.fresh_responses[(ref,)] = dict(proposals=[fixtures.school_proposal(title_quote=text, due='2026-02-12',
                evidence=[dict(ref=ref)], task_title='携带物品D' + str(index), task_goal=text,
                task_state='ready', task_purpose='admin')])
        before_calls = len(self.calls)
        self.assertEqual(self._tick(10)['failed'], 0)
        calls = self.calls[before_calls:]
        self.assertEqual(len(calls), 3)
        self.assertEqual(sum('existing_actions' in call['context'] for call in calls), 1)
        self.assertEqual(sum(call['name'] == 'family_agent_plan' for call in calls), 1)
        with self.app.connect() as c:
            states = {r['source_id']: r['processed'] for r in c.execute("SELECT source_id,processed FROM agent_messages WHERE source_id LIKE 'synthetic-fresh-%'")}
        self.assertEqual(sorted(states.values()), [0, 1])
        self.assertEqual(self._tick(15)['failed'], 0)
        with self.app.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_messages WHERE source_id LIKE 'synthetic-fresh-%' AND processed=0").fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 4)
        self.assertEqual(len(self._history_rows()), 1)

    def test_later_material_cannot_replace_history_action_with_whole_notice_refinement(self):
        group = self._legacy(missing='带《材料B》1份到校。')
        row = self._assert_review(group, '', 24 * 60)
        protected = self._protected()
        plan = json.loads(row['plan'])
        count = len(self.calls)
        with patch.object(agent, '_school_drafts', return_value=dict(fingerprint='synthetic-changed-material')):
            result = self._tick(24 * 60 + 10)
        self.assertEqual(result['failed'], 0)
        self.assertEqual(len(self.calls), count, 'A whole-notice model cannot reinterpret the saved B action anchor')
        refreshed = self._history_rows()[0]
        self.assertEqual((refreshed['title'], refreshed['body'], refreshed['due']), (row['title'], row['body'], row['due']))
        self.assertEqual(json.loads(refreshed['plan'])['school_action_anchor'], plan['school_action_anchor'])
        self.assertEqual(json.loads(refreshed['plan'])['school_task']['state'], 'review')
        self.assertEqual(refreshed['state'], 'pending')
        self.assertEqual(self._protected(), protected)


if __name__ == '__main__':
    unittest.main()

"""Same child, same concrete school affair reminded again (ROOT S01-S06).

All children, teachers, groups and messages are fictional; model replies are controlled mocks, no product model is called.
A reminder in other words, another channel or by another publisher links to the one saved task as provenance only:
its requirements, date, arrangement, status and feedback stay; different ranges, children or new rounds stay separate.
"""
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import test_agent
from test_agent import school_proposal

READING_QQ = 'Unit 3课文读两遍，朗读录音上传班级作业区，明天完成。'
READING_WECHAT = '提醒一下，明天要交Unit 3朗读录音，课文读两遍再上传。'


class SchoolSameAffairTests(unittest.TestCase):
    setUp = test_agent.AgentTests.setUp
    config = test_agent.AgentTests.config

    def _candidate(self, index, text, *, source='synthetic-group', platform='wechat', publisher='synthetic-teacher-a', child='child-1',
                   change='new', target='', title='英语：Unit 3朗读', goal=None, due='', purpose='learning', subject='英语'):
        config = json.loads((self.data / 'agent.json').read_text())
        if not any(s['id'] == source for s in config['sources']):
            config['sources'].append(dict(self.source, id=source, platform=platform, child_id=child, name='虚构' + source))
            (self.data / 'agent.json').write_text(json.dumps(config))
        with self.app.connect() as c:
            previous = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (source,)).fetchone()
        message = dict(id=str(index), time=self.now.isoformat(), sender='虚构显示名', text=text, unread=False, kind='text', sender_id=publisher)
        self.store.ingest(dict(source_id=source, expected_cursor=previous['cursor'] if previous else '10', cursor=str(index),
                               checked_at=self.now.isoformat(), last_message_time=self.now.isoformat(), error='', messages=[message]))
        ref = 'message:' + source + ':' + str(index)
        evidence = [dict(message, ref=ref, publisher=agent._publisher(source, message), content_incomplete=False)]
        targets = agent.school_targets(self.app, self.store, child, evidence=[text])
        raw = dict(proposals=[school_proposal(title_quote=text, focus='school', due=due, evidence=[dict(ref=ref)], learning_subject=subject,
                                              task_title=title, task_goal=goal or text, task_state='ready', task_reason='虚构原文明确。',
                                              task_change=change, task_target_id=target, task_purpose=purpose)])
        with patch.object(agent.family_llm, '_chat_json', return_value=raw):
            items = agent._select('school', evidence, school_goals=[], school_tasks=targets, as_of=self.now.date().isoformat())
        self.assertEqual(len(items), 1)
        item = items[0]; item.update(child_id=child, kind='school')
        if item['plan'].get('school_learning'): item['plan']['school_messages'] = [dict(source_id=source, message_id=str(index))]
        job = 'synthetic-same:' + source + ':' + str(index)
        self.store._save(job, 'synthetic-fixed', [item], self.now)
        with self.app.connect() as c:
            return dict(c.execute('SELECT * FROM agent_items WHERE job_id=?', (job,)).fetchone())

    def _original(self, index=11, text=READING_QQ, **values):
        values = dict(dict(source='synthetic-qq', platform='qq', due='2026-02-11'), **values)
        row = self._candidate(index, text, **values)
        return row, self.store.act(dict(id=row['id'], action='accept'))['task_id']

    def _refresh(self):
        with patch.object(agent.family_llm, '_chat_json') as model, patch.object(agent, '_now', return_value=self.now):
            result = agent._refresh_school(self.app, self.store, self.now, 0)
            model.assert_not_called()
        return result

    def _rows(self, c, table):
        return [dict(r) for r in c.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]

    def _child_tasks(self, c, name='示例甲'):
        return [t for t in self.app.tasks(c) if t['child'] == name]

    def _reading_reminder(self, task_id, index=12, **values):
        return self._candidate(index, READING_WECHAT, change='same', target=task_id, due='2026-02-11',
                               goal='Unit 3课文读两遍，朗读录音上传，明天交。', **values)

    def test_s01_paraphrased_reminder_from_another_channel_is_one_task_with_both_originals(self):
        original, task_id = self._original()
        with self.app.connect() as c: original = dict(c.execute('SELECT * FROM agent_items WHERE id=?', (original['id'],)).fetchone())
        row = self._reading_reminder(task_id)
        brief = json.loads(row['plan'])['school_task']
        self.assertEqual((brief['state'], brief['change'], brief['target_id']), ('ready', 'same', task_id))
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            tasks = self._child_tasks(c)
            self.assertEqual([t['id'] for t in tasks], [task_id])
            task = tasks[0]
            self.assertEqual(task['action'], original['body']); self.assertEqual(task['agenda']['due_on'], '2026-02-11')
            self.assertIn('message:synthetic-qq:11', task['source']); self.assertIn('message:synthetic-group:12', task['source'])
            linked = dict(c.execute('SELECT * FROM agent_items WHERE id=?', (row['id'],)).fetchone())
            self.assertEqual((linked['state'], linked['task_id']), ('accepted', task_id))
            plan = json.loads(linked['plan'])
            self.assertEqual(plan['school_duplicate_of'], original['id'])
            self.assertEqual(plan['school_same_receipt']['task_id'], task_id)
            # The reminder keeps its own channel, publisher and original; the canonical item is untouched.
            self.assertEqual(json.loads(linked['evidence'])[0]['ref'], 'message:synthetic-group:12')
            canonical = dict(c.execute('SELECT * FROM agent_items WHERE id=?', (original['id'],)).fetchone())
            self.assertEqual((canonical['evidence'], canonical['body'], canonical['plan']), (original['evidence'], original['body'], original['plan']))
            messages = {(r['source_id'], r['id']) for r in c.execute('SELECT source_id,id FROM agent_messages')}
            self.assertTrue({('synthetic-qq', '11'), ('synthetic-group', '12')} <= messages)
            before = (self._rows(c, 'manual_tasks'), self._rows(c, 'agent_items'))
        # Lost reply, retry and reopen keep one relation and one task.
        replay = agent.apply_school_same(self.app, self.store, row['id'], row['updated'])
        self.assertEqual((replay['task_id'], replay['replayed']), (task_id, True))
        self.assertEqual(self.store.act(dict(id=row['id'], action='accept'))['task_id'], task_id)
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            self.assertEqual((self._rows(c, 'manual_tasks'), self._rows(c, 'agent_items')), before)

    def test_s02_receipt_reminded_by_another_publisher_keeps_each_attribution(self):
        receipt = dict(title='班务：交《春季研学回执》', purpose='admin', subject='')
        original, task_id = self._original(21, '周五交《春季研学回执》，家长签字。', source='synthetic-group', platform='wechat',
                                           due='2026-02-13', goal='周五交《春季研学回执》，家长签字。', **receipt)
        row = self._candidate(22, '周五别忘把签好字的春季研学回执带来。', source='synthetic-qq', platform='qq', publisher='synthetic-head-teacher',
                              change='same', target=task_id, due='2026-02-13', goal='周五带来家长签字的春季研学回执。', **receipt)
        self.assertEqual(json.loads(row['plan'])['school_task']['state'], 'ready')
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            self.assertEqual([t['id'] for t in self._child_tasks(c)], [task_id])
            linked = dict(c.execute('SELECT * FROM agent_items WHERE id=?', (row['id'],)).fetchone())
            self.assertEqual(linked['task_id'], task_id)
            refs = {json.loads(r['evidence'])[0]['ref'] for r in c.execute('SELECT evidence FROM agent_items WHERE task_id=?', (task_id,))}
            senders = {(r['source_id'], r['id']): json.loads(r['payload']).get('sender_id') for r in c.execute('SELECT source_id,id,payload FROM agent_messages')}
        # Each original keeps its own channel and publisher; recognizing one affair does not make them one person.
        self.assertEqual(refs, {'message:synthetic-group:21', 'message:synthetic-qq:22'})
        self.assertEqual((senders[('synthetic-group', '21')], senders[('synthetic-qq', '22')]), ('synthetic-teacher-a', 'synthetic-head-teacher'))

    def test_s03_reminder_keeps_saved_feedback_completion_and_parent_arrangement(self):
        original, task_id = self._original()
        with self.app.connect() as c: focus = next(t for t in self.app.tasks(c) if t['id'] == task_id)['focus']
        agent.family_task_focus.save(self.app, dict(id=task_id, version=focus['version'], request_key='synthetic-same-arranged', mode='waiting',
            next_action='保留家长安排：晚饭后录音', waiting_for='等虚构家长回家', review_on='2026-02-11', scheduled_on='2026-02-11', box='inbox'))
        feedback = self.app.save_task_feedback(dict(task_id=task_id, child='示例甲', day='2026-02-10', note='虚构原作答：录音已上传。', request_key='synthetic-same-feedback'))
        self.app.save_task(dict(id=task_id, status='已完成', note='虚构家长已核对完成。'))
        with self.app.connect() as c:
            before = dict(task=next(t for t in self.app.tasks(c) if t['id'] == task_id), updates=self._rows(c, 'task_updates'), records=self._rows(c, 'records'))
        row = self._reading_reminder(task_id)
        self.assertEqual(json.loads(row['plan'])['school_task']['state'], 'ready')
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            after = next(t for t in self.app.tasks(c) if t['id'] == task_id)
            for key in ('title', 'action', 'focus'): self.assertEqual(after[key], before['task'][key])
            # The shared projection keeps the date and every source, and now also shows the reminder as provenance.
            for key, value in before['task']['agenda'].items():
                if isinstance(value, list): self.assertTrue(all(v in after['agenda'][key] for v in value), key)
                else: self.assertEqual(after['agenda'][key], value, key)
            self.assertIn('message:synthetic-group:12', json.dumps(after['agenda'], ensure_ascii=False))
            self.assertEqual(self._rows(c, 'task_updates'), before['updates']); self.assertEqual(self._rows(c, 'records'), before['records'])
            self.assertIn(feedback['record_id'], [r['id'] for r in before['records']])
            self.assertEqual(len(self._child_tasks(c)), 1)
            self.assertEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?', (row['id'],)).fetchone()[0], task_id)

    def test_s03_concurrent_parent_edit_invalidates_the_stale_relation(self):
        original, task_id = self._original()
        row = self._reading_reminder(task_id)
        with self.app.connect() as c: focus = next(t for t in self.app.tasks(c) if t['id'] == task_id)['focus']
        agent.family_task_focus.save(self.app, dict(id=task_id, version=focus['version'], request_key='synthetic-same-late-edit', mode='waiting',
            next_action='家长刚改的安排', waiting_for='等虚构家长', review_on='2026-02-11', scheduled_on='2026-02-11', box='inbox'))
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            stale = dict(c.execute('SELECT * FROM agent_items WHERE id=?', (row['id'],)).fetchone())
            self.assertEqual(stale['state'], 'pending'); self.assertFalse(stale['task_id'])
            self.assertEqual(json.loads(stale['plan'])['school_task']['state'], 'review')
            self.assertEqual(next(t for t in self.app.tasks(c) if t['id'] == task_id)['focus']['next_action'], '家长刚改的安排')
            self.assertEqual(len(self._child_tasks(c)), 1)

    def test_s04_literal_exercise_ranges_are_not_the_same_affair(self):
        # The contract's literal texts against the program guard (the mocked batch path needs native-anchored quotes for 练习).
        target = dict(id='T1', title='数学：练习二', goal='练习二第1、2题，今晚完成。', due='2026-02-10', status='待跟进', targets_complete=True,
                      append_basis=dict(canonical_id='A1', due='2026-02-10'))
        for text, state in (('练习二第4题，今晚完成。', 'review'), ('别忘了练习二第1、2题今晚完成。', 'ready')):
            brief = dict(change='same', target_id='T1', state='ready', purpose='learning', title='数学：练习二', goal=text, reason='')
            agent._school_same_brief(brief, [dict(ref='message:synthetic-group:31', kind='text', text=text, time=self.now.isoformat())], [target])
            self.assertEqual(brief['state'], state, text)

    def test_s04_independent_ranges_of_the_same_reading_stay_two_tasks(self):
        math = dict(title='英语：Unit 3朗读', subject='英语', source='synthetic-group', platform='wechat')
        original, task_id = self._original(31, 'Unit 3课文第1、2段读两遍，明天完成。', due='2026-02-11', goal='Unit 3课文第1、2段读两遍，明天完成。', **math)
        forged = self._candidate(32, 'Unit 3课文第4段读两遍，明天完成。', publisher='synthetic-teacher-b', change='same', target=task_id, due='2026-02-11',
                                 goal='Unit 3课文第4段读两遍，明天完成。', **math)
        brief = json.loads(forged['plan'])['school_task']
        self.assertEqual(brief['state'], 'review'); self.assertNotIn('target_basis', brief)
        self.assertEqual(self._refresh()['created'], 0)
        separate = self._candidate(33, 'Unit 3课文第4段读两遍，明天完成。', publisher='synthetic-teacher-b', due='2026-02-11', goal='Unit 3课文第4段读两遍，明天完成。', **math)
        self.assertEqual(self._refresh()['created'], 1)
        with self.app.connect() as c:
            tasks = self._child_tasks(c)
            self.assertEqual(len(tasks), 2)
            self.assertEqual(next(t for t in tasks if t['id'] == task_id)['action'], original['body'])
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?', (forged['id'],)).fetchone()[0], 'pending')
            self.assertNotEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?', (separate['id'],)).fetchone()[0], task_id)

    def test_s04_same_unit_or_title_with_another_object_or_count_is_not_the_same_affair(self):
        original, task_id = self._original()
        for index, text in ((41, '提醒一下，明天要交Unit 4朗读录音，课文读两遍再上传。'), (42, '提醒一下，明天要交Unit 3朗读录音，课文读三遍再上传。'),
                            (43, '更正：Unit 3朗读录音改为后天交。'), (44, '提醒一下，明天交Unit 3朗读录音，另外完成练习卷第1题。')):
            brief = json.loads(self._candidate(index, text, change='same', target=task_id, due='2026-02-11')['plan'])['school_task']
            self.assertEqual(brief['state'], 'review', text); self.assertNotIn('target_basis', brief)

    def test_s05_identical_text_for_another_child_never_links(self):
        original, task_id = self._original()
        sibling = dict(source='synthetic-sibling-group', child='child-2')
        with self.assertRaises(agent.AgentError):
            self._candidate(51, READING_WECHAT, change='same', target=task_id, due='2026-02-11', **sibling)
        own = self._candidate(52, READING_QQ, due='2026-02-11', **sibling)
        self.assertEqual(self._refresh()['created'], 1)
        with self.app.connect() as c:
            self.assertEqual([t['id'] for t in self._child_tasks(c)], [task_id])
            self.assertEqual(len(self._child_tasks(c, '示例乙')), 1)
            self.assertNotEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?', (own['id'],)).fetchone()[0], task_id)

    def test_s06_new_round_or_other_deadline_of_the_same_text_stays_separate(self):
        original, task_id = self._original()
        for index, text, due in ((61, '本周三重新布置同一课文Unit 3，下周五再交一次朗读录音。', '2026-02-20'),
                                 (62, '提醒：Unit 3朗读录音周五交。', '2026-02-13')):
            row = self._candidate(index, text, change='same', target=task_id, due=due)
            brief = json.loads(row['plan'])['school_task']
            self.assertEqual(brief['state'], 'review', text); self.assertNotIn('target_basis', brief)
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            self.assertEqual([t['id'] for t in self._child_tasks(c)], [task_id])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE state='pending'").fetchone()[0], 2)


    def test_discourse_labels_quoted_titles_equal_quantities_and_original_facts_keep_the_same_affair(self):
        original, task_id = self._original()
        for index, text in ((71, '补充提醒：Unit 3课文读两遍，朗读录音上传班级作业区，明天完成。'), (72, '温馨提醒：明天交Unit 3朗读录音，课文读2遍再上传。')):
            brief = json.loads(self._candidate(index, text, change='same', target=task_id, due='2026-02-11', goal=text)['plan'])['school_task']
            self.assertEqual((brief['state'], brief['change']), ('ready', 'same'), text + brief['reason'])
        for index, text in ((73, '补充：录音后在群里回复已上传。'), (74, '补充提醒：录音后在群里回复已上传。'), (75, '补充提醒：Unit 3课文读三遍。'),
                            (76, '再次提醒：下周五再交一次Unit 3朗读录音。'), (77, '补充提醒：另外完成练习卷第1题。')):
            brief = json.loads(self._candidate(index, text, change='same', target=task_id, due='2026-02-11')['plan'])['school_task']
            self.assertEqual(brief['state'], 'review', text); self.assertNotIn('target_basis', brief)
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            self.assertEqual([t['id'] for t in self._child_tasks(c)], [task_id])
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE task_id=? AND state='accepted'", (task_id,)).fetchone()[0], 3)

    def test_quoted_titles_ranges_and_facts_of_the_original_are_not_new_requirements(self):
        book = dict(title='语文：《不再孤单的小船》朗读', subject='语文', source='synthetic-group', platform='wechat')
        original, task_id = self._original(81, '《不再孤单的小船》第1-3段读两遍，明天完成。', goal='《不再孤单的小船》第1-3段读两遍，明天完成。', **book)
        brief = json.loads(self._candidate(82, '提醒：明天前把《不再孤单的小船》第1、2、3段读两遍。', change='same', target=task_id, due='2026-02-11',
                                           publisher='synthetic-teacher-b', source='synthetic-qq', platform='qq', title=book['title'], subject='语文')['plan'])['school_task']
        self.assertEqual(brief['state'], 'ready', brief['reason'])
        text = 'Unit 3课文读两遍，朗读录音约3分钟，上传班级作业区，明天完成。'
        original, reading = self._original(91, text, goal='Unit 3课文读两遍，录音上传班级作业区，明天完成。')
        brief = json.loads(self._candidate(92, '提醒：明天交Unit 3朗读录音，3分钟左右，课文读两遍。', change='same', target=reading, due='2026-02-11')['plan'])['school_task']
        self.assertEqual(brief['state'], 'ready', brief['reason'])

    def test_same_read_attachment_resent_with_a_reminder_stays_with_the_one_affair(self):
        import io
        original, task_id = self._original()
        def upload(data, name):
            saved = self.app.save_upload(io.BytesIO(data), len(data), name)
            return saved['id'] if isinstance(saved, dict) else saved
        sheet = b'%PDF-1.4 synthetic reading sheet'
        first, same, other = upload(sheet, 'synthetic-sheet.pdf'), upload(sheet, 'synthetic-sheet-again.pdf'), upload(b'%PDF-1.4 another', 'synthetic-other.pdf')
        with self.app.connect() as c: c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', ('synthetic-qq', '11', first))
        read = lambda store, c, source, message: {'read': True} if message.get('id') == '11' else None
        rows = {}
        for index, attached, receipt in ((12, same, read), (13, other, read), (14, same, lambda *a: None)):
            rows[index] = self._candidate(index, READING_WECHAT, change='same', target=task_id, due='2026-02-11')
            with self.app.connect() as c: c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', ('synthetic-group', str(index), attached))
            with patch.object(agent.family_media, 'school_evidence', side_effect=receipt), \
                 patch.object(agent.family_pdf_material, 'complete_evidence', return_value=None):
                self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            state = {i: dict(c.execute('SELECT state,task_id,plan FROM agent_items WHERE id=?', (r['id'],)).fetchone()) for i, r in rows.items()}
            self.assertEqual((state[12]['state'], state[12]['task_id']), ('accepted', task_id))
            for index in (13, 14):
                self.assertEqual(state[index]['state'], 'pending'); self.assertEqual(json.loads(state[index]['plan'])['school_task']['state'], 'review')
            self.assertEqual(len(self._child_tasks(c)), 1)
            kept = {(r['message_id'], r['upload_id']) for r in c.execute("SELECT * FROM agent_message_attachments WHERE source_id='synthetic-group'")}
            self.assertEqual(kept, {('12', same), ('13', other), ('14', same)})

    def _tick(self, reply=None, must=(), never=()):
        """One ordinary run_once; only the reconciliation call (must/never content) gets the reply, any other call fails."""
        calls = []
        def model(messages, schema, name, **kwargs):
            content = messages[-1]['content']
            matched = (reply is not None and name == 'family_agent_selection' and '独立行动补漏' not in messages[0]['content']
                       and all(m in content for m in must) and not any(n in content for n in never))
            calls.append('reconcile' if matched else name)
            if matched: return reply
            raise agent.AgentError('synthetic: no other model call')
        with patch.object(agent.family_llm, '_chat_json', side_effect=model), patch.object(agent, '_now', return_value=self.now):
            agent.run_once(self.app, now=self.now)
        self.assertLessEqual(len(calls), 3)
        return calls

    def _same_jobs(self):
        with self.app.connect() as c:
            return [dict(r) for r in c.execute("SELECT id,done FROM agent_jobs WHERE id LIKE 'school-same:%'")]

    def _school_rows(self, view):
        return [i for g in view['groups'] for i in g['items'] if i['origin'] == 'school'], [i for g in view['closed'] for i in g['items'] if i['origin'] == 'school']

    def test_s07_existing_duplicates_become_one_affair_on_the_normal_tick_with_feedback_ownership(self):
        receipt = dict(purpose='admin', subject='')
        first, keep = self._original(21, '周五交《春季研学回执》，家长签字。', source='synthetic-group', platform='wechat', due='2026-02-13',
                                     goal='周五交《春季研学回执》，家长签字。', title='班务：交《春季研学回执》', **receipt)
        text = '周五别忘交签好字的春季研学回执。'
        later = self._candidate(22, text, source='synthetic-qq', platform='qq', publisher='synthetic-head-teacher', due='2026-02-13',
                                goal='周五带来家长签字的春季研学回执。', title='班务：带来签好字的研学回执', **receipt)
        member = self.store.act(dict(id=later['id'], action='accept'))['task_id']
        self.assertNotEqual(member, keep)
        old = self.app.save_task_feedback(dict(task_id=member, child='示例甲', day='2026-02-10', note='虚构：回执已签好放进书包。', request_key='synthetic-s07-old'))
        with self.app.connect() as c: saved_old = dict(c.execute('SELECT * FROM records WHERE id=?', (old['record_id'],)).fetchone()); tasks_before = self._rows(c, 'manual_tasks')
        open_rows, _ = self._school_rows(self.app.day_view('child-1', '2026-02-10'))
        self.assertEqual(len(open_rows), 2)
        reply = dict(proposals=[school_proposal(title_quote=text, focus='school', due='2026-02-13', evidence=[dict(ref='message:synthetic-qq:22')], learning_subject='',
                                                task_title='班务：带来签好字的研学回执', task_goal='周五带来家长签字的春季研学回执。', task_state='ready',
                                                task_reason='虚构：同一份回执的再次提醒。', task_change='same', task_target_id=keep, task_purpose='admin')])
        # Fresh batches go first (here the fixture's never-batched messages fail and back off); a spare call then reconciles.
        ticks = [self._tick(reply, must=('message:synthetic-qq:22', keep), never=(member,)) for _ in range(3)]
        self.assertEqual(sum(t.count('reconcile') for t in ticks), 1)
        self.assertEqual(self._same_jobs(), [dict(id='school-same:' + later['id'], done=1)])
        view = self.app.day_view('child-1', '2026-02-10')
        open_rows, _ = self._school_rows(view)
        self.assertEqual([r['task_id'] for r in open_rows], [keep])
        row = open_rows[0]
        self.assertEqual(row['same_affair'], dict(state='grouped', task_ids=[keep, member]))
        self.assertEqual({p['ref'] for p in row['publications']}, {'message:synthetic-group:21', 'message:synthetic-qq:22'})
        self.assertEqual([(r['id'], r['task_id']) for r in row['records']], [(old['record_id'], member)])
        new = self.app.save_task_feedback(dict(task_id=keep, child='示例甲', day='2026-02-10', note='虚构：今天已交给老师。', request_key='synthetic-s07-new'))
        reopened, _ = self._school_rows(self.app.day_view('child-1', '2026-02-10'))
        self.assertEqual(len(reopened), 1)
        self.assertEqual(sorted((r['id'], r['task_id']) for r in reopened[0]['records']), sorted([(old['record_id'], member), (new['record_id'], keep)]))
        self.assertEqual(reopened[0]['progress'].get('feedback'), 2, reopened[0]['progress'])
        with self.app.connect() as c:
            self.assertEqual(dict(c.execute('SELECT * FROM records WHERE id=?', (old['record_id'],)).fetchone()), saved_old)
            self.assertEqual(self._rows(c, 'manual_tasks'), tasks_before)
            self.assertEqual(json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (later['id'],)).fetchone()[0])['school_same_task']['task_id'], keep)
        # The next ordinary tick does not ask again; a differing completion keeps both rows with the doubt stated.
        self.assertEqual(self._tick(reply, must=('message:synthetic-qq:22', keep), never=(member,)).count('reconcile'), 0)
        self.app.save_task(dict(id=member, status='已完成', note='虚构家长已核对。'))
        with self.app.connect() as c: member_update = dict(c.execute('SELECT * FROM task_updates WHERE id=?', (member,)).fetchone())
        for view in (self.app.day_view('child-1', '2026-02-10'), self.app.snapshot()['today_view']['child-1']):
            open_rows, closed_rows = self._school_rows(view)
            # One affair: the open earliest task with the member's records; the doubt is stated, completion is not inferred.
            self.assertEqual(([r['task_id'] for r in open_rows], closed_rows), ([keep], []))
            self.assertEqual(open_rows[0]['same_affair']['state'], 'uncertain'); self.assertIn('已完成', open_rows[0]['same_affair']['note'])
            self.assertEqual({(p['ref'], p['task_id']) for p in open_rows[0]['publications']}, {('message:synthetic-group:21', keep), ('message:synthetic-qq:22', member)})
            self.assertEqual(open_rows[0]['members'][0]['status'], '已完成')
        with self.app.connect() as c: self.assertEqual(dict(c.execute('SELECT * FROM task_updates WHERE id=?', (member,)).fetchone()), member_update)
        # The member's own original stays readable through the protected entry under its own task and child.
        out = self.store.message(dict(child_id='child-1', source_id='synthetic-qq', message_id='22', task_id=member), self.app.upload_info)
        self.assertIn(text, json.dumps(out, ensure_ascii=False))

    def test_equivalent_counts_and_a_compatible_addendum_stay_with_the_one_affair(self):
        photo = dict(title='语文：观察日记', subject='语文', source='synthetic-group', platform='wechat')
        original, task_id = self._original(101, '观察日记配两张照片，明天交。', goal='观察日记配两张照片，明天交。', **photo)
        same = json.loads(self._candidate(102, '提醒：观察日记配2张照片，明天交。', change='same', target=task_id, due='2026-02-11',
                                          publisher='synthetic-teacher-b', **photo)['plan'])['school_task']
        self.assertEqual(same['state'], 'ready', same['reason'])
        original, reading = self._original(103)
        added = self._candidate(104, '提醒：明天交Unit 3朗读录音，上传后请家长在群里回复已上传。', change='same', target=reading, due='2026-02-11')
        brief = json.loads(added['plan'])['school_task']
        # A clear extra step of the same affair is a supplement awaiting confirmation on that very task, never a new affair.
        self.assertEqual((brief['change'], brief['state'], brief['target_id']), ('append', 'review', reading))
        self.assertIn('回复已上传', added['body'])
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            self.assertEqual(len([t for t in self._child_tasks(c) if t['id'] == reading]), 1)
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?', (added['id'],)).fetchone()[0], 'pending')

    def test_s07_undated_saved_tasks_with_a_shared_word_are_not_offered(self):
        observe = dict(title='科学：观察', subject='科学', source='synthetic-group', platform='wechat', due='')
        self._original(111, '观察家里的一种植物，在观察本上写三句话。', **observe)
        self._original(112, '今天：观察本上画一种植物。', **observe)
        for _ in range(2): self._tick()
        self.assertEqual(self._same_jobs(), [])

    def _unrelated(self, count, start=200):
        for i in range(count):
            text = f'第{i + 1}号植物卡片涂色。'
            self._original(start + i, text, title=f'科学：植物卡片{i + 1}', subject='科学', source='synthetic-group', platform='wechat', goal=text)

    def test_window_fresh_reminder_finds_an_original_older_than_24_unrelated_tasks(self):
        original, task_id = self._original()
        self._unrelated(24)
        latest = agent.school_targets(self.app, self.store, 'child-1')
        self.assertNotIn(task_id, [t['id'] for t in latest]); self.assertFalse(latest[0]['targets_complete'])
        scoped = agent.school_targets(self.app, self.store, 'child-1', evidence=[READING_WECHAT])
        self.assertEqual(len(scoped), 24); self.assertIn(task_id, [t['id'] for t in scoped])
        self.assertTrue(scoped[0]['same_complete']); self.assertFalse(scoped[0]['targets_complete'])
        row = self._reading_reminder(task_id)
        self.assertEqual(json.loads(row['plan'])['school_task']['state'], 'ready')
        self.assertEqual(self._refresh()['created'], 0)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?', (row['id'],)).fetchone()[0], task_id)
            self.assertEqual(len(self._child_tasks(c)), 25)
        # Append keeps the whole-list completeness: a supplement to the same old task is not auto-applied past the window.
        added = self._candidate(13, '只补朗读：录音上传后确认上传成功。', change='append', target=task_id)
        self.assertEqual(json.loads(added['plan'])['school_task']['state'], 'review')

    def test_window_root_case_24_similar_unit_readings_scope_by_named_object(self):
        original, task_id = self._original()
        for n in range(10, 34):
            text = f'Unit {n}课文读两遍，朗读录音上传班级作业区，明天完成。'
            self._original(100 + n, text, source='synthetic-window-other', title=f'英语：Unit {n}朗读', goal=text)
        scoped = agent.school_targets(self.app, self.store, 'child-1', evidence=[READING_WECHAT])
        self.assertEqual((task_id in [t['id'] for t in scoped], scoped[0]['same_complete'], len(scoped)), (True, True, 24))
        row = self._candidate(55, READING_WECHAT, source='synthetic-window-reminder', change='same', target=task_id, due='2026-02-11', title='英语：Unit 3朗读')
        self.assertEqual(json.loads(row['plan'])['school_task']['state'], 'ready')

    def test_two_saved_tasks_fitting_the_same_reminder_on_one_date_stay_for_the_parent(self):
        first, one = self._original()
        second, two = self._original(12, READING_QQ.replace('明天完成', '明天完成，第二次布置'), source='synthetic-group', platform='wechat')
        brief = json.loads(self._candidate(13, READING_WECHAT, change='same', target=one, due='2026-02-11')['plan'])['school_task']
        self.assertEqual(brief['state'], 'review'); self.assertNotIn('target_basis', brief)

    def test_window_already_saved_repeat_older_than_24_unrelated_tasks_is_grouped(self):
        first, keep = self._original()
        self._unrelated(24)
        later = self._candidate(22, READING_WECHAT, source='synthetic-group', due='2026-02-11', title='英语：交Unit 3朗读录音', goal=READING_WECHAT)
        member = self.store.act(dict(id=later['id'], action='accept'))['task_id']
        reply = dict(proposals=[school_proposal(title_quote=READING_WECHAT, focus='school', due='2026-02-11', evidence=[dict(ref='message:synthetic-group:22')],
                                                learning_subject='英语', task_title='英语：交Unit 3朗读录音', task_goal=READING_WECHAT, task_state='ready',
                                                task_reason='虚构：同一朗读录音的再次提醒。', task_change='same', task_target_id=keep, task_purpose='learning')])
        ticks = [self._tick(reply, must=('message:synthetic-group:22', keep), never=(member,)) for _ in range(3)]
        self.assertEqual(sum(t.count('reconcile') for t in ticks), 1)
        with self.app.connect() as c:
            self.assertEqual(json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (later['id'],)).fetchone()[0])['school_same_task']['task_id'], keep)
        rows, _ = self._school_rows(self.app.day_view('child-1', '2026-02-10'))
        reading = [r for r in rows if r['task_id'] in (keep, member)]
        self.assertEqual([r['task_id'] for r in reading], [keep])

    def _grouped_with_files(self, read_ids):
        import io
        def upload(data, name):
            saved = self.app.save_upload(io.BytesIO(data), len(data), name)
            return saved['id'] if isinstance(saved, dict) else saved
        first, keep = self._original()
        later = self._candidate(22, READING_WECHAT, source='synthetic-group', due='2026-02-11', title='英语：交Unit 3朗读录音', goal=READING_WECHAT)
        member = self.store.act(dict(id=later['id'], action='accept'))['task_id']
        own, other = upload(b'%PDF-1.4 synthetic unit 3 sheet', 'synthetic-unit3.pdf'), upload(b'%PDF-1.4 synthetic recording guide', 'synthetic-guide.pdf')
        with self.app.connect() as c:
            c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', ('synthetic-qq', '11', own))
            c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', ('synthetic-group', '22', other))
        reply = dict(proposals=[school_proposal(title_quote=READING_WECHAT, focus='school', due='2026-02-11', evidence=[dict(ref='message:synthetic-group:22')],
                                                learning_subject='英语', task_title='英语：交Unit 3朗读录音', task_goal=READING_WECHAT, task_state='ready',
                                                task_reason='虚构：同一朗读录音的再次提醒。', task_change='same', task_target_id=keep, task_purpose='learning')])
        read = lambda store, c, source, message: {'read': True} if message.get('id') in read_ids else None
        with patch.object(agent.family_media, 'school_evidence', side_effect=read), patch.object(agent.family_pdf_material, 'complete_evidence', return_value=None):
            ticks = [self._tick(reply, must=('message:synthetic-group:22', keep), never=(member,)) for _ in range(3)]
        return keep, member, later, own, other, sum(t.count('reconcile') for t in ticks)

    def test_grouped_affair_materials_keep_each_verified_members_read_original_and_owner(self):
        import io, family_print
        keep, member, later, own, other, calls = self._grouped_with_files({'11', '22'})
        self.assertEqual(calls, 1)
        sibling_row, sibling = self._original(32, READING_QQ, source='synthetic-sibling-group', child='child-2')
        foreign = self.app.save_upload(io.BytesIO(b'%PDF-1.4 synthetic sibling sheet'), 32, 'synthetic-sibling.pdf')
        foreign = foreign['id'] if isinstance(foreign, dict) else foreign
        with self.app.connect() as c:
            c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', ('synthetic-sibling-group', '32', foreign))
            plan = json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (sibling_row['id'],)).fetchone()[0]); plan['school_same_task'] = dict(task_id=keep)
            c.execute('UPDATE agent_items SET plan=? WHERE id=?', (json.dumps(plan, ensure_ascii=False), sibling_row['id']))
        # Only the existing original-action scope proof is stood in (harness items carry no saved anchors); every other
        # check (relation, child, message authorization, upload, prepare scope) is the product's own.
        with patch.object(agent, 'school_original_upload_ids', side_effect=lambda store, c, row, ref, ids: ids):
            with self.app.connect() as c:
                c.execute('BEGIN'); context = self.app.homework_material_context(c, keep)
            allowed = context['allowed']
            self.assertEqual(context['school_error'], '')
            self.assertEqual((allowed[own]['origin'], allowed[own].get('owner_task_id')), ('school', None))
            self.assertEqual((allowed[other]['origin'], allowed[other]['owner_task_id']), ('school', member))
            self.assertNotIn(foreign, allowed)
            self.app.homework_print_sources(dict(task_id=keep, question_sources=[dict(type='upload', id=other)]))
            with self.assertRaises(family_print.PrintError): self.app.homework_print_sources(dict(task_id=keep, question_sources=[dict(type='upload', id=foreign)]))
            with self.app.connect() as c:
                plan = json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (later['id'],)).fetchone()[0]); plan.pop('school_same_task')
                c.execute('UPDATE agent_items SET plan=? WHERE id=?', (json.dumps(plan, ensure_ascii=False), later['id']))
            with self.assertRaises(family_print.PrintError): self.app.homework_print_sources(dict(task_id=keep, question_sources=[dict(type='upload', id=other)]))
        with self.app.connect() as c:
            self.assertEqual({r['upload_id'] for r in c.execute('SELECT upload_id FROM agent_message_attachments')}, {own, other, foreign})

    def test_saved_repeat_with_an_unread_different_file_is_not_grouped(self):
        keep, member, later, own, other, calls = self._grouped_with_files({'11'})
        self.assertEqual((calls, self._same_jobs()), (0, []))
        rows, _ = self._school_rows(self.app.day_view('child-1', '2026-02-10'))
        self.assertEqual(sorted(r['task_id'] for r in rows), sorted([keep, member]))

    def test_s07_unrelated_or_other_child_tasks_are_not_offered_to_the_model(self):
        first, keep = self._original()
        self._original(31, 'Unit 4课文读一遍，明天完成。', title='英语：Unit 4朗读')
        self._original(32, READING_QQ, source='synthetic-sibling-group', child='child-2')
        for _ in range(3): self._tick()
        self.assertEqual(self._same_jobs(), [])


if __name__ == '__main__':
    unittest.main()

"""Fictional regressions: a fold's later original stays visible for all four changes and its day wins.

The program folds a proved later notice into the waiting card or the saved task instead of opening an orphan card. These
tests keep that fold from hiding its own text: every line of the later original stays in order (a correction may state
its new range on one line and its new day on the next), the labelled replacement and the ground of a cancellation stay
readable, a moved day counts with or without a hand-back verb, and the later message stays readable in the task's
sources by the same note convention on both the pending-card and the saved-task path (never a cited message line, which
the agenda would read as one of the affair's own day-role messages).
"""
import datetime as dt
import json
import sqlite3
import unittest
from unittest import mock

import family_agent as agent

NOW = dt.datetime(2026, 11, 4, 20, 0, tzinfo=agent.TZ)


class _DB:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *error):
        return False


class _Store:
    """A store shim with only the read/write surface the fold helpers touch."""

    def __init__(self, connection):
        self.connection = connection

    def _db(self):
        return _DB(self.connection)


def quote(ref, text, time, change='same'):
    return dict(ref=ref, text=text, time=time, sender='数学李老师', publisher='publisher:fiction-math',
                kind='text', content_incomplete=False, attachments=[], related_messages=[ref], source='虚构班级')


def folded(change, ref='message:fiction-group:9', text='数学《星河练习》第12页第1—3题，今晚完成。'):
    return dict(item_id='agent-card', refs=[ref], change=change, at=NOW.isoformat(),
                originals=[dict(ref=ref, text=text, time='2026-11-04T17:00:00+08:00')])


class FoldedLinesTest(unittest.TestCase):
    def test_reminder_moves_to_a_later_notice_not_the_body(self):
        # A same-fold reminder is a later notice, not another current requirement: its whole original is a follow-up line.
        lines = agent._school_folded_lines(dict(school_folded=[folded('same')]))
        self.assertEqual(lines, ['后到提醒原文（2026-11-04 17:00）：数学《星河练习》第12页第1—3题，今晚完成。'])
        import family_agenda
        parsed = family_agenda._follow_up(lines[0])
        self.assertEqual(parsed['label'], '提醒')
        self.assertEqual(parsed['time'], '2026-11-04 17:00')
        self.assertIn('数学《星河练习》第12页第1—3题，今晚完成。', parsed['text'])

    def test_appended_and_updated_lines_stay_labelled(self):
        appended = agent._school_folded_lines(dict(school_folded=[folded('append', text='交回时间不变。')]))
        self.assertIn('后到补充原文（2026-11-04 17:00）：交回时间不变。', appended)
        updated = agent._school_folded_lines(dict(school_folded=[folded('update', text='更正第12页范围：只做第1—3题，第4题不做。')]))
        self.assertTrue(any(line.startswith('后到更正原文（2026-11-04 17:00）：') and '第4题不做' in line for line in updated), updated)

    def test_every_line_of_a_multiline_correction_stays_in_order(self):
        text = '更正：数学《每日练习》第26页只做第1—3题。\n明天早上交回。'
        lines = agent._school_folded_lines(dict(school_folded=[folded('update', text=text)]))
        joined = '\n'.join(lines)
        self.assertIn('只做第1—3题', joined)
        self.assertIn('明天早上交回', joined)
        self.assertLess(joined.index('只做第1—3题'), joined.index('明天早上交回'))

    def test_every_line_of_a_multiline_cancellation_stays(self):
        text = '明天美术改用教室材料，刚才收集落叶那一项取消。\n不用带叶子和旧书。'
        lines = agent._school_folded_lines(dict(school_folded=[folded('cancel', text=text)]))
        joined = '\n'.join(lines)
        self.assertIn('取消', joined)
        self.assertIn('不用带叶子和旧书', joined)

    def test_cancellation_ground_stays_labelled(self):
        lines = agent._school_folded_lines(dict(school_folded=[folded('cancel', text='刚才带落叶那一项取消，不用带。')]))
        self.assertTrue(any(line.startswith('取消依据（2026-11-04 17:00）：') and '取消' in line for line in lines), lines)

    def test_a_correction_line_names_the_sending_moment(self):
        lines = agent._school_folded_lines(dict(school_folded=[folded('update', text='更正：只做第1—3题。')]))
        self.assertTrue(lines and all(line.startswith('后到更正原文（2026-11-04 17:00）：') for line in lines), lines)

    def test_an_unfolded_plan_adds_nothing(self):
        self.assertEqual(agent._school_folded_lines({}), [])

    def test_body_carries_every_change_after_the_first_lines(self):
        plan = dict(school_folded=[folded('update', text='第12页只做第1—3题，第4题不做。')])
        body = agent._school_folded_body(plan, '完成数学《星河练习》第12页。')
        self.assertEqual(body.split('\n')[0], '完成数学《星河练习》第12页。')
        self.assertTrue(any('第4题不做' in line for line in body.split('\n')))


class FoldedDueTest(unittest.TestCase):
    def test_an_update_states_its_own_new_day(self):
        originals = [dict(text='改为下周一交回。', time='2026-11-04T17:00:00+08:00')]
        self.assertEqual(agent._school_late_due(originals), '2026-11-09')

    def test_a_reminder_keeping_the_day_states_the_same_day(self):
        originals = [dict(text='数学《星河练习》今晚完成，周五交给我。', time='2026-11-04T16:00:00+08:00')]
        self.assertEqual(agent._school_late_due(originals), '2026-11-06')

    def test_a_moved_day_counts_without_a_hand_back_verb(self):
        for text in ('改到11月10日交。', '推迟到11月10日交。', '改为11月10日交。', '改到11月10日。'):
            originals = [dict(text=text, time='2026-11-04T17:00:00+08:00')]
            self.assertEqual(agent._school_late_due(originals), '2026-11-10', text)

    def test_no_stated_day_returns_nothing(self):
        self.assertEqual(agent._school_late_due([dict(text='第12页范围不变。', time='2026-11-04T17:00:00+08:00')]), '')

    def test_a_plain_completion_day_is_never_a_new_deadline(self):
        self.assertEqual(agent._school_late_due([dict(text='今晚完成。', time='2026-11-04T17:00:00+08:00')]), '')


class FoldPendingTest(unittest.TestCase):
    """The waiting card keeps one identity: its body shows the later original and its due follows the change."""

    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('CREATE TABLE agent_items(id TEXT PRIMARY KEY, job_id TEXT, child_id TEXT, kind TEXT, '
                                'title TEXT, body TEXT, evidence TEXT, due TEXT, created TEXT, updated TEXT, '
                                'state TEXT, task_id TEXT, plan TEXT)')
        self.store = _Store(self.connection)

    def tearDown(self):
        self.connection.close()

    def save_card(self, body, due, plan):
        self.connection.execute("INSERT INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,created,updated,state,task_id,plan)"
                                " VALUES('agent-card','job','child-1','school','待核对：数学','%s','[]','%s','%s','%s','pending','','%s')"
                                % (body, due, NOW.isoformat(), NOW.isoformat(), json.dumps(plan)))
        self.connection.commit()
        return self.connection.execute("SELECT * FROM agent_items WHERE id='agent-card'").fetchone()

    def fold(self, change, incoming_body='数学《每日练习》第26页只做第1—3题，第4题不做，今晚完成。'):
        row = self.save_card('完成数学《每日练习》第26页。', '2026-11-06', dict(school_task=dict(state='review', goal='完成数学《每日练习》第26页。')))
        item = dict(child_id='child-1', body=incoming_body, due='2026-11-06',
                    evidence=[quote('message:fiction-wx:9', incoming_body, '2026-11-04T16:00:00+08:00')])
        ok = agent.Store._school_fold_pending(self.store, self.connection, item,
                                              dict(item_id='agent-card', change=change), NOW)
        self.assertTrue(ok)
        return self.connection.execute("SELECT * FROM agent_items WHERE id='agent-card'").fetchone()

    def test_a_replacement_joins_the_body_and_keeps_its_day(self):
        row = self.fold('update')
        self.assertIn('第4题不做', row['body'])
        self.assertEqual(row['due'], '2026-11-06')

    def test_a_multiline_replacement_keeps_both_the_range_and_the_new_day(self):
        row = self.fold('update', '更正：数学《每日练习》第26页只做第1—3题。\n明天早上交回。')
        self.assertIn('只做第1—3题', row['body'])
        self.assertIn('明天早上交回', row['body'])
        self.assertEqual(row['due'], '2026-11-05')

    def test_a_cancellation_shows_its_ground_and_clears_the_day(self):
        row = self.fold('cancel', '刚才带两片落叶那一项取消，不用带叶子和旧书。')
        self.assertIn('取消依据（2026-11-04 16:00）：', row['body'])
        self.assertIn('不用带叶子和旧书', row['body'])
        self.assertEqual(row['due'], '')

    def test_a_notice_older_than_the_adopted_correction_is_not_called_a_correction(self):
        # m04 arrived at 20:00 but was sent 16:00, before m09 (17:00) that already changed the range: it repeats the older
        # wording, so the card must read it as an earlier reminder, never as the correction of "第1—4题" beside "第1—3题".
        self.connection.execute('CREATE TABLE agent_messages(source_id TEXT, id TEXT, payload TEXT)')
        for source_id, message_id, when, text in (
                ('fiction-qq', '1', '2026-11-04T15:40:00+08:00', '数学《每日练习》第26页第1—4题，今晚完成。'),
                ('fiction-qq', '9', '2026-11-04T17:00:00+08:00', '更正：第26页只做第1—3题，第4题不做。')):
            self.connection.execute('INSERT INTO agent_messages VALUES(?,?,?)',
                                    (source_id, message_id, json.dumps(dict(time=when, text=text), ensure_ascii=False)))
        self.connection.commit()
        plan = dict(school_task=dict(state='ready', goal='完成数学《每日练习》第26页第1—3题。'),
                    school_messages=[dict(source_id='fiction-qq', message_id='1'),
                                     dict(source_id='fiction-qq', message_id='9')])
        self.save_card('完成数学《每日练习》第26页第1—3题，第4题不做。', '2026-11-06', plan)
        item = dict(child_id='child-1', body='完成数学《每日练习》第26页1—4题，今晚做并签字，周五交。',
                    due='2026-11-06',
                    evidence=[quote('message:fiction-wx:4', '再提醒今天那份数学《每日练习》：第26页1—4题，今晚做、签字，周五交。',
                                    '2026-11-04T16:00:00+08:00')])
        ok = agent.Store._school_fold_pending(self.store, self.connection, item,
                                              dict(item_id='agent-card', change='update'), NOW)
        self.assertTrue(ok)
        row = self.connection.execute("SELECT * FROM agent_items WHERE id='agent-card'").fetchone()
        self.assertIn('先前提醒（2026-11-04 16:00）：', row['body'])
        self.assertIn('第26页1—4题', row['body'])
        self.assertNotIn('后到更正原文', row['body'])
        self.assertEqual(row['due'], '2026-11-06')
        plan = json.loads(row['plan'])
        self.assertEqual(plan['school_folded'][-1]['change'], 'earlier')
        lines = [line for line in row['body'].split('\n') if '先前提醒' in line]
        self.assertEqual(len(lines), 1)
        # A string assertion is not enough: the projection must parse this line as one follow-up (label + time), or it stays
        # in the card's own body and the old "1—4题" wording still reads beside "1—3题".
        import family_agenda
        parsed = family_agenda._follow_up(lines[0])
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['label'], '先前提醒')
        self.assertEqual(parsed['time'], '2026-11-04 16:00')
        self.assertIn('第26页1—4题', parsed['text'])

    def test_a_plain_reminder_keeps_one_body_and_its_day(self):
        row = self.fold('same')
        # The reminder's words read as its own later notice; the card body keeps the requirement in force only.
        self.assertIn('后到提醒原文（2026-11-04 16:00）：', row['body'])
        self.assertIn('今晚完成', row['body'])
        self.assertEqual(row['due'], '2026-11-06')


class FoldAcceptTest(unittest.TestCase):
    """Accepting a card writes the folded lines into the task's action and the later message into its sources."""

    def setUp(self):
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('CREATE TABLE agent_items(id TEXT PRIMARY KEY, task_id TEXT)')
        self.connection.execute('CREATE TABLE manual_tasks(id TEXT PRIMARY KEY, action TEXT, source TEXT, due TEXT)')
        self.connection.execute("INSERT INTO agent_items(id,task_id) VALUES('agent-card','TASK-1')")
        self.connection.execute("INSERT INTO manual_tasks(id,action,source,due) VALUES('TASK-1','完成数学《每日练习》。',"
                                "'Agent建议:agent-card\\nmessage:fiction-qq:1\\n完成数学《每日练习》。','2026-11-06')")
        self.connection.commit()
        self.store = _Store(self.connection)

    def tearDown(self):
        self.connection.close()

    def plan_for(self, change, text):
        return dict(school_folded=[dict(refs=['message:fiction-wx:9'], change=change, at=NOW.isoformat(),
                                        originals=[dict(ref='message:fiction-wx:9', text=text,
                                                        time='2026-11-04T16:00:00+08:00')])])

    def test_action_source_and_day_after_acceptance(self):
        plan = self.plan_for('update', '数学《每日练习》第26页只做第1—3题，第4题不做。')
        agent._school_accept_fold(self.store, dict(id='agent-card'), plan)
        task = self.connection.execute("SELECT * FROM manual_tasks WHERE id='TASK-1'").fetchone()
        self.assertIn('第4题不做', task['action'])
        self.assertIn('后到原文', task['source'])
        self.assertIn('2026-11-04 16:00', task['source'])
        self.assertIn('只做第1—3题', task['source'])
        # A replacement is a readable note, never a cited message line: the agenda must not read the old range as a day role.
        self.assertNotIn('\nmessage:fiction-wx:9', '\n' + task['source'])

    def test_a_reminder_is_still_cited_as_a_message(self):
        plan = self.plan_for('same', '数学《每日练习》第26页1—3题，今晚做，周五交。')
        agent._school_accept_fold(self.store, dict(id='agent-card'), plan)
        task = self.connection.execute("SELECT * FROM manual_tasks WHERE id='TASK-1'").fetchone()
        self.assertIn('message:fiction-wx:9', task['source'])

    def test_the_note_carries_words_and_time_on_both_paths(self):
        note = agent._school_fold_note(('message:fiction-wx:9', '只做第1—3题，第4题不做。', 'update',
                                        '2026-11-04T16:00:00+08:00'))
        self.assertTrue(note.startswith(agent._SCHOOL_FOLD_NOTE))
        self.assertIn('2026-11-04 16:00', note)
        self.assertIn('只做第1—3题', note)
        self.assertFalse(note.startswith('message:'))

    def test_a_second_acceptance_does_not_duplicate_lines(self):
        plan = dict(school_folded=[folded('same')])
        agent._school_accept_fold(self.store, dict(id='agent-card'), plan)
        once = self.connection.execute("SELECT action,source FROM manual_tasks WHERE id='TASK-1'").fetchone()
        agent._school_accept_fold(self.store, dict(id='agent-card'), plan)
        twice = self.connection.execute("SELECT action,source FROM manual_tasks WHERE id='TASK-1'").fetchone()
        self.assertEqual(once['action'], twice['action'])
        self.assertEqual(once['source'], twice['source'])


class DocumentOriginalWaitTest(unittest.TestCase):
    """A document original's requirements are never dropped because the card was accepted before they were read.

    The page worker reads PDF/OOXML originals in the background. If the notice is accepted first, the free summary
    becomes a complete task without the attachment's executable requirements. These tests hold the acceptance while
    the reading can still arrive, release it with a readable material gap when the worker gave up, and prove an
    already merged original action is not read, waited for or duplicated a second time.
    """

    def setUp(self):
        import io
        import urllib.parse
        from test_agent import AgentTests
        self.fixture = AgentTests(methodName='runTest')
        self.fixture.setUp()
        self.app = self.fixture.app
        self.store = self.fixture.store
        self.source = self.fixture.source
        self.mid = 'race-1'
        stamp = '2026-11-04T16:05:00+08:00'
        self.store.ingest(dict(source_id=self.source['id'], expected_cursor='10', cursor='11', checked_at=stamp,
                               last_message_time=stamp, error='',
                               messages=[dict(id=self.mid, time=stamp, kind='text', sender='英语唐老师',
                                              sender_id='fiction-english', unread=False, message_order='1',
                                              text='英语《每日练习》见今天这份附件，今晚完成，做完放进英语夹里，明天带来。')]))
        import test_pdf
        raw = test_pdf.build_pdf(1)
        upload = self.app.save_upload(io.BytesIO(raw), len(raw), urllib.parse.quote('英语每日练习.pdf'))
        self.store.message_attachment(dict(child_id='child-1', source_id=self.source['id'], message_id=self.mid,
                                           attachment_id=upload['id'], action='attach'), self.app.upload_info)
        self.upload_id = upload['id']
        self.ref = 'message:' + self.source['id'] + ':' + self.mid

    def tearDown(self):
        self.fixture.doCleanups()

    def item(self, plan=None):
        brief = dict(policy=agent.SCHOOL_TASK_POLICY, state='ready', change='new', purpose='homework',
                     title='英语《每日练习》', goal='今晚完成英语《每日练习》。\n做完放进英语夹里，明天带来。',
                     reason='虚构：候选已是可直接保存的完整要求。')
        stamp = NOW.isoformat()
        evidence = [dict(ref=self.ref, time='2026-11-04T16:05:00+08:00', unread=False, kind='text',
                         text='英语《每日练习》见今天这份附件，今晚完成，做完放进英语夹里，明天带来。',
                         publisher='publisher:fiction-english', sender='英语唐老师')]
        with self.store._db() as c:
            c.execute("INSERT OR REPLACE INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,created,updated,plan,task_id) "
                      "VALUES('agent-race','messages:race','child-1','school','英语《每日练习》',?,?, '2026-11-04',?,?,?, '')",
                      ('今晚完成英语《每日练习》。\n做完放进英语夹里，明天带来。', json.dumps(evidence), stamp, stamp,
                       json.dumps(plan or {'school_task': brief})))
            return dict(c.execute("SELECT * FROM agent_items WHERE id='agent-race'").fetchone())

    def load(self):
        with self.store._db() as c:
            return dict(c.execute("SELECT * FROM agent_items WHERE id='agent-race'").fetchone())

    def tasks(self):
        with self.store._db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]

    def test_accept_waits_while_the_document_original_is_not_read_yet(self):
        row = self.item()
        created, failed = agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
        self.assertEqual((created, failed), (0, 0))
        with self.store._db() as c:
            saved = dict(c.execute("SELECT * FROM agent_items WHERE id='agent-race'").fetchone())
        plan = json.loads(saved['plan'])
        self.assertEqual(saved['state'], 'pending')
        self.assertEqual(plan['school_task']['state'], 'review')
        self.assertIn('原件（附件）尚未整理完成', plan['school_task']['reason'])
        self.assertEqual(plan['school_document_wait']['ticks'], 1)
        self.assertEqual(self.tasks(), [])

    def test_a_given_up_original_is_accepted_with_one_readable_gap(self):
        row = self.item()
        for _ in range(agent._SCHOOL_DOCUMENT_WAIT_TICKS):
            agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
            row = self.load()
        with self.store._db() as c:
            job_key = agent.family_pdf_material.job_key(dict(id=self.source['id']), dict(id=self.mid))
            c.execute("INSERT OR REPLACE INTO agent_jobs(id,fingerprint,attempts,next_try,error,done) "
                      "VALUES(?,?,3,'','页组整理未成功',1)", (job_key, 'gave-up'))
        row = self.load()
        agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
        saved = self.tasks()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['action'].count('内容待补：附件原件尚未读取'), 1)
        self.assertIn('英语每日练习.pdf', saved[0]['action'])

    def test_a_read_original_action_is_not_waited_for_or_duplicated(self):
        merged = ['一、看图选词第1—3题。', '二、标星单词 under、near 各抄写一遍。', '不需要录音。']
        brief = dict(policy=agent.SCHOOL_TASK_POLICY, state='ready', change='new', purpose='homework',
                     title='英语《每日练习》', goal='英语《每日练习》见今天这份附件，今晚完成。\n' + '\n'.join(merged))
        plan = {'school_task': dict(brief, goal='英语《每日练习》见今天这份附件，今晚完成。\n' + '\n'.join(merged)),
                'school_original_action': dict(requirements=[dict(text=t, ref=self.ref) for t in merged],
                                                                     anchors=[dict(ref=self.ref, quote='英语《每日练习》见今天这份附件，今晚完成。', upload_ids=[self.upload_id])])}
        plan = dict(plan, school_original_action=dict(plan['school_original_action'], requirements=plan['school_original_action']['requirements']))
        row = self.item(plan)
        with self.store._db() as c:
            c.execute("UPDATE agent_items SET body=? WHERE id='agent-race'", (plan['school_task']['goal'],))
        row = self.load()
        with self.store._db() as c:
            self.assertIsNone(agent._school_document_wait(self.store, row, json.loads(row['evidence'])))
        agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
        saved = self.tasks()
        self.assertEqual(len(saved), 1)
        for text in merged:
            self.assertEqual(saved[0]['action'].count(text), 1)

    def test_a_manual_accept_while_the_original_is_unread_is_refused(self):
        row = self.item()
        agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
        row = self.load()
        with self.assertRaises(agent.AgentError) as caught:
            self.store.act(dict(id='agent-race', action='accept', expected_updated=row['updated']))
        self.assertEqual((caught.exception.status, caught.exception.code), (409, 'school_document_unread'))
        saved = self.load()
        self.assertEqual(saved['state'], 'pending')
        self.assertIn('school_document_wait', json.loads(saved['plan']))
        self.assertEqual(self.tasks(), [])

    def test_the_release_path_accepts_while_the_worker_keeps_running(self):
        row = self.item()
        job_key = agent.family_pdf_material.job_key(dict(id=self.source['id']), dict(id=self.mid))
        with self.store._db() as c:
            c.execute("INSERT OR REPLACE INTO agent_jobs(id,fingerprint,attempts,next_try,error,done) VALUES(?,?,1,'','',0)", (job_key, 'running'))
        for _ in range(agent._SCHOOL_DOCUMENT_WAIT_TICKS):
            agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
            row = self.load()
            self.assertEqual(row['state'], 'pending')
        agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
        saved = self.tasks()
        self.assertEqual(len(saved), 1)
        plan = json.loads(self.load()['plan'])
        self.assertNotIn('school_document_wait', plan)
        self.assertIn('school_document_gap', plan)
        self.assertEqual(saved[0]['action'].count('内容待补：附件原件尚未读取'), 1)
        self.assertEqual(self.load()['state'], 'accepted')

    def test_a_late_original_requirement_joins_the_released_task_once(self):
        requirement_lines = ['一、看图选词第1—3题。', '二、标星单词 under、near 各抄写一遍。', '不需要录音。']
        row = self.item()
        for _ in range(agent._SCHOOL_DOCUMENT_WAIT_TICKS):
            agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
            row = self.load()
        agent._accept_school_reading(self.app, self.store, row, json.loads(row['evidence']), NOW)
        self.assertEqual(len(self.tasks()), 1)
        material = [dict(ref=self.ref, fingerprint='fictional-read-later', name='英语每日练习.pdf',
                         upload_id=self.upload_id, original='pdf', mime='application/pdf', conversion=None,
                         page_count=1, batches=[dict(pages=[1], updated='2026-11-04T20:07:00+08:00', draft=dict(
                             title='英语《每日练习》', note='老师写明的英语练习要求，未见孩子作答。', uncertainties=[],
                             originals=[dict(upload_id=self.upload_id, title='英语《每日练习》', note='', uncertainties=[],
                                             requirements=requirement_lines, deferred_contexts=[])]) )])]
        with mock.patch.object(agent, '_school_pdf', return_value=material):
            self.assertEqual(agent._school_document_late(self.store, NOW), 1)
            self.assertEqual(agent._school_document_late(self.store, NOW), 0)
        saved = self.tasks()
        self.assertEqual(len(saved), 1)
        for text in requirement_lines:
            self.assertEqual(saved[0]['action'].count(text), 1)
        self.assertNotIn('内容待补：附件原件尚未读取', saved[0]['action'])
        self.assertEqual(self.load()['state'], 'accepted')

    def test_an_image_attachment_is_not_a_document_wait(self):
        import io
        import urllib.parse
        raw = b'\xff\xd8\xff\xe0' + b'fictional-jpeg' + b'\xff\xd9'
        upload = self.app.save_upload(io.BytesIO(raw), len(raw), urllib.parse.quote('识字小卡.jpg'),
                                      )
        with self.store._db() as c:
            files = agent._school_document_files(c, dict(evidence=json.dumps([dict(ref=self.ref)])))
        self.assertEqual([f['upload_id'] for f in files], [self.upload_id])


if __name__ == '__main__':
    unittest.main()

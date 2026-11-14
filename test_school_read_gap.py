"""Fictional regressions: a school-message batch that never got a model answer is retried, visible and never duplicated.

The selection model can fail without finishing its answer (timeout or a truncated reply). The old job table stopped at
three attempts and left the originals unprocessed forever, so the day list silently lacked them. These tests hold the
whole loop: the permanent gap is written to the source the read-gap view already counts (with source, message ids,
attempt count, cause and the next retry), the next retry runs after the schedule and saves once, a cleared gap
disappears, and a content-level refusal keeps the original three-attempt limit and its next_try='' hand-over.
"""
import datetime as dt
import json
import unittest
from unittest.mock import patch

import family_agent as agent

NOW = dt.datetime(2026, 11, 4, 20, 0, tzinfo=agent.TZ)
TEXT = '今晚朗读《风经过小巷》第2、3自然段各两遍，明早抽听。'


def reply(ref):
    return dict(proposals=[dict(title_quote=TEXT, focus='school', due='', evidence=[dict(ref=ref)],
                                learning_subject='语文', learning_goal_id='', task_title='语文：朗读《风经过小巷》第2、3自然段',
                                task_goal='朗读《风经过小巷》第2、3自然段各两遍。', task_advice='', task_state='ready',
                                task_reason='虚构固定回执：老师明确要求今晚朗读。', task_change='new', task_target_id='',
                                task_purpose='learning', task_submission='')])


BRIEF = dict(title='语文：朗读《风经过小巷》第2、3自然段', goal='朗读《风经过小巷》第2、3自然段各两遍。', advice='', state='ready',
             reason='虚构固定回执。', purpose='learning', submission='', change='new', target_id='',
             learning_subject='语文', learning_goal_id='')


class SchoolReadGapTests(unittest.TestCase):
    """A fictional class group with one unprocessed message; no real model, source or private data."""

    def setUp(self):
        from test_agent import AgentTests
        self.fixture = AgentTests(methodName='runTest')
        self.fixture.setUp()
        self.app = self.fixture.app
        self.store = self.fixture.store
        self.source = self.fixture.source
        self.stamp = '2026-11-04T16:00:00+08:00'
        self.ref = 'message:' + self.source['id'] + ':gap-1'
        self.store.ingest(dict(source_id=self.source['id'], expected_cursor='10', cursor='11', checked_at=self.stamp,
                               last_message_time=self.stamp, error='',
                               messages=[dict(id='gap-1', time=self.stamp, kind='text', sender='语文林老师',
                                              sender_id='fiction-chinese', unread=False, message_order='1', text=TEXT)]))

    def tearDown(self):
        self.fixture.doCleanups()

    def round(self, at, model):
        with patch.object(agent.family_llm, '_chat_json', side_effect=lambda messages, schema, name, **kw: model(name)):
            return agent.run_once(self.app, at)

    def fixed(self, name):
        """One fictional model answer for both the selection and the school refresh."""
        if name == 'family_agent_selection': return reply(self.ref)
        return dict(BRIEF)

    def fails(self, name):
        if name == 'family_agent_selection': raise agent.family_llm.LLMDraftError('虚构模型尚未完成草稿')
        return dict(BRIEF)

    def job(self):
        with self.store._db() as c:
            row = c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
            return dict(row) if row else None

    def source_row(self):
        with self.store._db() as c:
            return dict(c.execute('SELECT * FROM agent_sources WHERE id=?', (self.source['id'],)).fetchone())

    def messages(self):
        with self.store._db() as c:
            return [dict(r) for r in c.execute('SELECT id,processed FROM agent_messages ORDER BY id')]

    def tasks(self):
        with self.store._db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]

    def schools(self):
        with self.store._db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]

    def exhaust(self):
        """Three immediate attempts, then the round that records the gap: no model call there."""
        for minutes in (0, 6, 17): self.round(NOW + dt.timedelta(minutes=minutes), self.fails)
        self.round(NOW + dt.timedelta(minutes=18), self.fails)

    def test_three_failures_leave_a_visible_gap_with_its_reason_and_retry_time(self):
        self.exhaust()
        job = self.job()
        retry_at = (NOW + dt.timedelta(minutes=17 + agent.SCHOOL_RETRY_MINUTES[0])).isoformat()
        self.assertEqual((job['attempts'], job['done'], job['next_try'], job['retry_at']), (agent.MAX_ATTEMPTS, 0, '', retry_at))
        self.assertIn('已记为读取缺口', job['error']); self.assertIn(retry_at, job['error'])
        gap = self.source_row()['error']
        self.assertTrue(gap.startswith(agent.SCHOOL_READ_GAP_PREFIX), gap)
        for part in (self.source['id'], 'gap-1', '3 次', '虚构模型尚未完成草稿', retry_at, self.source['name']):
            self.assertIn(part, gap)
        coverage = self.app.school_coverage('child-1')
        listed = [item for item in coverage['school_read_gaps'] if item['name'] == self.source['name']]
        self.assertEqual(len(listed), 1, coverage['school_read_gaps'])
        self.assertEqual((listed[0]['status'], listed[0]['reason']), ('最近读取未成功', gap))
        self.assertEqual([m['processed'] for m in self.messages()], [0])

    def test_the_scheduled_retry_saves_once_and_clears_the_gap(self):
        self.exhaust(); self.round(NOW + dt.timedelta(minutes=19), self.fails)
        self.assertTrue(self.source_row()['error'].startswith(agent.SCHOOL_READ_GAP_PREFIX))
        retry_at = dt.datetime.fromisoformat(self.job()['retry_at'])
        # Before its own retry time the batch is not claimed: no call, no save, the gap stays.
        calls = []
        def counted(name):
            calls.append(name); return self.fixed(name)
        self.round(retry_at - dt.timedelta(minutes=1), counted)
        self.assertEqual(calls, []); self.assertEqual(self.tasks(), [])
        result = self.round(retry_at, counted)
        self.assertEqual(calls.count('family_agent_selection'), 1, calls)
        self.assertEqual([m['processed'] for m in self.messages()], [1])
        self.assertEqual(len(self.tasks()), 1, result)
        self.assertEqual(len(self.schools()), 1)
        # The next round clears the gap and proves the saved batch is never written a second time.
        self.round(retry_at + dt.timedelta(minutes=3), counted)
        self.assertEqual(self.source_row()['error'], '')
        self.assertEqual(self.tasks(), self.tasks())
        self.assertEqual((len(self.tasks()), len(self.schools())), (1, 1))

    def test_the_retry_schedule_backs_off_and_stays_daily_after_five_failures(self):
        key = 'messages:' + agent._hash([self.source['id'], ['gap-1']])[:40]
        value = {'school_learning_policy': 8, 'messages': [
            dict(id='gap-1', time=self.stamp, kind='text', sender='语文林老师', sender_id='fiction-chinese',
                 unread=False, message_order='1', text=TEXT)]}
        at = NOW
        fp = self.store._job(key, value, at, model=True)
        self.assertTrue(fp)
        waits = []
        for attempt in range(1, 7):  # attempts 1-2 keep next_try; 3-6 hold the four scheduled retries
            self.store._fail(key, at, fingerprint=fp, reason=agent.family_llm.LLMDraftError('虚构模型尚未完成草稿'))
            job = self.job()
            if attempt < agent.MAX_ATTEMPTS:
                self.assertEqual(job['retry_at'], '', 'the original five/ten-minute waits keep next_try only')
                at = dt.datetime.fromisoformat(job['next_try']) + dt.timedelta(minutes=1)
            else:
                self.assertEqual(job['next_try'], '', 'once the original limit is spent next_try stays empty')
                waits.append((dt.datetime.fromisoformat(job['retry_at']) - at).total_seconds() / 60)
                at = dt.datetime.fromisoformat(job['retry_at'])
            self.assertTrue(self.store._job(key, value, at, model=True), 'the scheduled retry is claimable, attempt %d' % attempt)
        self.assertEqual(waits, [float(agent.SCHOOL_RETRY_MINUTES[0]), float(agent.SCHOOL_RETRY_MINUTES[1]),
                                 float(agent.SCHOOL_RETRY_MINUTES[2]), float(agent.SCHOOL_RETRY_MINUTES[2])], waits)

    def test_a_content_refusal_keeps_the_three_attempt_limit_and_writes_no_retry(self):
        def refuse(name):
            if name == 'family_agent_selection': raise agent.AgentError('虚构：学校补充要求未归到对应作业')
            return dict(BRIEF)
        for minutes in (0, 6, 17): self.round(NOW + dt.timedelta(minutes=minutes), refuse)
        self.round(NOW + dt.timedelta(minutes=18), refuse)
        job = self.job()
        self.assertEqual((job['attempts'], job['next_try'], job['retry_at']), (agent.MAX_ATTEMPTS, '', ''))
        self.assertIn('自动尝试共3次', job['error']); self.assertNotIn('已记为读取缺口', job['error'])
        gap = self.source_row()['error']
        self.assertTrue(gap.startswith(agent.SCHOOL_READ_GAP_PREFIX), gap)
        self.assertIn('虚构：学校补充要求未归到对应作业', gap); self.assertIn('需人工核对', gap)
        self.assertNotIn('下次自动重试', gap)
        self.assertIsNone(self.store._job('messages:' + agent._hash([self.source['id'], ['gap-1']])[:40],
                                          {'school_learning_policy': 8, 'messages': [
                                              dict(id='gap-1', time=self.stamp, kind='text', sender='语文林老师',
                                                   sender_id='fiction-chinese', unread=False, message_order='1', text=TEXT)]},
                                          NOW + dt.timedelta(days=1), model=True))


class SchoolNoiseIntakeTests(unittest.TestCase):
    """Fictional regressions for the deterministic pre-screen: chat never spends a call or mints a card."""

    def setUp(self):
        from test_agent import AgentTests
        self.fixture = AgentTests(methodName='runTest')
        self.fixture.setUp()
        self.app = self.fixture.app
        self.store = self.fixture.store
        self.source = self.fixture.source
        self.cursor = '10'
        self.at = NOW

    def tearDown(self):
        self.fixture.doCleanups()

    def ingest(self, rows):
        stamp = '2026-11-04T16:00:00+08:00'
        self.store.ingest(dict(source_id=self.source['id'], expected_cursor=self.cursor, cursor=str(int(self.cursor) + 1),
                               checked_at=stamp, last_message_time=stamp, error='',
                               messages=[dict(id=mid, time=stamp, kind='text', sender=sender, sender_id=account,
                                              unread=unread, message_order=str(i + 1), text=text)
                                         for i, (mid, sender, account, text, unread) in enumerate(rows)]))
        self.cursor = str(int(self.cursor) + 1)

    def round(self, model, at=None):
        with patch.object(agent.family_llm, '_chat_json', side_effect=model):
            return agent.run_once(self.app, at or self.at)

    def job(self):
        with self.store._db() as c:
            row = c.execute("SELECT * FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
            return dict(row) if row else None

    def items(self):
        with self.store._db() as c:
            return [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]

    def processed(self):
        with self.store._db() as c:
            return [r['processed'] for r in c.execute('SELECT processed FROM agent_messages ORDER BY id')]

    def test_a_chat_only_batch_is_saved_empty_without_a_model_call(self):
        self.ingest([('n1', '虚构家长', 'found-parent', '[强][强][强]', False),
                     ('n2', '虚构家长', 'found-parent', '收到', False),
                     ('n3', '虚构家长', 'found-parent', '👍', False),
                     ('n4', '虚构语文老师', 'found-teacher', '[已撤回，正文未读取]', False)])
        def model(messages, schema, name, **kw): raise AssertionError('a chat-only batch must not call the model')
        result = self.round(model)
        self.assertEqual((result['processed'], result['failed'], result['created']), (4, 0, 0))
        self.assertEqual(self.items(), [])
        self.assertEqual(self.processed(), [1, 1, 1, 1])
        with self.store._db() as c:
            events = [dict(r) for r in c.execute("SELECT * FROM agent_item_events WHERE kind='prescreen' ORDER BY id")]
        self.assertEqual(len(events), 4)
        self.assertTrue(all(row['note'] and row['item_id'].startswith('message:') for row in events))
        job = self.job()
        self.assertEqual((job['done'], job['attempts'], job['retry_at']), (1, 0, ''))
        for minutes in (3, 9):  # later ticks keep the same empty decision and never ask again
            self.round(model, self.at + dt.timedelta(minutes=minutes))
        self.assertEqual(self.job()['attempts'], 0)

    def test_a_mixed_batch_sends_only_the_teacher_message_to_the_model(self):
        import json as _json
        from test_agent import school_proposal
        teacher = '今晚朗读《风经过小巷》第2、3自然段各两遍，明早抽听。'
        self.ingest([('m1', '虚构语文老师', 'found-teacher', teacher, False),
                     ('m2', '虚构家长', 'found-parent', '[强][强][强]', False)])
        seen = {}
        def model(messages, schema, name, **kw):
            if name != 'family_agent_selection': return dict(BRIEF)
            content = _json.loads(messages[-1]['content'])
            seen['refs'] = [e['ref'] for e in content['evidence']]
            seen['calls'] = seen.get('calls', 0) + 1
            return dict(proposals=[school_proposal(title_quote=teacher, task_title='语文：朗读《风经过小巷》第2、3自然段',
                                                   task_goal='朗读《风经过小巷》第2、3自然段各两遍。', task_state='ready',
                                                   task_purpose='learning', evidence=[dict(ref='message:' + self.source['id'] + ':m1')])])
        result = self.round(model)
        self.assertEqual(seen['calls'], 1)
        self.assertEqual(seen['refs'], ['message:' + self.source['id'] + ':m1'])
        self.assertEqual(len(self.items()), 1, result)
        self.assertEqual(self.processed(), [1, 1])

    def test_placeholders_attachments_and_short_parent_orders_are_not_dropped(self):
        import io, json as _json
        from urllib.parse import quote
        self.ingest([('i1', '虚构家长', 'found-parent', '[图片]', True),
                     ('i2', '虚构家长', 'found-parent', '明天带水彩笔', False),
                     ('i3', '虚构语文老师', 'found-teacher', '收到', False)])
        upload = self.app.save_upload(io.BytesIO(b'fictional'), 9, quote('虚构.txt'))
        self.store.message_attachment(dict(child_id='child-1', source_id=self.source['id'], message_id='i3',
                                           attachment_id=upload['id'], action='attach'), self.app.upload_info)
        class Seen(Exception): pass
        seen = {}
        def model(messages, schema, name, **kw):
            if name != 'family_agent_selection': return dict(BRIEF)
            content = _json.loads(messages[-1]['content'])
            seen['refs'] = {e['ref'] for e in content['evidence']}
            raise Seen()
        with self.assertRaises(Seen): self.round(model)
        # the read picture and the short parent order are evidence; the acknowledged file is a hold pointer,
        # never evidence the model may resolve into an assignment.
        self.assertEqual(seen['refs'], {'message:' + self.source['id'] + ':' + mid for mid in ('i1', 'i2')})
        entry = dict(ref='message:' + self.source['id'] + ':i3', text='收到', kind='text', unread=False,
                     time='2026-11-04T16:00:00+08:00')
        self.assertEqual(agent._school_noise(dict(entry, attachments=[{'name': '虚构.txt', 'mime': 'text/plain'}])), '')
        pointer = agent._school_ack_original(dict(entry, attachments=[{'name': '虚构.txt', 'mime': 'text/plain'}]))
        self.assertTrue(pointer and '待整理' in str(pointer.get('title') or pointer.get('body') or pointer), pointer)

    def test_a_reference_reply_without_a_title_builds_no_row(self):
        from test_agent import school_proposal
        quote = '今天秋游的照片已经发到班级相册，供大家查看。'
        self.ingest([('r1', '虚构语文老师', 'found-teacher', quote, False)])
        ref = 'message:' + self.source['id'] + ':r1'
        def model(messages, schema, name, **kw):
            if name != 'family_agent_selection': return dict(BRIEF)
            return dict(proposals=[school_proposal(title_quote='', task_title='', task_goal='', task_state='reference',
                                                   task_purpose='unknown', evidence=[dict(ref=ref)])])
        result = self.round(model)
        self.assertEqual((len(self.items()), result['processed'], result['failed']), (0, 1, 0))
        self.assertEqual(self.processed(), [1])
        self.assertEqual(self.job()['done'], 1)


class SchoolExpiryTests(unittest.TestCase):
    """Plan §2/§4/§5: stale cards park as `expired` with one event, leave the pending list, and can be restored."""

    def setUp(self):
        from test_agent import AgentTests
        self.fixture = AgentTests(methodName='runTest')
        self.fixture.setUp()
        self.app = self.fixture.app
        self.store = self.fixture.store
        self.source = self.fixture.source

    def tearDown(self):
        self.fixture.doCleanups()

    def item(self, ident, *, tier='confirm', created_hours=49, due='', task_id='', keep=False, folded_hours=None):
        brief = dict(state='review', title='数学：完成《每日练习》第26页', goal='完成第26页1—3题。',
                     change='new', target_id='', purpose='learning', policy=0)
        if tier == 'ref': brief.update(state='reference')
        if tier == 'hold': brief.update(title='', goal='')
        if tier == 'todo': brief.update(state='ready', policy=agent.SCHOOL_TASK_POLICY, change='new', target_id='')
        if tier == 'same': brief.update(change='same', target_id='AGENT-1')
        plan = dict(school_task=brief)
        if keep: plan['school_keep'] = True
        if folded_hours is not None:
            plan['school_folded'] = [dict(change='same', at=(NOW - dt.timedelta(hours=folded_hours)).isoformat())]
        created = (NOW - dt.timedelta(hours=created_hours)).isoformat()
        with self.store._db() as c:
            c.execute("""INSERT INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,care_id,state,
                         created,updated,task_id,plan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (ident, 'messages:fixture', self.source['child_id'], 'school',
                       '数学：完成《每日练习》第26页', '完成第26页1—3题。',
                       json.dumps([dict(ref='message:' + self.source['id'] + ':' + ident, text='虚构原文')]),
                       due, '', 'pending', created, created, task_id, json.dumps(plan)))
        return ident

    def state(self, ident):
        with self.store._db() as c:
            return dict(c.execute('SELECT * FROM agent_items WHERE id=?', (ident,)).fetchone())

    def events(self, ident):
        with self.store._db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM agent_item_events WHERE item_id=? ORDER BY id', (ident,))]

    def test_stale_cards_park_while_due_or_kept_ones_stay(self):
        stale = self.item('stale', tier='confirm', created_hours=49)
        due = self.item('due', tier='confirm', created_hours=49,
                        due=(NOW + dt.timedelta(days=1)).date().isoformat())
        ref = self.item('ref', tier='ref', created_hours=25)
        hold = self.item('hold', tier='hold', created_hours=25)
        todo = self.item('todo', tier='todo', created_hours=72)
        linked = self.item('linked', tier='confirm', created_hours=49, task_id='AGENT-1')
        kept = self.item('kept', tier='confirm', created_hours=49, keep=True)
        folded = self.item('folded', tier='confirm', created_hours=60, folded_hours=30)
        agent._expire_school_pending(self.store, NOW)
        self.assertEqual(self.state(stale)['state'], 'expired')
        self.assertEqual([e['note'] for e in self.events(stale)], ['confirm'])
        self.assertEqual(self.state(ref)['state'], 'expired')
        self.assertEqual([e['note'] for e in self.events(ref)], ['ref'])
        self.assertEqual(self.state(hold)['state'], 'expired')
        self.assertEqual([e['note'] for e in self.events(hold)], ['hold'])
        for ident in (due, todo, linked, kept, folded):
            self.assertEqual(self.state(ident)['state'], 'pending', ident)
        view = self.store.snapshot()
        listed = {row['id'] for row in view['items'] if row['state'] == 'pending'}
        self.assertNotIn(stale, listed)
        self.assertIn(folded, listed)
        self.assertEqual(view['expired_count'], 3)
        self.assertEqual({row['id'] for row in view['expired']}, {stale, ref, hold})
        self.assertEqual({row['id']: row['tier'] for row in view['expired']}[stale], 'confirm')

    def test_restore_returns_a_card_and_keeps_it(self):
        ident = self.item('parked', tier='confirm', created_hours=49)
        agent._expire_school_pending(self.store, NOW)
        self.assertEqual(self.store.act(dict(id=ident, action='restore'))['state'], 'pending')
        row = self.state(ident)
        self.assertEqual(row['state'], 'pending')
        self.assertTrue(json.loads(row['plan'])['school_keep'])
        self.assertEqual([e['kind'] for e in self.events(ident)], ['expire', 'restore'])
        agent._expire_school_pending(self.store, NOW + dt.timedelta(days=3))
        self.assertEqual(self.state(ident)['state'], 'pending')
        view = self.store.snapshot()
        self.assertIn(ident, {row['id'] for row in view['items'] if row['state'] == 'pending'})
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=ident, action='restore'))

    def test_hidden_cards_are_counted_and_can_be_restored_after_they_expire(self):
        hold = self.item('hidden-hold', tier='hold', created_hours=25)
        ref = self.item('hidden-ref', tier='ref', created_hours=25)
        fresh = self.item('hidden-fresh', tier='hold', created_hours=1)
        folded_now = self.item('folded-now', tier='confirm', created_hours=72, folded_hours=0.02)
        view = self.store.snapshot()
        self.assertEqual(view['hidden_count'], 3, 'pending hold/ref cards stay counted while hidden')
        self.assertEqual({row['id'] for row in view['items']} & {hold, ref, fresh}, set())
        agent._expire_school_pending(self.store, NOW)
        view = self.store.snapshot()
        self.assertEqual({row['id'] for row in view['expired']} & {hold, ref}, {hold, ref})
        self.assertEqual(view['hidden_count'], 1, 'only the fresh hold is still pending and hidden')
        self.assertEqual(self.state(folded_now)['state'], 'pending', 'a just-folded card is not expired by age alone')
        for ident in (hold, ref):
            self.assertEqual(self.store.act(dict(id=ident, action='restore'))['state'], 'pending')
        view = self.store.snapshot()
        self.assertEqual(view['hidden_count'], 3, 'restored hold/ref cards are pending again')
        self.assertEqual({row['id'] for row in view['items']} & {hold, ref}, set())

    def test_the_event_table_and_source_columns_migrate_and_read_only_works(self):
        with self.store._db() as c:
            tables = {row['name'] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {row['name'] for row in c.execute('PRAGMA table_info(agent_sources)')}
        self.assertIn('agent_item_events', tables)
        self.assertTrue({'error_code', 'fail_count'} <= columns)
        read_only = agent.Store(self.app.connect, self.app.profiles, self.store.data, initialize=False)
        self.assertIsInstance(read_only.snapshot(), dict)


if __name__ == '__main__':
    unittest.main()

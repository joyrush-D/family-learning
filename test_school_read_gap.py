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


if __name__ == '__main__':
    unittest.main()

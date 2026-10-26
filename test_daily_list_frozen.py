"""Frozen fictional daily-list acceptance (验收-每日清单.md T01–T10); no household data, collectors, devices or printing.

Original texts, send times and expectations are copied from the frozen contract and are independent of any reply.
The model seam returns fixed fictional receipts: a pass proves only the real run_once→Store→calendar API→single-child
list path (validation, save, dates, display data), never the product model's own extraction quality, which stays unmeasured.
Set DAILY_LIST_REPORT to a file path to record each case's actual list view for the difference report.
"""
import datetime as dt
import json
import os
import traceback
import unittest

import family_agent as agent
import test_agent as fixtures
import test_school_native_coverage as native


def view(item):
    m = item['agenda']
    return dict(kind=item['kind'], title=item['title'], status=item['status'], category=m['category'],
                published_at=m.get('published_at', ''), complete_on=m.get('complete_on', ''), due_on=m['due_on'],
                due_kind=m.get('due_kind', ''), scheduled_on=m['scheduled_on'], body=item['body'],
                publications=[p['ref'] for p in m.get('publications', [])])


class DailyListFrozenTests(unittest.TestCase):
    _use_replies = native.SchoolNativeCoverageTests._use_replies

    def setUp(self):
        native.SchoolNativeCoverageTests.setUp(self)
        self.fixture.now = self.now = dt.datetime(2026, 11, 4, 20, tzinfo=agent.TZ)

    def _day(self, messages, day='2026-11-04'):
        """messages: (HH:MM, sender, publisher id, frozen text) sent on the contract's day in Asia/Shanghai."""
        payload = self.fixture.payload(cursor=str(10 + len(messages)))
        payload['messages'] = [dict(id=str(11 + i), message_order=str(11 + i), time=day + 'T' + hm + ':00+08:00', kind='text',
                                    sender=sender, sender_id=publisher, text=text, unread=False)
                               for i, (hm, sender, publisher, text) in enumerate(messages)]
        self.store.ingest(payload)
        return payload, ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]

    def _proposal(self, quote, refs, subject, goal, due='', purpose='learning', submission=''):
        return fixtures.school_proposal(
            title_quote=quote, due=due, evidence=[dict(ref=r) for r in refs], learning_subject=subject,
            task_title=(subject + '：' if subject else '') + quote, task_goal=goal, task_state='ready',
            task_purpose=purpose, task_submission=submission, task_reason='虚构固定回执，只验校验/保存/展示。')

    def _report(self, **line):
        report = os.environ.get('DAILY_LIST_REPORT')
        if report:
            with open(report, 'a', encoding='utf-8') as f:
                f.write(json.dumps(line, ensure_ascii=False) + '\n')

    def _run(self, payload, proposals, case, today='2026-11-04', now=None):
        """The real first pass and its saved single-child list. The replay is checked only after the case's own product
        assertions (_replay_adds_nothing), so a retry or reply-seam error never stands in front of the actual result."""
        self._use_replies(payload, [dict(proposals=proposals)])
        self._batch, self._ran_at = (payload, proposals), now or self.now
        result = agent.run_once(self.app, self._ran_at)
        with self.store._db() as c:
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        self.assertEqual(originals, payload['messages'], 'originals and send times are kept unchanged')
        snapshot = self.app.calendar_snapshot(today, today)
        listed = [view(i) for i in snapshot['inbox'] if i['kind'] in ('task', 'school') and i['child_ids'] == ['child-1']]
        visible = [i['title'] for i in snapshot['agenda'] if i['kind'] in ('task', 'school')]
        on_day = [i['title'] for i in listed if today in (i['due_on'], i['scheduled_on'], i['complete_on']) and i['title'] in visible]
        self._report(case=case, result={k: result[k] for k in ('failed', 'processed', 'created')}, model_calls=self.model.call_count,
                     items=[dict(state=r['state'], due=r['due'], title=r['title']) for r in rows],
                     listed=listed, visible=visible, on_day=on_day)
        return result, rows, listed, (on_day, visible)

    def _replay_adds_nothing(self, case):
        """A saved batch run again 7 minutes later adds no item and requests no second model receipt."""
        replay = agent.run_once(self.app, self._ran_at + dt.timedelta(minutes=7))
        self._report(case=case + '-replay', result={k: replay[k] for k in ('failed', 'processed', 'created')},
                     model_calls=self.model.call_count)
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0), 'a replay never adds a second item')
        self.assertEqual(self.model.call_count, 1, 'one bounded model receipt per batch')

    def _job(self):
        with self.store._db() as c:
            job = dict(c.execute("SELECT attempts, next_try, error, done FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone())
            processed = [r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')]
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            items = c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0]
        return job, processed, originals, items

    def _t01(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。'),
                                   ('18:02', '语文老师甲', 'cn-teacher-a', '刚才的朗读还要家长签字。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。')
        result, rows, listed, (on_day, visible) = self._run(payload, [reading], 'T01')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        item, = listed
        self.assertEqual((item['kind'], item['category']), ('task', 'homework'))
        self.assertIn('2026-11-04', (item['complete_on'], item['due_on'] if item['due_kind'] in ('', 'deadline') else ''))
        self.assertNotEqual(item['due_kind'], 'handback', 'no handback day is stated')
        for words in ('《荷塘》', '2遍', '签字'): self.assertIn(words, item['body'])
        self.assertEqual(item['publications'], refs, 'both originals keep their own source entry')
        self.assertEqual(item['published_at'][:16], '2026-11-04T18:00')
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing('T01')

    @unittest.expectedFailure  # Reproduced product defect, frozen expectation unchanged: the 刚才的朗读 supplement is not bound to
    def test_t01_continued_supplement_is_one_chinese_item_with_both_originals(self):  # its reading (pinned by the next test).
        self._t01()

    def test_t01_expected_failure_is_the_first_pass_product_result(self):
        """Pins T01's expected failure to the product's own first-pass result, never the reply seam or a replay, then checks
        the rejected batch's retries with a fixed receipt for each attempt: the original limit, nothing saved, originals kept.
        Remove together with T01's expectedFailure once the supplement is bound."""
        try:  # assertRaises drops the traceback, which is the evidence here
            self._t01()
        except self.failureException as failure:
            message, frames = str(failure), traceback.extract_tb(failure.__traceback__)
        else:
            self.fail('T01 passes now: remove its expectedFailure and this pin')
        own = [f for f in frames if os.path.basename(f.filename) == os.path.basename(__file__)]
        self.assertEqual((own[-1].name, own[-1].line), ('_t01', "self.assertEqual((result['failed'], result['processed']), (0, 2))"))
        self.assertIn('(1, 0) != (0, 2)', message)
        self.assertNotIn(os.path.basename(native.__file__), {os.path.basename(f.filename) for f in frames}, 'not the reply seam')
        self.assertEqual(self.model.call_count, 1, 'the first pass alone: no replay was reached')
        job, processed, originals, items = self._job()
        self.assertEqual((job['attempts'], job['done'], processed, items), (1, 0, [0, 0], 0))
        self.assertIn('学校补充要求未归到对应作业', job['error'])
        payload, proposals = self._batch
        self._use_replies(payload, [dict(proposals=proposals)] * (agent.MAX_ATTEMPTS - 1))
        for minutes in (7, 18, 60):  # attempt 2 after its 5-minute wait, attempt 3 after 10 more, then none
            agent.run_once(self.app, self._ran_at + dt.timedelta(minutes=minutes))
        job, processed, originals, items = self._job()
        self.assertEqual(self.model.call_count, agent.MAX_ATTEMPTS, 'one fixed receipt per attempt, never past the original limit')
        self.assertEqual((job['attempts'], job['done'], job['next_try'], processed, items), (agent.MAX_ATTEMPTS, 0, '', [0, 0], 0))
        self.assertIn('学校补充要求未归到对应作业', job['error'])
        self.assertIn('达到自动重试上限', job['error'])
        self.assertEqual(originals, payload['messages'])

    def test_t02_independent_supply_is_its_own_admin_item_on_its_own_day(self):
        text = '今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练。'
        payload, refs = self._day([('18:10', '老师乙', 'teacher-b', text)])
        reading = self._proposal('今晚跟读Unit 5两遍', refs, '英语', '今晚跟读Unit 5两遍。')
        rope = self._proposal('明天体育课带跳绳', refs, '', '11月5日体育课带跳绳；不要求在家训练。', due='2026-11-05', purpose='admin')
        result, rows, listed, (on_day, visible) = self._run(payload, [reading, rope], 'T02')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(len(listed), 2)
        english, = [i for i in listed if 'Unit 5' in i['body']]
        supply, = [i for i in listed if '跳绳' in i['body']]
        self.assertEqual(english['category'], 'homework')
        self.assertIn('2026-11-04', (english['complete_on'], english['due_on']))
        self.assertNotIn('跳绳', english['body'])
        self.assertEqual((supply['category'], supply['due_on'], supply['complete_on']), ('todo', '2026-11-05', ''))
        self.assertNotIn('Unit 5', supply['body'])
        self.assertFalse(any(i['title'].endswith('训练') or '在家训练' in i['title'] for i in listed), 'no training item is generated')
        self._replay_adds_nothing('T02')

    def test_t03_same_subject_from_two_teachers_stays_two_signed_items(self):
        payload, refs = self._day([('18:20', '数学老师甲', 'math-teacher-a', '今晚做练习二第1、2题。'),
                                   ('18:25', '数学老师乙', 'math-teacher-b', '今晚做练习二第4题。')])
        first = self._proposal('今晚做练习二第1、2题', refs[:1], '数学', '今晚做练习二第1、2题。')
        second = self._proposal('今晚做练习二第4题', refs[1:], '数学', '今晚做练习二第4题。')
        result, rows, listed, (on_day, visible) = self._run(payload, [first, second], 'T03')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        self.assertEqual(sorted(i['publications'] for i in listed), [refs[:1], refs[1:]], 'each keeps its own teacher and source')
        self.assertEqual(sorted('第1、2题' in i['body'] for i in listed), [False, True])
        self.assertTrue(all(i['category'] == 'homework' for i in listed))
        self._replay_adds_nothing('T03')

    def test_t03_counterexample_merged_reply_is_not_saved_as_one_item(self):
        payload, refs = self._day([('18:20', '数学老师甲', 'math-teacher-a', '今晚做练习二第1、2题。'),
                                   ('18:25', '数学老师乙', 'math-teacher-b', '今晚做练习二第4题。')])
        # Only the two teachers' merge is off-contract here: no due or other field the reply should not carry.
        merged = self._proposal('今晚做练习二第1、2题', refs, '数学', '今晚做练习二第1、2题；第4题。')
        result, rows, listed, _ = self._run(payload, [merged], 'T03-merged')
        self.assertEqual((result['failed'], result['processed'], result['created']), (1, 0, 0), 'the whole batch is kept for retry')
        job, processed, originals, items = self._job()
        self.assertIn('学校补充要求未归到对应作业', job['error'], "the other teacher's original is no supplement of this item")
        self.assertEqual((processed, items, listed), ([0, 0], 0, []), "two teachers' same-titled work is never one accepted item")

    def test_t04_late_organizing_keeps_the_original_days_and_unknown_completion(self):
        payload, refs = self._day([('18:30', '数学老师甲', 'math-teacher-a', '今晚完成第4题，明早交给数学课代表。')])
        work = self._proposal('今晚完成第4题，明早交给数学课代表', refs, '数学', '今晚完成第4题；11月5日早上交给数学课代表。',
                              due='2026-11-05', submission='11月5日早上交给数学课代表')
        late = dt.datetime(2026, 11, 6, 20, tzinfo=agent.TZ)
        self.fixture.now = late
        result, rows, listed, (on_day, visible) = self._run(payload, [work], 'T04', today='2026-11-06', now=late)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['category'], item['complete_on'], item['due_on'], item['due_kind'], item['scheduled_on']),
                         ('homework', '2026-11-04', '2026-11-05', 'handback', ''))
        self.assertEqual(item['published_at'][:16], '2026-11-04T18:30', 'not a new 11-06 assignment')
        self.assertEqual((visible, on_day), ([item['title']], []), 'an open overdue item is still checked on 11-06, not 11-06 work')
        self.assertIn(item['status'], ('待跟进', '待核对'), 'no feedback is no completion fact')
        self.assertIn('不推定完成', rows[0]['plan'], 'the overdue check never infers the child did or did not do it')
        self._replay_adds_nothing('T04')

    def test_t07_undated_consent_keeps_its_question_without_blocking_the_english_item(self):
        payload, refs = self._day([('18:45', '老师甲', 'teacher-a', '请家长签署同意书后交回。'),
                                   ('18:46', '英语老师', 'en-teacher', '今晚跟读Unit 6两遍。')])
        consent = self._proposal('请家长签署同意书后交回', refs[:1], '', '家长签署同意书后交回。', purpose='admin')
        english = self._proposal('今晚跟读Unit 6两遍', refs[1:], '英语', '今晚跟读Unit 6两遍。')
        result, rows, listed, (on_day, visible) = self._run(payload, [consent, english], 'T07')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        self.assertEqual(len(listed), 2)
        sign, = [i for i in listed if '同意书' in i['body']]
        reading, = [i for i in listed if 'Unit 6' in i['body']]
        self.assertEqual((sign['category'], sign['due_on'], sign['complete_on']), ('todo', '', ''), 'its date stays unknown')
        self.assertEqual((reading['kind'], reading['category']), ('task', 'homework'))
        self.assertIn('2026-11-04', (reading['complete_on'], reading['due_on']))
        self._replay_adds_nothing('T07')

    def test_t09_classroom_dictation_stays_its_own_next_day_item(self):
        text = '今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写；明天英语课听写。'
        payload, refs = self._day([('19:00', '英语老师', 'en-teacher', text)])
        reading = self._proposal('今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写', refs, '英语',
                                 '今晚听音频跟读Unit 5第1至8个单词，每个两遍；不用抄写。')
        dictation = self._proposal('明天英语课听写', refs, '英语', '11月5日英语课听写。', due='2026-11-05')
        result, rows, listed, (on_day, visible) = self._run(payload, [reading, dictation], 'T09')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(len(listed), 2)
        tonight, = [i for i in listed if '跟读' in i['body']]
        test, = [i for i in listed if '跟读' not in i['body']]
        self.assertIn('2026-11-04', (tonight['complete_on'], tonight['due_on']))
        self.assertIn('听写', test['body'])
        self.assertEqual((test['due_on'], test['complete_on']), ('2026-11-05', ''), 'the dictation is in class on 11-05, not tonight')
        self.assertNotIn('今晚', test['body'])
        self.assertNotIn('抄写', test['body'].replace('不用抄写', ''))
        self.assertEqual(on_day, [tonight['title']], 'only the follow-reading is tonight\'s work')
        self._replay_adds_nothing('T09')

    @unittest.expectedFailure  # Reproduced defect, frozen expectation unchanged: _school_role_days rejects any 或 and the undated 然后签字 role.
    def test_t10_reply_slip_choice_keeps_both_roles_and_both_options(self):
        text = '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。'
        payload, refs = self._day([('19:05', '班主任', 'head-teacher', text)])
        slip = self._proposal(text.rstrip('。'), refs, '', '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子11月5日早上交给班主任。',
                              due='2026-11-05', purpose='admin', submission='孩子明早交给班主任')
        result, rows, listed, (on_day, visible) = self._run(payload, [slip], 'T10')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['kind'], item['category'], item['complete_on'], item['due_on'], item['due_kind']),
                         ('task', 'todo', '2026-11-04', '2026-11-05', 'handback'))
        for words in ('参加', '不参加', '签字', '班主任'): self.assertIn(words, item['body'])
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing('T10')

    def test_t01_counterexample_a_send_day_due_for_tonight_work_states_no_handback(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍。', due='2026-11-04')
        result, rows, listed, _ = self._run(payload, [reading], 'T01-send-day-due')
        item, = listed  # Off-contract send-day due (发送日不作截止): adopted here, held for 今晚做练习二 (see RESULT); never a handback.
        self.assertNotEqual(item['due_kind'], 'handback')
        self.assertIn('2026-11-04', (item['complete_on'], item['due_on']))
        self._replay_adds_nothing('T01-send-day-due')


if __name__ == '__main__':
    unittest.main()

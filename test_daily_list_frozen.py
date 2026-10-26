"""Frozen fictional daily-list acceptance (验收-每日清单.md T01–T10); no household data, collectors, devices or printing.

Original texts, send times and expectations are copied from the frozen contract and are independent of any reply.
The model seam returns fixed fictional receipts: a pass proves only the real run_once→Store→calendar API→single-child
list path (validation, save, dates, display data), never the product model's own extraction quality, which stays unmeasured.
Set DAILY_LIST_REPORT to a file path to record each case's actual list view for the difference report.
"""
import datetime as dt
import json
import os
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

    def _run(self, payload, proposals, case, today='2026-11-04', now=None):
        self._use_replies(payload, [dict(proposals=proposals)])
        result = agent.run_once(self.app, now or self.now)
        with self.store._db() as c:
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        self.assertEqual(originals, payload['messages'], 'originals and send times are kept unchanged')
        snapshot = self.app.calendar_snapshot(today, today)
        listed = [view(i) for i in snapshot['inbox'] if i['kind'] in ('task', 'school') and i['child_ids'] == ['child-1']]
        visible = [i['title'] for i in snapshot['agenda'] if i['kind'] in ('task', 'school')]
        on_day = [i['title'] for i in listed if today in (i['due_on'], i['scheduled_on'], i['complete_on']) and i['title'] in visible]
        replay = agent.run_once(self.app, (now or self.now) + dt.timedelta(minutes=7))
        report = os.environ.get('DAILY_LIST_REPORT')
        if report:
            with open(report, 'a', encoding='utf-8') as f:
                f.write(json.dumps(dict(case=case, result={k: result[k] for k in ('failed', 'processed', 'created')},
                                        model_calls=self.model.call_count, items=[dict(state=r['state'], due=r['due'], title=r['title'])
                                                                               for r in rows],
                                        listed=listed, visible=visible, on_day=on_day, replay_created=replay['created']), ensure_ascii=False) + '\n')
        self.assertEqual((replay['processed'], replay['created']), (0, 0), 'a replay never adds a second item')
        self.assertEqual(self.model.call_count, 1, 'one bounded model receipt per batch')
        return result, rows, listed, (on_day, visible)

    def test_t01_continued_supplement_is_one_chinese_item_with_both_originals(self):
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

    def test_t03_counterexample_merged_reply_is_not_saved_as_one_item(self):
        payload, refs = self._day([('18:20', '数学老师甲', 'math-teacher-a', '今晚做练习二第1、2题。'),
                                   ('18:25', '数学老师乙', 'math-teacher-b', '今晚做练习二第4题。')])
        merged = self._proposal('今晚做练习二第1、2题', refs, '数学', '今晚做练习二第1、2题；第4题。', due='2026-11-04')
        self._use_replies(payload, [dict(proposals=[merged])])
        result = agent.run_once(self.app, self.now)
        listed = [view(i) for i in self.app.calendar_snapshot('2026-11-04', '2026-11-04')['inbox'] if i['kind'] in ('task', 'school')]
        report = os.environ.get('DAILY_LIST_REPORT')
        if report:
            with open(report, 'a', encoding='utf-8') as f:
                f.write(json.dumps(dict(case='T03-merged', result={k: result[k] for k in ('failed', 'processed', 'created')},
                                        listed=listed), ensure_ascii=False) + '\n')
        self.assertFalse(any(i['kind'] == 'task' and refs[0] in i['publications'] and refs[1] in i['publications'] for i in listed),
                         'two teachers\' same-titled work is never one accepted item')

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

    def test_t01_counterexample_a_send_day_due_for_tonight_work_is_held_not_adopted(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍。', due='2026-11-04')
        result, rows, listed, _ = self._run(payload, [reading], 'T01-send-day-due')
        row, = rows
        self.assertEqual((row['state'], row['due']), ('pending', ''), 'the send day is no deadline (prompt contract); it waits for review')
        self.assertIn(agent.SCHOOL_UNADOPTED_NOTE.strip(), row['plan'])


if __name__ == '__main__':
    unittest.main()

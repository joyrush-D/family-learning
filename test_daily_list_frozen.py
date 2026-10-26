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

import family_agenda
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
        self._replay_adds_nothing('T01')

    def _t02_batch(self):
        """T02's frozen message and its fixed fictional receipt: tonight's English reading and tomorrow's PE rope."""
        text = '今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练。'
        payload, refs = self._day([('18:10', '老师乙', 'teacher-b', text)])
        reading = self._proposal('今晚跟读Unit 5两遍', refs, '英语', '今晚跟读Unit 5两遍。')
        rope = self._proposal('明天体育课带跳绳', refs, '', '11月5日体育课带跳绳；不要求在家训练。', due='2026-11-05', purpose='admin')
        return payload, [reading, rope]

    def test_t02_independent_supply_is_its_own_admin_item_on_its_own_day(self):
        payload, proposals = self._t02_batch()
        result, rows, listed, (on_day, visible) = self._run(payload, proposals, 'T02')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(len(listed), 2)
        english, = [i for i in listed if 'Unit 5' in i['body']]
        supply, = [i for i in listed if '跳绳' in i['body']]
        self.assertEqual(english['category'], 'homework')
        self.assertIn('2026-11-04', (english['complete_on'], english['due_on']))
        self.assertNotIn('跳绳', english['body'])
        self.assertEqual((supply['category'], supply['due_on'], supply['complete_on']), ('todo', '2026-11-05', ''))
        # 11/5 is the PE lesson's arranged day for carrying the rope, not a deadline, handback or check; no parent plan is made up.
        self.assertEqual((supply['due_kind'], supply['scheduled_on']), ('arranged', ''))
        self.assertNotEqual(english['due_kind'], 'arranged')
        self.assertNotIn('2026-11-05', (english['due_on'], english['complete_on'], english['scheduled_on']), 'tonight never borrows tomorrow')
        self.assertNotIn('Unit 5', supply['body'])
        self.assertFalse(any(i['title'].endswith('训练') or '在家训练' in i['title'] for i in listed), 'no training item is generated')
        self._replay_adds_nothing('T02')

    def test_t02_only_carrying_to_that_days_lesson_is_an_arranged_day(self):
        meaning = lambda quote, due='2026-11-05', title='': family_agenda.date_meaning(quote, due, '2026-11-04', title)
        self.assertEqual(meaning('明天体育课带跳绳'), 'arranged')
        self.assertEqual(meaning('另外，明天体育课带跳绳，不要求在家训练'), 'arranged')
        self.assertEqual(meaning('今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练'), 'arranged')
        self.assertEqual(meaning('今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练', '2026-11-04'), 'deadline', 'tonight is not tomorrow')
        self.assertEqual(meaning('今晚跟读Unit 5两遍', '2026-11-05'), 'deadline')
        for quote in ('11月5日前准备好跳绳', '11月5日前带跳绳', '明天体育课不用带跳绳', '明天体育课取消，不用带跳绳', '今晚完成练习，明天带来'):
            self.assertEqual(meaning(quote), 'deadline', quote)
        self.assertEqual(meaning('今晚完成第4题，明早交给数学课代表'), 'handback')
        self.assertEqual(meaning('明早检查跳绳'), 'inspection')
        self.assertNotEqual(meaning('明天英语课听写'), 'arranged')
        self.assertEqual(meaning('运动会定于11月5日举行，请家长参加', title='参加运动会'), 'event')

    def test_t06_carrying_the_sheet_to_tomorrows_class_is_its_arranged_day(self):
        """T06's date reading only; its unread attachment is a separate open question. 带去课堂的<thing> carries a thing of
        its own to that day's lesson as T02's 带 does, so 11/5 is its arranged day. Without a thing of its own (the work
        itself), before that day, negated, with another predicate or handed in, it is not."""
        meaning = lambda quote, due='2026-11-05': family_agenda.date_meaning(quote, due, '2026-11-04')
        self.assertEqual(meaning('附件是明天带去课堂的实验观察表，今晚不填'), 'arranged')
        self.assertEqual(meaning('明天带去课堂的实验观察表'), 'arranged')
        self.assertNotEqual(meaning('附件是明天带去课堂的实验观察表，今晚不填', '2026-11-04'), 'arranged', 'tonight is not tomorrow')
        for quote in ('今晚完成练习，明天带去', '今晚填好观察表，明天带去课堂', '11月5日前带去课堂的实验观察表',
                      '明天不用带去课堂的实验观察表', '明天带去课堂的观察表要填好', '明天把作品带去参加展览'):
            self.assertEqual(meaning(quote), 'deadline', quote)
        self.assertEqual(meaning('明天把观察表带去学校交给老师'), 'handback')

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
        self._t10_original_reads(refs[0], text)

    def _t10_original_reads(self, ref, text):
        """The accepted slip's own teacher message opens from its task (Root: GET /api/agent/message returned 409). The slip
        was saved from its quoted words, no native action, and its message carries no file: its text is its whole scope.
        A changed original, another child's binding or a file added later still keep the old refusals."""
        source_id, message_id = ref[8:].rsplit(':', 1)
        with self.store._db() as c:
            row = dict(c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='accepted'").fetchone())
        self.assertNotIn('school_original_action', json.loads(row['plan']), 'saved from its reply, not a native action')
        ask = dict(child_id='child-1', source_id=source_id, message_id=message_id, task_id=row['task_id'])
        view = self.store.message(ask, None)
        self.assertEqual((view['task_id'], view['attachments'], view['action_material']['scoped']), (row['task_id'], [], True))
        self.assertEqual([q['text'] for q in view['action_material']['quotes']], [text])
        self.assertEqual([q['upload_ids'] for q in view['action_material']['quotes']], [[]], 'text only, no file bound')
        with self.store._db() as c:
            self.assertEqual(json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (row['id'],)).fetchone()[0]),
                             json.loads(row['plan']), 'reading saves nothing')
            with self.assertRaises(agent.AgentError):  # another child's binding of the same message
                agent.school_original_source_row(self.store, c, dict(row, child_id='child-other'), ref)
            c.execute('INSERT INTO agent_message_attachments(source_id,message_id,upload_id) VALUES(?,?,?)', (source_id, message_id, 'u-added'))
            with self.assertRaises(agent.AgentError) as added:  # a file now sharing the message: its share stays unknown
                agent.school_original_upload_ids(self.store, c, row, ref, ['u-added'])
            self.assertEqual((added.exception.status, added.exception.code), (409, 'school_original_scope_stale'))
            c.execute('DELETE FROM agent_message_attachments WHERE upload_id=?', ('u-added',))
            plan = json.loads(row['plan']); plan['school_task'].pop('origin_basis')
            with self.assertRaises(agent.AgentError) as legacy:  # a legacy decision that never recorded its basis
                agent.school_original_upload_ids(self.store, c, dict(row, plan=json.dumps(plan, ensure_ascii=False)), ref, [])
            self.assertEqual((legacy.exception.status, legacy.exception.code, str(legacy.exception)),
                             (409, 'school_original_scope_stale', '本项资料范围尚未核明，请查看老师完整原消息'), 'unverified, not changed')
            payload = json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?', (source_id, message_id)).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(payload, text=text.replace('明早', '后天')), ensure_ascii=False), source_id, message_id))
        with self.assertRaises(agent.AgentError) as changed:
            self.store.message(ask, None)
        self.assertEqual((changed.exception.status, changed.exception.code, str(changed.exception)),
                         (409, 'school_original_scope_stale', '本项原消息已变化，请回原消息重新核对'), 'a changed original')

    def test_t01_counterexample_a_send_day_due_for_tonight_work_states_no_handback(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍。', due='2026-11-04')
        result, rows, listed, _ = self._run(payload, [reading], 'T01-send-day-due')
        item, = listed  # Off-contract send-day due (发送日不作截止): adopted here, held for 今晚做练习二 (see RESULT); never a handback.
        self.assertNotEqual(item['due_kind'], 'handback')
        self.assertIn('2026-11-04', (item['complete_on'], item['due_on']))
        self._replay_adds_nothing('T01-send-day-due')


class ContinuedSupplementVariantTests(unittest.TestCase):
    """Fictional variants of T01's shared cause, not frozen contract cases: the same teacher's follow-up in the same source,
    within two minutes, pointing back to one listed object and only adding a step to it (刚才的朗读还要家长签字) is that one
    item's supplement. Another teacher or source, a later or earlier message, two items it could mean, a question, change,
    condition, negation, subject, or a day, count, title or worksheet of its own, a second clause or no pointer binds
    nothing: the whole batch stays for the existing retry, nothing saved, originals kept. Fixed receipts prove only the
    program layer."""
    setUp, _use_replies, _day, _proposal = (DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies,
                                            DailyListFrozenTests._day, DailyListFrozenTests._proposal)
    _report, _run, _replay_adds_nothing, _job = (DailyListFrozenTests._report, DailyListFrozenTests._run,
                                                 DailyListFrozenTests._replay_adds_nothing, DailyListFrozenTests._job)

    def _ledger(self, *later, first='今晚朗读《荷塘》2遍。'):
        """Each listed outcome of the first original and the supplement goals the shared ledger binds to it.
        later: (text, seconds after the list, publisher, source) of each following original."""
        sent = dt.datetime(2026, 11, 4, 18, tzinfo=agent.TZ)
        evidence = [dict(ref='message:synthetic-group:11', text=first, time=sent.isoformat(), publisher='cn-teacher-a')]
        evidence += [dict(ref='message:%s:%d' % (source, 12 + i), text=text, time=(sent + dt.timedelta(seconds=gap)).isoformat(),
                          publisher=publisher) for i, (text, gap, publisher, source) in enumerate(later)]
        for i, e in enumerate(evidence):
            e.update(kind='text', content_incomplete=False, unread=False, attachments=[], message_order=str(11 + i))
        return {a['quote']: [s['goal'] for s in a['supplements']] for a in agent._school_native_actions(evidence)
                if a['ref'] == evidence[0]['ref']}

    def test_the_ledger_binds_a_pointer_back_with_one_added_step(self):
        for text, goal in (('刚才的朗读还要家长签字。', '朗读还要家长签字'), ('上面的朗读也要家长签字', '朗读也要家长签字'),
                           ('刚刚布置的朗读还需要家长签字！', '朗读还需要家长签字'), ('前面的《荷塘》也请家长签字。', '《荷塘》也请家长签字')):
            self.assertEqual(self._ledger((text, 120, 'cn-teacher-a', 'synthetic-group')), {'今晚朗读《荷塘》2遍': [goal]}, text)
        self.assertEqual(self._ledger(('刚才的朗读还要家长签字。', 60, 'cn-teacher-a', 'synthetic-group'), first='今晚朗读《荷塘》2遍；抄写生字一遍。'),
                         {'今晚朗读《荷塘》2遍': ['朗读还要家长签字'], '抄写生字一遍': []}, 'only the item it names')

    def test_the_ledger_binds_nothing_without_one_clear_continuation(self):
        same = ('cn-teacher-a', 'synthetic-group')
        unbound = {'今晚朗读《荷塘》2遍': []}
        for later in (('刚才的朗读还要家长签字。', 60, 'cn-teacher-b', 'synthetic-group'),  # another teacher
                      ('刚才的朗读还要家长签字。', 60, 'cn-teacher-a', 'synthetic-other'),  # another source or child binding
                      ('刚才的朗读还要家长签字。', 600, *same), ('刚才的朗读还要家长签字。', -60, *same),  # no near, later context
                      ('刚才的朗读还要家长签字吗？', 60, *same), ('刚才的朗读如果读完还要家长签字。', 60, *same),
                      ('刚才的朗读还要改为家长签字。', 60, *same), ('刚才的朗读也不用家长签字。', 60, *same),
                      ('刚才的语文朗读还要家长签字。', 60, *same), ('刚才的朗读还要家长明早签字。', 60, *same),
                      ('刚才的朗读还要再读1遍。', 60, *same), ('刚才的朗读还要抄写生字两遍。', 60, *same),
                      ('刚才的朗读还要背诵《春》。', 60, *same), ('刚才的朗读还要完成练习册。', 60, *same),
                      ('刚才的朗读还要家长签字，明天体育课带跳绳。', 60, *same), ('刚才的朗读还要家长签字。明天体育课带跳绳。', 60, *same),
                      ('朗读还要家长签字。', 60, *same), ('刚才的背诵还要家长签字。', 60, *same)):
            self.assertEqual(self._ledger(later), unbound, later)
        self.assertEqual(self._ledger(('刚才的朗读还要家长签字。', 60, *same), first='今晚朗读《荷塘》2遍；朗读《春》1遍。'),
                         {'今晚朗读《荷塘》2遍': [], '朗读《春》1遍': []}, 'two items it could mean')
        with self.assertRaises(agent.AgentError) as both:  # two lists' items it could mean
            self._ledger(('今晚朗读《春》1遍。', 30, *same), ('刚才的朗读还要家长签字。', 60, *same))
        self.assertIn('学校补充同时对应多项作业', str(both.exception))

    def test_the_continued_step_joins_only_the_item_it_names(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍；抄写生字一遍。'),
                                   ('18:01', '语文老师甲', 'cn-teacher-a', '刚才的朗读还要家长签字。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。')
        copying = self._proposal('抄写生字一遍', refs[:1], '语文', '抄写生字一遍。')
        result, rows, listed, _ = self._run(payload, [reading, copying], 'T01-variant-two-items')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        read, = [i for i in listed if '《荷塘》' in i['body']]
        copy, = [i for i in listed if '抄写生字一遍' in i['body']]
        self.assertEqual((read['publications'], copy['publications']), (refs, refs[:1]), 'each keeps its own originals')
        self.assertIn('签字', read['body'])
        self.assertNotIn('签字', copy['body'])
        self.assertNotIn('抄写', read['body'])
        self._replay_adds_nothing('T01-variant-two-items')

    def _rejected(self, messages, proposals, case):
        """The whole batch stays for the original retry limit: nothing saved, originals kept, no further receipt."""
        payload, refs = self._day(messages)
        result, rows, listed, _ = self._run(payload, proposals(refs), case)
        self.assertEqual((result['failed'], result['processed'], result['created'], listed), (1, 0, 0, []))
        self._use_replies(payload, [dict(proposals=proposals(refs))] * (agent.MAX_ATTEMPTS - 1))
        for minutes in (7, 18, 60):  # attempt 2 after its 5-minute wait, attempt 3 after 10 more, then none
            agent.run_once(self.app, self._ran_at + dt.timedelta(minutes=minutes))
        job, processed, originals, items = self._job()
        self.assertEqual(self.model.call_count, agent.MAX_ATTEMPTS, 'one fixed receipt per attempt, never past the original limit')
        self.assertEqual((job['attempts'], job['done'], job['next_try'], processed, items), (agent.MAX_ATTEMPTS, 0, '', [0, 0], 0))
        self.assertEqual(originals, payload['messages'])
        return job['error']

    def test_another_teachers_follow_up_is_no_supplement(self):
        error = self._rejected([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。'),
                                ('18:02', '语文老师乙', 'cn-teacher-b', '刚才的朗读还要家长签字。')],
                               lambda refs: [self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。')],
                               'T01-variant-other-teacher')
        self.assertIn('学校补充要求未归到对应作业', error)

    def test_a_follow_up_two_items_could_mean_is_no_supplement(self):
        error = self._rejected([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍；朗读《春》1遍。'),
                                ('18:02', '语文老师甲', 'cn-teacher-a', '刚才的朗读还要家长签字。')],
                               lambda refs: [self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。'),
                                             self._proposal('朗读《春》1遍', refs[:1], '语文', '朗读《春》1遍。')],
                               'T01-variant-two-antecedents')
        self.assertIn('学校补充要求未归到对应作业', error)


class PointerBackIdentityHoldoutTests(unittest.TestCase):
    """Root's R16 holdout and its neighbours, fictional, on the same run_once→Store→calendar path: one shared nickname
    proves no publisher, so a follow-up pointing back (刚刚的朗读还要家长签字) joins an earlier message's item only from the
    same stable sender id and source and the one message it can mean. A missing or another id, another source or an
    unclear object keeps the whole batch for the existing retry (no new budget, nothing saved, originals kept); a sole
    message without an id still stands as its own action. Fixed receipts prove only the program layer."""
    setUp, _use_replies, _proposal = DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies, DailyListFrozenTests._proposal
    _report, _run, _replay_adds_nothing, _job = (DailyListFrozenTests._report, DailyListFrozenTests._run,
                                                 DailyListFrozenTests._replay_adds_nothing, DailyListFrozenTests._job)
    _rejected = ContinuedSupplementVariantTests._rejected
    R16 = (('18:00', '今晚朗读《暮色》3遍。'), ('18:01', '刚刚的朗读还要家长签字。'))

    def _day(self, messages, day='2026-11-04'):
        """messages: (HH:MM, stable sender id or None when missing, text), all sent under one shared nickname."""
        payload = self.fixture.payload(cursor=str(100 + len(messages)))
        payload['messages'] = [dict(id=str(101 + i), message_order=str(101 + i), time=day + 'T' + hm + ':00+08:00', kind='text',
                                    sender='虚构语文老师', text=text, unread=False, **({'sender_id': p} if p else {}))
                               for i, (hm, p, text) in enumerate(messages)]
        self.store.ingest(payload)
        return payload, ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]

    def _r16(self, refs, quote='今晚朗读《暮色》3遍'):
        """R16-fixed-exchange.json's one receipt: one reading-and-signature item citing every given original."""
        return [fixtures.school_proposal(
            title_quote=quote, evidence=[dict(ref=r) for r in refs], learning_subject='语文', task_title='语文：' + quote,
            task_goal=quote + '；朗读后家长签字。', task_state='ready', task_reason='虚构固定回执，只验校验/保存/展示。',
            task_purpose='learning')]

    def _held(self, ids, first, case):
        error = self._rejected([(hm, i, text) for (hm, text), i in zip(((self.R16[0][0], first), self.R16[1]), ids)],
                               lambda refs: self._r16(refs, first.rstrip('。')), case)
        self.assertIn('学校补充要求未归到对应作业', error)

    def test_r16_one_nickname_without_sender_ids_merges_nothing(self):
        self._held((None, None), self.R16[0][1], 'R16-missing-ids')

    def test_one_nickname_with_one_missing_sender_id_merges_nothing(self):
        self._held((None, 'cn-teacher-a'), self.R16[0][1], 'R16-first-id-missing')

    def test_one_nickname_with_the_later_sender_id_missing_merges_nothing(self):
        self._held(('cn-teacher-a', None), self.R16[0][1], 'R16-later-id-missing')

    def test_one_nickname_with_another_sender_id_merges_nothing(self):
        self._held(('cn-teacher-a', 'cn-teacher-b'), self.R16[0][1], 'R16-other-id')

    def test_one_nickname_with_another_sender_id_merges_nothing_outside_the_ledger(self):
        # A sole noun-first reading stays with the general reader, the path R16 itself took.
        self._held(('cn-teacher-a', 'cn-teacher-b'), '《暮色》朗读3遍。', 'R16-other-id-noun-first')

    def test_the_same_stable_sender_id_keeps_one_item_with_both_originals(self):
        for first, case in (('今晚朗读《暮色》3遍。', 'R16-same-id'), ('《暮色》朗读3遍。', 'R16-same-id-noun-first')):
            with self.subTest(case):
                self.doCleanups()
                self.setUp()
                payload, refs = self._day([(self.R16[0][0], 'cn-teacher-a', first), (self.R16[1][0], 'cn-teacher-a', self.R16[1][1])])
                result, rows, listed, _ = self._run(payload, self._r16(refs, first.rstrip('。')), case)
                self.assertEqual((result['failed'], result['processed'], len(rows)), (0, 2, 1))
                item, = listed
                self.assertEqual(item['publications'], refs, 'both originals stay cited')
                self.assertIn('签字', item['body'])
                self._replay_adds_nothing(case)

    def test_messages_without_sender_ids_still_stand_as_their_own_actions(self):
        payload, refs = self._day([('18:00', None, self.R16[0][1]), ('18:01', None, '抄写生字一遍。')])
        result, rows, listed, _ = self._run(payload, [
            self._proposal('今晚朗读《暮色》3遍', refs[:1], '语文', '今晚朗读《暮色》3遍。'),
            self._proposal('抄写生字一遍', refs[1:], '语文', '抄写生字一遍。')], 'R16-missing-ids-own-actions')
        self.assertTrue(all('sender_id' not in m for m in payload['messages']))
        self.assertEqual((result['failed'], result['processed'], len(rows), len(listed)), (0, 2, 2, 2))
        self.assertEqual(sorted(i['publications'] for i in listed), [refs[:1], refs[1:]], 'each keeps only its own original')
        self._replay_adds_nothing('R16-missing-ids-own-actions')

    def test_the_shared_check_needs_the_one_same_source_message_it_names(self):
        sent = dt.datetime(2026, 11, 4, 18, tzinfo=agent.TZ)

        def unproven(*rows):
            evidence = [dict(ref='message:%s:%d' % (source, 101 + i), text=text, time=(sent + dt.timedelta(minutes=i)).isoformat(),
                             publisher=publisher, kind='text', content_incomplete=False, unread=False, attachments=[],
                             message_order=str(101 + i)) for i, (source, publisher, text) in enumerate(rows)]
            return agent._school_native_pointer_unproven(evidence, {e['ref'] for e in evidence})
        g, a, follow = 'synthetic-group', 'publisher:a', self.R16[1][1]
        self.assertFalse(unproven((g, a, '《暮色》朗读3遍。'), (g, a, follow)))
        for rows in (((g, '', '《暮色》朗读3遍。'), (g, '', follow)),  # one nickname, both ids missing
                     ((g, a, '《暮色》朗读3遍。'), (g, 'publisher:b', follow)),  # another id
                     ((g, a, '《暮色》朗读3遍。'), ('synthetic-other', a, follow)),  # another source
                     ((g, a, '《暮色》背诵3遍。'), (g, a, follow)),  # an object no cited original names
                     ((g, a, '《暮色》朗读3遍。'), (g, a, '《春》朗读1遍。'), (g, a, follow))):  # two it could mean
            self.assertTrue(unproven(*rows), rows)
        self.assertFalse(unproven((g, '', follow)), 'a follow-up cited alone keeps the general checks')
        self.assertFalse(unproven((g, '', '今晚朗读《暮色》3遍。'), (g, '', '抄写生字一遍。')), 'no pointer, no new check')


class ReplySlipChoiceVariantTests(unittest.TestCase):
    """Fictional variants of T10's shared cause, not frozen contract cases, on the same run_once→Store→calendar path: a choice
    between answers, people or receivers (quoted or not, options of any length, the activity's own days inside options) and
    the same item's undated signing step (with or without 然后/再) keep both role days; a real day alternative, a condition,
    options naming this item's own role or day, or another item's day still leave the day unknown. Fixed receipts again
    prove only the program layer."""
    setUp, _use_replies, _day, _proposal = (DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies,
                                            DailyListFrozenTests._day, DailyListFrozenTests._proposal)
    _report, _run, _replay_adds_nothing = DailyListFrozenTests._report, DailyListFrozenTests._run, DailyListFrozenTests._replay_adds_nothing
    HANDBACK = '孩子11月5日早上交给班主任。'

    def _slip(self, text, case, goal, submission='孩子明早交给班主任'):
        payload, refs = self._day([('19:05', '班主任', 'head-teacher', text)])
        slip = self._proposal(text.rstrip('。'), refs, '', goal, due='2026-11-05', purpose='admin', submission=submission)
        return self._run(payload, [slip], case)

    def _both_roles(self, text, case, goal, words, **slip):
        result, rows, listed, (on_day, visible) = self._slip(text, case, goal, **slip)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['kind'], item['category'], item['complete_on'], item['due_on'], item['due_kind']),
                         ('task', 'todo', '2026-11-04', '2026-11-05', 'handback'))
        for w in words: self.assertIn(w, item['body'])
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing(case)

    def test_another_choice_between_quoted_options_keeps_both_roles(self):
        self._both_roles('今晚请家长在《午餐意向单》勾选“同意”或“不同意”，然后签字；孩子明早交给班主任。', 'V-choice-quoted',
                         '今晚家长在《午餐意向单》勾选“同意”或“不同意”，然后签字；' + self.HANDBACK, ('“同意”', '“不同意”', '签字'))

    def test_three_options_and_a_then_signing_step_keep_both_roles(self):
        self._both_roles('今晚请家长在《社团报名表》圈选‘美术’、‘篮球’或‘合唱’，再签字；孩子明早交给班主任。', 'V-choice-three',
                         '今晚家长在《社团报名表》圈选‘美术’、‘篮球’或‘合唱’，再签字；' + self.HANDBACK, ('‘美术’', '‘篮球’', '‘合唱’', '签字'))

    def test_the_same_items_signing_step_without_a_choice_keeps_both_roles(self):
        self._both_roles('今晚请家长核对《通讯录信息表》，然后签字；孩子明早交回。', 'V-step-sign',
                         '今晚家长核对《通讯录信息表》，然后签字；孩子11月5日早上交回。', ('核对', '签字', '交回'), submission='孩子明早交回')

    def _unknown(self, text, case, goal):
        result, rows, listed, (on_day, visible) = self._slip(text, case, goal)
        self._report(case=case + '-outcome', listed=listed, result={k: result[k] for k in ('failed', 'processed', 'created')})
        item, = listed
        self.assertEqual((result['failed'], result['processed'], item['kind'], item['complete_on']), (0, 1, 'school', ''),
                         'kept for review: a day the original leaves open is never read as both role days')
        self.assertNotEqual(item['due_kind'], 'handback')

    def test_a_real_day_alternative_stays_unknown(self):
        self._unknown('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任。', 'V-day-alternative',
                      '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子11月5日或6日交给班主任。')

    def test_options_naming_the_activitys_days_keep_the_slips_own_roles(self):
        # Revised negative control (Root P5): the days inside ‘明天出发’或‘后天出发’ are the trip's answer, not this slip's; its
        # own 今晚…签字 and 明早交 stay outside the options. Options naming this slip's own role or day stay unknown below.
        self._both_roles('今晚请家长在《研学活动回执》勾选‘明天出发’或‘后天出发’，然后签字；孩子明早交给班主任。', 'V-day-options',
                         '今晚家长在《研学活动回执》勾选‘明天出发’或‘后天出发’，然后签字；' + self.HANDBACK, ('‘明天出发’', '‘后天出发’'))

    def test_a_conditional_handback_stays_unknown(self):
        self._unknown('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；如果参加，孩子明早交给班主任。', 'V-condition',
                      '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；如果参加，' + self.HANDBACK)

    def test_another_items_day_is_not_the_slips(self):
        text = '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；数学练习册明早交给数学老师。'
        payload, refs = self._day([('19:05', '班主任', 'head-teacher', text)])
        slip = self._proposal('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字', refs, '',
                              '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字。', purpose='admin')
        book = self._proposal('数学练习册明早交给数学老师', refs, '数学', '数学练习册11月5日早上交给数学老师。', due='2026-11-05')
        result, rows, listed, _ = self._run(payload, [slip, book], 'V-sibling-day')
        self._report(case='V-sibling-day-outcome', listed=listed, result={k: result[k] for k in ('failed', 'processed', 'created')})
        receipt, = [i for i in listed if '回执' in i['body']]
        workbook, = [i for i in listed if '练习册' in i['body']]
        self.assertEqual((receipt['complete_on'], receipt['due_on'], receipt['due_kind']), ('', '', ''), "the workbook's day is never the slip's")
        self.assertEqual((workbook['due_on'], workbook['due_kind']), ('2026-11-05', 'handback'))

    def test_the_role_reader_takes_a_closed_choice_and_the_same_items_signing_step(self):
        cited = lambda text: [dict(ref='message:s:1', text=text, time='2026-11-04T19:05:00+08:00')]
        read = lambda text: agent._school_role_days(text, cited(text), [])
        positives = ('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《午餐意向单》勾选“同意”或“不同意”，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《社团报名表》圈选‘美术’、‘篮球’或者‘合唱’，再签字；孩子明早交给班主任。',
                     '今晚请家长核对《通讯录信息表》，然后签字；孩子明早交回。',
                     # Revised controls: a 或 between people, receivers or unquoted answers and options holding the activity's
                     # own days name no day of this slip; the choice stays in its words for the family.
                     '今晚请家长或孩子在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》勾选参加或不参加，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘明天出发’或‘后天出发’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，然后签字；孩子明早交给班主任或课代表。',
                     '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，签字后拍照上传；孩子明早交纸质版。',
                     '今晚请家长在《参观回执》勾选‘同意参加本学期全部四次周末社区志愿服务活动’或‘不同意’，然后签字；孩子明早交回。')
        missed = [text for text in positives if read(text) != ({'2026-11-04'}, '2026-11-05')]
        self.assertEqual(missed, [], 'each closed choice or same-item signing step keeps both role days')

    def test_the_role_reader_still_leaves_open_days_unknown(self):
        cited = lambda text: [dict(ref='message:s:1', text=text, time='2026-11-04T19:05:00+08:00')]
        read = lambda text, others=(): agent._school_role_days(text, cited(text), list(others))
        negatives = ('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任。',  # a real day alternative
                     '今晚或明晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》签字；孩子明天交或后天交给班主任。',
                     '今晚请家长在《参观回执》签字后拍照上传或明早交纸质版；孩子明早交给班主任。',  # a way bound to its own day
                     '今晚请家长在《研学活动回执》勾选‘明早交’或‘后天交’，然后签字。',  # options setting this slip's own day
                     '今晚请家长在《研学活动回执》签字；孩子‘明早’或‘后天’交给班主任。',  # its handback day only in options
                     '今晚请家长在《研学活动回执》勾选‘同意签字’或‘不同意’，然后签字；孩子明早交给班主任。',  # an option naming a role
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或许交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；如果参加，孩子明早交给班主任。',  # a condition
                     '若参加，今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任吗？',  # a question
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；回执取消，明早不用交。',  # a withdrawal
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早可能交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后交给班主任；孩子明早交回。',  # a handback step
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，明早签字；孩子明早交给班主任。',  # a step of its own day
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’；孩子明早交给班主任。',  # no finishing step
                     '后天请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。')  # done after its handback
        self.assertEqual([text for text in negatives if read(text) is not None], [])
        shared = '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。'
        self.assertIsNone(read(shared, ['孩子明早交给班主任']), "another proposal's quote of the range")
        other = cited(shared) + [dict(ref='message:s:2', text='研学活动改到后天。', time='2026-11-04T19:30:00+08:00')]
        self.assertIsNone(agent._school_role_days(shared, other, []), 'another cited original naming a day')


class RootRoleHoldoutTests(unittest.TestCase):
    """Root's independent fictional role-day holdouts, on the same run_once→Store→calendar path with Root's receipt shape:
    the goal is the original and the submission its last sentence word for word (no receiver added). A non-day choice
    (answers, receivers, people, ways) keeps both role days and stays in the family's words; a day the original leaves to
    choose stays open in both the stored item and its listed projection, while another role's explicit day is kept."""
    setUp, _use_replies, _day, _proposal = (DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies,
                                            DailyListFrozenTests._day, DailyListFrozenTests._proposal)
    _report, _run, _replay_adds_nothing = DailyListFrozenTests._report, DailyListFrozenTests._run, DailyListFrozenTests._replay_adds_nothing

    def _root(self, case, text, due='2026-11-05'):
        payload, refs = self._day([('19:05', '虚构班主任', 'root-fiction-teacher', text)])
        slip = self._proposal(text.rstrip('。'), refs, '', text, due=due, purpose='admin', submission=text.rsplit('；', 1)[-1].rstrip('。'))
        return self._run(payload, [slip], case)

    def _clear(self, case, text, kept):
        result, rows, listed, (on_day, visible) = self._root(case, text)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed  # one slip: no second task, no trip or receiver chosen for the family
        self.assertEqual((item['kind'], item['category'], item['complete_on'], item['due_on'], item['due_kind']),
                         ('task', 'todo', '2026-11-04', '2026-11-05', 'handback'))
        self.assertEqual(item['body'], text)
        self.assertIn(kept, item['title'], 'the choice stays in its own words')
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing(case)

    def test_p2_a_receiver_choice_is_no_day_choice(self):
        self._clear('ROOT-P2', '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，然后签字；孩子明早交给班主任或课代表。', '交给班主任或课代表')

    def test_p3_the_same_items_signing_step_needs_no_then(self):
        self._clear('ROOT-P3', '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，签字后拍照上传；孩子明早交纸质版。', '签字后拍照上传')

    def test_p4_unquoted_answers_are_as_clear(self):
        self._clear('ROOT-P4', '今晚请家长在《研学活动回执》勾选参加或不参加，然后签字；孩子明早交给班主任。', '勾选参加或不参加')

    def test_p5_the_trips_days_inside_options_are_not_the_slips(self):
        self._clear('ROOT-P5', '今晚请家长在《出行意向回执》勾选‘明天出发’或‘后天出发’，然后签字；孩子明早交回执给班主任。',
                    '‘明天出发’或‘后天出发’')

    def _open(self, case, text, due, field, explicit):
        result, rows, listed, _ = self._root(case, text, due)
        self._report(case=case + '-outcome', listed=listed, stored=[dict(state=r['state'], due=r['due']) for r in rows])
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual(item[field], '', 'a day the original leaves to choose is never one certain day')
        self.assertEqual(item['body'], text)
        return item, rows

    def test_n1_a_signing_day_choice_keeps_only_the_explicit_handback(self):
        item, _ = self._open('ROOT-N1', '今晚或明晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子后天交给班主任。',
                             '2026-11-06', 'complete_on', '2026-11-06')
        self.assertEqual((item['due_on'], item['due_kind']), ('2026-11-06', 'handback'), 'the explicit handback day is kept')

    def test_n2_a_handback_day_choice_is_open_in_the_stored_item_and_its_projection(self):
        item, rows = self._open('ROOT-N2', '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任。',
                                '2026-11-05', 'due_on', '')
        self.assertEqual((item['kind'], item['due_kind']), ('school', ''), 'kept for review with no deadline shown')
        self.assertEqual([r['due'] for r in rows], [''], 'the stored item holds no due either')

    def test_n3_a_condition_keeps_its_completion_open(self):
        item, _ = self._open('ROOT-N3', '如果参加，今晚请家长在《研学活动回执》签字；如果不参加，明晚再填写；孩子后天交给班主任。',
                             '2026-11-06', 'complete_on', '2026-11-06')
        self.assertEqual((item['due_on'], item['due_kind']), ('2026-11-06', 'handback'))

    def test_the_deadline_reader_keeps_a_day_choice_open_and_a_single_day(self):
        import family_agenda
        sent = '2026-11-04'
        self.assertEqual(family_agenda.deadline('孩子明早或后天交给班主任', sent), '')
        self.assertEqual(family_agenda.deadline('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任', sent), '')
        self.assertEqual(family_agenda.deadline('孩子明天交或后天交给班主任', sent), '')
        self.assertEqual(family_agenda.deadline('孩子后天交给班主任', sent), '2026-11-06', 'an explicit single day stays')
        self.assertEqual(family_agenda.deadline('今晚或明晚请家长签字；孩子后天交给班主任', sent), '2026-11-06',
                         "another role's day choice does not clear this explicit day")
        self.assertEqual(family_agenda.deadline('孩子后天交给班主任或课代表', sent), '2026-11-06', 'a receiver choice names no day')


def serve_t02(port):
    """Browser fixture: T02 saved by the real run_once into this disposable Store, read through the real app HTTP server
    as of 2026-11-04 20:00 Asia/Shanghai. Opening a page calls no model; no collector, device or household path is used."""
    case = DailyListFrozenTests('test_t02_independent_supply_is_its_own_admin_item_on_its_own_day')
    case.setUp()
    try:
        payload, proposals = case._t02_batch()
        case._run(payload, proposals, 'T02-served')
        app, fixed = case.app, case.now

        def deny(*args, **kwargs):
            raise AssertionError('opening the list or calendar must not call a model')
        app.family_llm._chat_json = deny

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
                return cls(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=value.tzinfo)

            def date(self):
                return FrozenDate(self.year, self.month, self.day)

        class FrozenDate(dt.date):
            @classmethod
            def today(cls):
                return cls(fixed.year, fixed.month, fixed.day)
        dt.datetime, dt.date = FrozenDateTime, FrozenDate
        app.prepare_assets()
        server = app.ThreadingHTTPServer(('127.0.0.1', port), app.Handler)
        print('T02 Store served', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        case.doCleanups()


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['--serve-t02']:
        serve_t02(int(sys.argv[2]))
    else:
        unittest.main()

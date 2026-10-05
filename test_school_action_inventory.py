"""Synthetic school action/condition ownership, using the real intake transaction.

Model receipts are fixed local substitutes, not extraction-quality evidence.
No household data, collector, device or external model is used. Missing an
independent outcome must remain retryable; an omitted literal standard of a
known action should instead be compiled from the complete original text.
"""
import base64
import copy
import datetime as dt
import io
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import test_agent as fixtures
import test_school_native_coverage as native


class SchoolActionInventoryTests(unittest.TestCase):
    # Reuse the isolated family, disabled collectors and bounded model seam.
    setUp = native.SchoolNativeCoverageTests.setUp
    _ingest = native.SchoolNativeCoverageTests._ingest
    _use_replies = native.SchoolNativeCoverageTests._use_replies
    _assert_rejected_batch = native.SchoolNativeCoverageTests._assert_rejected_batch

    def proposal(self, quote, refs, *, goal=None, due='', subject='英语', purpose='learning'):
        return fixtures.school_proposal(
            title_quote=quote, due=due, evidence=[dict(ref=ref) for ref in refs],
            learning_subject=subject, task_title=(subject + '：' if subject else '') + quote,
            task_goal=goal or quote, task_state='ready', task_purpose=purpose,
            task_reason='虚构回执，实际要求须按各自完整原文核对。')

    def run_receipt(self, payload, proposals):
        self._use_replies(payload, [dict(proposals=proposals)])
        return agent.run_once(self.app, self.now)

    def saved(self, payload, result, count):
        self.assertEqual((result['failed'], result['processed']), (0, len(payload['messages'])),
                         'complete native requirements should be compiled without a needless retry')
        self.assertEqual(self.model.call_count, 1)
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            self.assertEqual(len(rows), count, 'one record per independent outcome, not per procedural step')
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                             payload['messages'], 'compilation must not rewrite the originals')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            accepted = [r for r in rows if r['state'] == 'accepted']
            self.assertEqual(set(tasks), {r['task_id'] for r in accepted})
            for row in accepted:
                self.assertEqual((tasks[row['task_id']]['action'], tasks[row['task_id']]['due'],
                                  tasks[row['task_id']]['original_status']),
                                 (row['body'], row['due'], '待跟进'))
        return rows

    def test_numbered_actions_without_announced_count_cannot_lose_second_action(self):
        payload, refs = self._ingest([
            '英语，明天完成：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06')
        self._assert_rejected_batch(payload, self.run_receipt(payload, [reading]))

    def test_semicolon_actions_cannot_be_covered_by_one_message_reference(self):
        payload, refs = self._ingest(['英语作业：朗读Unit 2课文两遍；完成练习卷第1–3题。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs)
        self._assert_rejected_batch(payload, self.run_receipt(payload, [reading]))

    def test_exercise_deadline_in_next_sentence_is_not_borrowed_by_reading(self):
        payload, refs = self._ingest([
            '英语作业：朗读Unit 2课文两遍。完成练习卷第1–3题，明天交。'])
        proposals = [self.proposal(quote, refs, due='2026-10-06') for quote in
                     ('朗读Unit 2课文两遍', '完成练习卷第1–3题')]
        rows = self.saved(payload, self.run_receipt(payload, proposals), 2)
        reading = next(r for r in rows if '朗读' in r['title'])
        exercise = next(r for r in rows if '练习卷' in r['title'])
        self.assertEqual((reading['due'], reading['state']), ('', 'pending'))
        self.assertEqual((exercise['due'], exercise['state']), ('2026-10-06', 'accepted'))
        self.assertNotIn('明天交', reading['body'])
        self.assertIn('明天交', exercise['body'])

    def test_reading_deadline_in_next_sentence_is_not_borrowed_by_exercise(self):
        payload, refs = self._ingest([
            '英语作业：完成练习卷第1–3题。朗读Unit 2课文两遍，明天完成。'])
        proposals = [self.proposal(quote, refs, due='2026-10-06') for quote in
                     ('完成练习卷第1–3题', '朗读Unit 2课文两遍')]
        rows = self.saved(payload, self.run_receipt(payload, proposals), 2)
        reading = next(r for r in rows if '朗读' in r['title'])
        exercise = next(r for r in rows if '练习卷' in r['title'])
        self.assertEqual((exercise['due'], exercise['state']), ('', 'pending'))
        self.assertEqual((reading['due'], reading['state']), ('2026-10-06', 'accepted'))
        self.assertNotIn('明天完成', exercise['body'])

    def test_short_model_goal_compiles_all_single_sheet_standards_without_retry(self):
        payload, refs = self._ingest([
            '英语，明天完成一份练习卷：单面打印；完成第1–3题；'
            '完成后自查并请家长签字；第4题选做，不作完成要求。'])
        exercise = self.proposal('完成第1–3题', refs, due='2026-10-06')
        row, = self.saved(payload, self.run_receipt(payload, [exercise]), 1)
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        for clause in ('单面打印', '完成第1–3题', '完成后自查并请家长签字', '第4题选做', '不作完成要求'):
            self.assertIn(clause, row['body'], 'retain the original standard instead of asking the model to repeat it')

    def test_preparation_before_main_action_is_compiled_into_the_same_worksheet(self):
        payload, refs = self._ingest([
            '英语作业：先单面打印练习卷；明天完成练习卷第1–3题并自查；请家长在这份练习卷上签字。'])
        exercise = self.proposal('完成练习卷第1–3题', refs, due='2026-10-06')
        row, = self.saved(payload, self.run_receipt(payload, [exercise]), 1)
        self.assertTrue(row['title'].startswith('英语：'))
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        for clause in ('先单面打印练习卷', '明天完成练习卷第1–3题并自查', '请家长在这份练习卷上签字'):
            self.assertIn(clause, row['body'], 'preparation belongs to this worksheet even before its answer step')
        self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)

    def test_entire_optional_exercise_remains_optional_and_outside_required_tasks(self):
        payload, refs = self._ingest([
            '英语作业：明天完成练习卷第4题（选做，不要求提交）。'])
        exercise = self.proposal('完成练习卷第4题', refs, due='2026-10-06',
                                 goal='明天完成练习卷第4题（选做，不要求提交）。', purpose='optional')
        exercise.update(task_state='review', task_reason='整项选做，不自动加入必做事项。')
        row, = self.saved(payload, self.run_receipt(payload, [exercise]), 1)
        self.assertEqual((row['state'], row['task_id']), ('pending', ''))
        brief = json.loads(row['plan'])['school_task']
        self.assertEqual((brief['purpose'], brief['state']), ('optional', 'review'))
        for clause in ('完成练习卷第4题', '选做', '不要求提交'):
            self.assertIn(clause, row['body'])
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)

    def test_shared_before_deadline_qualifier_is_retained_for_both_actions(self):
        payload, refs = self._ingest([
            '英语，10月6日前完成两项要求：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。'])
        quotes = ('朗读Unit 2课文两遍', '完成练习卷第1–3题')
        proposals = [self.proposal(quote, refs, due='2026-10-06') for quote in quotes]
        rows = self.saved(payload, self.run_receipt(payload, proposals), 2)
        for own, foreign in (quotes, quotes[::-1]):
            row = next(r for r in rows if own in r['title'])
            self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
            self.assertIn(own, row['body'])
            self.assertIn('10月6日前', row['body'], 'the date alone must not erase the before qualifier')
            self.assertNotIn(foreign, row['body'])
            self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')

    def test_adjacent_unread_image_keeps_body_reviewable_through_the_save_transaction(self):
        self.source['platform'] = 'qq'
        self.fixture.config()
        payload = self.fixture.payload(cursor='12')
        common = dict(sender='虚构英语老师', sender_id='synthetic-teacher-1')
        payload['messages'] = [
            dict(common, id='11', message_order='11', time=self.now.isoformat(),
                 kind='text', unread=False, text='明天朗读Unit 2课文两遍'),
            dict(common, id='12', message_order='12', time=(self.now + dt.timedelta(seconds=30)).isoformat(),
                 kind='image', unread=True, text='[图片]'),
        ]
        self.store.ingest(payload)
        refs = ['message:' + self.source['id'] + ':' + message['id'] for message in payload['messages']]
        # The existing original-material fixture's synthetic one-pixel PNG has
        # real isolated bytes and a real attachment link, but no read draft.
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII=')
        upload = self.app.save_upload(io.BytesIO(png), len(png), 'synthetic-reading.png')
        self.store.message_attachment(dict(child_id='child-1', source_id=self.source['id'],
                                          message_id='12', attachment_id=upload['id'], action='attach'), dict)
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06',
                                goal='明天朗读Unit 2课文两遍')
        reading.update(task_state='review', task_reason='正文要求已读，相邻图片原件尚未读全。')

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, data_path), ('family_agent_selection', self.app.DATA))
            evidence = json.loads(messages[-1]['content'])['evidence']
            self.assertEqual([(e['ref'], e['text']) for e in evidence],
                             list(zip(refs, [m['text'] for m in payload['messages']])))
            self.assertTrue(evidence[0]['publisher'])
            self.assertEqual(evidence[0]['publisher'], evidence[1]['publisher'])
            self.assertEqual([e['related_messages'] for e in evidence], [refs, refs])
            self.assertEqual([(e['kind'], e['content_incomplete']) for e in evidence],
                             [('text', False), ('image', True)])
            self.assertEqual(evidence[0]['attachments'], [])
            self.assertEqual(evidence[1]['attachments'], [dict(name='synthetic-reading.png', mime='image/png')])
            return copy.deepcopy(dict(proposals=[reading]))

        self.model.side_effect = reply
        row, = self.saved(payload, agent.run_once(self.app, self.now), 1)
        self.assertEqual((row['state'], row['task_id']), ('pending', ''))
        self.assertIn('朗读Unit 2课文两遍', row['body'])
        plan = json.loads(row['plan'])
        self.assertEqual((plan['school_task']['purpose'], plan['school_task']['state']), ('learning', 'review'))
        self.assertIn('未读', plan['school_task']['reason'])
        self.assertFalse(plan.get('school_native_action'), 'unread originals remain on the original-material review route')
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
        with self.store._db() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')], [1, 1])
            self.assertEqual([tuple(r) for r in c.execute('SELECT message_id,upload_id FROM agent_message_attachments')],
                             [('12', upload['id'])])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_message_drafts').fetchone()[0], 0)
        self.assertEqual((self.fixture.data / 'uploads' / upload['id']).read_bytes(), png)

    def test_shared_notice_supplement_is_compiled_only_into_its_exercise(self):
        payload, refs = self._ingest([
            '英语，明天完成：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题。',
            '补充英语练习卷：单面打印；完成后自查并请家长签字；第4题选做。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs[:1], due='2026-10-06')
        exercise = self.proposal('完成练习卷第1–3题', refs, due='2026-10-06')
        rows = self.saved(payload, self.run_receipt(payload, [reading, exercise]), 2)
        reading_row = next(r for r in rows if '朗读' in r['title'])
        exercise_row = next(r for r in rows if '练习卷' in r['title'])
        for clause in ('单面打印', '完成后自查并请家长签字', '第4题选做'):
            self.assertIn(clause, exercise_row['body'])
            self.assertNotIn(clause, reading_row['body'])
        self.assertEqual([e['ref'] for e in json.loads(reading_row['evidence'])], refs[:1])
        self.assertEqual([e['ref'] for e in json.loads(exercise_row['evidence'])], refs)

    def test_subjects_and_independent_actions_do_not_bleed_across_semicolons(self):
        payload, refs = self._ingest([
            '明天作业：语文，朗读《示例短文》两遍；数学，完成练习册第8页。'])
        reading = self.proposal('朗读《示例短文》两遍', refs, due='2026-10-06', subject='语文')
        exercise = self.proposal('完成练习册第8页', refs, due='2026-10-06', subject='数学')
        rows = self.saved(payload, self.run_receipt(payload, [reading, exercise]), 2)
        for subject, own, foreign in [('语文', '朗读《示例短文》两遍', '完成练习册第8页'),
                                      ('数学', '完成练习册第8页', '朗读《示例短文》两遍')]:
            row = next(r for r in rows if own in r['body'])
            self.assertTrue(row['title'].startswith(subject + '：'))
            self.assertNotIn(foreign, row['body'])
            self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')

    def test_each_independent_action_keeps_its_own_explicit_date(self):
        payload, refs = self._ingest([
            '英语：10月6日前完成练习卷第1–3题；10月7日朗读Unit 2课文两遍。'])
        exercise = self.proposal('完成练习卷第1–3题', refs, due='2026-10-06')
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-07')
        rows = self.saved(payload, self.run_receipt(payload, [exercise, reading]), 2)
        for quote, expected, forbidden in [('完成练习卷第1–3题', '2026-10-06', '10月7日'),
                                           ('朗读Unit 2课文两遍', '2026-10-07', '10月6日前')]:
            row = next(r for r in rows if quote in r['body'])
            self.assertEqual((row['due'], row['state']), (expected, 'accepted'))
            self.assertNotIn(forbidden, row['body'])
        self.assertIn('10月6日前', next(r for r in rows if '练习卷' in r['title'])['body'])

    def test_learning_and_independent_safety_receipt_keep_distinct_purposes(self):
        payload, refs = self._ingest([
            '明天完成：1. 朗读Unit 2课文两遍；2. 请家长签署安全回执并交回。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06')
        receipt = self.proposal('请家长签署安全回执并交回', refs, due='2026-10-06', subject='', purpose='admin')
        rows = self.saved(payload, self.run_receipt(payload, [reading, receipt]), 2)
        for own, other, purpose in [('朗读Unit 2课文两遍', '安全回执', 'learning'),
                                    ('请家长签署安全回执并交回', '朗读Unit 2', 'admin')]:
            row = next(r for r in rows if own in r['body'])
            self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], purpose)
            self.assertNotIn(other, row['body'])
            self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))

    def test_independent_admin_action_cannot_disappear_behind_learning_reference(self):
        payload, refs = self._ingest([
            '明天完成：1. 朗读Unit 2课文两遍；2. 请家长签署安全回执并交回。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06')
        self._assert_rejected_batch(payload, self.run_receipt(payload, [reading]))

    def test_one_sheet_print_answer_check_and_sign_steps_remain_one_task(self):
        text = ('英语，明天完成一份练习卷，步骤如下：1. 单面打印练习卷；'
                '2. 完成练习卷第1–3题并自查；3. 请家长在这份练习卷上签字；第4题选做。')
        payload, refs = self._ingest([text])
        exercise = self.proposal('完成练习卷第1–3题并自查', refs, due='2026-10-06', goal=text)
        row, = self.saved(payload, self.run_receipt(payload, [exercise]), 1)
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        for clause in ('单面打印练习卷', '完成练习卷第1–3题并自查', '请家长在这份练习卷上签字', '第4题选做'):
            self.assertIn(clause, row['body'])
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
        self.assertEqual((replay['processed'], replay['created']), (0, 0))
        self.assertEqual(self.model.call_count, 1)

    def test_example_is_not_an_extra_exercise(self):
        payload, refs = self._ingest([
            '英语，明天朗读Unit 2课文两遍。示例：完成练习卷第1–3题只是说明作业格式，不是今天的作业。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06')
        row, = self.saved(payload, self.run_receipt(payload, [reading]), 1)
        self.assertIn('朗读Unit 2课文两遍', row['body'])
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        self.assertNotIn('练习卷', row['title'])

    def test_explicitly_unneeded_exercise_does_not_create_a_task(self):
        payload, refs = self._ingest(['英语，明天朗读Unit 2课文两遍；不用做练习卷。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06')
        row, = self.saved(payload, self.run_receipt(payload, [reading]), 1)
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        self.assertNotIn('练习卷', row['title'])

    def test_genuinely_unread_original_can_remain_pending(self):
        payload = self.fixture.payload()
        payload['messages'][0].update(kind='file', unread=True, sender_id='synthetic-teacher-1',
                                      text='数学练习卷的具体要求见附件，原件尚未取得。')
        self.store.ingest(payload)
        ref = 'message:' + self.source['id'] + ':' + payload['messages'][0]['id']
        proposal = self.proposal('数学练习卷', [ref], subject='数学')
        proposal.update(task_state='review', task_purpose='unknown',
                        task_goal='原件尚未取得，具体要求待核对。', task_reason='尚未取得原件。')

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual(name, 'family_agent_selection')
            self.assertEqual(data_path, self.app.DATA)
            return copy.deepcopy(dict(proposals=[proposal]))

        self.model.side_effect = reply
        row, = self.saved(payload, agent.run_once(self.app, self.now), 1)
        self.assertEqual(row['state'], 'pending')
        self.assertEqual(row['task_id'], '')

    def test_compiled_standard_is_rechecked_in_the_real_write_transaction(self):
        payload, refs = self._ingest([
            '英语，明天完成：1. 朗读Unit 2课文两遍；2. 完成练习卷第1–3题，第4题选做。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs, due='2026-10-06')
        exercise = self.proposal('完成练习卷第1–3题', refs, due='2026-10-06',
                                 goal='完成练习卷第1–3题，第4题选做。')
        self._use_replies(payload, [dict(proposals=[reading, exercise])])
        real_save, real_current = agent.Store._save, agent.Store._school_selection_current
        inflight, injected = [], []

        def capture(store, key, fingerprint, items, *args, **kwargs):
            if kwargs.get('school_context'):
                inflight[:] = items
            return real_save(store, key, fingerprint, items, *args, **kwargs)

        def changed_standard(store, c, *args, **kwargs):
            current = real_current(store, c, *args, **kwargs)
            if current and c.in_transaction and inflight and not injected:
                exercise_item = next(item for item in inflight if '练习卷' in item['title'])
                exercise_item['body'] = '完成练习卷第1–3题。'
                injected.append(True)
            return current

        with patch.object(agent.Store, '_save', new=capture), \
                patch.object(agent.Store, '_school_selection_current', new=changed_standard):
            result = agent.run_once(self.app, self.now)
        self.assertEqual(injected, [True], 'inject only after the real input check inside the write transaction')
        self._assert_rejected_batch(payload, result)

    def test_holdout_elliptical_worksheet_still_requires_its_own_action(self):
        payload, refs = self._ingest(['英语作业：Unit 2课文读两遍；练习卷第1–3题。'])
        reading = self.proposal('Unit 2课文读两遍', refs)
        exercise = self.proposal('练习卷第1–3题', refs)
        self._use_replies(payload, [dict(proposals=[reading]), dict(proposals=[reading, exercise])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))
        recovered = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((recovered['failed'], recovered['processed']), (0, 1),
                         'rejecting every receipt is not successful action coverage')
        self.assertEqual(self.model.call_count, 2)
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(rows), 2)
            for own, foreign in [('Unit 2课文读两遍', '练习卷第1–3题'),
                                  ('练习卷第1–3题', 'Unit 2课文读两遍')]:
                row = next(r for r in rows if own in r['title'])
                self.assertTrue(row['title'].startswith('英语：'))
                self.assertIn(own, row['body'])
                self.assertNotIn(foreign, row['body'])
                # README r188 and PRD 5 keep explicit, current homework visible
                # with unknown dates; missing dates do not make a ready task unread.
                self.assertEqual((row['due'], row['state']), ('', 'accepted'))
                self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')
                self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'])
            self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [1])
            tasks = {r['id']: dict(r) for r in c.execute('SELECT * FROM manual_tasks')}
            self.assertEqual(set(tasks), {row['task_id'] for row in rows})
            for row in rows:
                self.assertEqual((tasks[row['task_id']]['due'], tasks[row['task_id']]['action']),
                                 ('无明确截止', row['body']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        today = self.now.date().isoformat()
        calendar = self.app.calendar_snapshot(today, today)
        collected = [item for item in calendar['inbox'] if item['task_id'] in tasks]
        self.assertEqual(len(collected), 2)
        for item in collected:
            self.assertEqual((item['agenda']['published_on'], item['agenda']['due_on'],
                              item['agenda']['scheduled_on']), (today, '', ''))
            self.assertEqual(item['agenda']['category'], 'homework')
        self.assertEqual([item for item in collected if item['agenda']['due_on'] == today], [],
                         'visible undated homework is not counted as explicitly due today')

    def test_holdout_comma_between_two_outcomes_cannot_hide_the_second(self):
        payload, refs = self._ingest(['英语作业：朗读Unit 2课文两遍，完成练习卷第1–3题。'])
        reading = self.proposal('朗读Unit 2课文两遍', refs)
        self._assert_rejected_batch(payload, self.run_receipt(payload, [reading]))

    def test_holdout_two_named_worksheets_are_not_one_container(self):
        payload, refs = self._ingest([
            '英语，明天完成甲练习卷：单面打印；完成甲练习卷第1–3题；另完成乙练习卷第1–3题。'])
        first = self.proposal('完成甲练习卷第1–3题', refs, due='2026-10-06')
        second = self.proposal('完成乙练习卷第1–3题', refs)
        merged = dict(first, task_goal='单面打印；完成甲练习卷第1–3题；另完成乙练习卷第1–3题。')
        self._use_replies(payload, [dict(proposals=[merged]), dict(proposals=[first, second])])
        self._assert_rejected_batch(payload, agent.run_once(self.app, self.now))
        result = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(self.model.call_count, 2)
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            self.assertEqual(len(rows), 2)
            first_row = next(r for r in rows if '甲练习卷' in r['title'])
            second_row = next(r for r in rows if '乙练习卷' in r['title'])
            self.assertIn('单面打印', first_row['body'])
            self.assertIn('完成甲练习卷第1–3题', first_row['body'])
            self.assertNotIn('乙练习卷', first_row['body'])
            self.assertIn('完成乙练习卷第1–3题', second_row['body'])
            self.assertNotIn('甲练习卷', second_row['body'])
            self.assertNotIn('单面打印', second_row['body'])
            for row in rows:
                self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')
            self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages')],
                             payload['messages'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)

    def test_return_to_first_worksheet_does_not_attach_its_steps_to_the_second(self):
        payload, refs = self._ingest([
            '英语，明天完成甲练习卷：单面打印；另完成乙练习卷第1–3题；完成甲练习卷第4–6题并自查。'])
        first = self.proposal('完成甲练习卷', refs, due='2026-10-06')
        second = self.proposal('完成乙练习卷第1–3题', refs)
        result = self.run_receipt(payload, [first, second])
        if result['failed']:
            # Noncontiguous ownership may remain retryable; the existing
            # adjacent two-worksheet test controls successful normal ordering.
            self.assertEqual((result['failed'], result['processed'], result['created']), (1, 0, 0))
            self.assertLessEqual(self.model.call_count, 1)
            with self.store._db() as c:
                for table in ('agent_items', 'manual_tasks', 'records', 'task_updates'):
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
                self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                                 payload['messages'])
                self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [0])
                job = c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
                self.assertEqual((job['attempts'], job['done']), (1, 0))
                self.assertTrue(job['error'])
                self.assertEqual(job['next_try'], (self.now + dt.timedelta(minutes=5)).isoformat())
            return
        rows = self.saved(payload, result, 2)
        first_row = next(row for row in rows if '甲练习卷' in row['title'])
        second_row = next(row for row in rows if '乙练习卷' in row['title'])
        for clause in ('单面打印', '完成甲练习卷第4–6题并自查'):
            self.assertIn(clause, first_row['body'], 'explicitly returning to the first worksheet keeps its steps there')
            self.assertNotIn(clause, second_row['body'])
        self.assertNotIn('乙练习卷', first_row['body'])
        self.assertIn('完成乙练习卷第1–3题', second_row['body'])
        self.assertNotIn('甲练习卷', second_row['body'])
        self.assertEqual(first_row['due'], '2026-10-06')
        self.assertEqual(second_row['due'], '', 'the second worksheet must not borrow the first worksheet date')
        for row in rows:
            self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)

    def test_cancelling_supplement_cannot_turn_a_ready_receipt_into_required_work(self):
        payload, refs = self._ingest([
            '英语，明天完成练习卷第1–3题。',
            '补充英语练习卷：练习卷不用做了。'])
        exercise = self.proposal('完成练习卷第1–3题', refs, due='2026-10-06',
                                 goal='完成练习卷第1–3题；练习卷不用做了。')
        result = self.run_receipt(payload, [exercise])
        # Both retrying the conflicting batch and preserving a review item are
        # safe; attaching the cancellation as another mandatory step is not.
        if result['failed']:
            self.assertEqual((result['failed'], result['processed'], result['created']), (1, 0, 0))
            self.assertLessEqual(self.model.call_count, 1)
            with self.store._db() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0], 0)
                self.assertEqual([json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                                 payload['messages'])
                self.assertEqual([r[0] for r in c.execute('SELECT processed FROM agent_messages')], [0, 0])
                job = c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
                self.assertEqual((job['attempts'], job['done']), (1, 0))
                self.assertTrue(job['error'])
                self.assertEqual(job['next_try'], (self.now + dt.timedelta(minutes=5)).isoformat())
        else:
            row, = self.saved(payload, result, 1)
            self.assertEqual((row['state'], row['task_id']), ('pending', ''))
            self.assertEqual(json.loads(row['plan'])['school_task']['state'], 'review')
            self.assertIn('练习卷不用做了', row['body'])
            self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)
        with self.store._db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE state='accepted'").fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)

    def test_cancelling_supplement_keeps_a_correct_cancel_review_receipt(self):
        payload, refs = self._ingest([
            '英语，明天完成练习卷第1–3题。',
            '补充英语练习卷：练习卷不用做了。'])
        cancellation = self.proposal('练习卷不用做了', refs, goal='练习卷不用做了。')
        cancellation.update(task_state='review', task_change='cancel', task_reason='同批补充取消练习卷，待核对原要求。')
        row, = self.saved(payload, self.run_receipt(payload, [cancellation]), 1)
        self.assertEqual((row['state'], row['task_id']), ('pending', ''))
        brief = json.loads(row['plan'])['school_task']
        self.assertEqual((brief['state'], brief['change']), ('review', 'cancel'))
        self.assertIn('练习卷不用做了', row['body'])
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)

    def test_example_date_after_recitation_does_not_pollute_its_deadline_or_standards(self):
        payload, refs = self._ingest([
            '英语：明天背诵Unit 2。示例：“10月7日完成练习卷”，只说明格式，不是作业。'])
        recitation = self.proposal('背诵Unit 2', refs, due='2026-10-06')
        row, = self.saved(payload, self.run_receipt(payload, [recitation]), 1)
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        self.assertIn('背诵Unit 2', row['body'])
        for example in ('10月7日', '完成练习卷', '示例'):
            self.assertNotIn(example, row['body'])
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)

    def test_optional_exercise_followed_by_no_signature_stays_optional(self):
        payload, refs = self._ingest([
            '英语作业：明天完成练习卷第4题（选做，不要求提交），无需家长签字。'])
        exercise = self.proposal('完成练习卷第4题', refs, due='2026-10-06', purpose='optional',
                                 goal='明天完成练习卷第4题（选做，不要求提交），无需家长签字。')
        exercise.update(task_state='review', task_reason='整项选做，不要求提交或家长签字。')
        row, = self.saved(payload, self.run_receipt(payload, [exercise]), 1)
        self.assertEqual((row['due'], row['state'], row['task_id']), ('2026-10-06', 'pending', ''))
        brief = json.loads(row['plan'])['school_task']
        self.assertEqual((brief['purpose'], brief['state']), ('optional', 'review'))
        for clause in ('完成练习卷第4题', '选做', '不要求提交', '无需家长签字'):
            self.assertIn(clause, row['body'])
        self.assertEqual([e['ref'] for e in json.loads(row['evidence'])], refs)

    def test_holdout_quoted_example_does_not_create_reading_or_exercise(self):
        payload, refs = self._ingest([
            '示例：“朗读课文；完成练习卷”。今天不用做练习，只需明天背诵Unit 2。'])
        recitation = self.proposal('背诵Unit 2', refs, due='2026-10-06')
        row, = self.saved(payload, self.run_receipt(payload, [recitation]), 1)
        self.assertEqual((row['due'], row['state']), ('2026-10-06', 'accepted'))
        self.assertIn('背诵Unit 2', row['body'])
        self.assertNotIn('朗读课文', row['body'])
        self.assertNotIn('完成练习卷', row['body'])
        self.assertEqual(json.loads(row['plan'])['school_task']['purpose'], 'learning')

    def test_holdout_tomorrow_and_day_after_keep_separate_deadlines(self):
        payload, refs = self._ingest(['英语：明天朗读Unit 2；后天完成练习卷第1–3题。'])
        reading = self.proposal('朗读Unit 2', refs, due='2026-10-06')
        exercise = self.proposal('完成练习卷第1–3题', refs, due='2026-10-07')
        rows = self.saved(payload, self.run_receipt(payload, [reading, exercise]), 2)
        for own, expected, forbidden in [('朗读Unit 2', '2026-10-06', '后天'),
                                         ('完成练习卷第1–3题', '2026-10-07', '明天')]:
            row = next(r for r in rows if own in r['body'])
            self.assertEqual((row['due'], row['state']), (expected, 'accepted'))
            self.assertNotIn(forbidden, row['body'])


if __name__ == '__main__':
    unittest.main()

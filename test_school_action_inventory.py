"""Synthetic school action/condition ownership, using the real intake transaction.

Model receipts are fixed local substitutes, not extraction-quality evidence.
No household data, collector, device or external model is used. Missing an
independent outcome must remain retryable; an omitted literal standard of a
known action should instead be compiled from the complete original text.
"""
import copy
import datetime as dt
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


if __name__ == '__main__':
    unittest.main()

"""Fictional step-ownership cases S01–S07 (development run school-step-ownership-20261028-v1); no household data.

The originals and each item's expected words are the run's frozen truth, independent of any reply. The fixed fictional
receipts are the ones Root replayed on main: a model submission step joins an item only when that item's own original
words state it. A pass proves the real run_once→Store→calendar API→single-child list path and the one shared brief
check every recovery path re-reads, never the product model's own extraction quality.
"""
import json
import unittest

import family_agent as agent
import test_daily_list_frozen as frozen
import test_school_native_coverage as native

# (id, original, items): item = (quote, subject, purpose, goal, submission, due, required, forbidden)
CASES = (
    ('S01', '语文今晚完成《晨光练习册》第2页。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '明天交给语文课代表。', '',
       ('第2页',), ('课代表', '提交要求', '明天交')),)),
    ('S02', '语文今晚完成《晨光练习册》第2页，另有一份告知书请家长签字。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '请家长签字。', '',
       ('第2页',), ('签字', '告知书')),
      ('另有一份告知书请家长签字', '', 'admin', '告知书请家长签字。', '', '', ('告知书', '家长', '签字'), ('第2页',)))),
    ('S03', '语文今晚完成《晨光练习册》第2页，完成后请家长在练习册上签字。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '请家长签字。', '',
       ('第2页', '家长', '签字'), ()),)),
    ('S04', '语文今晚完成《晨光练习册》第2页。明天交给语文课代表。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '明天交给语文课代表。', '2026-11-05',
       ('第2页', '明天', '课代表'), ()),)),
    ('S05', '英语今晚朗读Unit 2两遍，录音后上传班级小程序打卡。',
     (('英语今晚朗读Unit 2两遍', '英语', 'learning', '英语今晚朗读Unit 2两遍。', '录音后上传班级小程序打卡。', '',
       ('Unit 2', '两遍', '录音', '上传', '小程序'), ()),)),
    ('S06', '数学今晚完成《数格练习册》第5页。明早交练习册。',
     (('数学今晚完成《数格练习册》第5页', '数学', 'learning', '数学今晚完成《数格练习册》第5页。', '明早交练习册。', '2026-11-05',
       ('第5页', '明早', '交练习册'), ('交至练习册', '交到练习册')),)),
    ('S07', '英语今晚跟读Unit 5两遍。',
     (('英语今晚跟读Unit 5两遍', '英语', 'learning', '英语今晚跟读Unit 5两遍。', '明晚录音上传班级小程序打卡。', '',
       ('Unit 5', '两遍'), ('录音', '上传', '小程序', '明晚')),)),
    # Root's v1 rejection controls (run school-step-ownership-20261028-v2): a clause naming its own other object owns its
    # step wherever it stands in the sentence; a clause naming this item's own object owns it even before the item.
    ('I03', '《安全告知书》请监护人签名，语文今晚朗读《春晓》三遍。',
     (('语文今晚朗读《春晓》三遍', '语文', 'learning', '语文今晚朗读《春晓》三遍。', '请监护人签名。', '',
       ('春晓', '三遍'), ('签名', '告知书', '监护人')),
      ('《安全告知书》请监护人签名', '', 'admin', '《安全告知书》请监护人签名。', '', '', ('告知书', '监护人', '签名'), ('春晓',)))),
    ('P02', '语文今晚完成《晨光练习册》第2页，告知书请家长签字。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '请家长签字。', '',
       ('第2页',), ('签字', '告知书')),
      ('告知书请家长签字', '', 'admin', '告知书请家长签字。', '', '', ('告知书', '家长', '签字'), ('第2页',)))),
    ('P01', '请家长在《星雨作业本》上签字，语文今晚完成《星雨作业本》第3页。',
     (('语文今晚完成《星雨作业本》第3页', '语文', 'learning', '语文今晚完成《星雨作业本》第3页。', '请家长在《星雨作业本》上签字。', '',
       ('第3页', '星雨作业本', '家长', '签字'), ()),)),
    # The original says no signature is needed: the goal keeps that sentence, no trusted field turns it into a requirement.
    ('I06', '语文今晚写《春日练习册》第4页，不需要家长签名。',
     (('语文今晚写《春日练习册》第4页', '语文', 'learning', '语文今晚写《春日练习册》第4页，不需要家长签名。', '家长签名。', '',
       ('第4页', '不需要家长签名'), ('提交要求',)),)),
)
RECEIPT = ['title', 'goal', 'advice', 'state', 'reason', 'change', 'target_id', 'purpose', 'submission']


class SchoolSubmissionOwnershipTests(unittest.TestCase):
    _use_replies = native.SchoolNativeCoverageTests._use_replies
    setUp = frozen.DailyListFrozenTests.setUp
    _day = frozen.DailyListFrozenTests._day
    _proposal = frozen.DailyListFrozenTests._proposal
    _report = frozen.DailyListFrozenTests._report
    _run = frozen.DailyListFrozenTests._run
    _replay_adds_nothing = frozen.DailyListFrozenTests._replay_adds_nothing

    def _case(self, case, text, items, goal=None):
        payload, refs = self._day([('18:10', '虚构老师', 'qa-teacher', text)])
        proposals = [self._proposal(quote, refs, subject, goal(own, step) if goal and step else own, due=due, purpose=purpose,
                                    submission=step)
                     for quote, subject, purpose, own, step, due, _, _ in items]
        result, rows, listed, _ = self._run(payload, proposals, case)
        self.assertEqual((result['failed'], result['processed'], len(listed)), (0, 1, len(items)), case)
        for quote, subject, purpose, own, step, due, required, forbidden in items:
            # Each item is the one whose own object its frozen goal names; another item's own words never decide it.
            anchor = own.rstrip('。')[:8]
            item, = [i for i in listed if anchor in i['body']]
            words = item['title'] + '\n' + item['body']
            for word in required: self.assertIn(word, words, (case, quote))
            for word in forbidden: self.assertNotIn(word, words, (case, quote))
            self.assertEqual((item['kind'], item['status']), ('task', '待跟进'), (case, quote, 'a clear item is collected'))
            self.assertEqual(item['category'], 'homework' if purpose == 'learning' else 'todo', (case, quote))
            self.assertEqual(item['publications'], refs, 'its own original only')
            self.assertEqual(item['published_at'][:16], '2026-11-04T18:10')
            if due: self.assertEqual(item['due_on'], due, (case, quote, 'its own handback day'))
        self._replay_adds_nothing(case)
        return rows

    def test_frozen_cases_keep_own_steps_and_drop_unowned_ones(self):
        for case, text, items in CASES:
            with self.subTest(case=case):
                self.setUp()
                self._case(case, text, items)

    def test_step_repeated_in_goal_reads_the_same_ownership(self):
        """The model wrote the same step into task_goal and task_submission: an unowned step leaves both, an owned one stays."""
        for case, text, items in CASES:
            with self.subTest(case=case):
                self.setUp()
                self._case(case + '-goal', text, items, goal=lambda own, step: own.rstrip('。') + '，' + step)

    def test_negated_step_is_never_a_trusted_requirement(self):
        """I06: the raw receipt keeps the model's step for tracing; the trusted task fields never hold it as a requirement."""
        case, text, items = next(c for c in CASES if c[0] == 'I06')
        for goal in (None, lambda own, step: own.rstrip('。') + '，' + step):
            with self.subTest(goal=bool(goal)):
                self.setUp()
                rows = self._case(case + ('-goal' if goal else ''), text, items, goal=goal)
                plan, = [json.loads(row['plan']) for row in rows]
                self.assertEqual(plan['school_selection_receipt']['submission'], '家长签名。')
                self.assertNotIn('submission', plan['school_task'])
                self.assertEqual(plan['school_task']['goal'], '语文今晚写《春日练习册》第4页，不需要家长签名。')

    def test_recovery_rereads_the_saved_receipt_with_the_same_proof(self):
        """Every saved reread, untouched correction and cleared reread re-runs _school_brief on the stored receipt and the
        item's own originals, without the selection's quote: it must reach the very goal the direct path saved."""
        for case, text, items in CASES:
            with self.subTest(case=case):
                self.setUp()
                rows = self._case(case + '-recovery', text, items)
                for row in rows:
                    plan = json.loads(row['plan']);raw = plan.get('school_selection_receipt')
                    if not raw or plan['school_task']['state'] == 'reference': continue
                    evidence = [dict(e, kind='text') for e in json.loads(row['evidence'])]
                    fresh = agent._school_brief({key: raw.get(key) or ('review' if key == 'state' else 'new' if key == 'change' else '')
                                                 for key in RECEIPT}, evidence=evidence, separate_learning=True)
                    self.assertEqual(fresh['goal'], plan['school_task']['goal'], (case, row['title']))


if __name__ == '__main__':
    unittest.main()

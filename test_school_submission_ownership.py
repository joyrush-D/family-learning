"""Fictional step-ownership cases S01–S07 (development run school-step-ownership-20261028-v1); no household data.

The originals and each item's expected words are the run's frozen truth, independent of any reply. The fixed fictional
receipts are the ones Root replayed on main: a model submission step joins an item only when that item's own original
words state it. A pass proves the real run_once→Store→calendar API→single-child list path and the one shared brief
check every recovery path re-reads, never the product model's own extraction quality.
"""
import copy
import datetime as dt
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
    # Root's v2 rejection boundaries (run school-step-ownership-20261028-v3), frozen before v3: a short other object with no
    # asker is its own item's (V01, V04); a postposed negation is read (V02); a reminder is no object and no negation (V03).
    ('V01', '语文今晚完成《朝露练习册》第4页，回执签字。',
     (('语文今晚完成《朝露练习册》第4页', '语文', 'learning', '语文今晚完成《朝露练习册》第4页。', '签字。', '',
       ('第4页',), ('签字', '回执')),
      ('回执签字', '', 'admin', '回执签字。', '', '', ('回执', '签字'), ('第4页',)))),
    ('V02', '语文今晚写《春日练习册》第4页，家长签名不需要。',
     (('语文今晚写《春日练习册》第4页', '语文', 'learning', '语文今晚写《春日练习册》第4页，家长签名不需要。', '家长签名。', '',
       ('第4页', '家长签名不需要'), ('提交要求',)),)),
    ('V03', '英语今晚朗读《青叶英语》第2页，不要忘记请家长签字。',
     (('英语今晚朗读《青叶英语》第2页', '英语', 'learning', '英语今晚朗读《青叶英语》第2页。', '请家长签字。', '',
       ('第2页', '家长', '签字'), ()),)),
    ('V04', '数学今晚写练习册第3页，联系册签字。',
     (('数学今晚写练习册第3页', '数学', 'learning', '数学今晚写练习册第3页。', '签字。', '',
       ('第3页',), ('签字', '联系册')),
      ('联系册签字', '', 'admin', '联系册签字。', '', '', ('联系册', '签字'), ('第3页',)))),
    # v3 controls: a negation the summary left out stays in the teacher's own words, never as a requirement (N01 inner,
    # N02 postposed); a negation of another action keeps the step in the teacher's words (N03); a step after another
    # item's own words is that item's (N04), unless the original states it for both (C01).
    ('N01', '语文今晚写《春日练习册》第4页，家长不用签字。',
     (('语文今晚写《春日练习册》第4页', '语文', 'learning', '语文今晚写《春日练习册》第4页。', '请家长签字。', '',
       ('第4页', '家长不用签字'), ('提交要求',)),)),
    ('N02', '语文今晚写《春日练习册》第4页，家长签名不需要。',
     (('语文今晚写《春日练习册》第4页', '语文', 'learning', '语文今晚写《春日练习册》第4页。', '家长签名。', '',
       ('第4页', '家长签名不需要'), ('提交要求',)),)),
    ('N03', '数学今晚完成《数格练习册》第5页，家长签字后不用交。',
     (('数学今晚完成《数格练习册》第5页', '数学', 'learning', '数学今晚完成《数格练习册》第5页。', '请家长签字。', '',
       ('第5页', '家长签字后不用交'), ('提交要求',)),)),
    ('N04', '语文今晚完成《晨光练习册》第2页，回执请家长签字，明天交给班主任。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '明天交给班主任。', '',
       ('第2页',), ('班主任', '回执', '提交要求')),
      ('回执请家长签字', '', 'admin', '回执请家长签字，明天交给班主任。', '', '', ('回执', '签字', '班主任'), ('第2页',)))),
    ('C01', '语文今晚完成《晨光练习册》第2页，数学今晚完成《数格练习册》第5页，两项都请家长签字。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '请家长签字。', '',
       ('第2页', '家长', '签字'), ('第5页',)),
      ('数学今晚完成《数格练习册》第5页', '数学', 'learning', '数学今晚完成《数格练习册》第5页。', '请家长签字。', '',
       ('第5页', '家长', '签字'), ('第2页',)))),
    # C02: a step naming this item again after another item's words (语文和数学都…) is both items'; N05: one naming only the
    # other item (数学完成后…) is that item's alone.
    ('C02', '语文今晚完成《晨光练习册》第2页，数学今晚完成《数格练习册》第5页，语文和数学都请家长签字。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '请家长签字。', '',
       ('第2页', '家长', '签字'), ('第5页',)),
      ('数学今晚完成《数格练习册》第5页', '数学', 'learning', '数学今晚完成《数格练习册》第5页。', '请家长签字。', '',
       ('第5页', '家长', '签字'), ('第2页',)))),
    ('N05', '语文今晚完成《晨光练习册》第2页，数学今晚完成《数格练习册》第5页，数学完成后请家长签字。',
     (('语文今晚完成《晨光练习册》第2页', '语文', 'learning', '语文今晚完成《晨光练习册》第2页。', '请家长签字。', '',
       ('第2页',), ('签字', '第5页')),
      ('数学今晚完成《数格练习册》第5页', '数学', 'learning', '数学今晚完成《数格练习册》第5页。', '请家长签字。', '',
       ('第5页', '家长', '签字'), ('第2页',)))),
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
        """I06, V02, N01–N03: the raw receipt keeps the model's step for tracing; the trusted task fields never hold it as a
        requirement, and the teacher's own clause stays in the goal word for word."""
        expected = {'I06': '语文今晚写《春日练习册》第4页，不需要家长签名。',
                    'V02': '语文今晚写《春日练习册》第4页，家长签名不需要。',
                    'N01': '语文今晚写《春日练习册》第4页。家长不用签字。',
                    'N02': '语文今晚写《春日练习册》第4页。家长签名不需要。',
                    'N03': '数学今晚完成《数格练习册》第5页。家长签字后不用交。'}
        for case, text, items in CASES:
            if case not in expected: continue
            for goal in (None, lambda own, step: own.rstrip('。') + '，' + step):
                with self.subTest(case=case, goal=bool(goal)):
                    self.setUp()
                    rows = self._case(case + ('-goal' if goal else ''), text, items, goal=goal)
                    plan, = [json.loads(row['plan']) for row in rows]
                    self.assertEqual(plan['school_selection_receipt']['submission'], items[0][4])
                    self.assertNotIn('submission', plan['school_task'])
                    self.assertEqual(plan['school_task']['goal'], expected[case])

    def test_recovery_rereads_the_saved_receipt_with_the_same_proof(self):
        """Every saved reread, untouched correction and cleared reread re-runs _school_brief on the stored receipt and the
        item's own originals with the quotes its same-original siblings were saved with (what _school_sibling_quotes
        reads): it must reach the very goal the direct path saved. This replays the shared brief check only; the saved
        reread state machine itself is Root's R259 reference."""
        for case, text, items in CASES:
            with self.subTest(case=case):
                self.setUp()
                rows = self._case(case + '-recovery', text, items)
                for row in rows:
                    plan = json.loads(row['plan']);raw = plan.get('school_selection_receipt')
                    if not raw or plan['school_task']['state'] == 'reference': continue
                    evidence = [dict(e, kind='text') for e in json.loads(row['evidence'])]
                    others = [json.loads(r['plan']).get('school_date_quote', '') for r in rows if r['id'] != row['id']]
                    fresh = agent._school_brief({key: raw.get(key) or ('review' if key == 'state' else 'new' if key == 'change' else '')
                                                 for key in RECEIPT}, evidence=evidence, separate_learning=True,
                                                **({'others': others} if others else {}))
                    self.assertEqual(fresh['goal'], plan['school_task']['goal'], (case, row['title']))


# Root v3 decision (run school-step-ownership-20261028-v4): six fictional messages, frozen truth sha256 fc9e33139f5aea79…,
# the unchanged raw deepseek-v4-1-flash-260910 reply (one call; refs message:synthetic-group:N) and Root's 0-API
# counterfactual correct split. The raw reply merges the separate 《返校回执》 sign-and-return into the 语文 exercise.
ROOT_V3_MESSAGES = [["18:05","虚构语文老师","qa-ordinary-cn","语文今晚完成《朝露练习册》第4页第1、2题；《返校回执》请家长签字，明早交回。"],["18:08","虚构英语老师","qa-ordinary-en","英语今晚朗读《青叶英语》第2页两遍，不要忘记请家长在记录本签字；录音不用上传。"],["18:10","虚构数学老师","qa-ordinary-math","数学今晚完成《晴空练习册》第6页第1至3题，完成后自己检查；明早交练习册。"],["18:20","虚构语文老师","qa-ordinary-cn","补充刚才《朝露练习册》第4页：第2题只写第一小问，其余要求不变。"],["18:25","虚构体育老师","qa-ordinary-pe","明天体育课带跳绳，不要求在家训练。"],["18:30","虚构科学老师","qa-ordinary-science","今天科学课学完了水的三种状态，这是课堂进度，供家长了解。"]]
ROOT_V3_RAW = json.loads('[{"due":"2026-11-05","evidence":[{"ref":"message:synthetic-group:11"},{"ref":"message:synthetic-group:14"}],"focus":"school","learning_goal_id":"","learning_subject":"语文","task_advice":"可先完成第1题，再做第2题第一小问，做完后对照题目要求检查。","task_change":"new","task_goal":"完成《朝露练习册》第4页第1、2题。\\n第2题只写第一小问，其余要求不变。\\n《返校回执》请家长签字，明早交回。","task_purpose":"learning","task_reason":"语文老师明确布置今晚练习册作业，并有后续补充限定第2题范围；回执签字交回与练习册同属该条消息的语文事项。","task_state":"ready","task_submission":"《返校回执》请家长签字，明早交回。","task_target_id":"","task_title":"语文：完成《朝露练习册》第4页","title_quote":"语文今晚完成《朝露练习册》第4页第1、2题；"},{"due":"","evidence":[{"ref":"message:synthetic-group:12"}],"focus":"school","learning_goal_id":"","learning_subject":"英语","task_advice":"可分两遍朗读，读完后请家长在记录本签字确认。","task_change":"new","task_goal":"朗读《青叶英语》第2页两遍。\\n请家长在记录本签字。\\n录音不用上传。","task_purpose":"learning","task_reason":"英语老师明确要求今晚朗读两遍并请家长签字，同时说明录音不用上传。","task_state":"ready","task_submission":"请家长在记录本签字；录音不用上传。","task_target_id":"","task_title":"英语：朗读《青叶英语》第2页两遍","title_quote":"英语今晚朗读《青叶英语》第2页两遍，不要忘记请家长在记录本签字；录音不用上传。"},{"due":"2026-11-05","evidence":[{"ref":"message:synthetic-group:13"}],"focus":"school","learning_goal_id":"","learning_subject":"数学","task_advice":"完成后按题目要求逐题自查，再放入练习册准备明早交回。","task_change":"new","task_goal":"完成《晴空练习册》第6页第1至3题。\\n完成后自己检查。\\n明早交练习册。","task_purpose":"learning","task_reason":"数学老师明确布置今晚练习册第6页第1至3题，要求自查并明早交练习册。","task_state":"ready","task_submission":"明早交练习册。","task_target_id":"","task_title":"数学：完成《晴空练习册》第6页","title_quote":"数学今晚完成《晴空练习册》第6页第1至3题，完成后自己检查；明早交练习册。"},{"due":"","evidence":[{"ref":"message:synthetic-group:15"}],"focus":"school","learning_goal_id":"","learning_subject":"","task_advice":"可提前把跳绳放入书包，避免体育课前遗漏。","task_change":"new","task_goal":"明天体育课带跳绳。\\n不要求在家训练。","task_purpose":"admin","task_reason":"体育老师明确要求明天体育课携带跳绳，并说明不要求在家训练；属于课前带物事务，无学习成果要求。","task_state":"ready","task_submission":"","task_target_id":"","task_title":"体育：明天体育课带跳绳","title_quote":"明天体育课带跳绳，不要求在家训练。"},{"due":"","evidence":[{"ref":"message:synthetic-group:16"}],"focus":"school","learning_goal_id":"","learning_subject":"","task_advice":"","task_change":"new","task_goal":"","task_purpose":"optional","task_reason":"科学老师仅说明今天课堂进度供家长了解，没有新增行动要求，不生成任务。","task_state":"reference","task_submission":"","task_target_id":"","task_title":"","title_quote":"今天科学课学完了水的三种状态，这是课堂进度，供家长了解。"}]')
ROOT_V3_SPLIT = json.loads('[{"due":"2026-11-04","evidence":[{"ref":"message:synthetic-group:11"},{"ref":"message:synthetic-group:14"}],"focus":"school","learning_goal_id":"","learning_subject":"语文","task_advice":"可先完成第1题，再做第2题第一小问，做完后对照题目要求检查。","task_change":"new","task_goal":"今晚完成《朝露练习册》第4页第1、2题。第2题只写第一小问，其余要求不变。","task_purpose":"learning","task_reason":"虚构反事实正面对照：只保本练习册的完整原要求。","task_state":"ready","task_submission":"","task_target_id":"","task_title":"语文：完成《朝露练习册》第4页","title_quote":"语文今晚完成《朝露练习册》第4页第1、2题"},{"due":"2026-11-05","evidence":[{"ref":"message:synthetic-group:11"}],"focus":"school","learning_goal_id":"","learning_subject":"","task_advice":"可先完成第1题，再做第2题第一小问，做完后对照题目要求检查。","task_change":"new","task_goal":"《返校回执》请家长签字，明早交回。","task_purpose":"admin","task_reason":"虚构反事实正面对照：原文独立表单签回，不归练习册。","task_state":"ready","task_submission":"明早交回。","task_target_id":"","task_title":"签署并交回《返校回执》","title_quote":"《返校回执》请家长签字，明早交回。"},{"due":"","evidence":[{"ref":"message:synthetic-group:12"}],"focus":"school","learning_goal_id":"","learning_subject":"英语","task_advice":"可分两遍朗读，读完后请家长在记录本签字确认。","task_change":"new","task_goal":"朗读《青叶英语》第2页两遍。\\n请家长在记录本签字。\\n录音不用上传。","task_purpose":"learning","task_reason":"英语老师明确要求今晚朗读两遍并请家长签字，同时说明录音不用上传。","task_state":"ready","task_submission":"请家长在记录本签字；录音不用上传。","task_target_id":"","task_title":"英语：朗读《青叶英语》第2页两遍","title_quote":"英语今晚朗读《青叶英语》第2页两遍，不要忘记请家长在记录本签字；录音不用上传。"},{"due":"2026-11-05","evidence":[{"ref":"message:synthetic-group:13"}],"focus":"school","learning_goal_id":"","learning_subject":"数学","task_advice":"完成后按题目要求逐题自查，再放入练习册准备明早交回。","task_change":"new","task_goal":"完成《晴空练习册》第6页第1至3题。\\n完成后自己检查。\\n明早交练习册。","task_purpose":"learning","task_reason":"数学老师明确布置今晚练习册第6页第1至3题，要求自查并明早交练习册。","task_state":"ready","task_submission":"明早交练习册。","task_target_id":"","task_title":"数学：完成《晴空练习册》第6页","title_quote":"数学今晚完成《晴空练习册》第6页第1至3题，完成后自己检查；明早交练习册。"},{"due":"","evidence":[{"ref":"message:synthetic-group:15"}],"focus":"school","learning_goal_id":"","learning_subject":"","task_advice":"可提前把跳绳放入书包，避免体育课前遗漏。","task_change":"new","task_goal":"明天体育课带跳绳。\\n不要求在家训练。","task_purpose":"admin","task_reason":"体育老师明确要求明天体育课携带跳绳，并说明不要求在家训练；属于课前带物事务，无学习成果要求。","task_state":"ready","task_submission":"","task_target_id":"","task_title":"体育：明天体育课带跳绳","title_quote":"明天体育课带跳绳，不要求在家训练。"},{"due":"","evidence":[{"ref":"message:synthetic-group:16"}],"focus":"school","learning_goal_id":"","learning_subject":"","task_advice":"","task_change":"new","task_goal":"","task_purpose":"optional","task_reason":"科学老师仅说明今天课堂进度供家长了解，没有新增行动要求，不生成任务。","task_state":"reference","task_submission":"","task_target_id":"","task_title":"","title_quote":"今天科学课学完了水的三种状态，这是课堂进度，供家长了解。"}]')

# Root's frozen expectation per outcome: (anchor, kind/category, required words, forbidden words, own refs, due_on, due_kind).
ROOT_V3_EXPECTED = (
    ('朝露练习册', 'homework', ('第4页', '第1', '2题', '第一小问'), ('返校回执', '家长签字', '上传', '晴空练习册'), (11, 14), '2026-11-04', 'deadline'),
    ('返校回执', 'todo', ('返校回执', '家长', '签字'), ('第4页', '第一小问', '青叶英语'), (11,), '2026-11-05', 'handback'),
    ('青叶英语', 'homework', ('第2页', '两遍', '家长', '记录本', '签字', '录音不用上传'), ('提交要求：上传', '必须上传', '需要上传', '返校回执'),
     (12,), '2026-11-04', 'deadline'),
    ('晴空练习册', 'homework', ('第6页', '1至3题', '检查', '交'), ('家长', '签字', '朝露练习册'), (13,), '2026-11-05', 'handback'),
    ('跳绳', 'todo', ('体育课', '带', '跳绳', '不要求在家训练'), ('家长签字', '晴空练习册'), (15,), '2026-11-05', 'arranged'),
)


class SchoolFormOutcomeTests(unittest.TestCase):
    """An explicit separate administrative form in the item's own original gets its own action, from the original's words,
    when the reply merged it into another proposal; an omitted one holds the batch for the existing bounded retry. Every
    case runs the real run_once→Store→calendar list; the model seam returns only the frozen fictional replies."""
    _use_replies = native.SchoolNativeCoverageTests._use_replies
    setUp = frozen.DailyListFrozenTests.setUp
    _day = frozen.DailyListFrozenTests._day
    _proposal = frozen.DailyListFrozenTests._proposal

    def _reply(self, proposals, shift=None):
        text = json.dumps(proposals, ensure_ascii=False).replace('message:synthetic-group:', 'message:' + self.source['id'] + ':')
        for old, new in (shift or {}).items(): text = text.replace(old, new)
        return dict(proposals=json.loads(text))

    def _state(self, today='2026-11-04'):
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
            job = dict(c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone())
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            tasks = [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
        snapshot = self.app.calendar_snapshot(today, today)
        listed = [frozen.view(i) for i in snapshot['inbox'] if i['kind'] in ('task', 'school') and i['child_ids'] == ['child-1']]
        return rows, job, originals, tasks, listed

    def _assert_root_five(self, listed, refs):
        self.assertEqual(len(listed), 5, [i['title'] for i in listed])
        for anchor, category, required, forbidden, own, due_on, due_kind in ROOT_V3_EXPECTED:
            item, = [i for i in listed if anchor in i['title'] + i['body']]
            words = item['title'] + '\n' + item['body']
            for word in required: self.assertIn(word, words, anchor)
            for word in forbidden: self.assertNotIn(word, words, anchor)
            self.assertEqual((item['kind'], item['status'], item['category']), ('task', '待跟进', category), anchor)
            self.assertEqual(item['publications'], [refs[i - 11] for i in own], (anchor, 'its own originals only'))
            self.assertEqual((item['due_on'], item['due_kind']), (due_on, due_kind), anchor)

    def test_root_raw_merged_form_gets_its_own_item_in_one_call(self):
        payload, refs = self._day(ROOT_V3_MESSAGES)
        raw = self._reply(ROOT_V3_RAW)
        self._use_replies(payload, [raw])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 6))
        rows, job, originals, tasks, listed = self._state()
        self.assertEqual(originals, payload['messages'], 'originals and send times are kept unchanged')
        self.assertEqual((job['attempts'], job['done'], self.model.call_count), (1, 1, 1), 'one receipt, no extra call')
        self._assert_root_five(listed, refs)
        self.assertEqual(len(tasks), 5)
        cn, = [r for r in rows if '朝露练习册' in r['title']]
        form, = [r for r in rows if '返校回执' in r['title']]
        cn_plan, form_plan = json.loads(cn['plan']), json.loads(form['plan'])
        receipt = {k: raw['proposals'][0]['task_' + k] for k in RECEIPT}
        # The model's merged reading stays verbatim on its own item; the formed item names exactly where it came from.
        self.assertEqual(cn_plan['school_selection_receipt'], receipt)
        self.assertEqual(cn_plan['school_split'], [dict(ref=refs[0], quote='《返校回执》请家长签字，明早交回')])
        self.assertNotIn('school_selection_receipt', form_plan)
        self.assertEqual(form_plan['school_split_from'], dict(index=0, receipt=receipt, ref=refs[0], quote='《返校回执》请家长签字，明早交回'))
        self.assertEqual((form['due'], cn['due']), ('2026-11-05', '2026-11-04'))
        self.assertEqual(json.loads(form['evidence'])[0]['ref'], refs[0])
        before = [dict(r) for r in rows]
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['failed'], replay['processed'], replay['created'], self.model.call_count), (0, 0, 0, 1))
        after, _, _, tasks_after, listed_after = self._state()
        self.assertEqual(after, before, 'a reopened day changes and adds nothing')
        self.assertEqual((len(tasks_after), len(listed_after)), (5, 5))

    def test_correct_split_reply_is_kept_as_returned(self):
        """Root's counterfactual control: a reply already giving each outcome its own proposal takes one call, gets no split
        mark and the same five tasks."""
        payload, refs = self._day(ROOT_V3_MESSAGES)
        self._use_replies(payload, [self._reply(ROOT_V3_SPLIT)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed'], self.model.call_count), (0, 6, 1))
        rows, job, _, tasks, listed = self._state()
        self._assert_root_five(listed, refs)
        self.assertEqual((len(rows), len(tasks)), (6, 5))
        self.assertFalse([r['id'] for r in rows if {'school_split', 'school_split_from'} & set(json.loads(r['plan']))])
        replay = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((replay['created'], self.model.call_count), (0, 1))

    def test_same_activity_steps_and_own_object_stay_one_item(self):
        """A signature or upload of the work itself, a closed name of the item's own object and a common scope are no separate form."""
        cases = (
            ('英语今晚朗读《青叶英语》第2页两遍，不要忘记请家长在记录本签字；录音不用上传。', '英语今晚朗读《青叶英语》第2页两遍',
             '英语', '朗读《青叶英语》第2页两遍。\n请家长在记录本签字。\n录音不用上传。', '请家长在记录本签字；录音不用上传。', ('记录本', '签字', '录音不用上传')),
            ('语文今晚完成《朝露练习册》第4页；《朝露练习册》请家长签字，明早交回。', '语文今晚完成《朝露练习册》第4页',
             '语文', '完成《朝露练习册》第4页。\n《朝露练习册》请家长签字，明早交回。', '《朝露练习册》请家长签字，明早交回。', ('第4页', '家长', '签字')),
            ('英语今晚朗读《青叶英语》第2页；读完后录音上传班级小程序。', '英语今晚朗读《青叶英语》第2页',
             '英语', '朗读《青叶英语》第2页。\n读完后录音上传班级小程序。', '读完后录音上传班级小程序。', ('录音', '上传', '小程序')),
            ('语文今晚完成《朝露练习册》第4页；《返校回执》和练习册都请家长签字。', '语文今晚完成《朝露练习册》第4页',
             '语文', '完成《朝露练习册》第4页。\n《返校回执》和练习册都请家长签字。', '请家长签字。', ('第4页', '家长', '签字')),
        )
        for text, quote, subject, goal, step, required in cases:
            with self.subTest(text=text):
                self.setUp()
                payload, refs = self._day([('18:10', '虚构老师', 'qa-teacher', text)])
                # A reply states the item's final handback day when its own words give one (the prompt's due rule).
                due = '2026-11-05' if '明早交回' in text else ''
                self._use_replies(payload, [dict(proposals=[self._proposal(quote, refs, subject, goal, due=due, submission=step)])])
                result = agent.run_once(self.app, self.now)
                rows, _, _, tasks, listed = self._state()
                # One item, never split. Whether it is collected today is the existing date-role reading (a separate
                # 今晚…；…明早交回 sentence stays for review on base too), not this check.
                self.assertEqual((result['failed'], len(rows), len(listed)), (0, 1, 1))
                self.assertFalse({'school_split', 'school_split_from'} & set(json.loads(rows[0]['plan'])))
                for word in required: self.assertIn(word, listed[0]['body'])

    def test_omitted_form_holds_the_batch_for_the_bounded_retry(self):
        """No proposal quotes or carries the separate form: nothing is saved, the originals stay, and only the next natural
        round's receipt may complete it. Three such receipts exhaust the batch with no fourth call."""
        omitted = self._reply(ROOT_V3_RAW)
        omitted['proposals'][0].update(task_goal='完成《朝露练习册》第4页第1、2题。\n第2题只写第一小问，其余要求不变。', task_submission='', due='')
        for repaired in (True, False):
            with self.subTest(repaired=repaired):
                self.setUp()
                payload, refs = self._day(ROOT_V3_MESSAGES)
                replies = [omitted, self._reply(ROOT_V3_SPLIT)] if repaired else [omitted] * 3
                self._use_replies(payload, copy.deepcopy(replies))
                first = agent.run_once(self.app, self.now)
                rows, job, originals, tasks, _ = self._state()
                self.assertEqual((first['failed'], first['processed'], first['created']), (1, 0, 0))
                self.assertEqual((rows, tasks, originals, job['attempts'], job['done']), ([], [], payload['messages'], 1, 0))
                self.assertIn('独立', job['error'])
                at = self.now
                for minutes in (6, 11, 30, 60):
                    at += dt.timedelta(minutes=minutes)
                    agent.run_once(self.app, at)
                rows, job, originals, tasks, listed = self._state()
                if repaired:
                    self.assertEqual((self.model.call_count, job['attempts'], job['done']), (2, 2, 1))
                    self._assert_root_five(listed, refs)
                    self.assertEqual(len(tasks), 5)
                else:
                    self.assertEqual((self.model.call_count, job['attempts'], job['done'], rows, tasks), (3, 3, 0, [], []))
                    self.assertIn('上限', job['error'])
                    self.assertEqual(originals, payload['messages'])

    def test_old_merged_batch_is_split_but_never_poured_into_today(self):
        """The same merged reply for messages sent two days ago: the form still gets its own item, but every own day is past,
        so the existing guards keep each for review instead of collecting it as today's work."""
        payload, refs = self._day(ROOT_V3_MESSAGES, day='2026-11-02')
        raw = self._reply(ROOT_V3_RAW, shift={'2026-11-05': '2026-11-03'})
        self._use_replies(payload, [raw])
        result = agent.run_once(self.app, self.now)
        rows, _, _, tasks, listed = self._state()
        self.assertEqual((result['failed'], tasks), (0, []), 'no past item is auto-collected')
        form, = [r for r in rows if '返校回执' in r['title']]
        self.assertEqual((form['state'], json.loads(form['plan'])['school_task']['state']), ('pending', 'review'))
        self.assertFalse([i for i in listed if '2026-11-04' in (i['due_on'], i['scheduled_on'], i['complete_on'])])


if __name__ == '__main__':
    unittest.main()

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
import family_task_focus
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

    def test_omitted_form_is_compiled_from_the_original_on_the_first_call(self):
        """v6 changes v4/v5's expectation (hold, then the identical temperature-0 request up to three times): no proposal
        quotes or carries the separate form, but its own complete original states it affirmatively (closed name, own signer,
        own handback), and that run, not the model's goal, is the evidence the requirement exists. The first call compiles it
        by the same chain as a merged one, marked as the program's; the model's own item keeps its receipt untouched. Later
        natural rounds add nothing. Replies that cannot be taken apart and failed requests keep the bounded retry (below)."""
        omitted = self._reply(ROOT_V3_RAW)
        omitted['proposals'][0].update(task_goal='完成《朝露练习册》第4页第1、2题。\n第2题只写第一小问，其余要求不变。', task_submission='', due='')
        payload, refs = self._day(ROOT_V3_MESSAGES)
        self._use_replies(payload, copy.deepcopy([omitted]))
        first = agent.run_once(self.app, self.now)
        rows, job, originals, tasks, listed = self._state()
        self.assertEqual((first['failed'], first['processed'], job['attempts'], job['done'], self.model.call_count), (0, 6, 1, 1, 1))
        self.assertEqual(originals, payload['messages'])
        self._assert_root_five(listed, refs)
        self.assertEqual(len(tasks), 5)
        cn, = [r for r in rows if '朝露练习册' in r['title']]
        form, = [r for r in rows if '返校回执' in r['title']]
        receipt = {k: omitted['proposals'][0]['task_' + k] for k in RECEIPT}
        self.assertEqual(json.loads(cn['plan'])['school_selection_receipt'], receipt, 'the model reading stays verbatim')
        self.assertNotIn('school_split', json.loads(cn['plan']), 'nothing was taken out of the model item')
        self.assertNotIn('school_selection_receipt', json.loads(form['plan']))
        self.assertEqual(json.loads(form['plan'])['school_split_from'],
                         dict(index=0, receipt=receipt, ref=refs[0], quote='《返校回执》请家长签字，明早交回', omitted=True))
        before = [dict(r) for r in rows]
        at = self.now
        for minutes in (6, 11, 30, 60):
            at += dt.timedelta(minutes=minutes)
            agent.run_once(self.app, at)
        after, _, _, tasks_after, _ = self._state()
        self.assertEqual((after, len(tasks_after), self.model.call_count), (before, 5, 1), 'no repeat, no duplicate')

    def test_unseparable_or_failed_replies_keep_the_bounded_retry(self):
        """Kept failure-limit controls: a reply naming the form in its own title cannot be taken apart, and a failed request
        is no reply; each keeps the failure count, saves nothing and exhausts after three attempts with no fourth call."""
        unseparable = self._reply(ROOT_V3_RAW)
        unseparable['proposals'][0]['task_title'] = '语文：完成《朝露练习册》第4页并交《返校回执》'
        for name in ('unseparable', 'request failure'):
            with self.subTest(name):
                self.setUp()
                payload, refs = self._day(ROOT_V3_MESSAGES)
                if name == 'unseparable':self._use_replies(payload, copy.deepcopy([unseparable] * 3))
                else:self.model.side_effect = agent.AgentError('虚构模型请求失败')
                first = agent.run_once(self.app, self.now)
                rows, job, originals, tasks, _ = self._state()
                self.assertEqual((first['failed'], rows, tasks, originals, job['attempts'], job['done']), (1, [], [], payload['messages'], 1, 0))
                at = self.now
                for minutes in (6, 11, 30, 60):
                    at += dt.timedelta(minutes=minutes)
                    agent.run_once(self.app, at)
                rows, job, originals, tasks, _ = self._state()
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


# Root's v4 held-out cases (truth sha256 928831aa…fde, frozen before Root received the v4 source), verbatim: each original,
# the reply mode Root's seam returns first, and each outcome's own words, day, purpose and subject.
ROOT_V4_HELDOUT = json.loads('''[{"expected_tasks":2,"first_response_mode":"merge_all_into_first","id":"A01_other_named_form_no_sibling","intent":"First raw gives only one combined learning proposal; no sibling model quote can supply missing ownership.","items":[{"due":"2026-11-04","forbidden":["秋游告知单","签字"],"goal":"语文今晚完成《溪桥练习册》第8页。","purpose":"learning","quote":"语文今晚完成《溪桥练习册》第8页","required":["溪桥练习册","第8页"],"subject":"语文","submission":""},{"due":"2026-11-05","forbidden":["溪桥练习册","第8页"],"goal":"《秋游告知单》家长签字，明早交回。","purpose":"admin","quote":"《秋游告知单》家长签字，明早交回","required":["秋游告知单","家长","签字","交回"],"subject":"","submission":"明早交回。"}],"messages":["语文今晚完成《溪桥练习册》第8页；《秋游告知单》家长签字，明早交回。"]},{"expected_tasks":2,"first_response_mode":"merge_all_into_first","id":"A02_distinct_claim_form_not_receipt_keyword","intent":"No 回执/告知书 object name, same common independent-object requirement.","items":[{"due":"2026-11-04","forbidden":["物品领用单","签名"],"goal":"数学今晚完成《双格练习册》第2页。","purpose":"learning","quote":"数学今晚完成《双格练习册》第2页","required":["双格练习册","第2页"],"subject":"数学","submission":""},{"due":"2026-11-05","forbidden":["双格练习册","第2页"],"goal":"家长在《物品领用单》上签名，明天交回。","purpose":"admin","quote":"家长在《物品领用单》上签名，明天交回","required":["物品领用单","家长","签名","交回"],"subject":"","submission":"明天交回。"}],"messages":["数学今晚完成《双格练习册》第2页；家长在《物品领用单》上签名，明天交回。"]},{"expected_tasks":1,"first_response_mode":"correct","id":"A03_same_book_signature_and_reading_one_outcome","intent":"A same named book and page, parent signature before primary across semicolon: one outcome, zero spurious repair or administrative duplicate.","items":[{"due":"2026-11-05","forbidden":[],"goal":"英语今晚读《雨桐阅读本》第5页两遍，请家长在《雨桐阅读本》第5页签名，明早交给英语老师。","purpose":"learning","quote":"英语今晚读《雨桐阅读本》第5页两遍，明早交给英语老师","required":["雨桐阅读本","第5页","两遍","家长","签名","交给英语老师"],"subject":"英语","submission":"请家长在《雨桐阅读本》第5页签名，明早交给英语老师。"}],"messages":["请家长在《雨桐阅读本》第5页签名；英语今晚读《雨桐阅读本》第5页两遍，明早交给英语老师。"]},{"expected_tasks":2,"first_response_mode":"merge_all_into_first","id":"A04_two_same_subject_learning_objects","intent":"Two independent learning outcomes in one subject stay distinct, shared check condition belongs to both.","items":[{"due":"2026-11-04","forbidden":["图形册","第3题"],"goal":"数学今晚完成《算数卡》第2题，做完检查。","purpose":"learning","quote":"数学今晚完成《算数卡》第2题","required":["算数卡","第2题","检查"],"subject":"数学","submission":""},{"due":"2026-11-04","forbidden":["算数卡","第2题"],"goal":"今晚完成《图形册》第3题，做完检查。","purpose":"learning","quote":"还要完成《图形册》第3题","required":["图形册","第3题","检查"],"subject":"数学","submission":""}],"messages":["数学今晚完成《算数卡》第2题；还要完成《图形册》第3题。两项做完都要检查。"]}]''')


# Each item's own day must hold for every case (v5 left A04's 图形册 open). Where a positive scope of the original gives
# it, the saved item names that basis: (case id, quote) -> (the scope's own words, kind).
SCOPE_BASIS = {('A04_two_same_subject_learning_objects', '还要完成《图形册》第3题'): ('数学今晚完成《算数卡》第2题', 'continued')}

# v6 date-scope controls (fictional, same shape as Root's cases): a continued item reads a day only from a proven scope.
SCOPE_CONTROLS = [
    dict(id='D1_same_subject_explicit_tomorrow', expected_tasks=2, first_response_mode='merge_all_into_first',
         messages=['数学今晚完成《算数卡》第2题；还要明天完成《图形册》第3题。两项做完都要检查。'],
         items=[dict(quote='数学今晚完成《算数卡》第2题', subject='数学', purpose='learning', goal='数学今晚完成《算数卡》第2题，做完检查。',
                     submission='', due='2026-11-04', required=['算数卡', '第2题', '检查'], forbidden=['图形册', '第3题']),
                dict(quote='还要明天完成《图形册》第3题', subject='数学', purpose='learning', goal='明天完成《图形册》第3题，做完检查。',
                     submission='', due='2026-11-05', required=['图形册', '第3题', '检查'], forbidden=['算数卡', '第2题'])]),
    dict(id='D2_parent_administrative_never_borrows_tonight', expected_tasks=2, first_response_mode='merge_all_into_first',
         messages=['数学今晚完成《算数卡》第2题；还要请家长在《安全告知单》上签字。'],
         items=[dict(quote='数学今晚完成《算数卡》第2题', subject='数学', purpose='learning', goal='数学今晚完成《算数卡》第2题。',
                     submission='', due='2026-11-04', required=['算数卡', '第2题'], forbidden=['安全告知单', '签字']),
                dict(quote='还要请家长在《安全告知单》上签字', subject='', purpose='admin', goal='请家长在《安全告知单》上签字。',
                     submission='', due='', required=['安全告知单', '家长', '签字'], forbidden=['算数卡', '第2题'])]),
    dict(id='D3_other_subject_never_borrows_tonight', expected_tasks=2, first_response_mode='merge_all_into_first',
         messages=['数学今晚完成《算数卡》第2题；英语还要读《晨读本》第3页。'],
         items=[dict(quote='数学今晚完成《算数卡》第2题', subject='数学', purpose='learning', goal='数学今晚完成《算数卡》第2题。',
                     submission='', due='2026-11-04', required=['算数卡', '第2题'], forbidden=['晨读本', '第3页']),
                dict(quote='英语还要读《晨读本》第3页', subject='英语', purpose='learning', goal='英语读《晨读本》第3页。',
                     submission='', due='', required=['晨读本', '第3页'], forbidden=['算数卡', '第2题'])]),
    dict(id='D4_no_day_is_never_guessed', expected_tasks=2, first_response_mode='merge_all_into_first',
         messages=['数学完成《算数卡》第2题；还要完成《图形册》第3题。两项做完都要检查。'],
         items=[dict(quote='数学完成《算数卡》第2题', subject='数学', purpose='learning', goal='数学完成《算数卡》第2题，做完检查。',
                     submission='', due='', required=['算数卡', '第2题', '检查'], forbidden=['图形册', '第3题']),
                dict(quote='还要完成《图形册》第3题', subject='数学', purpose='learning', goal='完成《图形册》第3题，做完检查。',
                     submission='', due='', required=['图形册', '第3题', '检查'], forbidden=['算数卡', '第2题'])]),
    dict(id='D5_explicit_common_scope', expected_tasks=2, first_response_mode='merge_all_into_first',
         messages=['数学完成《算数卡》第2题；还要完成《图形册》第3题。两项今晚都要完成。'],
         items=[dict(quote='数学完成《算数卡》第2题', subject='数学', purpose='learning', goal='数学完成《算数卡》第2题，今晚完成。',
                     submission='', due='2026-11-04', required=['算数卡', '第2题'], forbidden=['图形册', '第3题']),
                dict(quote='还要完成《图形册》第3题', subject='数学', purpose='learning', goal='完成《图形册》第3题，今晚完成。',
                     submission='', due='2026-11-04', required=['图形册', '第3题'], forbidden=['算数卡', '第2题'])]),
]
SCOPE_BASIS.update({('D5_explicit_common_scope', '数学完成《算数卡》第2题'): ('两项今晚都要完成', 'common'),
                    ('D5_explicit_common_scope', '还要完成《图形册》第3题'): ('两项今晚都要完成', 'common')})
A01_OWN = '语文今晚完成《溪桥练习册》第8页'


# Root v7 closed-object truth (closed-name-truth.json without C02, isolated-suffix-truth.json): distinct closed names
# sharing characters are other objects; the same book's same page before the item is its own step. C02's prepared
# 晨光练习册 stops before the model on the fixture's preparation ambiguity, another path, so it stays out of this set.
ROOT_V7_CLOSED = json.loads('''[{"expected_tasks": 2, "first_response_mode": "omit_other", "id": "C01_common_prefix_distinct_closed_books", "items": [{"due": "2026-11-04", "forbidden": ["长叶写本", "第2页"], "goal": "英语今晚完成《长叶读本》第3页。", "purpose": "learning", "quote": "英语今晚完成《长叶读本》第3页", "required": ["长叶读本", "第3页"], "subject": "英语", "submission": ""}, {"due": "2026-11-05", "forbidden": ["长叶读本", "第3页"], "goal": "明天完成《长叶写本》第2页。", "purpose": "learning", "quote": "明天完成《长叶写本》第2页", "required": ["长叶写本", "第2页"], "subject": "英语", "submission": ""}], "messages": ["英语今晚完成《长叶读本》第3页；明天完成《长叶写本》第2页。"]}, {"expected_tasks": 1, "first_response_mode": "correct", "id": "C03_same_closed_object_signature_stays_one", "items": [{"due": "2026-11-04", "forbidden": [], "goal": "英语今晚完成《长叶读本》第3页，请家长在《长叶读本》第3页签字。", "purpose": "learning", "quote": "英语今晚完成《长叶读本》第3页", "required": ["长叶读本", "第3页", "家长", "签字"], "subject": "英语", "submission": "请家长在《长叶读本》第3页签字。"}], "messages": ["请家长在《长叶读本》第3页签字；英语今晚完成《长叶读本》第3页。"]}, {"expected_tasks": 2, "first_response_mode": "omit_other", "id": "C04_common_suffix_without_seeded_prepared_book", "items": [{"due": "2026-11-04", "forbidden": ["翠云同步册", "第2页"], "goal": "英语今晚完成《青石同步册》第3页。", "purpose": "learning", "quote": "英语今晚完成《青石同步册》第3页", "required": ["青石同步册", "第3页"], "subject": "英语", "submission": ""}, {"due": "2026-11-05", "forbidden": ["青石同步册", "第3页"], "goal": "明天完成《翠云同步册》第2页。", "purpose": "learning", "quote": "明天完成《翠云同步册》第2页", "required": ["翠云同步册", "第2页"], "subject": "英语", "submission": ""}], "messages": ["英语今晚完成《青石同步册》第3页；明天完成《翠云同步册》第2页。"]}]''')
OTHER_OBJECT_SIGNATURE = dict(
    id='V7_other_closed_object_signature_before_the_item', expected_tasks=2, first_response_mode='merge_all_into_first',
    messages=['请家长在《长叶写本》第3页签字；英语今晚完成《长叶读本》第3页。'],
    items=[dict(quote='英语今晚完成《长叶读本》第3页', subject='英语', purpose='learning', goal='英语今晚完成《长叶读本》第3页。',
                submission='', due='2026-11-04', required=['长叶读本', '第3页'], forbidden=['长叶写本', '签字']),
           dict(quote='请家长在《长叶写本》第3页签字', subject='', purpose='admin', goal='请家长在《长叶写本》第3页签字。',
                submission='', due='', required=['长叶写本', '家长', '签字'], forbidden=['长叶读本'])])


class SchoolIndependentOutcomeTests(unittest.TestCase):
    """An explicit independent outcome of the original (another closed-name object with its own affirmed action, whatever
    it is called) gets its own item from the original's words, whether the reply merged it into another proposal or left it
    out. Real run_once→Store→calendar list at Root's natural rounds 0/6/12; the seam returns the case's first reply."""
    _use_replies = native.SchoolNativeCoverageTests._use_replies
    setUp = frozen.DailyListFrozenTests.setUp
    _day = frozen.DailyListFrozenTests._day
    _proposal = frozen.DailyListFrozenTests._proposal
    _state = SchoolFormOutcomeTests._state

    def _replies(self, case, refs, mode=None):
        def own(item):
            return self._proposal(item['quote'], refs, item['subject'], item['goal'], due=item['due'], purpose=item['purpose'],
                                  submission=item['submission'])
        split = dict(proposals=[own(item) for item in case['items']])
        mode = mode or case['first_response_mode']
        if mode == 'correct':return split, split
        # v6 omission: the reply returns only the first outcome, exactly as its own correct proposal.
        if mode == 'omit_all_but_first':return dict(proposals=[own(case['items'][0])]), split
        # Root's merge_all_into_first: the first outcome's quote, title, subject and purpose carrying every outcome's goal.
        merged = own(case['items'][0])
        merged.update(task_goal='\n'.join(i['goal'] for i in case['items']),
                      task_submission='\n'.join(i['submission'] for i in case['items'] if i['submission']),
                      due=max(i['due'] for i in case['items']))
        return dict(proposals=[merged]), split

    def _rounds(self, offsets=(0, 6, 12)):
        return [agent.run_once(self.app, self.now + dt.timedelta(minutes=m)) for m in offsets]

    def _check(self, case, mode=None):
        """One case at natural rounds 0/6/12: one call, each outcome's own task, words, category and day, raw receipts
        kept, the program's item marked with its source, and nothing added later."""
        mode = mode or case['first_response_mode']
        mode = 'omit_all_but_first' if mode == 'omit_other' else mode  # Root v7's name for the same reply
        self.setUp()
        payload, refs = self._day([('18:10', '虚构老师', 'qa-teacher', text) for text in case['messages']])
        first, split = self._replies(case, refs, mode)
        self._use_replies(payload, copy.deepcopy([first, split, split]))
        results = self._rounds([0])
        rows, job, originals, tasks, listed = self._state()
        self.assertEqual(originals, payload['messages'], 'originals and send times are kept unchanged')
        self.assertEqual((results[0]['failed'], job['attempts'], job['done']), (0, 1, 1), (case['id'], job['error']))
        self.assertEqual(self.model.call_count, 1, 'the original itself proves the outcome: no repair call')
        self.assertEqual((len(tasks), len(listed)), (case['expected_tasks'],) * 2, [t['action'] for t in tasks])
        for item in case['items']:
            task, = [t for t in tasks if all(w in t['action'] for w in item['required'])]
            view, = [i for i in listed if all(w in i['title'] + '\n' + i['body'] for w in item['required'])]
            row, = [r for r in rows if all(w in r['title'] + '\n' + r['body'] for w in item['required'])]
            for word in item['forbidden']:
                self.assertNotIn(word, task['action'] + task['title'], (case['id'], item['quote']))
                self.assertNotIn(word, view['title'] + '\n' + view['body'], (case['id'], item['quote']))
            self.assertEqual((view['kind'], view['status']), ('task', '待跟进'), (case['id'], item['quote']))
            self.assertEqual(view['category'], 'homework' if item['purpose'] == 'learning' else 'todo', item['quote'])
            self.assertEqual(view['publications'], refs, 'its own original only')
            # Every outcome's own frozen day, A04's continued 图形册 included (no open-day exemption any more).
            self.assertEqual((task['due'], row['due']), (item['due'] or '无明确截止', item['due']), (case['id'], item['quote']))
            basis = SCOPE_BASIS.get((case['id'], item['quote']))
            plan = json.loads(row['plan'])
            if basis:
                self.assertEqual(plan.get('school_date_scope'), dict(ref=refs[0], quote=basis[0], kind=basis[1]), item['quote'])
            else:
                self.assertNotIn('school_date_scope', plan, item['quote'])
        plans = [json.loads(r['plan']) for r in rows]
        receipt = {k: first['proposals'][0]['task_' + k] for k in RECEIPT}
        if mode == 'correct':
            self.assertFalse([p for p in plans if {'school_split', 'school_split_from'} & set(p)], 'a correct reply needs no repair')
        elif mode == 'omit_all_but_first':
            model, = [p for p in plans if 'school_selection_receipt' in p]
            formed = [p for p in plans if 'school_split_from' in p]
            self.assertEqual((model['school_selection_receipt'], 'school_split' in model), (receipt, False), 'model item untouched')
            self.assertEqual(len(formed), case['expected_tasks'] - 1)
            for plan in formed:
                mark = plan['school_split_from']
                self.assertEqual((mark['index'], mark['receipt'], mark['ref'], mark['omitted']), (0, receipt, refs[0], True))
                self.assertIn(mark['quote'], case['messages'][0], 'compiled from the original run')
        else:
            merged, = [p for p in plans if 'school_split' in p]
            formed, = [p for p in plans if 'school_split_from' in p]
            self.assertEqual(merged['school_selection_receipt'], receipt, 'the model reading stays verbatim')
            self.assertNotIn('school_selection_receipt', formed)
            self.assertEqual((formed['school_split_from']['receipt'], formed['school_split_from']['ref']), (receipt, refs[0]))
            self.assertNotIn('omitted', formed['school_split_from'])
            self.assertIn(formed['school_split_from']['quote'], case['messages'][0], 'formed from the original run')
        before = [dict(r) for r in rows]
        later = self._rounds([6, 12])
        after, _, _, tasks_after, _ = self._state()
        self.assertEqual([(r['created'], r['failed']) for r in later], [(0, 0), (0, 0)])
        self.assertEqual((after, len(tasks_after), self.model.call_count), (before, case['expected_tasks'], 1), 'reopen adds nothing')
        return rows, tasks, refs

    def test_root_heldout_outcomes_reach_their_own_tasks_in_natural_rounds(self):
        for case in ROOT_V4_HELDOUT:
            with self.subTest(case=case['id']):
                self._check(case)

    def test_continued_item_reads_its_day_only_from_a_proven_scope(self):
        """A04's 还要完成《图形册》第3题 continues 数学今晚完成《算数卡》第2题 (same subject, the child, a learning verb, no day,
        condition or change of its own, one day in the whole original), so 今晚 is its own scope. Controls: its own 明天 wins;
        a parent's administrative item or another subject never takes 今晚; a dateless original stays dateless; an explicit
        common scope (两项今晚都要完成) gives both items its day."""
        for case in SCOPE_CONTROLS:
            with self.subTest(case=case['id']):
                self._check(case)

    def test_omitted_outcome_is_compiled_from_the_original_on_the_first_call(self):
        """v6 changes v5's expectation (hold, then the identical request until exhausted): the reply returns only the first
        outcome, yet the complete original states the other affirmatively. The first call compiles it from the original run;
        no repair call, the model item untouched, nothing new in later rounds."""
        for case in ROOT_V4_HELDOUT + SCOPE_CONTROLS:
            if case['expected_tasks'] < 2:continue
            with self.subTest(case=case['id']):
                self._check(case, 'omit_all_but_first')

    def test_instrument_or_destination_name_is_no_separate_outcome(self):
        """A closed name the work is checked against or uploaded to is no object of its own: one item, never split."""
        for text, quote, goal in (
                ('数学今晚完成《晨光练习册》第2页，对照《参考答案》自己批改。', '数学今晚完成《晨光练习册》第2页', '完成《晨光练习册》第2页。\n对照《参考答案》自己批改。'),
                ('英语今晚朗读《青叶英语》第2页两遍，录音上传到《班级小程序》。', '英语今晚朗读《青叶英语》第2页两遍', '朗读《青叶英语》第2页两遍。\n录音上传到《班级小程序》。')):
            with self.subTest(text=text):
                self.setUp()
                payload, refs = self._day([('18:10', '虚构老师', 'qa-teacher', text)])
                self._use_replies(payload, [dict(proposals=[self._proposal(quote, refs, text[:2], goal)])])
                result = agent.run_once(self.app, self.now)
                rows, _, _, tasks, _ = self._state()
                self.assertEqual((result['failed'], len(rows), len(tasks), self.model.call_count), (0, 1, 1, 1))
                self.assertFalse({'school_split', 'school_split_from'} & set(json.loads(rows[0]['plan'])))

    def test_distinct_closed_names_sharing_characters_are_separate_objects(self):
        """v7 (Root C01/C04): 《长叶写本》 beside 《长叶读本》 and 《翠云同步册》 beside 《青石同步册》 are other objects however many
        characters they share. Whether the reply returns only the first outcome or merges both, the other one is its own
        item with its own day on the first call, and natural rounds add nothing."""
        for case in ROOT_V7_CLOSED:
            if case['expected_tasks'] < 2:continue
            for mode in (case['first_response_mode'], 'merge_all_into_first'):
                with self.subTest(case=case['id'], mode=mode):
                    self._check(case, mode)

    def test_same_closed_object_step_before_the_item_stays_its_own(self):
        """v7 (Root C03, beside A03): 请家长在《长叶读本》第3页签字 before 英语今晚完成《长叶读本》第3页 is the same book's same page:
        one item whose saved goal keeps the parent's signature, never an extra administrative item. Another closed object's
        signature in the same place (《长叶写本》) is no step of this item: it is its own item."""
        for case in [c for c in ROOT_V7_CLOSED if c['expected_tasks'] == 1] + [ROOT_V4_HELDOUT[2], OTHER_OBJECT_SIGNATURE]:
            with self.subTest(case=case['id']):
                self._check(case)

    def test_short_read_item_beside_a_distinct_closed_name_keeps_the_other_object(self):
        """B03's shape: the other closed object is its own item with its own day. The first item's short 读 day is a separate
        date fix, so only its words are checked here."""
        self.setUp()
        payload, refs = self._day([('18:10', '虚构老师', 'qa-teacher', '英语今晚读《长叶读本》第3页；明天完成《长叶写本》第2页。')])
        first = dict(proposals=[self._proposal('英语今晚读《长叶读本》第3页', refs, '英语', '英语今晚读《长叶读本》第3页。', due='2026-11-04')])
        self._use_replies(payload, copy.deepcopy([first] * 3))
        self._rounds()
        rows, job, _, tasks, _ = self._state()
        self.assertEqual((job['done'], len(rows), self.model.call_count), (1, 2, 1), [r['body'] for r in rows])
        # Alone (英语今晚读《长叶读本》第3页。) the short 读 item is held for review without a day too: that date fix is separate.
        own, = [r for r in rows if '长叶读本' in r['title'] + r['body']]
        other, = [t for t in tasks if '长叶写本' in t['action']]
        self.assertEqual(other['due'], '2026-11-05')
        self.assertNotIn('长叶写本', own['title'] + own['body'])
        self.assertNotIn('长叶读本', other['title'] + other['action'])

    def test_closed_name_identity_reader(self):
        """Root's reader facts: a closed name is its object's whole identity; an unclosed short name and a clause's own words
        beside another closed name still name the item. Before the item, only the same book's same range and day is its step."""
        names = agent._school_step_names
        self.assertFalse(names('明天完成《长叶写本》第2页', '《长叶读本》'))
        self.assertFalse(names('明天完成《翠云同步册》第2页', '《青石同步册》'))
        self.assertTrue(names('请家长在《长叶读本》第3页签字', '《长叶读本》'))
        self.assertTrue(names('完成后请家长在练习册上签字', '《晨光练习册》'))
        self.assertTrue(names('《长叶写本》和读本都请家长签字', '《长叶读本》'))
        owned = lambda step, text: agent._school_step_owned('英语今晚完成《长叶读本》第3页，' + step + '。', step + '。', [text])[0]
        self.assertTrue(owned('请家长在《长叶读本》第3页签字', '请家长在《长叶读本》第3页签字；英语今晚完成《长叶读本》第3页。'))
        for other in ('请家长在《长叶写本》第3页签字', '请家长在《长叶读本》第4页签字', '明天请家长在《长叶读本》第3页签字'):
            with self.subTest(other=other):
                self.assertFalse(owned(other, other + '；英语今晚完成《长叶读本》第3页。'))

    # --- v6: what the program may not compile, and the Store state machine around a compiled item ---

    def _ingest(self, messages, first=11, offset=0):
        """messages: dicts (hm, text, optional sender/publisher/kind/unread) stored as one collector payload after the last."""
        payload = self.fixture.payload(expected=str(first - 1), cursor=str(first - 1 + len(messages)), offset=offset)
        payload['messages'] = [dict(id=str(first + i), message_order=str(first + i), time='2026-11-04T' + m['hm'] + ':00+08:00',
                                    kind=m.get('kind', 'text'), sender=m.get('sender', '虚构老师'), sender_id=m.get('publisher', 'qa-teacher'),
                                    text=m['text'], unread=m.get('unread', False)) for i, m in enumerate(messages)]
        self.store.ingest(payload)
        return payload['messages'], ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]

    def _seam(self, steps):
        """Replies by step: a reply, an exception (a failed request) or a function of the request's own evidence."""
        seen = []

        def reply(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual((name, data_path), ('family_agent_selection', self.app.DATA))
            context = json.loads(messages[-1]['content'])
            seen.append(context['evidence'])
            self.assertLessEqual(len(seen), len(steps), 'no call beyond the bounded attempts')
            step = steps[len(seen) - 1]
            if isinstance(step, Exception):raise step
            return copy.deepcopy(step(context) if callable(step) else step)
        self.model.side_effect = reply
        return seen

    def _own_reply(self, context, own_ref):
        """The A01 learning item alone for its own original (the form left out); any other evidence cited as reference."""
        refs = [e['ref'] for e in context['evidence']]
        proposals = [self._proposal(A01_OWN, [own_ref], '语文', A01_OWN + '。', due='2026-11-04')] if own_ref in refs else []
        for e in context['evidence']:
            if e['ref'] == own_ref:continue
            if '青叶英语' in e['text']:
                proposals.append(self._proposal('英语今晚朗读《青叶英语》第2页两遍', [e['ref']], '英语', '英语今晚朗读《青叶英语》第2页两遍。', due='2026-11-04'))
                continue
            ref = self._proposal(e['text'].strip('。'), [e['ref']], '', '', purpose='optional')
            ref.update(task_state='reference', task_title='', task_goal='', task_reason='虚构固定回执：更正或撤回，仅保留原文。')
            proposals.append(ref)
        return dict(proposals=proposals)

    def _assert_not_compiled(self, name, originals, calls=3):
        """The program never compiled an item for name; the batch either kept the model's own reading or the existing bounded
        retry (at most three calls per evidence version, exhaustion stated), and the originals stay."""
        rows, _, saved, tasks, _ = self._state()
        with self.store._db() as c:
            jobs = [dict(r) for r in c.execute("SELECT attempts,done,error FROM agent_jobs WHERE id LIKE 'messages:%'")]
        self.assertFalse([r['id'] for r in rows if 'school_split_from' in json.loads(r['plan'])], 'no program item')
        self.assertFalse([t['id'] for t in tasks if name in t['title'] + t['action']], 'no task from the uncertain words')
        self.assertLessEqual(self.model.call_count, calls)
        self.assertEqual(saved, originals)
        if not any(j['done'] for j in jobs):self.assertTrue(any(j['attempts'] == 3 and '上限' in j['error'] for j in jobs), jobs)
        return rows, jobs, tasks

    def test_uncertain_or_unread_outcome_is_never_compiled(self):
        """Not the original's affirmed current requirement, so never the program's: a question, a condition earlier in the
        clause chain, a past completion, a change; and an unread original whose words are incomplete."""
        for text, unread in ((A01_OWN + '；《秋游告知单》需要家长签字吗？', False),
                             (A01_OWN + '；如果参加秋游，《秋游告知单》家长签字，明早交回。', False),
                             (A01_OWN + '；《秋游告知单》家长已签字交回，谢谢。', False),
                             (A01_OWN + '；《秋游告知单》改为下周一交回。', False),
                             (ROOT_V4_HELDOUT[0]['messages'][0], True)):
            with self.subTest(text=text, unread=unread):
                self.setUp()
                originals, refs = self._ingest([dict(hm='18:10', text=text, unread=unread)])
                self._seam([lambda context, own=refs[0]: self._own_reply(context, own)] * 3)
                self._rounds([0, 6, 12, 30, 60, 120])
                self._assert_not_compiled('秋游告知单', originals)

    def test_withdrawn_or_recalled_source_is_not_compiled_from_the_old_basis(self):
        """The same teacher's later correction names the form, or a later message of that teacher is recalled (content
        unknown): the program does not compile the form from the earlier words; the batch keeps the bounded retry."""
        for later in (dict(hm='18:40', text='更正：《秋游告知单》不用交了。'), dict(hm='18:40', kind='recalled', text='[已撤回，正文未读取]')):
            with self.subTest(later=later['text']):
                self.setUp()
                originals, refs = self._ingest([dict(hm='18:10', text=ROOT_V4_HELDOUT[0]['messages'][0]), later])
                self._seam([lambda context, own=refs[0]: self._own_reply(context, own)] * 3)
                self._rounds([0, 6, 12, 30, 60, 120])
                self._assert_not_compiled('秋游告知单', originals)

    def test_version_change_after_a_failed_request_is_read_whole(self):
        """Round 0's request fails (counted). The teacher's correction arrives before the next natural round: that round reads
        the current evidence, so the form is never compiled from the old basis; with no correction (control) the same retry
        compiles it once."""
        for corrected in (True, False):
            with self.subTest(corrected=corrected):
                self.setUp()
                originals, refs = self._ingest([dict(hm='18:10', text=ROOT_V4_HELDOUT[0]['messages'][0])])
                # A new evidence version gets its own bounded attempts (MAX_ATTEMPTS each), so at most 1 + 3 calls here.
                seen = self._seam([agent.AgentError('虚构模型请求失败')] + [lambda context, own=refs[0]: self._own_reply(context, own)] * 3)
                first, = self._rounds([0])
                self.assertEqual((first['failed'], self.model.call_count), (1, 1))
                if corrected:
                    more, _ = self._ingest([dict(hm='18:14', text='更正：《秋游告知单》不用交了。')], first=12, offset=1)
                    originals = originals + more
                self._rounds([6, 12, 30, 60, 120])
                if corrected:
                    self._assert_not_compiled('秋游告知单', originals, calls=4)
                    self.assertTrue(any(any('不用交了' in e['text'] for e in evidence) for evidence in seen[1:]), 'the retry read the correction')
                else:
                    rows, job, _, tasks, _ = self._state()
                    self.assertEqual((self.model.call_count, job['attempts'], job['done'], len(tasks)), (2, 2, 1, 2))
                    self.assertEqual(len([t for t in tasks if '秋游告知单' in t['title'] + t['action']]), 1)

    def test_compiled_task_is_neither_repeated_nor_overwritten(self):
        """Store state machine around a compiled item: a parent's edit of that task between natural rounds is kept, later
        rounds and a later batch of the same day never compile the same outcome again."""
        self.setUp()
        originals, refs = self._ingest([dict(hm='18:10', text=ROOT_V4_HELDOUT[0]['messages'][0])])
        self._seam([lambda context, own=refs[0]: self._own_reply(context, own)] * 2)
        self._rounds([0])
        rows, job, _, tasks, _ = self._state()
        self.assertEqual((job['done'], len(tasks), self.model.call_count), (1, 2, 1))
        form, = [t for t in tasks if '秋游告知单' in t['title'] + t['action']]
        family_task_focus.save(self.app, dict(id=form['id'], version=0, request_key='synthetic-v6-parent-edit', mode='next',
                                              next_action='', waiting_for='', review_on='', scheduled_on='2026-11-05',
                                              title='家长改：《秋游告知单》周四交', goal='家长已改：告知单签好后周四交给班主任。'))
        self.app.save_task(dict(id=form['id'], status='待跟进', note='虚构家长安排保留。'))
        rows_edit, _, _, tasks_edit, _ = self._state()
        edited = next(t for t in self.app.tasks() if t['id'] == form['id'])  # the parent's view: title, text and arrangement
        self.assertEqual((edited['title'], edited['focus']['scheduled_on']), ('家长改：《秋游告知单》周四交', '2026-11-05'))
        self.assertTrue(edited['action'].startswith('家长已改：'), edited['action'])
        self._rounds([6, 12])
        rows_after, _, _, tasks_after, _ = self._state()
        self.assertEqual((rows_after, tasks_after, self.model.call_count), (rows_edit, tasks_edit, 1), 'the parent edit stays')
        more, _ = self._ingest([dict(hm='18:40', text='英语今晚朗读《青叶英语》第2页两遍。', sender='虚构英语老师', publisher='qa-teacher-en')], first=12, offset=13)
        self._rounds([30, 60])
        rows_last, job, saved, tasks_last, _ = self._state()
        self.assertEqual(saved, originals + more)
        self.assertEqual(self.model.call_count, 2)
        self.assertEqual(len([t for t in tasks_last if '秋游告知单' in t['title'] + t['action']]), 1, 'compiled once')
        kept = next(t for t in self.app.tasks() if t['id'] == form['id'])
        self.assertEqual((kept['title'], kept['action'], kept['focus']), (edited['title'], edited['action'], edited['focus']), 'the parent edit stays')
        self.assertEqual(len(tasks_last), 3)


if __name__ == '__main__':
    unittest.main()

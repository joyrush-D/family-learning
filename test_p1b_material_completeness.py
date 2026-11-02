"""P1b: an original's requirements keep their own date roles and the same homework's submission (fictional development examples only)."""
import unittest

import family_agent as agent

SENT='2026-11-08T18:00:00+08:00';REF='message:fictional-class:1'


def roles(quote,others=()):
    return agent._school_original_roles([dict(ref=REF,quote=quote)],[dict(ref=REF,time=SENT,text=quote)],list(others))


class OriginalDateRoleTests(unittest.TestCase):
    def test_completion_and_handback_are_two_roles_of_one_requirement(self):
        for quote in ('今晚（2026年11月8日）做练习册第7页第2–4题，每题写步骤；明早（11月9日早上）交。',
                      '今晚做练习册第7页第2–4题，每题写步骤；明早交。',
                      '今晚做练习册第7页第2–4题，每题写步骤，明天早上交。'):
            with self.subTest(quote=quote):self.assertEqual(roles(quote),({'2026-11-08'},'2026-11-09'))

    def test_morning_reading_check_is_the_check_role(self):
        self.assertEqual(roles('今晚朗读第8课三遍，明天早读查。'),({'2026-11-08'},'2026-11-09'))
        self.assertIn('check',agent._school_clause_roles('明天早读查'))
        self.assertNotIn('check',agent._school_clause_roles('今晚查资料'))

    def test_conflicting_or_unknown_days_stay_for_the_existing_date_checks(self):
        self.assertIsNone(roles('今晚做练习册第7页第2–4题，每题写步骤；明天（11月10日）交。'))
        self.assertIsNone(agent._school_bracket_restated('明早（11月9日晚上）交','2026-11-08'))
        self.assertIsNone(agent._school_bracket_restated('今晚（11月8日）做第7页','') )
        self.assertEqual(agent._school_bracket_restated('今晚（11月8日）做第7页','2026-11-08'),'今晚做第7页')
        self.assertEqual(agent._school_bracket_restated('第7页第2–4题','2026-11-08'),'第7页第2–4题')

    def test_another_actions_quote_within_the_range_makes_it_shared(self):
        self.assertIsNone(roles('今晚做练习册第7页第2–4题，每题写步骤；明早交。',['每题写步骤']))


class SameHomeworkSubmissionTests(unittest.TestCase):
    brief=dict(title='语文：朗读第8课',goal='明天完成朗读第8课三遍，音频上传课堂平台。',purpose='learning',submission='音频上传课堂平台')

    def test_the_homeworks_own_upload_step_lends_its_words(self):
        self.assertTrue(agent._school_own_submission_sibling(self.brief,dict(task_purpose='admin',task_title='朗读音频提交',task_goal='音频上传课堂平台。')))

    def test_another_subjects_upload_or_a_receipt_stays_apart(self):
        for other in (dict(task_purpose='admin',task_title='数学：练习册照片上传',task_goal='数学练习册第7页照片上传课堂平台。'),
                      dict(task_purpose='admin',task_title='家长回执',task_goal='今晚选参加或不参加并签字，孩子周五交。'),
                      dict(task_purpose='learning',task_title='朗读音频提交',task_goal='音频上传课堂平台。')):
            with self.subTest(other=other['task_title']):self.assertFalse(agent._school_own_submission_sibling(self.brief,other))
        self.assertFalse(agent._school_own_submission_sibling(dict(self.brief,submission=''),dict(task_purpose='admin',task_title='朗读音频提交',task_goal='音频上传课堂平台。')))


if __name__=='__main__':
    unittest.main()

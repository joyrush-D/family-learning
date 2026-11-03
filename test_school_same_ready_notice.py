"""Fictional regressions: a saved item's unchanged steps stay its steps, and true negations stay negations."""
import unittest

import family_agent as agent


class StepNegationTest(unittest.TestCase):
    def test_unchanged_steps_are_no_negation(self):
        for clause in ('写算式、验算和家长签字、周五交回都不变', '家长签字和周五交回仍不变', '交回时间不变'):
            self.assertFalse(agent._school_step_negated(clause), clause)

    def test_true_negations_stay(self):
        for clause in ('家长不用签字', '不需要录音', '第4题不做', '签字后不用交', '签字不变，不用交回', '无需上传', '别交到群里'):
            self.assertTrue(agent._school_step_negated(clause), clause)

    def test_reminders_stay_no_negation(self):
        for clause in ('别忘了请家长签字', '不要忘记周五交回'):
            self.assertFalse(agent._school_step_negated(clause), clause)


def ev(ref, text, time, sender='数学李老师', publisher='publisher:fiction-math'):
    return dict(ref=ref, text=text, time=time, sender=sender, publisher=publisher, kind='text', content_incomplete=False,
                attachments=[], related_messages=[ref], source='虚构班级')


class RoleDaysTest(unittest.TestCase):
    LEAD = '数学《星河练习》第12页第1—4题，今晚完成。'
    HOME = LEAD + '每题写出算式并验算，请家长签字，周五交给我。'

    def test_range_correction_keeping_days_keeps_both_roles(self):
        fix = ev('m:b', '更正今天数学《星河练习》的范围：第12页只做第1—3题，第4题不做。写算式、验算和家长签字、周五交回都不变。', '2026-11-04T17:00:00+08:00')
        self.assertEqual(agent._school_role_days(self.LEAD, [ev('m:a', self.HOME, '2026-11-04T15:40:00+08:00'), fix], []), ({'2026-11-04'}, '2026-11-06'))

    def test_a_correction_moving_the_day_proves_no_roles(self):
        fix = ev('m:b', '更正今天数学《星河练习》的范围：第12页只做第1—3题。改为下周一交回。', '2026-11-04T17:00:00+08:00')
        self.assertIsNone(agent._school_role_days(self.LEAD, [ev('m:a', self.HOME, '2026-11-04T15:40:00+08:00'), fix], []))

    def test_another_teachers_unchanged_words_prove_no_roles(self):
        fix = ev('m:b', '更正今天数学《星河练习》的范围：第12页只做第1—3题。周五交回不变。', '2026-11-04T17:00:00+08:00', '语文周老师', 'publisher:fiction-other')
        self.assertIsNone(agent._school_role_days(self.LEAD, [ev('m:a', self.HOME, '2026-11-04T15:40:00+08:00'), fix], []))

    def test_another_subject_in_the_following_sentence_is_not_this_items(self):
        home = self.LEAD + '语文抄写词语，周五交给我。'
        self.assertIsNone(agent._school_role_days(self.LEAD, [ev('m:a', home, '2026-11-04T15:40:00+08:00')], []))

    def test_resource_today_is_no_action_day(self):
        quote = '英语《晨读单》见今天这份附件，今晚完成，做完放进英语夹里，明天带来。'
        self.assertEqual(agent._school_role_days(quote, [ev('m:c', quote, '2026-11-04T16:05:00+08:00', '英语王老师', 'publisher:fiction-en')], []),
                         ({'2026-11-04'}, '2026-11-05'))


class ListStepOwnershipTest(unittest.TestCase):
    TEXT = '英语《晨读单》见今天这份附件，今晚完成，做完放进英语夹里，明天带来。\n\n英语《晨读单》\n一、看图选词第1—3题。\n二、标星单词 under、near 各抄写一遍。'

    def test_lead_sentence_step_of_a_read_list_stays(self):
        goal = '完成英语《晨读单》：一、看图选词第1—3题；二、标星单词 under、near 各抄写一遍。\n做完放进英语夹里，明天带来。'
        self.assertTrue(agent._school_step_owned(goal, '做完放进英语夹里，明天带来。', [self.TEXT])[0])

    def test_another_objects_lead_step_stays_out(self):
        text = '语文《小溪本》今晚完成，做完放进语文夹里。\n\n英语《晨读单》\n一、看图选词第1—3题。\n二、标星单词 under、near 各抄写一遍。'
        goal = '完成英语《晨读单》：一、看图选词第1—3题；二、标星单词 under、near 各抄写一遍。\n做完放进语文夹里。'
        self.assertFalse(agent._school_step_owned(goal, '做完放进语文夹里。', [text])[0])


class ExcusedStepTest(unittest.TestCase):
    FACTS = '今晚朗读《溪边》第2、3自然段，各读两遍，读给家长听；不用录音，也不用上传，明早我抽听'

    def test_excusing_an_unrequired_step_is_no_change(self):
        self.assertFalse(agent._school_same_changes('朗读仍是《溪边》第2、3自然段各两遍，不用背诵，明早抽听。', self.FACTS))

    def test_only_unrequired_excuses_are_dropped(self):
        self.assertEqual(agent._school_unrequired_excuses_dropped('朗读仍是《溪边》第2、3自然段各两遍，不用背诵，明早抽听。', self.FACTS),
                         '朗读仍是《溪边》第2、3自然段各两遍，明早抽听。')
        self.assertEqual(agent._school_unrequired_excuses_dropped('不用读了，明早不抽听。', self.FACTS), '不用读了，明早不抽听。')

    def test_excusing_a_required_step_is_a_change(self):
        self.assertTrue(agent._school_same_changes('朗读仍是《溪边》第2、3自然段，不用读给家长听，明早抽听。', self.FACTS))


class Run3RegressionTest(unittest.TestCase):
    FACTS = '今晚朗读《溪边》第2、3自然段，各读两遍，读给家长听；不用录音，也不用上传，明早我抽听'

    def test_paragraph_numbers_never_stand_for_a_count(self):
        self.assertNotIn((3, ''), agent._school_counts('朗读《溪边》第2、3自然段，各读两遍', bound=True))
        self.assertFalse(agent._school_units_differ('朗读仍是《溪边》第2、3自然段各两遍，明早抽听。', self.FACTS))
        said = '朗读《溪边》第2、3自然段，各读三遍，读给家长听；不用录音，也不用上传，明早抽听。'
        self.assertTrue(agent._school_restated_reason(said, self.FACTS, said))
        same = '朗读《溪边》第2、3自然段，各读两遍，读给家长听；不用录音，也不用上传，明早抽听。'
        self.assertEqual(agent._school_restated_reason(same, self.FACTS, same), '')

    def test_same_title_of_another_subject_leads_no_step(self):
        text = '语文《每日练习》今晚完成，做完放进语文夹里。\n\n英语《每日练习》\n一、看图选词第1—3题。\n二、标星单词 under、near 各抄写一遍。'
        goal = '完成英语《每日练习》：一、看图选词第1—3题；二、标星单词 under、near 各抄写一遍。\n做完放进语文夹里。'
        self.assertFalse(agent._school_step_owned(goal, '做完放进语文夹里。', [text])[0])

    def test_a_paraphrased_waiver_keeps_the_change_review(self):
        said = '《溪边》仍默写两遍，不用动笔。'
        self.assertIn('不用动笔', agent._school_unrequired_excuses_dropped(said, '语文：默写《溪边》两遍。'))
        self.assertTrue(agent._school_restated_reason(said, '语文：默写《溪边》两遍。', '默写《溪边》两遍，不用动笔。'))

    def test_unchanged_correction_keeps_the_role_words(self):
        home = ev('m:a', RoleDaysTest.HOME, '2026-11-04T15:40:00+08:00')
        fix = ev('m:b', '更正今天数学《星河练习》的范围：第12页只做第1—3题，第4题不做。写算式、验算和家长签字、周五交回都不变。', '2026-11-04T17:00:00+08:00')
        found = agent._school_role_days(RoleDaysTest.LEAD, [home, fix], [], words=True)
        self.assertEqual(found[:2], ({'2026-11-04'}, '2026-11-06'))
        self.assertIn('周五交给我', found[2])


if __name__ == '__main__':
    unittest.main()

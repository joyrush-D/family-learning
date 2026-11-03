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


if __name__ == '__main__':
    unittest.main()

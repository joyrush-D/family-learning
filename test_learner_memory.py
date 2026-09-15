"""Correctable bi-temporal learner memory: append on confirm, supersede, read (R26)."""
import datetime as dt
import sqlite3
import unittest

import family_learner_memory as lm


def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    return c


NOW1 = dt.datetime(2026, 9, 10, 20, 0, 0)
NOW2 = dt.datetime(2026, 9, 20, 20, 0, 0)


def confirm(c, now, *, goal='goal-1', child='child-1', evidence, assessment, hypotheses,
            subject='英语', title='英语Unit3'):
    return lm.record_confirmation(c, now, child_id=child, goal_id=goal, subject=subject, title=title,
                                  confirmed_on=now.date().isoformat(), assessment=assessment,
                                  hypotheses=hypotheses, evidence_hash=evidence)


HYP = [dict(reason='ea/ee 形音对应不稳定', status='有支持', support=['record:1'], against=[]),
       dict(reason='整词字母顺序记忆弱', status='待验证', support=[], against=['record:2'])]


class LearnerMemoryTest(unittest.TestCase):
    def test_confirm_writes_assessment_and_hypotheses(self):
        c = conn()
        n = confirm(c, NOW1, evidence='h1', assessment='拼写仅4/10，ea/ee常混', hypotheses=HYP)
        self.assertEqual(n, 3)  # one assessment + two hypotheses
        card = lm.learner_card(c, 'child-1')
        self.assertEqual(len(card), 1)
        g = card[0]
        self.assertEqual(g['goal_id'], 'goal-1')
        self.assertEqual(g['assessment'], '拼写仅4/10，ea/ee常混')
        self.assertEqual([h['reason'] for h in g['hypotheses']], ['ea/ee 形音对应不稳定', '整词字母顺序记忆弱'])
        self.assertEqual(g['hypotheses'][0]['support'], ['record:1'])
        self.assertEqual(g['confirmed_on'], '2026-09-10')

    def test_replay_same_confirmation_does_not_duplicate(self):
        c = conn()
        confirm(c, NOW1, evidence='h1', assessment='A', hypotheses=HYP)
        again = confirm(c, NOW1, evidence='h1', assessment='A', hypotheses=HYP)
        self.assertEqual(again, 0)  # same evidence_hash on the current valid rows -> replay, no write
        self.assertEqual(len(lm.timeline(c, 'child-1')), 3)

    def test_new_confirmation_supersedes_and_keeps_history(self):
        c = conn()
        confirm(c, NOW1, evidence='h1', assessment='旧判断：ea/ee 混', hypotheses=HYP[:1])
        confirm(c, NOW2, evidence='h2', assessment='新判断：ea/ee 稳定，改看整词',
                hypotheses=[dict(reason='整词字母顺序记忆弱', status='有支持', support=['record:9'], against=[])])
        card = lm.learner_card(c, 'child-1')
        self.assertEqual(len(card), 1)
        self.assertEqual(card[0]['assessment'], '新判断：ea/ee 稳定，改看整词')
        self.assertEqual(card[0]['confirmed_on'], '2026-09-20')
        # Full history keeps the superseded judgment, marked invalid_from; current stays open.
        tl = lm.timeline(c, 'child-1')
        self.assertEqual(len(tl), 4)
        invalidated = [r for r in tl if r['invalid_from'] is not None]
        current = [r for r in tl if r['invalid_from'] is None]
        self.assertEqual(len(current), 2)  # new assessment + new hypothesis
        self.assertTrue(all(r['confirmed_on'] == '2026-09-10' for r in invalidated))
        self.assertEqual({r['invalid_from'] for r in invalidated}, {NOW2.isoformat()})

    def test_per_goal_supersession_is_independent(self):
        c = conn()
        confirm(c, NOW1, goal='goal-A', evidence='a1', assessment='目标A判断', hypotheses=[])
        confirm(c, NOW1, goal='goal-B', evidence='b1', assessment='目标B判断', hypotheses=[])
        confirm(c, NOW2, goal='goal-A', evidence='a2', assessment='目标A新判断', hypotheses=[])
        card = {g['goal_id']: g for g in lm.learner_card(c, 'child-1')}
        self.assertEqual(card['goal-A']['assessment'], '目标A新判断')
        self.assertEqual(card['goal-B']['assessment'], '目标B判断')  # untouched by goal-A's new confirmation

    def test_no_judgment_writes_nothing(self):
        c = conn()
        self.assertEqual(confirm(c, NOW1, evidence='h1', assessment='   ', hypotheses=[]), 0)
        self.assertEqual(lm.learner_card(c, 'child-1'), [])
        # A malformed hypothesis (no reason) is skipped, not stored.
        self.assertEqual(confirm(c, NOW1, evidence='h1', assessment='', hypotheses=[dict(status='有支持')]), 0)

    def test_reads_are_safe_before_any_write(self):
        c = conn()  # table does not exist yet
        self.assertEqual(lm.learner_card(c, 'child-1'), [])
        self.assertEqual(lm.timeline(c, 'child-1'), [])

    def test_prior_confirmations_returns_only_superseded_events_newest_first(self):
        c = conn()
        confirm(c, NOW1, evidence='h1', assessment='第一次判断', hypotheses=HYP[:1])
        # No supersession yet: the current confirmation is not a "prior" one.
        self.assertEqual(lm.prior_confirmations(c, 'child-1', 'goal-1'), [])
        confirm(c, NOW2, evidence='h2', assessment='第二次判断', hypotheses=HYP)
        prior = lm.prior_confirmations(c, 'child-1', 'goal-1')
        self.assertEqual(len(prior), 1)  # the first confirmation is now superseded history
        self.assertEqual(prior[0]['assessment'], '第一次判断')
        self.assertEqual(prior[0]['confirmed_on'], '2026-09-10')
        self.assertEqual([h['reason'] for h in prior[0]['hypotheses']], ['ea/ee 形音对应不稳定'])
        # The current (valid) judgment is excluded from prior_confirmations.
        self.assertEqual(lm.learner_card(c, 'child-1')[0]['assessment'], '第二次判断')

    def test_manual_plan_placeholder_is_recorded_as_confirmed_state(self):
        c = conn()
        n = confirm(c, NOW1, evidence='m1', assessment='家长制定的计划，尚无本轮助手评估。', hypotheses=[])
        self.assertEqual(n, 1)
        self.assertEqual(lm.learner_card(c, 'child-1')[0]['hypotheses'], [])


if __name__ == '__main__':
    unittest.main()

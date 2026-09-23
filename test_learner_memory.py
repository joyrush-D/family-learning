"""Correctable bi-temporal learner memory: append on confirm, supersede, read (R26)."""
import datetime as dt
import json
import sqlite3
import unittest

import family_learner_memory as lm


def conn():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    return c


NOW1 = dt.datetime(2026, 9, 10, 20, 0, 0)
NOW1_LATER = dt.datetime(2026, 9, 10, 21, 0, 0)
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

    def test_same_evidence_with_changed_judgment_is_a_new_confirmation(self):
        c = conn()
        confirm(c, NOW1, evidence='h1', assessment='旧判断', hypotheses=HYP[:1])
        written = confirm(c, NOW2, evidence='h1', assessment='家长核对后的新判断', hypotheses=HYP[1:])
        self.assertEqual(written, 2)
        self.assertEqual(lm.learner_card(c, 'child-1')[0]['assessment'], '家长核对后的新判断')
        self.assertEqual(len(lm.prior_confirmations(c, 'child-1', 'goal-1')), 1)

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
        raw = c.execute('SELECT id,invalid_from,superseded_by FROM learner_memory ORDER BY id').fetchall()
        replacement = next(r['id'] for r in raw if r['invalid_from'] is None)
        self.assertTrue(all(r['superseded_by'] == replacement for r in raw if r['invalid_from'] is not None))
        self.assertTrue(all(r['superseded_by'] is None for r in raw if r['invalid_from'] is None))

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

    def test_prior_confirmations_orders_same_day_by_confirmation_time(self):
        c = conn()
        confirm(c, NOW1, evidence='h1', assessment='当天第一次判断', hypotheses=[])
        confirm(c, NOW1_LATER, evidence='h2', assessment='当天第二次判断', hypotheses=[])
        confirm(c, NOW2, evidence='h3', assessment='现判断', hypotheses=[])
        self.assertEqual([x['assessment'] for x in lm.prior_confirmations(c, 'child-1', 'goal-1')],
                         ['当天第二次判断', '当天第一次判断'])
        c = conn()
        confirm(c, NOW1, goal='goal-A', evidence='a1', assessment='目标A', hypotheses=[])
        confirm(c, NOW1_LATER, goal='goal-B', evidence='b1', assessment='目标B', hypotheses=[])
        self.assertEqual([x['goal_id'] for x in lm.learner_card(c, 'child-1')], ['goal-B', 'goal-A'])

    def test_manual_plan_placeholder_is_recorded_as_confirmed_state(self):
        c = conn()
        n = confirm(c, NOW1, evidence='m1', assessment='家长制定的计划，尚无本轮助手评估。', hypotheses=[])
        self.assertEqual(n, 1)
        self.assertEqual(lm.learner_card(c, 'child-1')[0]['hypotheses'], [])

    # --- R26: a cited record corrected after a confirmation leaves that judgment without its basis ---
    def _records(self):
        c = conn()
        c.execute("CREATE TABLE records (id INTEGER PRIMARY KEY, child TEXT, day TEXT, category TEXT, subject TEXT, title TEXT, "
                  "note TEXT, score REAL, total REAL, related_record_id INTEGER, followup_kind TEXT DEFAULT '', "
                  "assistance TEXT DEFAULT '', practice_relation TEXT DEFAULT '', comparison_note TEXT DEFAULT '', attachments TEXT DEFAULT '[]')")
        c.execute('CREATE TABLE revisions (id INTEGER PRIMARY KEY, record_id INTEGER, previous TEXT, changed TEXT)')
        for n in range(1, 5):
            c.execute("INSERT INTO records(id,child,day,category,subject,title,note) VALUES(?,?,?,?,?,?,?)",
                      (n, '小明', '2026-09-0%d' % n, '学习进展', '英语', '记录%d' % n, '原文%d' % n))
        return c

    def _edit(self, c, rid, when, **changes):  # the app logs the previous row, then updates it
        prev = dict(c.execute('SELECT * FROM records WHERE id=?', (rid,)).fetchone())
        c.execute('INSERT INTO revisions(record_id,previous,changed) VALUES(?,?,?)', (rid, json.dumps(prev, ensure_ascii=False), when.isoformat()))
        if changes:
            c.execute('UPDATE records SET ' + ','.join(k + '=?' for k in changes) + ' WHERE id=?', (*changes.values(), rid))

    def test_corrected_refs_counts_only_material_edits_after_the_confirmation(self):
        c = self._records(); own = lambda name: name == '小明'
        self._edit(c, 1, NOW1 - dt.timedelta(hours=1), note='确认前已更正')  # the judgment already saw this
        self._edit(c, 2, NOW1_LATER)                                            # re-saved unchanged
        self._edit(c, 2, NOW1_LATER, attachments='["photo"]')                  # an original added, text unchanged
        self._edit(c, 3, NOW1_LATER, note='确认后更正：原来记错了')
        self._edit(c, 4, NOW1_LATER, child='小红')                              # corrected to the other child
        refs = ['record:4', 'record:1', 'task-feedback:x', 'record:2', 'record:3', 'record:99', 'record:3']
        self.assertEqual(lm.corrected_refs(c, refs, NOW1.isoformat(), own), ['record:4', 'record:3', 'record:99'])
        self.assertEqual(lm.corrected_refs(c, refs, '', own), [])  # no confirmation time, nothing to compare

    def test_corrected_refs_compares_aware_confirmation_times_on_the_local_clock(self):
        c = self._records(); own = lambda name: name == '小明'
        confirmed = NOW1.astimezone()  # goals store aware times; record edits are naive local times
        self._edit(c, 1, NOW1 - dt.timedelta(minutes=5), note='之前改的')
        self._edit(c, 2, NOW1 + dt.timedelta(minutes=5), note='之后改的')
        self.assertEqual(lm.corrected_refs(c, ['record:1', 'record:2'], confirmed.isoformat(), own), ['record:2'])

    def test_history_lists_the_judgments_whose_cited_records_were_corrected(self):
        c = self._records(); own = lambda name: name == '小明'
        confirm(c, NOW1, evidence='h1', assessment='A', hypotheses=HYP)  # cites record:1 (support), record:2 (against)
        confirm(c, NOW2, evidence='h2', assessment='B', hypotheses=HYP[:1])
        self._edit(c, 1, NOW1_LATER, note='确认后更正')
        prior = lm.prior_confirmations(c, 'child-1', 'goal-1', owned=own)
        self.assertEqual(prior[0]['corrected'], ['record:1'])
        self.assertEqual([h.get('corrected') for h in prior[0]['hypotheses']], [['record:1'], None])
        self.assertNotIn('corrected', lm.prior_confirmations(c, 'child-1', 'goal-1')[0])  # opt-in; old callers unchanged


if __name__ == '__main__':
    unittest.main()


class VideoEvidenceShapeTest(unittest.TestCase):
    def test_video_evidence_adds_only_the_confirmed_observations_and_names_the_remaining_media_as_unknown(self):
        from family_learner_memory import video_evidence, media_unreadable, VIDEO_CHECKED
        confirmed=[dict(upload_id='v1',review_id=3,token='t'*64,reviewed_at='2026-09-23T10:00:00',selected=[0],
                        observations=[dict(text='虚构画面',start_seconds=1,end_seconds=2)],uncertainties=[],duration_seconds=4.0,audio_assessed=False)]
        self.assertEqual(video_evidence(dict(attachments='["v1"]'),[]),{})
        one=video_evidence(dict(attachments='["v1"]',note='',score=None),confirmed)
        self.assertEqual(one,dict(video_observations=confirmed,video_observations_label=VIDEO_CHECKED,audio_assessed=False))
        self.assertTrue(video_evidence(dict(attachments='["v1","a2"]'),confirmed)['other_media_unread'])
        self.assertTrue(video_evidence(dict(attachments='["v1"]',transcript='x',transcript_state='待核对'),confirmed)['other_media_unread'])
        self.assertNotIn('other_media_unread',video_evidence(dict(attachments='["v1","a2"]',transcript='已核对文字',transcript_state='已核对'),confirmed))
        self.assertTrue(media_unreadable(dict(attachments='["v1"]',note='',score=None)))
        self.assertFalse(media_unreadable(dict(attachments='["v1"]',note='',score=None,**one)))

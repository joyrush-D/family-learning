"""P1a scope and save: a summary's note naming an earlier activity's day is no second day of this item (A); the ordinary
school_change write keeps the whole requirement the read projection keeps (B); a pending item's update proof binds a later
notice only when its own day is the item's (C) (PRD 3.2, AC01-03/11).

Newly made, wholly fictional development cases (not Root's blind samples): fictional teachers, groups and message ids, a
frozen Tuesday 2026-11-17. The model replies are handcrafted stand-ins, including the wrong update Root observed; no product
model is called. Every case goes through the ordinary selection (_select), Store save, refresh and the shared day projection,
and is read again from a freshly loaded app.
"""
import datetime as dt
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import family_review
import test_agent

SOURCES = [dict(id='fic-en2-qq', platform='qq', child_id='child-1', name='虚构乙英语群', cursor='10', enabled=True),
           dict(id='fic-sci2-wx', platform='wechat', child_id='child-1', name='虚构乙科学群', cursor='10', enabled=True)]
EN, SCI = 'fic-en2-qq', 'fic-sci2-wx'
DAY, THU, FRI = '2026-11-17', '2026-11-19', '2026-11-20'


def msg(ident, text, clock, sender='虚构乙英语老师', sender_id='fic-en2-teacher'):
    return dict(id=ident, sender_id=sender_id, sender=sender, text=text, time=DAY + 'T' + clock + ':00+08:00', kind='text',
                unread=False, message_order=ident)


def proposal(ref, quote, title, goal, *, state='ready', change='new', target='', due='', purpose='learning', subject='英语'):
    p = dict(title_quote=quote, focus='school', due=due, evidence=[{'ref': ref}], task_title=title, task_goal=goal, task_advice='',
             learning_subject=subject if purpose == 'learning' else '', learning_goal_id='', task_change=change, task_target_id=target,
             task_state=state, task_reason='虚构开发例的待核原因' if state == 'review' else '', task_purpose=purpose, task_submission='')
    assert set(p) == set(agent._school_fields['required'])
    return p


class ScopeSaveTests(unittest.TestCase):
    config = test_agent.AgentTests.config

    def setUp(self):
        test_agent.AgentTests.setUp(self)
        (self.data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': SOURCES}))

    def batch(self, source, messages, replies):
        now = dt.datetime.fromisoformat(messages[-1]['time']) + dt.timedelta(minutes=5)
        child = next(s['child_id'] for s in SOURCES if s['id'] == source)
        with self.app.connect() as c: previous = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (source,)).fetchone()
        self.store.ingest(dict(source_id=source, expected_cursor=previous['cursor'] if previous else '10', cursor=messages[-1]['id'],
                               checked_at=now.isoformat(), last_message_time=messages[-1]['time'], error='', messages=messages))
        evidence = [dict(m, ref='message:%s:%s' % (source, m['id']), publisher=agent._publisher(source, m), content_incomplete=False) for m in messages]
        targets = agent.school_targets(self.app, self.store, child, evidence=[m['text'] for m in messages])
        pending = agent.school_pending_targets(self.store, child)
        from family_goals import Store as Goals
        goals = Goals(self.app, self.store).school_candidates(child)
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': replies(targets, pending)}):
            items = agent._select('school', evidence, school_goals=goals, school_tasks=targets, school_pending=pending, as_of=now.date().isoformat())
        for item in items:
            item.update(child_id=child, kind='school')
            if item['plan'].get('school_learning'):
                item['plan']['school_messages'] = [dict(zip(('source_id', 'message_id'), e['ref'][8:].rsplit(':', 1))) for e in item.get('evidence', [])]
        self.store._save('p1a-scope:%s:%s' % (source, messages[-1]['id']), 'fictional', items, now)
        with patch.object(agent.family_llm, '_chat_json') as model, patch.object(agent, '_now', return_value=now):
            agent._refresh_school(self.app, self.store, now, 0); model.assert_not_called()
        return items

    def items_for(self, ref):
        with self.app.connect() as c:
            return [dict(r, plan=json.loads(r['plan'])) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")
                    if ref in [e['ref'] for e in json.loads(r['evidence'])]]

    def task(self, task_id):
        with self.app.connect() as c: return next(t for t in self.app.tasks(c) if t['id'] == task_id)

    def views(self, day):
        """The same day read by the running app and by a freshly loaded one (保存后重开)."""
        return [self.app.day_view('child-1', day), family_review.load_app(self.root, self.data).day_view('child-1', day)]

    def cards(self, view, word):
        return [r for g in view['groups'] for r in g['items'] if word in r['title']] + [u for u in view['upcoming'] if word in u['title']]


class SummaryRelationDayTests(ScopeSaveTests):
    """A: 和/与周四朗读第2段那场分别登记 relates a clear Friday item to the other activity; that day is no day of this item."""
    LESSON = '周五第二节英语课朗读《小树林》第5段。这次另外安排，和周四朗读第2段那场分别登记。'  # a class period: the ordinary path
    LOCATED = '周五英语课朗读《小树林》第5段。这次另外安排，和周四朗读第2段那场分别登记。'  # the program's own located action

    def thursday(self):
        r1 = 'message:%s:401' % EN
        self.batch(EN, [msg('401', '周四英语课朗读《小树林》第2段。', '17:00')], lambda targets, pending: [
            proposal(r1, '周四英语课朗读《小树林》第2段', '英语：周四英语课朗读《小树林》第2段', '周四英语课朗读《小树林》第2段。', due=THU)])
        thursday, = self.items_for(r1)
        self.assertEqual((thursday['state'], thursday['due']), ('accepted', THU), thursday)
        return thursday

    def friday(self, text, quote, goal, due=FRI):
        r2 = 'message:%s:402' % EN
        self.batch(EN, [msg('402', text, '20:00')], lambda targets, pending: [proposal(r2, quote, '英语：' + quote, goal, due=due)])
        item, = self.items_for(r2)
        return item

    def assert_two_days(self, thursday, item):
        self.assertEqual((item['state'], item['due']), ('accepted', FRI), item['plan'].get('school_task'))
        self.assertNotEqual(item['task_id'], thursday['task_id'], 'the independent activity is its own task')
        for day, word in ((THU, '第2段'), (FRI, '第5段')):
            for view in self.views(day):
                self.assertEqual([r['when'] for r in self.cards(view, word)], ['today'], (day, word))

    def test_lesson_item_keeps_its_own_day_beside_the_related_other_day(self):
        thursday = self.thursday()
        item = self.friday(self.LESSON, '周五第二节英语课朗读《小树林》第5段', '周五第二节英语课朗读《小树林》第5段；与周四朗读第2段那场是两项独立活动。')
        self.assert_two_days(thursday, item)
        self.assertIn('两项独立活动', self.task(item['task_id'])['action'], 'the relation note stays in the summary')

    def test_located_item_keeps_its_own_day_beside_the_related_other_day(self):
        thursday = self.thursday()
        item = self.friday(self.LOCATED, '周五英语课朗读《小树林》第5段', '周五英语课朗读《小树林》第5段；与周四朗读第2段那场是两项独立活动。')
        self.assert_two_days(thursday, item)
        self.assertIn('分别登记', self.task(item['task_id'])['action'], 'the original relation words stay')

    def test_a_relation_day_the_original_does_not_state_is_still_read(self):
        self.thursday()
        # The summary relates this reading to a Wednesday the original never names: that day is still the summary's own.
        item = self.friday(self.LESSON, '周五第二节英语课朗读《小树林》第5段', '周五第二节英语课朗读《小树林》第5段；与周三朗读那场是两项独立活动。')
        self.assertNotEqual((item['state'], item['due']), ('accepted', FRI))

    def test_a_summary_moving_this_item_to_the_related_day_still_fails(self):
        self.thursday()
        # The original states Friday; a summary also dating this reading Thursday contradicts it, relation note or not.
        item = self.friday(self.LESSON, '周五第二节英语课朗读《小树林》第5段', '周四第二节英语课朗读《小树林》第5段；与周四朗读第2段那场是两项独立活动。')
        self.assertNotEqual((item['state'], item['due']), ('accepted', FRI))

    def test_a_relation_clause_is_set_aside_only_for_its_own_clause(self):
        published = DAY
        evidence = [dict(ref='message:x:1', text=self.LESSON, time=DAY + 'T20:00:00+08:00')]
        self.assertEqual(agent._school_goal_dates('周五第二节英语课朗读《小树林》第5段；与周四朗读第2段那场是两项独立活动。', evidence), {FRI})
        # No relation in the original: the summary's second day is read as before (no day declared at all).
        plain = [dict(evidence[0], text='周五第二节英语课朗读《小树林》第5段。周四朗读第2段。')]
        self.assertEqual(agent._school_goal_dates('周五第二节英语课朗读《小树林》第5段；与周四朗读第2段那场是两项独立活动。', plain), {THU, FRI})
        self.assertEqual(agent._school_apart_free('周五朗读第5段。这次另外安排，和周四朗读第2段那场分别登记。'), '周五朗读第5段。这次另外安排，。')
        self.assertEqual(published, DAY)


class PendingOtherOccurrenceTests(ScopeSaveTests):
    """C: a later clear Friday reading of the same text is another occurrence, not the Thursday pending item's update."""

    def thursday_pending(self):
        r1 = 'message:%s:501' % EN
        self.batch(EN, [msg('501', '周四英语课展示朗读《小树林》，具体段落另通知。', '17:00')], lambda targets, pending: [
            proposal(r1, '周四英语课展示朗读《小树林》，具体段落另通知', '英语：周四英语课展示朗读《小树林》',
                     '周四英语课展示朗读《小树林》，具体段落另行通知。', state='review', due=THU)])
        first, = self.items_for(r1)
        self.assertEqual(first['state'], 'pending')
        return first

    def later(self, ident, text, quote, goal, due, change='update', clock='20:00'):
        ref = 'message:%s:%s' % (EN, ident)

        def replies(targets, pending):
            target = next(p['id'] for p in pending if '展示' in p['title'])
            return [proposal(ref, quote, '英语：' + quote, goal, change=change, target=target, due=due)]
        self.batch(EN, [msg(ident, text, clock)], replies)
        item, = self.items_for(ref)
        return item

    def test_wrong_update_to_pending_does_not_swallow_another_clear_occurrence(self):
        first = self.thursday_pending()
        item = self.later('502', '周五英语课再展示朗读一次《小树林》第5段。', '周五英语课再展示朗读一次《小树林》第5段',
                          '周五英语课再展示朗读一次《小树林》第5段。', FRI)
        self.assertNotIn('school_pending_of', item['plan'], 'a Friday occurrence is no update of the Thursday pending item')
        for view in self.views(FRI):
            self.assertEqual([r['when'] for r in self.cards(view, '第5段')], ['today'], 'the Friday occurrence keeps its own dated fact')
        for view in self.views(THU):
            self.assertEqual([r['when'] for r in self.cards(view, '展示') if '第5段' not in r['title']], ['today'],
                             'the Thursday pending item stays its own card')

    def test_one_message_with_the_pending_items_correction_and_another_occurrence_binds_each_apart(self):
        first = self.thursday_pending()
        ref = 'message:%s:505' % EN
        text = '周四英语课展示朗读的段落定为《小树林》第3段。另外安排周五英语课再展示朗读一次《小树林》第5段，和周四那场分别登记。'

        def replies(targets, pending):
            target = next(p['id'] for p in pending if '展示' in p['title'])
            return [proposal(ref, '周四英语课展示朗读的段落定为《小树林》第3段', '英语：周四英语课展示朗读《小树林》第3段',
                             '周四英语课展示朗读《小树林》第3段。', state='review', change='update', target=target, due=THU),
                    proposal(ref, '另外安排周五英语课再展示朗读一次《小树林》第5段', '英语：周五英语课再展示朗读一次《小树林》第5段',
                             '周五英语课再展示朗读一次《小树林》第5段；与周四那场分别登记。', due=FRI)]
        self.batch(EN, [msg('505', text, '20:10')], replies)
        items = {i['title']: i for i in self.items_for(ref)}
        correction = next(i for t, i in items.items() if '第3段' in t)
        other = next(i for t, i in items.items() if '第5段' in t)
        self.assertEqual(correction['plan'].get('school_pending_of', {}).get('item_id'), first['id'], 'the correction joins the pending card')
        self.assertNotIn('school_pending_of', other['plan'], 'the separate Friday occurrence is its own item')
        self.assertEqual(other['due'], FRI)

    def test_true_correction_on_the_same_day_still_joins_the_pending_card(self):
        first = self.thursday_pending()
        item = self.later('503', '周四英语课展示朗读的段落定为《小树林》第3段。', '周四英语课展示朗读的段落定为《小树林》第3段',
                          '周四英语课展示朗读《小树林》第3段。', THU)
        self.assertEqual(item['plan'].get('school_pending_of', {}).get('item_id'), first['id'])

    def test_a_stated_move_of_the_pending_day_still_joins_the_pending_card(self):
        first = self.thursday_pending()
        item = self.later('504', '周四英语课的《小树林》展示朗读改到周五英语课。', '周四英语课的《小树林》展示朗读改到周五英语课',
                          '《小树林》展示朗读改到周五英语课，具体段落另行通知。', FRI)
        self.assertEqual(item['plan'].get('school_pending_of', {}).get('item_id'), first['id'])



WED = '2026-11-18'


class RelationScopeTests(ScopeSaveTests):
    """run3: a relation note needs no demonstrative (A); an original saying its occurrence is separate refuses a pending link
    its short summary leaves unsaid, while a sibling's words in the same message do not (C). Newly made fictional cases."""
    QUOTE = '周五第二节英语课复述《风筝》第4段'
    LESSON = QUOTE + '。这两次分开安排。'

    def wednesday(self):
        r1 = 'message:%s:701' % EN
        self.batch(EN, [msg('701', '周三英语课复述《风筝》第1段。', '17:00')], lambda targets, pending: [
            proposal(r1, '周三英语课复述《风筝》第1段', '英语：周三英语课复述《风筝》第1段', '周三英语课复述《风筝》第1段。', due=WED)])
        wednesday, = self.items_for(r1)
        self.assertEqual((wednesday['state'], wednesday['due']), ('accepted', WED), wednesday)
        return wednesday

    def friday(self, goal, text=LESSON):
        ref = 'message:%s:702' % EN
        self.batch(EN, [msg('702', text, '20:00')], lambda targets, pending: [proposal(ref, self.QUOTE, '英语：' + self.QUOTE, goal, due=FRI)])
        item, = self.items_for(ref)
        return item

    def assert_apart(self, wednesday, item):
        self.assertEqual((item['state'], item['due']), ('accepted', FRI), item['plan'].get('school_task'))
        self.assertNotEqual(item['task_id'], wednesday['task_id'], 'the independent occurrence is its own task')
        for day, word in ((WED, '第1段'), (FRI, '第4段')):
            for view in self.views(day):
                self.assertEqual([r['when'] for r in self.cards(view, word)], ['today'], (day, word))

    def test_a_nominal_reference_without_a_demonstrative_dates_the_other_occurrence(self):
        wednesday = self.wednesday()
        self.assert_apart(wednesday, self.friday(self.QUOTE + '，与周三的复述属于两个独立安排。'))

    def test_the_other_word_order_reads_the_same(self):
        wednesday = self.wednesday()
        self.assert_apart(wednesday, self.friday(self.QUOTE + '；周三的复述与本次是两个独立安排。'))

    def test_a_demonstrative_reference_reads_the_same(self):
        wednesday = self.wednesday()
        self.assert_apart(wednesday, self.friday(self.QUOTE + '；和周三那次复述分开安排。'))

    SAME = QUOTE + '，和周三的复述分开安排。'  # the relation in this item's own sentence: the ordinary path reads its own clause

    def test_a_relation_in_the_items_own_sentence_dates_the_other_occurrence(self):
        wednesday = self.wednesday()
        self.assert_apart(wednesday, self.friday(self.QUOTE + '，与周三的复述属于两个独立安排。', text=self.SAME))

    def test_a_demonstrative_relation_in_the_items_own_sentence_reads_the_same(self):
        wednesday = self.wednesday()
        self.assert_apart(wednesday, self.friday(self.QUOTE + '；与周三复述第1段那次是两次独立安排。',
                                                 text='英语：' + self.QUOTE + '，与周三复述第1段那次是两次独立安排。'))

    def test_the_other_word_order_in_the_items_own_sentence_reads_the_same(self):
        wednesday = self.wednesday()
        self.assert_apart(wednesday, self.friday(self.QUOTE + '，周三的复述与本次是两个独立安排。',
                                                 text=self.QUOTE + '，周三的复述与本次是两个独立安排。'))

    def test_a_relation_day_no_original_or_listed_item_grounds_is_still_read(self):
        self.wednesday()
        # No listed item is dated Thursday and the original relates Wednesday: the model's own day stays this summary's.
        item = self.friday(self.QUOTE + '，与周四的复述属于两个独立安排。', text=self.SAME)
        self.assertNotEqual((item['state'], item['due']), ('accepted', FRI))

    def test_a_listed_day_grounds_only_where_the_items_own_original_words_say_separate(self):
        cited = lambda text: [dict(ref='message:x:1', text=text, time=DAY + 'T20:00:00+08:00')]
        listed = [dict(due=WED, title='英语：周三英语课复述《风筝》第1段', goal='周三英语课复述《风筝》第1段。')]
        goal = self.QUOTE + '，与周三的复述属于两个独立安排。'
        self.assertEqual(agent._school_listed_apart(self.QUOTE, cited(self.LESSON), goal, listed, []), {WED})
        self.assertEqual(agent._school_listed_apart(self.QUOTE, cited(self.QUOTE + '，请带课本。'), goal, listed, []), set())
        # A sibling's separateness in the same message is not this item's (另外安排… starts its own range).
        self.assertEqual(agent._school_listed_apart(self.QUOTE, cited(self.QUOTE + '。另外安排周六复述第5段，单独安排。'), goal, listed, []), set())
        self.assertEqual(agent._school_goal_dates(goal, cited(self.QUOTE + '，请带课本。'), frozenset()), set(), 'ungrounded: still read')

    def test_this_items_own_two_day_split_is_no_relation(self):
        for clause in ('周三和周五分别完成《风筝》第4段', '周三和周五两次分开完成复述', '和同学独立完成复述', '周三预习，周五上课'):
            self.assertIsNone(agent._SCHOOL_APART.search(clause), clause)
        for clause in ('与周三的复述属于两个独立安排', '和周三复述第1段的安排分开', '周三的复述与本次是两个独立安排',
                       '和周四朗读第2段那场分别登记', '与周四朗读第2段那场是两项独立活动', '跟周三那次不是同一次'):
            self.assertIsNotNone(agent._SCHOOL_APART.search(clause), clause)
        cited = [dict(ref='message:x:1', text='周三预习《风筝》第4段生词，周五第二节英语课复述第4段。', time=DAY + 'T20:00:00+08:00')]
        goal = '周三预习《风筝》第4段生词，周五第二节英语课复述第4段。'
        self.assertEqual(agent._school_goal_dates(goal, cited, frozenset({WED})), agent._school_goal_dates(goal, cited),
                         'a listed day never changes a summary that relates nothing')

    def rain_pending(self):
        r1 = 'message:%s:801' % EN
        self.batch(EN, [msg('801', '周三英语课做《雨后》听读展示，明晚补具体段落。', '17:00')], lambda targets, pending: [
            proposal(r1, '周三英语课做《雨后》听读展示，明晚补具体段落', '英语：周三英语课做《雨后》听读展示',
                     '周三英语课做《雨后》听读展示，具体段落明晚补充。', state='review')])
        first, = self.items_for(r1)
        self.assertEqual((first['state'], first['due']), ('pending', ''), 'the scalar day is unknown')
        return first

    def wrong_update(self, text, quote='周五英语课展示《雨后》第6段', due=FRI):
        ref = 'message:%s:802' % EN

        def replies(targets, pending):
            target = next(p['id'] for p in pending if '展示' in p['title'])
            return [proposal(ref, quote, '英语：' + quote, quote, change='update', target=target, due=due)]
        self.batch(EN, [msg('802', text, '20:00')], replies)
        item, = self.items_for(ref)
        return item

    def assert_own_card(self, item):
        self.assertNotIn('school_pending_of', item['plan'], 'the separate occurrence is no notice of the pending item')
        for view in self.views(FRI):
            self.assertEqual([r['when'] for r in self.cards(view, '第6段')], ['today'], 'the Friday occurrence keeps its own dated card')

    def test_c_the_originals_own_separateness_refuses_the_link_its_summary_omits(self):
        self.rain_pending()
        self.assert_own_card(self.wrong_update('周五英语课展示《雨后》第6段，这是独立的一次展示，单独安排。'))

    def test_c_a_following_sentence_referring_back_is_the_same_occurrences_words(self):
        self.rain_pending()
        self.assert_own_card(self.wrong_update('周五英语课展示《雨后》第6段。这是另一场展示。'))

    def test_c_separateness_heading_the_items_own_clause_refuses_the_link(self):
        self.rain_pending()
        self.assert_own_card(self.wrong_update('这次单独安排一场展示：周五英语课展示《雨后》第6段。'))

    def test_c_an_unlocated_quote_proves_no_scope_where_the_original_says_separate(self):
        self.rain_pending()
        item = self.wrong_update('周五英语课展示《雨后》第6段，这是独立的一次展示。', quote='周五展示《雨后》第6段')
        self.assertNotIn('school_pending_of', item['plan'], 'no located own words: the link is unproven')
        # The unlocated quote grounds no day of its own either (the existing date guard): it stays its own visible card.
        for view in self.views(FRI):
            self.assertEqual(len(self.cards(view, '第6段')), 1, 'the Friday occurrence is its own card, not hidden in the pending one')

    def test_c_a_siblings_separateness_leaves_the_correction_joined(self):
        first = self.rain_pending()
        ref = 'message:%s:803' % EN
        text = '周三英语课《雨后》听读展示的段落定为第2段。另外安排周五英语课展示《雨后》第6段，单独安排。'

        def replies(targets, pending):
            target = next(p['id'] for p in pending if '展示' in p['title'])
            return [proposal(ref, '周三英语课《雨后》听读展示的段落定为第2段', '英语：周三英语课《雨后》听读展示第2段',
                             '周三英语课《雨后》听读展示第2段。', state='review', change='update', target=target, due=WED),
                    proposal(ref, '另外安排周五英语课展示《雨后》第6段', '英语：周五英语课展示《雨后》第6段', '周五英语课展示《雨后》第6段。', due=FRI)]
        self.batch(EN, [msg('803', text, '20:10')], replies)
        items = {i['title']: i for i in self.items_for(ref)}
        correction = next(i for t, i in items.items() if '第2段' in t)
        other = next(i for t, i in items.items() if '第6段' in t)
        self.assertEqual(correction['plan'].get('school_pending_of', {}).get('item_id'), first['id'], 'the correction joins the pending card')
        self.assertNotIn('school_pending_of', other['plan'])
        self.assertEqual(other['due'], FRI)

    def test_c_a_sibling_opening_with_its_own_day_leaves_the_correction_joined(self):
        # Root run4 range-control: the next independent action opens with 这周五 and ends 单独安排. That separateness is
        # the sibling's own; the correction still joins the pending card and the Friday occurrence stays its own card.
        first = self.rain_pending()
        ref = 'message:%s:804' % EN
        text = '周三英语课《雨后》听读展示的段落定为第2段。这周五另外安排英语课《雨后》展示第6段，单独安排。'

        def replies(targets, pending):
            target = next(p['id'] for p in pending if '展示' in p['title'])
            return [proposal(ref, '周三英语课《雨后》听读展示的段落定为第2段', '英语：周三英语课《雨后》听读展示第2段',
                             '周三英语课《雨后》听读展示第2段。', state='review', change='update', target=target, due=WED),
                    proposal(ref, '这周五另外安排英语课《雨后》展示第6段', '英语：周五英语课《雨后》展示第6段',
                             '这周五另外安排英语课《雨后》展示第6段，单独安排。', due=FRI)]
        self.batch(EN, [msg('804', text, '20:00')], replies)
        items = {i['title']: i for i in self.items_for(ref)}
        correction = next(i for t, i in items.items() if '第2段' in t)
        other = next(i for t, i in items.items() if '第6段' in t)
        self.assertEqual(correction['plan'].get('school_pending_of', {}).get('item_id'), first['id'], 'the correction joins the pending card')
        self.assertNotIn('school_pending_of', other['plan'], 'the sibling Friday occurrence is its own item')
        for day in (DAY, WED, FRI):
            for view in self.views(day):
                rows = self.cards(view, '雨后')
                self.assertFalse([r for r in rows if '第2段' in r['title']], 'the correction is no card of its own')
                for row in rows:
                    if '第6段' in row['title']: continue
                    notices = (row.get('version') or {}).get('notices') or []
                    self.assertEqual(len([n for n in notices if '第2段' in n['title'] and '第6段' not in n['title']]), 1,
                                     'the pending card holds the correction as its notice')
                    self.assertEqual({p.get('ref') for p in row.get('publications') or []} >= {'message:%s:801' % EN, ref}, True,
                                     'the pending card keeps both publications')

    def test_c_own_range_ends_where_a_following_clause_states_its_own_work(self):
        def own(text, quote):
            return agent._school_own_range(quote, [dict(ref='message:x:1', text=text, time=DAY + 'T20:00:00+08:00')])
        correction = '周三英语课《雨后》听读展示的段落定为第2段'
        for sibling in ('这周五另外安排英语课《雨后》展示第6段，单独安排', '这次另外安排展示第6段，单独安排',
                        '本周五另外安排一次听写，单独登记', '这周五另外安排英语课《雨后》展示第2段，单独安排'):
            self.assertEqual(own(correction + '。' + sibling + '。', correction), correction, sibling)
        # Clauses only referring back keep this reply's separateness, as before (the negative controls stay).
        friday = '周五英语课展示《雨后》第6段'
        for back in ('这是独立的一次展示，单独安排', '这是另一场展示', '这周五的展示单独安排', '和周三第2段那场分别登记',
                     '这次展示第6段单独安排'):
            self.assertIn(back, own(friday + '，' + back + '。', friday), back)
        self.assertIn('这周五单独安排', own('展示《雨后》第6段，这周五单独安排。', '展示《雨后》第6段'),
                      'a day after a clause stating none may still be its own day')

    def test_c_a_true_range_supplement_still_joins_the_pending_card(self):
        first = self.rain_pending()
        item = self.wrong_update('周三英语课《雨后》听读展示的段落定为第2段。', quote='周三英语课《雨后》听读展示的段落定为第2段', due=WED)
        self.assertEqual(item['plan'].get('school_pending_of', {}).get('item_id'), first['id'])

    def test_c_a_range_supplement_stating_no_day_still_joins_the_pending_card(self):
        first = self.rain_pending()
        item = self.wrong_update('《雨后》听读展示的段落定为第2段。', quote='《雨后》听读展示的段落定为第2段', due='')
        self.assertEqual(item['plan'].get('school_pending_of', {}).get('item_id'), first['id'])

    def test_c_an_unknown_pending_day_is_no_wildcard_for_another_day(self):
        self.rain_pending()
        # No separateness is stated at all: the pending item's own Wednesday still binds, so Friday is another occurrence.
        self.assert_own_card(self.wrong_update('周五英语课展示《雨后》第6段。'))

    def test_c_a_stated_move_of_an_unknown_scalar_day_still_joins(self):
        first = self.rain_pending()
        item = self.wrong_update('《雨后》听读展示改到周五英语课，展示第6段。', quote='《雨后》听读展示改到周五英语课，展示第6段')
        self.assertEqual(item['plan'].get('school_pending_of', {}).get('item_id'), first['id'])


class SchoolChangeWholeTests(ScopeSaveTests):
    """B: the ordinary school_change write (POST /api/agent/action dispatches apply_school_change) keeps what the read keeps."""

    def science(self, notice, quote, goal, clock='20:30', title=''):
        sci = dict(sender='虚构乙科学老师', sender_id='fic-sci2-teacher')
        r1, r2 = 'message:%s:601' % SCI, 'message:%s:602' % SCI
        self.batch(SCI, [msg('601', '今晚用温度计测3次水温，把结果记在科学练习册第12页。', '17:00', **sci)], lambda targets, pending: [
            proposal(r1, '今晚用温度计测3次水温，把结果记在科学练习册第12页', '科学：测3次水温并记录', '今晚用温度计测3次水温，把结果记在科学练习册第12页。',
                     due=DAY, subject='科学')])
        first, = self.items_for(r1)
        if first['state'] == 'pending':  # the parent's ordinary accept of the clear original
            self.store.act(dict(id=first['id'], action='accept')); first, = self.items_for(r1)
        self.assertEqual(first['state'], 'accepted')
        self.batch(SCI, [msg('602', notice, clock, **sci)], lambda targets, pending: [
            proposal(r2, quote, title or '科学：' + quote, goal, state='review', change='update', target=first['task_id'], subject='科学')])
        item, = self.items_for(r2)
        self.assertEqual(item['state'], 'pending')
        return first['task_id'], item

    def request(self, item, task_id, body):
        """The form's own payload (app.js schoolChangeForm): the candidate's title and summary unless the parent edits them."""
        with self.app.connect() as c:
            task = next(t for t in self.app.tasks(c) if t['id'] == task_id)
            update = c.execute('SELECT updated FROM task_updates WHERE id=?', (task_id,)).fetchone()
            row = c.execute('SELECT updated FROM agent_items WHERE id=?', (item['id'],)).fetchone()
        brief = item['plan']['school_task']
        return dict(action='school_change', id=item['id'], target_id=task_id, change='update', title=brief['title'], body=body, due='',
                    expected_updated=row['updated'], target_version=task['focus']['version'], target_updated=update['updated'] if update else '')

    def saved(self, item_id, task_id):
        with self.app.connect() as c:
            row = c.execute('SELECT state,updated,plan FROM agent_items WHERE id=?', (item_id,)).fetchone()
            return dict(state=row['state'], updated=row['updated'], receipt='school_change_receipt' in json.loads(row['plan']),
                        action=self.task(task_id)['action'], version=self.task(task_id)['focus']['version'])

    def test_candidate_dropping_the_count_is_refused_unwritten_and_whole_words_then_save(self):
        task_id, item = self.science('更正：水温结果改记在记录单上，不用记在练习册。', '水温结果改记在记录单上，不用记在练习册',
                                     '用温度计测水温，结果记在记录单上，不用记在练习册。')
        view = self.app.day_view('child-1', DAY)
        row, = [r for g in view['groups'] for r in g['items'] if r.get('task_id') == task_id]
        self.assertEqual(row['version']['state'], 'review')
        self.assertTrue(any('缺少原要求中未改的部分' in why for why in row['version']['reasons']), row['version'])
        before = self.saved(item['id'], task_id)
        default = self.request(item, task_id, item['plan']['school_task']['goal'])
        with self.assertRaises(agent.AgentError) as refused:
            agent.apply_school_change(self.app, self.store, default)
        self.assertEqual((refused.exception.status, refused.exception.code), (409, 'school_change_incomplete'))
        self.assertIn('3次', str(refused.exception))
        self.assertEqual(self.saved(item['id'], task_id), before, 'nothing written: the requirement and the notice stay')
        self.assertIn('3次', self.task(task_id)['action'])
        # The parent writes the whole requirement: the same notice is confirmed, saved as written and kept after reopening.
        whole = '今晚用温度计测3次水温，把结果记在记录单上，不用记在练习册。'
        result = agent.apply_school_change(self.app, self.store, self.request(item, task_id, whole))
        self.assertEqual((result['state'], result['task_id']), ('accepted', task_id))
        reopened = family_review.load_app(self.root, self.data)
        with reopened.connect() as c:
            self.assertEqual(next(t for t in reopened.tasks(c) if t['id'] == task_id)['action'], whole)

    def test_candidate_with_only_a_stated_count_change_saves_the_whole_requirement(self):
        task_id, item = self.science('更正：水温改测2次。', '水温改测2次', '用温度计测2次水温。', title='科学：测2次水温并记录')
        view = self.app.day_view('child-1', DAY)
        row, = [r for g in view['groups'] for r in g['items'] if r.get('task_id') == task_id]
        shown = '\n'.join(row['version'].get('lines') or [])
        result = agent.apply_school_change(self.app, self.store, self.request(item, task_id, item['plan']['school_task']['goal']))
        self.assertEqual(result['state'], 'accepted')
        action = self.task(task_id)['action']
        for unit in ('温度计', '2次', '科学练习册第12页'):
            self.assertIn(unit, action)
        self.assertNotIn('3次', action)
        if row['version']['state'] == 'latest':
            self.assertEqual(action, shown, 'the write saves the very whole requirement the day projection showed')

    def test_a_restated_count_does_not_let_the_candidate_drop_that_clauses_method(self):
        # The notice restates the count and moves the record; the candidate drops the thermometer method of the restated clause.
        task_id, item = self.science('更正：水温改测2次，结果改记在记录单上。', '水温改测2次，结果改记在记录单上', '测2次水温，结果记在记录单上。')
        with self.assertRaises(agent.AgentError) as refused:
            agent.apply_school_change(self.app, self.store, self.request(item, task_id, item['plan']['school_task']['goal']))
        self.assertIn('温度计', str(refused.exception))
        self.assertIn('温度计', self.task(task_id)['action'])

    def test_parent_edited_words_are_the_familys_own(self):
        task_id, item = self.science('更正：水温结果改记在记录单上，不用记在练习册。', '水温结果改记在记录单上，不用记在练习册',
                                     '用温度计测水温，结果记在记录单上，不用记在练习册。')
        edited = '用温度计测水温，结果记在记录单上。'
        agent.apply_school_change(self.app, self.store, self.request(item, task_id, edited))
        self.assertEqual(self.task(task_id)['action'], edited)

if __name__ == '__main__':
    unittest.main()


MON = '2026-11-23'


class CorrectionUnitTests(ScopeSaveTests):
    """D: a same-publisher correction changes only its stated unit (Root run4). A count correction restating the original's
    own 今晚 (filed by the summary as a due day) is no move and keeps every date role; a stated move of the item's day keeps
    every unchanged unit (一个) whether or not the summary repeats it. Replies replay the shapes of the none and low returns,
    shifted onto this file's frozen Tuesday; no product model is called."""
    EN_T = dict(sender='虚构甲英语老师', sender_id='fic-en-teacher')
    SCI_T = dict(sender='虚构甲科学老师', sender_id='fic-sci-teacher')

    def originals(self):
        r_en, r_sci = 'message:%s:103' % EN, 'message:%s:105' % EN
        self.batch(EN, [msg('103', '英语：今晚听音频跟读Unit 9第1到6个单词，每词三遍。只做口头跟读，不用抄写；周五课堂听写，范围由老师明天再说。', '16:20', **self.EN_T),
                        msg('105', '科学：周四实验课带空的透明塑料瓶一个，今晚不用填写实验记录表。', '16:30', **self.SCI_T)],
                   lambda targets, pending: [
            proposal(r_en, '今晚听音频跟读Unit 9第1到6个单词，每词三遍', '英语：跟读Unit 9第1—6个单词',
                     '今晚听音频跟读Unit 9第1到6个单词，每词三遍。\n只做口头跟读，不用抄写。\n周五课堂听写，范围由老师明天再说。'),
            proposal(r_en, '周五课堂听写，范围由老师明天再说', '英语：周五课堂听写', '周五课堂进行英语听写。\n听写范围由老师明天再说，目前未公布。',
                     state='review', due=FRI),
            proposal(r_sci, '周四实验课带空的透明塑料瓶一个，今晚不用填写实验记录表', '科学：周四实验课带空透明塑料瓶',
                     '周四实验课带空的透明塑料瓶一个。\n今晚不用填写实验记录表。', due=THU, purpose='admin', subject='')])
        found = {}
        for ref, word in ((r_en, '跟读'), (r_sci, '塑料瓶')):
            item = next(i for i in self.items_for(ref) if word in i['title'])
            if item['state'] == 'pending':
                self.store.act(dict(id=item['id'], action='accept')); item = next(i for i in self.items_for(ref) if word in i['title'])
            self.assertEqual(item['state'], 'accepted')
            found[word] = item['task_id']
        return found['跟读'], found['塑料瓶']

    def corrections(self, english, science, english_due):
        en_task, sci_task = self.originals()
        r7, r8 = 'message:%s:107' % EN, 'message:%s:108' % EN

        def replies(targets, pending):
            dictation = next(p['id'] for p in pending if '听写' in p['title'])
            return [proposal(r7, 'Unit 9第1到6个单词今晚只需跟读两遍，仍然不用抄写', english[0], english[1], state='review', change='update',
                             target=en_task, due=english_due),
                    proposal(r7, '周五课堂听写的范围还没定，等明天另行通知', '英语：周五课堂听写', '周五课堂进行英语听写。\n听写范围尚未确定，等老师明天另行通知。',
                             state='review', change='same', target=dictation, due=FRI),
                    proposal(r8, '周四科学课改到下周一，前面通知带的透明塑料瓶也下周一再带', '科学：下周一实验课带空透明塑料瓶', science,
                             state='review', change='update', target=sci_task, due=MON, purpose='admin', subject='')]
        self.batch(EN, [msg('107', '更正刚才的英语跟读：Unit 9第1到6个单词今晚只需跟读两遍，仍然不用抄写；周五课堂听写的范围还没定，等明天另行通知。', '17:10', **self.EN_T),
                        msg('108', '周四科学课改到下周一，前面通知带的透明塑料瓶也下周一再带，今晚仍不用填写记录表。', '17:12', **self.SCI_T)], replies)
        return en_task, sci_task

    def row(self, view, task_id):
        rows = [r for g in view['groups'] for r in g['items'] if r.get('task_id') == task_id] + \
               [u for u in view['upcoming'] if u.get('task_id') == task_id]
        return rows

    def assert_whole(self, en_task, sci_task):
        for view in self.views(DAY):
            en, = self.row(view, en_task)
            version = en.get('version') or {}
            self.assertEqual(version.get('state'), 'latest', version)
            words = '\n'.join(version['lines'])
            for unit in ('听音频', '两遍', '只做口头跟读', '不用抄写'):
                self.assertIn(unit, words)
            self.assertNotIn('三遍', words, 'the stated count replaces the old one; the old number is no current requirement')
            self.assertEqual(en['when'], 'today', 'the original completion day stays')
        for view in self.views(MON):
            sci, = self.row(view, sci_task)
            version = sci.get('version') or {}
            self.assertEqual(version.get('state'), 'latest', version)
            words = '\n'.join(version['lines'])
            for unit in ('空的透明塑料瓶一个', '下周一', '不用填写实验记录表'):
                self.assertIn(unit, words)
            self.assertNotIn('周四', words, 'the moved day word is no current requirement')
        for view in self.views(THU):
            self.assertEqual(self.row(view, sci_task), [], 'the moved item no longer lists on its old day')

    def test_none_shape_summary_dropping_one_unchanged_quantity_composes_the_whole_original(self):
        en_task, sci_task = self.corrections(
            ('英语：跟读Unit 9第1—6个单词两遍', '今晚听音频跟读Unit 9第1到6个单词，每个单词跟读两遍。\n只做口头跟读，不用抄写。'),
            '科学实验课由周四改到下周一。\n前面通知要带的空透明塑料瓶改为下周一再带。\n今晚仍不用填写实验记录表。', '')
        self.assert_whole(en_task, sci_task)

    def test_low_shape_count_correction_restating_its_own_tonight_is_no_move(self):
        en_task, sci_task = self.corrections(
            ('英语：跟读Unit 9第1—6个单词', '今晚听音频跟读Unit 9第1到6个单词两遍。\n不用抄写。'),
            '科学课由周四改到下周一。\n前面通知带的空透明塑料瓶一个也下周一再带。\n今晚仍不用填写实验记录表。', DAY)
        self.assert_whole(en_task, sci_task)

    def test_a_move_notice_adding_its_own_requirement_stays_under_review(self):
        en_task, sci_task = self.originals()
        r8 = 'message:%s:108' % EN
        self.batch(EN, [msg('108', '周四科学课改到下周一，透明塑料瓶也下周一再带，另外每人带一把剪刀。', '17:12', **self.SCI_T)], lambda targets, pending: [
            proposal(r8, '周四科学课改到下周一，透明塑料瓶也下周一再带，另外每人带一把剪刀', '科学：下周一实验课带空透明塑料瓶',
                     '科学实验课改到下周一。\n透明塑料瓶下周一再带。', state='review', change='update', target=sci_task, due=MON,
                     purpose='admin', subject='')])
        for view in self.views(THU):
            sci, = self.row(view, sci_task)
            self.assertEqual(sci['version']['state'], 'review', 'an added requirement is no proven move-only change')

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

    def test_parent_edited_words_are_the_familys_own(self):
        task_id, item = self.science('更正：水温结果改记在记录单上，不用记在练习册。', '水温结果改记在记录单上，不用记在练习册',
                                     '用温度计测水温，结果记在记录单上，不用记在练习册。')
        edited = '用温度计测水温，结果记在记录单上。'
        agent.apply_school_change(self.app, self.store, self.request(item, task_id, edited))
        self.assertEqual(self.task(task_id)['action'], edited)

if __name__ == '__main__':
    unittest.main()

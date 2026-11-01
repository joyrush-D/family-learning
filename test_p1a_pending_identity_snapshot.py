"""P1a A/B: a later notice about a still-pending school item keeps that item's identity (one card, every original), and a
partial correction's latest requirement is the whole original with only the stated change (PRD 3.2, AC01-03/11).

Newly made, wholly fictional development cases (not Root's blind samples): fictional teachers, groups and message ids, a
frozen Tuesday 2026-11-10. The model replies are handcrafted stand-ins, including the omission Root observed (an update
that drops the original method and range); no product model is called. Every case goes through the ordinary selection
(_select), Store save, refresh and the shared day projection, and is read again from a freshly loaded app.
"""
import datetime as dt
import json
import unittest
from unittest.mock import patch

import family_agent as agent
import family_review
import test_agent

SOURCES = [dict(id='fic-en-qq', platform='qq', child_id='child-1', name='虚构甲英语群', cursor='10', enabled=True),
           dict(id='fic-sci-wx', platform='wechat', child_id='child-1', name='虚构甲科学群', cursor='10', enabled=True)]
EN, SCI = 'fic-en-qq', 'fic-sci-wx'
DAY, THU, FRI, MON = '2026-11-10', '2026-11-12', '2026-11-13', '2026-11-16'
READING = '今晚听录音跟读Lesson8第2–7词，每词四遍，不用抄写；本周五课堂听写，范围另通知。'
CORRECTION = '跟读改每词三遍，不用抄写；周五课堂听写仍在课内，范围还没定。'


def msg(ident, text, clock, sender='虚构英语老师', sender_id='fic-en-teacher'):
    return dict(id=ident, sender_id=sender_id, sender=sender, text=text, time=DAY + 'T' + clock + ':00+08:00', kind='text',
                unread=False, message_order=ident)


def proposal(ref, quote, title, goal, *, state='ready', change='new', target='', due='', purpose='learning', subject='英语'):
    p = dict(title_quote=quote, focus='school', due=due, evidence=[{'ref': ref}], task_title=title, task_goal=goal, task_advice='',
             learning_subject=subject if purpose == 'learning' else '', learning_goal_id='', task_change=change, task_target_id=target,
             task_state=state, task_reason='虚构开发例的待核原因' if state == 'review' else '', task_purpose=purpose, task_submission='')
    assert set(p) == set(agent._school_fields['required'])
    return p


class PendingIdentitySnapshotTests(unittest.TestCase):
    config = test_agent.AgentTests.config

    def setUp(self):
        test_agent.AgentTests.setUp(self)
        (self.data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': SOURCES}))
        self.requests = []

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
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': replies(targets, pending)}) as model:
            items = agent._select('school', evidence, school_goals=goals, school_tasks=targets, school_pending=pending, as_of=now.date().isoformat())
        self.requests.append(model.call_args)
        for item in items:
            item.update(child_id=child, kind='school')
            if item['plan'].get('school_learning'):
                item['plan']['school_messages'] = [dict(zip(('source_id', 'message_id'), e['ref'][8:].rsplit(':', 1))) for e in item.get('evidence', [])]
        self.store._save('p1a-pending:%s:%s' % (source, messages[-1]['id']), 'fictional', items, now)
        with patch.object(agent.family_llm, '_chat_json') as model, patch.object(agent, '_now', return_value=now):
            agent._refresh_school(self.app, self.store, now, 0); model.assert_not_called()
        return items

    def task_for(self, ref):
        with self.app.connect() as c:
            for r in c.execute("SELECT task_id,evidence FROM agent_items WHERE kind='school' AND state='accepted' AND task_id!='' ORDER BY rowid"):
                if ref in [e['ref'] for e in json.loads(r['evidence'])]: return r['task_id']
        return ''

    def items_for(self, ref):
        with self.app.connect() as c:
            return [dict(r, plan=json.loads(r['plan'])) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")
                    if ref in [e['ref'] for e in json.loads(r['evidence'])]]

    def views(self, day):
        """The same day read by the running app and by a freshly loaded one (保存后重开)."""
        return [self.app.day_view('child-1', day), family_review.load_app(self.root, self.data).day_view('child-1', day)]

    def rows(self, view):
        return [r for g in view['groups'] for r in g['items']]

    def cards(self, view, word):
        return [r for r in self.rows(view) if word in r['title']] + [u for u in view['upcoming'] if word in u['title']]

    def english_day(self, touched=False):
        r201, r202 = 'message:%s:201' % EN, 'message:%s:202' % EN
        self.batch(EN, [msg('201', READING, '17:00')], lambda targets, pending: [
            proposal(r201, '今晚听录音跟读Lesson8第2–7词，每词四遍，不用抄写', '英语：听录音跟读Lesson8第2–7词',
                     '今晚听录音跟读Lesson8第2–7词，每词四遍。\n不用抄写。', due=DAY),
            proposal(r201, '本周五课堂听写，范围另通知', '英语：周五课堂听写', '本周五课堂听写，听写范围另行通知。', state='review', due=FRI)])
        reading = self.task_for(r201)
        self.assertTrue(reading, 'the clear home reading is collected as a task')
        first = [i for i in self.items_for(r201) if i['state'] == 'pending']
        self.assertEqual([i['title'] for i in first], ['英语：周五课堂听写'], 'the range-pending classroom item stays pending')
        if touched:
            with self.app.connect() as c:
                c.execute('INSERT INTO task_updates(id,status,updated) VALUES(?,?,?)', (reading, '进行中', DAY + 'T19:00:00+08:00'))

        def replies(targets, pending):
            # Root's observed omission: the update states only the new count; the reminder is bound to the pending item.
            task = next(t['id'] for t in targets if '跟读' in t['title'])
            dictation = next(p['id'] for p in pending if '听写' in p['title'])
            return [proposal(r202, '跟读改每词三遍，不用抄写', '英语：跟读每词三遍', '跟读每词三遍。\n不用抄写。', state='review',
                             change='update', target=task),
                    proposal(r202, '周五课堂听写仍在课内，范围还没定', '英语：周五课堂听写', '周五课堂听写仍在课内，听写范围还没定。',
                             state='review', change='same', target=dictation, due=FRI)]
        self.batch(EN, [msg('202', CORRECTION, '20:30')], replies)
        return reading, first[0]['id']

    def test_request_lists_pending_items_apart_from_saved_tasks(self):
        self.english_day()
        messages, schema = self.requests[-1].args[:2]
        system, content = messages[0]['content'], json.loads(messages[1]['content'])
        pending = content['school_pending_items']
        self.assertEqual([p['title'] for p in pending], ['英语：周五课堂听写'])
        self.assertTrue(all(p['id'].startswith('pending:') and p['state'] == 'pending' and not ({'refs', 'latest'} & set(p)) for p in pending))
        self.assertFalse([t for t in content['school_tasks'] if t['id'].startswith('pending:')], 'no pending id poses as a saved task')
        enum = schema['properties']['proposals']['items']['properties']['task_target_id']['enum']
        self.assertEqual(enum, [''] + [t['id'] for t in content['school_tasks']] + [p['id'] for p in pending])
        self.assertEqual((system.count(agent.SCHOOL_PENDING_PROMPT), system.count(agent.SCHOOL_UPDATE_SNAPSHOT)), (1, 1))
        # The first request listed no original: it keeps its exact prompt (no snapshot or pending sentence), no pending key.
        first_system, first_content = self.requests[0].args[0][0]['content'], json.loads(self.requests[0].args[0][1]['content'])
        self.assertNotIn(agent.SCHOOL_UPDATE_SNAPSHOT, first_system); self.assertNotIn(agent.SCHOOL_PENDING_PROMPT, first_system)
        self.assertNotIn('school_pending_items', first_content)

    def test_partial_correction_latest_keeps_method_range_and_takes_new_count(self):
        reading, _ = self.english_day()
        for view in self.views(DAY):
            row, = [r for r in self.rows(view) if '跟读' in r['title']]
            self.assertEqual(row['version']['state'], 'latest', row['version'])
            text = '\n'.join(row['lines'])
            for unit in ('听录音', 'Lesson8', '第2–7词', '三遍', '不用抄写'):
                self.assertIn(unit, text)
            self.assertNotIn('四遍', text, 'the old count is history only')
            self.assertIn('四遍', '\n'.join(row['version']['previous']['lines']))
            self.assertEqual(row['version'].get('composed'), 'original_with_stated_change')
            self.assertIn('原四遍→三遍', row['version']['change'])
            self.assertTrue(row['today'], 'a notice stating no day keeps the original tonight')
            self.assertEqual({p['ref'] for p in row['publications']}, {'message:%s:201' % EN, 'message:%s:202' % EN})
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT action FROM manual_tasks WHERE id=?', (reading,)).fetchone()['action'],
                             '今晚听录音跟读Lesson8第2–7词，每词四遍。\n不用抄写。', 'reading writes nothing: the saved task stays as it was')

    def test_pending_classroom_item_reminder_is_one_card_with_both_originals_and_scope_unknown(self):
        _, earlier = self.english_day()
        for view in self.views(DAY) + self.views('2026-11-11'):
            self.assertEqual(len(self.cards(view, '听写')), 1, [r['title'] for r in self.rows(view)] + [u['title'] for u in view['upcoming']])
        for view in self.views(FRI):
            row, = [r for r in self.rows(view) if '听写' in r['title']]
            self.assertTrue(row['pending_review']); self.assertEqual(row['version']['state'], 'review')
            self.assertIn('同一待核事项有后续通知', row['version']['reasons'])
            self.assertEqual({p['ref'] for p in row['publications']}, {'message:%s:201' % EN, 'message:%s:202' % EN})
            self.assertNotIn('2–7', '\n'.join(row['lines']), 'the dictation range is never guessed from the reading')
            self.assertEqual(row['version']['previous']['due_on'], FRI)
        later = [i for i in self.items_for('message:%s:202' % EN) if '听写' in i['title']]
        self.assertEqual([(i['state'], i['plan']['school_pending_of']['item_id']) for i in later], [('pending', earlier)])
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?', (earlier,)).fetchone()['state'], 'pending',
                             'binding never accepts the range-unknown item')

    def test_family_touched_task_keeps_its_requirement_under_the_correction(self):
        self.english_day(touched=True)
        for view in self.views(DAY):
            row, = [r for r in self.rows(view) if '跟读' in r['title']]
            self.assertEqual(row['version']['state'], 'review'); self.assertIn('家庭已有完成、状态或修改', row['version']['reasons'])
            self.assertIn('四遍', '\n'.join(row['lines'])); self.assertEqual(row['status'], '进行中')

    def test_unproven_pending_targets_stay_their_own_cards(self):
        r201 = 'message:%s:201' % EN
        self.batch(EN, [msg('201', READING, '17:00')], lambda targets, pending: [
            proposal(r201, '今晚听录音跟读Lesson8第2–7词，每词四遍，不用抄写', '英语：听录音跟读Lesson8第2–7词',
                     '今晚听录音跟读Lesson8第2–7词，每词四遍。\n不用抄写。', due=DAY),
            proposal(r201, '本周五课堂听写，范围另通知', '英语：周五课堂听写', '本周五课堂听写，听写范围另行通知。', state='review', due=FRI)])
        other = [msg('203', '下周三英语竞赛初赛，自愿报名。', '20:00'), msg('204', '周五另有一次单词课堂测验，范围Lesson7。', '20:05'),
                 msg('205', '周五课堂听写请提前复习。', '20:10', sender='虚构英语助教', sender_id='fic-en-assistant')]

        def replies(targets, pending):
            # A reply wrongly binding an independent contest, another quiz and another publisher's line to the pending item.
            d = next(p['id'] for p in pending if '听写' in p['title']); ref = lambda n: 'message:%s:%s' % (EN, n)
            return [proposal(ref('203'), '下周三英语竞赛初赛，自愿报名', '英语：竞赛初赛自愿报名', '下周三英语竞赛初赛，自愿报名。',
                             state='review', change='same', target=d, purpose='optional'),
                    proposal(ref('204'), '周五另有一次单词课堂测验，范围Lesson7', '英语：周五单词课堂测验', '周五另有一次单词课堂测验，范围Lesson7。',
                             state='review', change='update', target=d, due=FRI),
                    proposal(ref('205'), '周五课堂听写请提前复习', '英语：周五课堂听写复习', '周五课堂听写请提前复习。',
                             state='review', change='same', target=d, due=FRI)]
        items = self.batch(EN, other, replies)
        self.assertFalse([i for i in items if i['plan'].get('school_pending_of')], 'no unproven binding is kept')
        for view in self.views(FRI):
            original, = [r for r in self.rows(view) if r['title'] == '英语：周五课堂听写']
            self.assertNotIn('version', original)
            self.assertEqual(len([r for r in self.rows(view) if '测验' in r['title']]), 1)
            self.assertEqual(len([r for r in self.rows(view) if '复习' in r['title']]), 1, 'another publisher stays apart')

    def science(self, goal, title):
        r301, r302 = 'message:%s:301' % SCI, 'message:%s:302' % SCI
        teacher = dict(sender='虚构科学老师', sender_id='fic-sci-teacher')
        self.batch(SCI, [msg('301', '周四上课带两个干净的空纸盒，今晚不填写观察表。', '16:00', **teacher)], lambda targets, pending: [
            proposal(r301, '周四上课带两个干净的空纸盒', '科学：周四上课带两个干净的空纸盒', '周四上课带两个干净的空纸盒。\n今晚不填写观察表。',
                     due=THU, purpose='admin')])
        task = self.task_for(r301); self.assertTrue(task)
        self.batch(SCI, [msg('302', '原通知的纸盒改下周一带来。', '20:00', **teacher)], lambda targets, pending: [
            proposal(r302, '原通知的纸盒改下周一带来', title, goal, state='review', change='update', target=task, due=MON, purpose='admin')])
        return task

    def test_date_correction_whole_snapshot_is_latest_and_tonight_stays_no_todo(self):
        self.science('下周一上课带两个干净的空纸盒。\n今晚不填写观察表。', '科学：下周一上课带两个干净的空纸盒')
        for view in self.views(MON):
            row, = [r for r in self.rows(view) if '纸盒' in r['title']]
            self.assertEqual(row['version']['state'], 'latest', row['version'])
            shown = row['title'] + '\n' + '\n'.join(row['lines'])  # a line repeating the title is shown as the title
            self.assertIn('两个干净的空纸盒', shown); self.assertIn('下周一', shown); self.assertIn('今晚不填写观察表', shown)
            self.assertIn('周四', row['version']['previous']['title'] + '\n'.join(row['version']['previous']['lines']))
        for view in self.views(DAY):
            self.assertFalse([r for r in self.rows(view) if '观察表' in r['title']], '今晚不填 never becomes a todo')
            self.assertEqual(len(self.cards(view, '纸盒')), 1)

    def test_date_correction_dropping_the_standard_stays_for_review_with_the_original(self):
        self.science('下周一带纸盒。', '科学：下周一带纸盒')
        for view in self.views(THU):
            row, = [r for r in self.rows(view) if '纸盒' in r['title']]
            self.assertEqual(row['version']['state'], 'review', row['version'])
            self.assertTrue(any(r.startswith('新要求的归纳缺少原要求中未改的部分') for r in row['version']['reasons']), row['version']['reasons'])
            shown = row['title'] + '\n' + '\n'.join(row['lines'])
            self.assertIn('两个干净的空纸盒', shown); self.assertIn('周四', shown)


if __name__ == '__main__':
    unittest.main()

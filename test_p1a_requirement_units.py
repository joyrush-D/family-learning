"""P1a B1-B4: requirement units, action date roles and one affair's versions on one card (PRD 3.2, AC01-03/11).

Replays Root's frozen, wholly fictional P0 day (12 messages, two children, QQ/WeChat, reminders, corrections, oral report)
through the ordinary selection, save, refresh and shared day projection. The four product-model replies are byte-exact
(SHA-256 checked); only their opaque task_target_id values are translated, through the observed output's own message refs,
to the ids this isolated replay creates. No product model is called; nothing real is read.
"""
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import family_agent as agent
import test_agent

FROZEN = json.loads((Path(__file__).with_suffix('.json')).read_text(encoding='utf-8'))


def frozen(name):
    text = FROZEN['files'][name]
    assert hashlib.sha256(text.encode('utf-8')).hexdigest() == FROZEN['sha256'][name], name
    return json.loads(text)


class P1aRequirementUnitTests(unittest.TestCase):
    config = test_agent.AgentTests.config

    def setUp(self):
        test_agent.AgentTests.setUp(self)
        self.fixture = frozen('fixture.json')
        self.now = agent.dt.datetime.fromisoformat(self.fixture['as_of'])
        (self.data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': self.fixture['sources']}))
        self.phases = {p['name']: p for p in self.fixture['phases']}

    def ingest(self, phase):
        source = phase['source']
        with self.app.connect() as c: previous = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (source,)).fetchone()
        messages = [dict(m) for m in phase['messages']]
        self.store.ingest(dict(source_id=source, expected_cursor=previous['cursor'] if previous else '10', cursor=messages[-1]['id'],
                               checked_at=self.now.isoformat(), last_message_time=messages[-1]['time'], error='', messages=messages))

    def task_for(self, ref):
        with self.app.connect() as c:
            for r in c.execute("SELECT task_id,evidence FROM agent_items WHERE kind='school' AND state='accepted' AND task_id!='' ORDER BY rowid"):
                if ref in [e['ref'] for e in json.loads(r['evidence'])]: return r['task_id']
        return ''

    def translate(self):
        observed = frozen('observed-synthetic.json')
        return {t['id']: self.task_for(t['agenda']['publications'][0]['ref']) for t in observed['tasks']}

    def replay(self, name, receipt):
        phase = self.phases[name]; source = phase['source']
        child = next(s['child_id'] for s in self.fixture['sources'] if s['id'] == source)
        self.ingest(phase)
        evidence = [dict(m, ref='message:%s:%s' % (source, m['id']), publisher=agent._publisher(source, m), content_incomplete=False) for m in phase['messages']]
        targets = agent.school_targets(self.app, self.store, child, evidence=[m['text'] for m in phase['messages']])
        reply = frozen(receipt); ids = self.translate()
        from family_goals import Store as Goals
        goals = Goals(self.app, self.store).school_candidates(child)
        for p in reply['proposals']:
            if p['task_target_id']: p['task_target_id'] = ids[p['task_target_id']]
            # Root's run had its own opaque goal ids; the same subject's goal of this replay (or none) stands in for it.
            if p['learning_goal_id']: p['learning_goal_id'] = next((g['id'] for g in goals if g.get('subject') == p['learning_subject']), '')
        with patch.object(agent.family_llm, '_chat_json', return_value=reply):
            items = agent._select('school', evidence, school_goals=goals, school_tasks=targets, as_of=self.fixture['day'])
        for item in items:
            item.update(child_id=child, kind='school')
            if item['plan'].get('school_learning'):
                item['plan']['school_messages'] = [dict(zip(('source_id', 'message_id'), e['ref'][8:].rsplit(':', 1))) for e in item.get('evidence', [])]
        self.store._save('p1a-replay:' + name, 'p1a-fixed', items, self.now)
        with patch.object(agent.family_llm, '_chat_json') as model, patch.object(agent, '_now', return_value=self.now):
            agent._refresh_school(self.app, self.store, self.now, 0); model.assert_not_called()
        return {e['ref']: i['plan']['school_task'] for i in items for e in i.get('evidence', [])[:1]}

    def whole_day(self, through='other_child_same_title'):
        briefs = {}
        for name, receipt in (('original_day', 'receipt-01.json'), ('cross_channel_reminders', 'receipt-02.json'),
                              ('same_publisher_corrections', 'receipt-03.json'), ('other_child_same_title', 'receipt-04.json')):
            briefs.update(self.replay(name, receipt))
            if name == through: break
        return briefs

    def view(self, day='2026-11-03', child='child-1'):
        return self.app.day_view(child, day)

    def rows(self, view):
        return [r for g in view['groups'] for r in g['items']]

    def by_title(self, view, word):
        found = [r for r in self.rows(view) if word in r['title']]
        self.assertEqual(len(found), 1, [r['title'] for r in self.rows(view)])
        return found[0]

    def fact(self, row, role):
        return next((f for f in row['facts'] if f['role'] == role), None)

    def test_b1_relation_clauses_link_reminders_as_one_affair_with_both_originals(self):
        briefs = self.whole_day('cross_channel_reminders')
        for ref in ('message:fictional-wechat-a:202', 'message:fictional-wechat-a:203'):
            self.assertEqual((briefs[ref]['state'], briefs[ref]['change']), ('ready', 'same'), briefs[ref].get('reason'))
            self.assertTrue(briefs[ref]['relation_quotes'])
        self.assertIn('和QQ群语文老师那条是同一件事', briefs['message:fictional-wechat-a:202']['relation_quotes'])
        self.assertIn('提醒一次', briefs['message:fictional-wechat-a:203']['relation_quotes'])
        view = self.view(); titles = [r['title'] for r in self.rows(view)]
        for word in ('山间小路', '青石练习册', '秋游回执'):
            row = self.by_title(view, word)
            self.assertEqual(len(row['publications']), 2, row['publications'])
            self.assertEqual({p['source_name'] for p in row['publications']}, {'虚构甲QQ群', '虚构甲微信群'})
        self.assertFalse([r for r in self.rows(view) if r['pending_review']], titles)

    def test_b1_guard_controls_keep_real_changes_and_link_pure_relation(self):
        self.whole_day('original_day')
        ids = self.translate()
        targets = agent.school_targets(self.app, self.store, 'child-1')
        expected = {'recorded_reminder': 'ready', 'same_obligation_without_discourse': 'ready', 'different_requirement_must_stay_separate': 'review'}
        target_of = {'语文：朗读《山间小路》两遍并签字': ids['AGENT-8a4497101bceb5f89ce3e971'], '班级：交回《秋游回执》': ids['AGENT-4be1b9a5da40e98d346fd320']}
        for n, case in enumerate(frozen('guard-controls.json')):
            message = dict(id=str(900 + n), sender_id='qa-head', sender='虚构班主任', text=case['text'], time='2026-11-03T16:51:00+08:00', kind='text', unread=False)
            evidence = [dict(message, ref='message:fictional-wechat-a:' + message['id'], publisher=agent._publisher('fictional-wechat-a', message), content_incomplete=False)]
            trial = dict(change='same', target_id=target_of[case['item']], state='ready', title=case['item'], goal=case['text'], reason='', purpose='learning' if '语文' in case['item'] else 'admin')
            agent._school_same_brief(trial, evidence, targets)
            self.assertEqual(trial['state'], expected[case['case']], (case['case'], case['text'], trial.get('reason')))
        # Real changes inside or beside relation words stay protected.
        for text in ('提醒语文《山间小路》朗读两遍并请家长在阅读登记本签字，明天早读查登记本；和QQ群语文老师那条是同一件事，改为朗读三遍。',
                     '《山间小路》家长签字，明天早读查登记本；和QQ群语文老师那条是同一件事，不用重复朗读。',
                     '提醒语文《山间小路》朗读两遍并请家长在阅读登记本签字，明天早读查登记本；同一件事，不用朗读了。'):
            message = dict(id='950', sender_id='qa-head', sender='虚构班主任', text=text, time='2026-11-03T16:51:00+08:00', kind='text', unread=False)
            evidence = [dict(message, ref='message:fictional-wechat-a:950', publisher=agent._publisher('fictional-wechat-a', message), content_incomplete=False)]
            trial = dict(change='same', target_id=target_of['语文：朗读《山间小路》两遍并签字'], state='ready', title='语文', goal=text, reason='', purpose='learning')
            agent._school_same_brief(trial, evidence, targets)
            self.assertNotEqual(trial['state'], 'ready', text)

    def test_b2_b3_negated_clause_has_no_day_and_parent_tonight_child_friday_are_separate(self):
        self.whole_day('original_day')
        view = self.view()
        rows = {r['title']: r for r in self.rows(view)}
        everything = self.rows(view) + view['upcoming']
        science = [r for r in everything if '透明塑料瓶' in r['title']]
        self.assertEqual(len(science), 1)
        science_row = next((r for r in self.rows(view) if '透明塑料瓶' in r['title']), None)
        self.assertIsNone(science_row, '周四带瓶不是今晚要做的事，只在即将一行')
        self.assertEqual(view['upcoming'][[u['title'] for u in view['upcoming']].index(science[0]['title'])]['day'], '2026-11-05')
        slip = self.by_title(view, '秋游回执')
        self.assertEqual((self.fact(slip, 'complete') or {}).get('value'), '2026-11-03', slip['facts'])
        self.assertEqual((self.fact(slip, 'due')['value'], self.fact(slip, 'due')['kind']), ('2026-11-06', 'handback'))
        self.assertEqual(slip['when'], 'today')
        history = self.by_title(view, '时代学案')
        self.assertEqual(history['when'], 'today'); self.assertEqual(self.fact(history, 'due')['value'], '2026-11-03')
        thursday = self.view('2026-11-05')
        bottle = self.by_title(thursday, '透明塑料瓶')
        self.assertIsNone(self.fact(bottle, 'complete')); self.assertEqual(bottle['when'], 'today')
        friday = self.view('2026-11-06')
        self.assertEqual(self.by_title(friday, '秋游回执')['when'], 'today')
        week = {w['day']: w for w in view['week']}
        for d in ('2026-11-03', '2026-11-05', '2026-11-06'):
            v = self.view(d)
            self.assertEqual((week[d]['open'], week[d]['today'], week[d]['upcoming']), (v['counts']['open'], v['counts']['today'], v['counts']['upcoming']))

    def test_b4_clear_same_publisher_update_shows_latest_on_the_one_card(self):
        self.whole_day()
        view = self.view()
        english = [r for r in self.rows(view) if 'Unit 9' in r['title'] and '听写' not in r['title']]
        self.assertEqual(len(english), 1, [r['title'] for r in self.rows(view)])
        row = english[0]
        self.assertEqual(row['version']['state'], 'latest', row['version'])
        self.assertIn('原三遍→两遍', row['version']['change'])
        self.assertTrue(any('两遍' in l for l in row['lines']), row['lines'])
        self.assertTrue(any('三遍' in l for l in row['version']['previous']['lines']))
        self.assertEqual({p['ref'] for p in row['publications']}, {'message:fictional-qq-a:103', 'message:fictional-qq-a:107'})
        self.assertFalse([r for r in self.rows(view) + view['upcoming'] if r['pending_review'] and '跟读' in r['title']])
        science = [u for u in view['upcoming'] if '透明塑料瓶' in u['title']] + [r for r in self.rows(view) if '透明塑料瓶' in r['title']]
        self.assertEqual(len(science), 1, '改到下周一的带瓶事项只在即将一行，带着变化，不另列')
        self.assertIn('11-05→11-09', science[0]['change']); self.assertNotIn(science[0], self.rows(view))
        monday = self.view('2026-11-09')
        bottle = self.by_title(monday, '透明塑料瓶')
        self.assertEqual(bottle['version']['state'], 'latest'); self.assertIn('11-05→11-09', bottle['version']['change'])
        # The pending notice remains the one place it is confirmed; nothing was written by reading.
        with self.app.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM agent_items WHERE state='pending' AND kind='school' AND plan LIKE '%\"change\": \"update\"%'").fetchone()[0], 2)
        other = self.view(child='child-2')
        self.assertEqual(len([r for r in self.rows(other) if '青石练习册' in r['title']]), 1)
        self.assertFalse(any('写出计算过程' in l for r in self.rows(other) for l in r['lines']))

    def test_b4_family_touched_or_other_publisher_update_stays_for_review_on_one_card(self):
        self.whole_day('original_day')
        english = self.task_for('message:fictional-qq-a:103')
        task = next(t for t in self.app.tasks(self.app.connect()) if t['id'] == english)
        self.app.update_task(english, dict(status='进行中', version=task.get('version', '')) if hasattr(self.app, 'update_task') else {}) if False else None
        with self.app.connect() as c:
            c.execute("INSERT INTO task_updates(id,status,updated) VALUES(?,?,?)", (english, '进行中', self.now.isoformat()))
        self.replay('cross_channel_reminders', 'receipt-02.json'); self.replay('same_publisher_corrections', 'receipt-03.json')
        view = self.view()
        rows = [r for r in self.rows(view) if 'Unit 9' in r['title'] and '听写' not in r['title']]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['version']['state'], 'review'); self.assertIn('家庭已有完成、状态或修改', row['version']['reasons'])
        self.assertTrue(any('三遍' in l for l in row['lines'])); self.assertEqual(row['status'], '进行中')
        self.assertTrue(any('两遍' in l for l in row['version']['notices'][0]['lines']))


if __name__ == '__main__':
    unittest.main()

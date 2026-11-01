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
            pending = [json.loads(r['plan'])['school_task'] for r in c.execute("SELECT plan FROM agent_items WHERE state='pending' AND kind='school'")]
            self.assertEqual(sorted(p['title'] for p in pending if p.get('change') == 'update'), ['科学：下周一实验课带空透明塑料瓶', '英语：跟读Unit 9第1—6个单词两遍'])
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


    def test_b1_relation_is_proven_whole_while_standards_quoted_states_and_new_rounds_stay(self):
        # Developer's own variants (Root keeps its held-out ones): other words for a pure relation link without the parent;
        # a standard, a quoted state or another item beside relation words is a requirement unit and stays for review.
        self.whole_day('original_day')
        ids = self.translate()
        targets = agent.school_targets(self.app, self.store, 'child-1')
        chinese, slip = ids['AGENT-8a4497101bceb5f89ce3e971'], ids['AGENT-4be1b9a5da40e98d346fd320']
        said = '提醒语文《山间小路》朗读两遍并请家长在阅读登记本签字，明天早读查登记本；'
        back = '秋游回执参加、不参加都交，今晚家长勾好并签字，周五孩子交班主任；'
        cases = [(chinese, said + '此处仅转发原要求，请不要理解为另布置第二项。', 'ready'),
                 (chinese, said + '这里只是转达前面语文老师的通知，并非另外一项任务。', 'ready'),
                 (slip, back + '和微信群王老师发的那份是一回事。', 'ready'),
                 (chinese, said + '和QQ群语文老师那条是同一件事，记得请家长明天签名。', 'ready'),
                 (chinese, said + '同原群那一份任务须注明朗读时长。', 'review'),
                 (chinese, said + '同原群那一份任务状态为“撤回”。', 'review'),
                 (chinese, said + '和QQ群语文老师那条是同一件事，务必用红笔圈出生字。', 'review'),
                 (chinese, said + '“不用签字”，和QQ群语文老师那条是同一件事。', 'review'),
                 (chinese, said + '这是另布置的第二项，请不要理解为原要求。', 'review'),
                 (slip, back + '请不要理解为另布置第二项，另交一张安全承诺书。', 'review')]
        for n, (target, text, expected) in enumerate(cases):
            message = dict(id=str(960 + n), sender_id='qa-head', sender='虚构班主任', text=text, time='2026-11-03T16:51:00+08:00', kind='text', unread=False)
            evidence = [dict(message, ref='message:fictional-wechat-a:' + message['id'], publisher=agent._publisher('fictional-wechat-a', message), content_incomplete=False)]
            trial = dict(change='same', target_id=target, state='ready', title='提醒', goal=text, reason='', purpose='learning' if target == chinese else 'admin')
            agent._school_same_brief(trial, evidence, targets)
            self.assertEqual(trial['state'], expected, (text, trial.get('reason')))
        # Root's minimal forms, as requirement units of the pure guard.
        geo = '地理：今晚完成《地形练习》第9页第2题，明天交。'
        for text in (geo + '同原群那一份任务须注明地图方向。', geo + '同原群那一份任务状态为“撤回”。'):
            body, relation = agent._school_relation_body(text)
            self.assertEqual((body, relation), (text, []))
            self.assertTrue(agent._school_same_changes(body, geo) or agent._school_same_unstated(body, geo), text)
        music = '音乐：周五带竖笛。'
        body, relation = agent._school_relation_body(music + '此处仅转发原要求，请不要理解为另布置第二项。')
        self.assertEqual((body, relation), (music, ['此处仅转发原要求', '请不要理解为另布置第二项']))
        self.assertFalse(agent._school_same_changes(body, music) or agent._school_same_unstated(body, music))
        for text in (music + '这是另布置的第二项。', music + '下周三再带一次竖笛。', '音乐：周五带两支竖笛。此处仅转发原要求。'):
            body, _ = agent._school_relation_body(text)
            self.assertTrue(agent._school_same_changes(body, music) or agent._school_counts(body) - agent._school_counts(music), text)

    def test_b2_double_negation_keeps_the_action_and_its_day(self):
        import family_agenda
        for clause in ('今晚不是不需要提交阅读卡', '明天不能不交', '今晚并非不用带回执'):
            self.assertFalse(agent._school_clause_negated(clause), clause)
            self.assertFalse(agent._school_negated_day(clause), clause)
            self.assertEqual(family_agenda._negated_actions(clause), set(), clause)
        self.assertIn('2026-11-03', family_agenda._action_deadlines('今晚不是不需要提交阅读卡，明早带到学校。', '2026-11-03'))
        # An ordinary negation still states no action or day; a contrasted positive step stays.
        self.assertTrue(agent._school_clause_negated('今晚不用填写实验记录表'))
        self.assertTrue(agent._school_negated_day('今晚不用填写实验记录表'))
        self.assertFalse(family_agenda._action_deadlines('今晚不用填写实验记录表。', '2026-11-03'))
        self.assertFalse(agent._school_clause_negated('今晚不用填表但要请家长签字'))

    def english(self, view):
        rows = [r for r in self.rows(view) if 'Unit 9' in r['title'] and '听写' not in r['title']]
        self.assertEqual(len(rows), 1, [r['title'] for r in self.rows(view)])
        return rows[0]

    def test_b4_unread_original_on_the_notice_keeps_review_until_wholly_read(self):
        import family_media
        self.whole_day()
        self.assertEqual(self.english(self.view())['version']['state'], 'latest')
        # An original (an unread PNG) linked straight to the read correction text: the text alone is not the whole notice.
        with self.app.connect() as c:
            c.execute('INSERT INTO agent_message_attachments(source_id,message_id,upload_id) VALUES(?,?,?)', ('fictional-qq-a', '107', 'f' * 32))
        row = self.english(self.view())
        self.assertEqual(row['version']['state'], 'review', row['version'])
        self.assertIn('通知或所附原件尚未读全', row['version']['reasons'])
        self.assertTrue(any('三遍' in l for l in row['lines']), row['lines'])
        read = dict(complete=True, upload_ids=['f' * 32], draft=dict(originals=[dict(upload_id='f' * 32, title='虚构原件', note='虚构：只需跟读两遍。', uncertainties=[])]))
        with patch.object(family_media, 'school_evidence', return_value=read):
            self.assertEqual(self.english(self.view())['version']['state'], 'latest', '读全原件后恢复明确最新展示')
        for partial in (dict(read, complete=False), dict(read, upload_ids=[]),
                        dict(read, draft=dict(originals=[dict(read['draft']['originals'][0], uncertainties=['右下角看不清'])]))):
            with patch.object(family_media, 'school_evidence', return_value=partial):
                self.assertEqual(self.english(self.view())['version']['state'], 'review', partial)

    def test_b4_latest_lines_must_be_the_notice_own_words(self):
        self.whole_day()
        with self.app.connect() as c:
            for x in c.execute("SELECT id,plan FROM agent_items WHERE state='pending' AND kind='school'").fetchall():
                plan = json.loads(x['plan'])
                if plan['school_task'].get('change') == 'update' and '跟读' in plan['school_task']['title']:
                    plan['school_task']['title'] = plan['school_task']['title'].replace('两遍', '四遍')
                    c.execute('UPDATE agent_items SET plan=? WHERE id=?', (json.dumps(plan, ensure_ascii=False), x['id']))
        row = self.english(self.view())
        self.assertEqual(row['version']['state'], 'review', row['version'])
        self.assertIn('新要求的归纳与通知原文对不上', row['version']['reasons'])
        self.assertTrue(any('三遍' in l for l in row['lines']), row['lines'])
    def same_trial(self, original, text, purpose='learning'):
        target = dict(id='T1', title=original.split('：')[0], goal=original, facts='', append_basis={'basis': 1}, same_complete=True,
                      targets_complete=True, status='', due='2026-11-04', same_basis=None)
        message = dict(id='990', sender_id='qa-head', sender='虚构老师', text=text, time='2026-11-03T16:51:00+08:00', kind='text', unread=False)
        evidence = [dict(message, ref='message:fictional-wechat-a:990', publisher='虚构老师', content_incomplete=False)]
        trial = dict(change='same', target_id='T1', state='ready', title='提醒', goal=text, reason='', purpose=purpose)
        agent._school_same_brief(trial, evidence, [target])
        return trial

    def test_p1a3_requirement_unit_type_matrix(self):
        # Developer's own semantic type matrix (Root keeps its held-out variants). A relation unit in any wording (a speech act on
        # the message, an identity, a denied other item) holds no requirement and its ordinal counts nothing; the same characters
        # bound to another actor, object, count or day are another requirement; real changes, standards and new rounds stay.
        original = '语文：今晚孩子朗读《山间》两遍并抄写《春晓》一遍，家长签字，明天交。'
        cases = [(original + '这条只是把老师原话再发一遍，不是第二份作业。', 'ready'),
                 (original + '这只是转一下，别当成第二份。', 'ready'),
                 (original + '重复一下，并非另一项任务。', 'ready'),
                 ('语文：《山间》今晚读两遍，《春晓》抄写一遍，家长签名，明天交。', 'ready'),
                 (original, 'ready'),
                 ('语文：今晚家长朗读《山间》两遍并抄写《春晓》一遍，孩子签字，明天交。', 'review'),
                 ('语文：今晚孩子朗读《春晓》两遍并抄写《山间》一遍，家长签字，明天交。', 'review'),
                 ('语文：今晚孩子朗读《山间》一遍并抄写《春晓》两遍，家长签字，明天交。', 'review'),
                 ('语文：明天孩子朗读《山间》两遍并抄写《春晓》一遍，家长签字，今晚交。', 'review'),
                 (original + '这条只是再发一遍，不是第二份，是第三份。', 'review'),
                 (original + '提醒孩子再读一遍。', 'review'),
                 (original + '同原群那一份任务须注明朗读时长。', 'review'),
                 (original + '重复一下，这份作业取消。', 'review')]
        for text, expected in cases:
            trial = self.same_trial(original, text)
            self.assertEqual(trial['state'], expected, (text, trial.get('reason')))
        # Root's controls: one actor's step given to the other is no repeat, whatever the shared characters.
        for old, new in (('语文：孩子须朗读两遍《山间》，家长须检查。', '语文：家长须朗读两遍《山间》，孩子须检查。'),
                         ('语文：今晚孩子写《生字表》第3页，家长签字，明天交。', '语文：今晚家长写《生字表》第3页，孩子签字，明天交。')):
            self.assertEqual(self.same_trial(old, old)['state'], 'ready')
            trial = self.same_trial(old, new)
            self.assertEqual(trial['state'], 'review', new); self.assertIn('由谁做哪一步', trial['reason'])
        self.assertEqual(agent._school_relation_body(original + '这只是转一下，别当成第二份。'), (original, ['这只是转一下', '别当成第二份']))
        # Relation words never cover work: an act not on the message itself or a denial of no whole item keeps the clause.
        for clause in ('请说明理由', '观察豆子发芽', '不要忘记带新的笔记本', '请告知老师', '提醒大家明天带竖笛', '请家长转告孩子', '转发一下第二份通知'):
            self.assertFalse(agent._school_relation_unit(clause), clause)

    def test_p1a3_double_negation_is_read_affirmative_by_every_time_role_reader(self):
        import family_agenda
        sent = '2026-11-03T16:51:00+08:00'
        for plain, double in (('今晚需要提交阅读卡，明早带到学校。', '今晚不是不需要提交阅读卡，明早带到学校。'),
                              ('今晚完成阅读卡，明天交给老师。', '今晚不能不完成阅读卡，明天交给老师。'),
                              ('今晚读课文，明天早读检查。', '今晚不是不用读课文，明天早读检查。')):
            handed, plain_handed = {}, {}
            roles = agent._school_role_days(double, [dict(text=double, time=sent)], [], handbacks=handed)
            self.assertEqual(roles, ({'2026-11-03'}, '2026-11-04'), double)
            self.assertEqual(roles, agent._school_role_days(plain, [dict(text=plain, time=sent)], [], handbacks=plain_handed), plain)
            # Corrected truth (run4): the double negation keeps tonight's own action and day, nothing more. 今晚(不是不)需要提交 is a
            # handback that evening, never work finished at home; the earlier day is named as a handback, not a completion.
            self.assertEqual(set(handed), {'2026-11-03'} if '提交' in double else set(), double)
            self.assertEqual(set(handed), set(plain_handed), plain)
            self.assertEqual(family_agenda._action_deadlines(double, '2026-11-03'), family_agenda._action_deadlines(plain, '2026-11-03'), double)
        # One evening handback with no later day keeps its own due; an ordinary negation still states no action or day.
        self.assertEqual(agent._school_role_days('今晚提交阅读卡。', [dict(text='今晚提交阅读卡。', time=sent)], []), (set(), '2026-11-03'))
        # An evening handback beside a later handback of another thing proves no link: the two-date guard keeps it for review.
        self.assertIsNone(agent._school_role_days('今晚提交电子版，明天交纸质版。', [dict(text='今晚提交电子版，明天交纸质版。', time=sent)], []))
        self.assertEqual(family_agenda.affirmed('今晚不用填写实验记录表'), '今晚不用填写实验记录表')
        self.assertFalse(family_agenda._action_deadlines('今晚不用填写实验记录表。', '2026-11-03'))

    def test_p1a4_requirement_units_stay_bound_tuples(self):
        # Developer type matrix (Root keeps its held-out variants): each actor/step/count/object/day unit is compared whole, so a
        # swap between two units of one step is another requirement however equal the unions; reorder/omission stays the same.
        original = '语文：学生抄写《竹叶》三遍，家长抄写《竹叶》一遍，明天检查。'
        cases = [('语文：学生抄写《竹叶》一遍，家长抄写《竹叶》三遍，明天检查。', 'review'),  # counts swapped between actors
                 ('语文：家长抄写《竹叶》一遍，学生抄写《竹叶》三遍，明天检查。', 'ready'),   # units reordered
                 ('语文：学生抄写《竹叶》三遍，明天检查。', 'ready'),                       # one unit omitted
                 ('语文：《竹叶》学生抄写三遍，家长抄一遍，明天检查。', 'ready'),           # shortened, object written once
                 ('语文：学生抄写《竹叶》三遍，家长抄写《竹叶》两遍，明天检查。', 'review')]
        for text, expected in cases:
            self.assertEqual(self.same_trial(original, text)['state'], expected, text)
        for old, new in (('语文：学生抄写《竹叶》三遍，家长抄写《松树》一遍，明天检查。', '语文：学生抄写《松树》三遍，家长抄写《竹叶》一遍，明天检查。'),
                         ('语文：学生今晚抄写《竹叶》，家长明天抄写《松树》。', '语文：学生明天抄写《竹叶》，家长今晚抄写《松树》。')):
            self.assertEqual(self.same_trial(old, old)['state'], 'ready', old)
            trial = self.same_trial(old, new)
            self.assertEqual(trial['state'], 'review', new); self.assertIn('由谁做哪一步', trial['reason'])
        units = agent._school_units(original)[agent._SCHOOL_UNIT_STEPS.index(r'抄写|抄')]
        self.assertEqual(sorted((u[0], sorted(u[1])) for u in units), [('child', [(3, '遍')]), ('parent', [(1, '遍')])])

    def test_p1a4_explanatory_negation_and_sign_synonyms_by_type(self):
        original = '语文：今晚孩子朗读《山间》两遍，家长签字，明天交。'
        for text, expected in ((original + '这仍是同一件，不必另外重做一轮。', 'ready'),          # another round denied
                               (original + '这只是同一件事，不用再单独做一遍。', 'ready'),
                               (original + '无需另外再读一遍。', 'ready'),                     # its verb restated above
                               ('语文：家长签字，明天交。无需另外再读一遍。', 'review'),         # 读 not restated: a change
                               ('语文：原先朗读取消，不必读，家长签字，明天交。', 'review'),      # real cancellation
                               (original + '不必读。', 'review'),                             # the work itself denied
                               (original + '明天再读一遍。', 'review'),                       # real new round
                               (original + '不用再读一遍，明天读三遍。', 'review')):
            self.assertEqual(self.same_trial(original, text)['state'], expected, text)
        signed = '班级：出行确认单请家长签好名字，周四交。'
        for text, expected in (('班级：那张已签名的出行确认单，让学生周四交。', 'ready'),  # a signed state, no new actor step
                               ('班级：那张已签名的《出行确认单》，让学生周四交。', 'ready'),
                               ('班级：出行确认单请家长签上姓名，周四交。', 'ready'),
                               ('班级：出行确认单请家长签好名字，让学生也签名，周四交。', 'review'),  # a real new signature
                               ('班级：出行确认单请家长签好名字，周四交。另外请奶奶也签字。', 'review')):
            self.assertEqual(self.same_trial(signed, text)['state'], expected, text)
        unsigned = '班级：出行确认单请家长填好，周四交。'
        self.assertEqual(self.same_trial(unsigned, '班级：那张已签名的出行确认单，让学生周四交。')['state'], 'review')

    def test_p1a4_evening_handback_is_no_completion_and_parent_steps_keep_their_day(self):
        import family_agenda
        sent = '2026-11-03T16:51:00+08:00'
        def roles(text):
            handed = {}; found = agent._school_role_days(text, [dict(text=text, time=sent)], [], handbacks=handed)
            return found, handed
        for text in ('班级：今晚在线提交《活动卡》，明早交给班主任。', '今晚提交原件，明早交给班主任。', '今晚需要提交阅读卡，明早带到学校。'):
            found, handed = roles(text)
            self.assertEqual(found, ({'2026-11-03'}, '2026-11-04'), text); self.assertEqual(list(handed), ['2026-11-03'], text)
            self.assertIn('提交', handed['2026-11-03'])
        for text, due in (('今晚家长签名，明早交。', '2026-11-04'), ('今晚选择参加项目，明早交回。', '2026-11-04'),
                          ('今晚完成阅读卡，明天交给老师。', '2026-11-04'),
                          ('今晚监护人在《出行确认单》圈选‘同意’或‘不同意’，并签上姓名；本周五让学生交给班主任。', '2026-11-06')):
            found, handed = roles(text)
            self.assertEqual(found, ({'2026-11-03'}, due), text); self.assertEqual(handed, {}, text)
        self.assertEqual(roles('今晚不必提交，明早交给老师。'), ((set(), '2026-11-04'), {}))
        self.assertFalse(agent._school_clause_negated(agent._school_choices_read('今晚监护人在《出行确认单》圈选‘同意’或‘不同意’')))
        for text in ('今晚提交电子版，明天交纸质版。', '今晚在线提交《活动卡》，明早科学课带放大镜。', '今晚提交活动卡，明早或后天交给班主任。'):
            self.assertIsNone(roles(text)[0], text)
        # The projection keeps both handbacks as two roles of the one item, the earlier never labelled 完成.
        agenda = dict(published_at='2026-11-03T16:51:00+08:00', due_on='2026-11-04', due_kind='handback', submit_on='2026-11-03',
                      submit_words='今晚在线提交《活动卡》')
        facts = family_agenda.day_facts(agenda, '2026-11-03', '2026-11-03', True)
        self.assertEqual([(f['role'], f['value']) for f in facts if f['role'] in ('complete', 'submit', 'due')],
                         [('submit', '2026-11-03'), ('due', '2026-11-04')])
        self.assertEqual(next(f for f in facts if f['role'] == 'submit')['words'], '今晚在线提交《活动卡》')
        self.assertEqual((family_agenda.day_role(agenda, '2026-11-03'), family_agenda.day_role(agenda, '2026-11-04')), ('today', 'today'))

    def test_p1a3_structured_linked_feedback_keeps_the_original_version(self):
        # A parent observation saved on its own and then linked through the record API (source stays the parent's own words,
        # linked_task_id names the task) is family feedback exactly as an 事项: record is: a later clear update stays for review.
        self.whole_day('original_day')
        english = self.task_for('message:fictional-qq-a:103')
        record = self.app.save_record(dict(child='示例甲', day='2026-11-03', category='家长观察', subject='英语', title='跟读观察',
                                           note='虚构：前三个单词读得较慢', source='家长手记'))['record_id']
        self.app.link_record_task(dict(record_id=record, child='示例甲', task_id=english))
        self.replay('cross_channel_reminders', 'receipt-02.json'); self.replay('same_publisher_corrections', 'receipt-03.json')
        row = self.english(self.view())
        self.assertEqual(row['version']['state'], 'review', row['version']); self.assertIn('家庭已有反馈', row['version']['reasons'])
        self.assertTrue(any('三遍' in l for l in row['lines'])); self.assertTrue(any('两遍' in l for l in row['version']['notices'][0]['lines']))
        with self.app.connect() as c:
            saved = c.execute('SELECT source,linked_task_id FROM records WHERE id=?', (record,)).fetchone()
        self.assertEqual((saved['source'], saved['linked_task_id']), ('家长手记', english))


if __name__ == '__main__':
    unittest.main()

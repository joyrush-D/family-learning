"""Role-aware school days for a lesson's own day, a negated day and a form's completion before its handback.

Pure fiction, no real model: each original goes through Store.ingest → run_once with a fixed reply (not model output) →
app.tasks and its agenda. A day its lesson directly heads is that lesson's arranged day, a negated tonight clause gives no
day, a negated 居家 practice leaves a bringing item admin, and a form's tonight choice/signature is its completion day while
its later handback stays the due. 签名 is the same signature as 签字, a lesson a qualified weekday heads (下周一课堂) keeps its
day beside another day's negated clause, and 明天上课检查 is that lesson's check (inspection) after tonight's own work.
"""
import copy
import datetime as dt
import json
import unittest

import family_agenda
import family_agent as agent
import test_school_native_coverage as native

PUBLISHED = '2026-11-10T16:00:00+08:00'  # a Tuesday; 周四 is 2026-11-12
FOLLOWUP = '2026-11-04T16:00:00+08:00'  # a Wednesday; 明天/周四 is 2026-11-05, 下周一 is 2026-11-09
SOURCE = dict(id='qa-date-role-public-01', platform='qq', name='虚构四年级二班')


class SchoolDateRoleTests(unittest.TestCase):
    setUp = native.SchoolNativeCoverageTests.setUp

    def run_one(self, text, purpose, subject, due, published=PUBLISHED):
        self.fixture.source.update(SOURCE);self.fixture.config()
        self.fixture.now = self.now = dt.datetime.fromisoformat(published).replace(tzinfo=agent.TZ) + dt.timedelta(minutes=30)
        payload = self.fixture.payload(cursor='1')
        payload['messages'] = [dict(id='1', time=published, kind='text', sender='虚构老师', text=text, unread=False,
                                    sender_id='qa-teacher-date-role', message_order='1')]
        self.store.ingest(payload)
        proposal = dict(title_quote=text, focus='school', due=due, evidence=[{'ref': 'message:%s:1' % SOURCE['id']}],
                        learning_subject=subject, learning_goal_id='', task_title=text[:16], task_goal=text, task_advice='',
                        task_change='new', task_target_id='', task_state='ready', task_reason='纯虚构固定回复，不是模型产物。',
                        task_purpose=purpose, task_submission='')
        self.model.side_effect = lambda *args, **kwargs:dict(proposals=[copy.deepcopy(proposal)])
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
        self.assertEqual(len(rows), 1, 'one own item')
        with self.app.connect() as c:
            tasks = {t['id']:t for t in self.app.tasks(c)}
        brief = json.loads(rows[0]['plan'])['school_task']
        task = tasks[rows[0]['task_id']]
        # The original's own words; a leading label naming the item's own subject (英语：) may stand as that subject instead.
        words = text[len(subject) + 1:] if subject and text.startswith((subject + '：', subject + ':')) else text
        self.assertIn(words.rstrip('。'), task['action'].replace('\n', ''))
        return rows[0], brief, task['agenda']

    def test_a_lesson_day_oral_activity_is_its_arranged_learning_day_and_a_negated_tonight_gives_none(self):
        for text in ('地理：周四课堂用地图口头介绍《河流之旅》，限3分钟，今晚不交书面作业。',
                     '地理：周四课堂用地图口头介绍《河流之旅》，限3分钟。',
                     '地理：周四地理课用地图口头介绍《河流之旅》，限3分钟，今晚不交书面作业。'):
            with self.subTest(text=text):
                self.setUp()
                row, brief, agenda = self.run_one(text, 'learning', '地理', '2026-11-12')
                self.assertEqual((row['state'], brief['state'], brief['purpose']), ('accepted', 'ready', 'learning'))
                self.assertEqual((agenda['category'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                                 ('homework', '2026-11-12', 'arranged', ''))

    def test_a_bringing_item_with_negated_home_practice_stays_admin_on_its_lesson_day(self):
        for text in ('周四音乐课带一支竖笛，不用居家练习。', '周四音乐课带一支竖笛，不用在家练习。'):
            with self.subTest(text=text):
                self.setUp()
                row, brief, agenda = self.run_one(text, 'admin', '', '2026-11-12')
                self.assertEqual((row['state'], brief['state'], brief['purpose']), ('accepted', 'ready', 'admin'))
                self.assertEqual((agenda['category'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                                 ('todo', '2026-11-12', 'arranged', ''))

    def test_a_forms_tonight_choice_and_signature_is_its_completion_before_its_later_handback(self):
        for text in ('《研学报名回执》今晚勾选同意或不同意并签字，孩子周四交给班主任。',
                     '今晚请家长在《研学报名回执》勾选同意或不同意并签字，孩子周四交给班主任。'):
            with self.subTest(text=text):
                self.setUp()
                row, brief, agenda = self.run_one(text, 'admin', '', '2026-11-12')
                self.assertEqual((row['state'], brief['state'], brief['purpose']), ('accepted', 'ready', 'admin'))
                self.assertEqual((agenda['category'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                                 ('todo', '2026-11-12', 'handback', '2026-11-10'))

    def test_actual_home_practice_or_an_inverse_still_reads_as_learning(self):
        value = dict(title='课堂准备', goal='', advice='', state='ready', reason='', purpose='admin')
        brief = lambda text:agent._school_brief(dict(value, goal=text), evidence=[dict(ref='message:s:1', text=text, kind='text', unread=False)],
                                                separate_learning=True)
        self.assertEqual(brief('周四音乐课带一支竖笛，不用居家练习。')['state'], 'ready')
        for text in ('周四音乐课带一支竖笛，今晚居家练习两遍。', '周四音乐课带一支竖笛，并非不用居家练习。',
                     '周四音乐课带一支竖笛，不用居家练习，今晚背诵课文。'):
            with self.subTest(text=text):self.assertEqual(brief(text)['state'], 'review')

    def test_negated_changed_recurring_or_other_role_days_keep_their_own_meaning(self):
        day = '2026-11-10'
        # A negated action ties no day; the positive one and a 不晚于 bound still do.
        self.assertEqual(family_agenda.deadlines('今晚不交书面作业。', day), set())
        self.assertEqual(family_agenda.deadlines('明天不用带跳绳。', day), set())
        self.assertEqual(family_agenda.deadlines('今晚交书面作业。', day), {'2026-11-10'})
        self.assertEqual(family_agenda.deadlines('明天不晚于8点交练习册。', day), {'2026-11-11'})
        # Only a lesson the day directly heads, done as stated, is that lesson's own day.
        self.assertEqual(agent._school_own_dates('周四地理课用地图口头介绍《河流之旅》，限3分钟，今晚不交书面作业。', day), {'2026-11-12'})
        for text in ('周四地理课不用口头介绍。', '每周四地理课口头介绍。', '周四地理课改为口头介绍。', '周四地理课要口头介绍吗？'):
            with self.subTest(text=text):self.assertEqual(agent._school_own_dates(text, day), set())
        # 别 ending another word is no negation: 明天分别完成 still ties tomorrow.
        self.assertEqual(family_agenda.deadlines('明天分别完成两件事。', day), {'2026-11-11'})
        self.assertEqual(family_agenda.date_meaning('周四地理课用地图口头介绍《河流之旅》。', '2026-11-12', day), 'arranged')
        # A check, test or handing in at that lesson keeps its own meaning, never the lesson's arrangement.
        for text in ('周四英语课听写单词。', '周四数学课交练习册。', '周四数学课前完成练习册第3页。', '周四地理课不用口头介绍。'):
            with self.subTest(text=text):self.assertNotEqual(family_agenda.date_meaning(text, '2026-11-12', day), 'arranged')
        # A weekday handback is the form's role day; no tonight work, a day left to choose or a recurring day gives no completion.
        read = lambda text:agent._school_role_days(text, [dict(text=text, time=PUBLISHED)], [])
        self.assertEqual(read('《研学报名回执》今晚勾选同意或不同意并签字，孩子周四交给班主任。'), ({'2026-11-10'}, '2026-11-12'))
        self.assertEqual(read('《研学报名回执》请家长签字，孩子周四交给班主任。'), (set(), '2026-11-12'))
        for text in ('《研学报名回执》今晚请家长签字，孩子周四或周五交给班主任。', '《研学报名回执》今晚请家长签字，孩子每周四交给班主任。'):
            with self.subTest(text=text):self.assertIsNone(read(text))

    def check_one(self, text, purpose, subject, expected):
        row, brief, agenda = self.run_one(text, purpose, subject, expected[1], FOLLOWUP)
        self.assertEqual((row['state'], brief['state'], brief['purpose']), ('accepted', 'ready', purpose))
        self.assertEqual((agenda['category'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']), expected)

    def test_a_qualified_weekday_lesson_beside_a_negated_tonight_is_that_lessons_arranged_day(self):
        for text in ('地理：下周一课堂用时间轴口头讲述《江河变迁》，限3分钟，今晚不用交纸质作业。',
                     '地理：下周一地理课用时间轴口头讲述《江河变迁》，限3分钟，今晚不用交纸质作业。',
                     '地理：下周一课堂用时间轴口头讲述《江河变迁》，限3分钟。'):
            with self.subTest(text=text):
                self.setUp()
                self.check_one(text, 'learning', '地理', ('homework', '2026-11-09', 'arranged', ''))

    def test_a_forms_tonight_choice_and_签名_is_its_completion_before_its_qualified_weekday_handback(self):
        for text in ('今晚请家长在《午餐选择单》勾选一种套餐并签名，孩子下周一交回。',
                     '《午餐选择单》今晚勾选一种套餐并签名，孩子下周一交给班主任。',
                     '今晚请家长在《午餐选择单》勾选一种套餐并签字，孩子下周一交回。'):
            with self.subTest(text=text):
                self.setUp()
                self.check_one(text, 'admin', '', ('todo', '2026-11-09', 'handback', '2026-11-04'))

    def test_tonight_learning_checked_at_tomorrows_lesson_is_done_tonight_and_inspected_then(self):
        for text in ('英语：今晚跟读Unit4对话两遍，不用抄写，明天上课检查。', '英语：今晚跟读Unit4对话两遍，明天上课检查。'):
            with self.subTest(text=text):
                self.setUp()
                self.check_one(text, 'learning', '英语', ('homework', '2026-11-05', 'inspection', '2026-11-04'))

    def test_negated_other_work_and_negated_home_practice_controls_keep_their_days(self):
        for text, purpose, subject, expected in (
                ('英语：今晚不用抄写旧词但要完成词表第2页，明天交给老师。', 'learning', '英语', ('homework', '2026-11-05', 'handback', '2026-11-04')),
                ('语文：今晚不用录音但要完成《枫影》练习题，明天交给语文老师。', 'learning', '语文', ('homework', '2026-11-05', 'handback', '2026-11-04')),
                ('周四体育课带一条短绳，无需居家练习。', 'admin', '', ('todo', '2026-11-05', 'arranged', ''))):
            with self.subTest(text=text):
                self.setUp()
                self.check_one(text, purpose, subject, expected)

    def test_qualified_weekday_lesson_签名_and_lesson_check_guards_keep_their_own_meaning(self):
        day = '2026-11-04'
        # Another day's negated clause set aside leaves the lesson's own day; a recurring, changed, negated, cancelled or asked
        # lesson still states none, and the negated clause alone none.
        self.assertEqual(agent._school_own_dates('地理：下周一课堂用时间轴口头讲述《江河变迁》，限3分钟，今晚不用交纸质作业。', day), {'2026-11-09'})
        for text in ('今晚不用交纸质作业。', '每周一课堂用时间轴口头讲述《江河变迁》，今晚不用交纸质作业。',
                     '下周一课堂改为用时间轴口头讲述，今晚不用交纸质作业。', '下周一课堂不用口头讲述，今晚不用交纸质作业。',
                     '下周一课堂的口头讲述取消，今晚不用交纸质作业。', '下周一课堂要口头讲述吗？今晚不用交纸质作业。'):
            with self.subTest(text=text):self.assertEqual(agent._school_own_dates(text, day), set())
        meaning = lambda text, due='2026-11-05':family_agenda.date_meaning(text, due, day)
        self.assertEqual(meaning('地理：下周一课堂用时间轴口头讲述《江河变迁》，限3分钟，今晚不用交纸质作业。', '2026-11-09'), 'arranged')
        # 明天上课检查 is that lesson's check as 明天早读检查 is; handing in there is its handback. A negated, joined, recurring
        # or chosen day's check is none of these.
        for text in ('英语：今晚跟读Unit4对话两遍，不用抄写，明天上课检查。', '今晚跟读Unit4对话两遍，明天上课时检查。', '今晚跟读Unit4对话两遍，明天早读检查。'):
            with self.subTest(text=text):self.assertEqual(meaning(text), 'inspection')
        self.assertEqual(meaning('今晚跟读Unit4对话两遍，明天上课交回。'), 'handback')
        for text in ('今晚跟读Unit4对话两遍，明天上课不检查。', '今晚跟读Unit4对话两遍，明天上课不用检查。', '今晚跟读Unit4对话两遍，明天上课检查并交回。',
                     '今晚跟读Unit4对话两遍，每天上课检查。', '今晚跟读Unit4对话两遍，明天或后天上课检查。'):
            with self.subTest(text=text):self.assertEqual(meaning(text), 'deadline')
        # 签名 is that lesson day's own predicate as 签字 is, never inside a 《》 title.
        self.assertEqual(meaning('下周一课堂讲述《签名的故事》。', '2026-11-09'), 'arranged')
        for text in ('下周一课堂讲述后签名。', '下周一课堂讲述后签字。'):
            with self.subTest(text=text):self.assertEqual(meaning(text, '2026-11-09'), 'deadline')
        # A form's tonight 签名 is its completion before its qualified-weekday handback; a signature only inside a name
        # (《家长签名确认单》、交回签名回执) completes nothing; a chosen, recurring or changed day, another cited original
        # stating a day or another proposal quoting its words leaves it to the date guards.
        read = lambda text, cited=(), others=():agent._school_role_days(text, [dict(text=text, time=FOLLOWUP), *cited], list(others))
        form = '今晚请家长在《午餐选择单》勾选一种套餐并签名，孩子下周一交回。'
        self.assertEqual(read(form), ({'2026-11-04'}, '2026-11-09'))
        self.assertEqual(read(form.replace('签名', '签字')), ({'2026-11-04'}, '2026-11-09'))
        self.assertEqual(read('《午餐选择单》今晚勾选一种套餐并签名，孩子下周一交给班主任。'), ({'2026-11-04'}, '2026-11-09'))
        for text in ('《家长签名确认单》孩子下周一交回。', '孩子下周一交回签名回执。'):
            with self.subTest(text=text):self.assertEqual(read(text), (set(), '2026-11-09'))
        for text in (form.replace('下周一', '下周一或下周二'), form.replace('下周一', '每周一'), form.replace('交回。', '交回改为下周二交回。')):
            with self.subTest(text=text):self.assertIsNone(read(text))
        self.assertIsNone(read(form, cited=[dict(text='午餐选择单改为下周二交回。', time=FOLLOWUP)]))
        self.assertIsNone(read(form, others=['孩子下周一交回']))
        # Withdrawing the signature (不用签名) withdraws it as 不用签字 does; a kept one or one inside a title does not.
        for later, withdrawn in (('午餐选择单不用签名了。', True), ('午餐选择单不用签字了。', True), ('午餐选择单照常签名。', False),
                                 ('请阅读《不用签名的理由》。', False)):
            with self.subTest(later=later):self.assertEqual(agent._school_range_withdrawn(form, [later]), withdrawn)
        self.assertTrue(agent._school_range_withdrawn('今晚请家长在《午餐选择单》勾选一种套餐，不用签名，孩子下周一交回。', []))

    def assessed(self, text, subject, due, expected):
        row, brief, agenda = self.run_one(text, 'learning', subject, due, FOLLOWUP)
        self.assertEqual((row['state'], brief['state'], brief['purpose']), ('accepted', 'ready', 'learning'))
        self.assertEqual((agenda['due_on'], agenda['due_kind'], agenda['complete_on'], agenda['subjects']), expected)
        return agenda

    def test_a_classroom_assessment_at_its_lesson_or_morning_reading_is_the_teachers_check(self):
        for text, subject, due in (('英语：明天英语课听写Unit 9第1至6个单词，不用在家另做听写。', '英语', '2026-11-05'),
                                   ('周五数学课测验小数乘法，今晚不用交纸质作业。', '数学', '2026-11-06'),
                                   ('语文：下周一早读抽背《溪桥》，不用另交录音。', '语文', '2026-11-09')):
            with self.subTest(text=text):
                self.setUp()
                self.assessed(text, subject, due, (due, 'inspection', '', [subject]))

    def test_tonight_follow_reading_and_tomorrows_classroom_dictation_stay_two_actions(self):
        text = '英语：今晚听音频跟读Unit 9第1至6个单词，每词2遍，不用抄写；明天英语课听写。'
        self.fixture.source.update(SOURCE);self.fixture.config()
        self.fixture.now = self.now = dt.datetime.fromisoformat(FOLLOWUP).replace(tzinfo=agent.TZ) + dt.timedelta(minutes=30)
        payload = self.fixture.payload(cursor='1')
        payload['messages'] = [dict(id='1', time=FOLLOWUP, kind='text', sender='虚构老师', text=text, unread=False,
                                    sender_id='qa-teacher-date-role', message_order='1')]
        self.store.ingest(payload)
        reply = lambda quote, title, due:dict(
            title_quote=quote, focus='school', due=due, evidence=[{'ref': 'message:%s:1' % SOURCE['id']}], learning_subject='英语',
            learning_goal_id='', task_title=title, task_goal=quote + '。', task_advice='', task_change='new', task_target_id='',
            task_state='ready', task_reason='纯虚构固定回复，不是模型产物。', task_purpose='learning', task_submission='')
        replies = [reply('英语：今晚听音频跟读Unit 9第1至6个单词，每词2遍，不用抄写', '英语：今晚跟读Unit 9', ''),
                   reply('明天英语课听写', '英语：明天课堂听写', '2026-11-05')]
        self.model.side_effect = lambda *args, **kwargs:dict(proposals=copy.deepcopy(replies))
        result = agent.run_once(self.app, self.now)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        with self.store._db() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
        with self.app.connect() as c:
            tasks = {t['id']:t for t in self.app.tasks(c)}
        self.assertEqual(sorted(r['state'] for r in rows), ['accepted', 'accepted'], 'two own actions, neither swallowed')
        tonight, = [tasks[r['task_id']] for r in rows if '跟读' in tasks[r['task_id']]['action']]
        dictation, = [tasks[r['task_id']] for r in rows if '跟读' not in tasks[r['task_id']]['action']]
        self.assertIn('2026-11-04', (tonight['agenda']['complete_on'], tonight['agenda']['due_on']))
        self.assertNotEqual(tonight['agenda']['due_kind'], 'inspection')
        self.assertIn('明天英语课听写', dictation['action'])
        self.assertEqual((dictation['agenda']['due_on'], dictation['agenda']['due_kind'], dictation['agenda']['complete_on'],
                          dictation['agenda']['subjects']), ('2026-11-05', 'inspection', '', ['英语']))

    def test_home_dictation_keeps_tonights_completion_before_its_handback(self):
        self.assessed('英语：今晚在家听写Unit 9第1至6个单词，每词1遍，明早把听写本交给英语老师。', '英语', '2026-11-05',
                      ('2026-11-05', 'handback', '2026-11-04', ['英语']))

    def test_a_carried_name_a_negation_a_bare_day_or_a_genuine_deadline_is_no_classroom_check(self):
        day = '2026-11-04'
        meaning = lambda text, due='2026-11-05':family_agenda.date_meaning(text, due, day)
        for text, due in (('明天英语课听写Unit 9单词。', '2026-11-05'), ('明天英语课上听写。', '2026-11-05'),
                          ('明天上课默写Unit 9短语。', '2026-11-05'), ('周五数学课测验小数乘法。', '2026-11-06'),
                          ('下周一早读抽背《溪桥》。', '2026-11-09')):
            with self.subTest(text=text):self.assertEqual(meaning(text, due), 'inspection')
        # Carrying a thing whose name holds 听写 is its own carrying, read as the lesson day's arrangement.
        for text in ('明天英语课带《单词听写本》，不用在家练习。', '明天英语课带单词听写本。'):
            with self.subTest(text=text):
                self.assertFalse(agent._school_lesson_assessment(text.split('，')[0]))
                self.assertNotEqual(meaning(text), 'inspection')
        self.assertEqual(meaning('明天英语课带《单词听写本》，不用在家练习。'), 'arranged')
        # Home dictation handed back next morning, or handed back after the lesson's own dictation, keeps its handback.
        self.assertEqual(meaning('今晚在家听写Unit 9单词，明早把听写本交给英语老师。'), 'handback')
        self.assertEqual(meaning('明天英语课听写并交回听写本。'), 'handback')
        # A negated, changed, recurring or chosen assessment, one with no lesson named (明天听写) and a day the work must come
        # before stay as they were: never the teacher's check, never a date from a name or a negation.
        for text in ('明天英语课不听写。', '明天英语课不用听写，今晚在家听写两遍。', '明天英语课听写取消。', '每天英语课听写。',
                     '明天或后天英语课听写。', '明天听写Unit 9单词。', '明天英语课前完成听写练习。',
                     '明天英语课前交听写订正。', '11月5日前完成听写练习。'):
            with self.subTest(text=text):self.assertEqual(meaning(text), 'deadline')
        self.assertEqual(family_agenda.deadlines('明天英语课带《单词听写本》，不用在家练习。', day) - {'2026-11-05'}, set())

    def test_an_own_course_header_kept_in_the_quote_reads_the_same_role_as_the_same_words_without_it(self):
        day = '2026-11-04'
        meaning = lambda text, due='2026-11-05':family_agenda.date_meaning(text, due, day)
        # The same own words read the same role whether the quote keeps its course header (英语：) or starts after it: a carried
        # thing at its lesson, a check, a handback, a lesson's own assessment. A real deadline before it, a negation, the work
        # itself, a ba-phrase, another predicate (准备好、并交回执、并完成) or a verb inside the carried name stays as it was.
        for label, body, role in (('英语', '明天英语课带《单词听写本》，不用在家练习。', 'arranged'),
                                  ('英语', '明天英语课带单词听写本。', 'arranged'),
                                  ('体育', '明天体育课带跳绳，不要求在家训练。', 'arranged'),
                                  ('科学', '附件是明天带去课堂的实验观察表，今晚不填', 'arranged'),
                                  ('语文和数学', '明天带尺子和字典。', 'arranged'),
                                  ('英语', '明天英语课听写。', 'inspection'),
                                  ('语文', '今晚朗读《晚照》2遍，请家长签字，明天早读检查。', 'inspection'),
                                  ('数学', '今晚完成练习册第12页第2至4题，写出计算过程，明天交回。', 'handback'),
                                  ('体育', '明天体育课带跳绳并交回执。', 'handback'),
                                  ('体育', '11月5日前带跳绳。', 'deadline'),
                                  ('体育', '明天体育课不用带跳绳。', 'deadline'),
                                  ('数学', '明天带来。', 'deadline'),
                                  ('数学', '明天把单词卡带到学校。', 'deadline'),
                                  ('英语', '明天准备好听写本。', 'deadline'),
                                  ('英语', '明天英语课不听写。', 'deadline'),
                                  ('英语', '明天英语课前交听写订正。', 'deadline'),
                                  ('英语', '明天英语课带《单词听写本》并完成听写练习。', 'deadline')):
            for text in (body, label + '：' + body, label + ':' + body):
                with self.subTest(text=text):self.assertEqual(meaning(text), role)
        # The header names the item only: it gives no day, tonight is not tomorrow, and a heading that is no course name
        # (班主任通知：) stays in its clause as before.
        self.assertEqual(meaning('体育：带跳绳。'), 'deadline')
        self.assertNotEqual(meaning('英语：明天英语课带《单词听写本》，不用在家练习。', day), 'arranged')
        self.assertEqual(family_agenda._day_clauses('英语：明天英语课带《单词听写本》，不用在家练习。', '2026-11-05', day), ['明天英语课带《_____》'])
        self.assertEqual(family_agenda._day_clauses('班主任通知：明天体育课带跳绳。', '2026-11-05', day), ['班主任通知：明天体育课带跳绳'])

    def test_a_header_kept_carrying_through_the_store_is_its_lessons_arranged_day_and_its_guards_stay(self):
        # The real Store → task agenda with the whole original quoted, header kept: the same day and role as without it.
        for text, expected in (('体育：周四体育课带一条短绳，无需居家练习。', ('todo', '2026-11-05', 'arranged', '')),
                               ('周四体育课带一条短绳，无需居家练习。', ('todo', '2026-11-05', 'arranged', '')),
                               ('英语：明天英语课带《单词听写本》，不用在家练习。', ('todo', '2026-11-05', 'arranged', '')),
                               ('体育：11月5日前带一条短绳。', ('todo', '2026-11-05', 'deadline', '')),
                               ('体育：明天准备好一条短绳。', ('todo', '2026-11-05', 'deadline', ''))):
            with self.subTest(text=text):
                self.setUp()
                self.check_one(text, 'admin', '', expected)

    def test_a_timed_preparation_at_home_through_the_store_is_its_own_deadline_and_its_guards_stay(self):
        # Root's removed case (4623c0cf): 体育：明天准备好一条短绳。 quoted whole, ready/admin, 11-05, became review/pending with
        # school_unadopted_due because 准备好 tied no day. Its own predicate now ties the day as 带 does: a deadline prepared at
        # home, never the lesson's arrangement or check, no guessed completion or submission; with or without its own course
        # label, a qualified weekday, an explicit date or a bound before the lesson.
        for text, due in (('体育：明天准备好一条短绳。', '2026-11-05'), ('明天准备好一条短绳。', '2026-11-05'),
                          ('体育：下周一准备好一条短绳。', '2026-11-09'), ('下周一准备好一条短绳。', '2026-11-09'),
                          ('体育：11月5日准备好一条短绳。', '2026-11-05'), ('11月5日准备好一条短绳。', '2026-11-05'),
                          ('体育：明天体育课前准备好一条短绳。', '2026-11-05'), ('明天体育课准备好一条短绳。', '2026-11-05')):
            with self.subTest(text=text):
                self.setUp()
                row, brief, agenda = self.run_one(text, 'admin', '', due, FOLLOWUP)
                self.assertEqual((row['state'], row['due'], brief['state'], brief['purpose'], brief.get('submission', '')),
                                 ('accepted', due, 'ready', 'admin', ''))
                self.assertNotIn('school_unadopted_due', json.loads(row['plan']))
                self.assertEqual((agenda['category'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                                 ('todo', due, 'deadline', ''))
        # A negated, optional, conditional or undated preparation ties no day: the model's day stays unadopted for review,
        # never accepted, and an unknown is never read as accepted.
        for text in ('体育：明天不用准备好一条短绳。', '体育：明天无需准备好一条短绳。', '体育：明天可以准备一条短绳。',
                     '体育：明天如果下雨就准备好雨伞。', '体育：准备好一条短绳。'):
            with self.subTest(text=text):
                self.setUp()
                row = self.unadopted(text, '2026-11-05')
                self.assertEqual((row['state'], row['due'], row['task_id']), ('pending', '', ''))

    def unadopted(self, text, due):
        self.fixture.source.update(SOURCE);self.fixture.config()
        self.fixture.now = self.now = dt.datetime.fromisoformat(FOLLOWUP).replace(tzinfo=agent.TZ) + dt.timedelta(minutes=30)
        payload = self.fixture.payload(cursor='1')
        payload['messages'] = [dict(id='1', time=FOLLOWUP, kind='text', sender='虚构老师', text=text, unread=False,
                                    sender_id='qa-teacher-date-role', message_order='1')]
        self.store.ingest(payload)
        proposal = dict(title_quote=text, focus='school', due=due, evidence=[{'ref': 'message:%s:1' % SOURCE['id']}],
                        learning_subject='', learning_goal_id='', task_title=text[:16], task_goal=text, task_advice='',
                        task_change='new', task_target_id='', task_state='ready', task_reason='纯虚构固定回复，不是模型产物。',
                        task_purpose='admin', task_submission='')
        self.model.side_effect = lambda *args, **kwargs:dict(proposals=[copy.deepcopy(proposal)])
        self.assertEqual(agent.run_once(self.app, self.now)['failed'], 0)
        with self.store._db() as c:
            row, = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
        plan = json.loads(row['plan'])
        self.assertEqual((plan['school_task']['state'], plan.get('school_unadopted_due')), ('review', due))
        return row

    def test_a_preparation_predicate_reads_its_own_day_and_names_negations_or_options_tie_none(self):
        day = '2026-11-04'
        for text, days in (('体育：明天准备好一条短绳。', {'2026-11-05'}), ('周四请家长准备齐三支彩笔。', {'2026-11-05'}),
                           ('明天准备两支彩笔。', {'2026-11-05'}), ('体育：下周一准备好一条短绳。', {'2026-11-09'}),
                           ('体育：11月5日准备好一条短绳。', {'2026-11-05'})):
            with self.subTest(text=text):
                self.assertEqual(family_agenda.deadlines(text, day), days)
                self.assertEqual(family_agenda.date_meaning(text, min(days), day), 'deadline')
        # No predicate (a name, a state, a question, a title), a negation, an option, a condition or no day ties nothing.
        for text in ('明天不用准备好一条短绳。', '明天无需准备好一条短绳。', '明天不需要准备好一条短绳。', '明天可以准备一条短绳。',
                     '明天自愿准备好一条短绳。', '明天建议准备好一条短绳。', '明天如果下雨就准备好雨伞。', '明天是否准备好一条短绳？',
                     '明天准备好了吗？', '明天体育课先做准备活动。', '明天准备一下。', '准备好一条短绳。', '明天的《准备好一条短绳》读本。'):
            with self.subTest(text=text):self.assertEqual(family_agenda.deadlines(text, day), set())
        # Carrying, a check and a handback keep their own roles beside the new predicate; a prepared thing handed in is a handback.
        meaning = lambda text:family_agenda.date_meaning(text, '2026-11-05', day)
        self.assertEqual(meaning('明天体育课带一条短绳。'), 'arranged')
        self.assertEqual(meaning('明天英语课听写。'), 'inspection')
        self.assertEqual(meaning('明天交准备好的短绳。'), 'handback')
        # Another item's day in the same notice is never this undated preparation's own.
        whole = '数学：明天交练习册。体育：准备好一条短绳。'
        self.assertTrue(agent._school_borrowed_day('体育：准备好一条短绳。', [dict(text=whole, time=FOLLOWUP)], '2026-11-05'))

    def prepared(self, text, title, due, proposals=None):
        """One original through the real Store → task agenda with a fixed correct reply, then a fresh Store reopen."""
        self.fixture.source.update(SOURCE);self.fixture.config()
        self.fixture.now = self.now = dt.datetime.fromisoformat(FOLLOWUP).replace(tzinfo=agent.TZ) + dt.timedelta(minutes=30)
        payload = self.fixture.payload(cursor='1')
        payload['messages'] = [dict(id='1', time=FOLLOWUP, kind='text', sender='虚构老师', text=text, unread=False,
                                    sender_id='qa-teacher-date-role', message_order='1')]
        self.store.ingest(payload);calls = []
        reply = proposals or [(text, title, due, 'admin')]
        def model(*args, **kwargs):
            calls.append(1)
            return dict(proposals=[dict(title_quote=q, focus='school', due=d, evidence=[{'ref': 'message:%s:1' % SOURCE['id']}],
                                        learning_subject='科学' if p == 'learning' else '', learning_goal_id='', task_title=t,
                                        task_goal=q, task_advice='', task_change='new', task_target_id='', task_state='ready', task_purpose=p,
                                        task_reason='纯虚构固定回复，不是模型产物。', task_submission='') for q, t, d, p in reply])
        self.model.side_effect = model
        self.assertEqual(agent.run_once(self.app, self.now)['failed'], 0)
        def saved():
            with self.store._db() as c:
                rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY rowid")]
            with self.app.connect() as c:
                tasks = {t['id']:t['agenda'] for t in self.app.tasks(c)}
            return rows, {r['id']:tasks.get(r['task_id']) for r in rows}
        rows, agendas = saved()
        agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
        again = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
        self.assertEqual((len(calls), again['processed']), (1, 0))
        self.assertEqual(saved(), (rows, agendas), 'reopened unchanged')
        return [(r, json.loads(r['plan'])['school_task'], agendas[r['id']]) for r in rows]

    def test_a_thing_prepared_tonight_then_carried_bare_is_one_items_completion_and_arranged_day_through_the_store(self):
        # Root's P04: 今晚准备好 one counted or named thing, 明天…课带去 the same thing: complete tonight, arranged on the lesson
        # day, todo/admin, the quoted original kept whole, no guessed submission; reopened unchanged.
        for text, title, subjects in (('科学：今晚准备好两张实验观察表，明天科学课带去。', '科学：准备并携带观察表', ['科学']),
                                      ('今晚请家长准备好一条短绳，明天体育课带去。', '体育：准备并携带短绳', ['体育']),
                                      ('英语：今晚准备好《单词听写本》，明天英语课带去。', '英语：准备并携带单词听写本', ['英语'])):
            with self.subTest(text=text):
                self.setUp()
                (row, brief, agenda), = self.prepared(text, title, '2026-11-05')
                self.assertEqual((row['state'], row['due'], brief['state'], brief['purpose'], brief.get('submission', '')),
                                 ('accepted', '2026-11-05', 'ready', 'admin', ''))
                self.assertEqual(json.loads(row['plan'])['school_date_quote'], text)
                self.assertEqual((agenda['category'], agenda['subjects'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                                 ('todo', subjects, '2026-11-05', 'arranged', '2026-11-04'))
        # Another object carried, a second thing, a conditional preparation, a handback instead of carrying or a third role
        # day: no link between the two days, so the two-date guard stays review and nothing is accepted.
        for text in ('科学：今晚准备好两张实验观察表，明天科学课带放大镜。', '科学：今晚准备好观察表和放大镜，明天科学课带去。',
                     '科学：如果有条件，今晚准备好两张观察表，明天科学课带去。', '科学：今晚准备好两张观察表，明天交给老师。',
                     '科学：今晚准备好两张实验观察表，明天科学课带去，后天交回。'):
            with self.subTest(text=text):
                self.setUp()
                (row, brief, agenda), = self.prepared(text, '科学：准备并携带观察表', '2026-11-05')
                self.assertEqual((row['state'], row['task_id'], brief['state'], agenda), ('pending', '', 'review', None))
        # A negated or optional preparation ties no day of its own: the one carrying day stays its plain deadline as before,
        # never the lesson's arrangement after a completion tonight.
        for text in ('科学：今晚不用准备观察表，明天科学课带去。', '科学：今晚可以准备好两张观察表，明天科学课带去。'):
            with self.subTest(text=text):
                self.setUp()
                (row, brief, agenda), = self.prepared(text, '科学：准备并携带观察表', '2026-11-05')
                self.assertEqual((agenda['due_on'], agenda['due_kind'], agenda['complete_on']), ('2026-11-05', 'deadline', ''))
        # The pair is read only inside one sentence of the item's own words; the plain readers keep every other reading.
        day = '2026-11-04'
        self.assertEqual(family_agenda.prepared_carry('科学：今晚准备好两张实验观察表，明天科学课带去', day), (0, 1))
        for text in ('科学：今晚完成练习册第3页，明天科学课带去', '科学：明天准备好两张观察表，明天科学课带去', '明天科学课带去',
                     '科学：今晚准备好两张观察表，明天科学课带跳绳', '今晚老师准备好两张观察表，明天科学课带去'):
            with self.subTest(text=text):self.assertIsNone(family_agenda.prepared_carry(text, day))
        self.assertEqual(family_agenda.date_meaning('明天科学课带去。', '2026-11-05', day), 'deadline')

    def test_a_separate_tonight_exercise_stays_its_own_item_beside_a_prepared_then_carried_thing(self):
        # The selection's own phase reader with each quote's sibling: the exercise keeps only its own tonight, the prepared
        # thing its tonight completion and its carrying day; neither range reaches the other, and a quote holding both
        # sentences is shared once another proposal quotes the exercise.
        text = '科学：今晚完成练习册第5页。今晚准备好两张实验观察表，明天科学课带去。'
        cited = [dict(text=text, time=FOLLOWUP)]
        exercise, carry = '科学：今晚完成练习册第5页。', '今晚准备好两张实验观察表，明天科学课带去。'
        self.assertIsNone(agent._school_role_days(exercise, cited, [carry]))
        self.assertEqual(agent._school_own_clause_dates(exercise, cited, [carry]), {'2026-11-04'})
        self.assertEqual(agent._school_role_days(carry, cited, [exercise]), ({'2026-11-04'}, '2026-11-05'))
        self.assertIsNone(agent._school_role_days(text, cited, [exercise]))
        self.assertEqual(family_agenda.date_meaning(carry, '2026-11-05', '2026-11-04'), 'arranged')
        self.assertEqual(family_agenda.date_meaning(exercise, '2026-11-04', '2026-11-04'), 'deadline')

    def test_a_named_thing_after_the_preparation_predicate_is_an_object_and_real_learning_stays_guarded(self):
        # Root's P03: the 《》 name prepared by 准备好 names the thing (its 听写 is no practice); the summary may repeat it after
        # the same predicate. Learning outside the name, an inverse and an unproven predicate stay review.
        (row, brief, agenda), = self.prepared('英语：明天准备好《单词听写本》，不用在家练习。', '英语：准备好单词听写本', '2026-11-05')
        self.assertEqual((row['state'], brief['state'], brief['purpose']), ('accepted', 'ready', 'admin'))
        self.assertEqual((agenda['category'], agenda['subjects'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                         ('todo', ['英语'], '2026-11-05', 'deadline', ''))
        learning = lambda title, goal:bool(agent._LEARNING_ACTIVITY.search(t:=agent._school_learning_text([title, goal], [goal]))
                                           or agent._LEARNING_ACTION.search(t))
        self.assertFalse(learning('英语：准备两本单词听写本', '英语：明天准备两本《单词听写本》。'))
        self.assertFalse(learning('英语：携带单词听写本', '英语：明天带《单词听写本》，不用在家练习。'))
        for title, goal in (('英语：准备好单词听写本', '英语：明天准备好《单词听写本》，今晚在家听写10个单词。'),
                            ('英语：准备好单词听写本', '英语：明天准备好《单词听写本》，并非不用练习。'),
                            ('英语：准备单词听写本', '英语：明天准备《单词听写本》。'),
                            ('英语：准备好单词听写本', '英语：明天准备好单词听写本。')):
            with self.subTest(goal=goal):self.assertTrue(learning(title, goal))

    P05 = '英语：今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备好《单词听写本》，明天英语课带去。'
    P05_READ = ('今晚跟读Unit 8第1至4个单词，每词2遍', '英语：跟读Unit 8第1至4个单词', '2026-11-04', 'learning', '英语')
    P05_PREPARE = ('今晚准备好《单词听写本》，明天英语课带去', '英语：准备好并携带单词听写本', '2026-11-05', 'admin', '')

    def listed(self, text, reply):
        """One original and a fixed reply of (quote, title, due, purpose, subject) through the real Store, its saved facts and list."""
        self.fixture.source.update(SOURCE);self.fixture.config()
        self.fixture.now = self.now = dt.datetime.fromisoformat(FOLLOWUP).replace(tzinfo=agent.TZ) + dt.timedelta(hours=1)
        payload = self.fixture.payload(cursor='1')
        payload['messages'] = [dict(id='1', time=FOLLOWUP, kind='text', sender='虚构老师', text=text, unread=False,
                                    sender_id='qa-teacher-date-role', message_order='1')]
        self.store.ingest(payload);calls = [];ref = 'message:%s:1' % SOURCE['id']
        def model(*args, **kwargs):
            calls.append(1)
            return dict(proposals=[dict(title_quote=q, focus='school', due=d, evidence=[{'ref': ref}], learning_subject=s,
                                        learning_goal_id='', task_title=t, task_goal=g, task_advice='', task_change='new',
                                        task_target_id='', task_state='ready', task_purpose=p, task_submission='',
                                        task_reason='纯虚构固定回复，不是模型产物。') for q, t, d, p, s, *goal in reply for g in [goal[0] if goal else q]])
        self.model.side_effect = model
        result = agent.run_once(self.app, self.now)
        def saved():
            with self.store._db() as c:
                facts = {n:[dict(r) for r in c.execute('SELECT * FROM ' + n + ' ORDER BY rowid')]
                         for n in ('agent_messages', 'agent_items', 'manual_tasks', 'records', 'task_updates', 'agent_jobs')}
            listing = [r for r in self.app.calendar_snapshot('2026-11-04', '2026-11-11')['inbox'] if r['kind'] in ('task', 'school')]
            return facts, listing
        facts, listing = saved()
        self.assertEqual([json.loads(r['payload']) for r in facts['agent_messages']], payload['messages'], 'original unchanged')
        return result, calls, facts, listing, saved, ref

    def test_root_p05_tonight_reading_and_a_prepared_then_carried_notebook_are_two_items_through_the_store_and_reopen(self):
        # Root's frozen P05: one teacher original with a standalone reading and a material preparation. The prepared 《》 name is
        # a thing no outcome writes (its 单词 is no word of 跟读…单词), so it is its own administrative outcome, never a step of the
        # reading; each correct own-quote proposal binds once, both list, and a fresh Store reopen adds no call or write.
        for text, read, prepare, subject in (
                (self.P05, self.P05_READ, self.P05_PREPARE, '英语'),
                # Analogous, not literal: another subject, exercise, asker, counted thing and lesson.
                ('数学：今晚完成练习册第12页；今晚请家长准备好一把直尺，明天数学课带去。',
                 ('今晚完成练习册第12页', '数学：完成练习册第12页', '2026-11-04', 'learning', '数学'),
                 ('今晚请家长准备好一把直尺，明天数学课带去', '数学：准备好并携带直尺', '2026-11-05', 'admin', ''), '数学')):
            with self.subTest(text=text):
                self.setUp()
                result, calls, facts, listing, saved, ref = self.listed(text, [read, prepare])
                self.assertEqual((result['failed'], result['processed'], len(calls)), (0, 1, 1))
                items = [r for r in facts['agent_items'] if r['kind'] == 'school']
                self.assertEqual(len(items), 2)
                with self.app.connect() as c:
                    tasks = {t['id']:t for t in self.app.tasks(c)}
                by_quote = {}
                for row in items:
                    plan = json.loads(row['plan']);brief = plan['school_task']
                    self.assertEqual((row['state'], brief['state']), ('accepted', 'ready'))
                    self.assertEqual({e['ref'] for e in json.loads(row['evidence'])}, {ref})
                    self.assertEqual(set(brief.get('origin_basis', {})), {ref})
                    by_quote[plan['school_native_action']['quote']] = (row, brief, tasks[row['task_id']]['agenda'])
                self.assertEqual(set(by_quote), {read[0], prepare[0]}, 'each owns its quote, nothing duplicated or missing')
                self.assertEqual(sorted(r['id'] for r in listing), sorted(r['task_id'] for r in items))
                row, brief, agenda = by_quote[read[0]]
                self.assertEqual((brief['purpose'], agenda['category'], agenda['subjects']), ('learning', 'homework', [subject]))
                self.assertTrue(agenda['complete_on'] == '2026-11-04' or (agenda['due_on'], agenda['due_kind']) == ('2026-11-04', 'deadline'))
                self.assertIn(agenda['due_on'], ('', '2026-11-04'))
                self.assertNotIn('准备', tasks[row['task_id']]['action'])
                row, brief, agenda = by_quote[prepare[0]]
                self.assertEqual((brief['purpose'], brief.get('submission', ''), row['due']), ('admin', '', '2026-11-05'))
                self.assertEqual((agenda['category'], agenda['subjects'], agenda['due_on'], agenda['due_kind'], agenda['complete_on']),
                                 ('todo', [subject], '2026-11-05', 'arranged', '2026-11-04'))
                self.assertNotIn(read[0], tasks[row['task_id']]['action'])
                agent.Store(self.app.connect, self.app.profiles, self.app.DATA, app=self.app)
                again = agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
                self.assertEqual((len(calls), again['processed']), (1, 0))
                self.assertEqual(saved()[:2], (facts, listing), 'reopened unchanged')

    def test_root_p05_duplicate_merged_or_missing_requirements_still_hold_the_whole_batch(self):
        # The two outcomes are each still required exactly once: a second proposal on either own quote, one quote or goal
        # merging the reading into tomorrow's carrying, or a reply leaving either out keeps the whole batch, the original
        # untouched and no item written.
        merged = '今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备好《单词听写本》，明天英语课带去'
        for reply, error in (([self.P05_READ, self.P05_READ, self.P05_PREPARE], '学校独立要求重复或合并'),
                             ([self.P05_READ, self.P05_PREPARE, self.P05_PREPARE], '学校独立要求重复或合并'),
                             ([(merged, '英语：跟读并准备单词听写本', '2026-11-05', 'learning', '英语')], '学校已定位要求未逐项归纳'),
                             ([self.P05_READ, (*self.P05_PREPARE, merged)], '不同学校成果被合并'),
                             ([self.P05_READ], '学校独立要求有遗漏'),
                             ([self.P05_PREPARE], '学校独立要求有遗漏')):
            with self.subTest(reply=[r[0] for r in reply]):
                self.setUp()
                result, calls, facts, listing, saved, ref = self.listed(self.P05, reply)
                self.assertEqual((result['failed'], result['processed'], result['created'], len(calls)), (1, 0, 0, 1))
                self.assertEqual([r for r in facts['agent_items'] if r['kind'] == 'school'], [])
                self.assertEqual((facts['manual_tasks'], listing), ([], []))
                job, = [j for j in facts['agent_jobs'] if j['id'].startswith('messages:')]
                self.assertEqual((job['attempts'], job['done']), (1, 0))
                self.assertIn(error, job['error'])
                self.assertEqual(facts['agent_messages'][0]['processed'], 0)

    def test_a_prepared_thing_an_outcome_already_writes_or_an_unproven_preparation_stays_with_that_outcome(self):
        # The same ledger: preparing the exercise's own workbook, a word-card sharing the reading's own words, a bare 准备 of a
        # name or no thing at all is no errand of its own; independent homework actions beside a preparation each stay separate.
        quotes = lambda text:[a['quote'] for a in agent._school_native_blocks(text)]
        self.assertEqual(quotes(self.P05), [self.P05_READ[0], self.P05_PREPARE[0]])
        self.assertEqual(quotes('英语：今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备好《单词听写本》，明天英语课带去；今晚抄写Unit 8单词各3遍。'),
                         [self.P05_READ[0], self.P05_PREPARE[0], '今晚抄写Unit 8单词各3遍'])
        self.assertEqual([a['purpose'] for a in agent._school_native_blocks(self.P05)], ['learning', 'admin'])
        for text in ('英语：今晚完成练习册第5页；今晚准备好练习册，明天英语课带去。',
                     '英语：今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备好单词卡，明天英语课带去。',
                     '英语：今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备《单词听写本》，明天英语课带去。',
                     '英语：今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备好，明天英语课带去。',
                     '英语：今晚跟读Unit 8第1至4个单词，每词2遍；今晚准备活动材料。'):
            with self.subTest(text=text):self.assertEqual(len(agent._school_native_blocks(text)), 1)


if __name__ == '__main__':
    unittest.main()

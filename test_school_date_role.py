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


if __name__ == '__main__':
    unittest.main()

"""Frozen fictional daily-list acceptance (验收-每日清单.md T01–T10); no household data, collectors, devices or printing.

Original texts, send times and expectations are copied from the frozen contract and are independent of any reply.
The model seam returns fixed fictional receipts: a pass proves only the real run_once→Store→calendar API→single-child
list path (validation, save, dates, display data), never the product model's own extraction quality, which stays unmeasured.
Set DAILY_LIST_REPORT to a file path to record each case's actual list view for the difference report.
"""
import datetime as dt
import hashlib
import json
import os
import unittest
from pathlib import Path

import family_agenda
import family_agent as agent
import test_agent as fixtures
import test_school_native_coverage as native


T06_TEXT = '附件是明天带去课堂的实验观察表，今晚不填。'  # 科学老师18:40 in 验收-每日清单.md; its attachment is not read here

# Root's one paid product-model call (development run daily-pointer-completion-20261028): the six fictional originals frozen
# before it, the fictional family rules it ran under and the selection it returned, kept byte for byte (no new call).
PRODUCT_SIX = (('18:00', '虚构语文老师', 'qa-cn-teacher', '语文今晚朗读《荷塘》2遍。'),
               ('18:02', '虚构语文老师', 'qa-cn-teacher', '刚才的朗读完成后还要请家长签字。'),
               ('18:05', '虚构数学老师', 'qa-math-teacher', '数学今晚完成《口算卡》第1题。'),
               ('18:06', '虚构数学老师', 'qa-math-teacher', '数学今晚完成《方格练习册》第3页第2题。'),
               ('18:10', '虚构老师乙', 'qa-mixed-teacher', '今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练。'),
               ('18:20', '虚构班主任', 'qa-head-teacher', '《活动回执》今晚请家长签字，孩子明天早上交给班主任。'))
PRODUCT_SIX_FAMILY = '| child-1 | 虚构甲 | — | 10岁 | 四年级 |\n| child-2 | 虚构乙 | — | 13岁 | 初一 |\n'
# Its truth.json outcomes: (subject, category, anchors, originals, requirements, forbidden words, completion day, (due day,
# due role) or None for tonight's homework, whose day may stand as its plain deadline but never a handback, check or arranged day).
PRODUCT_SIX_TRUTH = (
    ('语文', 'homework', ('荷塘', '朗读'), (0, 1), (r'(?:2|两)遍', r'家长.{0,12}签字', r'(?:朗读|读完|完成).{0,18}(?:后|完).{0,18}家长.{0,12}签字'),
     ('交给', '交回', '课代表', '拍照', '上传', '跳绳'), '2026-11-04', None),
    ('数学', 'homework', ('口算卡',), (2,), (r'第?1题',), ('方格练习册', '家长', '签字', '课代表', '交回', '跳绳'), '2026-11-04', None),
    ('数学', 'homework', ('方格练习册',), (3,), (r'第?3页', r'第?2题'), ('口算卡', '家长', '签字', '课代表', '交回', '跳绳'), '2026-11-04', None),
    ('英语', 'homework', ('Unit 5', '跟读'), (4,), (r'(?:2|两)遍',), ('跳绳', '家长', '签字', '回执', '交回'), '2026-11-04', None),
    ('体育', 'todo', ('跳绳',), (4,), (r'体育课.{0,12}带.{0,8}跳绳', '不要求在家训练'), ('Unit 5', '签字', '回执'), '', ('2026-11-05', 'arranged')),
    ('', 'todo', ('活动回执',), (5,), (r'家长.{0,12}签字', r'孩子.{0,25}(?:交给|交回|交到).{0,12}班主任', r'(?:明天早上|明早|11月5日早上|2026-11-05.{0,4}早上)'),
     ('荷塘', 'Unit 5', '跳绳', '口算卡', '方格练习册'), '2026-11-04', ('2026-11-05', 'handback')))
PRODUCT_SIX_REPLY = r'''{
  "proposals": [
    {
      "title_quote": "语文今晚朗读《荷塘》2遍。",
      "focus": "school",
      "due": "",
      "evidence": [
        {
          "ref": "message:synthetic-group:11"
        },
        {
          "ref": "message:synthetic-group:12"
        }
      ],
      "task_title": "语文：朗读《荷塘》2遍并请家长签字",
      "task_goal": "今晚朗读《荷塘》2遍。\n朗读完成后请家长签字。",
      "task_advice": "可先通读一遍熟悉内容，再完整朗读第二遍；读完后请家长签字确认。",
      "learning_subject": "语文",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求今晚朗读《荷塘》2遍，并由家长在完成后签字，属于具体学习任务。",
      "task_purpose": "learning",
      "task_submission": "朗读完成后请家长签字。"
    },
    {
      "title_quote": "数学今晚完成《口算卡》第1题。",
      "focus": "school",
      "due": "",
      "evidence": [
        {
          "ref": "message:synthetic-group:13"
        }
      ],
      "task_title": "数学：完成《口算卡》第1题",
      "task_goal": "今晚完成《口算卡》第1题。",
      "task_advice": "可先看清题目要求再作答，完成后自行检查一遍。",
      "learning_subject": "数学",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求今晚完成《口算卡》第1题，属于具体数学练习。",
      "task_purpose": "learning",
      "task_submission": ""
    },
    {
      "title_quote": "数学今晚完成《方格练习册》第3页第2题。",
      "focus": "school",
      "due": "",
      "evidence": [
        {
          "ref": "message:synthetic-group:14"
        }
      ],
      "task_title": "数学：完成《方格练习册》第3页第2题",
      "task_goal": "今晚完成《方格练习册》第3页第2题。",
      "task_advice": "可先读题再在方格练习册上作答，完成后检查书写和答案。",
      "learning_subject": "数学",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求今晚完成《方格练习册》第3页第2题，属于具体数学练习。",
      "task_purpose": "learning",
      "task_submission": ""
    },
    {
      "title_quote": "今晚跟读Unit 5两遍",
      "focus": "school",
      "due": "",
      "evidence": [
        {
          "ref": "message:synthetic-group:15"
        }
      ],
      "task_title": "英语：跟读Unit 5两遍",
      "task_goal": "今晚跟读Unit 5两遍。",
      "task_advice": "可跟着音频或录音逐句跟读，完成两遍后确认已读完整。",
      "learning_subject": "英语",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求今晚跟读Unit 5两遍，属于具体英语学习任务。",
      "task_purpose": "learning",
      "task_submission": ""
    },
    {
      "title_quote": "另外，明天体育课带跳绳，不要求在家训练",
      "focus": "school",
      "due": "2026-11-05",
      "evidence": [
        {
          "ref": "message:synthetic-group:15"
        }
      ],
      "task_title": "体育：明天体育课带跳绳",
      "task_goal": "明天体育课带跳绳。\n不要求在家训练。",
      "task_advice": "今晚可把跳绳放进书包，避免明天忘带。",
      "learning_subject": "",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求明天体育课带跳绳，并说明不要求在家训练，属于需携带物品的行政事项。",
      "task_purpose": "admin",
      "task_submission": ""
    },
    {
      "title_quote": "《活动回执》今晚请家长签字，孩子明天早上交给班主任。",
      "focus": "school",
      "due": "2026-11-05",
      "evidence": [
        {
          "ref": "message:synthetic-group:16"
        }
      ],
      "task_title": "活动回执：家长签字后明早交班主任",
      "task_goal": "《活动回执》今晚请家长签字。\n孩子明天早上交给班主任。",
      "task_advice": "签字后可将回执放入书包固定位置，明早到校后交给班主任。",
      "learning_subject": "",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求家长今晚签字，孩子明天早上交给班主任，属于需办理并交回表单的行政事项。",
      "task_purpose": "admin",
      "task_submission": "孩子明天早上交给班主任。"
    }
  ]
}
'''

# Root's actual product reply for the next four fictional originals (development run late-admin-date-20261028): their
# truth froze before the call and the reply is replayed byte for byte here (no new call).
NEXT_FOUR = (('18:30', '虚构数学老师', 'qa-math', '今晚完成第4题，明早交给数学课代表。'),
             ('18:45', '虚构班主任', 'qa-head', '请家长签署同意书后交回。'),
             ('19:00', '虚构英语老师', 'qa-en', '今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写；明天英语课听写。'),
             ('19:05', '虚构班主任', 'qa-head', '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。'))
# Each outcome by its own title anchor: its original, completion day and (due day, due role); a None role is tonight's
# homework, whose day may stand as its plain deadline but never a handback, check or arranged day.
NEXT_FOUR_TRUTH = {'第4题': (0, '2026-11-04', ('2026-11-05', 'handback')), '同意书': (1, '', ('', '')),
                   '跟读': (2, '2026-11-04', None), '听写': (2, '', ('2026-11-05', None)),
                   '研学活动回执': (3, '2026-11-04', ('2026-11-05', 'handback'))}
NEXT_FOUR_REPLY = r'''{
  "proposals": [
    {
      "title_quote": "今晚完成第4题，明早交给数学课代表",
      "focus": "school",
      "due": "2026-11-05",
      "evidence": [
        {
          "ref": "message:synthetic-group:11"
        }
      ],
      "task_title": "数学：完成第4题并明早交",
      "task_goal": "今晚完成第4题；明早交给数学课代表。",
      "task_advice": "可先独立完成第4题，再检查一遍书写和答案后装好，明早交给数学课代表。",
      "learning_subject": "数学",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求今晚完成第4题，明早交给数学课代表，属具体数学作业。",
      "task_purpose": "learning",
      "task_submission": "明早交给数学课代表"
    },
    {
      "title_quote": "请家长签署同意书后交回",
      "focus": "school",
      "due": "",
      "evidence": [
        {
          "ref": "message:synthetic-group:12"
        }
      ],
      "task_title": "签署同意书并交回",
      "task_goal": "请家长签署同意书后交回。",
      "task_advice": "可先确认同意书内容，再由家长签署并按要求交回。",
      "learning_subject": "",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求家长签署同意书后交回，属需办理的行政事务；未写明具体交回日期。",
      "task_purpose": "admin",
      "task_submission": "交回同意书"
    },
    {
      "title_quote": "今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写",
      "focus": "school",
      "due": "",
      "evidence": [
        {
          "ref": "message:synthetic-group:13"
        }
      ],
      "task_title": "英语：跟读Unit 5第1至8个单词",
      "task_goal": "今晚听音频跟读Unit 5第1至8个单词，每个两遍；不用抄写。",
      "task_advice": "可跟音频逐词朗读，每个单词读两遍，读完后可再听一遍确认发音。",
      "learning_subject": "英语",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写，属具体英语学习任务。",
      "task_purpose": "learning",
      "task_submission": ""
    },
    {
      "title_quote": "明天英语课听写",
      "focus": "school",
      "due": "2026-11-05",
      "evidence": [
        {
          "ref": "message:synthetic-group:13"
        }
      ],
      "task_title": "英语：明天课堂听写",
      "task_goal": "明天英语课听写。",
      "task_advice": "可在今晚跟读后自行回顾Unit 5第1至8个单词的读音和拼写，为明天课堂听写做准备。",
      "learning_subject": "英语",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确说明明天英语课听写，属需单独保留的考试/听写安排。",
      "task_purpose": "learning",
      "task_submission": ""
    },
    {
      "title_quote": "今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任",
      "focus": "school",
      "due": "2026-11-05",
      "evidence": [
        {
          "ref": "message:synthetic-group:14"
        }
      ],
      "task_title": "研学活动回执勾选签字并明早交",
      "task_goal": "今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。",
      "task_advice": "可先由家长确认参加或不参加并勾选，再签字，孩子明早带回交给班主任。",
      "learning_subject": "",
      "learning_goal_id": "",
      "task_change": "new",
      "task_target_id": "",
      "task_state": "ready",
      "task_reason": "已读文字明确要求家长在《研学活动回执》勾选并签字，孩子明早交给班主任，属需办理的行政事务。",
      "task_purpose": "admin",
      "task_submission": "孩子明早交给班主任"
    }
  ]
}
'''


def view(item):
    m = item['agenda']
    return dict(kind=item['kind'], title=item['title'], status=item['status'], category=m['category'],
                published_at=m.get('published_at', ''), complete_on=m.get('complete_on', ''), due_on=m['due_on'],
                due_kind=m.get('due_kind', ''), scheduled_on=m['scheduled_on'], body=item['body'],
                publications=[p['ref'] for p in m.get('publications', [])])


class DailyListFrozenTests(unittest.TestCase):
    _use_replies = native.SchoolNativeCoverageTests._use_replies

    def setUp(self):
        native.SchoolNativeCoverageTests.setUp(self)
        self.fixture.now = self.now = dt.datetime(2026, 11, 4, 20, tzinfo=agent.TZ)

    def _day(self, messages, day='2026-11-04'):
        """messages: (HH:MM, sender, publisher id, frozen text) sent on the contract's day in Asia/Shanghai."""
        payload = self.fixture.payload(cursor=str(10 + len(messages)))
        payload['messages'] = [dict(id=str(11 + i), message_order=str(11 + i), time=day + 'T' + hm + ':00+08:00', kind='text',
                                    sender=sender, sender_id=publisher, text=text, unread=False)
                               for i, (hm, sender, publisher, text) in enumerate(messages)]
        self.store.ingest(payload)
        return payload, ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]

    def _proposal(self, quote, refs, subject, goal, due='', purpose='learning', submission=''):
        return fixtures.school_proposal(
            title_quote=quote, due=due, evidence=[dict(ref=r) for r in refs], learning_subject=subject,
            task_title=(subject + '：' if subject else '') + quote, task_goal=goal, task_state='ready',
            task_purpose=purpose, task_submission=submission, task_reason='虚构固定回执，只验校验/保存/展示。')

    def test_u02_linked_pdf_requirements_reach_one_task_only_through_the_page_reader(self):
        """U02 with its linked one-page fictional PDF through actual run_once rounds only (no act(accept), no seeded rows).
        Mocked layers, labelled: the selection reply is Root's actual configured-Flash return for this exact request,
        replayed (no new model call); the page reader (test_pdf_material.renderer/page_model) and the school refresh are
        deterministic fake receipts. They prove the state machine, not original-reading accuracy. REQUIREMENT is
        fictional teacher text that exists only in the fake page receipt."""
        import copy, hashlib, io
        from urllib.parse import quote
        import test_pdf, test_pdf_material
        requirement = '连续观察绿豆发芽3天，每天记录芽长（毫米）和子叶颜色，并写一句观察发现。'
        (self.app.ROOT / '家庭运行规则.md').write_text(PRODUCT_SIX_FAMILY)
        self.source.update(id='qq:123456', platform='qq'); self.fixture.config()
        payload, refs = self._day([('18:40', '虚构科学老师', 'qa-science', '请按照附件里的要求完成实验观察表。')])
        raw = test_pdf.build_pdf(1)
        upload = self.app.save_upload(io.BytesIO(raw), len(raw), quote('示例观察表.pdf'))
        keys = dict(child_id='child-1', source_id='qq:123456', message_id='11')
        self.store.message_attachment(dict(keys, attachment_id=upload['id'], action='attach'), self.app.upload_info)
        actual = dict(proposals=[dict(
            title_quote='请按照附件里的要求完成实验观察表。', focus='school', due='', evidence=[dict(ref=refs[0])],
            task_title='科学：完成实验观察表',
            task_goal='按附件《示例观察表.pdf》中的要求完成实验观察表。\n附件内容尚未读取，具体观察项目、填写范围与完成标准未知。',
            task_advice='', learning_subject='', learning_goal_id='', task_change='new', task_target_id='', task_state='review',
            task_reason='正文明确要求完成实验观察表，但具体要求写在未读取的附件中，缺附件内的观察项目、填写范围与完成标准。',
            task_purpose='learning', task_submission='')])
        calls = []

        def model(messages, schema, name, timeout=60, *, data_path=None):
            self.assertEqual(data_path, self.app.DATA)
            context = json.loads(messages[-1]['content']); calls.append((name, context))
            if name == 'family_agent_selection':
                self.assertEqual([(e['ref'], e['text'], e['attachments']) for e in context['evidence']],
                                 [(refs[0], '请按照附件里的要求完成实验观察表。', [dict(mime='application/pdf', name='示例观察表.pdf')])])
                return copy.deepcopy(actual)
            docs = context.get('pdf_material') or []
            read = bool(docs) and all(d['complete'] and not d['omitted_groups'] and not d['truncated_groups'] for d in docs)
            brief = dict(title='科学：完成实验观察表', goal=requirement if read else actual['proposals'][0]['task_goal'], advice='',
                         state='ready' if read else 'review', reason='虚构固定回执：附件页组要求' + ('已整理。' if read else '未读。'),
                         purpose='learning', submission='', change='new', target_id='', learning_subject='科学', learning_goal_id='')
            if 'original_parts' not in context: return brief
            # The same deterministic assignment as test_school_pdf_evidence.refresh: one action per distinct literal requirement.
            parts = context['original_parts']; groups = []
            for part in parts:
                if not part.get('requirement'): continue
                group = next((g for g in groups if g[0]['text'] == part['text']), None)
                if group is None: groups.append([part])
                else: group.append(part)
            for group in groups:
                owned = {p['ref'] for p in group}; seen = {u for p in group for u in p['upload_ids']}
                # The teacher's own message words name the action (完成实验观察表); the page requirement adds its content.
                group[:0] = [p for p in parts if p['ref'] in owned and not p.get('requirement') and not p.get('background_only') and not p['upload_ids']]
                for part in parts:
                    if part.get('background_only') and part['ref'] in owned and part['text'].strip() and not set(part['upload_ids']) <= seen:
                        group.append(part); seen.update(part['upload_ids'])
            return dict(actions=[dict(brief, due='', existing_item_id=context['candidate_id'] if i == 0 else '',
                                      basis=[dict(part=p['id'], text=p['text'] if p.get('requirement') else p['text'][:2000]) for p in g])
                                 for i, g in enumerate(groups)])
        self.model.side_effect = model
        page = dict(originals=[dict(upload_id=upload['id'], title='虚构实验观察表', note='老师写明的观察要求，未见孩子填写。',
                                    uncertainties=[], requirements=[requirement], deferred_contexts=[])])

        def state():
            with self.store._db() as c:
                schools = [dict(x) for x in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
                tasks = [dict(x) for x in c.execute('SELECT * FROM manual_tasks')]
                originals = [json.loads(x[0]) for x in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            return schools, tasks, originals, self.store.message(keys, self.app.upload_info)

        def unchanged(originals, message):
            self.assertEqual(originals, payload['messages'])  # sender, publisher, sent time and text exact
            self.assertEqual([a['id'] for a in message['attachments']], [upload['id']])
            self.assertEqual(hashlib.sha256((self.app.DATA / 'uploads' / upload['id']).read_bytes()).hexdigest(),
                             hashlib.sha256(raw).hexdigest())
        with test_pdf_material.renderer(page_count=1), test_pdf_material.page_model([ValueError('虚构页组读取失败'), page]) as pages:
            first = agent.run_once(self.app, self.now)
            schools, tasks, originals, message = state()
            # Failed reading: the dependent requirement stays unknown and held; nothing is invented or accepted.
            self.assertEqual((first['failed'], len(schools), schools[0]['state'], tasks, pages.call_count), (1, 1, 'pending', [], 1))
            held = json.loads(schools[0]['plan'])['school_task']
            self.assertEqual(held['state'], 'review'); self.assertIn('未知', schools[0]['body']); self.assertNotIn(requirement, schools[0]['body'])
            self.assertEqual((message['pdf_material']['state'], message['pdf_material']['requirements_complete']), ('error', False))
            unchanged(originals, message)
            waited = agent.run_once(self.app, self.now + dt.timedelta(minutes=2))  # inside the existing 5-minute back-off
            self.assertEqual((pages.call_count, state()[1], waited['created']), (1, [], 0))
            agent.run_once(self.app, self.now + dt.timedelta(minutes=6))  # the bounded retry reads the whole page
            schools, tasks, originals, message = state()
            self.assertEqual((pages.call_count, message['pdf_material']['state'], message['pdf_material']['requirements_complete']), (2, 'ready', True))
            agent.run_once(self.app, self.now + dt.timedelta(minutes=7))  # existing automatic refresh and acceptance
            schools, tasks, originals, message = state()
            self.assertEqual(([s['state'] for s in schools], len(tasks)), (['accepted'], 1))
            final = json.loads(schools[0]['plan'])['school_task']
            for text in (tasks[0]['action'], schools[0]['body'], final['goal']):
                self.assertIn(requirement, text)
                self.assertNotEqual(text.strip(), '请按照附件里的要求完成实验观察表。')  # the teacher's words may stay beside the read requirement
                for vague in ('按附件', '未知', '尚未读取'): self.assertNotIn(vague, text)
            self.assertEqual((final['state'], final['auto_added'], schools[0]['task_id'], tasks[0]['id']), ('ready', True, tasks[0]['id'], schools[0]['task_id']))
            self.assertIn(refs[0], tasks[0]['source'])
            unchanged(originals, message)
            names = [n for n, _ in calls]
            accepted = (schools, tasks)
            again = agent.run_once(self.app, self.now + dt.timedelta(minutes=20))  # reopen: no repeat call, write or duplicate
            schools, tasks, originals, message = state()
            self.assertEqual(((schools, tasks), [n for n, _ in calls], pages.call_count, again['created']), (accepted, names, 2, 0))
        self.assertEqual(names[0], 'family_agent_selection'); self.assertEqual(names.count('family_agent_selection'), 1)
        self._report(case='U02_linked_pdf_page_reader_chain', calls=names, page_calls=2, task=tasks[0]['action'], goal=final['goal'], due=schools[0]['due'])

    U02_REQUIREMENT = '连续观察绿豆发芽3天，每天记录芽长（毫米）和子叶颜色，并写一句观察发现。'

    def _u02_variant(self, requirements, cite='all', title='虚构实验观察表', uncertainties=()):
        """The U02 message and its linked one-page fictional PDF; the fake page receipt reads at once. The fake ready
        refresh receipt cites each requirement part alone ('requirement'), beside the teacher's words ('all'), or the
        words alone ('message'). Fake receipts prove the state machine only, not reading accuracy."""
        import copy, io
        from urllib.parse import quote
        import test_pdf, test_pdf_material
        (self.app.ROOT / '家庭运行规则.md').write_text(PRODUCT_SIX_FAMILY)
        self.source.update(id='qq:123456', platform='qq'); self.fixture.config()
        _, refs = self._day([('18:40', '虚构科学老师', 'qa-science', '请按照附件里的要求完成实验观察表。')])
        raw = test_pdf.build_pdf(1)
        upload = self.app.save_upload(io.BytesIO(raw), len(raw), quote('示例观察表.pdf'))
        self.store.message_attachment(dict(child_id='child-1', source_id='qq:123456', message_id='11', attachment_id=upload['id'],
                                           action='attach'), self.app.upload_info)
        review = dict(proposals=[dict(title_quote='请按照附件里的要求完成实验观察表。', focus='school', due='', evidence=[dict(ref=refs[0])],
            task_title='科学：完成实验观察表', task_goal='按附件中的要求完成实验观察表。\n附件内容尚未读取，具体要求未知。', task_advice='',
            learning_subject='', learning_goal_id='', task_change='new', task_target_id='', task_state='review',
            task_reason='具体要求写在未读取的附件中。', task_purpose='learning', task_submission='')])
        contexts = []

        def model(messages, schema, name, timeout=60, *, data_path=None):
            context = json.loads(messages[-1]['content'])
            if name == 'family_agent_selection': return copy.deepcopy(review)
            brief = dict(title='科学：完成实验观察表', goal='完成实验观察表', advice='', state='ready', reason='虚构固定回执。', purpose='learning',
                         submission='', change='new', target_id='', learning_subject='科学', learning_goal_id='')
            if 'original_parts' not in context: return dict(brief, state='review', reason='虚构固定回执：附件未读。')
            contexts.append(context); parts = context['original_parts']
            words = [p for p in parts if not p.get('requirement') and not p.get('background_only') and not p['upload_ids']]
            owned = [p for p in parts if p.get('requirement')]
            groups = [words] if cite == 'message' else [(words if cite == 'all' else []) + [p] for p in owned]
            return dict(actions=[dict(brief, due='', existing_item_id=context['candidate_id'] if i == 0 else '',
                                      basis=[dict(part=p['id'], text=p['text']) for p in g]) for i, g in enumerate(groups)])
        self.model.side_effect = model
        page = dict(originals=[dict(upload_id=upload['id'], title=title, note='老师写明的观察要求，未见孩子填写。',
                                    uncertainties=list(uncertainties), requirements=list(requirements), deferred_contexts=[])])
        with test_pdf_material.renderer(page_count=1), test_pdf_material.page_model([page] * 4):
            for minutes in (0, 1, 8, 20, 40): agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))
        with self.store._db() as c:
            schools = [dict(x) for x in c.execute("SELECT * FROM agent_items WHERE kind='school'")]
            tasks = [dict(x) for x in c.execute('SELECT * FROM manual_tasks')]
        return schools, tasks, contexts

    def _u02_held(self, requirements, reached=True, reason='依据没有本项动作和对象', **kw):
        """Held pending with no task. With the default 'all' receipt the candidate keeps its own words, so only the
        requirement's own structure stands between it and acceptance (the exact positive is accepted)."""
        schools, tasks, contexts = self._u02_variant(requirements, **kw)
        self.assertEqual((bool(contexts), [s['state'] for s in schools], tasks), (reached, ['pending'], []))
        for text in requirements: self.assertNotEqual(schools[0]['body'].strip(), text)
        with self.store._db() as c:
            errors = [r[0] for r in c.execute("SELECT error FROM agent_jobs WHERE id LIKE 'school-task:%' AND error!=''")]
        self.assertEqual(any(reason in e for e in errors) if reason else errors, True if reason else [])
        return schools, contexts

    def test_u02_complete_page_requirement_is_its_own_action_and_only_its_exact_structure_counts(self):
        import copy
        schools, tasks, contexts = self._u02_variant([self.U02_REQUIREMENT])
        self.assertEqual(([s['state'] for s in schools], len(tasks), len(contexts)), (['accepted'], 1, 1))
        for text in (tasks[0]['action'], schools[0]['body']): self.assertIn(self.U02_REQUIREMENT, text)
        with self.store._db() as c:
            pdf = agent._pdf_evidence(agent._school_pdf(self.store, c, schools[0]))
        parts = agent._school_original_parts([], pdf, None); [part] = [p for p in parts if p.get('requirement')]
        own = lambda p=part, q=pdf, m=None: agent._school_own_requirement(p, q, m, '科学')
        partial = copy.deepcopy(pdf); partial['model'][0].update(page_count=2)
        self.assertEqual([own(), own(dict(part, text=part['text'][:-1])), own(dict(part, upload_ids=['0' * 32])),
                          own(dict(part, ref='message:qq:123456:12')), own(dict(part, pages=[2])), own(q=partial),
                          own(q=dict(pdf, uncertainties=['表格第二栏模糊'])), own(q=dict(pdf, requirements_complete=False)),
                          own(m=dict(uncertainties=['图片待核'])), own(q=None)],
                         [True] + [False] * 9)
        for p in parts:
            if not p.get('requirement'): self.assertFalse(own(p))

    def test_u02_page_requirement_that_is_only_a_date_gains_nothing(self):
        self._u02_held(['2026年11月6日前'])

    def test_u02_page_requirement_that_is_only_a_weekday_deadline_gains_nothing(self):
        self._u02_held(['下周一之前'])

    def test_u02_page_requirement_that_is_only_the_originals_title_gains_nothing(self):
        self._u02_held(['虚构实验观察表'])

    def test_u02_page_requirement_that_is_only_a_label_title_and_date_gains_nothing(self):
        self._u02_held(['科学：虚构实验观察表（11月6日前）'])

    def test_u02_page_requirement_that_is_only_the_file_name_gains_nothing(self):
        self._u02_held(['示例观察表'])

    def test_u02_page_reading_progress_never_becomes_a_complete_requirement(self):
        self._u02_held([self.U02_REQUIREMENT + '第2页本轮未送入。'], reached=False, reason='')

    def test_u02_doubted_complete_page_requirement_still_waits(self):
        schools, _ = self._u02_held([self.U02_REQUIREMENT], uncertainties=['表格第二栏字迹模糊，记录单位不清。'], reason='')
        self.assertEqual(json.loads(schools[0]['plan'])['school_task']['state'], 'review')

    def test_u02_teacher_words_alone_cannot_stand_for_the_unassigned_page_requirement(self):
        self._u02_held([self.U02_REQUIREMENT], cite='message')

    def test_u02_page_requirement_cannot_replace_the_candidates_own_words(self):
        # The existing candidate-identity guard is untouched: a ready action dropping the item's literal words is refused.
        self._u02_held([self.U02_REQUIREMENT], cite='requirement', reason='旧事项缺少可核对的同行动依据')

    def _report(self, **line):
        report = os.environ.get('DAILY_LIST_REPORT')
        if report:
            with open(report, 'a', encoding='utf-8') as f:
                f.write(json.dumps(line, ensure_ascii=False) + '\n')

    def _run(self, payload, proposals, case, today='2026-11-04', now=None):
        """The real first pass and its saved single-child list. The replay is checked only after the case's own product
        assertions (_replay_adds_nothing), so a retry or reply-seam error never stands in front of the actual result."""
        self._use_replies(payload, [dict(proposals=proposals)])
        self._batch, self._ran_at = (payload, proposals), now or self.now
        result = agent.run_once(self.app, self._ran_at)
        with self.store._db() as c:
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            rows = [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school' ORDER BY id")]
        self.assertEqual(originals, payload['messages'], 'originals and send times are kept unchanged')
        snapshot = self.app.calendar_snapshot(today, today)
        listed = [view(i) for i in snapshot['inbox'] if i['kind'] in ('task', 'school') and i['child_ids'] == ['child-1']]
        visible = [i['title'] for i in snapshot['agenda'] if i['kind'] in ('task', 'school')]
        on_day = [i['title'] for i in listed if today in (i['due_on'], i['scheduled_on'], i['complete_on']) and i['title'] in visible]
        self._report(case=case, result={k: result[k] for k in ('failed', 'processed', 'created')}, model_calls=self.model.call_count,
                     items=[dict(state=r['state'], due=r['due'], title=r['title']) for r in rows],
                     listed=listed, visible=visible, on_day=on_day)
        return result, rows, listed, (on_day, visible)

    def _replay_adds_nothing(self, case):
        """A saved batch run again 7 minutes later adds no item and requests no second model receipt."""
        replay = agent.run_once(self.app, self._ran_at + dt.timedelta(minutes=7))
        self._report(case=case + '-replay', result={k: replay[k] for k in ('failed', 'processed', 'created')},
                     model_calls=self.model.call_count)
        self.assertEqual((replay['failed'], replay['processed'], replay['created']), (0, 0, 0), 'a replay never adds a second item')
        self.assertEqual(self.model.call_count, 1, 'one bounded model receipt per batch')

    def _job(self):
        with self.store._db() as c:
            job = dict(c.execute("SELECT attempts, next_try, error, done FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone())
            processed = [r[0] for r in c.execute('SELECT processed FROM agent_messages ORDER BY rowid')]
            originals = [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
            items = c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0]
        return job, processed, originals, items

    def test_t01_continued_supplement_is_one_chinese_item_with_both_originals(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。'),
                                   ('18:02', '语文老师甲', 'cn-teacher-a', '刚才的朗读还要家长签字。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。')
        result, rows, listed, (on_day, visible) = self._run(payload, [reading], 'T01')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        item, = listed
        self.assertEqual((item['kind'], item['category']), ('task', 'homework'))
        self.assertIn('2026-11-04', (item['complete_on'], item['due_on'] if item['due_kind'] in ('', 'deadline') else ''))
        self.assertNotEqual(item['due_kind'], 'handback', 'no handback day is stated')
        for words in ('《荷塘》', '2遍', '签字'): self.assertIn(words, item['body'])
        self.assertEqual(item['publications'], refs, 'both originals keep their own source entry')
        self.assertEqual(item['published_at'][:16], '2026-11-04T18:00')
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing('T01')

    def test_product_six_paid_receipt_keeps_six_items_with_their_own_originals(self):
        """The paid receipt replayed unaltered: 刚才的朗读完成后还要请家长签字 is the same teacher's supplement two minutes after
        the reading it points back to (完成后 orders the signing after it and names no object of its own), so the whole batch
        saves six items, each with only its own object, count, executor, order, originals, send time and days."""
        self.assertEqual(hashlib.sha256(PRODUCT_SIX_REPLY.encode()).hexdigest(),
                         '8def450bb2ada557972a50f30ceb6e9e0306061b323b25bc70bf9bbde63fe88b', 'the paid receipt, unaltered')
        (self.fixture.root / '家庭运行规则.md').write_text(PRODUCT_SIX_FAMILY)
        payload, refs = self._day(PRODUCT_SIX)
        result, rows, listed, (on_day, visible) = self._run(payload, json.loads(PRODUCT_SIX_REPLY)['proposals'], 'product-six')
        self._report(case='product-six-request', request=self.model.call_args_list[0].args[0])
        self.assertEqual((result['failed'], result['processed'], len(rows), len(listed)), (0, 6, 6, 6))
        learning = {r['title']: json.loads(r['plan']).get('school_learning') for r in rows}
        for subject, category, anchors, sent, needs, forbidden, complete, due in PRODUCT_SIX_TRUTH:
            item, = [i for i in listed if all(a in i['body'] for a in anchors)]
            words = item['title'] + '\n' + item['body']
            self.assertEqual(item['category'], category, anchors)
            # Each homework keeps its own subject's learning record (both math items too); a notice keeps its own words.
            if category == 'homework': self.assertEqual(learning[item['title']], dict(subject=subject, goal_id=''), anchors)
            else: self.assertTrue(learning[item['title']] is None and subject in words, anchors)
            for need in needs: self.assertRegex(item['body'], need)
            for word in forbidden: self.assertNotIn(word, words, anchors)
            self.assertEqual(item['publications'], [refs[i] for i in sent], 'only its own originals')
            self.assertEqual(item['published_at'][:16], payload['messages'][sent[0]]['time'][:16])
            self.assertEqual(item['scheduled_on'], '', 'no planned day is invented')
            if due:
                self.assertEqual((item['complete_on'], item['due_on'], item['due_kind']), (complete,) + due, anchors)
            else:
                self.assertNotIn(item['due_kind'], ('handback', 'inspection', 'arranged'), anchors)
                self.assertIn(complete, (item['complete_on'], item['due_on'] if item['due_kind'] in ('', 'deadline') else ''), anchors)
        self.assertEqual(sorted(on_day), sorted(i['title'] for i in listed if i['due_kind'] != 'arranged'), 'tonight lists all but the rope')
        self._replay_adds_nothing('product-six')

    def _t02_batch(self, t06=False):
        """T02's frozen message and its fixed fictional receipt: tonight's English reading and tomorrow's PE rope. With t06,
        T06's frozen text in the same day (date only; its unread attachment is a separate open question)."""
        text = '今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练。'
        payload, refs = self._day([('18:10', '老师乙', 'teacher-b', text)] + ([('18:40', '科学老师', 'teacher-science', T06_TEXT)] if t06 else []))
        reading = self._proposal('今晚跟读Unit 5两遍', refs[:1], '英语', '今晚跟读Unit 5两遍。')
        rope = self._proposal('明天体育课带跳绳', refs[:1], '', '11月5日体育课带跳绳；不要求在家训练。', due='2026-11-05', purpose='admin')
        sheet = self._proposal('明天带去课堂的实验观察表', refs[1:], '', '11月5日带去课堂的实验观察表；今晚不填。', due='2026-11-05', purpose='admin')
        return payload, [reading, rope] + ([sheet] if t06 else [])

    def test_t06_sheet_saved_beside_t02_reads_its_arranged_day(self):
        """Only T06's date meaning through the real run_once and saved list, not the whole T06 (its attachment is unread):
        the sheet keeps 11/5 as its arranged day and its own words and original; T02's two siblings keep their own days."""
        payload, proposals = self._t02_batch(t06=True)
        result, rows, listed, _ = self._run(payload, proposals, 'T06-date')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        english, = [i for i in listed if 'Unit 5' in i['body']]
        rope, = [i for i in listed if '跳绳' in i['body']]
        sheet, = [i for i in listed if '实验观察表' in i['body']]
        self.assertEqual(len(listed), 3)
        self.assertEqual((sheet['category'], sheet['due_on'], sheet['due_kind'], sheet['complete_on'], sheet['scheduled_on']),
                         ('todo', '2026-11-05', 'arranged', '', ''), 'its arranged day; no completion day or parent plan made up')
        self.assertIn('今晚不填', sheet['body'])
        self.assertEqual(sheet['published_at'][:16], '2026-11-04T18:40')
        self.assertEqual(len(sheet['publications']), 1)
        self.assertNotIn(sheet['publications'][0], english['publications'] + rope['publications'], 'its own original only')
        self.assertEqual((rope['due_on'], rope['due_kind'], rope['scheduled_on']), ('2026-11-05', 'arranged', ''))
        self.assertIn('2026-11-04', (english['complete_on'], english['due_on']))
        self.assertNotIn('2026-11-05', (english['due_on'], english['complete_on'], english['scheduled_on']))
        self._replay_adds_nothing('T06-date')

    def test_a_parents_own_plan_day_for_a_carried_thing_stays_beside_its_arranged_day(self):
        """The parent plans the rope and the sheet on days of their own through the real task-focus save (the same generic
        form fields the card sends back), then the real snapshot: each still reads 11/5 as its 安排日 and shows its own plan;
        the originals, saved rows and words stay as saved, and the same plan request replayed writes nothing."""
        import family_task_focus
        payload, proposals = self._t02_batch(t06=True)
        self._run(payload, proposals, 'T06-plan')

        def stored():
            with self.store._db() as c:
                return ([dict(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')],
                        [dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')],
                        [json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')])
        before = stored()
        tasks = {t['id']: t for t in self.app.tasks()}
        rope = next(t for t in tasks.values() if '跳绳' in t['action'])
        sheet = next(t for t in tasks.values() if '实验观察表' in t['action'])
        plans = {rope['id']: '2026-11-04', sheet['id']: '2026-11-05'}

        def form(task, key):
            f, m = task['focus'], task['agenda']
            return dict(id=task['id'], version=f['version'], request_key='t06-carried-plan-' + key, mode=f['mode'], next_action='',
                        waiting_for=f['waiting_for'], review_on=f['review_on'], category=m['category'], published_on=m['published_on'],
                        due_on=m['due_on'], scheduled_on=plans[task['id']], box=f['box'], title=task['title'], goal=task['action'])
        requests = [form(rope, 'rope'), form(sheet, 'sheet')]
        for request in requests:
            self.assertFalse(family_task_focus.save(self.app, request)['request_replayed'])
        planned = {t['id']: t['focus'] for t in self.app.tasks()}
        for day in ('2026-11-04', '2026-11-05'):
            listed = {i['id']: i['agenda'] for i in self.app.calendar_snapshot(day, day)['inbox'] if i['kind'] == 'task'}
            for task in (rope, sheet):
                with self.subTest(day=day, task=task['title']):
                    m = listed[task['id']]
                    self.assertEqual((m['due_on'], m['due_kind'], m['complete_on'], m['scheduled_on']),
                                     ('2026-11-05', 'arranged', '', plans[task['id']]), 'its 安排日 beside the parent\'s own plan')
        self.assertEqual(stored(), before, 'originals, saved rows and saved words unchanged')
        for request in requests:
            self.assertTrue(family_task_focus.save(self.app, request)['request_replayed'])
        self.assertEqual({t['id']: t['focus'] for t in self.app.tasks()}, planned, 'the replayed plan writes nothing')
        self.assertEqual(self.model.call_count, 1)

    def test_t02_independent_supply_is_its_own_admin_item_on_its_own_day(self):
        payload, proposals = self._t02_batch()
        result, rows, listed, (on_day, visible) = self._run(payload, proposals, 'T02')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(len(listed), 2)
        english, = [i for i in listed if 'Unit 5' in i['body']]
        supply, = [i for i in listed if '跳绳' in i['body']]
        self.assertEqual(english['category'], 'homework')
        self.assertIn('2026-11-04', (english['complete_on'], english['due_on']))
        self.assertNotIn('跳绳', english['body'])
        self.assertEqual((supply['category'], supply['due_on'], supply['complete_on']), ('todo', '2026-11-05', ''))
        # 11/5 is the PE lesson's arranged day for carrying the rope, not a deadline, handback or check; no parent plan is made up.
        self.assertEqual((supply['due_kind'], supply['scheduled_on']), ('arranged', ''))
        self.assertNotEqual(english['due_kind'], 'arranged')
        self.assertNotIn('2026-11-05', (english['due_on'], english['complete_on'], english['scheduled_on']), 'tonight never borrows tomorrow')
        self.assertNotIn('Unit 5', supply['body'])
        self.assertFalse(any(i['title'].endswith('训练') or '在家训练' in i['title'] for i in listed), 'no training item is generated')
        self._replay_adds_nothing('T02')

    def test_t02_only_carrying_to_that_days_lesson_is_an_arranged_day(self):
        meaning = lambda quote, due='2026-11-05', title='': family_agenda.date_meaning(quote, due, '2026-11-04', title)
        self.assertEqual(meaning('明天体育课带跳绳'), 'arranged')
        self.assertEqual(meaning('另外，明天体育课带跳绳，不要求在家训练'), 'arranged')
        self.assertEqual(meaning('今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练'), 'arranged')
        self.assertEqual(meaning('今晚跟读Unit 5两遍；另外，明天体育课带跳绳，不要求在家训练', '2026-11-04'), 'deadline', 'tonight is not tomorrow')
        self.assertEqual(meaning('今晚跟读Unit 5两遍', '2026-11-05'), 'deadline')
        for quote in ('11月5日前准备好跳绳', '11月5日前带跳绳', '明天体育课不用带跳绳', '明天体育课取消，不用带跳绳', '今晚完成练习，明天带来'):
            self.assertEqual(meaning(quote), 'deadline', quote)
        self.assertEqual(meaning('今晚完成第4题，明早交给数学课代表'), 'handback')
        self.assertEqual(meaning('明早检查跳绳'), 'inspection')
        self.assertNotEqual(meaning('明天英语课听写'), 'arranged')
        self.assertEqual(meaning('运动会定于11月5日举行，请家长参加', title='参加运动会'), 'event')

    def test_t06_carrying_the_sheet_to_tomorrows_class_is_its_arranged_day(self):
        """T06's date reading only; its unread attachment is a separate open question. 带去课堂的<thing> carries a thing of
        its own to that day's lesson as T02's 带 does, so 11/5 is its arranged day. Without a thing of its own (the work
        itself), before that day, negated, with another predicate or handed in, it is not."""
        meaning = lambda quote, due='2026-11-05': family_agenda.date_meaning(quote, due, '2026-11-04')
        self.assertEqual(meaning('附件是明天带去课堂的实验观察表，今晚不填'), 'arranged')
        self.assertEqual(meaning('明天带去课堂的实验观察表'), 'arranged')
        self.assertNotEqual(meaning('附件是明天带去课堂的实验观察表，今晚不填', '2026-11-04'), 'arranged', 'tonight is not tomorrow')
        for quote in ('今晚完成练习，明天带去', '今晚填好观察表，明天带去课堂', '11月5日前带去课堂的实验观察表',
                      '明天不用带去课堂的实验观察表', '明天带去课堂的观察表要填好', '明天把作品带去参加展览'):
            self.assertEqual(meaning(quote), 'deadline', quote)
        self.assertEqual(meaning('明天把观察表带去学校交给老师'), 'handback')

    # Root's independent counterexamples to the T06 reading: each original only names the thing carried to tomorrow's class,
    # as T06 names its 实验观察表, so 11/5 is that thing's arranged day. 练/读/写 inside the thing's own name are no
    # completion, reading or writing it asks for.
    # (original, quoted own words, goal in T06's receipt shape, own words the card keeps)
    ROOT_CARRIED = (('附件是明天带去课堂的英语练习册，今晚不用做。', '明天带去课堂的英语练习册', '11月5日带去课堂的英语练习册；今晚不用做。', '今晚不用做'),
                    ('附件是明天带去课堂的读书记录表，今晚不填。', '明天带去课堂的读书记录表', '11月5日带去课堂的读书记录表；今晚不填。', '今晚不填'),
                    ('明天带去课堂的书写练习本。', '明天带去课堂的书写练习本', '11月5日带去课堂的书写练习本。', '书写练习本'))

    def test_root_a_verbs_character_inside_the_carried_things_name_is_no_predicate(self):
        meaning = lambda quote, due='2026-11-05': family_agenda.date_meaning(quote, due, '2026-11-04')
        for text, quote, _, _ in self.ROOT_CARRIED:
            for words in (text, quote):
                self.assertEqual(meaning(words), 'arranged', words)
            self.assertNotEqual(meaning(text, '2026-11-04'), 'arranged', 'tonight is not tomorrow')
        # A real predicate after the thing, a before-day, a negation, a handback or a check reads as before.
        for quote in ('明天带去课堂的观察表要填好', '明天带去课堂的英语练习册要做完', '明天带去课堂的读书记录表要填写',
                      '明天带去课堂的读书记录表填好', '明天带去课堂的书写练习本写好名字', '明天带去课堂的英语练习册填进记录表',
                      '11月5日前带去课堂的英语练习册', '明天不用带去课堂的读书记录表', '今晚完成英语练习册，明天带去课堂'):
            self.assertEqual(meaning(quote), 'deadline', quote)
        self.assertEqual(meaning('明天把英语练习册带去学校交给老师'), 'handback')
        self.assertEqual(meaning('明天早读检查读书记录表'), 'inspection')

    def _root_carried(self, case, text, quote, goal, kept):
        """One original sent at T06's 18:40 with T06's receipt shape, through the real run_once and saved single-child list."""
        payload, refs = self._day([('18:40', '虚构任课老师', 'teacher-carry', text)])
        thing = self._proposal(quote, refs, '', goal, due='2026-11-05', purpose='admin')
        result, rows, listed, _ = self._run(payload, [thing], case)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['category'], item['due_on'], item['due_kind'], item['complete_on'], item['scheduled_on']),
                         ('todo', '2026-11-05', 'arranged', '', ''), 'its arranged day; no completion day or parent plan made up')
        self.assertIn(kept, item['body'], 'its own words kept')
        self.assertEqual(item['published_at'][:16], '2026-11-04T18:40')
        self.assertEqual(item['publications'], refs, 'its own original only')
        self.assertEqual([json.loads(r['plan']).get('school_date_quote') for r in rows], [quote], 'the saved quote stays word for word')
        self._replay_adds_nothing(case)

    def test_root_a1_the_workbook_carried_to_class_reads_its_arranged_day(self):
        self._root_carried('ROOT-A1', *self.ROOT_CARRIED[0])

    def test_root_a2_the_reading_record_sheet_carried_to_class_reads_its_arranged_day(self):
        self._root_carried('ROOT-A2', *self.ROOT_CARRIED[1])

    def test_root_a3_the_writing_book_carried_to_class_reads_its_arranged_day(self):
        self._root_carried('ROOT-A3', *self.ROOT_CARRIED[2])

    def test_t03_same_subject_from_two_teachers_stays_two_signed_items(self):
        payload, refs = self._day([('18:20', '数学老师甲', 'math-teacher-a', '今晚做练习二第1、2题。'),
                                   ('18:25', '数学老师乙', 'math-teacher-b', '今晚做练习二第4题。')])
        first = self._proposal('今晚做练习二第1、2题', refs[:1], '数学', '今晚做练习二第1、2题。')
        second = self._proposal('今晚做练习二第4题', refs[1:], '数学', '今晚做练习二第4题。')
        result, rows, listed, (on_day, visible) = self._run(payload, [first, second], 'T03')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        self.assertEqual(sorted(i['publications'] for i in listed), [refs[:1], refs[1:]], 'each keeps its own teacher and source')
        self.assertEqual(sorted('第1、2题' in i['body'] for i in listed), [False, True])
        self.assertTrue(all(i['category'] == 'homework' for i in listed))
        self._replay_adds_nothing('T03')

    def test_t03_counterexample_merged_reply_is_not_saved_as_one_item(self):
        payload, refs = self._day([('18:20', '数学老师甲', 'math-teacher-a', '今晚做练习二第1、2题。'),
                                   ('18:25', '数学老师乙', 'math-teacher-b', '今晚做练习二第4题。')])
        # Only the two teachers' merge is off-contract here: no due or other field the reply should not carry.
        merged = self._proposal('今晚做练习二第1、2题', refs, '数学', '今晚做练习二第1、2题；第4题。')
        result, rows, listed, _ = self._run(payload, [merged], 'T03-merged')
        self.assertEqual((result['failed'], result['processed'], result['created']), (1, 0, 0), 'the whole batch is kept for retry')
        job, processed, originals, items = self._job()
        self.assertIn('学校补充要求未归到对应作业', job['error'], "the other teacher's original is no supplement of this item")
        self.assertEqual((processed, items, listed), ([0, 0], 0, []), "two teachers' same-titled work is never one accepted item")

    def test_t04_late_organizing_keeps_the_original_days_and_unknown_completion(self):
        payload, refs = self._day([('18:30', '数学老师甲', 'math-teacher-a', '今晚完成第4题，明早交给数学课代表。')])
        work = self._proposal('今晚完成第4题，明早交给数学课代表', refs, '数学', '今晚完成第4题；11月5日早上交给数学课代表。',
                              due='2026-11-05', submission='11月5日早上交给数学课代表')
        late = dt.datetime(2026, 11, 6, 20, tzinfo=agent.TZ)
        self.fixture.now = late
        result, rows, listed, (on_day, visible) = self._run(payload, [work], 'T04', today='2026-11-06', now=late)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['category'], item['complete_on'], item['due_on'], item['due_kind'], item['scheduled_on']),
                         ('homework', '2026-11-04', '2026-11-05', 'handback', ''))
        self.assertEqual(item['published_at'][:16], '2026-11-04T18:30', 'not a new 11-06 assignment')
        self.assertEqual((visible, on_day), ([item['title']], []), 'an open overdue item is still checked on 11-06, not 11-06 work')
        self.assertIn(item['status'], ('待跟进', '待核对'), 'no feedback is no completion fact')
        self.assertIn('不推定完成', rows[0]['plan'], 'the overdue check never infers the child did or did not do it')
        self._replay_adds_nothing('T04')

    def test_t07_undated_consent_keeps_its_question_without_blocking_the_english_item(self):
        payload, refs = self._day([('18:45', '老师甲', 'teacher-a', '请家长签署同意书后交回。'),
                                   ('18:46', '英语老师', 'en-teacher', '今晚跟读Unit 6两遍。')])
        consent = self._proposal('请家长签署同意书后交回', refs[:1], '', '家长签署同意书后交回。', purpose='admin')
        english = self._proposal('今晚跟读Unit 6两遍', refs[1:], '英语', '今晚跟读Unit 6两遍。')
        result, rows, listed, (on_day, visible) = self._run(payload, [consent, english], 'T07')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        self.assertEqual(len(listed), 2)
        sign, = [i for i in listed if '同意书' in i['body']]
        reading, = [i for i in listed if 'Unit 6' in i['body']]
        self.assertEqual((sign['category'], sign['due_on'], sign['complete_on']), ('todo', '', ''), 'its date stays unknown')
        self.assertEqual((reading['kind'], reading['category']), ('task', 'homework'))
        self.assertIn('2026-11-04', (reading['complete_on'], reading['due_on']))
        self._replay_adds_nothing('T07')

    def test_t09_classroom_dictation_stays_its_own_next_day_item(self):
        text = '今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写；明天英语课听写。'
        payload, refs = self._day([('19:00', '英语老师', 'en-teacher', text)])
        reading = self._proposal('今晚听音频跟读Unit 5第1至8个单词，每个两遍，不用抄写', refs, '英语',
                                 '今晚听音频跟读Unit 5第1至8个单词，每个两遍；不用抄写。')
        dictation = self._proposal('明天英语课听写', refs, '英语', '11月5日英语课听写。', due='2026-11-05')
        result, rows, listed, (on_day, visible) = self._run(payload, [reading, dictation], 'T09')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        self.assertEqual(len(listed), 2)
        tonight, = [i for i in listed if '跟读' in i['body']]
        test, = [i for i in listed if '跟读' not in i['body']]
        self.assertIn('2026-11-04', (tonight['complete_on'], tonight['due_on']))
        self.assertIn('听写', test['body'])
        self.assertEqual((test['due_on'], test['complete_on']), ('2026-11-05', ''), 'the dictation is in class on 11-05, not tonight')
        self.assertNotIn('今晚', test['body'])
        self.assertNotIn('抄写', test['body'].replace('不用抄写', ''))
        self.assertEqual(on_day, [tonight['title']], 'only the follow-reading is tonight\'s work')
        self._replay_adds_nothing('T09')

    def test_t10_reply_slip_choice_keeps_both_roles_and_both_options(self):
        text = '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。'
        payload, refs = self._day([('19:05', '班主任', 'head-teacher', text)])
        slip = self._proposal(text.rstrip('。'), refs, '', '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子11月5日早上交给班主任。',
                              due='2026-11-05', purpose='admin', submission='孩子明早交给班主任')
        result, rows, listed, (on_day, visible) = self._run(payload, [slip], 'T10')
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['kind'], item['category'], item['complete_on'], item['due_on'], item['due_kind']),
                         ('task', 'todo', '2026-11-04', '2026-11-05', 'handback'))
        for words in ('参加', '不参加', '签字', '班主任'): self.assertIn(words, item['body'])
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing('T10')
        self._t10_original_reads(refs[0], text)

    def _t10_original_reads(self, ref, text):
        """The accepted slip's own teacher message opens from its task (Root: GET /api/agent/message returned 409). The slip
        was saved from its quoted words, no native action, and its message carries no file: its text is its whole scope.
        A changed original, another child's binding or a file added later still keep the old refusals."""
        source_id, message_id = ref[8:].rsplit(':', 1)
        with self.store._db() as c:
            row = dict(c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='accepted'").fetchone())
        self.assertNotIn('school_original_action', json.loads(row['plan']), 'saved from its reply, not a native action')
        ask = dict(child_id='child-1', source_id=source_id, message_id=message_id, task_id=row['task_id'])
        view = self.store.message(ask, None)
        self.assertEqual((view['task_id'], view['attachments'], view['action_material']['scoped']), (row['task_id'], [], True))
        self.assertEqual([q['text'] for q in view['action_material']['quotes']], [text])
        self.assertEqual([q['upload_ids'] for q in view['action_material']['quotes']], [[]], 'text only, no file bound')
        with self.store._db() as c:
            self.assertEqual(json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (row['id'],)).fetchone()[0]),
                             json.loads(row['plan']), 'reading saves nothing')
            with self.assertRaises(agent.AgentError):  # another child's binding of the same message
                agent.school_original_source_row(self.store, c, dict(row, child_id='child-other'), ref)
            c.execute('INSERT INTO agent_message_attachments(source_id,message_id,upload_id) VALUES(?,?,?)', (source_id, message_id, 'u-added'))
            with self.assertRaises(agent.AgentError) as added:  # a file now sharing the message: its share stays unknown
                agent.school_original_upload_ids(self.store, c, row, ref, ['u-added'])
            self.assertEqual((added.exception.status, added.exception.code), (409, 'school_original_scope_stale'))
            c.execute('DELETE FROM agent_message_attachments WHERE upload_id=?', ('u-added',))
            plan = json.loads(row['plan']); plan['school_task'].pop('origin_basis')
            with self.assertRaises(agent.AgentError) as legacy:  # a legacy decision that never recorded its basis
                agent.school_original_upload_ids(self.store, c, dict(row, plan=json.dumps(plan, ensure_ascii=False)), ref, [])
            self.assertEqual((legacy.exception.status, legacy.exception.code, str(legacy.exception)),
                             (409, 'school_original_scope_stale', '本项资料范围尚未核明，请查看老师完整原消息'), 'unverified, not changed')
            payload = json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?', (source_id, message_id)).fetchone()[0])
            c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',
                      (json.dumps(dict(payload, text=text.replace('明早', '后天')), ensure_ascii=False), source_id, message_id))
        with self.assertRaises(agent.AgentError) as changed:
            self.store.message(ask, None)
        self.assertEqual((changed.exception.status, changed.exception.code, str(changed.exception)),
                         (409, 'school_original_scope_stale', '本项原消息已变化，请回原消息重新核对'), 'a changed original')

    def test_t01_counterexample_a_send_day_due_for_tonight_work_states_no_handback(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍。', due='2026-11-04')
        result, rows, listed, _ = self._run(payload, [reading], 'T01-send-day-due')
        item, = listed  # Off-contract send-day due (发送日不作截止): adopted here, held for 今晚做练习二 (see RESULT); never a handback.
        self.assertNotEqual(item['due_kind'], 'handback')
        self.assertIn('2026-11-04', (item['complete_on'], item['due_on']))
        self._replay_adds_nothing('T01-send-day-due')

    def _next_four(self, case, late=False):
        """The four originals and the actual reply through the real run_once, as of 11-04 20:00 or first organized 11-06 20:00."""
        now = dt.datetime(2026, 11, 6 if late else 4, 20, tzinfo=agent.TZ)
        self.fixture.now = now
        payload, refs = self._day(NEXT_FOUR)
        result, rows, listed, _ = self._run(payload, json.loads(NEXT_FOUR_REPLY)['proposals'], case, today=now.date().isoformat(), now=now)
        self.assertEqual((result['failed'], self.model.call_count), (0, 1))
        self.assertEqual(len(listed), 5, 'five outcomes, no manual item')
        return refs, rows, listed

    def _next_four_days(self, refs, listed):
        for anchor, (index, complete, due) in NEXT_FOUR_TRUTH.items():
            with self.subTest(anchor=anchor):
                item, = [i for i in listed if anchor in i['title']]
                self.assertEqual(item['publications'], [refs[index]], 'its own original only')
                self.assertEqual(item['published_at'][:16], '2026-11-04T' + NEXT_FOUR[index][0], 'not a new 11-06 assignment')
                if due is None:
                    self.assertIn(complete, (item['complete_on'], item['due_on']))
                    self.assertNotIn(item['due_kind'], ('handback', 'inspection', 'arranged', 'event'))
                    continue
                self.assertEqual((item['complete_on'], item['due_on']), (complete, due[0]))
                if due[1]: self.assertEqual(item['due_kind'], due[1])
                else: self.assertNotEqual(item['due_kind'], 'handback')

    def test_next_four_accepted_on_the_day_keep_each_own_days(self):
        refs, rows, listed = self._next_four('NEXT-FOUR-11-04')
        self.assertEqual({i['kind'] for i in listed}, {'task'})
        self._next_four_days(refs, listed)
        self._replay_adds_nothing('NEXT-FOUR-11-04')

    def test_next_four_first_organized_late_stay_pending_with_each_own_days(self):
        """Root's independent reproduction: the same reply first organized on 11-06 stays for review under the history guard,
        never accepted or made 11-06 work, while the slip's own words still name its 11-04 signing (今晚…然后签字；孩子明早交给
        班主任) as on its accepted card. The undated consent borrows no day; listing writes nothing."""
        refs, rows, listed = self._next_four('NEXT-FOUR-11-06', late=True)
        self.assertEqual({(i['kind'], i['status']) for i in listed}, {('school', '待核对')}, 'no old item is accepted automatically')
        self.assertEqual({r['state'] for r in rows}, {'pending'})
        self._next_four_days(refs, listed)
        source_id, message_id = refs[3][8:].rsplit(':', 1)
        self.assertIn(NEXT_FOUR[3][3], json.dumps(self.store.message(dict(child_id='child-1', source_id=source_id, message_id=message_id), None),
                                                  ensure_ascii=False), 'the same original opens')
        with self.store._db() as c:
            before = '\n'.join(c.iterdump())
        self.app.calendar_snapshot('2026-11-04', '2026-11-06')
        with self.store._db() as c:
            self.assertEqual('\n'.join(c.iterdump()), before, 'listing saves nothing')
            # Another live item quoting the slip's own handback words makes that range shared: no role is read from it.
            row = dict(c.execute("SELECT * FROM agent_items WHERE kind='school' AND evidence LIKE ?", ('%:' + message_id + '"%',)).fetchone())
            plan = json.loads(row['plan']); plan['school_date_quote'] = '孩子明早交给班主任'
            shared = dict(row, id=row['id'] + '-shared', title='孩子明早交给班主任', plan=json.dumps(plan, ensure_ascii=False))
            c.execute('INSERT INTO agent_items(%s) VALUES(%s)' % (','.join(shared), ','.join('?' * len(shared))), list(shared.values()))
        slip, = [view(i) for i in self.app.calendar_snapshot('2026-11-06', '2026-11-06')['inbox'] if i['id'] == row['id']]
        self.assertEqual((slip['complete_on'], slip['due_on']), ('', '2026-11-05'), "a sibling's overlapping words date nothing")
        with self.store._db() as c:
            c.execute('DELETE FROM agent_items WHERE id=?', (shared['id'],))
        self._replay_adds_nothing('NEXT-FOUR-11-06')


class ContinuedSupplementVariantTests(unittest.TestCase):
    """Fictional variants of T01's shared cause, not frozen contract cases: the same teacher's follow-up in the same source,
    within two minutes, pointing back to one listed object and only adding a step to it (刚才的朗读还要家长签字) is that one
    item's supplement. Another teacher or source, a later or earlier message, two items it could mean, a question, change,
    condition, negation, subject, or a day, count, title or worksheet of its own, a second clause or no pointer binds
    nothing: the whole batch stays for the existing retry, nothing saved, originals kept. Fixed receipts prove only the
    program layer."""
    setUp, _use_replies, _day, _proposal = (DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies,
                                            DailyListFrozenTests._day, DailyListFrozenTests._proposal)
    _report, _run, _replay_adds_nothing, _job = (DailyListFrozenTests._report, DailyListFrozenTests._run,
                                                 DailyListFrozenTests._replay_adds_nothing, DailyListFrozenTests._job)

    def _ledger(self, *later, first='今晚朗读《荷塘》2遍。'):
        """Each listed outcome of the first original and the supplement goals the shared ledger binds to it.
        later: (text, seconds after the list, publisher, source) of each following original."""
        sent = dt.datetime(2026, 11, 4, 18, tzinfo=agent.TZ)
        evidence = [dict(ref='message:synthetic-group:11', text=first, time=sent.isoformat(), publisher='cn-teacher-a')]
        evidence += [dict(ref='message:%s:%d' % (source, 12 + i), text=text, time=(sent + dt.timedelta(seconds=gap)).isoformat(),
                          publisher=publisher) for i, (text, gap, publisher, source) in enumerate(later)]
        for i, e in enumerate(evidence):
            e.update(kind='text', content_incomplete=False, unread=False, attachments=[], message_order=str(11 + i))
        return {a['quote']: [s['goal'] for s in a['supplements']] for a in agent._school_native_actions(evidence)
                if a['ref'] == evidence[0]['ref']}

    def test_the_ledger_binds_a_pointer_back_with_one_added_step(self):
        for text, goal in (('刚才的朗读还要家长签字。', '朗读还要家长签字'), ('上面的朗读也要家长签字', '朗读也要家长签字'),
                           ('刚刚布置的朗读还需要家长签字！', '朗读还需要家长签字'), ('前面的《荷塘》也请家长签字。', '《荷塘》也请家长签字')):
            self.assertEqual(self._ledger((text, 120, 'cn-teacher-a', 'synthetic-group')), {'今晚朗读《荷塘》2遍': [goal]}, text)
        self.assertEqual(self._ledger(('刚才的朗读还要家长签字。', 60, 'cn-teacher-a', 'synthetic-group'), first='今晚朗读《荷塘》2遍；抄写生字一遍。'),
                         {'今晚朗读《荷塘》2遍': ['朗读还要家长签字'], '抄写生字一遍': []}, 'only the item it names')

    def test_the_ledger_binds_nothing_without_one_clear_continuation(self):
        same = ('cn-teacher-a', 'synthetic-group')
        unbound = {'今晚朗读《荷塘》2遍': []}
        for later in (('刚才的朗读还要家长签字。', 60, 'cn-teacher-b', 'synthetic-group'),  # another teacher
                      ('刚才的朗读还要家长签字。', 60, 'cn-teacher-a', 'synthetic-other'),  # another source or child binding
                      ('刚才的朗读还要家长签字。', 600, *same), ('刚才的朗读还要家长签字。', -60, *same),  # no near, later context
                      ('刚才的朗读还要家长签字吗？', 60, *same), ('刚才的朗读如果读完还要家长签字。', 60, *same),
                      ('刚才的朗读还要改为家长签字。', 60, *same), ('刚才的朗读也不用家长签字。', 60, *same),
                      ('刚才的语文朗读还要家长签字。', 60, *same), ('刚才的朗读还要家长明早签字。', 60, *same),
                      ('刚才的朗读还要再读1遍。', 60, *same), ('刚才的朗读还要抄写生字两遍。', 60, *same),
                      ('刚才的朗读还要背诵《春》。', 60, *same), ('刚才的朗读还要完成练习册。', 60, *same),
                      ('刚才的朗读还要家长签字，明天体育课带跳绳。', 60, *same), ('刚才的朗读还要家长签字。明天体育课带跳绳。', 60, *same),
                      ('朗读还要家长签字。', 60, *same), ('刚才的背诵还要家长签字。', 60, *same)):
            self.assertEqual(self._ledger(later), unbound, later)
        self.assertEqual(self._ledger(('刚才的朗读还要家长签字。', 60, *same), first='今晚朗读《荷塘》2遍；朗读《春》1遍。'),
                         {'今晚朗读《荷塘》2遍': [], '朗读《春》1遍': []}, 'two items it could mean')
        with self.assertRaises(agent.AgentError) as both:  # two lists' items it could mean
            self._ledger(('今晚朗读《春》1遍。', 30, *same), ('刚才的朗读还要家长签字。', 60, *same))
        self.assertIn('学校补充同时对应多项作业', str(both.exception))

    def test_the_continued_step_joins_only_the_item_it_names(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍；抄写生字一遍。'),
                                   ('18:01', '语文老师甲', 'cn-teacher-a', '刚才的朗读还要家长签字。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。')
        copying = self._proposal('抄写生字一遍', refs[:1], '语文', '抄写生字一遍。')
        result, rows, listed, _ = self._run(payload, [reading, copying], 'T01-variant-two-items')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        read, = [i for i in listed if '《荷塘》' in i['body']]
        copy, = [i for i in listed if '抄写生字一遍' in i['body']]
        self.assertEqual((read['publications'], copy['publications']), (refs, refs[:1]), 'each keeps its own originals')
        self.assertIn('签字', read['body'])
        self.assertNotIn('签字', copy['body'])
        self.assertNotIn('抄写', read['body'])
        self._replay_adds_nothing('T01-variant-two-items')

    def _rejected(self, messages, proposals, case):
        """The whole batch stays for the original retry limit: nothing saved, originals kept, no further receipt."""
        payload, refs = self._day(messages)
        result, rows, listed, _ = self._run(payload, proposals(refs), case)
        self.assertEqual((result['failed'], result['processed'], result['created'], listed), (1, 0, 0, []))
        self._use_replies(payload, [dict(proposals=proposals(refs))] * (agent.MAX_ATTEMPTS - 1))
        for minutes in (7, 18, 60):  # attempt 2 after its 5-minute wait, attempt 3 after 10 more, then none
            agent.run_once(self.app, self._ran_at + dt.timedelta(minutes=minutes))
        job, processed, originals, items = self._job()
        self.assertEqual(self.model.call_count, agent.MAX_ATTEMPTS, 'one fixed receipt per attempt, never past the original limit')
        self.assertEqual((job['attempts'], job['done'], job['next_try'], processed, items), (agent.MAX_ATTEMPTS, 0, '', [0, 0], 0))
        self.assertEqual(originals, payload['messages'])
        return job['error']

    def test_another_teachers_follow_up_is_no_supplement(self):
        error = self._rejected([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍。'),
                                ('18:02', '语文老师乙', 'cn-teacher-b', '刚才的朗读还要家长签字。')],
                               lambda refs: [self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。')],
                               'T01-variant-other-teacher')
        self.assertIn('学校补充要求未归到对应作业', error)

    def test_a_follow_up_two_items_could_mean_is_no_supplement(self):
        error = self._rejected([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍；朗读《春》1遍。'),
                                ('18:02', '语文老师甲', 'cn-teacher-a', '刚才的朗读还要家长签字。')],
                               lambda refs: [self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读后请家长签字。'),
                                             self._proposal('朗读《春》1遍', refs[:1], '语文', '朗读《春》1遍。')],
                               'T01-variant-two-antecedents')
        self.assertIn('学校补充要求未归到对应作业', error)

    def test_an_order_after_the_object_is_no_object_of_its_own(self):
        """完成后/做完以后 only orders the added step after the pointed-back object: it binds under the same identity and
        window, kept in the requirement, and hides no other teacher, source, candidate, change, negation, day or count."""
        same = ('cn-teacher-a', 'synthetic-group')
        for text, goal in (('刚才的朗读完成后还要请家长签字。', '朗读完成后还要请家长签字'), ('上面的朗读读完以后也要家长签字', '朗读读完以后也要家长签字'),
                           ('刚刚布置的《荷塘》读完之后还需要家长签字！', '《荷塘》读完之后还需要家长签字')):
            self.assertEqual(self._ledger((text, 120, *same)), {'今晚朗读《荷塘》2遍': [goal]}, text)
        self.assertEqual(self._ledger(('刚才的朗读完成后还要请家长签字。', 60, *same), first='今晚朗读《荷塘》2遍；抄写生字一遍。'),
                         {'今晚朗读《荷塘》2遍': ['朗读完成后还要请家长签字'], '抄写生字一遍': []}, 'only the item it names')
        unbound = {'今晚朗读《荷塘》2遍': []}
        for later in (('刚才的朗读完成后还要请家长签字。', 60, 'cn-teacher-b', 'synthetic-group'),  # another teacher
                      ('刚才的朗读完成后还要请家长签字。', 60, 'cn-teacher-a', 'synthetic-other'),  # another source or child binding
                      ('刚才的朗读完成后还要请家长签字。', 600, *same), ('刚才的朗读完成后改为家长签字。', 60, *same),
                      ('刚才的朗读完成后取消家长签字。', 60, *same), ('刚才的朗读完成后也不用家长签字。', 60, *same),
                      ('刚才的朗读完成后还要家长签字吗？', 60, *same), ('刚才的朗读完成后明天还要家长签字。', 60, *same),
                      ('刚才的朗读完成后还要家长明早签字。', 60, *same), ('刚才的朗读完成后还要再读1遍。', 60, *same),
                      ('刚才的朗读完成后还要再读两遍。', 60, *same), ('刚才的作业完成后还要家长签字。', 60, *same),
                      ('刚才的完成后还要家长签字。', 60, *same)):
            self.assertEqual(self._ledger(later), unbound, later)
        self.assertEqual(self._ledger(('刚才的朗读完成后还要请家长签字。', 60, *same), first='今晚朗读《荷塘》2遍；朗读《春》1遍。'),
                         {'今晚朗读《荷塘》2遍': [], '朗读《春》1遍': []}, 'two items it could mean')

    def test_an_after_completion_step_joins_only_the_item_it_names(self):
        payload, refs = self._day([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍；抄写生字一遍。'),
                                   ('18:01', '语文老师甲', 'cn-teacher-a', '刚才的朗读完成后还要请家长签字。')])
        reading = self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍。\n朗读完成后请家长签字。')
        copying = self._proposal('抄写生字一遍', refs[:1], '语文', '抄写生字一遍。')
        result, rows, listed, _ = self._run(payload, [reading, copying], 'T01-variant-after-completion')
        self.assertEqual((result['failed'], result['processed']), (0, 2))
        read, = [i for i in listed if '《荷塘》' in i['body']]
        copy, = [i for i in listed if '抄写生字一遍' in i['body']]
        self.assertEqual((read['publications'], copy['publications']), (refs, refs[:1]), 'each keeps its own originals')
        self.assertRegex(read['body'], '朗读完成后.{0,6}家长签字')
        self.assertNotIn('签字', copy['body'])
        self._replay_adds_nothing('T01-variant-after-completion')

    def test_an_after_completion_follow_up_from_another_teacher_or_for_two_items_is_no_supplement(self):
        error = self._rejected([PRODUCT_SIX[0], ('18:02', '虚构语文老师乙', 'qa-cn-teacher-b', PRODUCT_SIX[1][3])],
                               lambda refs: json.loads(PRODUCT_SIX_REPLY)['proposals'][:1], 'product-six-other-teacher')
        self.assertIn('学校补充要求未归到对应作业', error)
        self.doCleanups()
        self.setUp()
        error = self._rejected([('18:00', '语文老师甲', 'cn-teacher-a', '今晚朗读《荷塘》2遍；朗读《春》1遍。'),
                                ('18:02', '语文老师甲', 'cn-teacher-a', '刚才的朗读完成后还要请家长签字。')],
                               lambda refs: [self._proposal('今晚朗读《荷塘》2遍', refs, '语文', '今晚朗读《荷塘》2遍；朗读完成后请家长签字。'),
                                             self._proposal('朗读《春》1遍', refs[:1], '语文', '朗读《春》1遍。')],
                               'T01-variant-after-completion-two-antecedents')
        self.assertIn('学校补充要求未归到对应作业', error)


class PointerBackIdentityHoldoutTests(unittest.TestCase):
    """Root's R16 holdout and its neighbours, fictional, on the same run_once→Store→calendar path: one shared nickname
    proves no publisher, so a follow-up pointing back (刚刚的朗读还要家长签字) joins an earlier message's item only from the
    same stable sender id and source and the one message it can mean. A missing or another id, another source or an
    unclear object keeps the whole batch for the existing retry (no new budget, nothing saved, originals kept); a sole
    message without an id still stands as its own action. Fixed receipts prove only the program layer."""
    setUp, _use_replies, _proposal = DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies, DailyListFrozenTests._proposal
    _report, _run, _replay_adds_nothing, _job = (DailyListFrozenTests._report, DailyListFrozenTests._run,
                                                 DailyListFrozenTests._replay_adds_nothing, DailyListFrozenTests._job)
    _rejected = ContinuedSupplementVariantTests._rejected
    R16 = (('18:00', '今晚朗读《暮色》3遍。'), ('18:01', '刚刚的朗读还要家长签字。'))

    def _day(self, messages, day='2026-11-04'):
        """messages: (HH:MM, stable sender id or None when missing, text), all sent under one shared nickname."""
        payload = self.fixture.payload(cursor=str(100 + len(messages)))
        payload['messages'] = [dict(id=str(101 + i), message_order=str(101 + i), time=day + 'T' + hm + ':00+08:00', kind='text',
                                    sender='虚构语文老师', text=text, unread=False, **({'sender_id': p} if p else {}))
                               for i, (hm, p, text) in enumerate(messages)]
        self.store.ingest(payload)
        return payload, ['message:' + self.source['id'] + ':' + m['id'] for m in payload['messages']]

    def _r16(self, refs, quote='今晚朗读《暮色》3遍'):
        """R16-fixed-exchange.json's one receipt: one reading-and-signature item citing every given original."""
        return [fixtures.school_proposal(
            title_quote=quote, evidence=[dict(ref=r) for r in refs], learning_subject='语文', task_title='语文：' + quote,
            task_goal=quote + '；朗读后家长签字。', task_state='ready', task_reason='虚构固定回执，只验校验/保存/展示。',
            task_purpose='learning')]

    def _held(self, ids, first, case):
        error = self._rejected([(hm, i, text) for (hm, text), i in zip(((self.R16[0][0], first), self.R16[1]), ids)],
                               lambda refs: self._r16(refs, first.rstrip('。')), case)
        self.assertIn('学校补充要求未归到对应作业', error)

    def test_r16_one_nickname_without_sender_ids_merges_nothing(self):
        self._held((None, None), self.R16[0][1], 'R16-missing-ids')

    def test_one_nickname_with_one_missing_sender_id_merges_nothing(self):
        self._held((None, 'cn-teacher-a'), self.R16[0][1], 'R16-first-id-missing')

    def test_one_nickname_with_the_later_sender_id_missing_merges_nothing(self):
        self._held(('cn-teacher-a', None), self.R16[0][1], 'R16-later-id-missing')

    def test_one_nickname_with_another_sender_id_merges_nothing(self):
        self._held(('cn-teacher-a', 'cn-teacher-b'), self.R16[0][1], 'R16-other-id')

    def test_one_nickname_with_another_sender_id_merges_nothing_outside_the_ledger(self):
        # A sole noun-first reading stays with the general reader, the path R16 itself took.
        self._held(('cn-teacher-a', 'cn-teacher-b'), '《暮色》朗读3遍。', 'R16-other-id-noun-first')

    def test_the_same_stable_sender_id_keeps_one_item_with_both_originals(self):
        for first, case in (('今晚朗读《暮色》3遍。', 'R16-same-id'), ('《暮色》朗读3遍。', 'R16-same-id-noun-first')):
            with self.subTest(case):
                self.doCleanups()
                self.setUp()
                payload, refs = self._day([(self.R16[0][0], 'cn-teacher-a', first), (self.R16[1][0], 'cn-teacher-a', self.R16[1][1])])
                result, rows, listed, _ = self._run(payload, self._r16(refs, first.rstrip('。')), case)
                self.assertEqual((result['failed'], result['processed'], len(rows)), (0, 2, 1))
                item, = listed
                self.assertEqual(item['publications'], refs, 'both originals stay cited')
                self.assertIn('签字', item['body'])
                self._replay_adds_nothing(case)

    def test_messages_without_sender_ids_still_stand_as_their_own_actions(self):
        payload, refs = self._day([('18:00', None, self.R16[0][1]), ('18:01', None, '抄写生字一遍。')])
        result, rows, listed, _ = self._run(payload, [
            self._proposal('今晚朗读《暮色》3遍', refs[:1], '语文', '今晚朗读《暮色》3遍。'),
            self._proposal('抄写生字一遍', refs[1:], '语文', '抄写生字一遍。')], 'R16-missing-ids-own-actions')
        self.assertTrue(all('sender_id' not in m for m in payload['messages']))
        self.assertEqual((result['failed'], result['processed'], len(rows), len(listed)), (0, 2, 2, 2))
        self.assertEqual(sorted(i['publications'] for i in listed), [refs[:1], refs[1:]], 'each keeps only its own original')
        self._replay_adds_nothing('R16-missing-ids-own-actions')

    def test_the_shared_check_needs_the_one_same_source_message_it_names(self):
        sent = dt.datetime(2026, 11, 4, 18, tzinfo=agent.TZ)

        def unproven(*rows):
            evidence = [dict(ref='message:%s:%d' % (source, 101 + i), text=text, time=(sent + dt.timedelta(minutes=i)).isoformat(),
                             publisher=publisher, kind='text', content_incomplete=False, unread=False, attachments=[],
                             message_order=str(101 + i)) for i, (source, publisher, text) in enumerate(rows)]
            return agent._school_native_pointer_unproven(evidence, {e['ref'] for e in evidence})
        g, a, follow = 'synthetic-group', 'publisher:a', self.R16[1][1]
        self.assertFalse(unproven((g, a, '《暮色》朗读3遍。'), (g, a, follow)))
        for rows in (((g, '', '《暮色》朗读3遍。'), (g, '', follow)),  # one nickname, both ids missing
                     ((g, a, '《暮色》朗读3遍。'), (g, 'publisher:b', follow)),  # another id
                     ((g, a, '《暮色》朗读3遍。'), ('synthetic-other', a, follow)),  # another source
                     ((g, a, '《暮色》背诵3遍。'), (g, a, follow)),  # an object no cited original names
                     ((g, a, '《暮色》朗读3遍。'), (g, a, '《春》朗读1遍。'), (g, a, follow))):  # two it could mean
            self.assertTrue(unproven(*rows), rows)
        self.assertFalse(unproven((g, '', follow)), 'a follow-up cited alone keeps the general checks')
        self.assertFalse(unproven((g, '', '今晚朗读《暮色》3遍。'), (g, '', '抄写生字一遍。')), 'no pointer, no new check')

    def test_an_order_after_the_object_keeps_the_one_message_identity(self):
        sent = dt.datetime(2026, 11, 4, 18, tzinfo=agent.TZ)

        def unproven(*rows):
            evidence = [dict(ref='message:%s:%d' % (source, 11 + i), text=text, time=(sent + dt.timedelta(minutes=2 * i)).isoformat(),
                             publisher=publisher, kind='text', content_incomplete=False, unread=False, attachments=[],
                             message_order=str(11 + i)) for i, (source, publisher, text) in enumerate(rows)]
            return agent._school_native_pointer_unproven(evidence, {e['ref'] for e in evidence})
        g, a, first, follow = 'synthetic-group', 'qa-cn-teacher', PRODUCT_SIX[0][3], PRODUCT_SIX[1][3]
        self.assertFalse(unproven((g, a, first), (g, a, follow)))
        self.assertFalse(unproven((g, a, first), (g, a, '刚刚的朗读做完以后请家长签字。')))
        for rows in (((g, '', first), (g, '', follow)),  # one nickname, both ids missing
                     ((g, a, first), (g, 'qa-cn-teacher-b', follow)),  # another teacher
                     ((g, a, first), ('synthetic-other', a, follow)),  # another source or child binding
                     ((g, a, '语文今晚背诵《荷塘》2遍。'), (g, a, follow)),  # an object no cited original names
                     ((g, a, first), (g, a, '今晚朗读《春》1遍。'), (g, a, follow)),  # two it could mean
                     ((g, a, first), (g, a, '刚才的朗读完成后明天还要家长签字。'))):  # a day the order word cannot hide
            self.assertTrue(unproven(*rows), rows)


class ReplySlipChoiceVariantTests(unittest.TestCase):
    """Fictional variants of T10's shared cause, not frozen contract cases, on the same run_once→Store→calendar path: a choice
    between answers, people or receivers (quoted or not, options of any length, the activity's own days inside options) and
    the same item's undated signing step (with or without 然后/再) keep both role days; a real day alternative, a condition,
    options naming this item's own role or day, or another item's day still leave the day unknown. Fixed receipts again
    prove only the program layer."""
    setUp, _use_replies, _day, _proposal = (DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies,
                                            DailyListFrozenTests._day, DailyListFrozenTests._proposal)
    _report, _run, _replay_adds_nothing = DailyListFrozenTests._report, DailyListFrozenTests._run, DailyListFrozenTests._replay_adds_nothing
    HANDBACK = '孩子11月5日早上交给班主任。'

    def _slip(self, text, case, goal, submission='孩子明早交给班主任'):
        payload, refs = self._day([('19:05', '班主任', 'head-teacher', text)])
        slip = self._proposal(text.rstrip('。'), refs, '', goal, due='2026-11-05', purpose='admin', submission=submission)
        return self._run(payload, [slip], case)

    def _both_roles(self, text, case, goal, words, **slip):
        result, rows, listed, (on_day, visible) = self._slip(text, case, goal, **slip)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual((item['kind'], item['category'], item['complete_on'], item['due_on'], item['due_kind']),
                         ('task', 'todo', '2026-11-04', '2026-11-05', 'handback'))
        for w in words: self.assertIn(w, item['body'])
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing(case)

    def test_another_choice_between_quoted_options_keeps_both_roles(self):
        self._both_roles('今晚请家长在《午餐意向单》勾选“同意”或“不同意”，然后签字；孩子明早交给班主任。', 'V-choice-quoted',
                         '今晚家长在《午餐意向单》勾选“同意”或“不同意”，然后签字；' + self.HANDBACK, ('“同意”', '“不同意”', '签字'))

    def test_three_options_and_a_then_signing_step_keep_both_roles(self):
        self._both_roles('今晚请家长在《社团报名表》圈选‘美术’、‘篮球’或‘合唱’，再签字；孩子明早交给班主任。', 'V-choice-three',
                         '今晚家长在《社团报名表》圈选‘美术’、‘篮球’或‘合唱’，再签字；' + self.HANDBACK, ('‘美术’', '‘篮球’', '‘合唱’', '签字'))

    def test_the_same_items_signing_step_without_a_choice_keeps_both_roles(self):
        self._both_roles('今晚请家长核对《通讯录信息表》，然后签字；孩子明早交回。', 'V-step-sign',
                         '今晚家长核对《通讯录信息表》，然后签字；孩子11月5日早上交回。', ('核对', '签字', '交回'), submission='孩子明早交回')

    def _unknown(self, text, case, goal):
        result, rows, listed, (on_day, visible) = self._slip(text, case, goal)
        self._report(case=case + '-outcome', listed=listed, result={k: result[k] for k in ('failed', 'processed', 'created')})
        item, = listed
        self.assertEqual((result['failed'], result['processed'], item['kind'], item['complete_on']), (0, 1, 'school', ''),
                         'kept for review: a day the original leaves open is never read as both role days')
        self.assertNotEqual(item['due_kind'], 'handback')

    def test_a_real_day_alternative_stays_unknown(self):
        self._unknown('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任。', 'V-day-alternative',
                      '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子11月5日或6日交给班主任。')

    def test_options_naming_the_activitys_days_keep_the_slips_own_roles(self):
        # Revised negative control (Root P5): the days inside ‘明天出发’或‘后天出发’ are the trip's answer, not this slip's; its
        # own 今晚…签字 and 明早交 stay outside the options. Options naming this slip's own role or day stay unknown below.
        self._both_roles('今晚请家长在《研学活动回执》勾选‘明天出发’或‘后天出发’，然后签字；孩子明早交给班主任。', 'V-day-options',
                         '今晚家长在《研学活动回执》勾选‘明天出发’或‘后天出发’，然后签字；' + self.HANDBACK, ('‘明天出发’', '‘后天出发’'))

    def test_a_conditional_handback_stays_unknown(self):
        self._unknown('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；如果参加，孩子明早交给班主任。', 'V-condition',
                      '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；如果参加，' + self.HANDBACK)

    def test_another_items_day_is_not_the_slips(self):
        text = '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；数学练习册明早交给数学老师。'
        payload, refs = self._day([('19:05', '班主任', 'head-teacher', text)])
        slip = self._proposal('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字', refs, '',
                              '今晚家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字。', purpose='admin')
        book = self._proposal('数学练习册明早交给数学老师', refs, '数学', '数学练习册11月5日早上交给数学老师。', due='2026-11-05')
        result, rows, listed, _ = self._run(payload, [slip, book], 'V-sibling-day')
        self._report(case='V-sibling-day-outcome', listed=listed, result={k: result[k] for k in ('failed', 'processed', 'created')})
        receipt, = [i for i in listed if '回执' in i['body']]
        workbook, = [i for i in listed if '练习册' in i['body']]
        self.assertEqual((receipt['complete_on'], receipt['due_on'], receipt['due_kind']), ('', '', ''), "the workbook's day is never the slip's")
        self.assertEqual((workbook['due_on'], workbook['due_kind']), ('2026-11-05', 'handback'))

    def test_the_role_reader_takes_a_closed_choice_and_the_same_items_signing_step(self):
        cited = lambda text: [dict(ref='message:s:1', text=text, time='2026-11-04T19:05:00+08:00')]
        read = lambda text: agent._school_role_days(text, cited(text), [])
        positives = ('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《午餐意向单》勾选“同意”或“不同意”，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《社团报名表》圈选‘美术’、‘篮球’或者‘合唱’，再签字；孩子明早交给班主任。',
                     '今晚请家长核对《通讯录信息表》，然后签字；孩子明早交回。',
                     # Revised controls: a 或 between people, receivers or unquoted answers and options holding the activity's
                     # own days name no day of this slip; the choice stays in its words for the family.
                     '今晚请家长或孩子在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》勾选参加或不参加，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘明天出发’或‘后天出发’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，然后签字；孩子明早交给班主任或课代表。',
                     '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，签字后拍照上传；孩子明早交纸质版。',
                     '今晚请家长在《参观回执》勾选‘同意参加本学期全部四次周末社区志愿服务活动’或‘不同意’，然后签字；孩子明早交回。')
        missed = [text for text in positives if read(text) != ({'2026-11-04'}, '2026-11-05')]
        self.assertEqual(missed, [], 'each closed choice or same-item signing step keeps both role days')

    def test_the_role_reader_still_leaves_open_days_unknown(self):
        cited = lambda text: [dict(ref='message:s:1', text=text, time='2026-11-04T19:05:00+08:00')]
        read = lambda text, others=(): agent._school_role_days(text, cited(text), list(others))
        negatives = ('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任。',  # a real day alternative
                     '今晚或明晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》签字；孩子明天交或后天交给班主任。',
                     '今晚请家长在《参观回执》签字后拍照上传或明早交纸质版；孩子明早交给班主任。',  # a way bound to its own day
                     '今晚请家长在《研学活动回执》勾选‘明早交’或‘后天交’，然后签字。',  # options setting this slip's own day
                     '今晚请家长在《研学活动回执》签字；孩子‘明早’或‘后天’交给班主任。',  # its handback day only in options
                     '今晚请家长在《研学活动回执》勾选‘同意签字’或‘不同意’，然后签字；孩子明早交给班主任。',  # an option naming a role
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或许交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；如果参加，孩子明早交给班主任。',  # a condition
                     '若参加，今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任吗？',  # a question
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；回执取消，明早不用交。',  # a withdrawal
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早可能交给班主任。',
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后交给班主任；孩子明早交回。',  # a handback step
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，明早签字；孩子明早交给班主任。',  # a step of its own day
                     '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’；孩子明早交给班主任。',  # no finishing step
                     '后天请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。')  # done after its handback
        self.assertEqual([text for text in negatives if read(text) is not None], [])
        shared = '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早交给班主任。'
        self.assertIsNone(read(shared, ['孩子明早交给班主任']), "another proposal's quote of the range")
        other = cited(shared) + [dict(ref='message:s:2', text='研学活动改到后天。', time='2026-11-04T19:30:00+08:00')]
        self.assertIsNone(agent._school_role_days(shared, other, []), 'another cited original naming a day')


class RootRoleHoldoutTests(unittest.TestCase):
    """Root's independent fictional role-day holdouts, on the same run_once→Store→calendar path with Root's receipt shape:
    the goal is the original and the submission its last sentence word for word (no receiver added). A non-day choice
    (answers, receivers, people, ways) keeps both role days and stays in the family's words; a day the original leaves to
    choose stays open in both the stored item and its listed projection, while another role's explicit day is kept."""
    setUp, _use_replies, _day, _proposal = (DailyListFrozenTests.setUp, DailyListFrozenTests._use_replies,
                                            DailyListFrozenTests._day, DailyListFrozenTests._proposal)
    _report, _run, _replay_adds_nothing = DailyListFrozenTests._report, DailyListFrozenTests._run, DailyListFrozenTests._replay_adds_nothing

    def _root(self, case, text, due='2026-11-05'):
        payload, refs = self._day([('19:05', '虚构班主任', 'root-fiction-teacher', text)])
        slip = self._proposal(text.rstrip('。'), refs, '', text, due=due, purpose='admin', submission=text.rsplit('；', 1)[-1].rstrip('。'))
        return self._run(payload, [slip], case)

    def _clear(self, case, text, kept):
        result, rows, listed, (on_day, visible) = self._root(case, text)
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed  # one slip: no second task, no trip or receiver chosen for the family
        self.assertEqual((item['kind'], item['category'], item['complete_on'], item['due_on'], item['due_kind']),
                         ('task', 'todo', '2026-11-04', '2026-11-05', 'handback'))
        self.assertEqual(item['body'], text)
        self.assertIn(kept, item['title'], 'the choice stays in its own words')
        self.assertEqual(on_day, [item['title']])
        self._replay_adds_nothing(case)

    def test_p2_a_receiver_choice_is_no_day_choice(self):
        self._clear('ROOT-P2', '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，然后签字；孩子明早交给班主任或课代表。', '交给班主任或课代表')

    def test_p3_the_same_items_signing_step_needs_no_then(self):
        self._clear('ROOT-P3', '今晚请家长在《参观回执》勾选‘同意’或‘不同意’，签字后拍照上传；孩子明早交纸质版。', '签字后拍照上传')

    def test_p4_unquoted_answers_are_as_clear(self):
        self._clear('ROOT-P4', '今晚请家长在《研学活动回执》勾选参加或不参加，然后签字；孩子明早交给班主任。', '勾选参加或不参加')

    def test_p5_the_trips_days_inside_options_are_not_the_slips(self):
        self._clear('ROOT-P5', '今晚请家长在《出行意向回执》勾选‘明天出发’或‘后天出发’，然后签字；孩子明早交回执给班主任。',
                    '‘明天出发’或‘后天出发’')

    def _open(self, case, text, due, field, explicit):
        result, rows, listed, _ = self._root(case, text, due)
        self._report(case=case + '-outcome', listed=listed, stored=[dict(state=r['state'], due=r['due']) for r in rows])
        self.assertEqual((result['failed'], result['processed']), (0, 1))
        item, = listed
        self.assertEqual(item[field], '', 'a day the original leaves to choose is never one certain day')
        self.assertEqual(item['body'], text)
        return item, rows

    def test_n1_a_signing_day_choice_keeps_only_the_explicit_handback(self):
        item, _ = self._open('ROOT-N1', '今晚或明晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子后天交给班主任。',
                             '2026-11-06', 'complete_on', '2026-11-06')
        self.assertEqual((item['due_on'], item['due_kind']), ('2026-11-06', 'handback'), 'the explicit handback day is kept')

    def test_n2_a_handback_day_choice_is_open_in_the_stored_item_and_its_projection(self):
        item, rows = self._open('ROOT-N2', '今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任。',
                                '2026-11-05', 'due_on', '')
        self.assertEqual((item['kind'], item['due_kind']), ('school', ''), 'kept for review with no deadline shown')
        self.assertEqual([r['due'] for r in rows], [''], 'the stored item holds no due either')

    def test_n3_a_condition_keeps_its_completion_open(self):
        item, _ = self._open('ROOT-N3', '如果参加，今晚请家长在《研学活动回执》签字；如果不参加，明晚再填写；孩子后天交给班主任。',
                             '2026-11-06', 'complete_on', '2026-11-06')
        self.assertEqual((item['due_on'], item['due_kind']), ('2026-11-06', 'handback'))

    def test_the_deadline_reader_keeps_a_day_choice_open_and_a_single_day(self):
        import family_agenda
        sent = '2026-11-04'
        self.assertEqual(family_agenda.deadline('孩子明早或后天交给班主任', sent), '')
        self.assertEqual(family_agenda.deadline('今晚请家长在《研学活动回执》勾选‘参加’或‘不参加’，然后签字；孩子明早或后天交给班主任', sent), '')
        self.assertEqual(family_agenda.deadline('孩子明天交或后天交给班主任', sent), '')
        self.assertEqual(family_agenda.deadline('孩子后天交给班主任', sent), '2026-11-06', 'an explicit single day stays')
        self.assertEqual(family_agenda.deadline('今晚或明晚请家长签字；孩子后天交给班主任', sent), '2026-11-06',
                         "another role's day choice does not clear this explicit day")
        self.assertEqual(family_agenda.deadline('孩子后天交给班主任或课代表', sent), '2026-11-06', 'a receiver choice names no day')


def serve_t02(port):
    """Browser fixture: T02 saved by the real run_once into this disposable Store, read through the real app HTTP server
    as of 2026-11-04 20:00 Asia/Shanghai. Opening a page calls no model; no collector, device or household path is used."""
    case = DailyListFrozenTests('test_t02_independent_supply_is_its_own_admin_item_on_its_own_day')
    case.setUp()
    try:
        payload, proposals = case._t02_batch(t06=True)
        case._run(payload, proposals, 'T02-served')
        app, fixed = case.app, case.now

        def deny(*args, **kwargs):
            raise AssertionError('opening the list or calendar must not call a model')
        app.family_llm._chat_json = deny

        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                value = fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
                return cls(value.year, value.month, value.day, value.hour, value.minute, value.second, tzinfo=value.tzinfo)

            def date(self):
                return FrozenDate(self.year, self.month, self.day)

        class FrozenDate(dt.date):
            @classmethod
            def today(cls):
                return cls(fixed.year, fixed.month, fixed.day)
        dt.datetime, dt.date = FrozenDateTime, FrozenDate
        # The fixture's fictional family rules stay the only documents read; pages come from this source tree.
        docs = {name: (app.ROOT / name).read_text() for name in ('家庭运行规则.md',)}
        app.read = lambda name: docs.get(name, '')
        app.ROOT = Path(__file__).resolve().parent
        app.prepare_assets()
        server = app.ThreadingHTTPServer(('127.0.0.1', port), app.Handler)
        print('T02 Store served', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        case.doCleanups()


if __name__ == '__main__':
    import sys
    if sys.argv[1:2] == ['--serve-t02']:
        serve_t02(int(sys.argv[2]))
    else:
        unittest.main()

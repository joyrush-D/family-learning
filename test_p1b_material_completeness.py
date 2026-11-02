"""P1b: an original's requirements keep their own date roles and the same homework's submission (fictional development examples only)."""
import datetime as dt
import unittest
from unittest.mock import patch

import family_agent as agent

SENT='2026-11-08T18:00:00+08:00';REF='message:fictional-class:1'


def roles(quote,others=()):
    return agent._school_original_roles([dict(ref=REF,quote=quote)],[dict(ref=REF,time=SENT,text=quote)],list(others))


class OriginalDateRoleTests(unittest.TestCase):
    def test_completion_and_handback_are_two_roles_of_one_requirement(self):
        for quote in ('今晚（2026年11月8日）做练习册第7页第2–4题，每题写步骤；明早（11月9日早上）交。',
                      '今晚做练习册第7页第2–4题，每题写步骤；明早交。',
                      '今晚做练习册第7页第2–4题，每题写步骤，明天早上交。'):
            with self.subTest(quote=quote):self.assertEqual(roles(quote),({'2026-11-08'},'2026-11-09'))

    def test_morning_reading_check_is_the_check_role(self):
        self.assertEqual(roles('今晚朗读第8课三遍，明天早读查。'),({'2026-11-08'},'2026-11-09'))
        self.assertIn('check',agent._school_clause_roles('明天早读查'))
        self.assertNotIn('check',agent._school_clause_roles('今晚查资料'))

    def test_future_auxiliary_jiang_keeps_its_own_predicate(self):
        import family_agenda
        for clause in ('明天将完成社会调查','将完成调查报告','明天将完成调查'):
            with self.subTest(clause=clause):
                roles=agent._school_clause_roles(clause);self.assertNotIn('check',roles);self.assertIn('finish',roles)
        self.assertNotEqual(family_agenda.date_meaning('明天将完成社会调查','2026-11-09','2026-11-08'),'inspection')
        self.assertIn('check',agent._school_clause_roles('明早查'))
        self.assertIn('handback',agent._school_clause_roles('将回执交给班主任'))
        self.assertNotIn('handback',agent._school_clause_roles('将交通安全告知书签字'))

    def test_conflicting_or_unknown_days_stay_for_the_existing_date_checks(self):
        self.assertIsNone(roles('今晚做练习册第7页第2–4题，每题写步骤；明天（11月10日）交。'))
        self.assertIsNone(agent._school_bracket_restated('明早（11月9日晚上）交','2026-11-08'))
        self.assertIsNone(agent._school_bracket_restated('今晚（11月8日）做第7页','') )
        self.assertEqual(agent._school_bracket_restated('今晚（11月8日）做第7页','2026-11-08'),'今晚做第7页')
        self.assertEqual(agent._school_bracket_restated('第7页第2–4题','2026-11-08'),'第7页第2–4题')

    def test_another_actions_quote_within_the_range_makes_it_shared(self):
        self.assertIsNone(roles('今晚做练习册第7页第2–4题，每题写步骤；明早交。',['每题写步骤']))


class SameHomeworkSubmissionTests(unittest.TestCase):
    brief=dict(title='语文：朗读第8课',goal='明天完成朗读第8课三遍，音频上传课堂平台。',purpose='learning',submission='音频上传课堂平台')

    def test_the_homeworks_own_upload_step_lends_its_words(self):
        self.assertTrue(agent._school_own_submission_sibling(self.brief,dict(task_purpose='admin',task_title='朗读音频提交',task_goal='音频上传课堂平台。')))

    def test_another_subjects_upload_or_a_receipt_stays_apart(self):
        for other in (dict(task_purpose='admin',task_title='数学：练习册照片上传',task_goal='数学练习册第7页照片上传课堂平台。'),
                      dict(task_purpose='admin',task_title='家长回执',task_goal='今晚选参加或不参加并签字，孩子周五交。'),
                      dict(task_purpose='learning',task_title='朗读音频提交',task_goal='音频上传课堂平台。')):
            with self.subTest(other=other['task_title']):self.assertFalse(agent._school_own_submission_sibling(self.brief,other))
        self.assertFalse(agent._school_own_submission_sibling(dict(self.brief,submission=''),dict(task_purpose='admin',task_title='朗读音频提交',task_goal='音频上传课堂平台。')))


class OwnSubmissionStepSpanTests(unittest.TestCase):
    text='英语：每轮先听示范再朗读第6课三轮，末轮录音上传作业栏目。数学：练习册第9页照片上传作业栏目。'

    def test_the_step_in_the_items_own_sentence_is_its_own(self):
        self.assertTrue(agent._school_own_step_quote('每轮先听示范再朗读第6课三轮',self.text,'末轮录音上传作业栏目'))

    def test_another_sentence_subject_negation_or_third_quote_stays_apart(self):
        quote='每轮先听示范再朗读第6课三轮'
        self.assertFalse(agent._school_own_step_quote(quote,self.text,'练习册第9页照片上传作业栏目'))
        self.assertFalse(agent._school_own_step_quote(quote,'英语：每轮先听示范再朗读第6课三轮，数学练习册照片上传作业栏目。','数学练习册照片上传作业栏目'))
        self.assertFalse(agent._school_own_step_quote(quote,'英语：每轮先听示范再朗读第6课三轮，录音不用上传作业栏目。','录音不用上传作业栏目'))
        self.assertFalse(agent._school_own_step_quote(quote,self.text,'末轮录音上传作业栏目',['末轮录音']))


import test_agent


class SameHomeworkFlowTests(test_agent.AgentTests):
    """select -> save -> refresh -> manual task -> repeat, on the fictional store test_agent already builds (only this test runs here)."""

    def test_quoted_recording_step_keeps_the_whole_method_through_save_and_reopen(self):
        from test_agent import school_proposal
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        text='明天完成英语朗读第6课，每轮先听示范再朗读三轮，末轮录音上传作业栏目。'
        goal='英语朗读第6课，每轮先听示范再朗读三轮，末轮录音上传作业栏目。'
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        proposals=[school_proposal(title_quote='朗读第6课',due=due,evidence=[dict(ref=ref)],task_title='英语：朗读第6课',task_goal=goal,
                                   task_state='ready',task_reason='明确朗读及其提交。',task_purpose='learning',task_submission='末轮录音上传作业栏目'),
                   school_proposal(title_quote='末轮录音上传作业栏目',due=due,evidence=[dict(ref=ref)],task_title='朗读录音上传',
                                   task_goal='录音上传作业栏目。',task_state='ready',task_reason='同一朗读作业的提交步骤。',task_purpose='admin')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)],
                                school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([item['plan']['school_task']['state'] for item in items],['ready','review'])
        for words in ('每轮先听示范','三轮','末轮录音上传作业栏目'):self.assertIn(words,items[0]['body'])
        key='synthetic-p1b-recording-step';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved items need no model')):
            collected=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        self.assertEqual((collected['created'],repeated['created']),(1,0))
        with self.app.connect() as c:
            actions=[r['action'] for r in c.execute('SELECT action FROM manual_tasks')]
        self.assertEqual(len(actions),1)
        for words in ('每轮先听示范','三轮','末轮录音上传作业栏目'):self.assertIn(words,actions[0])


import json
import test_image_original_date_scope as scope
import test_daily_list_whole_day as whole
_ScopeBase=next(v for v in vars(scope).values() if isinstance(v,type) and issubclass(v,unittest.TestCase) and hasattr(v,'_chain'))
ROLE_OLD='2026年11月4日晚听音频跟读Unit 7第3至10个单词，每个单词跟读3遍；不用抄写。'
ROLE_NEW='2026年11月4日晚听音频跟读Unit 7第3至10个单词，每个单词跟读3遍，不用抄写，2026年11月5日早上交。'


class OriginalRoleChainTests(_ScopeBase):
    """The real image-original chain (save_upload -> message_attachment -> reader -> original actions -> Store -> list -> reopen)
    with a fictional requirement holding its own completion and handback days beside a same-page dictation of its own day."""

    def test_completion_and_handback_roles_reach_the_day_view_and_reopen(self):
        self._roles(ROLE_NEW)

    def test_matching_brackets_give_the_same_roles(self):
        self._roles('今晚（2026年11月4日）听音频跟读Unit 7第3至10个单词，每个单词跟读3遍，不用抄写，明早（11月5日早上）交。')

    def test_a_conflicting_bracket_is_never_a_due_or_role(self):
        self._roles('今晚听音频跟读Unit 7第3至10个单词，每个单词跟读3遍，不用抄写，明早（11月6日早上）交。',conflict=True)

    def _roles(self,text,conflict=False):
        fix=json.loads(json.dumps(scope.FIX,ensure_ascii=False).replace(ROLE_OLD,text))
        real=agent._school_original_actions
        def cite(store,row,result,parts,*args,**kwargs):
            # The controlled model stub cites each read part by the id this run's reader gave it (ids follow the read text).
            ids={p['text']:p['id'] for p in parts}
            for action in result.get('actions',[]):
                for quote in action.get('basis',[]):quote['part']=ids.get(quote.get('text'),quote.get('part'))
            return real(store,row,result,parts,*args,**kwargs)
        with patch.object(scope,'FIX',fix),patch.object(agent,'_school_original_actions',cite):self._chain()
        follow=self._follow(self._db()[0])
        if conflict:
            # 明早 and its bracket name two days: no due is taken from either and no role is projected; the read words stay.
            self.assertNotEqual(follow['due'],'2026-11-06');self.assertIn('11月6日',json.loads(follow['plan'])['school_original_action']['requirements'][0]['text'])
            if follow['state']=='accepted':self.assertEqual(json.loads(follow['plan'])['school_task']['state'],'ready')
            else:self.assertEqual(json.loads(follow['plan'])['school_task']['state'],'review')
            return
        self.assertEqual((follow['state'],follow['due'],json.loads(follow['plan'])['school_task']['state']),('accepted','2026-11-05','ready'))
        def agenda():
            mine,_=whole.WholeDayTests._list(self)
            items={('follow' if '跟读' in i['title']+i['body'] else 'dictation'):i['agenda'] for i in mine
                   if [p['ref'] for p in i['agenda'].get('publications',[])]==[self.ref]}
            return items
        first=agenda()
        self.assertEqual((first['follow']['complete_on'],first['follow']['due_on']),(scope.DAY,'2026-11-05'),first['follow'])
        self.assertEqual((first['dictation']['due_on'],first['dictation'].get('due_kind')),('2026-11-05','inspection'))
        made=self._db();agent.run_once(self.app,self.now+dt.timedelta(minutes=2))  # reopen: no call, write or duplicate
        self.assertEqual(self._db(),made)
        self.assertEqual(agenda(),first)


def load_tests(loader,tests,pattern):
    suite=unittest.TestSuite()
    for case in (OriginalDateRoleTests,SameHomeworkSubmissionTests,OwnSubmissionStepSpanTests):suite.addTests(loader.loadTestsFromTestCase(case))
    suite.addTest(SameHomeworkFlowTests('test_quoted_recording_step_keeps_the_whole_method_through_save_and_reopen'))
    for name in ('test_completion_and_handback_roles_reach_the_day_view_and_reopen','test_matching_brackets_give_the_same_roles','test_a_conflicting_bracket_is_never_a_due_or_role'):
        suite.addTest(OriginalRoleChainTests(name))
    return suite


if __name__=='__main__':
    unittest.main()

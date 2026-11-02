"""P1b: an original's requirements keep their own date roles and the same homework's submission (fictional development examples only)."""
import datetime as dt
import json
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

    def test_a_recording_of_another_lesson_or_an_earlier_recording_is_another_object(self):
        text='英语：朗读Unit 5课文三遍，并把Unit 4的朗读录音上传作业栏目。'
        self.assertFalse(agent._school_own_step_quote('朗读Unit 5课文三遍',text,'把Unit 4的朗读录音上传作业栏目'))
        self.assertFalse(agent._school_own_step_quote('朗读第6课三遍','语文：朗读第6课三遍，把昨天录好的朗读音频上传作业栏目。','把昨天录好的朗读音频上传作业栏目'))
        self.assertFalse(agent._school_own_step_quote('朗读《春》三遍','语文：朗读《春》三遍，《夏》的朗读录音上传作业栏目。','《夏》的朗读录音上传作业栏目'))
        self.assertTrue(agent._school_own_step_quote('朗读Unit 5课文三遍','英语：朗读Unit 5课文三遍，Unit 5录音上传作业栏目。','Unit 5录音上传作业栏目'))


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
        # The step is proven this reading's own submission: it is not another pending card but joins the reading once accepted.
        self.assertEqual([item['plan']['school_task']['state'] for item in items],['ready','ready'])
        self.assertEqual(items[1]['plan']['school_task']['submission_of'],dict(title=items[0]['title'],body=items[0]['body'],due=due))
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
        with self.store._db() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM agent_items WHERE job_id=? ORDER BY title',(key,))]
        reading=next(r for r in rows if r['title']==items[0]['title']);step=next(r for r in rows if r is not reading)
        # No pending card stays on any day or after reopen; the step row keeps its own evidence and points at the reading.
        self.assertEqual(sorted(r['state'] for r in rows),['accepted','accepted'])
        self.assertEqual((step['task_id'],json.loads(step['plan']).get('school_duplicate_of')),(reading['task_id'],reading['id']))
        self.assertEqual(json.loads(step['evidence']),json.loads(reading['evidence']))

    def test_another_lessons_recording_upload_stays_its_own_item_through_save_and_reopen(self):
        from test_agent import school_proposal
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        text='明天完成英语朗读Unit 5课文三遍，并把Unit 4的朗读录音上传作业栏目。'
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        proposals=[school_proposal(title_quote='朗读Unit 5课文三遍',due=due,evidence=[dict(ref=ref)],task_title='英语：朗读Unit 5课文',
                                   task_goal='英语朗读Unit 5课文三遍，并把Unit 4的朗读录音上传作业栏目。',task_state='ready',task_reason='明确朗读。',
                                   task_purpose='learning',task_submission='把Unit 4的朗读录音上传作业栏目'),
                   school_proposal(title_quote='把Unit 4的朗读录音上传作业栏目',due=due,evidence=[dict(ref=ref)],task_title='英语：上传Unit 4朗读录音',
                                   task_goal='把Unit 4的朗读录音上传作业栏目。',task_state='ready',task_reason='另一份材料的上传。',task_purpose='admin')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)],
                                school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(len(items),2,[i['body'] for i in items])
        reading,upload=items
        self.assertIn('Unit 5',reading['body']);self.assertIn('三遍',reading['body']);self.assertNotIn('Unit 4',reading['body'])
        self.assertIn('Unit 4',upload['body']);self.assertIn('上传作业栏目',upload['body'])
        key='synthetic-p1b-other-lesson-upload';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved items need no model')):
            agent._refresh_school(self.app,self.store,self.now,0);agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        with self.app.connect() as c:
            bodies=[r['action'] for r in c.execute('SELECT action FROM manual_tasks')]
        self.assertFalse([b for b in bodies if 'Unit 5' in b and 'Unit 4' in b],bodies)  # the reading never carries the other upload
        with self.store._db() as c:
            plans=[json.loads(r['plan']) for r in c.execute('SELECT plan FROM agent_items WHERE job_id=?',(key,))]
        self.assertFalse([p for p in plans if p.get('school_duplicate_of') or p['school_task'].get('submission_of')])  # another object


import json
import test_image_original_date_scope as scope
import test_daily_list_whole_day as whole
_ScopeBase=next(v for v in vars(scope).values() if isinstance(v,type) and issubclass(v,unittest.TestCase) and hasattr(v,'_chain'))
ROLE_OLD='2026年11月4日晚听音频跟读Unit 7第3至10个单词，每个单词跟读3遍；不用抄写。'
ROLE_NEW='2026年11月4日晚听音频跟读Unit 7第3至10个单词，每个单词跟读3遍，不用抄写，2026年11月5日早上交。'


class ResourceTimeTests(unittest.TestCase):
    def test_only_a_clause_giving_out_a_material_drops_its_day(self):
        free=agent._school_resource_time_free
        self.assertEqual(free('周三前签字并交回，配套空白表11月3日发放，'),'周三前签字并交回，')
        for kept in ('11月6日发放后当天填好交回。','明天交给数学老师。','11月6日交回回执，11月7日交回第二份。'):
            with self.subTest(kept=kept):self.assertEqual(free(kept),kept)


class OriginalRoleChainTests(_ScopeBase):
    """The real image-original chain (save_upload -> message_attachment -> reader -> original actions -> Store -> list -> reopen)
    with a fictional requirement holding its own completion and handback days beside a same-page dictation of its own day."""

    def test_completion_and_handback_roles_reach_the_day_view_and_reopen(self):
        self._roles(ROLE_NEW)

    def test_matching_brackets_give_the_same_roles(self):
        self._roles('今晚（2026年11月4日）听音频跟读Unit 7第3至10个单词，每个单词跟读3遍，不用抄写，明早（11月5日早上）交。')

    def test_a_material_issue_day_in_the_same_line_is_no_role_or_due(self):
        # Its completion and handback days stay its roles; the day the audio was given out is information only.
        self._roles('2026年11月4日晚听音频跟读Unit 7第3至10个单词，每个单词跟读3遍，不用抄写，跟读音频已于2026年11月3日下发，2026年11月5日早上交。')

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


import copy
import family_llm

R_DICT='2026年11月5日英语课参加听写。'
R_SHEET='2026年11月4日晚完成英语练习纸第二部分。'
U_RES='跟读用的音频未随图片附上，需家长另行获取音频。'
U_READ='练习纸第二部分要做的题号看不清。'


class UncertaintyScopeValidatorTests(unittest.TestCase):
    ident='0'*32

    def _check(self,scopes):
        value=dict(originals=[dict(upload_id=self.ident,title='英语作业',note='三项要求。',uncertainties=[U_RES,U_READ],
                                   requirements=[ROLE_OLD,R_DICT,R_SHEET],uncertainty_scopes=scopes)])
        return family_llm.validate_school_material(value,original_ids=[self.ident],require_requirements=True)

    def test_only_exact_doubts_and_own_lines_are_a_scope(self):
        kept=self._check([dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource'),
                          dict(uncertainty=U_READ,requirements=['练习纸第二部分'],kind='reading')])
        self.assertEqual(kept['originals'][0]['uncertainty_scopes'],[dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource')])
        self.assertEqual(kept['originals'][0]['uncertainties'],[U_RES,U_READ])  # the unscoped doubt keeps its words
        again=family_llm.validate_school_material(kept,original_ids=[self.ident],require_requirements=True)
        self.assertEqual(again,kept)  # a saved receipt reads back unchanged
        twice=self._check([dict(uncertainty=U_READ,requirements=[R_SHEET],kind='reading'),dict(uncertainty=U_READ,requirements=[R_DICT],kind='reading')])
        self.assertEqual(twice['originals'][0]['uncertainty_scopes'],[])
        for bad in ([dict(uncertainty=U_READ,requirements=[],kind='reading')],[dict(uncertainty=U_READ,requirements=[R_SHEET],kind='other')],'x'):
            with self.subTest(bad=bad),self.assertRaises(family_llm.LLMDraftError):self._check(bad)

    def test_a_resource_claim_naming_a_reading_gap_is_a_reading_gap(self):
        for doubt in (U_RES,'配套空白表未随原件附上，需家长另行打印。','签字单为纸本，未随附件发送。'):
            with self.subTest(doubt=doubt):self.assertEqual(agent._school_doubt_kind(doubt,'resource'),'resource')
        for doubt in (U_READ,'朗读音频对应第几课不明确。','通知提到的附件未收到。','签字单日期看不清。','空白表要填写的内容不清楚。','原件缺第2页。'):
            with self.subTest(doubt=doubt):self.assertEqual(agent._school_doubt_kind(doubt,'resource'),'reading')
        self.assertEqual(agent._school_doubt_kind(U_RES,'reading'),'reading')

    def test_a_line_stating_its_work_is_not_held_by_a_missing_question_text_but_an_unknown_range_is(self):
        kind=agent._school_doubt_kind;line='数学：完成练习册第7页第2至4题，每题写步骤，11月5日交。'
        for doubt in ('练习册第7页电子题面未上传，无法核对题目内容。','参考答案未上传，之后无法核对。'):
            with self.subTest(doubt=doubt):self.assertEqual(kind(doubt,'resource',[line]),'resource')
        for doubt,lines in (('附件未上传，题目内容无法读取。',['完成附件所列练习题。']),('第8页题面未上传。',[line]),('练习册题面未上传。',['完成练习册。']),
                            ('第7页要做哪几题不清楚，参考答案也未上传。',['完成练习册第7页。']),('朗读音频未附，截止日期未注明。',['朗读第3课三遍。'])):
            with self.subTest(doubt=doubt):self.assertEqual(kind(doubt,'resource',lines),'reading')


class DoubtViewTests(unittest.TestCase):
    def test_only_its_own_lines_and_unscoped_doubts_reach_an_action(self):
        a=dict(ref='message:s:1',upload_ids=['u1'],text='甲',requirement=True);b=dict(a,text='乙');other=dict(a,upload_ids=['u2'])
        gap='本原件后续第4页仍待整理：处理范围'  # a deferred page group is never a scoped doubt
        value=dict(uncertainties=['甲的朗读音频未附',U_READ,gap],doubt_scopes=[
            dict(ref='message:s:1',upload_id='u1',pages=[1],uncertainty='甲的朗读音频未附',requirements=['甲'],kind='resource'),
            dict(ref='message:s:1',upload_id='u1',pages=[1],uncertainty=U_READ,requirements=['乙'],kind='reading')])
        view=agent._school_doubt_view
        self.assertEqual((view(value,[a])['uncertainties'],view(value,[a])['resource_uncertainties']),([gap],['甲的朗读音频未附']))
        self.assertEqual(view(value,[b])['uncertainties'],[U_READ,gap])
        self.assertEqual(view(value,[other])['uncertainties'],[gap])  # the same words in another upload are not its line
        self.assertEqual(view(value,[])['uncertainties'],[gap])
        old=dict(uncertainties=['甲的朗读音频未附']);self.assertIs(view(old,[a]),old)  # an old receipt is unchanged

class ScopedDoubtImageChainTests(_ScopeBase):
    """C on the real image-original chain (save_upload -> attach -> reader receipt -> saved draft -> original actions ->
    Store -> day list -> reopen): one original, three requirement lines, two doubts (fictional; controlled model stubs)."""

    @staticmethod
    def _receipt(fix,scopes):
        original=fix['call_1']['originals'][0]
        original['requirements'].append(R_SHEET);original['uncertainties']=[U_RES,U_READ]
        if scopes is not None:original['uncertainty_scopes']=scopes
        return fix

    def _scoped(self,scopes):
        fix=self._receipt(copy.deepcopy(scope.FIX),scopes)
        sheet=copy.deepcopy(fix['call_3']['actions'][1])
        sheet.update(title='英语：练习纸第二部分',goal=R_SHEET,reason='原件第三项要求。',due='2026-11-04',existing_item_id='',basis=[dict(part='',text=R_SHEET)])
        fix['call_3']['actions'].append(sheet)
        real=agent._school_original_actions
        def cite(store,row,result,parts,*args,**kwargs):
            ids={p['text']:p['id'] for p in parts}
            for action in result.get('actions',[]):
                for quote in action.get('basis',[]):quote['part']=ids.get(quote.get('text'),quote.get('part'))
            return real(store,row,result,parts,*args,**kwargs)
        with patch.object(scope,'FIX',fix),patch.object(agent,'_school_original_actions',cite):self._chain()
        found={}
        for r in self._db()[0].values():
            action=json.loads(r['plan']).get('school_original_action') or {}
            if action.get('requirements'):found[action['requirements'][0]['text']]=r
        self.assertEqual(set(found),{ROLE_OLD,R_DICT,R_SHEET})
        with self.store._db() as c:
            saved=json.loads(c.execute("SELECT payload FROM agent_message_drafts WHERE message_id='503'").fetchone()['payload'])
        self.assertEqual(saved['originals'][0]['uncertainties'],[U_RES,U_READ])  # the reader's doubts stay word for word
        return found

    @staticmethod
    def brief(row):return json.loads(row['plan'])['school_task']

    def _request(self):
        # The actual original-actions request this normal chain sent (recorded by the stubbed model entry, 0 API).
        calls=[c for c in self.model.call_args_list if (c.args[2] if len(c.args)>2 else c.kwargs.get('name'))=='family_school_task']
        self.assertEqual(len(calls),1);messages=calls[0].args[0]
        prompt=''.join(m['content'] for m in messages[:-1] if isinstance(m.get('content'),str))
        return prompt,{p['text']:p for p in json.loads(messages[-1]['content'])['original_parts'] if p.get('requirement')}

    def _doubts(self,parts):
        return {k:(p['reading_doubts'],p['resource_doubts'],p['unlocated_doubts']) for k,p in parts.items()}

    def _day(self):
        mine,_=whole.WholeDayTests._list(self)
        return sorted((i['title']+i['body'],i['kind'],i['status'],bool(i.get('task_id')),i['agenda'].get('resource_needed',[])) for i in mine
                      if [p['ref'] for p in i['agenda'].get('publications',[])]==[self.ref])

    def test_each_doubt_holds_only_the_requirement_it_names(self):
        found=self._scoped([dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource'),dict(uncertainty=U_READ,requirements=[R_SHEET],kind='reading')])
        follow,dictation,sheet=found[ROLE_OLD],found[R_DICT],found[R_SHEET]
        self.assertEqual([r['state'] for r in (follow,dictation,sheet)],['accepted','accepted','pending'])
        self.assertEqual(self.brief(follow).get('resource_needed'),[U_RES]);self.assertIn(U_RES,self.brief(follow)['reason'])
        self.assertNotIn(U_READ,self.brief(follow)['reason']);self.assertIn('本项要求已读全',self.brief(follow)['reason'])
        self.assertNotIn('resource_needed',self.brief(dictation))
        prompt,parts=self._request()
        self.assertIn(agent._SCHOOL_PART_DOUBT_PROMPT.strip(),prompt)  # the rule reaches the mapper with the scoped lines
        self.assertEqual(self._doubts(parts),{ROLE_OLD:([],[U_RES],[]),R_DICT:([],[],[]),R_SHEET:([U_READ],[],[])})
        for doubt in (U_RES,U_READ):self.assertNotIn(doubt,self.brief(dictation)['reason'])
        self.assertEqual(self.brief(sheet)['state'],'review');self.assertIn(U_READ,self.brief(sheet)['reason']);self.assertNotIn(U_RES,self.brief(sheet)['reason'])
        day=self._day();shown={text:rest for text,*rest in day}
        # The two freed lines are the day's tasks; the line with its own reading gap is still a card to check, not a task.
        self.assertEqual([shown[next(t for t in shown if w in t)] for w in ('跟读','听写','练习纸')],
                         [['task','待跟进',True,[U_RES]],['task','待跟进',True,[]],['school','待核对',False,[]]])
        made=self._db();agent.run_once(self.app,self.now+dt.timedelta(minutes=2))  # reopen: no call, write or duplicate
        self.assertEqual(self._db(),made);self.assertEqual(self._day(),day)

    def test_an_old_receipt_without_scopes_keeps_every_doubt_original_wide(self):
        found=self._scoped(None)
        self.assertEqual({r['state'] for r in found.values()},{'pending'})
        self.assertEqual(set(map(str,self._doubts(self._request()[1]).values())),{str(([],[],[U_RES,U_READ]))})  # all unlocated
        for r in found.values():
            for doubt in (U_RES,U_READ):self.assertIn(doubt,self.brief(r)['reason'])

    def test_one_line_with_a_reading_and_a_resource_doubt_stays_review_in_its_own_words(self):
        found=self._scoped([dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource'),dict(uncertainty=U_READ,requirements=[ROLE_OLD],kind='reading')])
        follow=found[ROLE_OLD];reason=self.brief(follow)['reason']
        self.assertEqual([found[k]['state'] for k in (ROLE_OLD,R_DICT,R_SHEET)],['pending','accepted','accepted'])
        self.assertEqual(self.brief(follow)['state'],'review');self.assertIn(U_READ,reason);self.assertIn(U_RES,reason)
        self.assertNotIn('本项要求已读全',reason);self.assertEqual(self.brief(follow).get('resource_needed'),[U_RES])
        self.assertEqual(self._doubts(self._request()[1])[ROLE_OLD],([U_READ],[U_RES],[]))
        made=self._db();agent.run_once(self.app,self.now+dt.timedelta(minutes=2));self.assertEqual(self._db(),made)

    SCOPES=[dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource'),dict(uncertainty=U_READ,requirements=[R_SHEET],kind='reading')]

    def _later(self,minutes):
        # Later normal rounds: the reader returns a receipt with scopes; the stubbed mapper answers by the saved ids (0 API).
        real=agent._school_original_actions
        def cite(store,row,result,parts,*args,**kwargs):
            ids={p['text']:p['id'] for p in parts}
            with store._db() as c:
                known={json.loads(r['plan'])['school_original_action']['requirements'][0]['text']:r['id'] for r in c.execute("SELECT id,plan FROM agent_items WHERE kind='school'")
                       if (json.loads(r['plan']).get('school_original_action') or {}).get('requirements')}
            for action in result.get('actions',[]):
                for quote in action.get('basis',[]):quote['part']=ids.get(quote.get('text'),quote.get('part'))
                action['existing_item_id']=known.get(action['basis'][0]['text'],'')
            return real(store,row,result,parts,*args,**kwargs)
        with patch.object(agent,'_school_original_actions',cite):
            for m in minutes:agent.run_once(self.app,self.now+dt.timedelta(minutes=m))

    def _as_saved_before_scopes(self):
        # The stored receipt as code before the scope protocol wrote it: the same reading without the scope_requested mark.
        with self.store._db() as c:
            payload=json.loads(c.execute("SELECT payload FROM agent_message_drafts WHERE message_id='503'").fetchone()['payload'])
            self.assertEqual(payload.pop('scope_requested'),1)
            c.execute("UPDATE agent_message_drafts SET payload=? WHERE message_id='503'",(json.dumps(payload,ensure_ascii=False),))

    def _receipt_row(self):
        with self.store._db() as c:
            row=dict(c.execute("SELECT * FROM agent_message_drafts WHERE message_id='503'").fetchone())
            message=json.loads(c.execute("SELECT payload FROM agent_messages WHERE id='503'").fetchone()['payload'])
            job=dict(c.execute('SELECT * FROM agent_jobs WHERE id=?',(agent.family_media.draft_key(self.source,message),)).fetchone())
        return row,job

    def test_an_old_undecided_receipt_is_read_once_more_for_its_scopes(self):
        found=self._scoped(None);ids={k:r['id'] for k,r in found.items()}  # read before scopes: every line held
        self._as_saved_before_scopes();old,job=self._receipt_row()
        self.reads.side_effect=[scope.swap(self._receipt(copy.deepcopy(scope.FIX),self.SCOPES)['call_1'],self.upload)]
        self._later((2,3))
        self.assertEqual(self.reads.call_count,2)  # one bounded re-read through the normal reader
        self.assertEqual(json.loads(self._receipt_row()[0]['payload']).get('scope_requested'),1)
        new,job2=self._receipt_row();payload=json.loads(new['payload'])
        self.assertEqual(payload['originals'][0]['uncertainty_scopes'],self.SCOPES)
        self.assertEqual(payload['previous_scope_receipt'],dict(fingerprint=old['fingerprint'],payload=old['payload'],updated=old['updated']))
        self.assertEqual((job2['attempts'],job2['done']),(job['attempts']+1,1))  # the job's own budget, one more attempt
        rows={json.loads(r['plan'])['school_original_action']['requirements'][0]['text']:r for r in self._db()[0].values()
              if (json.loads(r['plan']).get('school_original_action') or {}).get('requirements')}
        self.assertEqual({k:r['id'] for k,r in rows.items()},ids)  # same items, same ids
        self.assertEqual([rows[k]['state'] for k in (ROLE_OLD,R_DICT,R_SHEET)],['accepted','accepted','pending'])
        self.assertIn(U_READ,self.brief(rows[R_SHEET])['reason'])
        made=self._db();self._later((4,5))  # later rounds: no read, call, write or duplicate
        self.assertEqual((self.reads.call_count,self._db()),(2,made))

    def test_a_decided_item_or_an_exhausted_job_keeps_the_old_receipt(self):
        for case in ('decided','exhausted'):
            with self.subTest(case=case):
                if case=='exhausted':self.setUp()
                found=self._scoped(None);self._as_saved_before_scopes();old,job=self._receipt_row()
                with self.store._db() as c:
                    if case=='decided':c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(found[R_DICT]['id'],))
                    else:c.execute('UPDATE agent_jobs SET attempts=? WHERE id=?',(agent.MAX_ATTEMPTS,job['id']))
                self.reads.side_effect=[scope.swap(self._receipt(copy.deepcopy(scope.FIX),self.SCOPES)['call_1'],self.upload)]
                self._later((2,3))
                self.assertEqual((self.reads.call_count,self._receipt_row()[0]),(1,old))  # no re-read; the old receipt stays

    def test_a_decision_while_the_supplement_reads_keeps_the_old_receipt(self):
        found=self._scoped(None);self._as_saved_before_scopes();old,job=self._receipt_row()
        receipt=scope.swap(self._receipt(copy.deepcopy(scope.FIX),self.SCOPES)['call_1'],self.upload)
        def read(*args,**kwargs):  # the parent dismisses one item while the model reads
            with self.store._db() as c:c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(found[R_DICT]['id'],))
            return copy.deepcopy(receipt)
        self.reads.side_effect=read
        self._later((2,))
        new,job2=self._receipt_row()
        self.assertEqual((self.reads.call_count,new),(2,old))  # read once; nothing of it is saved
        self.assertEqual(job2['attempts'],job['attempts']+1)  # the spent attempt stays on the job's own budget
        self._later((3,4));self.assertEqual((self.reads.call_count,self._receipt_row()[0]),(2,old))  # decided: never again

    def test_a_false_resource_or_unverifiable_pointer_never_frees_a_line(self):
        found=self._scoped([dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource'),dict(uncertainty=U_READ,requirements=[R_SHEET],kind='resource')])
        self.assertEqual([found[k]['state'] for k in (ROLE_OLD,R_DICT,R_SHEET)],['accepted','accepted','pending'])
        self.assertIn(U_READ,self.brief(found[R_SHEET])['reason'])

    def test_a_pointer_to_no_requirement_line_stays_original_wide(self):
        found=self._scoped([dict(uncertainty=U_RES,requirements=[ROLE_OLD],kind='resource'),dict(uncertainty=U_READ,requirements=['练习纸第二部分'],kind='reading')])
        self.assertEqual({r['state'] for r in found.values()},{'pending'})
        for r in found.values():self.assertIn(U_READ,self.brief(r)['reason'])


import test_school_pdf_evidence as pdf_evidence


class PdfOriginalRoleTests(pdf_evidence.SchoolPdfEvidenceTests):
    """A read PDF original's saved requirement reaches the day view with its own completion and handback days (fictional)."""

    def test_pdf_requirement_roles_reach_the_day_view_and_stay_on_reopen(self):
        keys=self.native_notice('p1b-pdf-roles');day=self.now.date();after=day+dt.timedelta(days=1)
        math='数学：%d月%d日晚完成练习册第7页第2至4题，每题写步骤，%d月%d日早上交。'%(day.month,day.day,after.month,after.day)
        chinese='语文：%d月%d日早读前背诵第3课第1段。'%(after.month,after.day)
        self.seed_groups(keys=keys,note='题面背景',uncertainties=[],requirements=[math,chinese])
        ident=self.candidate(keys=keys,ident='p1b-pdf-roles')
        def mapping(messages):
            context=json.loads(messages[-1]['content'])
            parts={p['text']:p['id'] for p in context['original_parts'] if p.get('requirement')}
            return {'actions':[dict(pdf_evidence.draft(goal=math),due=day.isoformat(),existing_item_id=ident,basis=[dict(part=parts[math],text=math)]),
                               dict(pdf_evidence.draft(goal=chinese),due=after.isoformat(),existing_item_id='',basis=[dict(part=parts[chinese],text=chinese)])]}
        self.refresh(mapping)
        row=self.item(ident)
        self.assertEqual(row['due'],after.isoformat(),row)  # its own handback day, though the reply named the completion day
        with self.store._db() as c:
            saved=agent.school_original_requirements(self.store,c,dict(row))
        self.assertEqual([r['text'] for r in saved],[math])
        def agendas():
            return {('math' if '练习册' in t['title']+t.get('action','') else 'chinese'):t['agenda'] for t in self.app.tasks()
                    if '练习册' in t['title']+t.get('action','') or '背诵' in t['title']+t.get('action','')}
        first=agendas()
        self.assertEqual((first['math'].get('complete_on'),first['math']['due_on']),(day.isoformat(),after.isoformat()),first['math'])
        self.assertEqual(first['chinese']['due_on'],after.isoformat(),first['chinese'])
        self.assertNotEqual(first['chinese'].get('complete_on'),day.isoformat())  # never borrows the math item's evening
        self.assertEqual(agendas(),first)  # reopening reads the same facts, no write


    def test_a_pending_pdf_item_shows_its_proven_roles_whatever_day_is_selected(self):
        import family_agenda
        keys=self.native_notice('p1b-pdf-pending');day=self.now.date();after=day+dt.timedelta(days=1)
        math='数学：%d月%d日晚完成练习册第7页第2至4题，每题写步骤，%d月%d日早上交。'%(day.month,day.day,after.month,after.day)
        self.seed_groups(keys=keys,note='题面背景',uncertainties=['另附回执模板未附'],requirements=[math])
        ident=self.candidate(keys=keys,ident='p1b-pdf-pending')
        def mapping(messages):
            context=json.loads(messages[-1]['content']);parts={p['text']:p['id'] for p in context['original_parts'] if p.get('requirement')}
            return {'actions':[dict(pdf_evidence.draft(goal=math),due=day.isoformat(),existing_item_id=ident,basis=[dict(part=parts[math],text=math)])]}
        self.refresh(mapping);row=self.item(ident)
        # The unscoped doubt still holds it for review (requirement-scoped doubts are another P1b step); its days are proven.
        self.assertEqual((row['state'],row['due'],json.loads(row['plan'])['school_task']['state']),('pending',after.isoformat(),'review'))
        def facts(selected):
            snapshot=family_agenda.snapshot(self.app,selected.isoformat(),selected.isoformat())
            found=[i['agenda'] for i in snapshot['inbox'] if i.get('id')==ident]
            self.assertEqual(len(found),1,selected);return {k:found[0].get(k) for k in ('due_on','due_kind','complete_on','published_on')}
        first=facts(day)
        self.assertEqual(first,dict(due_on=after.isoformat(),due_kind='handback',complete_on=day.isoformat(),published_on=day.isoformat()))
        self.assertEqual(facts(after),first)  # the selected day never re-reads its relative words
        self.assertEqual(facts(day),first)  # reopening reads the same facts



class ScopedDoubtPdfTests(pdf_evidence.SchoolPdfEvidenceTests):
    """C on the PDF channel: saved page-group receipts of one original (three lines, two doubts) -> validator on read ->
    _pdf_evidence -> original actions -> Store -> day tasks; the same protocol as the image original (fictional)."""
    RES='朗读示范音频未随资料附上，需家长另行获取。'

    def _run(self,scoped):
        keys=self.native_notice('p1b-pdf-scoped');day=self.now.date()
        lines=dict(数学='数学：%d月%d日晚完成练习册第7页第2至4题，每题写步骤。'%(day.month,day.day),
                   语文='语文：%d月%d日晚朗读第3课课文三遍。'%(day.month,day.day),
                   英语='英语：%d月%d日晚完成练习纸第二部分。'%(day.month,day.day))
        fp=self.seed_groups(keys=keys,note='题面背景',uncertainties=[self.RES,U_READ],requirements=list(lines.values()))
        if scoped:
            with self.store._db() as c:
                for r in c.execute('SELECT source_id,message_id,first_page,payload FROM agent_pdf_material WHERE fingerprint=?',(fp,)).fetchall():
                    payload=json.loads(r['payload'])
                    payload['originals'][0]['uncertainty_scopes']=[dict(uncertainty=self.RES,requirements=[lines['语文']],kind='resource'),
                                                                   dict(uncertainty=U_READ,requirements=[lines['英语']],kind='reading')]
                    c.execute('UPDATE agent_pdf_material SET payload=? WHERE source_id=? AND message_id=? AND fingerprint=? AND first_page=?',
                              (json.dumps(payload,ensure_ascii=False),r['source_id'],r['message_id'],fp,r['first_page']))
        ident=self.candidate(keys=keys,ident='p1b-pdf-scoped')
        def mapping(messages):
            context=json.loads(messages[-1]['content']);self.sent=context  # the actual mapper request, 0 API
            self.prompt=''.join(m['content'] for m in messages[:-1] if isinstance(m.get('content'),str))
            parts={p['text']:p['id'] for p in context['original_parts'] if p.get('requirement')}
            return {'actions':[dict(pdf_evidence.draft(goal=text),title=subject+'：'+text[text.index('晚')+1:][:14],learning_subject=subject,
                                    due=day.isoformat(),existing_item_id=ident if subject=='数学' else '',basis=[dict(part=parts[text],text=text)])
                               for subject,text in lines.items()]}
        self.refresh(mapping)
        with self.store._db() as c:
            rows={json.loads(r['plan'])['school_original_action']['requirements'][0]['text']:dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")
                  if (json.loads(r['plan']).get('school_original_action') or {}).get('requirements')}
        self.assertEqual(set(rows),set(lines.values()))
        self.lines=lines
        return {subject:rows[text] for subject,text in lines.items()}

    def sent_doubts(self):
        parts={p['text']:p for p in self.sent['original_parts'] if p.get('requirement')}
        return {s:(parts[t]['reading_doubts'],parts[t]['resource_doubts'],parts[t]['unlocated_doubts']) for s,t in self.lines.items()}

    def tasks(self):
        return sorted(t['title'] for t in self.app.tasks() if any(w in t['title']+t.get('action','') for w in ('练习册','朗读','练习纸')))

    def test_each_scoped_doubt_holds_only_its_own_pdf_line(self):
        rows=self._run(True);brief=lambda s:json.loads(rows[s]['plan'])['school_task']
        self.assertEqual([rows[s]['state'] for s in ('数学','语文','英语')],['accepted','accepted','pending'])
        self.assertEqual(brief('语文').get('resource_needed'),[self.RES]);self.assertNotIn('resource_needed',brief('数学'))
        self.assertEqual(brief('英语')['state'],'review');self.assertIn(U_READ,brief('英语')['reason']);self.assertNotIn(U_READ,brief('数学')['reason'])
        self.assertIn(agent._SCHOOL_PART_DOUBT_PROMPT.strip(),self.prompt)
        self.assertEqual(self.sent_doubts(),{'数学':([],[],[]),'语文':([],[self.RES],[]),'英语':([U_READ],[],[])})
        first=self.tasks()
        self.assertEqual(len(first),2,first);self.assertFalse([t for t in first if t.startswith('英语')],first)
        needs={t['title'][:2]:t['agenda'].get('resource_needed') for t in self.app.tasks() if t['title'][:2] in ('数学','语文')}
        self.assertEqual(needs,{'数学':None,'语文':[self.RES]})  # the day view shows the freed line's own needed material
        self.assertEqual(self.tasks(),first)  # reopening reads the same tasks

    def test_old_pdf_receipts_without_scopes_hold_every_line(self):
        rows=self._run(False)
        self.assertEqual({r['state'] for r in rows.values()},{'pending'});self.assertEqual(self.tasks(),[])
        self.assertEqual(set(map(str,self.sent_doubts().values())),{str(([],[],[self.RES,U_READ]))})
        for r in rows.values():self.assertIn(U_READ,json.loads(r['plan'])['school_task']['reason'])


class PdfScopeSupplementTests(pdf_evidence.SchoolPdfEvidenceTests):
    """D on the PDF worker: an old undecided page group without scopes -> pdfm.prepare (real page rendering stand-in, reader
    stubbed, 0 API) -> one bounded re-read on the document job's own attempts -> re-map on its own job -> same ids (fictional)."""
    RES='朗读示范音频未随资料附上，需家长另行获取。'

    def _old(self):
        import family_pdf_material as pdfm
        self.keys=keys=self.native_notice('p1b-pdf-d');self.day=day=self.now.date()
        self.lines=lines=dict(数学='数学：%d月%d日晚完成练习册第7页第2至4题，每题写步骤。'%(day.month,day.day),
                             语文='语文：%d月%d日晚朗读第3课课文三遍。'%(day.month,day.day),英语='英语：%d月%d日晚完成练习纸第二部分。'%(day.month,day.day))
        fp=self.seed_groups(keys=keys,note='题面背景',uncertainties=[self.RES,U_READ],requirements=list(lines.values()))
        with self.store._db() as c:  # only the first group holds the doubts, as read before uncertainty_scopes
            for r in c.execute('SELECT first_page,payload FROM agent_pdf_material WHERE fingerprint=? AND first_page>1',(fp,)).fetchall():
                payload=json.loads(r['payload']);payload['originals'][0]['uncertainties']=[]
                c.execute('UPDATE agent_pdf_material SET payload=? WHERE fingerprint=? AND first_page=?',(json.dumps(payload,ensure_ascii=False),fp,r['first_page']))
            source,message=self.store._message_context(c,keys);value=pdfm.pdf_input(self.store,c,source,message)
            self.doc_key=pdfm._document_key(source,message,value)
            done={p for b in pdfm._batches(pdfm._rows(c,source,message,value['fingerprint']),value['upload_id'])[0] for p in b['pages']}
            c.execute('INSERT OR REPLACE INTO agent_jobs(id,fingerprint,attempts,done) VALUES(?,?,1,1)',(self.doc_key,agent._hash(pdfm._job_value(value['fingerprint'],done))))
            self.upload_id=value['upload_id'];self.fp=fp
        self.ident=self.candidate(keys=keys,ident='p1b-pdf-d')
        self.refresh(self._mapping(first=True))
        return self.rows()

    def _mapping(self,first=False):
        def reply(messages):
            context=json.loads(messages[-1]['content']);parts={p['text']:p['id'] for p in context['original_parts'] if p.get('requirement')}
            known={} if first else {text:r['id'] for text,r in self.rows().items()}
            return {'actions':[dict(pdf_evidence.draft(goal=t),title=s+'：'+t[t.index('晚')+1:][:14],learning_subject=s,due=self.day.isoformat(),
                                    existing_item_id=(self.ident if s=='数学' else '') if first else known[t],basis=[dict(part=parts[t],text=t)])
                               for s,t in self.lines.items()]}
        return reply

    def rows(self):
        with self.store._db() as c:
            return {json.loads(r['plan'])['school_original_action']['requirements'][0]['text']:dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")
                    if (json.loads(r['plan']).get('school_original_action') or {}).get('requirements')}

    def job(self,key):
        with self.store._db() as c:return dict(c.execute('SELECT * FROM agent_jobs WHERE id=?',(key,)).fetchone())

    def group(self):
        with self.store._db() as c:return json.loads(c.execute('SELECT payload FROM agent_pdf_material WHERE fingerprint=? AND first_page=1',(self.fp,)).fetchone()['payload'])

    def _read(self,minutes,reply):
        import family_pdf_material as pdfm
        import test_pdf_material
        with test_pdf_material.renderer(11),patch.object(agent.family_llm,'extract_draft',side_effect=reply) as read:
            result=pdfm.prepare(self.store,self.now+dt.timedelta(minutes=minutes),budget=1)
        return result,read

    def receipt(self):
        return dict(originals=[dict(upload_id=self.upload_id,title='第1-3页组',note='题面背景',uncertainties=[self.RES,U_READ],
            requirements=list(self.lines.values()),deferred_contexts=[],uncertainty_scopes=[dict(uncertainty=self.RES,requirements=[self.lines['语文']],kind='resource'),
            dict(uncertainty=U_READ,requirements=[self.lines['英语']],kind='reading')])])

    def test_an_old_undecided_pdf_group_is_read_once_more_and_remapped_on_its_own_budgets(self):
        before=self._old();ids={t:r['id'] for t,r in before.items()};old=self.group()
        self.assertEqual({r['state'] for r in before.values()},{'pending'})  # unscoped old doubts hold every line
        task_key='school-task:'+self.ident;mapper=self.job(task_key)
        result,read=self._read(5,[self.receipt()])
        self.assertEqual((result,read.call_count),(dict(used=1,failed=0),1))
        self.assertEqual((read.call_args.kwargs['original_pages'],read.call_args.kwargs['previous_requirements']),([1,2,3],list(self.lines.values())))
        group=self.group();doc=self.job(self.doc_key)
        self.assertEqual(group['originals'][0]['uncertainty_scopes'],self.receipt()['originals'][0]['uncertainty_scopes'])
        self.assertEqual((group['previous_group']['payload'],group['previous_group']['scope_supplement']),(old,True))
        self.assertEqual((doc['attempts'],doc['done']),(2,1))  # the read job's own count, one more
        _,calls=self.refresh(self._mapping(),minutes=6)
        rows=self.rows();self.assertEqual(len(calls),1)
        self.assertEqual({t:r['id'] for t,r in rows.items()},ids)
        self.assertEqual([rows[self.lines[s]]['state'] for s in ('数学','语文','英语')],['accepted','accepted','pending'])
        self.assertEqual(self.job(task_key)['attempts'],mapper['attempts']+1)  # the mapping job's own count, never a new budget
        made=(self.rows(),self.group(),self.job(self.doc_key),self.job(task_key))
        result,read=self._read(7,AssertionError('no second read'))
        _,calls=self.refresh(self._mapping(),minutes=8)
        self.assertEqual((result['used'],read.call_count,len(calls)),(0,0,0))
        self.assertEqual((self.rows(),self.group(),self.job(self.doc_key),self.job(task_key)),made)

    def test_a_decided_item_or_an_exhausted_read_job_keeps_the_old_group(self):
        for case in ('decided','exhausted'):
            with self.subTest(case=case):
                if case=='exhausted':self.setUp()
                rows=self._old();old=self.group()
                with self.store._db() as c:
                    if case=='decided':c.execute("UPDATE agent_items SET state='dismissed' WHERE id=?",(rows[self.lines['英语']]['id'],))
                    else:c.execute('UPDATE agent_jobs SET attempts=? WHERE id=?',(agent.MAX_ATTEMPTS,self.doc_key))
                result,read=self._read(5,[self.receipt()])
                self.assertEqual((result['used'],read.call_count,self.group()),(0,0,old))

def load_tests(loader,tests,pattern):
    suite=unittest.TestSuite()
    for case in (OriginalDateRoleTests,SameHomeworkSubmissionTests,OwnSubmissionStepSpanTests):suite.addTests(loader.loadTestsFromTestCase(case))
    suite.addTest(SameHomeworkFlowTests('test_quoted_recording_step_keeps_the_whole_method_through_save_and_reopen'))
    suite.addTest(SameHomeworkFlowTests('test_another_lessons_recording_upload_stays_its_own_item_through_save_and_reopen'))
    suite.addTest(PdfOriginalRoleTests('test_pdf_requirement_roles_reach_the_day_view_and_stay_on_reopen'))
    suite.addTest(PdfOriginalRoleTests('test_a_pending_pdf_item_shows_its_proven_roles_whatever_day_is_selected'))
    suite.addTests(loader.loadTestsFromTestCase(ResourceTimeTests))
    for name in ('test_completion_and_handback_roles_reach_the_day_view_and_reopen','test_matching_brackets_give_the_same_roles','test_a_conflicting_bracket_is_never_a_due_or_role',
                 'test_a_material_issue_day_in_the_same_line_is_no_role_or_due'):
        suite.addTest(OriginalRoleChainTests(name))
    suite.addTests(loader.loadTestsFromTestCase(UncertaintyScopeValidatorTests))
    suite.addTests(loader.loadTestsFromTestCase(DoubtViewTests))
    for name in ('test_each_doubt_holds_only_the_requirement_it_names','test_an_old_receipt_without_scopes_keeps_every_doubt_original_wide',
                 'test_a_false_resource_or_unverifiable_pointer_never_frees_a_line','test_a_pointer_to_no_requirement_line_stays_original_wide',
                 'test_one_line_with_a_reading_and_a_resource_doubt_stays_review_in_its_own_words',
                 'test_an_old_undecided_receipt_is_read_once_more_for_its_scopes','test_a_decided_item_or_an_exhausted_job_keeps_the_old_receipt',
                 'test_a_decision_while_the_supplement_reads_keeps_the_old_receipt'):
        suite.addTest(ScopedDoubtImageChainTests(name))
    for name in ('test_each_scoped_doubt_holds_only_its_own_pdf_line','test_old_pdf_receipts_without_scopes_hold_every_line'):
        suite.addTest(ScopedDoubtPdfTests(name))
    for name in ('test_an_old_undecided_pdf_group_is_read_once_more_and_remapped_on_its_own_budgets','test_a_decided_item_or_an_exhausted_read_job_keeps_the_old_group'):
        suite.addTest(PdfScopeSupplementTests(name))
    return suite


if __name__=='__main__':
    unittest.main()

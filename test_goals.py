"""Synthetic goal lifecycle checks; no household data or external services."""
import contextlib
import io
import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import family_agent as agent
import family_goals as goals
import family_review
import family_study


def synthetic_plan(value):
    e=value['evidence'][-1];school=[s for s in value['evidence'] if s['ref'].startswith('school:')]
    cited=[e] if not school or e['ref'].startswith('school:') else [school[-1],e]
    return {'proposal':dict(title='先核对一个判断过程',goal='能解释判断所用的线索',action='家长请孩子选一道已有题，说说看到的时间线索；不愿继续就停止。',why_now='根据已保存的家长反馈先核对。',estimated_minutes=10,review_on=value['as_of'],evidence=[dict(ref=x['ref'],quote=x['text'][:30]) for x in cited],assessment='现有反馈不足以确定知识缺口。',hypotheses=[dict(reason='句子中时间线索理解可能不牢',support=[],against=[],test='使用现有一道题，请孩子说出选项理由；不提示答案。',status='待验证')],resource='已有课本；具体页码待家长核对。',mastery_check='相近新题中独立解释，记录帮助。',choice='核实')}


def synthetic_school_proposal(evidence, subject, title, goal, *, goal_id='', state='ready', reason='已读学校要求明确。', purpose='learning'):
    """Complete school-model contract with explicit task content, separate from a proposed learning plan."""
    return dict(title_quote=evidence['text'][:120],focus='school',due='',evidence=[dict(ref=evidence['ref'])],
        learning_subject=subject,learning_goal_id=goal_id,task_title=title,task_goal=goal,task_advice='',
        task_state=state,task_reason=reason,task_change='new',task_target_id='',task_purpose=purpose,task_submission='')


class GoalTests(unittest.TestCase):
    def test_interval_new_attempt_cannot_be_described_as_absent(self):
        first = dict(day='2026-09-08', subject='数学', assistance='独立尝试', practice_relation='')
        later = dict(day='2026-09-16', subject='数学', assistance='独立尝试', practice_relation='相近的新题或新片段')
        self.assertEqual(goals._interval_new_attempt([first, later]),('2026-09-08','2026-09-16',8))
        self.assertIsNone(goals._interval_new_attempt([first, later | {'day':'2026-09-10'}]))
        self.assertIsNone(goals._interval_new_attempt([first, later | {'assistance':'提示后答对'}]))
        self.assertIsNone(goals._interval_new_attempt([first, later | {'subject':'语文'}]))
        claim = '9月16日答对，但目前也没有间隔后复测证据。'
        corrected = goals._FALSE_INTERVAL_ABSENCE.sub('已记录一次间隔后的独立新题表现，仍需更多证据', claim)
        self.assertIn('已记录一次间隔后的独立新题表现', corrected)
        self.assertNotIn('没有间隔后复测', corrected)

    def test_interval_retest_rejects_old_answer_before_independent_new_question(self):
        self.evaluate()
        with self.store.agent._db() as c:
            ctx=self.store._context(c,self.store._get(c,self.ident))
        ctx['input_records']=[
            dict(day='2026-09-08',subject='英语',assistance='独立尝试',practice_relation=''),
            dict(day='2026-09-16',subject='英语',assistance='独立尝试',practice_relation='相近的新题或新片段')]
        plan=synthetic_plan(self.last_input)
        plan['proposal']['action']='先告诉孩子上次答案是B，再给一题未做过的新题请他独立答。'
        with self.assertRaisesRegex(agent.AgentError,'独立新题前'):
            self.store._proposal(plan,ctx,self.now)
        plan['proposal']['action']='先给一题未做过的新题请孩子独立答，再讨论上次答案。'
        result=self.store._proposal(plan,ctx,self.now)
        self.assertIn('相隔8天',result['assessment'])

    def setUp(self):
        tmp=tempfile.TemporaryDirectory(prefix='synthetic-goals-');self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);self.data=self.root/'private';self.data.mkdir()
        (self.root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.app=family_review.load_app(self.root,self.data);self.store=goals.Store(self.app)
        self.now=agent._now();self.count=0
        self.model=patch.object(goals.family_llm,'_chat_json',side_effect=self.reply).start();self.addCleanup(patch.stopall)
        self.ident=self.action('create',child_id='child-1',title='读懂句子中的时间',subject='英语',baseline='家长观察：孩子有时猜选项。',resources='家里现有课本和学习设备')['id']

    def action(self,action,**obj):
        self.count+=1
        return self.store.action(dict(action=action,request_key='synthetic-request-'+str(self.count).zfill(8),**obj))

    def goal(self):return next(g for g in self.store.snapshot()['goals'] if g['id']==self.ident)

    def feedback(self,note='家长转述孩子：会认单词，但说不出为什么。',**obj):
        return self.action('feedback',id=self.ident,day=self.now.date().isoformat(),source='家长转述孩子',note=note,**obj)

    @contextlib.contextmanager
    def on(self,days_ago):
        """Run a step as if on that day: confirmation times come from agent._now, feedback days from self.now."""
        real=self.now;self.now=real-dt.timedelta(days=days_ago)
        try:
            with patch.object(agent,'_now',return_value=self.now):yield self.now.date().isoformat()
        finally:self.now=real

    def resave(self,rid,**changes):
        with self.app.connect() as c:row=dict(c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone())
        self.app.save_record(dict({k:row[k] or '' for k in ('child','day','category','subject','title','note','source','assistance','practice_relation')},id=rid,**changes))

    def test_missing_context_wording_does_not_claim_absence(self):
        def answer(messages,*args,**kwargs):
            p=synthetic_plan(json.loads(messages[-1]['content']))
            p['proposal'].update(assessment='当前没有学校任务、时间账或已确认教学计划。孩子没有独立答对。',
                                 why_now='当前没有当天放学后时间账。',action='今天没有时间账，先核对。')
            p['proposal']['hypotheses'][0]['reason']='目前没有作答证据，原因待核对。'
            return p
        self.model.side_effect=answer
        result=self.evaluate()['pending']
        self.assertEqual(result['assessment'],'本轮未提供学校任务、时间账或已确认教学计划。孩子没有独立答对。')
        self.assertEqual(result['why_now'],'本轮未提供当天放学后时间账。')
        self.assertEqual(result['action'],'本轮未提供时间账，先核对。')
        self.assertEqual(result['hypotheses'][0]['reason'],'本轮未提供作答证据，原因待核对。')
        self.assertEqual(result['evidence'][0]['quote'],'家长提供的情况（尚需结合实际作答核对）：\n家长观察：孩子有时猜选项。'[:30])

    def test_method_history_keeps_each_confirmed_method_with_its_feedback_conditions_and_reason(self):
        def adjusts(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content']);self.last_input=value;plan=synthetic_plan(value)
            if value['current_plan']:plan['proposal'].update(action='改为家长先示范圈出一个时间词，再请孩子独立圈下一句。',why_now='不提示时说不出线索，先换成示范后独立圈词。',choice='调整')
            return plan
        self.model.side_effect=adjusts
        with self.on(14) as d14:self.approve(self.evaluate())
        first=self.goal()['current_plan']['action']
        with self.on(10) as d10:hinted=self.feedback('家长转述孩子：这样找线索挺好玩，提示后说对了。',assistance='少量提示')['record_id']
        with self.on(7) as d7:alone=self.feedback('家长观察：不提示时说不出线索，孩子说不想做了。',assistance='独立尝试',practice_relation='相近的新题或新片段')['record_id']
        with self.on(6) as d6:
            self.approve(self.evaluate());sameday=self.feedback('家长观察：当天又试了一次。')['record_id']
        with self.on(3):later=self.feedback('家长观察：示范后能独立圈出两个时间词。',assistance='独立尝试')['record_id']
        self.evaluate();old,new=self.last_input['method_history']        # the next round reads it
        self.assertIn('method_history',goals.PROMPT)
        self.assertEqual([(e['version'],e['confirmed_on'],e['replaced_on'],e['current']) for e in (old,new)],[(1,d14,d6,False),(2,d6,'',True)])
        self.assertEqual(old['method']['action'],first)                  # the method as confirmed then, not today's
        self.assertNotEqual(new['method']['action'],first)
        self.assertEqual(new['adopted_reason'],dict(choice='调整',why_now='不提示时说不出线索，先换成示范后独立圈词。'))
        # Opposite feedback on one method stays side by side, each with its own day and help condition; no verdict is derived.
        self.assertEqual([(f['ref'],f['day'],f['assistance'],f['practice_relation'],f['same_day']) for f in old['feedback']],
                         [('record:%d'%hinted,d10,'少量提示','',False),('record:%d'%alone,d7,'独立尝试','相近的新题或新片段',False)])
        self.assertEqual([(f['ref'],f['same_day']) for f in new['feedback']],[('record:%d'%sameday,True),('record:%d'%later,False)])
        self.assertTrue(all(f['in_evidence'] and f['source'].startswith('家长转述孩子') for e in (old,new) for f in e['feedback']))
        self.assertEqual(set(old),{'version','confirmed_on','replaced_on','current','method','adopted_reason','feedback','feedback_omitted'})
        # A parent's correction shows in the old episode and the next analysis; neither confirmed version is rewritten.
        plan_before=self.goal()['current_plan']
        self.resave(hinted,note='家长更正：那次是看过答案后才说对的。',assistance='看过讲解或答案')
        g=self.goal();seen=g['method_history'][0]['feedback'][0]
        self.assertEqual((seen['assistance'],seen.get('corrected')),('看过讲解或答案',True))
        self.assertNotIn('corrected',g['method_history'][0]['feedback'][1])
        self.assertEqual(g['method_history'][0]['method']['action'],first);self.assertEqual(g['current_plan'],plan_before)
        self.assertTrue(g['evidence_changed'])
        self.evaluate();self.assertTrue(self.last_input['method_history'][0]['feedback'][0]['corrected'])
        self.assertEqual(self.goal()['current_plan'],plan_before)       # still a suggestion until the parent confirms
        # Another child's goal never sees these versions; a record moved to the other child leaves this history,
        # and the analysis withholds earlier methods while a reviewed basis cannot be checked.
        other=self.action('create',child_id='child-2',title='虚构另一目标',subject='英语',baseline='家长观察：虚构情况。')['id']
        self.assertEqual(next(g for g in self.store.snapshot()['goals'] if g['id']==other)['method_history'],[])
        self.resave(alone,child='示例乙')
        self.assertNotIn('record:%d'%alone,[f['ref'] for e in self.goal()['method_history'] for f in e['feedback']])
        self.evaluate();self.assertTrue(self.last_input['previous_context_unavailable']);self.assertEqual(self.last_input['method_history'],[])

    def test_confirming_a_plan_persists_the_judgment_to_learner_memory(self):
        import family_learner_memory as lm
        pending=self.evaluate();self.approve(pending)
        with self.store.agent._db() as c:card=lm.learner_card(c,'child-1')
        self.assertEqual(len(card),1)
        self.assertEqual(card[0]['goal_id'],self.ident)
        self.assertEqual(card[0]['assessment'],'现有反馈不足以确定知识缺口。')
        self.assertEqual([h['reason'] for h in card[0]['hypotheses']],['句子中时间线索理解可能不牢'])
        # A confirmation records once; nothing else here re-approves, so history stays two rows.
        with self.store.agent._db() as c:self.assertEqual(len(lm.timeline(c,'child-1',self.ident)),2)

    def test_prior_confirmations_reach_re_evaluation_only_after_supersession(self):
        p1=self.evaluate();self.approve(p1)                       # judgment recorded, still current
        self.feedback(note='家长转述：按上次方法做了，仍卡在同一处。')  # evidence changes
        self.evaluate()                                            # current judgment not yet superseded
        self.assertEqual(self.last_input['prior_confirmations'],[])
        self.approve()                                             # new confirmation supersedes the first
        self.feedback(note='家长转述：又核对了一次。')
        self.evaluate()                                            # the first confirmation is now prior history
        prior=self.last_input['prior_confirmations']
        self.assertEqual(len(prior),1)
        self.assertEqual(prior[0]['assessment'],'现有反馈不足以确定知识缺口。')
        self.assertEqual(prior[0]['confirmed_on'],self.now.date().isoformat())

    def test_correcting_a_cited_record_flags_that_judgment_its_history_and_the_next_analysis(self):
        rid=self.feedback(note='家长转述孩子：ea 和 ee 常混，拼写 3/10。')['record_id'];ref='record:%d'%rid
        def cites(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content']);self.last_input=value
            plan=synthetic_plan(value);plan['proposal']['hypotheses'][0].update(support=[ref],status='有支持');return plan
        self.model.side_effect=cites
        self.approve(self.evaluate())
        def resave(**changes):
            with self.app.connect() as c:row=dict(c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone())
            self.app.save_record(dict({k:row[k] or '' for k in ('child','day','category','subject','title','note','source')},id=rid,**changes))
        resave()                                                      # an unchanged re-save is not a correction
        self.assertNotIn('corrected',self.goal()['hypotheses_detail'][0])
        resave(note='家长更正：之前记错了，拼写其实是 7/10。')
        self.assertEqual(self.goal()['hypotheses_detail'][0]['corrected'],[ref])
        plan_before=self.goal()['current_plan']
        self.evaluate()                                               # the next analysis is told not to reuse it
        self.assertEqual(self.last_input['previous_hypotheses'][0]['corrected'],[ref])
        self.assertIn('带corrected的判断',goals.PROMPT)
        self.assertEqual(self.goal()['current_plan'],plan_before)    # the formal plan changes only on approval
        self.approve()                                                # re-confirmed on the corrected record
        g=self.goal()
        self.assertNotIn('corrected',g['hypotheses_detail'][0])      # the new judgment already saw the correction
        self.assertEqual(g['prior_confirmations'][0]['corrected'],[ref])  # the superseded one keeps the flag
        self.feedback(note='家长观察：又核对了一次。');self.evaluate()
        self.assertEqual(self.last_input['prior_confirmations'][0]['corrected'],[ref])
        resave(child='示例乙')                                         # moved to the other child: no longer its basis
        self.assertEqual(self.goal()['hypotheses_detail'][0]['corrected'],[ref])

    def test_teacher_requirements_reach_goals_and_withdrawal_invalidates_only_suggestions(self):
        teachers=self.app.teacher_store()
        profile=dict(display_name='虚构英语教师',subject='英语',child_ids=['child-1'],version=0,request_key='synthetic-goal-teacher')
        teacher=teachers.save_teacher(profile)['teacher']
        body=dict(teacher_id=teacher['id'],day=self.now.date().isoformat(),kind='requirement',target='class',
                  behavior='从已有课本任选两句，先说时间线索，再解释选择。',teacher_reason='听清楚思考过程',
                  parent_note='家长推测：可能因为基础差。',version=0,request_key='synthetic-teacher-requirement')
        observation=teachers.save_observation(body)['observation']
        pending=self.evaluate();ref='school:teacher:'+observation['id']
        e=next(e for e in self.last_input['evidence'] if e['ref']==ref)
        self.assertEqual(e['kind'],'school_requirement');self.assertEqual(e['text'],body['behavior'])
        self.assertEqual(e['teacher_reason'],body['teacher_reason']);self.assertEqual(e['recorded_by'],'parent')
        self.assertNotIn(body['parent_note'],json.dumps(self.last_input,ensure_ascii=False))
        self.assertEqual(self.goal()['teacher_requirements'][0]['ref'],ref)
        invalid=synthetic_plan(self.last_input);invalid['proposal']['hypotheses'][0].update(support=[ref],status='有支持')
        with self.store.agent._db() as c:context=self.store._context(c,self.store._get(c,self.ident))
        with self.assertRaises(agent.AgentError):self.store._proposal(invalid,context,self.now)
        self.approve(pending);approved=self.goal()['current_plan']
        corrected=teachers.save_observation(dict(body,id=observation['id'],version=1,request_key='synthetic-requirement-edit',behavior='更正：只选一句，不用书面抄写。'))['observation']
        changed=self.goal();self.assertTrue(changed['evidence_changed']);self.assertEqual(changed['current_plan'],approved)
        self.assertTrue(changed['reviewed_evidence'][0]['quote_changed'])
        stale=self.evaluate()
        teachers.save_observation(dict(body,id=corrected['id'],version=2,request_key='synthetic-requirement-withdraw',status='withdrawn'))
        current=self.goal();self.assertEqual(current['teacher_requirements'],[]);self.assertTrue(current['pending_stale'])
        self.assertIn(ref,current['unavailable_reviewed_refs']);self.assertEqual(current['current_plan'],approved)
        with self.assertRaises(agent.AgentError):self.approve(stale)

    def test_teacher_requirements_respect_child_subject_kind_archive_and_existing_read_budget(self):
        teachers=self.app.teacher_store();profiles=[]
        for index,(child,subject) in enumerate([('child-1','英语'),('child-2','英语'),('child-1','语文'),('child-1','')]):
            profiles.append(teachers.save_teacher(dict(display_name='虚构教师'+str(index),subject=subject,child_ids=[child],version=0,request_key='synthetic-teacher-scope-'+str(index)))['teacher'])
        for index,teacher in enumerate(profiles):
            for kind in ['requirement','praise','preference']:
                for target in ['class','other_students']:
                    teachers.save_observation(dict(teacher_id=teacher['id'],day=self.now.date().isoformat(),kind=kind,target=target,
                        behavior=f'虚构限定材料 {index} {kind} {target}',version=0,request_key=f'synthetic-teacher-scope-{index}-{kind}-{target}'))
        first=self.evaluate();self.assertEqual(len(self.goal()['teacher_requirements']),1)
        self.assertEqual(self.goal()['teacher_requirements'][0]['text'],'虚构限定材料 0 requirement class')
        self.approve(first);retained=first['pending']['evidence'][0]['ref']
        for i in range(8):
            teachers.save_observation(dict(teacher_id=profiles[0]['id'],day=self.now.date().isoformat(),kind='requirement',target='class',
                behavior='后续虚构要求 '+str(i),version=0,request_key='synthetic-teacher-budget-'+str(i)))
        self.evaluate();g=self.goal();self.assertEqual(len(g['teacher_requirements']),6);self.assertEqual(g['teacher_requirements_omitted'],3)
        self.assertIn(retained,[e['ref'] for e in g['teacher_requirements']]);self.assertEqual(self.last_input['omitted_teacher_requirements'],3)
        teacher=profiles[0];teachers.save_teacher({k:v for k,v in teacher.items() if k in ('id','display_name','subject','child_ids','source_ids','archived','public_url','version')}|dict(archived=True,request_key='synthetic-teacher-archive'))
        self.assertEqual(self.goal()['teacher_requirements'],[])

    def test_calendar_constrains_learning_without_a_time_account_and_preserves_recurring_exceptions(self):
        calendar=self.app.calendar_store();day=self.now.date().isoformat()
        body=dict(id='c'*32,version=0,child_ids=['child-1','child-2'],title='共享运动安排',category='activity',
                  day=day,start_time='19:10',end_time='19:40',location='不需要发给模型的地点',note='私有日历备注不进入分析',status='confirmed',repeat='daily',until='')
        calendar.save(body);self.evaluate();context=self.last_input['day_context']
        self.assertEqual([e['title'] for e in context['calendar_events']],['共享运动安排'])
        self.assertIsNone(context['window_minutes_after_known_appointments'])
        self.assertNotIn(body['note'],json.dumps(self.last_input,ensure_ascii=False));self.assertNotIn(body['location'],json.dumps(self.last_input,ensure_ascii=False))
        family_study.Store(self.app).save_day(dict(child_id='child-1',day=day,request_key='synthetic-calendar-day',start_time='19:00',stop_time='20:00',bed_time='20:30'))
        calendar.save(dict(body,id='d'*32,child_ids=['child-1'],title='重叠的已确认安排',repeat='none',start_time='19:30',end_time='19:50'))
        for ident,child,status in [('e','child-2','confirmed'),('f','child-1','tentative'),('a','child-1','cancelled')]:
            calendar.save(dict(body,id=ident*32,child_ids=[child],title='另一孩子私有安排' if child=='child-2' else status,repeat='none',status=status,start_time='19:00',end_time='20:00'))
        pending=self.evaluate();context=self.last_input['day_context']
        self.assertEqual(context['window_minutes_after_known_appointments'],20,'overlap counts once; tentative/cancelled do not reserve time')
        self.assertEqual(context['known_windows'],[dict(start_time='19:00',end_time='19:10'),dict(start_time='19:50',end_time='20:00')])
        self.assertNotIn('另一孩子私有安排',json.dumps(self.last_input,ensure_ascii=False))
        study=family_study.Store(self.app)
        work=study.save_item(dict(child_id='child-1',day=day,request_key='synthetic-calendar-work-link',title='日历中的同一份作业',planned_minutes=20))
        linked=dict(id='synthetic-work-slot',child_ids=['child-1'],title='日历中的同一份作业',category='study',day=day,start_time='19:00',end_time='19:10',status='confirmed',source='虚构安排',task_id=work['saved_item_id'])
        (self.data/'日历来源.json').write_text(json.dumps(dict(events=[linked])))
        pending=self.evaluate();context=self.last_input['day_context']
        self.assertEqual(context['window_minutes_after_known_appointments'],20,'one assignment must not be counted as extra calendar load')
        self.assertEqual(study.snapshot('child-1',day)['summary']['available_minutes'],20)
        calendar.save_occurrence(dict(series_id=body['id'],series_version=1,origin_day=day,slot_id='',version=0,day=day,start_time='19:10',end_time='19:40',status='cancelled',note='今天取消一次'))
        self.assertTrue(self.goal()['pending_stale'])
        with self.assertRaises(agent.AgentError):self.approve(pending)
        self.evaluate();self.assertEqual(self.last_input['day_context']['window_minutes_after_known_appointments'],40)
        tomorrow=(self.now.date()+dt.timedelta(days=1)).isoformat()
        self.assertEqual(calendar.snapshot(tomorrow,tomorrow)['events'][0]['status'],'confirmed')

    def test_calendar_gaps_remain_unknown_and_changes_during_analysis_discard_old_suggestions(self):
        calendar=self.app.calendar_store();day=self.now.date().isoformat()
        body=dict(id='b'*32,version=0,child_ids=['child-1'],title='钟点未确定的学校安排',category='activity',day=day,start_time='',end_time='',status='confirmed',repeat='none',until='')
        calendar.save(body);self.evaluate();context=self.last_input['day_context']
        self.assertEqual(context['confirmed_events_without_clock'],1);self.assertIsNone(context['window_minutes_after_known_appointments'])
        original=self.reply
        def changed(*args,**kwargs):
            result=original(*args,**kwargs);calendar.save(dict(body,version=1,start_time='19:00',end_time='20:00'));return result
        self.feedback('补充本次原始反馈，重新分析安排')
        self.model.side_effect=changed
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'stale')
        self.model.side_effect=original
        (self.data/'日历来源.json').write_text('{broken')
        self.evaluate();context=self.last_input['day_context']
        self.assertTrue(context['calendar_incomplete']);self.assertEqual(context['calendar_events'][0]['title'],body['title'])
        self.assertNotIn('{broken',json.dumps(self.last_input,ensure_ascii=False))
        other=self.app.new_task(dict(child='示例乙',title='另一孩子的私有待办',category='todo'))['id']
        source=dict(body,id='synthetic-other-link',task_id=other,title='不能提供的错误关联',source='虚构来源')
        source.pop('version');source.pop('repeat');source.pop('until')
        shared=dict(source,id='synthetic-shared-link',child_ids=['child-1','child-2'],title='两个孩子的共享活动',start_time='19:00',end_time='20:00')
        (self.data/'日历来源.json').write_text(json.dumps(dict(events=[source,shared])))
        calendar.save_timetable(dict(id='a'*32,version=0,child_id='child-1',title='只有节次的课表',effective_from=day,effective_until='',note='',attachments=[],week=[dict(weekday=self.now.isoweekday(),sessions=[dict(slot='第一节',title='语文')])]),self.app.timetable_uploads)
        self.evaluate();context=self.last_input['day_context']
        self.assertEqual(context['unavailable_calendar_events'],1);self.assertEqual(context['timetables_without_clock'],1)
        self.assertNotIn('不能提供的错误关联',json.dumps(self.last_input,ensure_ascii=False))
        self.assertNotIn('另一孩子的私有待办',json.dumps(self.last_input,ensure_ascii=False))
        self.assertEqual(next(e for e in context['calendar_events'] if e['title']==shared['title'])['task_id'],'')
        family_study.Store(self.app).save_day(dict(child_id='child-1',day=day,request_key='synthetic-timetable-gap',start_time='19:00',stop_time='21:00'))
        self.evaluate();context=self.last_input['day_context']
        self.assertEqual(context['window_minutes_after_known_appointments'],60,'clockless timetable flags uncertainty, not an extra duration')
        self.assertEqual(context['timetables_without_clock'],1)
        self.approve(self.goal());calls=self.model.call_count
        self.assertEqual(goals.Store(self.app).process(self.ident,self.now)['state'],'current');self.assertEqual(self.model.call_count,calls)

    def test_omitted_calendar_titles_do_not_erase_their_time_constraints(self):
        day=self.now.date().isoformat();calendar=self.app.calendar_store()
        family_study.Store(self.app).save_day(dict(child_id='child-1',day=day,request_key='synthetic-many-appointments',start_time='19:00',stop_time='20:00'))
        for i in range(25):
            calendar.save(dict(id=f'{i+100:032x}',version=0,child_ids=['child-1'],title='虚构已确认安排 '+str(i),category='activity',
                day=day,start_time='19:10' if i<24 else '19:50',end_time='19:50' if i<24 else '20:00',status='confirmed',repeat='none',until=''))
        self.evaluate();context=self.last_input['day_context']
        self.assertEqual(len(context['calendar_events']),24);self.assertEqual(context['omitted_calendar_events'],1)
        self.assertEqual(context['window_minutes_after_known_appointments'],10)
        self.assertEqual(context['known_windows'],[dict(start_time='19:00',end_time='19:10')])

    def test_registered_work_and_rest_reach_analysis_without_other_child_or_fake_free_time(self):
        self.evaluate();self.assertIsNone(self.last_input['day_context'])
        study=family_study.Store(self.app);day=self.now.date().isoformat()
        study.save_day(dict(child_id='child-1',day=day,request_key='synthetic-rest-boundary',start_time='19:30',stop_time='20:00',bed_time='20:30'))
        for child,title,minutes in [('child-1','已有语文功课',50),('child-1','未估时间的数学',None),('child-2','另一孩子私有功课',40)]:
            study.save_item(dict(child_id=child,day=day,request_key='synthetic-work-'+child+str(minutes),title=title,subject='综合',planned_minutes=minutes))
        pending=self.evaluate();context=self.last_input['day_context']
        self.assertEqual(context['stop_time'],'20:00');self.assertEqual(context['preparing_for_bed_at'],'20:30')
        self.assertEqual({i['title'] for i in context['other_registered_work']},{'已有语文功课','未估时间的数学'})
        self.assertTrue(any(i['planned_minutes'] is None for i in context['other_registered_work']))
        self.assertNotIn('free_minutes',context);self.assertFalse(context['closed_at'])
        self.assertNotIn('另一孩子私有功课',json.dumps(self.last_input,ensure_ascii=False))
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        pause=synthetic_plan(self.last_input);pause['proposal'].update(choice='暂停',estimated_minutes=None)
        self.assertIn('截止时间本轮未提供',self.store._proposal(pause,ctx,self.now)['assessment'])
        with self.app.connect() as c: c.execute("UPDATE study_days SET stop_time='19:45' WHERE child_id='child-1' AND day=?",(day,))
        self.assertTrue(self.goal()['pending_stale'])
        with self.assertRaises(agent.AgentError):self.approve(pending)
        current=self.evaluate();self.assertEqual(self.last_input['day_context']['stop_time'],'19:45')
        self.approve(current);calls=self.model.call_count
        self.assertEqual(goals.Store(self.app).process(self.ident,self.now)['state'],'current')
        self.assertEqual(self.model.call_count,calls)

        before_stop=self.now.replace(hour=19,minute=44,second=0,microsecond=0)
        after_stop=before_stop+dt.timedelta(minutes=1)
        with self.app.connect() as c:
            row=self.store._get(c,self.ident)
            early=self.store._context(c,row,before_stop)
            self.assertFalse(early['day_context']['after_stop_time'])
            self.assertEqual(early['evidence_hash'],self.store._context(c,row,before_stop+dt.timedelta(seconds=50))['evidence_hash'])
            late=self.store._context(c,row,after_stop)
            self.assertTrue(late['day_context']['after_stop_time'])
            self.assertNotEqual(early['evidence_hash'],late['evidence_hash'])

    def test_day_context_change_during_analysis_discards_plan_and_keeps_time_account(self):
        study=family_study.Store(self.app);day=self.now.date().isoformat()
        saved=study.save_item(dict(child_id='child-1',day=day,request_key='synthetic-work-concurrent',title='原有学校功课',planned_minutes=20))
        original=self.reply
        def changed(*args,**kwargs):
            value=original(*args,**kwargs)
            with self.app.connect() as c:c.execute('UPDATE study_items SET planned_minutes=60 WHERE id=?',(saved['saved_item_id'],))
            return value
        self.model.side_effect=changed
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'stale')
        self.assertIsNone(self.goal()['pending']);self.assertIsNone(self.goal()['current_plan'])
        self.assertEqual(study.snapshot('child-1',day)['items'][0]['planned_minutes'],60)

    def test_day_context_bounds_current_task_and_reassigned_work(self):
        self.approve(self.evaluate());task_id=self.goal()['task_id'];study=family_study.Store(self.app);day=self.now.date().isoformat()
        own=study.save_item(dict(child_id='child-1',day=day,request_key='synthetic-current-goal-work',task_id=task_id,planned_minutes=8))
        other=study.save_item(dict(child_id='child-1',day=day,request_key='synthetic-reassigned-work',title='不能串入的功课',planned_minutes=30))
        with self.app.connect() as c:
            c.execute("UPDATE manual_tasks SET child='示例乙' WHERE id=?",(other['saved_item_id'],))
        self.evaluate();context=self.last_input['day_context']
        self.assertTrue(context['current_goal_registered']);self.assertEqual(context['unavailable_items'],1)
        self.assertEqual(context['other_registered_work'],[])
        before=self.goal()['context_hash']
        with self.app.connect() as c:c.execute('UPDATE study_items SET elapsed_seconds=90 WHERE id=?',(own['saved_item_id'],))
        self.assertEqual(self.goal()['context_hash'],before,'timer ticks do not trigger repeated model calls')
        with self.app.connect() as c:
            for i in range(26):
                ident='synthetic-work-'+str(i)
                c.execute('INSERT INTO manual_tasks VALUES (?,?,?,?,?,?,?)',(ident,'示例甲','学校功课 '+str(i),day,'待跟进','虚构登记',''))
                c.execute('INSERT INTO study_items(id,child_id,day,task_id,title,subject,version,creation_hash,last_request_key,last_request_hash) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,'child-1',day,ident,'学校功课 '+str(i),'综合',1,'h','k','h'))
        self.evaluate();context=self.last_input['day_context']
        self.assertEqual(len(context['other_registered_work']),24);self.assertEqual(context['omitted_items'],2)

    def test_legacy_plan_goal_survives_read_and_edit_without_recreating_task(self):
        self.approve(self.evaluate());before=self.goal();expected=before['current_plan']['goal']
        with self.store.agent._db() as c:
            plan=json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?',(self.ident,)).fetchone()['plan'])
            plan['goal']=plan['approved'].pop('goal');legacy=agent._json(plan)
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(legacy,self.ident))
        current=self.goal();self.assertEqual(current['current_plan']['goal'],expected)
        with self.store.agent._db() as c:
            self.assertEqual(c.execute('SELECT plan FROM agent_items WHERE id=?',(self.ident,)).fetchone()['plan'],legacy)
        self.action('manual',id=self.ident,expected_version=current['version'],context_hash=current['context_hash'],
                    plan={**current['current_plan'],'review_on':(self.now.date()+dt.timedelta(days=7)).isoformat()})
        saved=self.goal();self.assertEqual(saved['task_id'],before['task_id']);self.assertEqual(saved['current_plan']['goal'],expected)
        self.assertEqual(saved['records'],before['records'])

    def test_course_context_is_bounded_same_child_subject_and_never_ability_evidence(self):
        body=dict(child='示例甲',day='2026-09-01',category='课程进度',subject='英语',title='虚构教材第二单元',
                  note='老师说今天讲到问路；下周是否继续未知。版本待核对。',source='老师反馈',request_key='synthetic-course-record')
        for field in ('subject','note'):
            with self.assertRaises(ValueError): self.app.save_record(dict(body,**{field:' '}))
        saved=self.app.save_record(body);self.assertEqual(self.app.save_record(body)['record_id'],saved['record_id'])
        for child,subject in [('示例乙','英语'),('示例甲','语文')]:
            self.app.save_record(dict(body,child=child,subject=subject,request_key='',note='OTHER_CONTEXT_PRIVATE_CANARY'))
        g=self.evaluate();self.assertEqual(g['records'],[])
        self.assertEqual([r['id'] for r in g['course_records']],[saved['record_id']])
        self.assertNotIn('OTHER_CONTEXT_PRIVATE_CANARY',json.dumps(self.last_input))
        evidence=next(e for e in self.last_input['evidence'] if e['ref']=='record:'+str(saved['record_id']))
        self.assertEqual(evidence['kind'],'school_requirement')
        self.assertEqual(g['pending']['hypotheses'][0]['support'],[])
        with self.store.agent._db() as c: ctx=self.store._context(c,self.store._get(c,self.ident))
        malicious=synthetic_plan(self.last_input);malicious['proposal']['hypotheses'][0].update(support=[evidence['ref']],status='有支持')
        with self.assertRaisesRegex(agent.AgentError,'学校要求'): self.store._proposal(malicious,ctx,self.now)
        self.approve(g);before=self.goal()['current_plan'];self.feedback('家长转述：孩子尚未试过这些内容。')
        pending=self.evaluate();changed=dict(body,id=saved['record_id'],request_key='',note='老师更正：明天才讲，今天只介绍主题。')
        self.app.save_record(changed);g=self.goal()
        self.assertTrue(g['pending_stale']);self.assertEqual(g['current_plan'],before)
        with self.assertRaises(agent.AgentError):self.approve(pending)
        self.evaluate();self.assertIn(changed['note'],json.dumps(self.last_input,ensure_ascii=False))
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM revisions WHERE record_id=?',(saved['record_id'],)).fetchone()[0],1)
        observed=self.app.save_record(dict(child='示例甲',day='2026-09-02',category='家长观察',subject='',title='虚构课后反馈',note='家长转述：愿意指图，还没有独立表达。',source='家长转述孩子',related_record_id=saved['record_id'],followup_kind='补充观察'))
        self.evaluate();self.assertIn(observed['record_id'],[r['id'] for r in self.goal()['records']])
        self.assertIn(observed['record_id'],self.store.managed_ids())
        self.assertNotEqual(next(e for e in self.last_input['evidence'] if e['ref']=='record:'+str(observed['record_id'])).get('kind'),'school_requirement')
        # Explicitly linking the same record does not duplicate the automatic context or turn it into performance.
        self.action('link',id=self.ident,expected_version=self.goal()['version'],record_ids=[saved['record_id']])
        self.evaluate();self.assertEqual(self.goal()['course_records'],[])
        self.assertEqual(sum(e['ref']==evidence['ref'] for e in self.last_input['evidence']),1)
        self.assertEqual(next(e for e in self.last_input['evidence'] if e['ref']==evidence['ref'])['kind'],'school_requirement')

    def test_course_context_retains_reviewed_original_and_reports_omitted_records(self):
        for number in range(8):
            self.app.save_record(dict(child='示例甲',day=f'2026-09-{number+1:02}',category='课程进度',subject='英语',
                title=f'虚构课次{number}',note='计划学习本课，实际是否讲过未知。',source='家长转述老师'))
        self.evaluate();g=self.goal();self.assertEqual(len(g['course_records']),6);self.assertEqual(g['course_omitted'],2)
        self.assertEqual([r['title'] for r in g['course_records']],[f'虚构课次{i}' for i in range(2,8)])
        self.approve(g);retained=g['pending']['evidence'][0]['ref']
        for number in range(8,15):
            self.app.save_record(dict(child='示例甲',day=f'2026-09-{number+1:02}',category='课程进度',subject='英语',
                title=f'虚构课次{number}',note='后续计划，是否适用于此目标未知。',source='老师反馈'))
        self.evaluate();self.assertIn(retained,[e['ref'] for e in self.last_input['evidence']])
        self.assertEqual(self.goal()['course_omitted'],9)

    def test_school_only_citations_cannot_be_hypothesis_support(self):
        evidence=[dict(ref='school:message:54321@chatroom:1',text='任选一个地方介绍。')]
        schema=agent._evidence_schema(goals.SCHEMA,evidence)
        properties=schema['properties']['proposal']['properties']
        self.assertEqual(properties['evidence']['items']['properties']['ref']['enum'],[evidence[0]['ref']])
        for field in ('support','against'):
            self.assertEqual(properties['hypotheses']['items']['properties'][field]['maxItems'],0)
            self.assertNotIn('enum',properties['hypotheses']['items']['properties'][field]['items'])
        self.assertNotIn('enum',goals.PROPOSAL['properties']['evidence']['items']['properties']['ref'])
        self.assertEqual(agent._evidence_schema(agent.PLAN_SCHEMA,[]),agent.PLAN_SCHEMA)

    def test_task_feedback_reaches_goal_and_revises_without_changing_plan(self):
        self.approve(self.evaluate());before=self.goal();task=before['task_id']
        payload=dict(id=task,status='进行中',note='家长转述：孩子说困了，今天先停；只在提示后完成。',expected_updated='')
        self.app.save_task(payload);self.app.save_task(payload)
        g=self.goal();self.assertEqual(len(g['task_feedback']),1);self.assertTrue(g['evidence_changed'])
        self.assertEqual(g['current_plan'],before['current_plan']);self.assertEqual(g['records'],[])
        g=self.evaluate();e=self.last_input['evidence'][-1]
        self.assertEqual(e['kind'],'task_feedback');self.assertEqual(e['text'],payload['note'])
        self.assertEqual(e['task_id'],task);self.assertEqual(e['source_kind'],'parent_task_feedback')
        self.approve(g);self.assertFalse(self.goal()['evidence_changed'])
        self.assertEqual(self.store.process(self.ident,self.now)['state'],'current')
        self.assertEqual(len(self.goal()['task_feedback']),1,'plan approval is not learning feedback')
        old=self.goal();self.app.save_task(dict(id=task,status='进行中',note='更正：刚才并未完成，只讲了第一步。'))
        self.assertTrue(self.goal()['evidence_changed']);g=self.evaluate()
        self.assertEqual(len(self.last_input['evidence']),3);self.assertIn('更正',self.last_input['evidence'][-1]['text'])
        self.assertEqual(self.goal()['current_plan'],old['current_plan'])
        self.assertEqual(len(goals.Store(self.app).snapshot()['goals'][0]['task_feedback']),2)
        original=self.reply
        def concurrent(*args,**kwargs):
            result=original(*args,**kwargs);self.app.save_task(dict(id=task,status='进行中',note='分析时补充：孩子愿意明天口述。'));return result
        self.app.save_task(dict(id=task,status='进行中',note='补充：准备重新核对第一步。'))
        self.model.side_effect=concurrent
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'stale')
        with self.assertRaises(agent.AgentError):self.approve(g)

    def test_parent_observation_on_goal_task_reaches_original_goal(self):
        self.approve(self.evaluate());before=self.goal();task=before['task_id']
        saved=self.app.save_task_feedback(dict(task_id=task,child='示例甲',day=self.now.date().isoformat(),
            category='家长观察',note='家长观察：孩子独立说出大意，转折仍需核对。',
            request_key='synthetic-goal-task-observation'))
        goal=self.goal()
        self.assertEqual([r['id'] for r in goal['records']],[saved['record_id']])
        self.assertTrue(goal['evidence_changed'])
        self.assertEqual(goal['current_plan'],before['current_plan'])
        self.evaluate()
        self.assertIn('record:'+str(saved['record_id']),[r['ref'] for r in self.last_input['evidence']])

    def test_school_task_feedback_and_results_follow_explicit_links_and_child(self):
        def school_task(child, goal):
            task=self.app.new_task(dict(child=child,title='英语：介绍一种文具',category='homework'))['id']
            with self.app.connect() as c:
                c.execute("INSERT INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,state,created,updated,task_id,plan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ('school-'+task,'synthetic-school-link', 'child-1' if child=='示例甲' else 'child-2','school','文具练习','','[]','','accepted',self.now.isoformat(),self.now.isoformat(),task,json.dumps(dict(school_goal_id=goal,school_messages=[]))))
            self.app.save_task(dict(id=task,status='进行中',note=child+'家长转述：第二点需要提示。'))
            return task
        own=school_task('示例甲',self.ident);school_task('示例乙',self.ident)
        other=self.action('create',child_id='child-1',title='另一英语目标',subject='英语')['id']
        school_task('示例甲',other)
        self.assertEqual([x['task_id'] for x in self.goal()['task_feedback']],[own])
        family_study.Store(self.app)
        record=self.app.save_record(dict(child='示例甲',day=self.now.date().isoformat(),category='家长观察',subject='英语',title='虚构作业结果',note='本次独立讲出第一点。',source='虚构作业计时'))
        with self.app.connect() as c:
            c.execute("INSERT INTO study_items(id,child_id,day,task_id,title,subject,record_id,version,creation_hash,last_request_key,last_request_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)",('school-result','child-1',self.now.date().isoformat(),own,'文具练习','英语',record['record_id'],1,'h','k','h'))
        self.assertEqual([r['id'] for r in self.goal()['records']],[record['record_id']])
        self.evaluate();self.assertEqual(len([e for e in self.last_input['evidence'] if e.get('kind')=='task_feedback']),1)
        with self.app.connect() as c:c.execute("UPDATE manual_tasks SET child='示例乙' WHERE id=?",(own,))
        g=self.goal();self.assertFalse(g['task_feedback']);self.assertFalse(g['records']);self.assertEqual(g['task_missing'],1);self.assertTrue(g['pending_stale'])

    def test_exam_result_source_follows_only_the_exact_linked_task(self):
        def task(child,title):
            return self.app.new_task(dict(child=child,title=title,due=self.now.date().isoformat(),category='todo'))['id']
        linked=task('示例甲','英语 Unit1 单元测验')
        unlinked=task('示例甲','英语 Unit2 单元测验')
        foreign=task('示例乙','英语 Unit1 单元测验')
        with self.app.connect() as c:
            c.execute("INSERT INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,state,created,updated,task_id,plan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ('school-exam-link','synthetic-exam-link','child-1','school','英语 Unit1 单元测验','','[]',self.now.date().isoformat(),'accepted',self.now.isoformat(),self.now.isoformat(),linked,
                 json.dumps(dict(school_goal_id=self.ident,school_messages=[]))))
        self.evaluate()
        result=dict(child='示例甲',day=self.now.date().isoformat(),category='成绩',subject='英语',title='Unit1 测验结果',
                    note='听写中有两个词需要核对。',source='事项:'+linked,score=78,total=100,request_key='synthetic-exam-result-link')
        saved=self.app.save_record(result)
        replayed=self.app.save_record(result)
        self.assertEqual(replayed['record_id'],saved['record_id']);self.assertTrue(replayed['replayed'])
        current=self.goal()
        self.assertEqual([r['id'] for r in current['records']],[saved['record_id']])
        self.assertTrue(current['pending_stale']);self.assertIn(saved['record_id'],self.store.managed_ids())
        self.assertEqual(self.app.task_status(next(t for t in self.app.tasks() if t['id']==linked)),'待跟进')

        unrelated=self.app.save_record(dict(result,title='Unit2 测验结果',note='同科但未关联的事项。',source='事项:'+unlinked,
                                               request_key='synthetic-unlinked-exam-result'))
        self.assertEqual([r['id'] for r in self.goal()['records']],[saved['record_id']])
        self.assertNotIn(unrelated['record_id'],self.store.managed_ids())
        for source in ('事项:'+foreign,'事项:missing-task'):
            with self.assertRaises(self.app.RecordError) as failure:
                self.app.save_record(dict(result,source=source,request_key='synthetic-invalid-'+str(len(source))))
            self.assertEqual(failure.exception.code,'record_task_mismatch')

        self.evaluate()
        evidence=json.dumps(self.last_input['evidence'],ensure_ascii=False)
        self.assertIn(result['note'],evidence);self.assertNotIn('同科但未关联的事项',evidence)

    def test_task_feedback_bounds_and_legacy_note_are_explicit(self):
        self.approve(self.evaluate());task=self.goal()['task_id']
        for i in range(30):self.app.save_task(dict(id=task,status='进行中',note='虚构反馈'+str(i)+('甲'*1500 if i==29 else '')))
        g=self.goal();self.assertEqual(len(g['task_feedback']),24);self.assertEqual(g['task_feedback_omitted'],6)
        self.evaluate();e=self.last_input['evidence'][-1];self.assertEqual(len(e['text']),1200);self.assertTrue(e['content_incomplete'])
        self.assertGreater(len(g['task_feedback'][-1]['text']),1200)
        with self.app.connect() as c:c.execute('DELETE FROM task_history WHERE task_id=?',(task,))
        g=self.goal();self.assertEqual(len(g['task_feedback']),1);original_feedback=g['task_feedback']
        self.approve(self.evaluate());g=self.goal();self.assertEqual(g['task_feedback'],original_feedback);self.assertFalse(g['evidence_changed'])
        self.assertEqual(self.store.process(self.ident,self.now)['state'],'current')
        self.app.save_task(dict(id=task,status='进行中',note='更正：原文字是尚待核对的转述。'))
        g=self.goal();self.assertEqual(len(g['task_feedback']),2);self.assertEqual(len({h['ref'] for h in g['task_feedback']}),2)
        original_hash=g['context_hash']
        for status,note in [('已完成','家长通过清单勾选确认此事项已完成。'),('待跟进','家长撤销完成，继续跟进。')]:
            self.app.save_task(dict(id=task,status=status,note=note));self.assertEqual(self.goal()['context_hash'],original_hash)

    def test_reviewed_old_evidence_and_counterexample_survive_recent_window(self):
        self.feedback('最初情况尚待核对。')
        early=self.feedback('只看词形能解释；纯听时选错了意思。')['record_id']
        ref='record:'+str(early)
        def anchored(*args,**kwargs):
            result=self.reply(*args,**kwargs);p=result['proposal']
            e=next(e for e in self.last_input['evidence'] if e['ref']==ref)
            p['evidence']=[dict(ref=ref,quote='只看词形能解释')]
            p['hypotheses'][0].update(reason='听音识义尚需核对',support=[ref],against=[],status='有支持')
            return result
        self.model.side_effect=anchored;self.approve(self.evaluate());formal=self.goal()['current_plan']
        self.assertEqual(self.goal()['reviewed_evidence'][0]['quote'],'只看词形能解释')
        with self.app.connect() as c:
            row=c.execute('SELECT plan FROM agent_items WHERE id=?',(self.ident,)).fetchone();plan=json.loads(row['plan']);del plan['approved_evidence']
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),self.ident))
        self.assertEqual(self.goal()['reviewed_evidence'][0]['ref'],ref,'legacy accepted proposal remains readable')
        counter=self.app.save_record(dict(child='示例甲',day=self.now.date().isoformat(),category='家长观察',title='不同条件下的核对',note='另一词条无词形提示时能解释，但范围有限。',source='家长观察',related_record_id=early,followup_kind='独立复测',assistance='独立尝试'))['record_id']
        for i in range(30):self.feedback('后续日常记录'+str(i))
        self.model.side_effect=self.reply;self.evaluate()
        refs={e['ref'] for e in self.last_input['evidence']}
        self.assertIn(ref,refs);self.assertIn('record:'+str(counter),refs)
        self.assertEqual(len(self.goal()['records']),24);self.assertEqual(self.goal()['current_plan'],formal)
        self.app.save_record(dict(id=early,child='示例甲',day=self.now.date().isoformat(),category='家长观察',title='已更正的早期核对',note='更正：当时先听过解释，不能算独立。',source='家长观察',assistance='看过讲解或答案'))
        self.assertTrue(self.goal()['pending_stale']);self.evaluate()
        current=next(e['text'] for e in self.last_input['evidence'] if e['ref']==ref)
        self.assertIn('更正：当时先听过解释',current);self.assertNotIn('只看词形能解释',current)
        self.assertEqual(self.goal()['current_plan'],formal)
        quoted=self.goal()['reviewed_evidence'][0];self.assertEqual(quoted['quote'],'只看词形能解释');self.assertTrue(quoted['quote_changed'])

    def test_reviewed_task_note_is_retrieved_and_missing_ownership_is_not_leaked(self):
        self.approve(self.evaluate());task=self.goal()['task_id']
        self.app.save_task(dict(id=task,status='进行中',note='早期方法反馈：孩子愿意口述，未确认书面独立。'))
        self.approve(self.evaluate());ref=self.goal()['reviewed_evidence'][0]['ref']
        for i in range(30):self.app.save_task(dict(id=task,status='进行中',note='后续作息反馈'+str(i)))
        self.evaluate();self.assertIn(ref,{e['ref'] for e in self.last_input['evidence']})
        self.assertEqual(len(self.goal()['task_feedback']),24);self.assertEqual(self.goal()['task_feedback_omitted'],7)
        with self.app.connect() as c:c.execute("UPDATE manual_tasks SET child='示例乙' WHERE id=?",(task,))
        g=self.goal();self.assertIn(ref,g['unavailable_reviewed_refs']);self.assertEqual(g['reviewed_evidence'][0]['quote'],'')
        self.assertNotIn('早期方法反馈',json.dumps(g,ensure_ascii=False))

    def test_evidence_budget_reports_reviewed_refs_it_cannot_include(self):
        for i in range(24):self.feedback('虚构条件记录'+str(i))
        def many_refs(*args,**kwargs):
            result=self.reply(*args,**kwargs);refs=[e['ref'] for e in self.last_input['evidence'] if e['ref'].startswith('record:')]
            result['proposal']['hypotheses']=[dict(reason='需结合条件核对的假设'+str(i),support=refs[i*6:i*6+4],against=refs[i*6+4:i*6+6],test='核对原始条件，不把次数当掌握。',status='有反证') for i in range(4)]
            return result
        self.model.side_effect=many_refs;self.approve(self.evaluate());formal=self.goal()['current_plan']
        for i in range(6):self.feedback('最新补充条件'+str(i))
        self.model.side_effect=self.reply;self.evaluate();g=self.goal()
        self.assertEqual(len(g['records']),24);self.assertEqual(len(g['omitted_reviewed_refs']),6)
        self.assertEqual(g['omitted_reviewed_refs'],self.last_input['omitted_reviewed_refs'])
        self.assertFalse(self.last_input['unavailable_reviewed_refs']);self.assertEqual(g['current_plan'],formal)

    def test_revoked_reference_cannot_return_through_old_model_summary_or_plan(self):
        self.approve(self.evaluate());task=self.goal()['task_id'];note='仅用于范围核验的原记录词句'
        self.app.save_task(dict(id=task,status='进行中',note=note))
        def derived(*args,**kwargs):
            result=self.reply(*args,**kwargs);p=result['proposal'];p['assessment']='仍待核对：'+note;p['action']='请核对：'+note
            return result
        self.model.side_effect=derived;self.approve(self.evaluate());formal=self.goal()['current_plan']
        with self.app.connect() as c:c.execute("UPDATE manual_tasks SET child='示例乙' WHERE id=?",(task,))
        self.model.side_effect=self.reply;self.evaluate()
        self.assertNotIn(note,json.dumps(self.last_input,ensure_ascii=False))
        self.assertTrue(self.last_input['previous_context_unavailable']);self.assertIsNone(self.last_input['current_plan'])
        self.assertEqual(self.goal()['current_plan'],formal,'parent audit plan remains stored; it is withheld from the model')

    def test_word_directions_remain_separate_retry_and_feed_goal(self):
        before=self.goal();self.approve(self.evaluate());approved=self.goal()['current_plan']
        check=dict(word='pen',meaning='用于写字的笔',material='虚构课堂词表',phase='首次核对',
                   results=dict(hear_meaning='答错',read_meaning='本次独立答对',hear_spelling='提示后答对'))
        obj=dict(action='feedback',request_key='synthetic-word-feedback-0001',id=self.ident,
                 day=self.now.date().isoformat(),source='家长观察',note='只听时选择了“书”；见到词形后选择“笔”。',word_check=check)
        r=self.store.action(obj);self.assertTrue(self.store.action(obj)['replayed'])
        g=self.goal();self.assertEqual(len(g['records']),len(before['records'])+1);self.assertEqual(g['current_plan'],approved)
        note=g['records'][-1]['note'];self.assertIn('听英文 → 选中文：答错',note)
        self.assertEqual(g['records'][-1]['assistance'],'');self.assertEqual(g['records'][-1]['practice_relation'],'')
        self.assertIn('看英文 → 选中文：本次独立答对',note);self.assertIn('看中文 → 说英文：未测',note)
        history=g['word_history'];self.assertEqual(len(history['checks']),1);self.assertFalse(history['unparsed'])
        self.assertEqual(history['checks'][0]['results']['hear_meaning'],'答错')
        self.assertEqual(history['checks'][0]['results']['meaning_speaking'],'未测')
        self.assertTrue(history['checks'][0]['has_note'])
        changed=json.loads(json.dumps(obj));changed['word_check']['results']['hear_meaning']='本次独立答对'
        with self.assertRaises(Exception):self.store.action(changed)
        self.assertEqual(self.goal()['records'][-1]['note'],note)
        self.evaluate();self.assertEqual(note,json.loads(next(e['text'] for e in self.last_input['evidence'] if e['ref']=='record:'+str(r['record_id'])))['note'])
        self.assertEqual(self.goal()['current_plan'],approved)
        for bad in [dict(check,phase='刚练过或看过答案'),dict(check,phase='尚未核对'),dict(check,results={'unknown':'答错'}),
                    dict(check,results={'hear_meaning':'已掌握'}),dict(check,results={}),dict(check,results={'hear_meaning':'未测'})]:
            with self.assertRaises(agent.AgentError):goals.word_check_note(bad)
        with self.assertRaisesRegex(agent.AgentError,'各方向'):
            self.store.action(dict(obj,request_key='synthetic-word-bad-assistance',assistance='独立尝试'))
        other=self.action('create',child_id='child-2',title='另一位孩子英语',subject='英语')['id']
        self.assertFalse(next(x for x in self.store.snapshot()['goals'] if x['id']==other)['records'])
        self.assertEqual(next(x for x in self.store.snapshot()['goals'] if x['id']==other)['word_history'],dict(checks=[],unparsed=[],words=[],retest_days=goals.WORD_RETEST_DAYS,retest_candidates=[],retest_omitted=0),'another child sees no word history or candidates')

    def test_direction_progress_is_deterministic_and_reaches_the_model(self):
        today=self.now.date();ago=lambda n:(today-dt.timedelta(days=n)).isoformat()
        wc=lambda word,phase,res:dict(word=word,meaning='老师',material='虚构词表',phase=phase,results={'meaning_spelling':res})
        # A direction that climbs 答错 -> 提示后答对 -> 间隔后独立答对 (间隔后复测, gap>=7) reads as 改善 and reached.
        for day,phase,res in [(ago(20),'首次核对','答错'),(ago(12),'刚练过或看过答案','提示后答对'),(ago(2),'间隔后复测','本次独立答对')]:
            self.action('feedback',id=self.ident,day=day,source='家长观察',note='',word_check=wc('teacher',phase,res))
        # A flat direction: 提示后答对 twice, never independent.
        for day in (ago(15),ago(3)):
            self.action('feedback',id=self.ident,day=day,source='家长观察',note='',word_check=dict(wc('please','首次核对','提示后答对'),word='please',meaning='请'))
        words={(w['word'],w['meaning']):w for w in self.goal()['word_history']['words']}
        climbed=words[('teacher','老师')]['progress']['meaning_spelling']
        self.assertEqual((climbed['first_status'],climbed['latest_status'],climbed['reached_independent'],climbed['trend']),('答错','间隔后独立答对',True,'改善'))
        flat=words[('please','请')]['progress']['meaning_spelling']
        self.assertEqual((flat['first_status'],flat['latest_status'],flat['reached_independent'],flat['trend']),('提示后答对','提示后答对',False,'持平'))
        # A single dated check gives '仅一次，证据不足'; undated checks yield no trajectory.
        self.action('feedback',id=self.ident,day=ago(1),source='家长观察',note='',word_check=dict(wc('eat','首次核对','答错'),word='eat',meaning='吃'))
        once=next(w for w in self.goal()['word_history']['words'] if w['word']=='eat')['progress']['meaning_spelling']
        self.assertEqual(once['trend'],'仅一次，证据不足')
        # The deterministic progress and the plan-confirmation date reach the model input.
        self.approve(self.evaluate())
        self.evaluate()
        rows={(r['word'],r['direction']):r for r in self.last_input['progress']}
        self.assertEqual(rows[('teacher','看中文 → 拼英文')]['trend'],'改善')
        self.assertTrue(rows[('teacher','看中文 → 拼英文')]['reached_independent'])
        self.assertEqual(rows[('please','看中文 → 拼英文')]['reached_independent'],False)
        self.assertRegex(self.last_input['current_plan_confirmed_on'],r'^\d{4}-\d{2}-\d{2}$')

    def test_progress_keeps_nonanswers_conditions_and_interval_evidence_separate(self):
        today=self.now.date();ago=lambda n:(today-dt.timedelta(days=n)).isoformat();mode='meaning_spelling'
        def progress(rows):
            items=[dict(day=d,phase=p,results={mode:r}) for d,p,r in rows]
            return goals._direction_progress(items,mode,goals.word_status(items,today)[mode],today)
        first=(ago(10),'首次核对','本次独立答对');last=(ago(1),'间隔后复测','本次独立答对')
        value=progress([first,last]);self.assertEqual(value['trend'],'持平');self.assertTrue(value['reached_independent'])
        self.assertEqual(progress([(ago(10),'首次核对','未作答'),(ago(1),'首次核对','提示后答对')])['trend'],'证据不足')
        self.assertEqual(progress([first,(ago(10),'间隔后复测','本次独立答对'),(ago(1),'首次核对','答错')])['trend'],'证据不足')
        self.assertEqual(progress([first,(ago(1),'首次核对','答错')])['trend'],'退步')
        self.assertEqual(progress([first,((today+dt.timedelta(days=1)).isoformat(),'间隔后复测','本次独立答对')])['trend'],'证据不足')

    def test_model_progress_reuses_the_existing_record_window(self):
        for i in range(30):
            self.action('feedback',id=self.ident,day=(self.now.date()-dt.timedelta(days=30-i)).isoformat(),source='家长观察',note='',
                        word_check=dict(word='syntheticword'+str(i),meaning='虚构目标义',material='虚构词表',phase='首次核对',results={'meaning_spelling':'提示后答对'}))
        self.evaluate()
        included={goals.word_history([json.loads(e['text'])],self.now.date())['words'][0]['word'] for e in self.last_input['evidence'] if e['ref'].startswith('record:')}
        self.assertEqual({r['word'] for r in self.last_input['progress']},included)
        self.assertLessEqual(len(included),24);self.assertGreater(self.last_input['omitted_records'],0)
        self.assertIn('首末对照',self.last_input['progress_scope'])

    def test_word_status_and_interval_retest_candidates_follow_stated_rules(self):
        today=self.now.date();ago=lambda n:(today-dt.timedelta(days=n)).isoformat()
        check=lambda day,word_check:self.action('feedback',id=self.ident,day=day,source='家长观察',note='',word_check=word_check)
        pen=dict(word='pen',meaning='写字用的笔',material='虚构词表',phase='首次核对',results=dict(hear_meaning='答错'))
        check(ago(20),pen)
        check(ago(13),dict(pen,phase='刚练过或看过答案',results=dict(hear_meaning='提示后答对')))
        check(ago(12),dict(pen,results=dict(hear_meaning='本次独立答对',read_meaning='本次独立答对')))
        check(ago(2),dict(pen,word='fence',meaning='围栏',results=dict(read_meaning='答错')))
        history=self.goal()['word_history'];self.assertEqual(history['retest_days'],goals.WORD_RETEST_DAYS)
        status={(w['word'],w['meaning']):w for w in history['words']}
        hear=status[('pen','写字用的笔')]['directions']['hear_meaning']
        # A next-day independent answer is only "once"; the previous same-direction check was one day earlier.
        self.assertEqual((hear['status'],hear['day'],hear['gap_days'],hear['days_since'],hear['verified'],hear['retest_due']),('一次独立答对',ago(12),1,12,False,True))
        read=status[('pen','写字用的笔')]['directions']['read_meaning']
        self.assertEqual((read['status'],read['gap_days'],read['retest_due']),('一次独立答对',None,True))
        self.assertNotIn('hear_spelling',status[('pen','写字用的笔')]['directions'],'untested directions stay unknown')
        self.assertEqual(status[('fence','围栏')]['directions']['read_meaning']['status'],'最近答错')
        self.assertEqual(status[('fence','围栏')]['retest_due'],[],'wrong answers need practice, not an interval retest')
        self.assertEqual(history['retest_candidates'],[dict(word='pen',meaning='写字用的笔',modes=['hear_meaning','read_meaning'],day=ago(12))])
        # A spaced retest recorded 10 days after the previous hear check verifies that direction only.
        check(ago(2),dict(pen,phase='间隔后复测',results=dict(hear_meaning='本次独立答对')))
        words={(w['word'],w['meaning']):w for w in self.goal()['word_history']['words']}
        hear=words[('pen','写字用的笔')]['directions']['hear_meaning']
        self.assertEqual((hear['status'],hear['gap_days'],hear['verified'],hear['retest_due']),('间隔后独立答对',10,True,False))
        self.assertEqual(words[('pen','写字用的笔')]['verified'],['hear_meaning']);self.assertEqual(words[('pen','写字用的笔')]['retest_due'],['read_meaning'])
        self.assertEqual(self.goal()['word_history']['retest_candidates'][0]['modes'],['read_meaning'])
        # Without the 间隔后复测 condition, an interval retest too soon afterwards, or a prompted answer, is not verification.
        check(ago(2),dict(pen,results=dict(read_meaning='本次独立答对')))
        read=next(w for w in self.goal()['word_history']['words'] if w['word']=='pen')['directions']['read_meaning']
        self.assertEqual((read['status'],read['gap_days'],read['verified'],read['retest_due']),('一次独立答对',10,False,False))
        check(ago(1),dict(pen,phase='间隔后复测',results=dict(read_meaning='本次独立答对')))
        read=next(w for w in self.goal()['word_history']['words'] if w['word']=='pen')['directions']['read_meaning']
        self.assertEqual((read['status'],read['gap_days'],read['verified'],read['retest_due']),('一次独立答对',1,False,False))
        self.assertEqual(self.goal()['word_history']['retest_candidates'],[],'a check within the interval is not yet due again')
        check(ago(0),dict(pen,phase='间隔后复测',results=dict(hear_meaning='提示后答对')))
        hear=next(w for w in self.goal()['word_history']['words'] if w['word']=='pen')['directions']['hear_meaning']
        self.assertEqual((hear['status'],hear['verified'],hear['retest_due']),('提示后答对',False,False))
        # Same-day results that differ are reported rather than ordered by guess.
        check(ago(0),dict(pen,phase='首次核对',results=dict(hear_meaning='答错')))
        hear=next(w for w in self.goal()['word_history']['words'] if w['word']=='pen')['directions']['hear_meaning']
        self.assertEqual((hear['status'],hear['retest_due'],hear['verified']),('同日多次结果不一',False,False))
        # Direct projection with an explicit date: candidates are capped and the overflow is counted.
        records=[dict(id=i,day=ago(9),source='家长观察',note=goals.word_check_note(dict(pen,word='w%02d'%i,results=dict(read_meaning='本次独立答对')))) for i in range(25)]
        projected=goals.word_history(records,today=today)
        self.assertEqual((len(projected['retest_candidates']),projected['retest_omitted']),(goals.WORD_RETEST_LIMIT,5))
        self.assertEqual(projected['retest_candidates'][0]['word'],'w00')
        self.assertEqual(goals.word_history(records,today=today-dt.timedelta(days=5))['retest_candidates'],[],'not due before the interval')
        odd=goals.word_history([dict(records[0],day='未知日期')],today=today)['words'][0]['directions']['read_meaning']
        self.assertEqual((odd['status'],odd['retest_due']),('日期无法核对',False))

    def test_word_status_does_not_infer_order_or_future_results(self):
        rows=[dict(day='2026-09-01',phase='首次核对',results={'hear_meaning':'本次独立答对'}),
              dict(day='2026-09-10',phase='间隔后复测',results={'hear_meaning':'本次独立答对'})]
        today=dt.date(2026,9,14)
        conflicting=rows+[dict(rows[-1],phase='刚练过或看过答案')]
        for checks in (conflicting,list(reversed(conflicting))):
            result=goals.word_status(checks,today)['hear_meaning']
            self.assertEqual((result['status'],result['verified'],result['retest_due']),('同日核对条件不一',False,False))
        future=goals.word_status(rows,dt.date(2026,9,5))['hear_meaning']
        self.assertEqual((future['status'],future['verified'],future['retest_due']),('日期在未来，待核对',False,False))
        unknown=goals.word_status(rows+[dict(rows[-1],day='未知日期')],today)['hear_meaning']
        self.assertEqual((unknown['status'],unknown['verified']),('日期无法核对',False))

    def test_word_history_retains_dates_senses_and_current_corrections_beyond_model_window(self):
        check=dict(word='pen',meaning='写字用的笔',material='虚构词表',phase='首次核对',results=dict(hear_meaning='答错'))
        past=(self.now.date()-dt.timedelta(days=3)).isoformat();today=self.now.date().isoformat()
        first=self.action('feedback',id=self.ident,day=past,source='家长观察',note='',word_check=check)['record_id']
        second=self.feedback('',word_check=dict(check,phase='间隔后复测',results=dict(hear_meaning='本次独立答对')))['record_id']
        third=self.feedback('',word_check=dict(check,meaning='围栏',results=dict(read_meaning='提示后答对')))['record_id']
        for i in range(30):self.feedback('虚构日常反馈 '+str(i))
        g=self.goal();history=g['word_history']['checks']
        self.assertEqual([r['id'] for r in history],[third,second,first])
        self.assertEqual([r['day'] for r in history],[today,today,past])
        self.assertEqual([r['meaning'] for r in history],['围栏','写字用的笔','写字用的笔'])
        self.assertEqual(history[1]['results']['hear_meaning'],'本次独立答对')
        self.assertEqual(history[2]['results']['hear_meaning'],'答错')
        self.assertEqual(history[1]['results']['hear_spelling'],'未测')
        self.assertEqual(len(g['records']),24);self.assertGreater(g['omitted_count'],0)
        self.assertNotIn(second,{r['id'] for r in g['records']})
        self.assertEqual(goals.Store(self.app).snapshot()['goals'][0]['word_history'],g['word_history'])
        # Correct the same original record, keeping its revision; no stale second database.
        base=dict(id=second,child='示例甲',day=today,category='家长观察',title='已更正的核对',source='家长观察')
        self.app.save_record(dict(base,note=goals.word_check_note(dict(check,phase='刚练过或看过答案',results=dict(hear_meaning='提示后答对')))))
        updated=next(r for r in self.goal()['word_history']['checks'] if r['id']==second)
        self.assertEqual(updated['results']['hear_meaning'],'提示后答对');self.assertEqual(updated['phase'],'刚练过或看过答案')
        malformed=goals.word_check_note(check).replace('听英文 → 选中文：答错','听英文 → 选中文：需重测')
        self.app.save_record(dict(base,note=malformed))
        history=self.goal()['word_history'];self.assertNotIn(second,{r['id'] for r in history['checks']})
        self.assertEqual(history['unparsed'],[dict(id=second,day=today)])
        self.app.save_record(dict(base,note='更正：这次仅讨论词义，没有测验。'))
        history=self.goal()['word_history'];self.assertFalse(history['unparsed'])
        self.assertNotIn(second,{r['id'] for r in history['checks']})
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM revisions WHERE record_id=?',(second,)).fetchone()[0],3)

    def reply(self,messages,schema,name,timeout,**kwargs):
        self.assertEqual(name,'family_learning_plan');self.assertEqual(kwargs['data_path'],self.data)
        with sqlite3.connect(self.app.DB,timeout=.1) as c:c.execute('BEGIN IMMEDIATE');c.rollback()
        value=json.loads(messages[-1]['content']);self.last_input=value;e=value['evidence'][-1]
        properties=schema['properties']['proposal']['properties']
        refs=[e['ref'] for e in value['evidence']]
        self.assertEqual(properties['evidence']['items']['properties']['ref']['enum'],refs)
        for field in ('support','against'):
            self.assertEqual(properties['hypotheses']['items']['properties'][field]['items']['enum'],
                             [e['ref'] for e in value['evidence'] if not e['ref'].startswith('school:') and e.get('kind')!='school_requirement'])
        self.assertNotIn('enum',goals.PROPOSAL['properties']['evidence']['items']['properties']['ref'])
        return synthetic_plan(value)

    def evaluate(self):
        result=self.store.process(self.ident,self.now,explicit=True);self.assertEqual(result['state'],'ready');return self.goal()

    def approve(self,g=None,**overrides):
        g=g or self.goal();return self.action('approve',id=self.ident,expected_version=g['version'],proposal_id=g['pending']['id'],context_hash=g['context_hash'],**overrides)

    def test_linked_teaching_task_attempts_reach_only_that_goal_and_memory_waits_for_approval(self):
        import family_guided, family_learner_memory as lm
        self.ident=self.action('create',child_id='child-1',title='虚构学校要求：说清时间线索',subject='英语',
                               school_target='学校要求：朗读后说出句子里的时间线索。')['id']
        self.assertEqual(self.goal()['records'],[])
        self.approve(self.evaluate())
        def remembered():
            with self.store.agent._db() as c:return len(lm.timeline(c,'child-1',self.ident))
        memory=remembered()
        parent,child=family_guided.Store(self.app),family_guided.Store(self.app,authorize=lambda c,child_id:None)
        def material(title,**extra):
            self.count+=1
            body=dict(request_key='synthetic-guided-'+str(self.count).zfill(8),child_id='child-1',version=0,title=title,subject='英语',
                      question_text='虚构句子：He reads after dinner. 时间线索是什么？',question_attachments=[],reference_text='after dinner',
                      reference_checked=True,shared=True,**extra)
            return body,parent.save_material(body)
        body,saved=material('虚构关联任务',goal_id=self.ident)
        self.assertEqual(parent.save_material(body)['session_id'],saved['session_id'])
        linked,unlinked=saved['session_id'],material('虚构同科未关联任务')[1]['session_id']
        def act(ident,**fields):
            self.count+=1;version=next(s for s in parent.snapshot()['sessions'] if s['id']==ident)['version']
            child.action(dict(request_key='synthetic-attempt-'+str(self.count).zfill(8),child_id='child-1',id=ident,version=version,**fields))
        with patch.object(family_guided.family_llm,'guided_hint',return_value=dict(hint='先找表示时间的词。',question='哪几个词说明什么时候？',uncertainties=[])):
            act(linked,action='attempt',kind='first',text='我觉得是 reads。',assistance='')
            act(linked,action='hint')
            act(linked,action='attempt',kind='explain_again',text='是 after dinner。',assistance='少量提示')
            act(unlinked,action='attempt',kind='first',text='未关联任务的回答。',assistance='')
        sessions={s['id']:s for s in parent.snapshot()['sessions']}
        first,second=[e['record_id'] for e in sessions[linked]['events'] if e['kind']=='attempt']
        other=next(e['record_id'] for e in sessions[unlinked]['events'] if e['kind']=='attempt')
        g=self.goal();seen={r['id']:r for r in g['records']}
        self.assertEqual(set(seen),{first,second})                          # the same-subject unlinked task stays out
        self.assertEqual((seen[first]['assistance'],seen[second]['assistance'],seen[second]['related_record_id']),('','少量提示',first))
        self.assertIn('已提供 0 条系统提示',seen[first]['comparison_note']);self.assertIn('已提供 1 条系统提示',seen[second]['comparison_note'])
        self.assertIn('不据此认定独立完成或掌握',seen[second]['comparison_note'])
        self.assertTrue(all(r['source']==family_guided.SOURCE+linked for r in seen.values()))
        plan_before=g['current_plan'];self.assertTrue(g['evidence_changed'])        # the earlier analysis awaits update
        self.assertEqual(remembered(),memory)
        refs=['record:%d'%first,'record:%d'%second]
        def cites(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content']);self.last_input=value;plan=synthetic_plan(value)
            plan['proposal']['hypotheses'][0].update(support=[refs[1]],against=[refs[0]],status='有支持');return plan
        self.model.side_effect=cites
        pending=self.evaluate()
        self.assertLessEqual(set(refs),{e['ref'] for e in self.last_input['evidence']})
        self.assertNotIn('record:%d'%other,json.dumps(self.last_input))
        self.assertEqual(pending['current_plan'],plan_before);self.assertEqual(remembered(),memory)   # a suggestion is not memory
        self.approve(pending)
        self.assertGreater(remembered(),memory)
        with self.store.agent._db() as c:card=next(x for x in lm.learner_card(c,'child-1') if x['goal_id']==self.ident)
        self.assertIn(refs[1],json.dumps(card))
        # The attempt itself stays immutable; a parent's linked correction and an out-of-band move both mark the analysis stale.
        note=self.app.save_record(dict(child='示例甲',day=self.now.date().isoformat(),category='学习进展',title='家长补充观察',
            note='家长更正：再次表达前孩子看过参考。',related_record_id=second,followup_kind='补充观察',assistance='看过讲解或答案'))['record']['id']
        g=self.goal();self.assertIn(note,{r['id'] for r in g['records']});self.assertTrue(g['evidence_changed'])
        plan_now=g['current_plan']
        with self.app.connect() as c:c.execute("UPDATE records SET child='示例乙' WHERE id=?",(second,));c.commit()
        g=self.goal();self.assertEqual(g['hypotheses_detail'][0]['corrected'],[refs[1]])
        self.assertNotIn(second,{r['id'] for r in g['records']});self.assertEqual(g['current_plan'],plan_now)
        mate=self.action('create',child_id='child-2',title='虚构另一孩子目标',subject='英语',baseline='家长观察：虚构。')['id']
        self.assertEqual(next(x for x in self.store.snapshot()['goals'] if x['id']==mate)['records'],[])

    def test_lifecycle_coalesces_same_day_and_updates_same_task(self):
        self.assertEqual(self.goal()['records'],[])
        one=self.feedback();two=self.feedback('家长观察：晚些时候不用提示，能说出一条线索。')
        g=self.evaluate();self.assertEqual(len(self.last_input['evidence']),3)
        self.assertIsNone(g['current_plan']);self.assertEqual(len(g['records']),2)
        original=self.approve(g)['task_id'];self.assertTrue(original)
        agent.family_task_focus.save(self.app,dict(id=original,version=0,request_key='synthetic-task-card-wording',mode='next',next_action='旧可选做法',waiting_for='',review_on='',title='家长另写的旧标题',goal='家长另写的旧目标'))
        g=self.goal();self.assertFalse(g['evidence_changed']);self.assertIsNone(g['pending'])
        self.feedback('第二次家长转述：同样练习很无聊，愿意换口头讲解。')
        self.assertTrue(self.goal()['evidence_changed']);g=self.evaluate()
        self.assertEqual(self.last_input['current_plan']['title'],'先核对一个判断过程')
        payload=dict(action='approve',id=self.ident,expected_version=g['version'],proposal_id=g['pending']['id'],context_hash=g['context_hash'],request_key='synthetic-repeat-approval')
        self.assertEqual(self.store.action(payload)['task_id'],original)
        self.assertTrue(self.store.action(payload)['replayed'])
        task=next(t for t in self.app.tasks() if t['id']==original)
        self.assertEqual(task['title'],self.goal()['current_plan']['title']);self.assertEqual(task['focus']['next_action'],'')
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM task_history').fetchone()[0],1)
        self.assertEqual(len(self.goal()['history']),2)
        restarted=goals.Store(self.app).snapshot();self.assertEqual(restarted['goals'][0]['task_id'],original)

    def test_concurrent_feedback_and_approval_corrections_keep_formal_plan(self):
        self.feedback();g=self.evaluate();self.approve(g);original=self.goal()['current_plan']
        self.feedback('一次练习靠提示完成');g=self.evaluate()
        self.feedback('补充：孩子没有独立做过')
        with self.assertRaises(agent.AgentError) as raised:self.approve(g)
        self.assertEqual(raised.exception.status,409);self.assertEqual(self.goal()['current_plan'],original)
        g=self.evaluate();self.action('keep',id=self.ident,expected_version=g['version'],proposal_id=g['pending']['id'])
        self.assertEqual(self.goal()['current_plan'],original);self.assertEqual(len(self.goal()['records']),3)
        g=self.goal();self.action('edit',id=self.ident,expected_version=g['version'],baseline='更正：不是已确认知识缺口，仅为观察。')
        with self.assertRaises(agent.AgentError):self.action('edit',id=self.ident,expected_version=g['version'],baseline='陈旧填写')
        self.assertTrue(self.goal()['evidence_changed'])

    def test_old_edited_plan_cannot_be_approved_as_new_proposal(self):
        self.feedback();old=self.evaluate();old_plan=old['pending']
        self.feedback('新增需要进一步核对的情况');new=self.evaluate()
        with self.assertRaises(agent.AgentError):self.action('approve',id=self.ident,expected_version=new['version'],proposal_id=new['pending']['id'],context_hash=old['context_hash'],plan=old_plan)
        self.assertIsNone(self.goal()['current_plan'])

    def test_record_correction_invalidates_proposal_and_keeps_history(self):
        ident=self.feedback()['record_id'];g=self.evaluate();self.approve(g)
        self.feedback('另一次尝试');g=self.evaluate()
        self.app.save_record(dict(id=ident,child='示例甲',day=self.now.date().isoformat(),category='家长观察',title='学习目标反馈',note='更正：当时看过答案，并非独立解释。',source='家长转述孩子 · 学习目标:'+self.ident,assistance='看过讲解或答案'))
        self.assertTrue(self.goal()['evidence_changed']);self.assertIsNone(self.goal()['pending'])
        with self.assertRaises(agent.AgentError):self.approve(g)
        with self.app.connect() as c:self.assertGreater(c.execute('SELECT count(*) FROM revisions').fetchone()[0],0)

    def test_input_changes_during_inference_discard_old_suggestion(self):
        original=self.reply
        def change(*a,**k):
            answer=original(*a,**k);self.feedback('分析期间新增反馈');return answer
        self.model.side_effect=change
        result=self.store.process(self.ident,self.now,explicit=True)
        self.assertEqual(result,dict(state='stale',created=0,used=1));self.assertIsNone(self.goal()['pending'])

    def test_feedback_retry_after_rename_and_child_isolation(self):
        original=bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010804000000b51c0c020000000b4944415478da63fcff1f0003030200ef9a590d0000000049454e44ae426082')
        upload=self.app.save_upload(io.BytesIO(original),len(original),'synthetic-evidence.png')['id']
        payload=dict(action='feedback',id=self.ident,request_key='synthetic-feedback-stable',day=self.now.date().isoformat(),source='家长观察',note='独立解释仍需要核对。',attachments=[upload])
        read_store=goals.Store(self.app,self.app.agent_store(read_only=True))
        self.assertEqual(read_store.feedback_receipt(self.ident,payload['request_key'],payload['source'])['state'],'missing')
        first=self.store.action(payload);g=self.goal();plan=g['current_plan']
        self.assertEqual(read_store.feedback_receipt(self.ident,payload['request_key'],payload['source']),dict(state='linked',record_id=first['record_id']))
        self.action('edit',id=self.ident,expected_version=g['version'],title='修改后的阶段名称',subject='综合')
        replay=self.store.action(payload)
        self.assertEqual(replay['record_id'],first['record_id']);self.assertTrue(replay['replayed'])
        self.app.save_profile(dict(child_id='child-1',name='示例甲新称呼',grade='四年级',classroom='',reason='虚构档案称呼更正',version=0))
        self.assertEqual(read_store.feedback_receipt(self.ident,payload['request_key'],payload['source'])['state'],'linked')
        with self.app.connect() as c:
            rows=c.execute('SELECT note,attachments,request_key FROM records WHERE source=?',('家长观察 · 学习目标:'+self.ident,)).fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['note'],payload['note'])
        self.assertEqual(json.loads(rows[0]['attachments']),[upload]);self.assertEqual((self.data/'uploads'/upload).read_bytes(),original)
        self.assertEqual(self.goal()['current_plan'],plan)
        with self.assertRaises(self.app.RecordError):self.store.action(dict(payload,note='另一份文字不能复用原提交标识'))
        second=self.app.save_record(dict(child='示例乙',day=self.now.date().isoformat(),category='家长观察',title='另一位孩子的记录',note='不能串用',source='家长观察'))
        with self.assertRaises(agent.AgentError):self.action('link',id=self.ident,expected_version=self.goal()['version'],record_ids=[second['record_id']])
        self.assertEqual(len(self.goal()['records']),1)
        self.assertEqual(read_store.feedback_receipt(self.ident,payload['request_key'],'老师反馈')['state'],'changed')
        self.resave(first['record_id'],note='更正后的原话')
        self.assertEqual(read_store.feedback_receipt(self.ident,payload['request_key'],payload['source'])['state'],'changed')
        with self.assertRaises(self.app.RecordError) as changed:self.store.action(payload)
        self.assertEqual((changed.exception.status,changed.exception.code),(409,'request_record_changed'))
        self.resave(first['record_id'],source='老师反馈 · 学习目标:'+self.ident)
        self.assertEqual(read_store.feedback_receipt(self.ident,payload['request_key'],payload['source'])['state'],'changed')

    def test_feedback_receipt_repairs_saved_but_unlinked_record(self):
        key='synthetic-unlinked-feedback'
        payload=dict(action='feedback',id=self.ident,request_key=key,day=self.now.date().isoformat(),source='家长观察',note='孩子说了大意，转折待核对。')
        saved=self.app.save_record(dict(child='示例甲',day=payload['day'],category='家长观察',subject='',title='学习目标反馈',note=payload['note'],source='家长观察 · 学习目标:'+self.ident,assistance='',practice_relation='',attachments=[],request_key='goal-feedback-'+agent._hash([self.ident,key])[:64]))
        read_store=goals.Store(self.app,self.app.agent_store(read_only=True))
        self.assertEqual(read_store.feedback_receipt(self.ident,key,payload['source']),dict(state='unlinked',record_id=saved['record_id']))
        self.assertEqual(self.store.action(payload)['record_id'],saved['record_id'])
        self.assertEqual(read_store.feedback_receipt(self.ident,key,payload['source'])['state'],'linked')
        self.assertEqual(len(self.goal()['records']),1)

    def test_feedback_changed_between_record_save_and_goal_link_is_not_linked(self):
        before=self.goal()['current_plan'];save=self.app.save_record
        for kind,changes in [('source',{'source':'老师反馈 · 学习目标:'+self.ident}),('child',{'child':'示例乙'})]:
            with self.subTest(kind=kind):
                key='synthetic-feedback-link-race-'+kind
                payload=dict(action='feedback',id=self.ident,request_key=key,day=self.now.date().isoformat(),source='家长观察',note='虚构原话待核对。')
                def change_before_link(obj):
                    saved=save(obj)
                    with self.app.connect() as c: row=dict(c.execute('SELECT * FROM records WHERE id=?',(saved['record_id'],)).fetchone())
                    save(dict({name:row[name] or '' for name in ('child','day','category','subject','title','note','source','assistance','practice_relation')},id=saved['record_id'],**changes))
                    return saved
                with patch.object(self.app,'save_record',side_effect=change_before_link):
                    with self.assertRaises(agent.AgentError) as changed:self.store.action(payload)
                self.assertEqual((changed.exception.status,changed.exception.code),(409,'goal_feedback_changed'))
                self.assertEqual(self.store.feedback_receipt(self.ident,key,payload['source'])['state'],'changed')
                self.assertEqual(self.goal()['records'],[])
                self.assertEqual(self.goal()['current_plan'],before)
        with self.store.agent._db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],2)

    def test_feedback_survives_model_failure_without_a_fake_plan(self):
        saved=self.feedback('孩子独立说出大意，但漏了转折。')
        self.model.side_effect=goals.family_llm.LLMDraftError('synthetic offline')
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'error')
        g=self.goal();self.assertEqual([r['id'] for r in g['records']],[saved['record_id']])
        self.assertIsNone(g['pending']);self.assertIsNone(g['current_plan'])

    def test_manual_plan_offline_pause_and_study_result_link(self):
        self.model.side_effect=goals.family_llm.LLMDraftError('offline')
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'error')
        g=self.goal();p=dict(title='家长安排一次核对',goal='听孩子的解释',action='用已有课本，请孩子选题讲一讲。',review_on=self.now.date().isoformat(),estimated_minutes=10)
        task=self.action('manual',id=self.ident,expected_version=g['version'],context_hash=g['context_hash'],plan=p)['task_id']
        g=self.goal();self.action('pause',id=self.ident,expected_version=g['version'])
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'paused')
        g=self.goal();self.action('manual',id=self.ident,expected_version=g['version'],context_hash=g['context_hash'],plan=p)
        self.assertEqual(self.goal()['lifecycle'],'paused')
        record=self.feedback('今日作业中的真实结果')['record_id']
        family_study.Store(self.app)
        with self.app.connect() as c:
            c.execute("INSERT INTO study_items(id,child_id,day,task_id,title,subject,record_id,version,creation_hash,last_request_key,last_request_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?)",('study-test','child-1',self.now.date().isoformat(),task,'示例作业','英语',record,1,'h','k','h'))
            row=c.execute('SELECT plan FROM agent_items WHERE id=?',(self.ident,)).fetchone();plan=json.loads(row['plan']);plan['learning']['record_ids']=[]
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),self.ident))
        self.assertEqual(self.goal()['records'][0]['id'],record)
        self.assertEqual(self.goal()['lifecycle'],'paused')

    def test_reject_fabricated_evidence_and_worker_skips_raw_record(self):
        self.feedback()
        response=self.reply
        def invalid(*a,**k):
            answer=response(*a,**k);answer['proposal']['hypotheses'][0]['support']=['record:999999'];return answer
        self.model.side_effect=invalid
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'error')
        self.assertIsNone(self.goal()['pending'])
        self.model.side_effect=response
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[])))
        self.now+=dt.timedelta(hours=1)
        agent.run_once(self.app,now=self.now)
        self.assertIsNotNone(self.goal()['pending'])
        with self.app.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM agent_jobs WHERE id LIKE 'record:%'").fetchone()[0],0)

    def test_unknown_causes_and_raw_feedback_drive_same_plan_without_promoting_guesses(self):
        self.action('edit',id=self.ident,expected_version=self.goal()['version'],baseline='不知道卡在哪里。',
                    hypotheses='未经验证的词义猜测',verification='计划尝试听音比较，但尚未执行')
        first=self.evaluate()
        facts='\n'.join(e['text'] for e in self.last_input['evidence'])
        self.assertIn('不知道卡在哪里',facts)
        self.assertNotIn('未经验证的词义猜测',facts)
        self.assertNotIn('计划尝试听音比较',facts)
        self.assertEqual(self.last_input['learning_goal']['hypotheses'],'未经验证的词义猜测')
        self.assertEqual(goals.SCHEMA['properties']['proposal']['type'],'object')
        task=self.approve(first)['task_id'];original=self.goal()['current_plan']
        self.feedback('读过解释后答对了原题；孩子说困了，不想再写。',assistance='看过讲解或答案',practice_relation='同一道题或同一片段')
        def adjusted(*args,**kwargs):
            answer=self.reply(*args,**kwargs);p=answer['proposal']
            p.update(choice='暂停',estimated_minutes=None,why_now='本次有疲倦反馈；看过解释后答对原题不代表独立掌握。',
                     action='今天结束练习，保留原目标；休息后再安排一小步。')
            return answer
        self.model.side_effect=adjusted
        pending=self.evaluate()
        self.assertEqual(self.last_input['current_plan'],original)
        self.assertIn('看过讲解或答案',self.last_input['evidence'][-1]['text'])
        self.assertEqual(pending['pending']['choice'],'暂停')
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident))
        invalid={'proposal':{k:v for k,v in pending['pending'].items() if k in goals.PROPOSAL['required']}};invalid['proposal']['estimated_minutes']=5
        with self.assertRaisesRegex(agent.AgentError,'暂停建议'):self.store._proposal(invalid,ctx,self.now)
        self.assertEqual(pending['current_plan'],original)
        self.assertEqual(self.approve(pending)['task_id'],task)
        self.assertIn('今天结束练习',self.goal()['current_plan']['action'])
        self.feedback('家长还不知道下次怎么安排。')
        self.model.side_effect=lambda *a,**k:{'proposal':None}
        self.assertEqual(self.store.process(self.ident,self.now,explicit=True)['state'],'error')
        self.assertIsNone(self.goal()['pending'])
        self.assertIn('今天结束练习',self.goal()['current_plan']['action'])

    def test_school_requirements_are_citable_but_never_proof_of_a_learning_deficit(self):
        original='虚构课堂任务：任选一种说明顺序，介绍文具的两点用途；篇幅和截止未说明。'
        self.action('edit',id=self.ident,expected_version=self.goal()['version'],school_target=original)
        g=self.evaluate();requirement=next(e for e in self.last_input['evidence'] if e.get('kind')=='school_requirement')
        self.assertEqual(requirement['text'],original)
        self.assertEqual(g['pending']['evidence'][0]['ref'],requirement['ref'])
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident))
        for field in ('support','against'):
            invalid=synthetic_plan(self.last_input);invalid['proposal']['hypotheses'][0][field]=[requirement['ref']]
            with self.assertRaisesRegex(agent.AgentError,'学校要求不是'):self.store._proposal(invalid,ctx,self.now)
        self.approve(g)
        self.action('edit',id=self.ident,expected_version=self.goal()['version'],school_target='虚构老师更正：本次只介绍一个用途。')
        updated=self.goal();self.assertTrue(updated['evidence_changed'])
        self.assertEqual(updated['history'][-1]['previous']['school_target'],original)
        self.assertIsNotNone(updated['current_plan'])
        other=self.action('create',child_id='child-2',title='另一位孩子的目标',subject='语文')['id']
        with self.store.agent._db() as c:other_context=self.store._context(c,self.store._get(c,other))
        self.assertFalse(any(e.get('kind')=='school_requirement' for e in other_context['evidence']))

    def test_plan_keeps_the_teachers_words_a_check_and_an_unknown_baseline_until_the_parent_confirms(self):
        source=dict(id='synthetic-school-writing',platform='wechat',child_id='child-2',name='虚构语文班级',cursor='0',enabled=True)
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        original='语文习作：介绍一处你喜欢的地方。写2-3个理由，每段有中心句，结合看到、听到、闻到的感官体验；篇幅与截止未说明。'
        quote='写2-3个理由，每段有中心句';inputs=[];changes={}
        def plan(value):
            school=[e for e in value['evidence'] if e['ref'].startswith('school:message:')]
            result=synthetic_plan(value)
            if not school:return result
            result['proposal'].update(title='习作：介绍一处喜欢的地方',goal='按老师要求写出2-3个理由，每段有中心句',
                action='第一步：先口述想介绍的地方和两个理由。\n第二步：给每个理由说一句中心句。\n第三步：补上当时看到、听到或闻到的。\n第四步：对照老师要求自查。',
                mastery_check='学习表现记录：孩子原话、实际帮助、卡住的步骤；完成习作不等于独立掌握。',
                evidence=[dict(ref=school[-1]['ref'],quote=quote)])
            result['proposal'].update(changes);return result
        def model(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content'])
            if name=='family_agent_selection':
                return dict(proposals=[synthetic_school_proposal(e,'语文','语文：介绍喜欢的地方',
                    '介绍一处喜欢的地方，写2–3个理由；每段有中心句，结合看到、听到、闻到的感官体验。篇幅与截止未说明。') for e in value['evidence']])
            inputs.append(value);return plan(value)
        self.model.side_effect=model
        self.store.agent.ingest(dict(source_id=source['id'],expected_cursor='0',cursor='1',checked_at=self.now.isoformat(),last_message_time=self.now.isoformat(),error='',
            messages=[dict(id='1',time=self.now.isoformat(),kind='text',sender='虚构老师',text=original,unread=False)]))
        goal=lambda:next(g for g in self.store.snapshot()['goals'] if g['child_id']=='child-2')
        # A generic plan that drops the teacher's words never reaches the parent.
        changes.update(evidence=[dict(ref='',quote='尚无作答证据')])
        def generic(value):
            result=plan(value);result['proposal']['evidence'][0]['ref']=value['evidence'][0]['ref'];return result
        self.model.side_effect=lambda messages,schema,name,timeout,**k:(model(messages,schema,name,timeout,**k) if name=='family_agent_selection'
            else generic(json.loads(messages[-1]['content'])))
        agent.run_once(self.app,self.now);g=goal()
        self.assertEqual(g['baseline'],goals.SCHOOL_BASELINE);self.assertEqual(g['school_messages'][0]['text'],original)
        self.assertIsNone(g['pending']);self.assertEqual(g['processing'],'error');self.assertIsNone(g['current_plan'])
        changes.clear();self.model.side_effect=model;self.now+=dt.timedelta(hours=1);agent.run_once(self.app,self.now);g=goal()
        self.assertEqual(g['pending']['evidence'],[dict(ref=g['school_messages'][0]['ref'],quote=quote)])
        self.assertEqual([h['status'] for h in g['pending']['hypotheses']],['待验证'])
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,g['id']))
        value=inputs[-1];background=value['evidence'][0]['ref'];self.assertIn('尚无作答证据',value['evidence'][0]['text'])
        invalid=plan(value);invalid['proposal']['hypotheses'][0].update(support=[background],status='有支持')
        with self.assertRaisesRegex(agent.AgentError,'尚无作答证据'):self.store._proposal(invalid,ctx,self.now)
        invalid=plan(value);invalid['proposal']['mastery_check']=''
        with self.assertRaises(agent.AgentError):self.store._proposal(invalid,ctx,self.now)
        pause=plan(value);pause['proposal'].update(choice='暂停',estimated_minutes=None,mastery_check='',evidence=[dict(ref=background,quote='尚无作答证据')])
        self.assertEqual(self.store._proposal(pause,ctx,self.now)['choice'],'暂停')
        self.action('approve',id=g['id'],expected_version=g['version'],proposal_id=g['pending']['id'],context_hash=g['context_hash'])
        g=goal();confirmed=g['current_plan'];self.assertIn('学习表现记录',confirmed['mastery_check']);self.assertTrue(confirmed['review_on'])
        requirement,=g['school_tasks']
        self.assertEqual(requirement['goal'],next(t for t in self.app.tasks() if t['id']==requirement['id'])['action'])
        for condition in ('2–3个理由','每段有中心句','感官体验','篇幅与截止未说明'):
            self.assertIn(condition,requirement['goal'])
        self.assertEqual([(e['quote'],e['available'],e['quote_changed']) for e in g['reviewed_evidence']],[(quote,True,False)])
        card=lambda:json.dumps([dict(r) for r in self.app.connect().execute('SELECT * FROM manual_tasks WHERE id=?',(g['task_id'],))],ensure_ascii=False)
        shown=card();self.assertIn('第一步',shown)
        for private in ('学习表现记录',g['assessment'],g['hypotheses_detail'][0]['reason']):self.assertNotIn(private,shown)
        # Feedback proposes an adjustment; the formal plan and the child's task card wait for the parent.
        self.action('feedback',id=g['id'],day=self.now.date().isoformat(),source='家长转述孩子',note='孩子原话：我喜欢外婆家的院子，因为有桂花香；第二个理由想不出来。')
        def adjusted(value):
            said=next(e for e in value['evidence'] if '想不出来' in e['text'])
            return dict(choice='调整',why_now='第二个理由想不出来，先只补一个理由。',evidence=[dict(ref=value['evidence'][-1]['ref'],quote=quote),dict(ref=said['ref'],quote='第二个理由想不出来')])
        self.model.side_effect=lambda messages,schema,name,timeout,**k:(changes.update(adjusted(json.loads(messages[-1]['content']))) or model(messages,schema,name,timeout,**k))
        self.now+=dt.timedelta(minutes=1);agent.run_once(self.app,self.now);after=goal()
        self.assertIn(original,[e['text'] for e in inputs[-1]['evidence']]);self.assertEqual(inputs[-1]['current_plan'],confirmed)
        self.assertEqual(after['pending']['choice'],'调整');self.assertEqual(after['pending']['evidence'][0]['quote'],quote)
        self.assertEqual(after['current_plan'],confirmed);self.assertEqual(card(),shown);self.assertNotIn('桂花香',shown)

    def school_scope_fixture(self, *, before_dates=True):
        """Saved, entirely fictional tasks; this tests projection, not model extraction quality."""
        source=dict(id='synthetic-plan-scope',platform='wechat',child_id='child-1',name='虚构来源',cursor='0',enabled=True)
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        first=(self.now.date()+dt.timedelta(days=1)).isoformat();second=(self.now.date()+dt.timedelta(days=2)).isoformat()
        texts={
            'M1':f'请分别完成两项：{first}'+('前' if before_dates else '当日')+f' Unit 3课文读两遍，朗读录音上传班级作业区；{second}前完成练习卷第1–4题，做完检查。',
            'M4':'补充练习卷：第4题选做，第1–3题必做。',
            'M5':'练习卷题目和家长参考分别打印；家长参考仅供家长核对，不给孩子照抄。',
            'M8':'补充 Unit 3朗读：录音要读完整篇，不用背诵。'}
        self.store.agent.ingest(dict(source_id=source['id'],expected_cursor='0',cursor='4',checked_at=self.now.isoformat(),
            last_message_time=self.now.isoformat(),error='',messages=[dict(id=ident,time=(self.now+dt.timedelta(minutes=n)).isoformat(),
                kind='text',sender='虚构英语发布者',text=text,unread=False) for n,(ident,text) in enumerate(texts.items())]))
        def save(title,body,due,refs,*,accept=True,change='new'):
            self.count+=1;key='synthetic-school-scope-'+str(self.count)
            item=dict(child_id='child-1',kind='school',title=title,body=body,due=due,
                evidence=[dict(ref='message:'+source['id']+':'+ref,text=texts[ref]) for ref in refs],
                plan=dict(school_learning=dict(subject='英语',goal_id=self.ident),school_goal_id=self.ident,
                    school_messages=[dict(source_id=source['id'],message_id=ref) for ref in refs],
                    school_task=dict(title=title,goal=body,advice='',state='ready',change=change,target_id='',purpose='learning',policy=agent.SCHOOL_TASK_POLICY)))
            fp=self.store.agent._job(key,dict(sequence=self.count),self.now)
            self.store.agent._save(key,fp,[item],self.now)
            with self.app.connect() as c:ident=c.execute('SELECT id FROM agent_items WHERE job_id=?',(key,)).fetchone()['id']
            if accept:return self.store.agent.act(dict(id=ident,action='accept'))['task_id']
            return ident
        reading=save('英语：Unit 3朗读','Unit 3课文读两遍，朗读录音上传班级作业区。',first,['M1'])
        supplement=save('英语：Unit 3朗读补充',texts['M8'],'',['M8'],accept=False,change='append')
        task=next(t for t in self.app.tasks() if t['id']==reading)
        with self.app.connect() as c:updated=c.execute('SELECT updated FROM agent_items WHERE id=?',(supplement,)).fetchone()['updated']
        agent.apply_school_change(self.app,self.store.agent,dict(action='school_change',id=supplement,target_id=reading,change='append',
            title=task['title'],body=texts['M8'],due='',expected_updated=updated,target_version=task['focus']['version'],target_updated=''))
        return dict(source=source,texts=texts,first=first,second=second,reading=reading,save=save)

    def test_school_plan_scope_keeps_only_linked_reading_and_complete_shared_original(self):
        fixture=self.school_scope_fixture();self.evaluate()
        task,=self.last_input['school_tasks']
        current=next(t for t in self.app.tasks() if t['id']==fixture['reading'])
        self.assertEqual((task['id'],task['title'],task['goal'],task['due_on'],task['category']),
            (current['id'],current['title'],current['action'],fixture['first'],current['agenda']['category']))
        self.assertIn('读两遍',task['goal']);self.assertIn('上传班级作业区',task['goal']);self.assertIn('不用背诵',task['goal'])
        self.assertNotIn('练习卷',task['goal'])
        refs={'school:message:'+fixture['source']['id']+':'+m for m in ('M1','M8')}
        self.assertEqual(set(task['source_refs']),refs)
        originals={e['ref']:e for e in self.last_input['evidence'] if e.get('source_kind')=='group_message'}
        self.assertEqual(set(originals),refs)
        self.assertEqual(originals['school:message:'+fixture['source']['id']+':M1']['text'],fixture['texts']['M1'])
        self.assertTrue(all(e['sender']=='虚构英语发布者' and e['time'] for e in originals.values()))
        effective=next(e for e in self.last_input['evidence'] if e['ref']=='school:task:'+fixture['reading'])
        self.assertEqual(effective['text'],current['action']);self.assertEqual(set(effective['source_refs']),refs)
        self.assertIn('未列入school_tasks的其他事项不能扩为本轮要求',goals.PROMPT)
        # Legacy link lists can omit an already applied append; the current task's publication chain still retains its source.
        with self.app.connect() as c:
            row=c.execute('SELECT id,plan FROM agent_items WHERE id=?',(task['item_id'],)).fetchone();plan=json.loads(row['plan'])
            plan['school_messages']=[dict(source_id=fixture['source']['id'],message_id='M1')]
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),row['id']))
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        self.assertEqual(set(ctx['school_tasks'][0]['source_refs']),refs)
        self.assertEqual({e['ref'] for e in ctx['school_messages']},refs)

    def test_school_plan_scope_keeps_two_linked_tasks_dates_and_optional_reference_limits_separate(self):
        fixture=self.school_scope_fixture()
        worksheet=fixture['save']('英语：练习卷','练习卷第1–3题必做，第4题选做，做完检查。'+
            '保留每题自己的作答，不抄参考。'*30+'题目和家长参考分别打印；家长参考仅供家长核对，不给孩子照抄。',
            fixture['second'],['M1','M4','M5'])
        self.evaluate();tasks={t['id']:t for t in self.last_input['school_tasks']}
        self.assertEqual(set(tasks),{fixture['reading'],worksheet})
        self.assertEqual(tasks[fixture['reading']]['due_on'],fixture['first']);self.assertEqual(tasks[worksheet]['due_on'],fixture['second'])
        self.assertNotIn('练习卷',tasks[fixture['reading']]['goal']);self.assertNotIn('朗读',tasks[worksheet]['goal'])
        self.assertGreater(len(tasks[worksheet]['goal']),400)
        for condition in ('第1–3题必做','第4题选做','做完检查','分别打印','仅供家长核对','不给孩子照抄'):
            self.assertIn(condition,tasks[worksheet]['goal'])
        self.assertEqual(tasks[worksheet]['goal'],next(t for t in self.app.tasks() if t['id']==worksheet)['action'])
        shared='school:message:'+fixture['source']['id']+':M1'
        self.assertTrue(all(shared in t['source_refs'] for t in tasks.values()))
        self.assertEqual(sum(e['ref']==shared for e in self.last_input['evidence']),1)
        self.assertEqual(set(tasks[fixture['reading']]['source_refs']),{shared,'school:message:'+fixture['source']['id']+':M8'})
        shown={t['id']:t for t in self.goal()['school_tasks']}
        self.assertEqual(shown,tasks)
        self.assertEqual(self.goal()['school_tasks_omitted'],0)

    def test_school_completion_checks_cannot_be_regenerated_as_learning_observations(self):
        fixture=self.school_scope_fixture();self.evaluate()
        with self.store.agent._db() as c:
            ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        before=self.goal()
        wrong=synthetic_plan(self.last_input)
        wrong['proposal']['mastery_check']='本次要求自查：朗读要背诵。学习表现记录：记录实际帮助。'
        with self.assertRaisesRegex(agent.AgentError,'不能另列学校完成标准'):
            self.store._proposal(wrong,ctx,self.now)
        self.assertEqual(self.goal(),before)
        observed=synthetic_plan(self.last_input)
        observed['proposal']['mastery_check']='学习表现记录：记录孩子本次自查时的原话、实际帮助和卡住的步骤；是否能独立读尚未知。'
        self.assertEqual(self.store._proposal(observed,ctx,self.now)['mastery_check'],observed['proposal']['mastery_check'])
        self.assertEqual(before['school_tasks'][0]['goal'],next(t for t in self.app.tasks() if t['id']==fixture['reading'])['action'])

    def test_school_execution_plan_cannot_transfer_reading_count_or_shorten_deadline(self):
        fixture=self.school_scope_fixture(before_dates=False);self.evaluate()
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        before=self.goal()
        for field,text,error in (('action','按老师要求录制两遍朗读。','录音数量'),
                ('why_now','请在'+fixture['first']+'前完成朗读。','完成日期'),
                ('action','录制三次朗读后提交。','录音数量')):
            wrong=synthetic_plan(self.last_input);wrong['proposal'][field]=text
            with self.assertRaisesRegex(agent.AgentError,error):self.store._proposal(wrong,ctx,self.now)
            self.assertEqual(self.goal(),before)
        proper=synthetic_plan(self.last_input)
        proper['proposal']['action']='按原要求读两遍，第二遍同时录音；学习观察建议：记录两次朗读的表现。'
        self.assertEqual(self.store._proposal(proper,ctx,self.now)['action'],proper['proposal']['action'])
        optional=synthetic_plan(self.last_input);optional['proposal']['action']='可选建议：另录两遍，仅在孩子愿意且家长同意时尝试，不属于学校必做。'
        self.assertEqual(self.store._proposal(optional,ctx,self.now)['action'],optional['proposal']['action'])

    def test_school_execution_count_and_before_date_need_the_same_effective_task(self):
        fixture=self.school_scope_fixture();self.evaluate()
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        task=ctx['school_tasks'][0]
        task['goal']='Unit 3录音2遍，'+fixture['first']+'前交回。'
        proper=synthetic_plan(self.last_input)
        proper['proposal']['action']='Unit 3录制二遍。';proper['proposal']['why_now']='原要求是'+fixture['first']+'前交回。'
        self.assertEqual(self.store._proposal(proper,ctx,self.now)['action'],proper['proposal']['action'])
        # The complete, uniquely scoped source clause still proves "before"
        # when the collected task body did not repeat the date phrase.
        task['goal']='Unit 3课文读两遍，朗读录音上传。'
        proper=synthetic_plan(self.last_input);proper['proposal']['why_now']='原要求是'+fixture['first']+'前完成朗读。'
        self.assertEqual(self.store._proposal(proper,ctx,self.now)['why_now'],proper['proposal']['why_now'])
        other=dict(task,id='synthetic-other-reading',title='英语：Unit 4',goal='Unit 4录音2遍。')
        task['goal']='Unit 3课文读两遍，朗读录音上传。';ctx['school_tasks'].append(other)
        borrowed=synthetic_plan(self.last_input);borrowed['proposal']['action']='Unit 3录制两遍。'
        with self.assertRaisesRegex(agent.AgentError,'录音数量'):self.store._proposal(borrowed,ctx,self.now)
        # Another task's earlier-deadline wording cannot justify shortening this one.
        task['goal']+='在'+fixture['first']+'当日完成。'
        other['goal']='Unit 4录音2遍，'+fixture['second']+'前完成。';other['due_on']=fixture['second']
        borrowed=synthetic_plan(self.last_input);borrowed['proposal']['why_now']='需在'+fixture['first']+'前完成Unit 3。'
        with self.assertRaisesRegex(agent.AgentError,'完成日期'):self.store._proposal(borrowed,ctx,self.now)

    def test_school_execution_object_tokens_do_not_borrow_counts_or_date_edges(self):
        tasks=[dict(id='synthetic-u3',title='英语：Unit 3',goal='Unit 3课文读两遍，2026-10-06当日完成。',due_on='2026-10-06'),
               dict(id='synthetic-u30',title='英语：Unit 30',goal='Unit 30录音2遍，2026-10-07前完成。',due_on='2026-10-07')]
        for text in ('Unit3录制两遍。','Unit3须10月7日前完成。','Unit3须10月8日前完成。'):
            with self.assertRaises(agent.AgentError):goals._school_execution_facts(dict(action=text,why_now='沿原要求。'),tasks)
        good=dict(action='Unit30录制二遍。',why_now='Unit30在10月7日前完成。')
        goals._school_execution_facts(good,tasks)
        tasks[1].update(goal='Unit 30录音2遍，2026-10-06前完成。',due_on='2026-10-06')
        goals._school_execution_facts(dict(action='Unit30录制二遍。',why_now='Unit30在10月6日前完成。'),tasks)
        with self.assertRaises(agent.AgentError):
            goals._school_execution_facts(dict(action='沿原要求。',why_now='在10月6日前完成。'),tasks)

    def test_effective_school_requirement_changes_expire_old_plan_and_reject_late_receipt(self):
        fixture=self.school_scope_fixture();self.approve(self.evaluate());approved=self.goal()['current_plan']
        self.feedback('虚构家长反馈：本次还未尝试，学校要求保持。')
        pending=self.evaluate();old_hash=pending['context_hash'];old_messages=pending['school_messages']
        def edit(goal,due=None):
            task=next(t for t in self.app.tasks() if t['id']==fixture['reading']);self.count+=1
            return agent.family_task_focus.save(self.app,dict(id=task['id'],version=task['focus']['version'],
                request_key='synthetic-effective-requirement-'+str(self.count),mode='next',next_action='',waiting_for='',review_on='',
                title=task['title'],goal=goal,category=task['agenda']['category'],published_on=task['agenda']['published_on'],
                due_on=due or task['agenda']['due_on']))
        # This is an effective parent correction, not an edit of the immutable school notice.
        edit('家长核对后的有效要求：Unit 3只读一遍，录音上传班级作业区。',fixture['second'])
        changed=self.goal();self.assertNotEqual(changed['context_hash'],old_hash);self.assertTrue(changed['pending_stale'])
        self.assertIsNone(changed['pending']);self.assertEqual(changed['current_plan'],approved);self.assertEqual(changed['school_messages'],old_messages)
        with self.assertRaises(agent.AgentError):self.approve(pending)
        self.evaluate();self.assertEqual(self.last_input['school_tasks'][0]['due_on'],fixture['second'])
        self.assertIn('只读一遍',self.last_input['school_tasks'][0]['goal'])
        before=self.goal()['pending'];count=self.model.call_count
        # A feedback save intentionally supersedes pending suggestions. Change the
        # effective requirement instead, so this round tests the late-return guard
        # while the previous pending row is still present.
        edit('家长本轮核对：Unit 3只读第一段，录音上传班级作业区。')
        def late(messages,*args,**kwargs):
            value=json.loads(messages[-1]['content']);edit('家长再次核对：Unit 3只读第一句，录音上传班级作业区。')
            return synthetic_plan(value)
        self.model.side_effect=late
        result=self.store.process(self.ident,self.now,explicit=True)
        self.assertEqual(result['state'],'stale');self.assertEqual(result['created'],0);self.assertEqual(self.model.call_count,count+1)
        after=self.goal();self.assertIsNone(after['pending']);self.assertTrue(after['pending_stale']);self.assertEqual(after['current_plan'],approved)
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?',(before['id'],)).fetchone()['state'],'pending')

    def test_school_plan_scope_does_not_borrow_other_goals_or_children(self):
        fixture=self.school_scope_fixture()
        other_goal=self.action('create',child_id='child-1',title='虚构另一英语目标',subject='英语')['id']
        other=fixture['save']('英语：另一目标练习','虚构另一目标要求：练习卷第4题选做。',fixture['second'],['M4'])
        with self.app.connect() as c:
            row=c.execute('SELECT id,plan FROM agent_items WHERE task_id=?',(other,)).fetchone();plan=json.loads(row['plan']);plan['school_goal_id']=other_goal
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),row['id']))
        # A dangling task ownership/link is not permission to use another child's current requirements.
        foreign=fixture['save']('英语：虚构异孩任务','另一孩子的虚构要求。',fixture['second'],['M5'])
        with self.app.connect() as c:c.execute("UPDATE manual_tasks SET child='示例乙' WHERE id=?",(foreign,))
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        self.assertEqual([t['id'] for t in ctx['school_tasks']],[fixture['reading']])
        self.assertNotIn('另一孩子的虚构要求',json.dumps(ctx['evidence'],ensure_ascii=False))
        self.assertNotIn('school:task:'+other,{e['ref'] for e in ctx['evidence']})
        with self.app.connect() as c:
            row=c.execute('SELECT id,plan FROM agent_items WHERE task_id=?',(foreign,)).fetchone()
            c.execute("UPDATE agent_items SET child_id='child-2' WHERE id=?",(row['id'],))
        self.evaluate();self.assertEqual([t['id'] for t in self.last_input['school_tasks']],[fixture['reading']])
        source=fixture['source'];source['child_id']='child-2'
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident),self.now)
        self.assertEqual(ctx['school_messages'],[]);self.assertTrue(ctx['school_missing'])
        self.assertEqual(ctx['school_tasks'],[])

    def test_school_plan_scope_budget_marks_omissions_and_hashes_unselected_requirements(self):
        fixture=self.school_scope_fixture()
        def reviewed(messages,*args,**kwargs):
            value=json.loads(messages[-1]['content']);self.last_input=value;result=synthetic_plan(value)
            effective=next(e for e in value['evidence'] if e['ref']=='school:task:'+fixture['reading'])
            result['proposal']['evidence']=[dict(ref=effective['ref'],quote=effective['text'][:30])]
            return result
        self.model.side_effect=reviewed;self.approve(self.evaluate())
        all_ids={fixture['reading']}
        for n in range(6):
            self.now+=dt.timedelta(seconds=1)
            all_ids.add(fixture['save']('英语：虚构独立练习'+str(n),'虚构练习'+str(n)+'：只做当前练习，条件保持完整。'+ '保留该练习的要求。'*50,
                fixture['second'],['M1']))
        self.model.side_effect=self.reply;self.evaluate()
        selected={t['id'] for t in self.last_input['school_tasks']}
        self.assertEqual(len(selected),6);self.assertEqual(self.last_input['omitted_school_tasks'],1)
        self.assertIn(fixture['reading'],selected)  # Previously approved task evidence is retrieved within the budget.
        effective=[e for e in self.last_input['evidence'] if e.get('source_kind')=='effective_school_task']
        self.assertEqual({e['task_id'] for e in effective},selected)
        current={t['id']:t for t in self.app.tasks()}
        self.assertTrue(all(t['goal']==current[t['id']]['action'] for t in self.last_input['school_tasks']))
        self.assertEqual(self.goal()['school_tasks_omitted'],1)
        self.assertEqual({t['id'] for t in self.goal()['school_tasks']},selected)
        self.assertIn('omitted_school_tasks大于零',goals.PROMPT);self.assertIn('不能声称全部学校要求已核完',goals.PROMPT)
        omitted,=all_ids-selected;old_hash=self.goal()['context_hash'];task=current[omitted]
        agent.family_task_focus.save(self.app,dict(id=omitted,version=task['focus']['version'],request_key='synthetic-omitted-requirement',
            mode='next',next_action='',waiting_for='',review_on='',goal=task['action']+'\n家长核对补充：本题无需抄参考。'))
        changed=self.goal();self.assertNotEqual(changed['context_hash'],old_hash);self.assertTrue(changed['pending_stale'])

    def test_independent_message_to_goal_plan_feedback_and_teacher_correction(self):
        source=dict(id='synthetic-school',platform='wechat',child_id='child-1',name='虚构班级',cursor='100',enabled=True)
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        original='英语口头介绍：\u00a0观察家里一件文具，说出两点用途。开头任选提问或直接介绍，用自己的真实观察。'
        def ingest(ident,text):
            self.store.agent.ingest(dict(source_id=source['id'],expected_cursor=str(ident-1),cursor=str(ident),
                checked_at=self.now.isoformat(),last_message_time=self.now.isoformat(),error='',
                messages=[dict(id=str(ident),time=self.now.isoformat(),kind='text',sender='虚构发布者',text=text,unread=False)]))
        requests=[]
        def model(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content']);requests.append((name,value))
            if name=='family_agent_selection':
                self.assertEqual([g['id'] for g in value['learning_goals']],[self.ident])
                e=value['evidence'][0]
                proposal=synthetic_school_proposal(e,'英语','英语：口头介绍一种文具',
                    '观察家里一件文具，说出两点用途；开头任选提问或直接介绍，用自己的真实观察。',goal_id=self.ident)
                if e['text'].startswith('更正'):
                    target=next(t for t in value['school_tasks'] if t['title']=='英语：口头介绍一种文具')
                    proposal.update(task_goal='本次只说一点用途，开头仍可任选。',task_state='review',
                        task_reason='更正须核对原学校事项后确认。',task_change='update',task_target_id=target['id'])
                return dict(proposals=[proposal])
            result=synthetic_plan(value)
            for e in result['proposal']['evidence']: e['quote']=e['quote'].replace('\u00a0',' ')
            return result
        self.model.side_effect=model;ingest(101,original)
        agent.run_once(self.app,self.now)
        g=self.goal();self.assertIsNotNone(g['pending']);self.assertEqual(g['school_target'],'')
        self.assertEqual(g['school_messages'][0]['text'],original);self.assertEqual(g['school_messages'][0]['source'],'虚构班级')
        self.assertEqual([n for n,v in requests],['family_agent_selection','family_learning_plan'])
        self.assertTrue(any(e.get('source_kind')=='group_message' for e in requests[-1][1]['evidence']))
        self.assertIn('\u00a0',g['pending']['evidence'][0]['quote'])
        invalid=synthetic_plan(requests[-1][1]);invalid['proposal']['hypotheses'][0]['support']=[g['school_messages'][0]['ref']]
        with self.store.agent._db() as c:ctx=self.store._context(c,self.store._get(c,self.ident))
        with self.assertRaisesRegex(agent.AgentError,'学校要求不是'):self.store._proposal(invalid,ctx,self.now)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks WHERE source=?',('学习目标:'+self.ident,)).fetchone()[0],0)
            school_tasks=[dict(t) for t in c.execute('SELECT * FROM manual_tasks')]
            self.assertEqual(len(school_tasks),1)
            school_task=school_tasks[0]
            self.assertEqual((school_task['title'],school_task['action']),('英语：口头介绍一种文具',
                '观察家里一件文具，说出两点用途；开头任选提问或直接介绍，用自己的真实观察。'))
            self.assertIn('message:'+source['id']+':101',school_task['source'])
        self.assertEqual(g['task_id'],'')  # The original school task exists; the proposed extra plan still waits for approval.
        self.assertEqual(agent.run_once(self.app,self.now)['created'],0);self.assertEqual(len(requests),2)
        self.approve(g);task=self.goal()['task_id'];old_plan=self.goal()['current_plan']
        self.feedback('孩子原话：它可以写字；第二点用途需要家长提示。')
        self.now+=dt.timedelta(minutes=1);agent.run_once(self.app,self.now)
        self.assertIn('第二点用途需要家长提示',agent._json(requests[-1][1]['evidence']))
        self.assertEqual(self.goal()['current_plan'],old_plan)
        feedback_pending=self.goal()['pending'];self.assertIsNotNone(feedback_pending)
        plan_calls=sum(name=='family_learning_plan' for name,_ in requests)
        self.now+=dt.timedelta(minutes=1);correction='更正英语口头介绍：本次只说一点用途，开头仍可任选。'
        ingest(102,correction);agent.run_once(self.app,self.now)
        g=self.goal();self.assertEqual([m['text'] for m in g['school_messages']],[original])
        self.assertEqual(g['task_id'],task);self.assertEqual(g['current_plan'],old_plan);self.assertEqual(g['pending'],feedback_pending)
        self.assertEqual(sum(name=='family_learning_plan' for name,_ in requests),plan_calls)
        with self.app.connect() as c:
            changes=[dict(row) for row in c.execute("SELECT * FROM agent_items WHERE kind='school'")
                if any(e['ref']=='message:'+source['id']+':102' for e in json.loads(row['evidence']))]
            change,=changes;brief=json.loads(change['plan'])['school_task']
            self.assertEqual((change['state'],brief['state'],brief['change'],brief['target_id']),('pending','review','update',school_task['id']))
            self.assertEqual(change['body'],'本次只说一点用途，开头仍可任选。')
            self.assertIn(correction,json.loads(change['evidence'])[0]['text'])
            self.assertNotIn('school_learning',json.loads(change['plan']))
            self.assertEqual(dict(c.execute('SELECT * FROM manual_tasks WHERE id=?',(school_task['id'],)).fetchone()),school_task)
        self.store.agent.act(dict(action='dismiss',id=change['id']))
        g=self.goal();self.assertFalse(g['pending_stale']);self.assertEqual(g['pending'],feedback_pending)
        self.assertEqual([m['text'] for m in g['school_messages']],[original]);self.assertEqual(g['current_plan'],old_plan)
        source['child_id']='child-2';(self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        self.assertEqual(self.goal()['school_messages'],[]);self.assertEqual(self.goal()['school_missing'],1)

    def test_school_routing_creates_one_goal_and_respects_pause(self):
        source=dict(id='synthetic-school-two',platform='wechat',child_id='child-2',name='另一虚构班级',cursor='0',enabled=True)
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        def model(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content'])
            if name=='family_agent_selection':
                self.assertFalse(any(g['id']==self.ident for g in value['learning_goals']))
                return dict(proposals=[synthetic_school_proposal(e,'语文',
                    '语文：介绍一种文具' if '介绍一种文具' in e['text'] else '语文：按使用顺序说',
                    '介绍一种文具。' if '介绍一种文具' in e['text'] else '补充要求：按使用顺序说。') for e in value['evidence']])
            return synthetic_plan(value)
        self.model.side_effect=model
        self.store.agent.ingest(dict(source_id=source['id'],expected_cursor='0',cursor='2',checked_at=self.now.isoformat(),last_message_time=self.now.isoformat(),error='',
            messages=[dict(id=str(i),time=self.now.isoformat(),kind='text',sender='虚构老师',text=t,unread=False)
                for i,t in [(1,'语文观察练习：介绍一种文具。'),(2,'语文补充：按使用顺序说。')]]))
        agent.run_once(self.app,self.now);other=[g for g in self.store.snapshot()['goals'] if g['child_id']=='child-2']
        self.assertEqual(len(other),1);g=other[0];self.assertEqual(len(g['school_messages']),2)
        self.assertFalse(self.goal()['school_messages']);self.assertIsNotNone(g['pending'])
        self.action('pause',id=g['id'],expected_version=g['version'])
        self.now+=dt.timedelta(minutes=2);before=self.model.call_count
        agent.run_once(self.app,self.now);self.assertEqual(self.model.call_count,before)
        g=next(g for g in self.store.snapshot()['goals'] if g['child_id']=='child-2')
        self.action('resume',id=g['id'],expected_version=g['version'])
        accepted_refs=[m['ref'] for m in g['school_messages']]
        # Clear original requirements are now auto-collected; dismissing a pending
        # suggestion must not delete their accepted tasks or learning evidence.
        with self.app.connect() as c:
            accepted_tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
        for message in g['school_messages']:
            with self.assertRaises(agent.AgentError) as rejected:
                self.store.agent.act(dict(action='dismiss',id=message['item_id']))
            self.assertEqual(rejected.exception.status,409)
        agent.run_once(self.app,self.now);self.assertEqual(self.model.call_count,before+1)
        self.assertEqual(self.model.call_args.args[2],'family_learning_plan')
        g=next(g for g in self.store.snapshot()['goals'] if g['child_id']=='child-2')
        self.assertEqual([m['ref'] for m in g['school_messages']],accepted_refs);self.assertEqual(g['processing'],'ready')
        self.assertIsNotNone(g['pending'])  # Resuming produces a fresh proposal, not an already-approved plan.
        with self.app.connect() as c:
            self.assertEqual([dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')],accepted_tasks)
        agent.run_once(self.app,self.now);self.assertEqual(self.model.call_count,before+1)

    def test_school_selector_rejects_foreign_goal_and_unread_requirements(self):
        evidence=[dict(ref='message:synthetic:1',text='[图片]',content_incomplete=True)]
        result=dict(proposals=[synthetic_school_proposal(evidence[0],'英语','','',goal_id='foreign-goal',
            state='review',reason='图片内容尚未读取，具体学校要求待补充。',purpose='unknown')])
        self.model.side_effect=lambda *a,**k:result
        with self.assertRaisesRegex(agent.AgentError,'归属'):
            agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        result['proposals'][0]['learning_goal_id']=''
        selected=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(len(selected),1);self.assertNotIn('school_learning',selected[0]['plan']);self.assertEqual(selected[0]['plan']['school_task']['state'],'review');self.assertEqual(selected[0]['plan']['school_task']['title'],'')
        self.assertIn('未读全',selected[0]['plan']['school_task']['reason'])
        evidence.append(dict(ref='message:synthetic:2',text='英语口述：介绍一种文具。',content_incomplete=False))
        result['proposals'].append(synthetic_school_proposal(evidence[1],'英语','英语：口述介绍一种文具','口述介绍一种文具。'))
        selected=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(len(selected),2);self.assertIn('plan',selected[1])
        self.assertEqual(selected[1]['evidence'][0]['text'],evidence[1]['text'])
        result['proposals'][1]['evidence'][0]['ref']='message:foreign:1'
        with self.assertRaisesRegex(agent.AgentError,'引用'):
            agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())

    def test_bad_source_does_not_block_routing_and_no_match_is_not_forced(self):
        source=dict(id='synthetic-routing',platform='wechat',child_id='child-1',name='虚构班级',cursor='0',enabled=True)
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[source])))
        self.store.agent.ingest(dict(source_id=source['id'],expected_cursor='0',cursor='1',checked_at=self.now.isoformat(),last_message_time=self.now.isoformat(),error='',
            messages=[dict(id='1',time=self.now.isoformat(),kind='text',sender='虚构发布者',text='英语口述：介绍文具。',unread=False)]))
        item=dict(child_id='child-1',kind='school',title='英语口述',body='待核对',due='',evidence=[],
                  plan=dict(school_learning=dict(subject='英语',goal_id=''),school_messages=[dict(source_id=source['id'],message_id='1')]))
        bad={**item,'plan':{**item['plan'],'school_messages':[dict(source_id='removed-source',message_id='1')]}}
        fp=self.store.agent._job('synthetic-routing-receipt',{},self.now)
        self.store.agent._save('synthetic-routing-receipt',fp,[bad,item],self.now,[(source['id'],'1')])
        self.assertEqual(self.store.route_school(),1)
        self.assertEqual(self.goal()['school_messages'],[])
        generated=next(g for g in self.store.snapshot()['goals'] if g['id']!=self.ident)
        self.assertEqual(generated['subject'],'英语');self.assertEqual(len(generated['school_messages']),1)
        self.assertEqual(self.store.route_school(),0)



class MediaFeedbackEvidenceTests(unittest.TestCase):
    """#23: task feedback media reaches the linked goal as one record; only a parent-checked transcript adds words."""
    action=GoalTests.action;goal=GoalTests.goal;reply=GoalTests.reply;evaluate=GoalTests.evaluate;approve=GoalTests.approve;on=GoalTests.on
    TASK='M-synthetic-1'

    def setUp(self):
        GoalTests.setUp(self)
        with self.app.connect() as c:
            for ident,child in ((self.TASK,'示例甲'),('M-synthetic-2','示例甲'),('M-synthetic-3','示例乙')):
                c.execute('INSERT INTO manual_tasks(id,child,title,due,original_status,source,action) VALUES(?,?,?,?,?,?,?)',(ident,child,'虚构听写','','待跟进','虚构来源','虚构要求'))
            c.execute('UPDATE agent_items SET task_id=? WHERE id=?',(self.TASK,self.ident))

    def media(self,**obj):
        self.count+=1;content=('synthetic original %d'%self.count).encode()
        upload=self.app.save_upload(io.BytesIO(content),len(content),'synthetic-voice-%d.txt'%self.count)['id']
        body=dict(task_id=self.TASK,child='示例甲',day=self.now.date().isoformat(),subject='英语',request_key='synthetic-media-'+str(self.count).zfill(8),attachments=[upload])
        body.update(obj);self.last_body=body
        return self.app.save_task_feedback(dict(body))

    def ctx(self):
        with self.store.agent._db() as c:return self.store._context(c,self.store._get(c,self.ident))

    def test_checked_audio_only_feedback_is_one_parent_checked_item_and_a_correction_changes_freshness(self):
        empty=self.ctx();saved=self.media(transcript='虚构转写：听写时把 yesterday 写成 yestoday。',transcript_state='已核对');ref='record:%d'%saved['record_id']
        ctx=self.ctx();record=next(r for r in ctx['records'] if r['id']==saved['record_id'])
        self.assertEqual((record['note'],record['transcript_state'],record['source'],record['day']),('','已核对','事项:'+self.TASK,self.last_body['day']))
        self.assertIn('yestoday',record['transcript']);self.assertNotIn('media_unread',record)
        items=[e for e in ctx['evidence'] if e['ref']==ref];self.assertEqual(len(items),1);self.assertNotIn('media_unread',items[0])
        self.assertIn('yestoday',items[0]['text']);self.assertNotEqual(empty['evidence_hash'],ctx['evidence_hash'])
        self.assertFalse([e for e in ctx['evidence'] if e['ref'].startswith('task-feedback:')])
        self.app.save_task_feedback(dict(task_id=self.TASK,child='示例甲',record_id=saved['record_id'],expected_created=saved['feedback']['created'],transcript='虚构转写：更正后是 yesterdy。'))
        fixed=self.ctx();self.assertNotEqual(ctx['evidence_hash'],fixed['evidence_hash'])
        self.assertIn('yesterdy',agent._json(fixed['evidence']));self.assertNotIn('yestoday',agent._json(fixed['evidence']))

    def test_unchecked_transcript_and_bare_media_stay_unknown_with_their_words_withheld(self):
        checked=self.media(transcript='虚构已核对转写',transcript_state='已核对');pending=self.media(transcript='虚构未核对内容',transcript_state='待核对');bare=self.media()
        ctx=self.ctx();by={r['id']:r for r in ctx['records']}
        for saved in (pending,bare):
            self.assertTrue(by[saved['record_id']]['media_unread']);self.assertNotIn('transcript',by[saved['record_id']])
            self.assertTrue(next(e for e in ctx['evidence'] if e['ref']=='record:%d'%saved['record_id'])['media_unread'])
        self.assertEqual(by[pending['record_id']]['transcript_state'],'待核对');self.assertNotIn('虚构未核对内容',agent._json(ctx['evidence']))

    def test_unread_media_is_rejected_for_both_cause_directions_and_checked_text_reaches_a_proposal(self):
        # Fresh goals isolate the guard from the normal retry backoff after a rejected model reply.
        for kind, fields, allowed in (
            ('pending', dict(transcript='SECRET_UNCHECKED_WORDS',transcript_state='待核对'), False),
            ('bare', {}, False),
            ('checked', dict(transcript='虚构核对：听写漏写了一个词',transcript_state='已核对'), True),
            ('parent-note', dict(note='家长观察：第一次漏写一个词',transcript='SECRET_UNCHECKED_WORDS',transcript_state='待核对'), True),
        ):
            saved=self.media(**fields);ref='record:%d'%saved['record_id']
            for side in ('support','against'):
                with self.subTest(kind=kind,side=side):
                    self.ident=self.action('create',child_id='child-1',title='虚构独立核对 '+kind+side,subject='英语',record_ids=[saved['record_id']])['id']
                    ctx=self.ctx()
                    def reply(messages,schema,name,timeout,**kwargs):
                        value=json.loads(messages[-1]['content']);self.assertNotIn('SECRET_UNCHECKED_WORDS',agent._json(value))
                        result=synthetic_plan(value)
                        result['proposal']['hypotheses']=[dict(reason='虚构原因',support=[ref] if side=='support' else [],against=[ref] if side=='against' else [],test='请核对本次帮助条件',status='有支持' if side=='support' else '有反证')]
                        return result
                    self.model.side_effect=reply
                    model_result=reply([{'content':agent._json(dict(evidence=ctx['evidence'],as_of=self.now.date().isoformat()))}],None,None,None)
                    if not allowed:
                        with self.assertRaisesRegex(agent.AgentError,'未核对的原件或转写'):
                            self.store._proposal(model_result,ctx,self.now)
                    else:self.store._proposal(model_result,ctx,self.now)
                    calls=self.model.call_count;result=self.store.process(self.ident,self.now,explicit=True)
                    self.assertEqual(self.model.call_count,calls+1)
                    self.assertEqual(result['state'],'ready' if allowed else 'error')
                    goal=self.goal();self.assertIsNone(goal['current_plan'])
                    if allowed:self.assertEqual(goal['pending']['hypotheses'][0][side],[ref])
                    else:self.assertIsNone(goal['pending'])

    def test_note_with_transcript_is_one_ref_and_a_retry_adds_nothing(self):
        saved=self.media(note='虚构家长说明：第二遍才听出来。',transcript='虚构转写内容',transcript_state='已核对');again=self.app.save_task_feedback(dict(self.last_body))
        self.assertTrue(again['replayed']);self.assertEqual(again['record_id'],saved['record_id'])
        ctx=self.ctx();refs=[e['ref'] for e in ctx['evidence'] if e['ref'].startswith(('record:','task-feedback:'))]
        self.assertEqual(refs,['record:%d'%saved['record_id']]);record=ctx['records'][0]
        self.assertEqual((record['note'],record['transcript']),('虚构家长说明：第二遍才听出来。','虚构转写内容'))
        self.assertEqual(agent._json(ctx['evidence']).count('虚构转写内容'),1)

    def test_other_task_and_other_child_feedback_is_not_this_goals_evidence(self):
        mine=self.media(transcript='虚构本事项转写',transcript_state='已核对')
        self.media(task_id='M-synthetic-2',transcript='虚构同孩其他事项',transcript_state='已核对');self.media(task_id='M-synthetic-3',child='示例乙',transcript='虚构另一孩子',transcript_state='已核对')
        ctx=self.ctx();self.assertEqual([r['id'] for r in ctx['records']],[mine['record_id']])
        text=agent._json(ctx['evidence']);self.assertNotIn('虚构同孩其他事项',text);self.assertNotIn('虚构另一孩子',text)

    def test_text_only_records_keep_their_previous_shape(self):
        rid=GoalTests.feedback(self)['record_id'];ctx=self.ctx();record=next(r for r in ctx['records'] if r['id']==rid)
        with self.app.connect() as c:row=dict(c.execute('SELECT * FROM records WHERE id=?',(rid,)).fetchone())
        self.assertEqual(record,{k:row[k] for k in goals.RECORD_FIELDS})
        self.assertEqual(next(e for e in ctx['evidence'] if e['ref']=='record:%d'%rid),dict(ref='record:%d'%rid,text=agent._json(record)))

    def test_downgrading_a_checked_transcript_makes_the_confirmed_judgment_stale_without_changing_the_plan(self):
        saved=self.media(day=(self.now-dt.timedelta(days=5)).date().isoformat(),transcript='虚构转写：把 yesterday 听成 today。',transcript_state='已核对');ref='record:%d'%saved['record_id']
        with self.on(3):self.approve(self.evaluate())
        goal=self.goal();self.assertFalse(goal['evidence_changed']);plan=goal['current_plan']
        self.app.save_task_feedback(dict(task_id=self.TASK,child='示例甲',record_id=saved['record_id'],expected_created=saved['feedback']['created'],transcript_state='待核对'))
        goal=self.goal();self.assertTrue(goal['evidence_changed']);self.assertEqual(goal['current_plan'],plan)
        self.assertNotIn('yesterday',agent._json(self.ctx()['evidence']))
        with self.app.connect() as c:
            self.assertEqual(goals.family_learner_memory.corrected_refs(c,[ref],goal['current_plan_confirmed_at'],self.store._owned(c,'child-1')),[ref])

    def test_diagnosis_reads_the_checked_transcript_and_gives_unread_media_no_status(self):
        import family_diagnosis
        checked=self.media(transcript='虚构已核对转写',transcript_state='已核对');pending=self.media(transcript='虚构未核对内容',transcript_state='待核对')
        ev={e['ref']:e for e in family_diagnosis.evidence(self.app,'child-1','英语')};good,unread='record:%d'%checked['record_id'],'record:%d'%pending['record_id']
        self.assertEqual(ev[good]['text'],family_diagnosis.CHECKED_TRANSCRIPT+'虚构已核对转写');self.assertNotIn('media_unread',ev[good])
        self.assertTrue(ev[unread]['media_unread']);self.assertNotIn('虚构未核对内容',json.dumps(list(ev.values()),ensure_ascii=False))
        def status(ref):
            result=dict(knowledge_components=[dict(name='虚构知识点',error_type='',misconception='',status='有支持',evidence=[ref],suggestion='')],summary='',uncertainties=[])
            return family_diagnosis._validate(result,list(ev.values()))['knowledge_components'][0]['status']
        self.assertEqual((status(good),status(unread)),('有支持','待验证'))


if __name__=='__main__':unittest.main()

"""Synthetic goal lifecycle checks; no household data or external services."""
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
    e=value['evidence'][-1]
    return {'proposal':dict(title='先核对一个判断过程',goal='能解释判断所用的线索',action='家长请孩子选一道已有题，说说看到的时间线索；不愿继续就停止。',why_now='根据已保存的家长反馈先核对。',estimated_minutes=10,review_on=value['as_of'],evidence=[dict(ref=e['ref'],quote=e['text'][:30])],assessment='现有反馈不足以确定知识缺口。',hypotheses=[dict(reason='句子中时间线索理解可能不牢',support=[],against=[],test='使用现有一道题，请孩子说出选项理由；不提示答案。',status='待验证')],resource='已有课本；具体页码待家长核对。',mastery_check='相近新题中独立解释，记录帮助。',choice='核实')}


class GoalTests(unittest.TestCase):
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
        payload=dict(action='feedback',id=self.ident,request_key='synthetic-feedback-stable',day=self.now.date().isoformat(),source='家长观察',note='独立解释仍需要核对。')
        first=self.store.action(payload);g=self.goal()
        self.action('edit',id=self.ident,expected_version=g['version'],title='修改后的阶段名称',subject='综合')
        self.assertEqual(self.store.action(payload)['record_id'],first['record_id'])
        second=self.app.save_record(dict(child='示例乙',day=self.now.date().isoformat(),category='家长观察',title='另一位孩子的记录',note='不能串用',source='家长观察'))
        with self.assertRaises(agent.AgentError):self.action('link',id=self.ident,expected_version=self.goal()['version'],record_ids=[second['record_id']])
        self.assertEqual(len(self.goal()['records']),1)

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
                return dict(proposals=[dict(title_quote=e['text'][:30],focus='school',due='',learning_subject='英语',
                    learning_goal_id=self.ident,evidence=[dict(ref=e['ref'])])])
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
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)
        self.assertEqual(agent.run_once(self.app,self.now)['created'],0);self.assertEqual(len(requests),2)
        self.approve(g);task=self.goal()['task_id'];old_plan=self.goal()['current_plan']
        self.feedback('孩子原话：它可以写字；第二点用途需要家长提示。')
        self.now+=dt.timedelta(minutes=1);agent.run_once(self.app,self.now)
        self.assertIn('第二点用途需要家长提示',agent._json(requests[-1][1]['evidence']))
        self.assertEqual(self.goal()['current_plan'],old_plan)
        self.now+=dt.timedelta(minutes=1);correction='更正英语口头介绍：本次只说一点用途，开头仍可任选。'
        ingest(102,correction);agent.run_once(self.app,self.now)
        g=self.goal();self.assertEqual([m['text'] for m in g['school_messages']],[original,correction])
        self.assertEqual(g['task_id'],task);self.assertEqual(g['current_plan'],old_plan);self.assertIsNotNone(g['pending'])
        self.store.agent.act(dict(action='dismiss',id=g['school_messages'][-1]['item_id']))
        g=self.goal();self.assertTrue(g['pending_stale']);self.assertIsNone(g['pending'])
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
                return dict(proposals=[dict(title_quote=e['text'],focus='school',due='',learning_subject='语文',learning_goal_id='',
                    evidence=[dict(ref=e['ref'])]) for e in value['evidence']])
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
        for message in g['school_messages']:self.store.agent.act(dict(action='dismiss',id=message['item_id']))
        agent.run_once(self.app,self.now);self.assertEqual(self.model.call_count,before)
        g=next(g for g in self.store.snapshot()['goals'] if g['child_id']=='child-2')
        self.assertEqual(g['school_messages'],[]);self.assertEqual(g['processing'],'current')

    def test_school_selector_rejects_foreign_goal_and_unread_requirements(self):
        evidence=[dict(ref='message:synthetic:1',text='[图片]',content_incomplete=True)]
        result=dict(proposals=[dict(title_quote='[图片]',focus='school',due='',learning_subject='英语',learning_goal_id='foreign-goal',
                                   evidence=[dict(ref=evidence[0]['ref'])])])
        self.model.side_effect=lambda *a,**k:result
        with self.assertRaisesRegex(agent.AgentError,'归属'):
            agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        result['proposals'][0]['learning_goal_id']=''
        selected=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(len(selected),1);self.assertNotIn('school_learning',selected[0]['plan']);self.assertEqual(selected[0]['plan']['school_task']['state'],'review');self.assertEqual(selected[0]['plan']['school_task']['title'],'')
        evidence.append(dict(ref='message:synthetic:2',text='英语口述：介绍一种文具。',content_incomplete=False))
        result['proposals'].append(dict(title_quote=evidence[1]['text'],focus='school',due='',learning_subject='英语',learning_goal_id='',
                                       evidence=[dict(ref=evidence[1]['ref'])]))
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


if __name__=='__main__':unittest.main()

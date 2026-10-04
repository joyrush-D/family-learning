"""Isolated synthetic checks for the standalone Agent; no external model or collectors."""
from contextlib import contextmanager, redirect_stdout
import datetime as dt
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import family_agent as agent
import family_review


def school_proposal(**values):
    """Complete current school-model fixture; malformed-response tests use raw dictionaries."""
    result = dict(title_quote='待核对原文', focus='school', due='', evidence=[],
        learning_subject='', learning_goal_id='', task_title='', task_goal='', task_advice='',
        task_state='review', task_reason='虚构资料的具体要求尚待补充。', task_change='new',
        task_target_id='', task_purpose='unknown', task_submission='')
    result.update(values)
    return result


class AgentTests(unittest.TestCase):
    def _school_selection_authorization_change(self, change):
        from family_settings import Store as Settings
        self.source['id']='54321@chatroom';self.config()
        payload=self.payload();payload['messages'][0]['text']='明天交回活动回执。'
        self.store.ingest(payload)
        proposal=school_proposal(title_quote='活动回执',due='2026-02-11',
            evidence=[dict(ref='message:'+self.source['id']+':11')],
            task_title='交回活动回执',task_goal='明天交回活动回执。',
            task_state='ready',task_reason='要求明确。',task_purpose='admin')
        settings=Settings(self.app)
        def configure(enabled=True, source_enabled=True):
            state=settings.snapshot()
            rows=[{k:r[k] for k in ('id','platform','child_id','name','enabled')} for r in state['sources']]
            rows[0]['enabled']=source_enabled
            settings.save_sources(dict(revision=state['revision'],enabled=enabled,sources=rows))
        def model(*args,**kwargs):
            if change=='agent':configure(enabled=False)
            elif change=='source':configure(source_enabled=False)
            return dict(proposals=[proposal])
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            first=agent.run_once(self.app,self.now)
        self.assertEqual(called.call_count,1)
        if change:
            self.assertEqual(first['processed'],0,'revoked input must not be marked processed')
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0],'11')
            configure()
            with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])) as retry:
                recovered=agent.run_once(self.app,self.now+dt.timedelta(minutes=6))
                self.assertEqual(recovered['processed'],1)
                agent.run_once(self.app,self.now+dt.timedelta(minutes=7))
            self.assertEqual(retry.call_count,1)
        else:self.assertEqual(first['processed'],1)
        with self.app.connect() as c:
            task,=c.execute('SELECT child,title,due,action,original_status FROM manual_tasks').fetchall()
            self.assertEqual(tuple(task),('示例甲','交回活动回执','2026-02-11','明天交回活动回执。','待跟进'))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(json.loads(c.execute('SELECT payload FROM agent_messages').fetchone()[0])['text'],payload['messages'][0]['text'])

    def test_school_selection_drops_result_when_agent_stopped_during_model(self):
        self._school_selection_authorization_change('agent')

    def test_school_selection_drops_result_when_source_stopped_during_model(self):
        self._school_selection_authorization_change('source')

    def test_school_selection_current_source_still_auto_collects_once(self):
        self._school_selection_authorization_change('')

    def test_school_source_paused_after_claim_makes_no_model_call(self):
        from family_settings import Store as Settings
        self.source['id']='54321@chatroom';self.config();self.store.ingest(self.payload())
        original=agent.Store._job
        def claim(store,key,*args,**kwargs):
            value=original(store,key,*args,**kwargs)
            if key.startswith('messages:') and value:
                settings=Settings(self.app);state=settings.snapshot()
                sources=[{k:r[k] for k in ('id','platform','child_id','name','enabled')} for r in state['sources']]
                sources[0]['enabled']=False
                settings.save_sources(dict(revision=state['revision'],enabled=True,sources=sources))
            return value
        with patch.object(agent.Store,'_job',claim),patch.object(agent.family_llm,'_chat_json') as model:
            result=agent.run_once(self.app,self.now)
        self.assertEqual(model.call_count,0)
        self.assertEqual((result['processed'],result['created']),(0,0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            job,=c.execute("SELECT done,error,next_try,fingerprint FROM agent_jobs WHERE id LIKE 'messages:%'").fetchall()
            self.assertEqual((job['done'],job['error'],job['next_try']),(1,'',''))
            self.assertTrue(job['fingerprint'].startswith('discarded:'))

    def test_new_message_during_selection_does_not_revoke_the_original_batch(self):
        self.store.ingest(self.payload())
        proposal=school_proposal(title_quote='明天带阅读材料',due='2026-02-11',
            evidence=[dict(ref='message:'+self.source['id']+':11')],
            task_title='带阅读材料',task_goal='明天带阅读材料。',
            task_state='ready',task_reason='要求明确。',task_purpose='admin')
        def model(*args,**kwargs):
            incoming=self.payload(expected='11',cursor='12',message='12',offset=1)
            incoming['messages'][0]['text']='后天交回活动回执。';self.store.ingest(incoming)
            return dict(proposals=[proposal])
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            result=agent.run_once(self.app,self.now)
        self.assertEqual(called.call_count,1);self.assertEqual(result['processed'],1)
        with self.app.connect() as c:
            self.assertEqual(dict(c.execute('SELECT id,processed FROM agent_messages')),{ '11':1,'12':0})
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0],'12')
            task,=c.execute('SELECT child,title,due,action,original_status FROM manual_tasks').fetchall()
            self.assertEqual(tuple(task),('示例甲','带阅读材料','2026-02-11','明天带阅读材料。','待跟进'))

    def test_school_saved_message_change_during_selection_keeps_the_changed_message_unprocessed(self):
        self.store.ingest(self.payload())
        proposal=school_proposal(title_quote='明天带阅读材料',due='2026-02-11',
            evidence=[dict(ref='message:'+self.source['id']+':11')],
            task_title='带阅读材料',task_goal='明天带阅读材料。',
            task_state='ready',task_reason='要求明确。',task_purpose='admin')
        def model(*args,**kwargs):
            # Fault injection into the synthetic saved bytes, never a production repair route.
            with self.app.connect() as c:
                message=json.loads(c.execute('SELECT payload FROM agent_messages').fetchone()[0])
                message['text']='后天交回活动回执。'
                c.execute('UPDATE agent_messages SET payload=?',(agent._json(message),))
            return dict(proposals=[proposal])
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            result=agent.run_once(self.app,self.now)
        self.assertEqual(called.call_count,1);self.assertEqual(result['processed'],0)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            payload,processed=c.execute('SELECT payload,processed FROM agent_messages').fetchone()
            self.assertEqual((json.loads(payload)['text'],processed),('后天交回活动回执。',0))

    def _school_auto_accept_after_pause(self, disable_agent):
        self.store.ingest(self.payload())
        proposal=school_proposal(title_quote='明天带阅读材料',due='2026-02-11',
            evidence=[dict(ref='message:'+self.source['id']+':11')],
            task_title='带阅读材料',task_goal='明天带阅读材料。',
            task_state='ready',task_reason='要求明确。',task_purpose='admin')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            items=agent._select('school',[dict(ref='message:'+self.source['id']+':11',text=self.payload()['messages'][0]['text'],time=self.now.isoformat())],as_of=self.now.date().isoformat(),school_goals=[])
        items=[dict(i,kind='school',child_id='child-1') for i in items]
        self.store._save('synthetic-auto-source-race','fixture',items,self.now,[(self.source['id'],'11')])
        self.source['enabled']=disable_agent;self.config(enabled=not disable_agent)
        with patch.object(agent.family_llm,'_chat_json') as model:
            rejected=agent._refresh_school(self.app,self.store,self.now,0)
        self.assertEqual(model.call_count,0);self.assertEqual(rejected['created'],0)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT state FROM agent_items').fetchone()[0],'pending')
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],1)
        self.source['enabled']=True;self.config()
        with patch.object(agent.family_llm,'_chat_json') as model:
            recovered=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=2),0)
        self.assertEqual(model.call_count,0)
        self.assertEqual((recovered['created'],repeated['created']),(1,0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT original_status FROM manual_tasks').fetchone()[0],'待跟进')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)

    def test_saved_school_draft_does_not_auto_accept_after_agent_pause(self):
        self._school_auto_accept_after_pause(True)

    def test_saved_school_draft_does_not_auto_accept_after_source_pause(self):
        self._school_auto_accept_after_pause(False)

    def _pending_school_refresh_after_pause(self, phase, disable_agent):
        self.store.ingest(self.payload())
        reply=dict(title='带阅读材料',goal='明天带阅读材料。',advice='',state='ready',reason='要求明确。',
                   purpose='admin',submission='',change='new',target_id='',learning_subject='',learning_goal_id='')
        brief=dict(reply,policy=agent.SCHOOL_TASK_POLICY-1)
        item=dict(kind='school',child_id='child-1',title=reply['title'],body=reply['goal'],due='2026-02-11',
                  evidence=[dict(ref='message:'+self.source['id']+':11',text=self.payload()['messages'][0]['text'])],
                  plan=dict(school_task=brief))
        self.store._save('synthetic-pending-source-race','fixture',[item],self.now,[(self.source['id'],'11')])
        def pause():
            self.source['enabled']=disable_agent;self.config(enabled=not disable_agent)
        if phase=='before':pause()
        def model(*args,**kwargs):
            if phase=='during':pause()
            return reply
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            rejected=agent._refresh_school(self.app,self.store,self.now,1)
        self.assertEqual(called.call_count,0 if phase=='before' else 1)
        self.assertEqual(rejected['created'],0)
        with self.app.connect() as c:
            saved,=c.execute('SELECT state,plan FROM agent_items').fetchall()
            self.assertEqual((saved['state'],json.loads(saved['plan'])),('pending',item['plan']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],1)
        self.source['enabled']=True;self.config()
        with patch.object(agent.family_llm,'_chat_json',return_value=reply) as called:
            recovered=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=2),1)
        self.assertEqual(called.call_count,1)
        self.assertEqual((recovered['created'],repeated['created']),(1,0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0],'11')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)

    def test_pending_school_refresh_makes_no_call_after_agent_pause(self):
        self._pending_school_refresh_after_pause('before',True)

    def test_pending_school_refresh_makes_no_call_after_source_pause(self):
        self._pending_school_refresh_after_pause('before',False)

    def test_pending_school_refresh_keeps_old_draft_if_agent_paused_during_model(self):
        self._pending_school_refresh_after_pause('during',True)

    def test_pending_school_refresh_keeps_old_draft_if_source_paused_during_model(self):
        self._pending_school_refresh_after_pause('during',False)

    def test_separate_school_conclusions_do_not_borrow_related_attachments(self):
        sent='2026-10-05T16:00:00+08:00'
        refs=['message:synthetic-minutes:'+str(i) for i in range(1,6)]
        texts=['明天完成两项：Unit 2课文读两遍；练习卷第1–4题。朗读录音上传班级作业区。',
               '练习卷第4题选做，前3题必做。',
               '这是刚才练习卷的题目附件。',
               '这是刚才练习卷的家长参考答案附件。',
               '10月7日前请家长打印活动回执，签字后让孩子交回。不用盖章。']
        evidence=[dict(ref=ref,text=text,time=sent,kind='text',source='虚构班级群',
            sender='示例英语发布者' if i<4 else '示例班主任',
            publisher='publisher:synthetic-english' if i<4 else 'publisher:synthetic-admin',
            related_messages=refs[:4] if i<4 else refs[4:],content_incomplete=False,attachments=[])
            for i,(ref,text) in enumerate(zip(refs,texts))]
        evidence[2]['attachments']=[dict(name='synthetic-questions.pdf',mime='application/pdf')]
        evidence[3]['attachments']=[dict(name='synthetic-parent-reference.pdf',mime='application/pdf')]
        proposals=[]
        for title,goal,due,selected,purpose,submission in [
            ('英语：朗读Unit 2','课文读两遍，将朗读录音上传到班级作业区。','2026-10-06',refs[:1],'learning','朗读录音上传到班级作业区'),
            ('英语：完成练习卷','第1–3题必做，第4题选做。','2026-10-06',refs[:4],'learning',''),
            ('家长事务：活动回执','家长打印回执并签字，再让孩子交回；无需盖章。','2026-10-07',refs[4:],'admin',''),
        ]:
            proposals.append(dict(title_quote=texts[0] if purpose=='learning' else texts[4],focus='school',due=due,
                evidence=[dict(ref=ref) for ref in selected],learning_subject='英语' if purpose=='learning' else '',
                learning_goal_id='',task_title=title,task_goal=goal,task_advice='',task_state='ready',
                task_reason='原文要求明确。',task_change='new',task_target_id='',task_purpose=purpose,task_submission=submission))
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-05')
        self.assertEqual(len(items),3)
        # A publication can contain two tasks; its worksheet is not an attachment to the reading task.
        self.assertEqual([q['ref'] for q in items[0]['evidence']],refs[:1])
        self.assertEqual([q['ref'] for q in items[1]['evidence']],refs[:4])
        self.assertEqual([q['ref'] for q in items[2]['evidence']],refs[4:])
        self.assertEqual([x['due'] for x in items],['2026-10-06','2026-10-06','2026-10-07'])
        self.assertIn('两遍',items[0]['body'])
        self.assertIn('班级作业区',items[0]['body'])
        self.assertEqual(items[1]['body'],'第1–3题必做，第4题选做。')
        self.assertEqual(items[2]['body'],'家长打印回执并签字，再让孩子交回；无需盖章。')

    def test_school_routing_requires_organized_fields_before_success(self):
        evidence=[dict(ref='message:synthetic:1',text='英语：朗读Unit 2两遍。',time=self.now.isoformat(),content_incomplete=False)]
        legacy=dict(title_quote='英语',focus='school',due='',evidence=[dict(ref=evidence[0]['ref'])],
                    learning_subject='英语',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[legacy])):
            with self.assertRaises(agent.AgentError):
                agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        complete=school_proposal(title_quote='英语',evidence=[dict(ref=evidence[0]['ref'])],
            task_title='英语：朗读Unit 2',task_goal='课文读两遍。',task_state='ready',task_purpose='learning')
        for field in agent.SCHOOL_SCHEMA['properties']['proposals']['items']['required']:
            missing=dict(complete);missing.pop(field)
            with self.subTest(field=field),patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[missing])):
                with self.assertRaises(agent.AgentError):
                    agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())

    def test_school_routing_can_preserve_six_independent_requirements(self):
        evidence=[];proposals=[]
        for i,subject in enumerate(['语文','数学','英语','历史','科学','家长签字'],1):
            due=(self.now.date()+dt.timedelta(days=i)).isoformat()
            text=subject+'：请在'+due+'前完成虚构要求'+str(i)+'。'
            ref='message:synthetic:'+str(i)
            evidence.append(dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False))
            proposals.append(dict(title_quote=subject,focus='school',due=due,evidence=[dict(ref=ref)],
                learning_subject=subject if i<6 else '',learning_goal_id='',task_title=subject+'：虚构要求'+str(i),
                task_goal='完成虚构要求'+str(i),task_advice='',task_state='ready',task_reason='原文要求明确。',
                task_change='new',task_target_id='',task_purpose='learning' if i<6 else 'admin',task_submission=''))
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(len(items),6)
        self.assertEqual({q['ref'] for item in items for q in item['evidence']},{e['ref'] for e in evidence})

    def test_one_message_keeps_six_distinct_requirements_and_their_semantics(self):
        ref='message:synthetic-six:1';due=(self.now.date()+dt.timedelta(days=1)).isoformat()
        requirements=[
            ('英语：朗读Unit 2','课文读两遍，将朗读录音上传班级作业区。','朗读录音上传班级作业区','learning'),
            ('英语：抄写Unit 2单词','抄写第8页的10个单词，每词一遍。','','learning'),
            ('英语：默写Unit 2单词','默写第8页的10个单词。','','learning'),
            ('英语：完成练习卷','第1–3题必做，第4题选做。','','learning'),
            ('英语：订正练习','有错题的同学订正第5页的错题，订正后拍照上传班级作业区。','拍照上传班级作业区','learning'),
            ('英语：选读故事','选做：阅读第9页故事，不要求提交录音。','','optional'),
        ]
        text='明天完成以下六项英语要求：\n'+'\n'.join(str(i)+'. '+goal for i,(_,goal,_,_) in enumerate(requirements,1))
        evidence=[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)]
        proposals=[school_proposal(title_quote='六项英语要求',due=due,evidence=[dict(ref=ref)],
            learning_subject='英语' if purpose=='learning' else '',task_title=title,task_goal=goal,
            task_state='ready' if purpose=='learning' and not goal.startswith('有错题') else 'review',task_reason='原文逐项要求。',
            task_purpose=purpose,task_submission=submission) for title,goal,submission,purpose in requirements]
        # This controls preservation of a correct model result; it does not measure model extraction accuracy.
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)) as model:
            items=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(model.call_args.args[1]['properties']['proposals']['maxItems'],36)
        self.assertEqual([(i['title'],i['body'],i['due']) for i in items],[(t,g,due) for t,g,_,_ in requirements])
        self.assertEqual([i['plan']['school_task'].get('submission','') for i in items],[s for _,_,s,_ in requirements])
        self.assertEqual([i['plan']['school_task']['purpose'] for i in items],[p for _,_,_,p in requirements])
        self.assertEqual([i['plan']['school_task']['state'] for i in items],['ready']*4+['review','review'])
        self.assertTrue(all(i['evidence']==[dict(ref=ref,text=text[:600])] for i in items))

    def _independent_school_actions_with_parent_receipt(self, with_submission, *, receipt_name='独立活动回执', own_learning=False):
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        learning_title='英语：朗读第5课' if with_submission else '数学：完成练习卷'
        learning_goal=('朗读第5课课文两遍，录音上传班级作业区。' if with_submission else
                       '完成练习卷第1–3题（必做），第4题选做。')
        submission='录音上传班级作业区' if with_submission else ''
        admin_title='家长事务：'+receipt_name
        admin_goal=('家长先阅读课文，再签字交回'+receipt_name+'。无需盖章。' if own_learning else
                    '家长在'+receipt_name+'上签字，再让孩子交回。无需盖章。')
        text='明天完成两件独立的事：\n1. '+learning_goal+'\n2. '+admin_goal
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        proposals=[school_proposal(title_quote='朗读第5课' if with_submission else '练习卷',due=due,
            evidence=[dict(ref=ref)],task_title=learning_title,task_goal=learning_goal,
            task_state='ready',task_reason='第一项是孩子的独立学习要求。',task_purpose='learning',task_submission=submission),
            school_proposal(title_quote=receipt_name,due=due,evidence=[dict(ref=ref)],
                task_title=admin_title,task_goal=admin_goal,task_state='ready',
                task_reason='第二项是另一份家长回执，属于独立事务。',task_purpose='admin')]
        evidence=[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)]
        # A correct saved-model response has already separated the two actions. Sharing its
        # original notice must not turn the independent receipt into the homework submission.
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)) as response:
            items=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(response.call_count,1)
        self.assertEqual([(item['title'],item['body'],item['due']) for item in items],
                         [(learning_title,learning_goal,due),(admin_title,admin_goal,due)])
        self.assertEqual([item['plan']['school_task']['purpose'] for item in items],['learning','admin'])
        self.assertEqual([item['plan']['school_task']['state'] for item in items],
                         ['ready','review' if own_learning else 'ready'],
                         'a receipt name is not a learning action, but its own reading requirement still needs review')
        if own_learning:self.assertIn('学习活动',items[1]['plan']['school_task']['reason'])
        self.assertEqual(items[0]['plan']['school_task'].get('submission',''),submission)
        self.assertNotIn('submission',items[1]['plan']['school_task'])
        self.assertTrue(all(item['evidence']==[dict(ref=ref,text=text)] for item in items))
        key='synthetic-independent-school-actions';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved actions need no model')):
            collected=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        expected_created=1 if own_learning else 2
        self.assertEqual((collected['created'],repeated['created']),(expected_created,0))
        with self.app.connect() as c:
            tasks={row['title']:dict(row) for row in c.execute('SELECT * FROM manual_tasks')}
            expected_tasks=[(learning_title,learning_goal)]+([] if own_learning else [(admin_title,admin_goal)])
            self.assertEqual(set(tasks),{title for title,_ in expected_tasks})
            for title,goal in expected_tasks:
                task=tasks[title]
                self.assertEqual((task['child'],task['action'],task['due'],task['original_status']),
                                 ('示例甲',goal,due,'待跟进'))
                self.assertIn(ref,task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="accepted"').fetchone()[0],expected_created)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="pending"').fetchone()[0],2-expected_created)
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_one_notice_keeps_independent_parent_receipt_beside_homework_submission(self):
        self._independent_school_actions_with_parent_receipt(True)

    def test_one_notice_keeps_independent_parent_receipt_beside_exercises_without_submission(self):
        self._independent_school_actions_with_parent_receipt(False)

    def test_reading_activity_receipt_name_does_not_hide_the_independent_parent_action(self):
        self._independent_school_actions_with_parent_receipt(True,receipt_name='阅读活动回执')

    def test_parent_receipt_with_its_own_reading_requirement_stays_review(self):
        self._independent_school_actions_with_parent_receipt(True,receipt_name='阅读活动回执',own_learning=True)

    def test_same_homework_checkin_does_not_become_an_independent_admin_task(self):
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        goal='朗读第5课课文两遍，录音上传班级作业区。'
        text='明天完成朗读第5课课文两遍，录音上传班级作业区。'
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        proposals=[school_proposal(title_quote='朗读第5课',due=due,evidence=[dict(ref=ref)],
            task_title='英语：朗读第5课',task_goal=goal,task_state='ready',task_reason='明确朗读及其提交。',
            task_purpose='learning',task_submission='录音上传班级作业区'),
            school_proposal(title_quote='录音上传',due=due,evidence=[dict(ref=ref)],task_title='朗读录音提交',
                task_goal='录音上传班级作业区。',task_state='ready',task_reason='同一朗读作业的提交步骤。',task_purpose='admin')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)],
                                school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([item['plan']['school_task']['state'] for item in items],['ready','review'])
        self.assertEqual(items[0]['body'],goal)
        self.assertEqual(items[0]['plan']['school_task']['submission'],'录音上传班级作业区')
        self.assertTrue(all(item['evidence']==[dict(ref=ref,text=text)] for item in items))
        key='synthetic-same-homework-submission';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved submission needs no model')):
            collected=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        self.assertEqual((collected['created'],repeated['created']),(1,0))
        with self.app.connect() as c:
            task,=c.execute('SELECT child,title,action,due,original_status FROM manual_tasks').fetchall()
            self.assertEqual(tuple(task),('示例甲','英语：朗读第5课',goal,due,'待跟进'))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="pending"').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_independent_receipt_is_not_the_homework_submission_when_the_channel_matches(self):
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        text=('明天分别完成两件独立的事：\n'
              '1. 朗读第5课课文两遍，录音在班级小程序提交。\n'
              '2. 家长在班级小程序提交防溺水回执，与朗读录音分开提交。')
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        learning_title='英语：朗读第5课'
        learning_goal='朗读第5课课文两遍，在班级小程序提交朗读录音。'
        admin_title='家长事务：提交防溺水回执';admin_goal='在班级小程序提交。'
        proposals=[school_proposal(title_quote='朗读第5课',due=due,evidence=[dict(ref=ref)],
            task_title=learning_title,task_goal=learning_goal,task_state='ready',
            task_reason='第一项是朗读及其录音提交。',task_purpose='learning',
            task_submission='在班级小程序提交朗读录音。'),
            school_proposal(title_quote='防溺水回执',due=due,evidence=[dict(ref=ref)],
                task_title=admin_title,task_goal=admin_goal,task_state='ready',
                task_reason='标题指定另一份回执，原文明说与朗读录音分开提交。',task_purpose='admin')]
        # The title identifies the independent document; its action can share the
        # homework's channel without becoming a second copy of the recording.
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)],
                                school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([(item['title'],item['body'],item['due']) for item in items],
                         [(learning_title,learning_goal,due),(admin_title,admin_goal,due)])
        self.assertEqual([item['plan']['school_task']['state'] for item in items],['ready','ready'],
                         'distinct documents must remain separate even when both use the same submission channel')
        self.assertEqual([item['plan']['school_task']['purpose'] for item in items],['learning','admin'])
        self.assertTrue(all(item['evidence']==[dict(ref=ref,text=text)] for item in items))
        key='synthetic-independent-receipt-shared-channel';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved actions need no model')):
            collected=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        self.assertEqual((collected['created'],repeated['created']),(2,0))
        with self.app.connect() as c:
            tasks={row['title']:dict(row) for row in c.execute('SELECT * FROM manual_tasks')}
            self.assertEqual(set(tasks),{learning_title,admin_title})
            for title,goal in [(learning_title,learning_goal),(admin_title,admin_goal)]:
                task=tasks[title]
                self.assertEqual((task['child'],task['action'],task['due'],task['original_status']),
                                 ('示例甲',goal,due,'待跟进'))
                self.assertIn(ref,task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="accepted"').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def _same_recording_submission_stays_one_homework(self, admin_goal):
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        submission='在班级小程序提交录音'
        goal='朗读第5课课文两遍，'+submission+'。'
        text='明天完成'+goal
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        proposals=[school_proposal(title_quote='朗读第5课',due=due,evidence=[dict(ref=ref)],
            task_title='英语：朗读第5课',task_goal=goal,task_state='ready',
            task_reason='同一朗读作业及其录音提交。',task_purpose='learning',task_submission=submission),
            school_proposal(title_quote='提交录音',due=due,evidence=[dict(ref=ref)],
                task_title='录音提交',task_goal=admin_goal,task_state='ready',
                task_reason='这一录音属于第一项朗读作业，并非独立成果。',task_purpose='admin')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)],
                                school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([item['plan']['school_task']['state'] for item in items],['ready','review'])
        self.assertIn('避免重复',items[1]['plan']['school_task']['reason'])
        self.assertEqual((items[1]['title'],items[1]['body']),('录音提交',admin_goal))
        self.assertEqual(items[0]['plan']['school_task']['submission'],submission)
        self.assertTrue(all(item['evidence']==[dict(ref=ref,text=text)] for item in items))
        key='synthetic-recording-title-is-submission';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved submission needs no model')):
            collected=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        self.assertEqual((collected['created'],repeated['created']),(1,0))
        with self.app.connect() as c:
            task,=c.execute('SELECT child,title,action,due,original_status,source FROM manual_tasks').fetchall()
            self.assertEqual(tuple(task)[:5],('示例甲','英语：朗读第5课',goal,due,'待跟进'))
            self.assertIn(ref,task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="accepted"').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="pending"').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_recording_submission_title_remains_a_step_of_the_same_homework(self):
        self._same_recording_submission_stays_one_homework('在班级小程序提交录音')

    def test_same_recording_submission_with_reordered_upload_words_is_not_a_second_task(self):
        self._same_recording_submission_stays_one_homework('上传录音到班级小程序。')

    def _school_admin_requires_a_ready_learning_peer(self, peer_kind):
        ref='message:'+self.source['id']+':11';due='2026-02-11'
        admin_title='家长事务：独立活动回执';admin_goal='家长签字交回活动回执。'
        first=('朗读第5课仅供参考。' if peer_kind=='reference' else
               '自愿选做：朗读第5课两遍。' if peer_kind=='optional' else
               '朗读第5课课文两遍。'+('其他学习要求见另发图片。' if peer_kind=='unread' else ''))
        text='英语：'+first+'\n家长明天完成另一件独立事务：'+admin_goal
        payload=self.payload();payload['messages'][0]['text']=text
        learning_refs=[dict(ref=ref)]
        if peer_kind=='unread':
            payload['messages'].append(dict(id='12',time=self.now.isoformat(),kind='image',sender='示例老师',
                text='[图片原件：1份，内容未读]',unread=True))
            payload['cursor']='12';learning_refs.append(dict(ref='message:'+self.source['id']+':12'))
        self.store.ingest(payload)
        proposals=[school_proposal(title_quote='朗读第5课',due='2026-02-12' if peer_kind=='date' else '',
            evidence=learning_refs,task_title='英语：朗读第5课',task_goal=first,
            task_state='reference' if peer_kind=='reference' else 'ready',
            task_reason='固定原始模型状态，程序还须核用途、附件和日期。',
            task_purpose='optional' if peer_kind=='optional' else 'learning'),
            school_proposal(title_quote='活动回执',due=due,evidence=[dict(ref=ref)],
                task_title=admin_title,task_goal=admin_goal,task_state='ready',task_reason='已读行政正文明确。',
                task_purpose='admin')]
        evidence=[dict(ref='message:'+self.source['id']+':'+m['id'],text=m['text'],time=m['time'],
                       kind=m['kind'],unread=m['unread'],content_incomplete=m['unread']) for m in payload['messages']]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(items[0]['plan']['school_task']['state'],'reference' if peer_kind=='reference' else 'review')
        self.assertEqual(items[1]['plan']['school_task']['state'],'review',
                         'a reference, optional or guarded peer cannot remove the mixed-notice protection')
        self.assertEqual((items[1]['title'],items[1]['body'],items[1]['due']),
                         (admin_title,admin_goal,due))
        self.assertEqual([q['ref'] for q in items[0]['evidence']],[q['ref'] for q in learning_refs])
        self.assertEqual(items[1]['evidence'],[dict(ref=ref,text=text)])
        if peer_kind=='unread':self.assertIn('未读',items[0]['plan']['school_task']['reason'])
        if peer_kind=='date':
            self.assertEqual(items[0]['due'],'')
            self.assertIn('未采用模型日期',items[0]['plan']['school_task']['reason'])
        key='synthetic-nonready-learning-peer-'+peer_kind;fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],m['id']) for m in payload['messages']],
                         school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('guarded actions need no model')):
            collected=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        self.assertEqual((collected['created'],repeated['created']),(0,0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items WHERE state="accepted"').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_reference_learning_peer_does_not_unlock_mixed_admin_protection(self):
        self._school_admin_requires_a_ready_learning_peer('reference')

    def test_optional_learning_peer_does_not_unlock_mixed_admin_protection(self):
        self._school_admin_requires_a_ready_learning_peer('optional')

    def test_unread_learning_peer_does_not_unlock_mixed_admin_protection(self):
        self._school_admin_requires_a_ready_learning_peer('unread')

    def test_unguarded_model_date_does_not_make_a_learning_peer_unlock_admin_protection(self):
        self._school_admin_requires_a_ready_learning_peer('date')

    def test_school_output_bound_is_shared_and_overflow_never_truncates(self):
        ref='message:synthetic-many:1'
        evidence=[dict(ref=ref,text='原文包含36条独立学校说明。',time=self.now.isoformat(),content_incomplete=False)]
        proposals=[school_proposal(title_quote='学校说明',evidence=[dict(ref=ref)],task_title='说明'+str(i),
            task_goal='独立说明'+str(i),task_state='reference',task_reason='参考内容，不生成任务。',task_purpose='optional') for i in range(36)]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)) as model:
            self.assertEqual(len(agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())),36)
        self.assertEqual(model.call_args.args[1]['properties']['proposals']['maxItems'],agent.SCHOOL_PROPOSAL_LIMIT)
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals+[dict(proposals[0])])):
            with self.assertRaises(agent.AgentError):
                agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())

    def test_school_model_empty_purpose_is_rejected_while_saved_legacy_brief_stays_readable(self):
        ref='message:synthetic-purpose:1';text='请明天带阅读材料到校。'
        evidence=[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)]
        proposal=school_proposal(title_quote='带阅读材料',evidence=[dict(ref=ref)],
            task_title='带阅读材料',task_goal='带阅读材料到校。',task_state='ready',task_purpose='')
        self.assertEqual(set(proposal),set(agent.SCHOOL_SCHEMA['properties']['proposals']['items']['required']))
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            with self.assertRaises(agent.AgentError):
                agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        legacy=dict(title='带阅读材料',goal='带阅读材料到校。',advice='',state='ready',reason='旧记录要求明确。')
        for value in (legacy,dict(legacy,purpose='')):
            with self.subTest(saved_purpose=value.get('purpose')):
                brief=agent._school_brief(value,evidence=evidence)
                self.assertEqual((brief['title'],brief['goal'],brief['state']),('带阅读材料','带阅读材料到校。','ready'))
                self.assertEqual(brief.get('purpose',''),'')

    def test_explicitly_negated_child_action_does_not_block_parent_notice(self):
        endings=('不用让孩子抄写。','无需孩子抄写。','不必抄写。','不要求学生抄写。',
                 '不要默写。','不得听写。','禁止跟读。','勿背诵。')
        for ending in endings:
            text='家长核对学校通讯录，有误修改，无误点“已核对”。不要在群里发电话号码或截图，'+ending
            value=dict(title='家长事务：核对紧急联系电话',goal=text,advice='',state='ready',
                       reason='独立家长事务，要求明确。',purpose='admin')
            for separate in (False,True):
                with self.subTest(ending=ending,separate=separate):
                    evidence=[dict(ref='message:synthetic-negative:1',text=text,kind='text',unread=False)]
                    brief=agent._school_brief(value,evidence=evidence,separate_learning=separate)
                    self.assertEqual((brief['state'],brief['purpose'],brief['goal']),('ready','admin',text))
                    self.assertEqual(evidence[0]['text'],text,'negative requirements remain in the original')

    def test_negation_does_not_remove_positive_or_inverse_learning_requirements(self):
        cases=('不用抄写，但需朗读两遍。','先朗读两遍，再核对通讯录；不用抄写。',
               '不用抄写再朗读两遍。','并非不用抄写。','不是不需要背诵。',
               '不要忘记朗读。','不要只抄写。','无需录音，但完成第1–3题。',
               '不用抄写课文。','并不是禁止同学订正。','不要求朗读速度达标。',
               '不要求朗读流利。','不要求朗读 次数达标。','请家长不要忘记让孩子朗读后签字。',
               '并非（不用让孩子抄写）。','不是（不需要学生朗读）。',
               '并非（签字后，不用抄写）。','不是（核对后；无需朗读）。','并非\n不用抄写。')
        # Only direct negated verbs are removed from classification. Unresolved objects
        # and inverse/limited negation remain guarded, never deleted from the notice.
        for clause in cases:
            text='家长核对通讯录。'+clause
            value=dict(title='家长事务：核对通讯录',goal=text,advice='',state='ready',reason='',purpose='admin')
            for separate in (False,True):
                with self.subTest(clause=clause,separate=separate):
                    brief=agent._school_brief(value,evidence=[dict(ref='message:synthetic-negative:2',text=text,kind='text')],
                                              separate_learning=separate)
                    self.assertEqual((brief['state'],brief['goal']),('review',text))
                    self.assertIn('同时提到学习活动',brief['reason'])

        text='不用让孩子抄写。家长核对学校通讯录。'
        brief=agent._school_brief(dict(title='家长事务：核对联系电话',goal=text,advice='',state='ready',reason='',purpose='admin'),
            evidence=[dict(ref='message:synthetic-negative:3',text=text,kind='text')],separate_learning=True)
        self.assertEqual((brief['state'],brief['goal']),('ready',text))

    def test_negated_child_action_parent_notice_is_collected_once_with_original_deadline(self):
        self.now=dt.datetime(2026,10,4,10,tzinfo=agent.TZ)
        text='请家长后天完成学校通讯录中的紧急联系电话核对；有误修改，无误点“已核对”。不要在群里发电话号码或核对截图，不用让孩子抄写。'
        payload=self.payload();payload['messages'][0].update(text=text,time='2026-10-03T16:20:00+08:00')
        self.store.ingest(payload)
        ref='message:'+self.source['id']+':11';title='家长事务：核对紧急联系电话'
        proposal=school_proposal(title_quote='紧急联系电话',due='2026-10-05',evidence=[dict(ref=ref)],
            task_title=title,task_goal=text,task_state='ready',task_reason='明确家长事务。',task_purpose='admin')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            items=agent._select('school',[dict(ref=ref,text=text,time=payload['messages'][0]['time'],content_incomplete=False)],
                                school_goals=[],school_tasks=[],as_of=self.now.date().isoformat())
        self.assertEqual(items[0]['plan']['school_task']['state'],'ready')
        key='synthetic-negative-child-action';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved notice must not need another model')):
            first=agent._refresh_school(self.app,self.store,self.now,0)
            repeat=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0)
        self.assertEqual((first['created'],repeat['created']),(1,0))
        with self.app.connect() as c:
            task,=list(c.execute('SELECT * FROM manual_tasks'))
            self.assertEqual((task['title'],task['action'],task['due'],task['original_status']),
                             (title,text,'2026-10-05','待跟进'))
            self.assertIn(ref,task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_school_admin_material_preparation_does_not_hide_actual_learning_actions(self):
        cases=[
            ('请明天带阅读材料到校。','ready'),
            ('请明天携带英语练习卷。','ready'),
            ('请家长打印语文作业单，明天带到校。','ready'),
            ('请明天带阅读材料，朗读第5课三遍后上传录音。','review'),
            ('请携带英语练习卷，完成练习卷第1–3题后签到。','review'),
            ('请打印语文作业单，完成作业单第2题后上传。','review'),
            ('请明天带阅读材料，阅读第5课后在班级小程序打卡。','review'),
            ('请打印英语练习卷，完成第1–3题后上传。','review'),
            ('请家长打印语文作业单，孩子做第2题后交回。','review'),
            ('请带阅读材料，读第5课后在班级小程序打卡。','review'),
            ('请打印英语练习卷，做完后拍照上传。','review'),
            ('请带阅读材料，把第2页读两遍后打卡。','review'),
        ]
        for i,(text,state) in enumerate(cases):
            ref='message:synthetic-material-action:'+str(i)
            proposal=school_proposal(title_quote=text[:120],evidence=[dict(ref=ref)],
                task_title='准备学校资料',task_goal=text,task_state='ready',task_reason='模型归为学校事务。',task_purpose='admin')
            with self.subTest(text=text),patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
                item,=agent._select('school',[dict(ref=ref,text=text,time=self.now.isoformat(),content_incomplete=False)],
                    school_goals=[],as_of=self.now.date().isoformat())
            brief=item['plan']['school_task']
            self.assertEqual((brief['state'],brief['purpose'],item['body']),(state,'admin',text))
            self.assertNotIn('school_learning',item['plan'])
            if state=='review':self.assertIn('学习活动',brief['reason'])

    def test_first_batch_correction_and_unknown_prior_task_keep_distinct_change_guards(self):
        original='明天完成《桥的观察单》，A、B、C栏必做。'
        correction='更正第二项《桥的观察单》：A、B必做，C选做，不做C也算完成；原期限不变。'
        ref1='message:synthetic-correction:m1';ref2='message:synthetic-correction:m2'
        evidence=[dict(ref=ref1,text=original,time='2026-10-03T16:10:00+08:00',publisher='publisher:synthetic-a',content_incomplete=False),
                  dict(ref=ref2,text=correction,time='2026-10-04T08:05:00+08:00',publisher='publisher:synthetic-a',content_incomplete=False)]
        base=school_proposal(title_quote=original,task_title='语文：完成《桥的观察单》',
            task_goal='完成《桥的观察单》：A、B必做，C选做，不做C也算完成。',task_state='ready',
            task_purpose='learning',learning_subject='语文',due='2026-10-04',evidence=[dict(ref=ref1),dict(ref=ref2)])
        for label,change,target,tasks,state in (
                ('first-batch','new','',[],'ready'),
                ('unresolved-old','update','',[],'review'),
                ('saved-task','update','saved-task',[dict(id='saved-task')],'review'),
                ('cancel','cancel','',[],'review')):
            value=dict(base,task_change=change,task_target_id=target)
            with self.subTest(label=label),patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[value])):
                item,=agent._select('school',evidence,school_goals=[],school_tasks=tasks,as_of='2026-10-04')
                brief=item['plan']['school_task']
                self.assertEqual((brief['change'],brief['target_id'],brief['state']),(change,target,state))
                self.assertEqual(item['body'],base['task_goal'])
                self.assertEqual([q['text'] for q in item['evidence']],[original,correction])
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[dict(base,
                title_quote=correction,due='',task_change='update',evidence=[dict(ref=ref2)])])):
            item,=agent._select('school',evidence[1:],school_goals=[],school_tasks=[],as_of='2026-10-04')
        self.assertEqual((item['plan']['school_task']['change'],item['plan']['school_task']['state']),('update','review'))
        self.assertEqual(item['due'],'')

    def test_multi_action_batch_recovers_only_its_directly_dated_admin_action(self):
        text='请家长后天完成学校通讯录中的紧急联系电话核对；有误修改，无误点已核对。不要在群里发号码，不用让孩子抄写。'
        ref='message:synthetic-admin:m1';other='message:synthetic-admin:m2'
        evidence=[dict(ref=ref,text=text,time='2026-10-03T16:20:00+08:00',kind='text',content_incomplete=False),
                  dict(ref=other,text='今天朗读课文两遍。',time='2026-10-04T08:00:00+08:00',kind='text',content_incomplete=False)]
        parent=school_proposal(title_quote=text[:120],evidence=[dict(ref=ref)],task_title='核对紧急联系电话',
            task_goal=text.replace('后天',''),task_state='ready',task_purpose='admin')
        reading=school_proposal(title_quote='今天朗读课文两遍。',evidence=[dict(ref=other)],due='2026-10-04',
            task_title='朗读课文',task_goal='今天朗读课文两遍。',task_state='ready',task_purpose='learning',learning_subject='语文')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[parent,reading])):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-04')
        self.assertEqual((items[0]['due'],items[0]['plan']['school_task']['state'],items[0]['body']),
            ('2026-10-05','ready',parent['task_goal']))
        self.assertEqual(items[1]['due'],'2026-10-04')
        cases=[
            ('请家长完成学校通讯录中的紧急联系电话核对；明天交回活动回执。',parent['task_goal'],'2026-10-03T16:20:00+08:00',False),
            (text,parent['task_goal'],'',False),
            (text,parent['task_goal'],'2026-10-03T16:20:00',False),
            (text,parent['task_goal'],'2026-10-03T16:20:00+08:00',True),
            (text,parent['task_goal']+'2026-10-06前完成。','2026-10-03T16:20:00+08:00',False),
            (text,parent['task_goal'].replace('紧急联系电话','家庭电话'),'2026-10-03T16:20:00+08:00',False)]
        for source,goal,time,unread in cases:
            with self.subTest(source=source,goal=goal,time=time,unread=unread):
                self.assertEqual(agent._school_explicit_action_due(dict(change='new',purpose='admin',goal=goal),
                    [dict(ref=ref,text=source,time=time,kind='text',content_incomplete=unread)]),'')
        self.assertEqual(agent._school_explicit_action_due(dict(change='update',purpose='admin',goal=parent['task_goal']),evidence[:1]),'')
        self.assertEqual(agent._school_explicit_action_due(dict(change='new',purpose='admin',goal=parent['task_goal']),evidence[:1]*2),'')

    def test_first_batch_correction_requires_a_unique_dated_original_and_same_publisher(self):
        original='明天完成两项。第一项朗读课文。第二项：完成《桥的观察单》，A、B、C三栏都要做。'
        change='更正10月3日16:10发布的第二项《桥的观察单》：A、B栏仍必做；C栏改为选做，原期限不变。'
        evidence=[dict(ref='message:synthetic:m1',text=original,time='2026-10-03T16:10:00+08:00',kind='text',publisher='publisher:a',content_incomplete=False),
                  dict(ref='message:synthetic:m2',text=change,time='2026-10-04T08:05:00+08:00',kind='text',publisher='publisher:a',content_incomplete=False)]
        brief=dict(change='update',target_id='',title='完成《桥的观察单》',goal='A/B必做，C选做。')
        proof=agent._school_first_batch_correction(brief,evidence)
        self.assertEqual((proof['original_ref'],proof['correction_ref'],proof['object']),
            ('message:synthetic:m1','message:synthetic:m2','《桥的观察单》'))
        for values in (evidence[1:],evidence+[dict(evidence[0],ref='message:synthetic:m3')],
                       [evidence[0],dict(evidence[1],publisher='publisher:b')],
                       [dict(evidence[0],content_incomplete=True),evidence[1]],
                       [dict(evidence[0],time='2026-10-03T16:10:00'),evidence[1]],
                       [evidence[0],dict(evidence[1],time='2026-10-04T08:05:00')],
                       [evidence[0],dict(evidence[1],text=change.replace('16:10','16:11'))],
                       [evidence[0],dict(evidence[1],text=change+'取消整个观察单。')]):
            self.assertIsNone(agent._school_first_batch_correction(brief,values))
        self.assertIsNone(agent._school_first_batch_correction(dict(brief,target_id='saved-task'),evidence))
        self.assertIsNone(agent._school_first_batch_correction(dict(brief,change='cancel'),evidence))

    def _legacy_initial_correction(self, *, duplicate=False, sibling=False, sibling_body=None):
        """Reproduce a saved r188 selection, without inventing the later initial snapshot."""
        self.now=dt.datetime(2026,10,4,10,tzinfo=agent.TZ);self.config()
        original='明天完成两项语文要求。第一项：朗读课文两遍，不用录音。第二项：完成《桥的观察单》，A、B、C三栏都要做，不打印或上传。'
        correction='更正10月3日16:10发布的第二项《桥的观察单》：A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。其余要求和原期限不变。'
        values=[dict(id='11',time='2026-10-03T16:10:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text=original,unread=False),
                dict(id='12',time='2026-10-04T08:05:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text=correction,unread=False)]
        if duplicate:values.append(dict(values[0],id='13'))
        payload=self.payload(cursor='13' if duplicate else '12');payload['messages']=values;self.store.ingest(payload)
        evidence=[dict(ref='message:'+self.source['id']+':'+v['id'],text=v['text'],time=v['time'],kind=v['kind'],
            publisher=agent._publisher(self.source['id'],v),content_incomplete=False) for v in values]
        proposal=school_proposal(title_quote=original,task_title='语文：完成《桥的观察单》',task_goal='完成《桥的观察单》，A、B必做，C选做。',
            due='2026-10-04',task_state='ready',task_change='update',task_purpose='learning',learning_subject='语文',
            evidence=[dict(ref=e['ref']) for e in evidence[:2]])
        proposals=[proposal]
        if duplicate:proposals.append(dict(proposal,evidence=[dict(ref=evidence[2]['ref'])]))
        if sibling:proposals.append(school_proposal(title_quote='朗读课文两遍，不用录音。',task_title='语文：朗读课文',
            task_goal='朗读课文两遍，不用录音。',due='2026-10-04',task_state='ready',task_purpose='learning',learning_subject='语文',evidence=[dict(ref=evidence[0]['ref'])]))
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-04')
        for item in items:
            item.update(child_id='child-1',kind='school')
            item['plan'].pop('school_selection_receipt',None)  # This field did not exist in r188.
        key='messages:'+agent._hash([self.source['id'],[v['id'] for v in values]])[:40]
        fp=self.store._job(key,dict(school_learning_policy=8,messages=values),self.now,model=True)
        self.store._save(key,fp,items,self.now,[(self.source['id'],v['id']) for v in values])
        with self.app.connect() as c:rows=[dict(r) for r in c.execute("SELECT * FROM agent_items ORDER BY rowid")]
        if sibling:self.store.act(dict(id=rows[1]['id'],action='accept',**(dict(action_text=sibling_body) if sibling_body else {})))
        return rows[0],key,fp,evidence[:2]

    def _legacy_mapping(self,row,evidence):
        def mapped(messages,schema,*args,**kwargs):
            context=json.loads(messages[-1]['content']);parts=context['original_parts']
            self.assertEqual(context['verified_first_batch_correction']['original_ref'],evidence[0]['ref'])
            self.assertIn('不证明旧输出正确',context['legacy_reread'])
            return dict(actions=[dict(title='语文：完成《桥的观察单》',goal='完成《桥的观察单》。',advice='',state='ready',
                reason='同一原通知及明确栏目更正已对应。',purpose='learning',submission='',change='new',target_id='',
                learning_subject='语文',learning_goal_id='',due='2026-10-04',existing_item_id=row['id'],
                basis=[dict(part=p['id'],text=p['text']) for p in parts],condition_changes=[dict(old_part=parts[0]['id'],
                    old_text='A、B、C三栏都要做',new_part=parts[1]['id'],new_text='A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。')])])
        return mapped

    def test_legacy_initial_correction_refreshes_when_policy_and_sources_are_unchanged(self):
        row,key,fp,evidence=self._legacy_initial_correction(sibling=True)
        old=dict(row);self.assertNotIn('school_generated_snapshot',json.loads(row['plan']))
        with self.app.connect() as c:
            sources=[dict(r) for r in c.execute('SELECT * FROM agent_sources')]
            messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages')]
            sibling=dict(c.execute('SELECT * FROM agent_items WHERE id!=?',(row['id'],)).fetchone())
            sibling_task=dict(c.execute('SELECT * FROM manual_tasks').fetchone())
        with patch.object(agent.family_llm,'_chat_json',side_effect=self._legacy_mapping(row,evidence)) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0),dict(used=0,failed=0,created=0))
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=1))
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1),dict(used=0,failed=0,created=0))
        self.assertEqual(model.call_count,1)
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone());plan=json.loads(saved['plan'])
            self.assertEqual((saved['state'],saved['due']),('accepted','2026-10-04'))
            self.assertNotIn('school_generated_snapshot',plan,'recovery must not claim an immutable initial snapshot existed')
            self.assertEqual(plan['school_legacy_correction_recovery']['previous'],old)
            self.assertNotIn('朗读课文',saved['body']);self.assertIn('C栏改为选做',saved['body']);self.assertIn('不打印或上传',saved['body'])
            self.assertEqual(sources,[dict(r) for r in c.execute('SELECT * FROM agent_sources')])
            self.assertEqual(messages,[dict(r) for r in c.execute('SELECT * FROM agent_messages')])
            self.assertEqual(sibling,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(sibling['id'],)).fetchone()))
            self.assertEqual(sibling_task,dict(c.execute('SELECT * FROM manual_tasks WHERE id=?',(sibling_task['id'],)).fetchone()))
            self.assertEqual(tuple(c.execute('SELECT fingerprint,done FROM agent_jobs WHERE id=?',(key,)).fetchone()),(fp,1))
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],2)

    def test_legacy_correction_reread_keeps_expired_due_pending(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        with patch.object(agent.family_llm,'_chat_json',side_effect=self._legacy_mapping(row,evidence)) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(days=2),1),dict(used=1,failed=0,created=0))
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(days=2,minutes=1),1),dict(used=0,failed=0,created=0))
        self.assertEqual(model.call_count,1)
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone());plan=json.loads(saved['plan'])
            self.assertEqual((saved['state'],saved['due'],plan['school_task']['state']),('pending','2026-10-04','review'))
            self.assertIn('原截止日期已过',plan['school_task']['reason']);self.assertIn('C栏改为选做',saved['body'])
            self.assertEqual(plan['school_legacy_correction_recovery']['previous'],row)
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_legacy_correction_rejects_parent_changed_effective_sibling(self):
        row,key,fp,evidence=self._legacy_initial_correction(sibling=True,sibling_body='完成《桥的观察单》，A、B栏必做。')
        with self.store._db() as c:self.assertIsNone(agent._school_legacy_batch_correction(self.store,c,row,evidence))

    def test_correction_rejects_later_named_or_numbered_cancellation(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        for text in ('更正10月3日16:10发布的第二项《桥的观察单》：取消本项，观察单不用做。','原第二项不用做了。'):
            with self.store._db() as c:
                c.execute('SAVEPOINT cancellation')
                message=dict(id='13',time='2026-10-04T08:10:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text=text,unread=False)
                c.execute('INSERT INTO agent_messages(source_id,id,payload,processed) VALUES(?,?,?,1)',(self.source['id'],'13',agent._json(message)))
                self.assertIsNone(agent._school_legacy_batch_correction(self.store,c,row,evidence))
                whole=evidence+[dict(message,ref='message:'+self.source['id']+':13',publisher=evidence[0]['publisher'],content_incomplete=False)]
                self.assertIsNone(agent._school_first_batch_correction(json.loads(row['plan'])['school_task'],whole))
                c.execute('ROLLBACK TO cancellation');c.execute('RELEASE cancellation')

    def test_legacy_correction_discards_new_cancellation_during_model(self):
        row,key,fp,evidence=self._legacy_initial_correction();mapped=self._legacy_mapping(row,evidence)
        def changed(*args,**kwargs):
            payload=self.payload(expected='12',cursor='13');payload['messages']=[dict(id='13',time='2026-10-04T10:01:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='原第二项不用做了。',unread=False)]
            self.store.ingest(payload)
            return mapped(*args,**kwargs)
        with patch.object(agent.family_llm,'_chat_json',side_effect=changed) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=0))
        self.assertEqual(model.call_count,1)
        with self.app.connect() as c:
            self.assertEqual(row,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone()))
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_legacy_correction_acceptance_rechecks_arrivals_after_reread_save(self):
        row,key,fp,evidence=self._legacy_initial_correction();save=agent._save_school_originals
        def arrived(*args,**kwargs):
            saved=save(*args,**kwargs)
            message=dict(id='13',time='2026-10-04T10:01:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='原第二项不用做了。',unread=False)
            args[1].execute('INSERT INTO agent_messages(source_id,id,payload,processed) VALUES(?,?,?,1)',(self.source['id'],'13',agent._json(message)))
            return saved
        with patch.object(agent.family_llm,'_chat_json',side_effect=self._legacy_mapping(row,evidence)),patch.object(agent,'_save_school_originals',side_effect=arrived):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=0))
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone());brief=json.loads(saved['plan'])['school_task']
            self.assertEqual((saved['state'],brief['state']),('pending','review'));self.assertIn('后发变化',brief['reason'])
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_rejected_legacy_correction_never_falls_back_to_old_policy_summary(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        with self.app.connect() as c:
            plan=json.loads(row['plan']);plan['school_task']['policy']=8
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(agent._json(plan),row['id']))
            message=dict(id='13',time='2026-10-04T10:01:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='原第二项不用做了。',unread=False)
            c.execute('INSERT INTO agent_messages(source_id,id,payload,processed) VALUES(?,?,?,1)',(self.source['id'],'13',agent._json(message)))
            old=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone())
        with patch.object(agent.family_llm,'_chat_json') as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=0,failed=0,created=0))
        model.assert_not_called()
        with self.app.connect() as c:self.assertEqual(old,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone()))

    def test_legacy_correction_includes_complete_additional_native_requirements(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        payload=self.payload(expected='12',cursor='13');payload['messages']=[dict(id='13',time='2026-10-04T09:00:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='补发《桥的观察单》：A栏填写两种方法并写单位。',unread=False)]
        self.store.ingest(payload)
        with patch.object(agent.family_llm,'_chat_json',side_effect=self._legacy_mapping(row,evidence)):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=1))
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone())
            self.assertIn('A栏填写两种方法并写单位',saved['body'])
            self.assertIn('message:'+self.source['id']+':13',{e['ref'] for e in json.loads(saved['evidence'])})

    def test_legacy_correction_does_not_ignore_later_unread_original(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        payload=self.payload(expected='12',cursor='13');payload['messages']=[dict(id='13',time='2026-10-04T09:00:00+08:00',kind='image',sender='虚构发布者',sender_id='synthetic-a',text='[图片]',unread=True)]
        self.store.ingest(payload)
        with patch.object(agent.family_llm,'_chat_json') as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=0,failed=0,created=0))
        model.assert_not_called()

    def test_legacy_correction_model_review_remains_pending(self):
        row,key,fp,evidence=self._legacy_initial_correction();mapped=self._legacy_mapping(row,evidence)
        def uncertain(*args,**kwargs):
            value=mapped(*args,**kwargs);value['actions'][0].update(state='review',reason='实际栏目要求仍有模糊，不能判为ready。')
            return value
        with patch.object(agent.family_llm,'_chat_json',side_effect=uncertain):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=0))
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone())
            self.assertEqual((saved['state'],json.loads(saved['plan'])['school_task']['state']),('pending','review'))
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_legacy_correction_model_failure_obeys_existing_backoff_and_limit(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        with patch.object(agent.family_llm,'_chat_json',side_effect=agent.AgentError('虚构模型失败')) as model:
            for minute,used in [(0,1),(1,0),(6,1),(7,0),(17,1),(40,0)]:
                result=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=minute),1)
                self.assertEqual(result,dict(used=used,failed=used,created=0))
        self.assertEqual(model.call_count,3)
        with self.app.connect() as c:
            self.assertEqual(row,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone()))
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def _legacy_admin_rejection(self):
        self.now=dt.datetime(2026,10,4,10,tzinfo=agent.TZ);self.config()
        text='请家长后天完成学校通讯录中的紧急联系电话核对；有误就在学校通讯录中修改，无误点“已核对”。不要在班级群发布电话号码或核对截图，不用让孩子抄写。'
        payload=self.payload();payload['messages'][0].update(time='2026-10-03T16:20:00+08:00',text=text,sender='虚构发布者',sender_id='synthetic-a');self.store.ingest(payload)
        evidence=[dict(ref='message:'+self.source['id']+':11',text=text,time='2026-10-03T16:20:00+08:00',kind='text',publisher=agent._publisher(self.source['id'],payload['messages'][0]),content_incomplete=False)]
        proposal=school_proposal(title_quote=text,task_title='家长核对学校通讯录紧急联系电话',task_goal=text,due='2026-10-05',task_state='review',task_purpose='admin',evidence=[dict(ref=evidence[0]['ref'])])
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):items=agent._select('school',evidence,school_goals=[],as_of='2026-10-04')
        item=items[0];item.update(kind='school',child_id='child-1');item['plan'].pop('school_selection_receipt',None)
        item['plan']['school_task'].update(policy=9,state='review',reason='旧规则将孩子抄写误当正向学习动作。')
        key='messages:'+agent._hash([self.source['id'],['11']])[:40];fp=self.store._job(key,dict(school_learning_policy=9,messages=payload['messages']),self.now,model=True)
        self.store._save(key,fp,items,self.now,[(self.source['id'],'11')])
        with self.app.connect() as c:old=dict(c.execute('SELECT * FROM agent_items').fetchone())
        result=dict(title=proposal['task_title'],goal=text,advice='',state='ready',reason='原文为独立家长核对事务，孩子抄写被明确否定。',change='new',target_id='',purpose='admin',submission='',learning_subject='',learning_goal_id='')
        return old,key,fp,result

    def test_school_semantic_upgrade_rereads_old_admin_rejection_and_preserves_payload(self):
        old,key,fp,result=self._legacy_admin_rejection()
        with patch.object(agent.family_llm,'_chat_json',return_value=result) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=1))
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1),dict(used=0,failed=0,created=0))
        self.assertEqual(model.call_count,1)
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(old['id'],)).fetchone());plan=json.loads(saved['plan'])
            self.assertEqual((saved['state'],saved['due'],plan['school_task']['purpose']),('accepted','2026-10-05','admin'))
            self.assertEqual(plan['school_previous_policy'],old);self.assertIn('不用让孩子抄写',saved['body'])
            self.assertNotIn('school_learning',plan)
            self.assertEqual(tuple(c.execute('SELECT fingerprint,done FROM agent_jobs WHERE id=?',(key,)).fetchone()),(fp,1))

    def test_legacy_admin_upgrade_rejects_later_cancellation_without_a_model_call(self):
        old,key,fp,result=self._legacy_admin_rejection()
        payload=self.payload(expected='11',cursor='12');payload['messages']=[dict(id='12',time='2026-10-04T09:00:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='取消学校通讯录紧急联系电话核对。',unread=False)]
        # Preserve the native publisher rather than relying on its display name.
        with self.app.connect() as c:original=json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?',('11',)).fetchone()[0])
        payload['messages'][0].update(sender=original['sender'],sender_id=original['sender_id']);self.store.ingest(payload)
        with patch.object(agent.family_llm,'_chat_json',return_value=result) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=0,failed=0,created=0))
        model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual(old,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(old['id'],)).fetchone()))
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_legacy_admin_upgrade_discards_cancellation_during_model(self):
        old,key,fp,result=self._legacy_admin_rejection()
        def arrived(*args,**kwargs):
            payload=self.payload(expected='11',cursor='12');payload['messages']=[dict(id='12',time='2026-10-04T10:01:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='取消学校通讯录紧急联系电话核对。',unread=False)]
            self.store.ingest(payload);return result
        with patch.object(agent.family_llm,'_chat_json',side_effect=arrived) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=0))
        self.assertEqual(model.call_count,1)
        with self.app.connect() as c:
            self.assertEqual(old,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(old['id'],)).fetchone()))
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_legacy_admin_upgrade_rejects_an_unknown_later_publisher(self):
        old,key,fp,result=self._legacy_admin_rejection()
        payload=self.payload(expected='11',cursor='12');payload['messages']=[dict(id='12',time='2026-10-04T09:00:00+08:00',kind='text',sender='虚构发布者',text='取消学校通讯录紧急联系电话核对。',unread=False)]
        self.store.ingest(payload)
        with patch.object(agent.family_llm,'_chat_json',return_value=result) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=0,failed=0,created=0))
        model.assert_not_called()
        with self.app.connect() as c:self.assertEqual(old,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(old['id'],)).fetchone()))

    def test_legacy_admin_upgrade_rechecks_after_save_before_acceptance(self):
        old,key,fp,result=self._legacy_admin_rejection();accept=agent._accept_school_reading
        def arrived(app,store,row,evidence,now,**kwargs):
            payload=self.payload(expected='11',cursor='12');payload['messages']=[dict(id='12',time='2026-10-04T10:01:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='取消学校通讯录紧急联系电话核对。',unread=False)]
            self.store.ingest(payload);return accept(app,store,row,evidence,now,**kwargs)
        with patch.object(agent.family_llm,'_chat_json',return_value=result),patch.object(agent,'_accept_school_reading',side_effect=arrived):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=0))
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(old['id'],)).fetchone());plan=json.loads(saved['plan'])
            self.assertEqual((saved['state'],plan['school_task']['state']),('pending','review'))
            self.assertEqual(plan['school_previous_policy'],old);self.assertIn('后发变化',plan['school_task']['reason'])
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_legacy_admin_scope_rejects_a_mixed_global_instruction_in_another_named_correction(self):
        old,key,fp,result=self._legacy_admin_rejection()
        original='明天完成两项。第一项朗读课文。第二项：完成《桥的观察单》，A、B、C三栏都要做。'
        for ending in ('观察单，所有学校事务无需完成','观察单所有学校事务无需完成'):
            with self.store._db() as c:
                c.execute('SAVEPOINT mixed_scope')
                values=[dict(id='10',time='2026-10-03T16:10:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text=original,unread=False),
                    json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?',('11',)).fetchone()[0]),
                    dict(id='12',time='2026-10-04T08:05:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='更正10月3日16:10发布的第二项《桥的观察单》：A、B栏仍必做；C栏改为选做，不做C栏也算完成'+ending+'。其余要求和原期限不变。',unread=False)]
                c.execute('DELETE FROM agent_messages')
                for value in values:c.execute('INSERT INTO agent_messages(source_id,id,payload,processed) VALUES(?,?,?,1)',(self.source['id'],value['id'],agent._json(value)))
                new_key='messages:'+agent._hash([self.source['id'],[v['id'] for v in values]])[:40];new_fp=agent._hash(dict(school_learning_policy=9,messages=values))
                c.execute('UPDATE agent_jobs SET id=?,fingerprint=? WHERE id=?',(new_key,new_fp,key))
                changed=dict(old,id='agent-'+agent._hash([new_key,new_fp,0])[:32],job_id=new_key)
                evidence,_=agent._school_material(self.store,c,changed)
                self.assertIsNone(agent._school_legacy_policy_scope(self.store,c,changed,evidence))
                c.execute('ROLLBACK TO mixed_scope');c.execute('RELEASE mixed_scope')

    def test_legacy_correction_does_not_ignore_an_ambiguous_number_only_supplement(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        payload=self.payload(expected='12',cursor='13');payload['messages']=[dict(id='13',time='2026-10-04T09:00:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text='补发第二项：A栏填写两种方法并写单位。',unread=False)]
        self.store.ingest(payload)
        with patch.object(agent.family_llm,'_chat_json',side_effect=self._legacy_mapping(row,evidence)) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=0,failed=0,created=0))
        model.assert_not_called()
        with self.app.connect() as c:self.assertEqual(row,dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone()))

    def test_legacy_correction_does_not_recover_an_ambiguous_initial_batch(self):
        row,key,fp,evidence=self._legacy_initial_correction(duplicate=True)
        with self.store._db() as c:self.assertIsNone(agent._school_legacy_batch_correction(self.store,c,row,evidence))

    def test_legacy_correction_retains_edits_decisions_and_dependencies(self):
        row,key,fp,evidence=self._legacy_initial_correction()
        with self.store._db() as c:
            self.assertIsNotNone(agent._school_legacy_batch_correction(self.store,c,row,evidence))
            for changed in (dict(row,state='accepted'),dict(row,state='dismissed'),dict(row,record_id=99),dict(row,task_id='saved-task'),
                    dict(row,body=row['body']+'家长补充'),dict(row,updated=self.now.replace(minute=1).isoformat()),
                    dict(row,plan=agent._json(dict(json.loads(row['plan']),approved=dict(title='家长明确安排')))),
                    dict(row,plan=agent._json(dict(json.loads(row['plan']),school_original_action=dict(identity='already-mapped'))))):
                self.assertIsNone(agent._school_legacy_batch_correction(self.store,c,changed,evidence))
            c.execute('SAVEPOINT invalid_receipt')
            c.execute('UPDATE agent_jobs SET fingerprint=? WHERE id=?',('unknown',key))
            self.assertIsNone(agent._school_legacy_batch_correction(self.store,c,row,evidence))
            c.execute('ROLLBACK TO invalid_receipt');c.execute('RELEASE invalid_receipt')
            c.execute('SAVEPOINT hidden_task')
            fallback='AGENT-'+agent._hash(row['id'])[:24]
            c.execute('INSERT INTO manual_tasks(id,child,title,due,action,source,original_status) VALUES(?,?,?,?,?,?,?)',
                (fallback,'示例甲','家长已有独立事项','2026-10-04','保留家长内容','家长手记','待跟进'))
            self.assertIsNone(agent._school_legacy_batch_correction(self.store,c,row,evidence))
            c.execute('ROLLBACK TO hidden_task');c.execute('RELEASE hidden_task')

    def test_initial_school_batch_saves_immutable_generated_correction_proof(self):
        self.now=dt.datetime(2026,10,4,10,tzinfo=agent.TZ)
        self.config()
        texts=['明天完成两项语文要求。第一项朗读课文两遍，不用录音。第二项：完成《桥的观察单》，A、B、C三栏都要做，不打印或上传。',
               '更正10月3日16:10发布的第二项《桥的观察单》：A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。其余要求和原期限不变。']
        payload=self.payload(cursor='12')
        payload['messages']=[dict(id=str(11+i),time=['2026-10-03T16:10:00+08:00','2026-10-04T08:05:00+08:00'][i],
            kind='text',sender='虚构发布者',sender_id='synthetic-a',text=text,unread=False) for i,text in enumerate(texts)]
        self.store.ingest(payload)
        with self.app.connect() as c:values=[json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
        evidence=[dict(ref='message:'+self.source['id']+':'+v['id'],text=v['text'],time=v['time'],kind=v['kind'],
            publisher=agent._publisher(self.source['id'],v),content_incomplete=False) for v in values]
        proposal=school_proposal(title_quote=texts[0],task_title='语文：完成《桥的观察单》',task_goal='完成《桥的观察单》，A、B必做，C选做。',
            due='2026-10-04',task_state='ready',task_change='update',task_purpose='learning',learning_subject='语文',
            evidence=[dict(ref=e['ref']) for e in evidence])
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-04')
        self.assertEqual(items[0]['plan']['school_task']['change'],'update')
        for item in items:item.update(child_id='child-1',kind='school')
        key='messages:'+agent._hash([self.source['id'],[v['id'] for v in values]])[:40]
        fp=self.store._job(key,dict(school_learning_policy=8,messages=values),self.now,model=True)
        self.store._save(key,fp,items,self.now,[(self.source['id'],v['id']) for v in values],school_context=(self.source,values))
        with self.app.connect() as c:row=dict(c.execute('SELECT * FROM agent_items').fetchone())
        plan=json.loads(row['plan'])
        self.assertEqual((plan['school_task']['change'],plan['school_task']['state']),('new','review'))
        self.assertEqual(plan['school_first_batch_correction']['original_text'],texts[0])
        self.assertEqual(plan['school_generated_snapshot'],agent._school_generated_snapshot(row))
        self.assertNotEqual(plan['school_generated_snapshot'],agent._school_generated_snapshot(dict(row,body=row['body']+'家长补充。')))
        self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0),dict(used=0,failed=0,created=0))
        self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),0),dict(used=0,failed=0,created=0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0],2)
        with self.store._db() as c:
            current,_=agent._school_material(self.store,c,row)
            self.assertEqual(agent._school_untouched_batch_correction(self.store,c,row,current),plan['school_first_batch_correction'])
            self.assertIsNone(agent._school_untouched_batch_correction(self.store,c,dict(row,body=row['body']+'家长补充'),current))
            self.assertIsNone(agent._school_untouched_batch_correction(self.store,c,dict(row,state='accepted'),current))
        def original_result(messages,schema,*args,**kwargs):
            context=json.loads(messages[-1]['content'])
            self.assertEqual(context['verified_first_batch_correction'],plan['school_first_batch_correction'])
            self.assertIn('condition_changes',schema['properties']['actions']['items']['required'])
            parts=context['original_parts']
            changes=[dict(old_part=parts[0]['id'],old_text='A、B、C三栏都要做',new_part=parts[1]['id'],
                          new_text='A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。')]
            return dict(actions=[dict(title='语文：完成《桥的观察单》',goal='完成《桥的观察单》。',advice='',
                state='ready',reason='同批完整原要求及更正条件已对应。',purpose='learning',submission='',
                change='new',target_id='',learning_subject='语文',learning_goal_id='',due='2026-10-04',
                existing_item_id=row['id'],basis=[dict(part=p['id'],text=p['text']) for p in parts],condition_changes=changes)])
        with patch.object(agent.family_llm,'_chat_json',side_effect=original_result) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=0,created=1))
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1),dict(used=0,failed=0,created=0))
        self.assertEqual(model.call_count,1)
        with self.app.connect() as c:
            saved=dict(c.execute('SELECT * FROM agent_items').fetchone())
            self.assertEqual((saved['id'],saved['state'],saved['due']),(row['id'],'accepted','2026-10-04'))
            self.assertEqual(json.loads(saved['plan'])['school_generated_snapshot'],plan['school_generated_snapshot'])
            self.assertNotIn('A、B、C三栏都要做',saved['body'])
            self.assertIn('C栏改为选做',saved['body'])
            self.assertIn('不做C栏也算完成观察单',saved['body'])
            self.assertNotIn('朗读课文',saved['body'])
            self.assertIn('不打印或上传',saved['body'])
            action=json.loads(saved['plan'])['school_original_action']
            self.assertEqual(action['basis_projection'][0]['original']['quote'],texts[0])
            self.assertEqual(action['basis_projection'][0]['scoped']['quote'],plan['school_first_batch_correction']['action_text'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0],2)

        import family_agenda
        task,=self.app.tasks();self.assertEqual(task['agenda']['published_at'],'2026-10-03T16:10:00+08:00')
        self.assertEqual(task['agenda']['due_on'],'2026-10-04')
        refs=[q['ref'] for q in json.loads(saved['evidence'])]
        with self.app.connect() as c:
            before='\n'.join(c.iterdump())
            self.assertEqual(agent.school_original_publication_ref(self.store,c,saved),refs[0])
            self.assertEqual(agent.school_original_publication_ref(self.store,c,dict(saved,child_id='child-2')),'')
            self.assertEqual(agent.school_original_publication_ref(self.store,c,dict(saved,state='pending')),'')
            unproven=family_agenda.metadata(self.app,c,'child-1',task['title'],task['due'],list(reversed(refs)))
            self.assertEqual(unproven['published_on'],'','unrelated different days still cannot be collapsed to the earliest date')
            explicit=family_agenda.metadata(self.app,c,'child-1',task['title'],task['due'],refs,
                dict(category='homework',published_on='2026-10-02'),publication_ref=refs[0])
            self.assertEqual(explicit['published_on'],'2026-10-02','explicit parent dates retain priority')
            self.assertEqual(explicit['published_at'],'')
            self.assertEqual(before,'\n'.join(c.iterdump()))
            c.execute('SAVEPOINT stale_publication')
            payload=json.loads(c.execute('SELECT payload FROM agent_messages WHERE id=?',('11',)).fetchone()[0])
            payload['time']='2026-10-03T16:11:00+08:00'
            c.execute('UPDATE agent_messages SET payload=? WHERE id=?',(json.dumps(payload),'11'))
            self.assertEqual(agent.school_original_publication_ref(self.store,c,saved),'','a changed original invalidates the display proof')
            c.execute('ROLLBACK TO stale_publication');c.execute('RELEASE stale_publication')
            self.assertEqual(before,'\n'.join(c.iterdump()))

    def _school_rejects_first_batch_conversion(self,*,duplicate=False,wrong_date=False,naive=False):
        self.now=dt.datetime(2026,10,4,10,tzinfo=agent.TZ);self.config()
        original=('10月5日完成第二项：《桥的观察单》，A、B、C三栏都要做；10月6日交回活动回执。' if wrong_date
                  else '明天完成第二项：《桥的观察单》，A、B、C三栏都要做。')
        correction='更正10月3日16:10发布的第二项《桥的观察单》：A、B栏仍必做；C栏改为选做，原期限不变。'
        payload=self.payload(cursor='13' if duplicate else '12')
        payload['messages']=[dict(id='11',time='2026-10-03T16:10:00' if naive else '2026-10-03T16:10:00+08:00',
            kind='text',sender='虚构发布者',sender_id='synthetic-a',text=original,unread=False),
            dict(id='12',time='2026-10-04T08:05:00+08:00',kind='text',sender='虚构发布者',sender_id='synthetic-a',text=correction,unread=False)]
        if duplicate:payload['messages'].append(dict(payload['messages'][0],id='13',time='2026-10-03T16:10:30+08:00'))
        if naive:
            with self.assertRaises(agent.AgentError):self.store.ingest(payload)
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            return
        self.store.ingest(payload)
        with self.app.connect() as c:values=[json.loads(r[0]) for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')]
        evidence=[dict(ref='message:'+self.source['id']+':'+v['id'],text=v['text'],time=v['time'],kind=v['kind'],
            publisher=agent._publisher(self.source['id'],v),content_incomplete=False) for v in values[:2]]
        proposal=school_proposal(title_quote=original[:120],task_title='语文：完成《桥的观察单》',task_goal='完成《桥的观察单》。',
            due='2026-10-06' if wrong_date else '2026-10-04',task_state='ready',task_change='update',
            task_purpose='learning',learning_subject='语文',evidence=[dict(ref=e['ref']) for e in evidence])
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-04')
        for item in items:item.update(child_id='child-1',kind='school')
        key='messages:'+agent._hash([self.source['id'],[v['id'] for v in values]])[:40]
        fp=self.store._job(key,dict(school_learning_policy=8,messages=values),self.now,model=True)
        self.store._save(key,fp,items,self.now,[(self.source['id'],v['id']) for v in values],school_context=(self.source,values))
        with self.app.connect() as c:
            row=dict(c.execute('SELECT * FROM agent_items').fetchone())
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
        plan=json.loads(row['plan']);self.assertNotIn('school_first_batch_correction',plan)
        self.assertEqual((plan['school_task']['change'],plan['school_task']['state']),('update','review'))

    def test_first_batch_save_does_not_borrow_another_action_date(self):
        self._school_rejects_first_batch_conversion(wrong_date=True)

    def test_first_batch_save_requires_unique_original_in_the_whole_batch(self):
        self._school_rejects_first_batch_conversion(duplicate=True)

    def test_first_batch_save_does_not_infer_timezone(self):
        self._school_rejects_first_batch_conversion(naive=True)

    def _first_batch_condition_fixture(self):
        original='明天完成两项语文要求。第一项朗读课文。第二项：完成《桥的观察单》，A、B、C三栏都要做，不照抄示例，不打印或上传。'
        change='更正10月3日16:10发布的第二项《桥的观察单》：A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。其余要求和原期限不变。'
        requirements='A栏：选出两个描写桥的词语，写在语文本上。B栏：用自己的话写三句完整的话，分别说明桥的位置、外形和用途。C栏：用自己的话补写一句喜欢桥的理由。不得照抄参考句。'
        evidence=[dict(ref='message:synthetic:m1',text=original,time='2026-10-03T16:10:00+08:00',kind='text',publisher='publisher:a',content_incomplete=False),
                  dict(ref='message:synthetic:m4',text=change,time='2026-10-04T08:05:00+08:00',kind='text',publisher='publisher:a',content_incomplete=False)]
        proof=agent._school_first_batch_correction(dict(change='update',target_id='',title='完成《桥的观察单》'),evidence)
        parts=[dict(id=e['ref'],ref=e['ref'],text=e['text'],upload_ids=[],pages=[]) for e in evidence]
        parts.append(dict(id='requirement:docx',ref='message:synthetic:m2',text=requirements,upload_ids=['a'*32],pages=[],requirement=True))
        anchors=[dict(ref=p['ref'],upload_ids=p['upload_ids'],pages=p['pages'],quote=p['text']) for p in parts]
        anchors[0]['quote']=proof['action_text']
        changes=[dict(old_part=evidence[0]['ref'],old_text='A、B、C三栏都要做',new_part=evidence[1]['ref'],new_text='A、B栏仍必做；C栏改为选做')]
        return parts,anchors,changes,proof

    def test_effective_column_conditions_keep_every_output_word_and_original(self):
        import copy
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        before=copy.deepcopy((parts,anchors,changes,proof))
        texts=agent._school_effective_conditions(parts,anchors,changes,proof)
        self.assertEqual((parts,anchors,changes,proof),before)
        joined='\n'.join(texts)
        self.assertNotIn('A、B、C三栏都要做',joined)
        for text in ['两个描写桥的词语','三句完整的话','位置、外形和用途','一句喜欢桥的理由',
                     'C栏（选做时）：用自己的话','不做C栏也算完成观察单','不得照抄参考句','不打印或上传']:
            self.assertIn(text,joined)
        value=dict(title='完成《桥的观察单》',goal='模型摘要',submission='')
        result=agent._school_requirement_goal(value,texts)
        self.assertIn('A、B栏必做；C栏选做',result['title'])
        self.assertEqual(agent._school_requirement_goal(result,texts),result)

    def test_effective_conditions_apply_only_to_the_anchor_containing_the_changed_span(self):
        import copy
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        date=dict(anchors[0],quote=proof['shared_date_text']);quotes=[date]+anchors
        before=copy.deepcopy((parts,quotes,changes,proof))
        texts=agent._school_effective_conditions(parts,quotes,changes,proof)
        self.assertEqual((parts,quotes,changes,proof),before)
        self.assertEqual(texts[1].count('A、B栏仍必做；C栏改为选做'),1)
        self.assertIn(proof['shared_date_text'],texts)
        partial=copy.deepcopy(quotes);partial[1]['quote']=proof['action_text'].split('C三栏都要做')[0]+'C'
        with self.assertRaises(agent.AgentError):agent._school_effective_conditions(parts,partial,changes,proof)
        with self.assertRaises(agent.AgentError):agent._school_effective_conditions(parts,quotes+[dict(anchors[0])],changes,proof)

    def test_admin_body_keeps_the_explicit_native_parent_actor_when_summary_omits_it(self):
        value=dict(title='核对学校通讯录',goal='在学校通讯录中核对紧急联系电话；有误修改，无误点已核对。',advice='',state='ready',reason='',purpose='admin',submission='',change='new',target_id='')
        evidence=[dict(ref='message:synthetic:m3',kind='text',time='2026-10-03T16:20:00+08:00',publisher='publisher:a',unread=False,
            text='请家长后天完成学校通讯录中的紧急联系电话核对；有误就在学校通讯录中修改，无误点“已核对”。不用让孩子抄写。')]
        brief=agent._school_brief(value,evidence=evidence)
        self.assertEqual(brief['goal'],'家长：'+value['goal']);self.assertEqual(brief['purpose'],'admin')
        already=dict(value,goal='家长核对学校通讯录，信息有误时修改。')
        self.assertEqual(agent._school_brief(already,evidence=evidence)['goal'],already['goal'])
        for text in ('不用请家长核对学校通讯录。','有人转述“请家长核对学校通讯录”。'):
            self.assertEqual(agent._school_brief(value,evidence=[dict(evidence[0],text=text)])['goal'],value['goal'])
        self.assertEqual(agent._school_brief(value,evidence=[dict(evidence[0],unread=True)])['goal'],value['goal'])

    def _effective_instruction_fixture(self):
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        parts[-1]['text']='完成《桥的观察单》：'+parts[-1]['text']
        anchors[-1]['quote']=parts[-1]['text']
        changes[0]['new_text']='A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单'
        caption=dict(id='message:synthetic:m2',ref='message:synthetic:m2',upload_ids=[],pages=[],
            text='补发《桥的观察单》。本条附件只对应16:10通知的第二项观察单，不属于第一项朗读材料。')
        parts.insert(1,caption)
        anchors.insert(1,dict(ref=caption['ref'],upload_ids=[],pages=[],quote=caption['text']))
        return parts,anchors,changes,proof

    def test_effective_instructions_separate_routing_and_preserve_current_standards(self):
        import copy
        parts,anchors,changes,proof=self._effective_instruction_fixture()
        before=copy.deepcopy((parts,anchors,changes,proof))
        goal=agent._school_effective_instructions(parts,anchors,changes,proof)[0]
        self.assertEqual((parts,anchors,changes,proof),before)
        for text in ['补发','本条附件只对应','更正10月3日16:10','第二项：','其余要求和原期限不变','A、B、C三栏都要做']:
            self.assertNotIn(text,goal)
        self.assertEqual(goal.count('A、B栏仍必做'),1)
        self.assertEqual(goal.count('C栏改为选做，不做C栏也算完成观察单'),1)
        for text in ['两个描写桥的词语','语文本','三句完整的话','位置、外形和用途','一句喜欢桥的理由',
                     'C栏（选做时）：用自己的话','不得照抄参考句','不照抄示例','不打印或上传']:
            self.assertIn(text,goal)
        self.assertEqual(goal.count('完成《桥的观察单》。'),1)

    def test_effective_instructions_resolve_shared_date_for_only_this_action(self):
        import copy
        parts,anchors,changes,proof=self._effective_instruction_fixture()
        anchors.insert(0,dict(anchors[0],quote=proof['shared_date_text']))
        before=copy.deepcopy((parts,anchors,changes,proof))
        goal=agent._school_effective_instructions(parts,anchors,changes,proof)[0]
        self.assertEqual((parts,anchors,changes,proof),before)
        self.assertTrue(goal.startswith('2026-10-04完成《桥的观察单》。'))
        self.assertNotIn('明天完成两项',goal)
        self.assertEqual(goal.count('完成《桥的观察单》。'),1)
        for text in ['两个描写桥的词语','三句完整的话','一句喜欢桥的理由','C栏（选做时）','不做C栏也算完成观察单']:
            self.assertIn(text,goal)

    def test_effective_instructions_keep_business_residuals_and_other_file_pointers(self):
        parts,anchors,changes,proof=self._effective_instruction_fixture()
        parts[1]['text']+='请周五交回并签字。'
        anchors[1]['quote']=parts[1]['text']
        parts[2]['text']+='A栏仍须用两种方法。按稍后另一份附件要求在答题卡上作答。按稍后附件的栏目要求在答题卡上作答。'
        proof['correction_text']=parts[2]['text'];anchors[2]['quote']=parts[2]['text']
        goal=agent._school_effective_instructions(parts,anchors,changes,proof)[0]
        for text in ['请周五交回并签字','A栏仍须用两种方法','按稍后另一份附件要求在答题卡上作答','按稍后附件的栏目要求在答题卡上作答']:
            self.assertIn(text,goal)
        # An unread caption and a missing unique inherited deadline remain visible.
        goal=agent._school_effective_instructions(parts,anchors[:-1],changes,dict(proof,shared_date_text='',
            action_text=proof['action_text'].replace('明天','')))[0]
        self.assertIn('补发《桥的观察单》',goal)
        self.assertIn('本条附件只对应',goal)
        self.assertIn('其余要求和原期限不变',goal)

    def test_effective_instructions_do_not_deduplicate_full_standards_across_files(self):
        import copy
        parts,anchors,changes,proof=self._effective_instruction_fixture()
        other=copy.deepcopy(parts[-1]);other.update(id='requirement:second',upload_ids=['b'*32])
        parts.append(other);anchors.append(dict(ref=other['ref'],upload_ids=other['upload_ids'],pages=[],quote=other['text']))
        texts=agent._school_effective_instructions(parts,anchors,changes,proof)
        goal=agent._school_requirement_goal(dict(title='完成《桥的观察单》',goal='',submission=''),texts)['goal']
        self.assertEqual(goal.count('两个描写桥的词语'),2)
        self.assertEqual(goal.count('三句完整的话'),2)

    def test_effective_instructions_keep_equal_native_words_under_different_columns(self):
        parts,anchors,changes,proof=self._effective_instruction_fixture()
        extra='A栏补充要求：\n用两种方法。\nB栏补充要求：\n用两种方法。'
        parts[0]['text']+=extra;proof['original_text']=parts[0]['text'];proof['action_text']+=extra
        anchors[0]['quote']=proof['action_text']
        goal=agent._school_effective_instructions(parts,anchors,changes,proof)[0]
        self.assertEqual(goal.count('用两种方法'),2)
        self.assertIn('A栏补充要求',goal)
        self.assertIn('B栏补充要求',goal)
        self.assertEqual(goal.count('C栏改为选做，不做C栏也算完成观察单'),1)

    def test_instruction_layout_keeps_quoted_punctuation_and_decimal_units(self):
        text='用“先测量；再记录。最后检查”的方法，结果写成1.25厘米。不得照抄。'
        self.assertEqual(agent._school_instruction_clauses(text),[
            '用“先测量；再记录。最后检查”的方法，结果写成1.25厘米。','不得照抄。'])
        text='请抄写"先测量；再记录。"，保留1.25厘米。不得照抄参考。'
        self.assertEqual(agent._school_instruction_clauses(text),[
            '请抄写"先测量；再记录。"，保留1.25厘米。','不得照抄参考。'])

    def test_first_batch_scope_projects_only_a_complete_proven_native_action(self):
        import copy
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        raw=copy.deepcopy(anchors);raw[0]['quote']=parts[0]['text']
        before=copy.deepcopy((parts,raw,proof))
        scoped,projection=agent._school_scoped_correction_anchors(parts,raw,proof)
        self.assertEqual(scoped,anchors)
        self.assertEqual(projection,[dict(original=raw[0],scoped=anchors[0])])
        self.assertEqual((parts,raw,proof),before)
        self.assertEqual(agent._school_scoped_correction_anchors(parts,anchors,proof),(anchors,[]))
        cases=[]
        for quote in ['明天完成两项语文要求。第一项朗读课文。',proof['action_text'].split('，')[0],
                      parts[0]['text'].replace('不打印或上传。','')]:
            altered=copy.deepcopy(raw);altered[0]['quote']=quote;cases.append((parts,altered,proof))
        for field in ['requirement','background_only']:
            altered=copy.deepcopy(parts);altered[0][field]=True;cases.append((altered,raw,proof))
        altered=copy.deepcopy(parts);altered[0]['text']+='补充说明';cases.append((altered,raw,proof))
        altered=copy.deepcopy(proof);altered['action_text']='第一项朗读课文。';cases.append((parts,raw,altered))
        altered=copy.deepcopy(raw);altered[0]['upload_ids']=['a'*32];cases.append((parts,altered,proof))
        cases.append((parts,raw+[copy.deepcopy(raw[0])],proof))
        for sources,quotes,basis in cases:
            with self.subTest(quotes=quotes,basis=basis):
                with self.assertRaises(agent.AgentError):agent._school_scoped_correction_anchors(sources,quotes,basis)

    def test_effective_conditions_allow_only_matching_optional_completion_equivalence(self):
        import copy
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        for obj in ['观察单','桥的观察单','《桥的观察单》']:
            literal='A、B栏仍必做；C栏改为选做，不做C栏也算完成'+obj+'。'
            sources=copy.deepcopy(parts);sources[1]['text']=sources[1]['text'].replace(
                'A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。',literal)
            quotes=copy.deepcopy(anchors);quotes[1]['quote']=sources[1]['text']
            basis=dict(proof,correction_text=sources[1]['text'])
            texts=agent._school_effective_conditions(sources,quotes,[dict(changes[0],new_text=literal)],basis)
            joined='\n'.join(texts)
            self.assertIn(literal.rstrip('。'),joined)
            self.assertIn('C栏（选做时）：用自己的话',joined)
            self.assertNotIn('。，',joined)
        for ending in ['不做A栏也算完成观察单','不做C栏也算完成朗读课文','不做C栏也算完成全班作业',
                       '不做C栏也算完成观察单，明天交回','不做C栏也算完成观察单，B栏只写一句',
                       '不做C栏也算完成观察单，不用做A栏','不做C栏也算完成所有作业']:
            literal='A、B栏仍必做；C栏改为选做，'+ending+'。'
            sources=copy.deepcopy(parts);sources[1]['text']=sources[1]['text'].replace(
                'A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。',literal)
            quotes=copy.deepcopy(anchors);quotes[1]['quote']=sources[1]['text']
            with self.subTest(ending=ending):
                with self.assertRaises(agent.AgentError):agent._school_effective_conditions(
                    sources,quotes,[dict(changes[0],new_text=literal)],dict(proof,correction_text=sources[1]['text']))

    def test_optional_completion_short_name_cannot_collide_with_another_named_action(self):
        import copy
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        for other in ['《河的观察单》','《观察单》']:
            sources=copy.deepcopy(parts);sources[0]['text']=sources[0]['text'].replace('第一项朗读课文。','第一项：完成'+other+'，写三句话。')
            basis=dict(proof,original_text=sources[0]['text'])
            for name in ['观察单','桥的观察单','《桥的观察单》']:
                literal='A、B栏仍必做；C栏改为选做，不做C栏也算完成'+name+'。'
                sources[1]['text']=proof['correction_text'].replace(
                    'A、B栏仍必做；C栏改为选做，不做C栏也算完成观察单。',literal)
                basis['correction_text']=sources[1]['text'];quotes=copy.deepcopy(anchors);quotes[1]['quote']=sources[1]['text']
                mapping=[dict(changes[0],new_text=literal)]
                with self.subTest(other=other,name=name):
                    if name=='观察单':
                        with self.assertRaises(agent.AgentError):agent._school_effective_conditions(sources,quotes,mapping,basis)
                    else:self.assertTrue(agent._school_effective_conditions(sources,quotes,mapping,basis))

    def test_action_reading_uses_complete_requirements_without_changing_collection_flags(self):
        import copy
        ref='message:synthetic:m2';requirement='完成《桥的观察单》：A栏写两个词语。B栏写三句完整的话。'
        raw=[dict(ref=ref,text='补发《桥的观察单》。',kind='text',unread=True,content_incomplete=True)]
        quotes=[dict(ref=ref,quote=raw[0]['text'],upload_ids=[],pages=[]),
                dict(ref=ref,quote=requirement,upload_ids=['a'*32],pages=[])]
        requirements=[dict(ref=ref,text=requirement,upload_ids=['a'*32])]
        before=copy.deepcopy((raw,quotes,requirements))
        read=agent._school_action_read_evidence(raw,quotes,requirements)
        self.assertEqual((read[0]['unread'],read[0]['content_incomplete']),(False,False))
        self.assertIn(requirement,read[0]['text'])
        self.assertEqual((raw,quotes,requirements),before)
        for altered in [[],requirements*2,[dict(requirements[0],text='A栏写两个词语。')],
                        [dict(requirements[0],ref='message:synthetic:other')],
                        [dict(requirements[0],upload_ids=['b'*32])]]:
            self.assertEqual(agent._school_action_read_evidence(raw,quotes,altered),raw)
        changed=copy.deepcopy(quotes);changed[-1]['pages']=[2]
        self.assertEqual(agent._school_action_read_evidence(raw,changed,requirements),raw)
        fragment=[dict(raw[0],kind='qq_window_fragment')]
        self.assertEqual(agent._school_action_read_evidence(fragment,quotes,requirements),fragment)
        material=dict(fingerprint='synthetic',uncertainties=['B栏文字模糊'],complete_refs=[],refs=[ref])
        value=dict(title='完成观察单',goal=requirement,state='ready',purpose='learning',change='new',target_id='')
        self.assertEqual(agent._school_brief(value,evidence=read,material=material)['state'],'review')

    def test_effective_column_changes_reject_missing_ambiguous_or_standard_replacements(self):
        import copy
        parts,anchors,changes,proof=self._first_batch_condition_fixture()
        cases=[]
        cases.append((parts,anchors,[],proof))
        cases.append((parts,anchors,changes,None))
        mixed=copy.deepcopy(anchors);mixed[0]['quote']=parts[0]['text']
        cases.append((parts,mixed,changes,proof))
        cases.append((parts,anchors,[dict(changes[0],old_text=parts[0]['text'])],proof))
        cases.append((parts,anchors,[dict(changes[0],new_text='A、B栏仍必做；C栏改为选做，不做A栏也算完成观察单')],proof))
        cases.append((parts,anchors,[dict(changes[0],new_text='C栏改为选做')],proof))
        cases.append((parts,anchors,changes*2,proof))
        cases.append((parts,anchors[1:],changes,proof))
        prefix=copy.deepcopy(anchors);prefix[1]['quote']=parts[1]['text'].split('：')[0]+'：'
        cases.append((parts,prefix,changes,proof))
        duplicate=copy.deepcopy(parts);duplicate[0]['text']+='A、B、C三栏都要做'
        cases.append((duplicate,anchors,changes,proof))
        conflicting=copy.deepcopy(parts);conflicting[-1]['text']+='C栏必做。'
        quotes=copy.deepcopy(anchors);quotes[-1]['quote']=conflicting[-1]['text']
        cases.append((conflicting,quotes,changes,proof))
        for wording in ['C栏为必做。','C栏是必做。','C栏仍必做。']:
            conflicting=copy.deepcopy(parts);conflicting[-1]['text']+=wording
            quotes=copy.deepcopy(anchors);quotes[-1]['quote']=conflicting[-1]['text']
            cases.append((conflicting,quotes,changes,proof))
        negative=copy.deepcopy(parts);negative[0]['text']=negative[0]['text'].replace('A、B、C三栏都要做','不要求A、B、C三栏都要做')
        quotes=copy.deepcopy(anchors);quotes[0]['quote']=negative[0]['text']
        cases.append((negative,quotes,changes,proof))
        missing=copy.deepcopy(parts);missing.append(dict(parts[0],id='unused-old',text='A、B、C三栏都要做'))
        cases.append((missing,anchors,[dict(changes[0],old_part='unused-old')],proof))
        for index,(sources,quotes,mapping,basis) in enumerate(cases):
            with self.subTest(index=index):
                before=copy.deepcopy((sources,quotes,mapping,basis))
                with self.assertRaises(agent.AgentError):agent._school_effective_conditions(sources,quotes,mapping,basis)
                self.assertEqual((sources,quotes,mapping,basis),before)

    def test_first_batch_action_scope_does_not_inherit_another_action_date(self):
        from family_agenda import deadlines
        obj='《桥的观察单》';ordinal='第二项'
        common='明天完成两项语文要求。第一项：朗读课文。第二项：完成'+obj+'，A、B、C三栏都要做。'
        scope=agent._school_first_batch_action_scope(common,ordinal,obj)
        self.assertEqual(deadlines(scope['action_text']+'\n'+scope['shared_date_text'],'2026-10-03'),{'2026-10-04'})
        self.assertNotIn('朗读课文',scope['action_text'])
        own='第一项：明天朗读课文。第二项：完成'+obj+'，A、B、C三栏都要做。'
        scope=agent._school_first_batch_action_scope(own,ordinal,obj)
        self.assertEqual(scope['shared_date_text'],'')
        self.assertEqual(deadlines(scope['action_text'],'2026-10-03'),set())
        direct='10月5日完成第二项：'+obj+'。第三项：10月6日交回回执。'
        scope=agent._school_first_batch_action_scope(direct,ordinal,obj)
        self.assertEqual(deadlines(scope['action_text'],'2026-10-03'),{'2026-10-05'})
        self.assertNotIn('交回回执',scope['action_text'])
        self.assertIsNone(agent._school_first_batch_action_scope(own,'第三项',obj))
        for prefix in ['明天完成两项中的朗读，观察单不设期限。','明天完成两项但只检查朗读。',
                       '明天完成三项语文要求。']:
            scope=agent._school_first_batch_action_scope(prefix+own,ordinal,obj)
            self.assertEqual(scope['shared_date_text'],'')
            self.assertEqual(deadlines(scope['action_text'],'2026-10-03'),set())

    def _school_batch_failure_recovers(self, failure):
        payload=self.payload(cursor='16')
        payload['messages']=[dict(id=str(i),time=self.now.isoformat(),kind='text',sender='示例发布者',
            text='英语：请明天完成独立练习'+str(i)+'。',unread=False) for i in range(11,17)]
        self.store.ingest(payload)
        proposals=[school_proposal(title_quote='英语',evidence=[dict(ref='message:'+self.source['id']+':'+m['id'])],
            due='2026-02-11',task_title='英语：独立练习'+m['id'],task_goal='完成独立练习'+m['id']+'。',
            task_state='ready',task_reason='明确的新要求。',task_purpose='learning') for m in payload['messages']]
        bad=proposals[:-1] if failure=='omitted' else [] if failure=='empty' else [dict(p) for p in proposals]
        if failure=='missing_field':bad[0].pop('task_purpose')
        with patch.object(agent.family_llm,'_chat_json',side_effect=[dict(proposals=bad),dict(proposals=proposals)]) as model:
            first=agent.run_once(self.app,self.now)
            self.assertEqual((first['failed'],first['processed'],first['created']),(1,0,0))
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
                job=c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()
                self.assertEqual((job['attempts'],job['done']),(1,0));self.assertTrue(job['error'])
                self.assertEqual(job['next_try'],(self.now+dt.timedelta(minutes=5)).isoformat())
                self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0],'16')
                self.assertEqual([json.loads(r[0])['text'] for r in c.execute('SELECT payload FROM agent_messages ORDER BY rowid')],
                    [m['text'] for m in payload['messages']])
            agent.run_once(self.app,self.now+dt.timedelta(minutes=1));self.assertEqual(model.call_count,1)
            recovered=agent.run_once(self.app,self.now+dt.timedelta(minutes=6))
            self.assertEqual((recovered['failed'],recovered['processed']),(0,6));self.assertEqual(model.call_count,2)
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0],6)
                self.assertEqual(tuple(c.execute("SELECT attempts,done,error,next_try FROM agent_jobs WHERE id LIKE 'messages:%'").fetchone()),(2,1,'',''))
                items=[tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')]
                tasks=[tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')]
                self.assertEqual(len(items),6);self.assertEqual(len(tasks),6)
                saved={r['title']:(r['body'],r['due'],r['state']) for r in c.execute('SELECT * FROM agent_items')}
                self.assertEqual(saved,{p['task_title']:(p['task_goal'],p['due'],'accepted') for p in proposals})
            replay=agent.run_once(self.app,self.now+dt.timedelta(minutes=7))
            self.assertEqual((replay['processed'],replay['created']),(0,0));self.assertEqual(model.call_count,2)
            with self.app.connect() as c:
                self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM agent_items ORDER BY id')],items)
                self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY id')],tasks)

    def test_school_omitted_message_fails_whole_batch_then_recovers_idempotently(self):
        self._school_batch_failure_recovers('omitted')

    def test_school_empty_result_fails_whole_batch_then_recovers_idempotently(self):
        self._school_batch_failure_recovers('empty')

    def test_school_missing_field_fails_whole_batch_then_recovers_idempotently(self):
        self._school_batch_failure_recovers('missing_field')

    def test_school_routing_rejects_silently_omitted_original_messages(self):
        evidence=[];proposals=[]
        for i in range(1,7):
            ref='message:synthetic:'+str(i)
            evidence.append(dict(ref=ref,text='英语：完成虚构独立练习'+str(i)+'。',time=self.now.isoformat(),content_incomplete=False))
            proposals.append(dict(title_quote='英语',focus='school',due='',evidence=[dict(ref=ref)],
                learning_subject='英语',learning_goal_id='',task_title='英语：独立练习'+str(i),
                task_goal='完成虚构独立练习'+str(i)+'。',task_advice='',task_state='ready',task_reason='原文要求明确。',
                task_change='new',task_target_id='',task_purpose='learning',task_submission=''))
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals[:5])):
            with self.assertRaises(agent.AgentError):
                agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())

    def test_one_school_requirement_can_keep_six_original_messages(self):
        evidence=[dict(ref='message:synthetic:'+str(i),text='语文作业：朗读。' if i==0 else '本次朗读要求的补充说明 '+str(i),
            time=self.now.isoformat(),sender='示例语文老师',publisher='publisher:synthetic',content_incomplete=False) for i in range(6)]
        proposal=dict(title_quote='语文作业',focus='school',due='',evidence=[dict(ref=e['ref']) for e in evidence],
            learning_subject='语文',learning_goal_id='',task_title='语文：朗读',task_goal='朗读并保留补充要求。',task_advice='',
            task_state='ready',task_reason='同一次要求的补充说明。',task_change='new',task_target_id='',task_purpose='learning',task_submission='')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            items=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([e['ref'] for e in items[0]['evidence']],[e['ref'] for e in evidence])
        self.assertEqual(items[0]['plan']['school_task']['state'],'ready')
        evidence[1].update(kind='text',text='[图片原件：1份，内容未读]',content_incomplete=True)
        evidence[0]['kind']='text'
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            pending=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(pending[0]['plan']['school_task']['goal'],'朗读并保留补充要求。')
        self.assertEqual(pending[0]['plan']['school_task']['state'],'review')
        self.assertIn('已读正文要求已保留',pending[0]['plan']['school_task']['reason'])
        for e in evidence:
            e.update(source='虚构学校群',publisher='publisher:synthetic',related_messages=[x['ref'] for x in evidence],attachments=[])
        evidence[1]['attachments']=[dict(name='synthetic-reading.png',mime='image/png')]
        proposal['evidence']=[dict(ref=e['ref']) for e in evidence]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            linked=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([e['ref'] for e in linked[0]['evidence']],[e['ref'] for e in evidence])
        self.assertEqual(linked[0]['plan']['school_task']['state'],'review')
        evidence[1]['attachments']=[]  # Bytes can arrive after the original publication's text.
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            waiting=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([e['ref'] for e in waiting[0]['evidence']],[e['ref'] for e in evidence])
        self.assertEqual(waiting[0]['plan']['school_task']['state'],'review')
        proposal['evidence']=[dict(ref=evidence[0]['ref']),dict(ref=evidence[2]['ref'])]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            with self.assertRaises(agent.AgentError):
                agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        evidence[-1]['publisher']='publisher:other'
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            with self.assertRaises(agent.AgentError):
                agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        other=school_proposal(title_quote=evidence[-1]['text'],evidence=[dict(ref=evidence[-1]['ref'])],
            task_state='reference',task_reason='另一发布者的说明单独保留。')
        remaining=school_proposal(title_quote=evidence[1]['text'],
            evidence=[dict(ref=e['ref']) for e in evidence if e['ref'] not in {evidence[0]['ref'],evidence[2]['ref'],evidence[-1]['ref']}],
            task_reason='附件和补充内容尚待整理。')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal,remaining,other])):
            separate=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual([e['ref'] for e in separate[0]['evidence']], [evidence[0]['ref'],evidence[2]['ref']])
        self.assertEqual([e['ref'] for e in separate[-1]['evidence']],[evidence[-1]['ref']])

    def test_school_batch_does_not_split_body_and_pending_attachment_before_bytes_arrive(self):
        messages=[dict(id=str(i),time=(self.now+dt.timedelta(seconds=i)).isoformat(),kind='text',sender='示例老师',
            sender_id='20001',message_order=str(i),text='独立的虚构通知 '+str(i),unread=False) for i in range(1,73)]
        messages[5]['text']='英语：朗读课文，题目见附件。'
        messages[6].update(text='[图片原件：1份，内容未读]',unread=True)
        messages[7]['text']='以上是朗读练习的题目。'
        raw=[dict(payload=json.dumps(m)) for m in messages]
        batches=agent._school_batches('synthetic-group',raw)
        self.assertEqual([[m['id'] for m in b] for b in batches[:2]],[list(map(str,range(1,6))),list(map(str,range(6,12)))])
        self.assertEqual(len(batches),6);self.assertTrue(all(len(b)<=6 and sum(len(agent._json(m)) for m in b)<=14000 for b in batches))
        views=[dict(source_id='synthetic-group',message=m) for m in messages[5:8]]
        self.assertEqual(len(agent._publication_groups(views)),1)
        views[1]['message']=dict(views[1]['message'],sender_id='20002')
        self.assertEqual(len(agent._publication_groups(views)),3)

    def test_saved_publications_keep_publishers_originals_attachments_and_paging_without_writes(self):
        import family_media
        self.source['platform']='qq'; self.config()
        messages=[]
        for i in range(1,42):
            messages.append(dict(id=str(i),time=(self.now+dt.timedelta(seconds=i)).isoformat(),kind='text',
                sender='示例英语老师',sender_id='20001',message_order=str(i),text='英语：独立要求 '+str(i),unread=False))
        messages[0]['text']='英语：朗读课文两遍，练习题见附件。'
        messages[1].update(text='[图片原件：1份，内容未读]',unread=True)
        messages[2]['text']='以上是朗读练习的题目。'
        messages[3]['sender_id']='20002'  # Same card, different account; never merge.
        messages[5]['message_order']='8'  # Unseen stream positions cannot be called consecutive.
        for m in messages[6:8]:m.pop('sender_id')
        self.store.ingest(dict(self.payload(),messages=messages,cursor='41'))
        png=__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII=')
        upload=self.app.save_upload(io.BytesIO(png),len(png),'synthetic-reading.png')
        keys=dict(child_id='child-1',source_id=self.source['id'],message_id='2')
        self.store.message_attachment(dict(keys,attachment_id=upload['id'],action='attach'),dict)
        with self.store._db() as c:
            source,message=self.store._message_context(c,keys); value=family_media.draft_input(self.store,c,source,message)
            note=dict(title='示例朗读练习',note='朗读 Unit 2 两遍；选做题任选。',uncertainties=[])
            note['requirements']=[note['note']]
            checked=agent.family_llm.validate_school_material(dict(originals=[dict(upload_id=upload['id'],**note)]),original_ids=value['original_ids'])
            c.execute('INSERT INTO agent_message_drafts VALUES(?,?,?,?,?)',(source['id'],'2',value['fingerprint'],
                json.dumps(dict(kind='school_material',**checked)),self.now.isoformat()))
        def snapshot():
            with self.store._db() as c:
                names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
                return {name:list(map(tuple,c.execute('SELECT * FROM "'+name+'"'))) for name in names}
        before=snapshot()
        view=self.store.school_messages(dict(child_id='child-1'),dict)
        self.assertEqual(view['total'],41);self.assertEqual(view['next_offset'],'36')
        self.assertEqual(sorted(p['count'] for p in view['publishers']),[1,2,38])
        bundle=view['groups'][0];self.assertEqual([v['message_id'] for v in bundle['messages']],['1','2','3'])
        import copy
        different=copy.deepcopy(bundle['messages']);different[2]['message']['text']='数学：完成第3页。'
        self.assertEqual([len(g['messages']) for g in agent._publication_groups(different)],[2,1],
                         'a later independent requirement is not an attachment caption')
        self.assertEqual(bundle['messages'][1]['attachments'][0]['name'],'synthetic-reading.png')
        self.assertEqual(bundle['messages'][1]['material_draft']['draft']['note'],'朗读 Unit 2 两遍；选做题任选。')
        self.assertEqual(view['groups'][1]['messages'][0]['message_id'],'4')
        self.assertTrue(all(len(g['messages'])==1 for g in view['groups'][1:]))
        page2=self.store.school_messages(dict(child_id='child-1',day=view['day'],offset='36'),dict)
        self.assertEqual([v['message_id'] for g in page2['groups'] for v in g['messages']],['37','38','39','40','41'])
        self.assertEqual(snapshot(),before,'browse never collects, calls a model or writes business state')
        with self.assertRaises(agent.AgentError) as conflict:
            self.store.ingest(dict(self.payload(expected='41',cursor='42'),messages=[dict(messages[0],sender_id='other')]))
        self.assertEqual(conflict.exception.code,'message_conflict');self.assertEqual(snapshot(),before)
        self.assertEqual(self.store.school_messages(dict(child_id='child-2'),dict)['total'],0)
        for changes in ({'offset':'-1'},{'day':'bad-day'},{'child_id':'missing'},{'extra':'20001'}):
            with self.assertRaises(agent.AgentError):self.store.school_messages(dict(child_id='child-1')|changes,dict)
        self.store.message_attachment(dict(keys,attachment_id=upload['id'],action='detach'),dict)
        fresh=self.store.school_messages(dict(child_id='child-1'),dict)
        self.assertEqual([v['message_id'] for v in fresh['groups'][0]['messages']],['1','2','3'],
                         'native pending-original markers keep verified publications together before bytes arrive')
        pending=fresh['groups'][0]['messages'][1]
        self.assertEqual(pending['attachments'],[])
        self.assertNotEqual((pending['material_draft'] or {}).get('state'),'ready')
        self.source['child_id']='child-2'; self.config()
        self.assertEqual(self.store.school_messages(dict(child_id='child-1'),dict)['total'],0)

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='synthetic-agent-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve(); self.data = self.root / 'private'; self.data.mkdir()
        (self.root / '家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.app = family_review.load_app(self.root, self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.now = dt.datetime(2026, 2, 10, 8, tzinfo=agent.TZ)
        self.source = dict(id='synthetic-group', platform='wechat', child_id='child-1', name='虚构班级', cursor='10', enabled=True)
        self.config()

    def _prepared_school_image(self, uncertain=False, native=False):
        import base64, family_media
        self.source['platform']='qq';self.config()
        payload=self.payload();payload['messages'][0].update(kind='image',text='[图片]',unread=True)
        if native:
            import family_collect
            from test_collect import qq_event,qq_envelope
            self.source['id']='qq:10002';self.config()
            raw=qq_event(11,ident='11',text='');raw.update(time=int(self.now.timestamp()),unread_elements=[dict(element_type=2,content_read=False)],content_complete=False)
            payload.update(source_id=self.source['id'],messages=[family_collect.qq_native_page(qq_envelope([raw]),self.source)[0][2]])
        self.store.ingest(payload)
        png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII=')
        upload=self.app.save_upload(io.BytesIO(png),len(png),'synthetic-school.png')
        keys=dict(child_id='child-1',source_id=self.source['id'],message_id='11',attachment_id=upload['id'],action='attach')
        self.store.message_attachment(keys,dict)
        with self.store._db() as c:
            source,message=self.store._message_context(c,keys)
            value=family_media.draft_input(self.store,c,source,message)
            note=dict(title='虚构英语作业',note='英语：朗读Unit 2课文两遍，完成练习册第8页。',uncertainties=['图片右下角的提交方式看不清'] if uncertain else [])
            note['requirements']=[note['note']]
            draft=dict(kind='school_material',**agent.family_llm.validate_school_material(dict(originals=[dict(upload_id=upload['id'],**note)]),original_ids=value['original_ids']))
            c.execute('INSERT INTO agent_message_drafts VALUES(?,?,?,?,?)',(source['id'],message['id'],value['fingerprint'],json.dumps(draft,ensure_ascii=False),self.now.isoformat()))
        brief=dict(title='',goal='',advice='',state='review',reason='原件或具体要求尚未读全，请先核对。',policy=agent.SCHOOL_TASK_POLICY)
        item=dict(child_id='child-1',kind='school',title='待核对：[图片]',body=agent.FOCUS['school'],due='',evidence=[dict(ref='message:'+self.source['id']+':11',text='[图片]')],plan=dict(school_task=brief))
        self.store._save('synthetic-image-task','fixture',[item],self.now)
        with self.store._db() as c: ident=c.execute("SELECT id FROM agent_items WHERE job_id='synthetic-image-task'").fetchone()[0]
        return ident,keys,value

    def _original_reply(self,ident,result):
        with self.store._db() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone())
            evidence,_=agent._school_material(self.store,c,row)
            material=agent._school_drafts(self.store,c,row)
        part=agent._school_original_parts(evidence,None,material)[-1]
        return {'actions':[dict(result,due='',existing_item_id=ident,basis=[dict(part=part['id'],text=part['text'])])]}

    def test_teacher_image_is_school_material_and_prepared_content_reaches_task_understanding(self):
        ident,keys,value=self._prepared_school_image(native=True)
        self.assertEqual(value['kind'],'school_material','teacher originals must not become child performance drafts')
        self.assertTrue(agent._needs_task_details('[图片原件：1份，内容未读]'))
        def model(messages,*args,**kwargs):
            context=json.loads(messages[-1]['content'])
            self.assertEqual(context['school_material'][0]['draft']['note'],'英语：朗读Unit 2课文两遍，完成练习册第8页。')
            return self._original_reply(ident,dict(title='英语：朗读与第8页练习',goal='朗读Unit 2课文两遍；完成练习册第8页。',advice='',state='ready',reason='原件要求明确。',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id=''))
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1)['created'],1)
            self.assertEqual(called.call_count,1)
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1)['used'],0)
        with self.store._db() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone())
            self.assertEqual(row['state'],'accepted');self.assertEqual(row['title'],'英语：朗读与第8页练习')
            self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],1)

    def test_school_original_refresh_rejects_partial_structure_before_retry(self):
        ident,keys,_=self._prepared_school_image(native=True)
        ready=dict(title='英语：朗读与第8页练习',goal='朗读Unit 2课文两遍；完成练习册第8页。',
            advice='',state='ready',reason='原件要求明确。',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
        partial={k:v for k,v in ready.items() if k in {'title','goal','advice','state','reason'}}
        with self.store._db() as c:
            before=tuple(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone())
            original=tuple(c.execute('SELECT * FROM agent_message_drafts').fetchone())
        with patch.object(agent.family_llm,'_chat_json',side_effect=[partial,self._original_reply(ident,ready)]) as model:
            failed=agent._refresh_school(self.app,self.store,self.now,1)
            self.assertEqual(failed,dict(used=1,failed=1,created=0))
            with self.store._db() as c:
                self.assertEqual(tuple(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone()),before)
                self.assertEqual(tuple(c.execute('SELECT * FROM agent_message_drafts').fetchone()),original)
                self.assertEqual(tuple(c.execute('SELECT attempts,done FROM agent_jobs WHERE id=?',('school-task:'+ident,)).fetchone()),(1,0))
                self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1)['used'],0)
            self.assertEqual(model.call_count,1)
            recovered=agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=6),1)
            self.assertEqual(recovered,dict(used=1,failed=0,created=1))
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=7),1)['used'],0)
            self.assertEqual(model.call_count,2)
        with self.store._db() as c:
            row=c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone()
            self.assertEqual((row['state'],row['title'],row['body']),('accepted',ready['title'],'英语：朗读Unit 2课文两遍，完成练习册第8页。'))
            self.assertEqual(tuple(c.execute('SELECT attempts,done FROM agent_jobs WHERE id=?',('school-task:'+ident,)).fetchone()),(2,1))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(tuple(c.execute('SELECT * FROM agent_message_drafts').fetchone()),original)

    def test_school_original_refresh_rejects_complete_fields_with_empty_purpose(self):
        ident,_,_=self._prepared_school_image(native=True)
        invalid=dict(title='英语：朗读与第8页练习',goal='朗读Unit 2课文两遍；完成练习册第8页。',
            advice='',state='ready',reason='模型未明确用途。',purpose='',submission='',change='new',target_id='',learning_subject='',learning_goal_id='')
        self.assertEqual(set(invalid),set(agent.TASK_BRIEF_SCHEMA['required']))
        with self.store._db() as c:
            before=tuple(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone())
            original=tuple(c.execute('SELECT * FROM agent_message_drafts').fetchone())
        with patch.object(agent.family_llm,'_chat_json',return_value=self._original_reply(ident,invalid)) as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1),dict(used=1,failed=1,created=0))
            self.assertEqual(model.call_count,1)
        with self.store._db() as c:
            self.assertEqual(tuple(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone()),before)
            self.assertEqual(tuple(c.execute('SELECT * FROM agent_message_drafts').fetchone()),original)
            job=c.execute('SELECT attempts,done,error FROM agent_jobs WHERE id=?',('school-task:'+ident,)).fetchone()
            self.assertEqual((job['attempts'],job['done']),(1,0));self.assertTrue(job['error'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)

    def test_uncertain_school_original_keeps_understood_requirements_and_rejects_stale_bytes(self):
        ident,keys,value=self._prepared_school_image(uncertain=True)
        result=dict(title='英语：朗读与第8页练习',goal='朗读Unit 2课文两遍；完成练习册第8页。',advice='',state='ready',reason='模型认为可收集',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',return_value=self._original_reply(ident,result)):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1)['created'],0)
        with self.store._db() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone());b=json.loads(row['plan'])['school_task']
            self.assertEqual(row['title'],result['title']);self.assertEqual(row['body'],'英语：朗读Unit 2课文两遍，完成练习册第8页。')
            self.assertEqual(b['state'],'review');self.assertIn('提交方式看不清',b['reason'])
        (self.data/'uploads'/keys['attachment_id']).write_bytes(b'changed original')
        with self.assertRaises(agent.AgentError) as caught:self.store.act(dict(id=ident,action='accept',expected_updated=row['updated']))
        self.assertEqual(caught.exception.status,409)
        with self.store._db() as c:self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_material_keeps_screenshot_and_missing_originals_for_specific_followup(self):
        ready=dict(title='英语：朗读',goal='朗读Unit 2两遍',advice='',state='ready',reason='',purpose='learning')
        material=dict(fingerprint='synthetic',refs=['message:s:1'],complete_refs=['message:s:1'],uncertainties=[])
        for kind in ('qq_window_fragment','text'):
            with self.subTest(kind=kind):
                m=material if kind=='qq_window_fragment' else dict(material,complete_refs=[])
                brief=agent._school_brief(ready,incomplete=True,evidence=[dict(ref='message:s:1',text='可见英语要求',kind=kind,unread=True)],material=m)
                self.assertEqual(brief['state'],'review');self.assertEqual(brief['goal'],ready['goal'])
                self.assertIn('截图' if kind=='qq_window_fragment' else '附件',brief['reason'])

    def test_school_original_date_comes_from_original_not_reading_day(self):
        ident,keys,_=self._prepared_school_image(native=True)
        with self.store._db() as c:
            draft=json.loads(c.execute('SELECT payload FROM agent_message_drafts').fetchone()[0]);draft['note']='英语：朗读Unit 2两遍，明天提交。'
            draft['originals'][0]['note']=draft['note']
            draft['originals'][0]['requirements']=[draft['note']]
            c.execute('UPDATE agent_message_drafts SET payload=?',(json.dumps(draft),))
        ready=dict(title='英语：朗读',goal=draft['note'],advice='',state='ready',reason='',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',return_value=self._original_reply(ident,ready)):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(days=1),1)['created'],1)
        with self.store._db() as c:self.assertEqual(c.execute('SELECT due FROM agent_items WHERE id=?',(ident,)).fetchone()[0],'2026-02-11')

    def test_historical_undated_school_original_retains_requirements_without_today_task(self):
        ident,keys,_=self._prepared_school_image(native=True)
        ready=dict(title='英语：朗读',goal='朗读Unit 2两遍',advice='',state='ready',reason='',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',return_value=self._original_reply(ident,ready)):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(days=1),1)['created'],0)
        with self.store._db() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone())
            self.assertEqual(row['body'],'英语：朗读Unit 2课文两遍，完成练习册第8页。');self.assertIn('早于今天',json.loads(row['plan'])['school_task']['reason'])
            self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)

    def test_unknown_send_date_or_changed_deadline_never_auto_adopts_school_material(self):
        ident,keys,_=self._prepared_school_image(native=True)
        ready=dict(title='英语：朗读',goal='朗读Unit 2两遍',advice='',state='ready',reason='',purpose='learning',submission='',change='new',target_id='',learning_subject='英语',learning_goal_id='')
        with self.store._db() as c:
            c.execute("UPDATE agent_items SET due='2026-02-11' WHERE id=?",(ident,))
            draft=json.loads(c.execute('SELECT payload FROM agent_message_drafts').fetchone()[0]);draft['note']='英语：今天提交朗读。'
            draft['originals'][0]['note']=draft['note']
            draft['originals'][0]['requirements']=[draft['note']]
            c.execute('UPDATE agent_message_drafts SET payload=?',(json.dumps(draft),))
        with patch.object(agent.family_llm,'_chat_json',return_value=self._original_reply(ident,ready)):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1)['created'],0)
        with self.store._db() as c:
            brief=json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?',(ident,)).fetchone()[0])['school_task']
            self.assertIn('日期不同',brief['reason']);self.assertEqual(c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0],0)
        # A complete interpretation cannot establish when an undated original was published.
        with self.store._db() as c: c.execute("UPDATE agent_items SET due='' WHERE id=?",(ident,))
        evidence=[dict(ref='message:s:1',kind='text',time='',unread=True,text='[图片原件：1份，内容未读]')]
        with patch.object(agent,'_school_material',return_value=(evidence,[])),patch.object(agent,'_school_current',return_value=True),patch.object(agent,'_school_drafts',return_value=dict(fingerprint='new',refs=['message:s:1'],complete_refs=['message:s:1'],uncertainties=[],model=[dict(ref='message:s:1',draft=dict(title='英语',note='2026-02-10前提交朗读',uncertainties=[]))])),patch.object(agent.family_llm,'_chat_json',return_value=ready):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,1)['created'],0)

    def test_all_pending_notices_remain_actionable_after_backfill(self):
        with self.app.connect() as c:
            rows=[(f'notice-{n}',f'job-{n}',f'child-{n%2+1}','school',f'虚构通知 {n}','请家长核对','[]','','pending',
                   f'2026-02-10T08:{n%60:02d}:00+08:00',f'2026-02-10T08:{n%60:02d}:00+08:00','{}') for n in range(110)]
            c.executemany("INSERT INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,state,created,updated,plan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",rows)
        visible=self.store.snapshot()['items']
        self.assertEqual(len(visible),110)
        self.assertEqual({r['child_id'] for r in visible},{'child-1','child-2'})
        self.assertIn('notice-0',{r['id'] for r in visible})

    def test_diagnosis_review_reminder_lists_due_weak_knowledge_points(self):
        import family_diagnosis, family_llm
        from unittest.mock import patch
        saved = self.app.save_record(dict(child='示例甲', day='2026-02-01', category='学习进展', subject='数学',
            title='错题：进位', note='题面：27+8=? 学生原答：315', source=family_diagnosis.WRONG_SOURCE))['record_id']
        # A supported weakness cites a real record; one that cites nothing is kept as 待验证 and sets no reminder.
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加',
            misconception='个位满十未进1', status='有支持', evidence=['record:%d' % saved], suggestion='摆小棒进位')],
            summary='', uncertainties=[])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            family_diagnosis.diagnose(self.app, 'child-1', '数学', now=dt.datetime(2026, 2, 1))
        due = agent._diagnosis_reviews(self.store, self.now)  # review_on 2026-02-08 <= now 2026-02-10
        self.assertEqual([d['name'] for d in due], ['两位数进位加法'])
        self.assertEqual(due[0]['subject'], '数学')
        # Not yet due if we look before the interval elapses.
        self.assertEqual(agent._diagnosis_reviews(self.store, dt.datetime(2026, 2, 3, tzinfo=agent.TZ)), [])

    def test_due_recheck_reminder_links_the_original_wrong_question(self):
        import family_diagnosis, family_llm
        saved = self.app.save_record(dict(child='示例甲', day='2026-02-01', category='学习进展', subject='数学',
            title='数学错题：第3题', note='题面：27+8=? 学生原答：315', source=family_diagnosis.WRONG_SOURCE))['record_id']
        draft = dict(knowledge_components=[dict(name='两位数进位加法', error_type='进位漏加', misconception='个位满十未进1',
            status='有支持', evidence=['record:%d' % saved], suggestion='摆小棒进位')], summary='', uncertainties=[])
        with patch.object(family_llm, '_chat_json', return_value=draft):
            family_diagnosis.diagnose(self.app, 'child-1', '数学', now=dt.datetime(2026, 2, 1))
        def reminders():
            with patch.object(agent, '_plan_learning', return_value=None), patch.object(agent.family_llm, '_chat_json') as model:
                agent.run_once(self.app, self.now); model.assert_not_called()  # deterministic, no model call
            self.now += dt.timedelta(minutes=1)
            with self.app.connect() as c:
                return [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='review' AND title LIKE '到期复测%'")]
        item, = reminders()
        self.assertEqual((item['child_id'], item['record_id'], item['state'], item['due']), ('child-1', saved, 'pending', '2026-02-08'))
        self.assertEqual(json.loads(item['evidence']), [{'ref': 'record:%d' % saved, 'text': '2026-02-01 · 数学错题：第3题'}])
        self.assertIn('复测', item['body']); self.assertIn('不代表已经掌握', item['body'])
        self.assertEqual(len(reminders()), 1)  # the next tick neither duplicates nor re-nags
        # An independent re-check on a fresh item, then re-diagnosis: the weakness is no longer supported, so the reminder retires.
        self.app.save_record(dict(child='示例甲', day='2026-02-09', category='学习进展', subject='数学', title='复测：进位加法',
            note='新题 38+5=43，独立做对', source='家长观察', related_record_id=saved, followup_kind='复测',
            assistance='独立尝试', practice_relation='相近的新题或新片段'))
        cleared = dict(draft, knowledge_components=[dict(draft['knowledge_components'][0], status='有反证')])
        with patch.object(family_llm, '_chat_json', return_value=cleared):
            family_diagnosis.diagnose(self.app, 'child-1', '数学', now=dt.datetime(2026, 2, 10))
        self.assertEqual([r['state'] for r in reminders()], ['superseded'])

    def test_background_diagnosis_runs_once_per_tick_only_when_evidence_changed(self):
        import family_diagnosis, family_llm
        ids = [self.app.save_record(dict(child='示例甲', day='2026-02-0%d' % n, category='学习进展', subject=subject,
            title=subject + '错题：第%d题' % n, note='题面：虚构 学生原答：虚构', source=family_diagnosis.WRONG_SOURCE))['record_id']
            for n, subject in [(1, '数学'), (2, '数学'), (3, '语文')]]
        calls = []
        def model(messages, schema, name, *args, **kwargs):
            calls.append((name, json.loads(messages[-1]['content']).get('subject')))
            return dict(knowledge_components=[], summary='', uncertainties=['虚构：证据不足'])
        def tick():
            before = len(calls)
            with patch.object(agent, '_plan_learning', side_effect=AssertionError('错题 are not planned one by one')), \
                 patch.object(family_llm, '_chat_json', side_effect=model):
                agent.run_once(self.app, self.now)
            self.now += dt.timedelta(minutes=10)
            return calls[before:]
        self.assertEqual(tick(), [('family_diagnosis', '数学')])  # one per tick, after school and goal work
        self.assertEqual(tick(), [('family_diagnosis', '语文')])
        self.assertEqual(tick(), [])                                 # nothing changed: no model call
        self.app.save_record(dict(child='示例甲', day='2026-02-09', category='学习进展', subject='数学', title='复测：进位',
            note='新题独立做对', source='家长观察', related_record_id=ids[0], followup_kind='复测',
            assistance='独立尝试', practice_relation='相近的新题或新片段'))
        self.assertEqual(tick(), [('family_diagnosis', '数学')])  # the re-check refreshes that subject only
        self.assertEqual(tick(), [])

    def test_background_diagnosis_backs_off_then_pauses_and_says_why(self):
        import family_diagnosis, family_llm
        self.app.save_record(dict(child='示例甲', day='2026-02-01', category='学习进展', subject='数学', title='数学错题：第1题',
            note='题面：虚构', source=family_diagnosis.WRONG_SOURCE))
        calls = []
        def failing(*args, **kwargs):
            calls.append(1); raise family_llm.LLMDraftError('虚构模型超时')
        def tick(minutes):
            with patch.object(agent, '_plan_learning', return_value=None), patch.object(family_llm, '_chat_json', side_effect=failing):
                agent.run_once(self.app, self.now)
            self.now += dt.timedelta(minutes=minutes)
        tick(1); tick(1)
        self.assertEqual(len(calls), 1)  # retried only after the backoff, not on every tick
        for _ in range(4): tick(60)
        self.assertEqual(len(calls), 3)  # capped at three attempts per evidence version
        subject = self.app.goals_snapshot()['diagnosis']['child-1']['subjects'][0]
        self.assertIn('虚构模型超时', subject['auto_paused'])
        with patch.object(family_llm, '_chat_json', return_value=dict(knowledge_components=[], summary='', uncertainties=['x'])):
            family_diagnosis.diagnose(self.app, 'child-1', '数学')  # the parent's button still works
        self.assertNotIn('auto_paused', self.app.goals_snapshot()['diagnosis']['child-1']['subjects'][0])

    def test_background_diagnosis_reads_a_parent_kept_tag_once_per_version_within_the_retry_cap(self):
        import family_diagnosis, family_llm
        record = dict(child='示例甲', day='2026-02-01', category='学习进展', subject='数学', title='数学错题：第1题',
                      source=family_diagnosis.WRONG_SOURCE)
        body = '题面：38+5=？\n学生原答：313'
        rid = self.app.save_record(dict(record, note=body))['record_id']
        seen = []
        def model(messages, schema, name, *args, **kwargs):
            seen.append([(r.get('topic_hint'), r.get('error_hint')) for r in json.loads(messages[-1]['content'])['records']])
            return dict(knowledge_components=[], summary='', uncertainties=['虚构：证据不足'])
        def tick(side_effect, minutes=10):
            before = len(seen)
            with patch.object(agent, '_plan_learning', side_effect=AssertionError('错题 are not planned one by one')), \
                 patch.object(family_llm, '_chat_json', side_effect=side_effect):
                agent.run_once(self.app, self.now)
            self.now += dt.timedelta(minutes=minutes)
            return seen[before:]
        self.assertEqual(tick(model), [[(None, None)]])  # an untagged 错题 is diagnosed exactly as before
        self.assertEqual(tick(model), [])
        # The parent keeps a candidate on that record: one new evidence version, read by the model once.
        self.app.save_record(dict(record, id=rid, note=body + '\n知识点（家长核对）：两位数进位加法\n错误类型（家长核对）：进位漏加'))
        self.assertEqual(tick(model), [[('两位数进位加法', '进位漏加')]])
        self.assertEqual(tick(model), [])
        # A corrected candidate is a new version too, and a failing model is still tried at most three times for it.
        self.app.save_record(dict(record, id=rid, note=body + '\n知识点（家长核对）：两位数进位加法\n错误类型（家长核对）：数位对齐错误'))
        failures = []
        def failing(*args, **kwargs):
            failures.append(1); raise family_llm.LLMDraftError('虚构模型超时')
        for _ in range(6): tick(failing, 60)
        self.assertEqual(len(failures), 3)
        self.assertIn('虚构模型超时', self.app.goals_snapshot()['diagnosis']['child-1']['subjects'][0]['auto_paused'])

    def test_exam_result_loop_uses_real_task_flow_and_retires_closed_or_rescheduled_reminders(self):
        exam = self.app.new_task(dict(child='示例甲', title='英语 Unit1-3 单元测验', due='2026-02-05'))
        for title, due in [('数学练习', '2026-02-05'), ('语文单元测验', '2026-02-20'),
                ('英语测试', '2026-02-10'), ('打印英语考试卷', '2026-02-05'),
                ('订正测验', '2026-02-05'), ('核酸检测', '2026-02-05'),
                ('期末复习', '2026-02-05'), ('英语考试', '无明确截止')]:
            self.app.new_task(dict(child='示例乙', title=title, due=due, action='为英语考试做准备'))
        self.app.new_task(dict(child='示例乙', title='参加英语考试', due='2026-02-05', box='wish'))
        def items():
            with self.app.connect() as c:
                return [dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='review' AND title LIKE '记录考试结果%'")]
        def tick():
            # Separate existing record analysis from the deterministic exam reminder.
            with patch.object(agent, '_plan_learning', return_value=None), patch.object(agent.family_llm, '_chat_json') as model:
                agent.run_once(self.app, self.now); model.assert_not_called()
            self.now += dt.timedelta(minutes=1)
            return [i for i in items() if i['state'] == 'pending']
        self.assertEqual(len(tick()), 1)
        item = items()[0]
        self.assertEqual(item['child_id'], 'child-1')
        self.assertIn('task:' + exam['id'], item['evidence'])
        self.assertTrue(json.loads(item['plan'])['exam_result_pending'])
        tick(); self.assertEqual(len(items()), 1)
        # Saving a result is evidence, not a parent's completion decision.
        self.app.save_record(dict(child='示例甲', day='2026-02-05', category='成绩', subject='英语',
            title='虚构考试结果', note='拼写需要核对', source='事项:' + exam['id'], score=60, total=100))
        self.assertEqual(len(tick()), 1)
        for closed in ('已完成', '不参加', '不适用'):
            self.app.save_task(dict(id=exam['id'], status=closed, note='虚构家长确认'))
            self.assertEqual(tick(), [])
            self.assertFalse(any(i['state']=='pending' for i in items()))
            self.app.save_task(dict(id=exam['id'], status='待跟进', note='虚构家长重新打开'))
            self.assertEqual(len(tick()), 1)
        # Rescheduling retires the old reminder; a later past date gets one new reminder.
        with self.app.connect() as c:
            c.execute("UPDATE manual_tasks SET due='2026-02-20' WHERE id=?", (exam['id'],))
        self.assertEqual(tick(), [])
        with self.app.connect() as c:
            c.execute("UPDATE manual_tasks SET due='2026-02-06' WHERE id=?", (exam['id'],))
        pending=tick(); self.assertEqual(len(pending), 1); self.assertEqual(pending[0]['due'], '2026-02-06')
        self.store.act(dict(id=pending[0]['id'], action='dismiss'))
        self.assertEqual(tick(), [], 'acknowledged reminder is not regenerated without a change')


    def test_course_record_does_not_create_parallel_practice_and_reclassification_retires_pending(self):
        ident=self.record()
        with self.app.connect() as c:
            c.execute("UPDATE records SET category='课程进度' WHERE id=?",(ident,))
            c.execute("INSERT INTO agent_items(id,job_id,child_id,kind,title,body,evidence,due,state,created,updated,plan) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                ('synthetic-course-old','record:'+str(ident),'child-1','care','旧建议','待核对','[]','','pending',self.now.isoformat(),self.now.isoformat(),'{}'))
        with patch.object(agent.family_llm,'_chat_json') as model:
            agent.run_once(self.app,self.now);model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual(c.execute("SELECT state FROM agent_items WHERE id='synthetic-course-old'").fetchone()[0],'superseded')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)

    def config(self, enabled=True):
        (self.data / 'agent.json').write_text(json.dumps({'enabled': enabled, 'sources': [self.source]}))

    def test_identical_school_notice_keeps_one_task_decision_and_all_sources(self):
        sources=[self.source,dict(self.source,id='synthetic-second',name='虚构另一班群'),
                 dict(self.source,id='synthetic-sibling',name='虚构另一孩子班群',child_id='child-2')]
        (self.data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=sources)))
        text='语文：完成虚构观察记录。明天带到学校。'
        cursors={s['id']:'10' for s in sources}
        def candidate(source, index, *, content=text, stamp=None, title='语文：完成观察记录', unread=False):
            stamp=stamp or self.now.isoformat()
            self.store.ingest(dict(self.payload(expected=cursors[source['id']],cursor=str(index),message=str(index)),
                source_id=source['id'],messages=[dict(id=str(index),time=stamp,kind='text',sender='示例老师',text=content,unread=unread)]))
            cursors[source['id']]=str(index)
            item=dict(child_id=source['child_id'],kind='school',title=title,body='完成一份自己的观察记录。',due='',
                evidence=[dict(ref='message:'+source['id']+':'+str(index),text=content)],
                plan=dict(school_task=dict(title=title,goal='完成一份自己的观察记录。',advice='',state='ready',reason='明确要求',policy=agent.SCHOOL_TASK_POLICY),
                          school_learning=dict(subject='语文',goal_id=''),school_messages=[dict(source_id=source['id'],message_id=str(index))]))
            key='synthetic-copy:'+str(index);self.store._save(key,'fixture',[item],self.now)
            with self.app.connect() as c:return c.execute('SELECT id FROM agent_items WHERE job_id=?',(key,)).fetchone()[0]
        first=candidate(sources[0],11)
        task=self.store.act(dict(id=first,action='accept'))['task_id']
        from family_goals import Store as Goals
        goals=Goals(self.app,self.store)
        self.assertEqual(goals.route_school(),1)
        self.app.save_task(dict(id=task,status='不适用',note='虚构家长已确认不需要。'))
        with self.app.connect() as c:
            before_updates=[tuple(r) for r in c.execute('SELECT * FROM task_updates')]
            before_task=dict(c.execute('SELECT * FROM manual_tasks WHERE id=?',(task,)).fetchone())
        second=candidate(sources[1],12)
        with patch.object(agent.family_llm,'_chat_json') as model:
            refreshed=agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
        self.assertEqual(refreshed['created'],0)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(before_updates,[tuple(r) for r in c.execute('SELECT * FROM task_updates')])
            saved=dict(c.execute('SELECT * FROM manual_tasks WHERE id=?',(task,)).fetchone())
            self.assertEqual({k:v for k,v in saved.items() if k!='source'},{k:v for k,v in before_task.items() if k!='source'})
            self.assertIn('message:synthetic-group:11',saved['source'])
            self.assertIn('message:synthetic-second:12',saved['source'])
            item=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(second,)).fetchone())
            self.assertEqual(item['task_id'],task)
            canonical=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(first,)).fetchone())
            self.assertEqual(len(json.loads(canonical['evidence'])),2)
        self.assertEqual(self.store.act(dict(id=second,action='accept'))['task_id'],task)
        reopened=agent.Store(self.app.connect,self.app.profiles,self.data,app=self.app)
        self.assertEqual(reopened.act(dict(id=second,action='accept'))['task_id'],task)
        self.assertEqual(goals.route_school(),0)
        with self.app.connect() as c:
            roots=goals.roots(c);self.assertEqual(len(roots),1)
            context,missing,_=goals._school_context(c,roots[0])
            self.assertEqual(len(context),2);self.assertEqual(missing,0)
        # Same wording on another day, changed full text, sibling, another split task and unread media are distinct.
        variants=[(sources[0],dict(stamp=(self.now+dt.timedelta(days=1)).isoformat())),
                  (sources[0],dict(content=text+'补充新的要求。')),(sources[2],{}),
                  (sources[0],dict(title='语文：另一个独立成果')),(sources[0],dict(unread=True))]
        for index,(source,extra) in enumerate(variants,20):
            ident=candidate(source,index,**extra)
            result=self.store.act(dict(id=ident,action='accept'))
            self.assertNotEqual(result['task_id'],task);self.assertNotIn('deduplicated',result)
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],6)
        skipped=candidate(sources[0],30,title='虚构不需跟进的事项')
        self.store.act(dict(id=skipped,action='dismiss'))
        repeated=candidate(sources[1],31,title='虚构不需跟进的事项')
        decision=self.store.act(dict(id=repeated,action='accept'))
        self.assertEqual(decision,dict(ok=True,state='dismissed',task_id='',deduplicated=True))
        self.assertEqual(self.store.act(dict(id=repeated,action='accept')),decision)
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],6)
        with self.app.connect() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(first,)).fetchone())
            for refs in ([dict(ref='message:broken')],[dict(ref=None)],[None]):
                self.assertIsNone(self.store._school_identity(c,dict(row,evidence=json.dumps(refs))))

    def test_school_change_requires_parent_and_preserves_task_history(self):
        from family_goals import Store as Goals
        def add(index, text, *, change='new', target='', cid='child-1', unread=False):
            source=self.source if cid=='child-1' else dict(self.source,id='synthetic-other',child_id=cid)
            with self.app.connect() as c:
                previous=c.execute('SELECT cursor FROM agent_sources WHERE id=?',(source['id'],)).fetchone()
                current=previous['cursor'] if previous else '10'
            self.store.ingest(dict(self.payload(expected=current,cursor=str(index),message=str(index)),source_id=source['id'],messages=[dict(id=str(index),time=self.now.isoformat(),sender='虚构老师',text=text,unread=unread,kind='text')]))
            tasks=agent.school_targets(self.app,self.store,cid)
            raw=dict(proposals=[school_proposal(title_quote=text,focus='school',due='',evidence=[dict(ref='message:'+source['id']+':'+str(index))],learning_subject='语文',learning_goal_id='',task_title='语文：观察记录',task_goal=text,task_advice='',task_state='ready',task_reason='原文要求',task_change=change,task_target_id=target,task_purpose='learning')])
            with patch.object(agent.family_llm,'_chat_json',return_value=raw):
                items=agent._select('school',[dict(ref='message:'+source['id']+':'+str(index),text=text,time=self.now.isoformat(),content_incomplete=unread)],school_goals=[],school_tasks=tasks,as_of=self.now.date().isoformat())
            item=items[0];item.update(child_id=cid,kind='school')
            if item['plan'].get('school_learning'):item['plan']['school_messages']=[dict(source_id=source['id'],message_id=str(index))]
            self.store._save('change:'+str(index),'fixture',[item],self.now)
            with self.app.connect() as c:return c.execute('SELECT id FROM agent_items WHERE job_id=?',('change:'+str(index),)).fetchone()[0]
        def request(ident,target,change='update'):
            with self.app.connect() as c:
                task=next(t for t in self.app.tasks(c) if t['id']==target);update=c.execute('SELECT updated FROM task_updates WHERE id=?',(target,)).fetchone();row=c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone()
                return dict(action='school_change',id=ident,target_id=target,change=change,title='语文：完成观察记录',body='只写两点观察，不用画图。',due='2026-02-12',expected_updated=row['updated'],target_version=task['focus']['version'],target_updated=update['updated'] if update else '')
        first=add(11,'请写三点观察并画一幅图。');task_id=self.store.act(dict(id=first,action='accept'))['task_id']
        goals=Goals(self.app,self.store);self.assertEqual(goals.route_school(),1)
        change=add(12,'更正：观察记录只写两点，不用画图。',change='update',target=task_id)
        with patch.object(agent.family_llm,'_chat_json') as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0);model.assert_not_called()
        with self.assertRaises(agent.AgentError):self.store.act(dict(id=change,action='accept'))
        self.app.save_task(dict(id=task_id,status='已完成',note='虚构家长已核对原成果。'))
        payload=request(change,task_id)
        self.app.save_task(dict(id=task_id,status='已完成',note='虚构家长补充真实帮助情况。'))
        with self.assertRaises(agent.AgentError):agent.apply_school_change(self.app,self.store,payload)
        payload=request(change,task_id);result=agent.apply_school_change(self.app,self.store,payload)
        self.assertTrue(result['completion_needs_review']);self.assertEqual(result['task_id'],task_id);self.assertTrue(agent.apply_school_change(self.app,self.store,payload)['replayed'])
        with self.assertRaises(agent.AgentError):agent.apply_school_change(self.app,self.store,dict(payload,body='重试时内容已变'))
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id);self.assertTrue(task['school_completion_needs_review']);self.assertEqual(task['action'],payload['body']);self.assertEqual(task['agenda']['due_on'],'2026-02-12')
            self.assertIn('message:synthetic-group:11',task['source']);self.assertIn('message:synthetic-group:12',task['source'])
            self.assertEqual(c.execute('SELECT status FROM task_updates WHERE id=?',(task_id,)).fetchone()[0],'已完成')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_focus_history').fetchone()[0],1)
            context,missing,_=goals._school_context(c,goals.roots(c)[0]);self.assertEqual(len(context),2);self.assertEqual(missing,0)
        self.assertEqual(goals.route_school(),0)
        # Same original notice after the correction preserves both correction sources and the closed decision.
        repeat=add(13,'请写三点观察并画一幅图。');self.assertEqual(self.store.act(dict(id=repeat,action='accept'))['task_id'],task_id)
        with self.app.connect() as c:self.assertEqual(len(goals._school_context(c,goals.roots(c)[0])[0]),3)
        cancel=add(14,'取消本次观察记录。',change='cancel',target=task_id)
        agent.apply_school_change(self.app,self.store,request(cancel,task_id,'cancel'))
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT status FROM task_updates WHERE id=?',(task_id,)).fetchone()[0],'已完成')
        self.app.save_task(dict(id=task_id,status='待跟进',note='虚构家长恢复核对。'))
        cancel2=add(15,'再次确认：取消本次观察记录。',change='cancel',target=task_id)
        cancel_request=request(cancel2,task_id,'cancel');save=self.app.save_task
        def fail_after_status(*args,**kwargs):
            save(*args,**kwargs);raise RuntimeError('synthetic interruption after status write')
        with patch.object(self.app,'save_task',side_effect=fail_after_status):
            with self.assertRaises(RuntimeError):agent.apply_school_change(self.app,self.store,cancel_request)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT status FROM task_updates WHERE id=?',(task_id,)).fetchone()[0],'待跟进')
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?',(cancel2,)).fetchone()[0],'pending')
        agent.apply_school_change(self.app,self.store,cancel_request)
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT status FROM task_updates WHERE id=?',(task_id,)).fetchone()[0],'不适用')
        unread=add(16,'变更原件尚未读清。',change='update',target=task_id,unread=True)
        with self.assertRaises(agent.AgentError):agent.apply_school_change(self.app,self.store,request(unread,task_id))
        with self.app.connect() as c:c.execute('UPDATE agent_items SET evidence=? WHERE id=?',(json.dumps([dict(ref=None)]),unread))
        with self.assertRaises(agent.AgentError):agent.apply_school_change(self.app,self.store,request(unread,task_id))
        # Source/child changes cannot attach a sibling notice to this child's task.
        config=json.loads((self.data/'agent.json').read_text());config['sources'].append(dict(self.source,id='synthetic-other',child_id='child-2'));(self.data/'agent.json').write_text(json.dumps(config))
        sibling=add(17,'取消另一孩子的活动。',change='cancel',cid='child-2')
        with self.assertRaises(agent.AgentError):agent.apply_school_change(self.app,self.store,request(sibling,task_id,'cancel'))
        self.assertNotIn(task_id,[x['id'] for x in agent.school_targets(self.app,self.store,'child-2')])
        # Unmatched corrections stay reviewable; a forged model target is rejected.
        with self.assertRaises(agent.AgentError):agent._school_brief(dict(title='变更',goal='请核对',advice='',reason='',state='ready',change='update',target_id='other-child-task'))
        ambiguous=agent._school_brief(dict(title='新增要求',goal='请核对',advice='',reason='模型判断',state='ready',change='new',target_id=task_id),school_tasks=[dict(id=task_id)])
        self.assertEqual((ambiguous['state'],ambiguous['change'],ambiguous['target_id']),('review','new',''))
        self.assertIn('新要求还是学校变更',ambiguous['reason'])

    def _school_append_candidate(self, index, text, *, change='new', target='', title='英语：Unit 3朗读', goal=None,
                                 due='', publisher='synthetic-teacher-a', child='child-1', unread=False, during_model=None):
        """A separately ingested batch; no reply_ref and no copied target provenance."""
        source=self.source if child=='child-1' else dict(self.source,id='synthetic-append-sibling',child_id=child)
        config=json.loads((self.data/'agent.json').read_text())
        if not any(s['id']==source['id'] for s in config['sources']):
            config['sources'].append(source);(self.data/'agent.json').write_text(json.dumps(config))
        with self.app.connect() as c:
            previous=c.execute('SELECT cursor FROM agent_sources WHERE id=?',(source['id'],)).fetchone()
        message=dict(id=str(index),time=self.now.isoformat(),sender='同一个虚构显示名',text=text,unread=unread,kind='text')
        if publisher: message['sender_id']=publisher
        self.store.ingest(dict(source_id=source['id'],expected_cursor=previous['cursor'] if previous else '10',cursor=str(index),
            checked_at=self.now.isoformat(),last_message_time=self.now.isoformat(),error='',messages=[message]))
        ref='message:'+source['id']+':'+str(index)
        evidence=[dict(message,ref=ref,publisher=agent._publisher(source['id'],message),content_incomplete=unread)]
        targets=agent.school_targets(self.app,self.store,child)
        raw=dict(proposals=[school_proposal(title_quote=text,focus='school',due=due,evidence=[dict(ref=ref)],
            learning_subject='数学' if publisher=='synthetic-math-b' else '英语',task_title=title,task_goal=goal or text,task_state='ready',task_reason='虚构原文明确。',
            task_change=change,task_target_id=target,task_purpose='learning')])
        def returned(*args,**kwargs):
            if during_model: during_model()
            return raw
        with patch.object(agent.family_llm,'_chat_json',side_effect=returned):
            items=agent._select('school',evidence,school_goals=[],school_tasks=targets,as_of=self.now.date().isoformat())
        self.assertEqual(len(items),1)
        item=items[0];item.update(child_id=child,kind='school')
        if item['plan'].get('school_learning'): item['plan']['school_messages']=[dict(source_id=source['id'],message_id=str(index))]
        self.store._save('synthetic-append:'+str(index),'synthetic-fixed',[item],self.now)
        with self.app.connect() as c:
            return dict(c.execute('SELECT * FROM agent_items WHERE job_id=?',('synthetic-append:'+str(index),)).fetchone())

    def _school_append_original(self, index=11, *, extra='', title='英语：Unit 3朗读', publisher='synthetic-teacher-a', child='child-1'):
        text='Unit 3课文读两遍，朗读录音上传班级作业区，明天完成。'+extra
        row=self._school_append_candidate(index,text,title=title,due='2026-02-11',publisher=publisher,child=child)
        return row,self.store.act(dict(id=row['id'],action='accept'))['task_id']

    def _school_append_auto(self, row):
        brief=json.loads(row['plan'])['school_task']
        with patch.object(agent,'_now',return_value=self.now):
            return agent.apply_school_change(self.app,self.store,agent._school_append_request(row,brief),school_auto=True)

    def test_explicit_supplement_mislabeled_new_uses_original_task_and_deadline(self):
        original,task_id=self._school_append_original()
        row=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功，不要求背诵。',
            title='英语：补朗读并上传录音',goal='补朗读，确认上传成功，不要求背诵')
        brief=json.loads(row['plan'])['school_task']
        self.assertEqual((brief['state'],brief['change'],brief['target_id']),('ready','append',task_id))
        self.assertEqual(brief['goal'],'录音上传后确认上传成功，不要求背诵。')
        self.assertNotIn('submission',brief)
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0)
            model.assert_not_called()
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertIn(original['body'],task['action'])
            self.assertIn(brief['goal'],task['action'])
            self.assertIn('message:synthetic-group:12',task['source'])
            self.assertEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?',(row['id'],)).fetchone()[0],task_id)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
        # A genuinely new reading requirement is not merged by subject/activity.
        new=self._school_append_candidate(13,'Unit 4课文读一遍，明天完成。',title='英语：Unit 4朗读',due='2026-02-11')
        self.assertEqual(json.loads(new['plan'])['school_task']['change'],'new')
        self.assertNotEqual(self.store.act(dict(id=new['id'],action='accept'))['task_id'],task_id)

    def test_explicit_supplement_new_cannot_bypass_ambiguous_or_changed_origin(self):
        original,task_id=self._school_append_original()
        delta='只补朗读：录音上传后确认上传成功。'
        for index,publisher,child,text in ((12,'synthetic-other-teacher','child-1',delta),
                (13,'','child-1',delta),(14,'synthetic-teacher-a','child-2',delta),
                (15,'synthetic-teacher-a','child-1','只补朗读：明天确认上传成功。'),
                (16,'synthetic-teacher-a','child-1','只补朗读：取消朗读，改为背诵。')):
            row=self._school_append_candidate(index,text,publisher=publisher,child=child)
            self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
        def parent_change():
            agent.family_task_focus.save(self.app,dict(id=task_id,version=0,request_key='synthetic-new-supplement-edit',
                mode='later',next_action='等家长核对',waiting_for='',review_on='2026-02-12',goal='家长核对后的要求保留。'))
        stale=self._school_append_candidate(17,delta,during_model=parent_change)
        with self.assertRaises(agent.AgentError): self._school_append_auto(stale)
        later=self._school_append_candidate(18,delta)
        self.assertEqual(json.loads(later['plan'])['school_task']['state'],'review')
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(next(t for t in self.app.tasks(c) if t['id']==task_id)['action'],'家长核对后的要求保留。')
            self.assertEqual(c.execute('SELECT body FROM agent_items WHERE id=?',(original['id'],)).fetchone()[0],original['body'])

    def test_explicit_supplement_new_with_two_readings_does_not_guess_a_target(self):
        self._school_append_original()
        self._school_append_original(12,title='英语：另一份朗读')
        row=self._school_append_candidate(13,'只补朗读：录音上传后确认上传成功。')
        self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
        with patch.object(agent.family_llm,'_chat_json') as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0)
            model.assert_not_called()
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],2)

    def test_school_handback_preserves_physical_object_and_separate_submission_channel(self):
        for index,obj in enumerate(('数学本','订正本','原卷','活动回执','答题卡'),21):
            original='完成当前练习，明天交'+obj+'。'
            value=dict(title='完成练习并交回'+obj,goal='完成当前练习；交至'+obj+'。',advice='',reason='原文明确。',
                purpose='learning',state='ready',change='new',target_id='',submission='提交至'+obj)
            brief=agent._school_brief(value,evidence=[dict(ref='message:synthetic-group:'+str(index),text=original,kind='text')])
            self.assertEqual(brief['submission'],'交'+obj)
            self.assertNotIn('至'+obj,brief['goal'])
            self.assertIn('交'+obj,brief['goal'])
        value.update(goal='完成练习，在班级作业区提交录音。',submission='提交至班级作业区')
        brief=agent._school_brief(value,evidence=[dict(ref='message:synthetic-group:30',text='朗读录音提交至班级作业区。',kind='text')])
        self.assertEqual(brief['submission'],'提交至班级作业区')
        value.update(goal='交数学本；照片提交至数学本照片区。',submission='照片提交至数学本照片区')
        brief=agent._school_brief(value,evidence=[dict(ref='message:synthetic-group:32',text='完成教材练习，明天交数学本；照片提交至数学本照片区。',kind='text')])
        self.assertEqual(brief['submission'],'照片提交至数学本照片区');self.assertIn('提交至数学本照片区',brief['goal'])
        for negative in ('不交数学本。','无需交数学本。','别交数学本。'):
            original=dict(ref='message:synthetic-group:33',text=negative,kind='text')
            body=dict(goal='交至数学本。')
            with self.assertRaisesRegex(agent.AgentError,'否定或范围疑点'):
                agent._school_handback(body,'交至数学本',[original])
            self.assertEqual(body['goal'],'交至数学本。')
        value.update(goal='交至数学本。',submission='交至数学本')
        reminder=agent._school_brief(value,evidence=[dict(ref='message:synthetic-group:34',text='10月8日请不要忘记交数学本。',kind='text')])
        self.assertEqual(reminder['submission'],'交数学本');self.assertEqual(reminder['state'],'ready')
        # Unread content cannot justify rewriting either field.
        value.update(goal='交至数学本。',submission='交至数学本')
        original=dict(ref='message:synthetic-group:31',text='交数学本。',kind='text',unread=True)
        with patch.object(agent,'_school_handback',wraps=agent._school_handback) as rewrite:
            unread=agent._school_brief(value,incomplete=True,evidence=[original])
            rewrite.assert_not_called()
        self.assertEqual(unread['state'],'review');self.assertEqual(unread['goal'],'')
        self.assertEqual(original['text'],'交数学本。')

    def test_mixed_supplement_does_not_swallow_a_separate_assignment(self):
        original,task_id=self._school_append_original()
        text='只补朗读：录音上传后确认上传成功。另项：完成练习卷第1题。'
        for index,change,target in ((12,'new',''),(13,'append',task_id)):
            row=self._school_append_candidate(index,text,change=change,target=target)
            brief=json.loads(row['plan'])['school_task']
            self.assertEqual(brief['state'],'review');self.assertNotIn('target_basis',brief)
            self.assertIn('完成练习卷第1题',row['body'])
        with patch.object(agent.family_llm,'_chat_json') as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0);model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(next(t for t in self.app.tasks(c) if t['id']==task_id)['action'],original['body'])

    def test_school_cross_batch_append_keeps_task_arrangements_sources_and_original_replay(self):
        from family_goals import Store as Goals
        original,task_id=self._school_append_original()
        goals=Goals(self.app,self.store);self.assertEqual(goals.route_school(),1)
        with self.app.connect() as c: focus=next(t for t in self.app.tasks(c) if t['id']==task_id)['focus']
        agent.family_task_focus.save(self.app,dict(id=task_id,version=focus['version'],request_key='synthetic-append-arranged',
            mode='waiting',next_action='保留家长安排：晚饭后录音',waiting_for='等虚构家长回家',review_on='2026-02-11',scheduled_on='2026-02-11',box='inbox'))
        added=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功，不要求背诵。',change='append',target=task_id)
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0);model.assert_not_called()
        payload=agent._school_append_request(added,json.loads(added['plan'])['school_task'])
        self.assertTrue(agent.apply_school_change(self.app,self.store,payload,school_auto=True)['replayed'])
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertIn(original['body'],task['action']);self.assertIn('确认上传成功，不要求背诵',task['action'])
            self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertEqual((task['focus']['mode'],task['focus']['next_action'],task['focus']['waiting_for'],task['focus']['scheduled_on']),
                ('waiting','保留家长安排：晚饭后录音','等虚构家长回家','2026-02-11'))
            canonical=c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone()
            self.assertEqual((canonical['evidence'],canonical['body']),(original['evidence'],original['body']))
            self.assertIn('message:synthetic-group:12',task['source'])
            self.assertEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?',(added['id'],)).fetchone()[0],task_id)
            self.assertEqual(len(goals._school_context(c,goals.roots(c)[0])[0]),2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)
        self.assertEqual(goals.route_school(),0)
        repeated,repeat_id=self._school_append_original(13)
        self.assertEqual(repeat_id,task_id)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertIn('确认上传成功',next(t for t in self.app.tasks(c) if t['id']==task_id)['action'])

    def test_school_original_action_append_and_repeated_notice_keep_scoped_messages(self):
        original,task_id=self._school_append_original()
        self.store.app=self.app
        keys=dict(child_id='child-1',source_id=self.source['id'])
        with self.store._db() as c:
            canonical=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
            evidence,_=agent._school_material(self.store,c,canonical)
            plan=json.loads(canonical['plan']);ref=evidence[0]['ref'];quote=evidence[0]['text']
            self.assertEqual(plan['school_task']['origin_basis'],agent._school_message_basis(evidence))
            anchor=dict(ref=ref,upload_ids=[],pages=[],quote=quote)
            plan['school_original_action']=dict(identity=agent._hash(['child-1',[agent._json([ref,[],quote])]]),
                scope=agent._hash(['child-1',[ref],[]]),root_id=original['id'],anchors=[anchor])
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(agent._json(plan),original['id']))

        def saved_state():
            with self.app.connect() as c:
                present={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                return {table:[tuple(r) for r in c.execute('SELECT * FROM '+table+' ORDER BY rowid')]
                        for table in ('agent_items','manual_tasks','records','task_updates','task_focus','task_focus_history') if table in present}

        def read_text(message_id,text):
            before=saved_state()
            with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved messages need no model')) as model:
                view=self.store.message(dict(keys,message_id=message_id,task_id=task_id),self.app.upload_info)
            model.assert_not_called()
            self.assertEqual((view['task_id'],view['message']['text']),(task_id,text))
            self.assertEqual((view['attachments'],view['unavailable_attachment_ids'],view['nearby_materials']),([],[],[]))
            self.assertIsNone(view['pdf_material']);self.assertIsNone(view['material_draft'])
            self.assertTrue(view['action_material']['scoped'])
            self.assertEqual(view['action_material']['quotes'],[dict(text=text,upload_ids=[],pages=[])])
            self.assertEqual(saved_state(),before,'task message previews must not write family or task records')

        read_text('11',quote)
        delta='只补朗读：录音上传后确认上传成功，不要求背诵。'
        added=self._school_append_candidate(12,delta,change='append',target=task_id)
        self._school_append_auto(added)
        with self.app.connect() as c:
            canonical=c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone()
            self.assertEqual((canonical['body'],canonical['evidence']),(original['body'],original['evidence']))
            self.assertEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?',(added['id'],)).fetchone()[0],task_id)
        with self.subTest(message='accepted supplement'):
            read_text('12',delta)

        repeated,repeat_id=self._school_append_original(13)
        self.assertEqual(repeat_id,task_id)
        with self.subTest(message='original after same-day repeated notice'):
            read_text('11',quote)
        with self.app.connect() as c:
            canonical=c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone()
            self.assertEqual(canonical['body'],original['body'])
            self.assertTrue(all(e in json.loads(canonical['evidence']) for e in json.loads(original['evidence'])))
            self.assertIn(anchor,json.loads(canonical['plan'])['school_original_action']['anchors'])
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertIn(original['body'],task['action']);self.assertEqual(task['action'].count(delta),1)
            self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertEqual(c.execute('SELECT task_id FROM agent_items WHERE id=?',(repeated['id'],)).fetchone()[0],task_id)
            self.assertEqual(tuple(c.execute('SELECT (SELECT COUNT(*) FROM manual_tasks),'
                '(SELECT COUNT(*) FROM records),(SELECT COUNT(*) FROM task_updates)').fetchone()),(1,0,0))
        foreign=self.app.new_task(dict(child='示例乙',title='虚构其他孩子作业',category='homework'))
        before=saved_state()
        with self.assertRaises(agent.AgentError):
            self.store.message(dict(keys,message_id='12',task_id=foreign['id']),self.app.upload_info)
        self.assertEqual(saved_state(),before,'rejecting a foreign task must not change saved records')

    def test_school_cross_batch_textbook_append_and_duplicate_keep_one_requirement(self):
        text='教材第38页第2、3题必做，明天交数学本。'
        original=self._school_append_candidate(11,text,title='数学：教材第38页第2、3题',due='2026-02-11',publisher='synthetic-math-b')
        task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
        delta='仅补教材作业：先独立做，再按书中示例检查；不会的题先标记，不要照抄示例答案。'
        first=self._school_append_candidate(12,delta,change='append',target=task_id,title='教材作业补充',publisher='synthetic-math-b')
        self._school_append_auto(first)
        repeated=self._school_append_candidate(13,delta,change='append',target=task_id,title='教材作业补充',publisher='synthetic-math-b')
        self.assertTrue(self._school_append_auto(repeated)['deduplicated'])
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(task['action'].count(delta),1);self.assertIn('第2、3题必做',task['action'])
            self.assertIn('message:synthetic-group:12',task['source']);self.assertIn('message:synthetic-group:13',task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_focus_history').fetchone()[0],1)

    def test_school_append_unit_prefix_is_not_the_same_object(self):
        text='Unit30课文读两遍，朗读录音上传班级作业区，明天完成。'
        original=self._school_append_candidate(11,text,title='英语：Unit30朗读',due='2026-02-11')
        task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
        with self.app.connect() as c:
            before=next(t for t in self.app.tasks(c) if t['id']==task_id)
            canonical=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
        for index,change,delta in ((12,'new','只补Unit3朗读：录音上传后确认上传成功。'),
                                  (13,'append','只补朗读Unit3：录音上传后确认上传成功。')):
            with self.subTest(change=change):
                row=self._school_append_candidate(index,delta,change=change,target=task_id if change=='append' else '')
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual(brief['state'],'review','Unit3 must not append to Unit30')
                self.assertNotIn('target_basis',brief);self.assertNotIn('input_basis',brief)
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0)
            model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual(next(t for t in self.app.tasks(c) if t['id']==task_id),before)
            self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone()),canonical)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            for index in (12,13):
                row=c.execute('SELECT state,task_id FROM agent_items WHERE job_id=?',('synthetic-append:'+str(index),)).fetchone()
                self.assertEqual(tuple(row),('pending',''))

    def test_school_append_unit_spacing_keeps_one_canonical_task_and_arrangement(self):
        original,task_id=self._school_append_original()
        agent.family_task_focus.save(self.app,dict(id=task_id,version=0,request_key='synthetic-unit-spacing-arrangement',
            mode='waiting',next_action='保留家长安排：晚饭后录音',waiting_for='等虚构家长回家',
            review_on='2026-02-11',scheduled_on='2026-02-11',box='inbox'))
        for index,change,delta in ((12,'new','只补Unit3朗读：录音上传后确认上传成功。'),
                                  (13,'append','只补朗读Unit3：再检查录音音量清楚。')):
            with self.subTest(change=change):
                row=self._school_append_candidate(index,delta,change=change,target=task_id if change=='append' else '')
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual((brief['state'],brief['change'],brief['target_id']),('ready','append',task_id))
                self.assertEqual(brief['target_basis']['canonical_id'],original['id'])
                self._school_append_auto(row)
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertIn(original['body'],task['action'])
            self.assertIn('确认上传成功',task['action']);self.assertIn('再检查录音音量清楚',task['action'])
            self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertEqual((task['focus']['mode'],task['focus']['next_action'],task['focus']['waiting_for'],task['focus']['scheduled_on']),
                ('waiting','保留家长安排：晚饭后录音','等虚构家长回家','2026-02-11'))
            canonical=c.execute('SELECT state,task_id,evidence,body,due FROM agent_items WHERE id=?',(original['id'],)).fetchone()
            self.assertEqual(tuple(canonical),('accepted',task_id,original['evidence'],original['body'],original['due']))
            for index in (11,12,13):self.assertIn('message:synthetic-group:'+str(index),task['source'])
            for index in (12,13):
                self.assertEqual(c.execute('SELECT state,task_id FROM agent_items WHERE job_id=?',('synthetic-append:'+str(index),)).fetchone()['task_id'],task_id)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_school_append_exact_unit_isolates_competing_peer(self):
        original=self._school_append_candidate(11,'Unit3课文读两遍，朗读录音上传班级作业区，明天完成。',
            title='英语：Unit3朗读',due='2026-02-11')
        task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
        other=self._school_append_candidate(12,'Unit30课文读两遍，朗读录音上传班级作业区，明天完成。',
            title='英语：Unit30朗读',due='2026-02-11')
        other_id=self.store.act(dict(id=other['id'],action='accept'))['task_id']
        self.assertNotEqual(task_id,other_id)
        with self.app.connect() as c:
            other_before=next(t for t in self.app.tasks(c) if t['id']==other_id)
            other_canonical=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(other['id'],)).fetchone())
        row=self._school_append_candidate(13,'只补朗读Unit3：录音上传后确认上传成功。',change='append',target=task_id)
        brief=json.loads(row['plan'])['school_task']
        self.assertEqual((brief['state'],brief['target_id']),('ready',task_id))
        self._school_append_auto(row)
        with self.app.connect() as c:
            tasks={t['id']:t for t in self.app.tasks(c)}
            self.assertEqual(len(tasks),2);self.assertEqual(tasks[other_id],other_before)
            self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?',(other['id'],)).fetchone()),other_canonical)
            self.assertIn(original['body'],tasks[task_id]['action']);self.assertIn('确认上传成功',tasks[task_id]['action'])
            self.assertEqual(tasks[task_id]['agenda']['due_on'],'2026-02-11')
            self.assertIn('message:synthetic-group:13',tasks[task_id]['source'])
            self.assertNotIn('message:synthetic-group:13',tasks[other_id]['source'])

    def test_school_append_save_rechecks_forged_unit_prefix_basis(self):
        original=self._school_append_candidate(11,'Unit30课文读两遍，朗读录音上传班级作业区，明天完成。',
            title='英语：Unit30朗读',due='2026-02-11')
        task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
        delta='只补朗读Unit3：录音上传后确认上传成功。'
        row=self._school_append_candidate(12,delta,change='append',target=task_id)
        # Simulate an old/forged ready receipt that bypassed the routing guard.
        # Its current source and target fingerprints are valid; only the object is wrong.
        with self.app.connect() as c:
            evidence,_=agent._school_material(self.store,c,row)
            target=next(t for t in agent.school_targets(self.app,self.store,'child-1',connection=c) if t['id']==task_id)
            plan=json.loads(row['plan'])
            plan['school_task'].update(state='ready',change='append',target_id=task_id,goal=delta,
                target_basis=target['append_basis'],input_basis=agent._school_message_basis(evidence))
            c.execute('UPDATE agent_items SET plan=? WHERE id=?',(json.dumps(plan),row['id']))
        with self.app.connect() as c:
            row=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(row['id'],)).fetchone())
            before='\n'.join(c.iterdump())
        with self.assertRaises(agent.AgentError):self._school_append_auto(row)
        with self.app.connect() as c:self.assertEqual('\n'.join(c.iterdump()),before,'object mismatch must roll back every save')

    def test_school_append_compound_units_do_not_collapse_to_a_prefix(self):
        cases=(('Unit3.1','Unit3.1A','new'),('Unit3A','Unit3A.1','append'),
               ('Unit3','Unit3-4','new'),('Unit3','Unit3+Unit30','append'),
               ('Unit3','Unit3/4','append'),('Unit3','Unit3&4','new'))
        before={}
        for n,(unit,supplement,change) in enumerate(cases):
            index=11+2*n;publisher='synthetic-compound-negative-'+str(n)
            original=self._school_append_candidate(index,unit+'课文读两遍，朗读录音上传班级作业区，明天完成。',
                title='英语：'+unit+'朗读（虚构复合负例'+str(n)+'）',due='2026-02-11',publisher=publisher)
            task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
            with self.app.connect() as c:before[task_id]=next(t for t in self.app.tasks(c) if t['id']==task_id)
            row=self._school_append_candidate(index+1,'只补'+supplement+'朗读：录音上传后确认上传成功。',
                change=change,target=task_id if change=='append' else '',publisher=publisher,title='英语：朗读补充')
            with self.subTest(original=unit,supplement=supplement):
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual(brief['state'],'review')
                self.assertNotIn('target_basis',brief);self.assertNotIn('input_basis',brief)
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual({t['id']:t for t in self.app.tasks(c)},before,'no rejected object may auto-append or create work')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)

    def test_school_append_exact_compound_units_allow_case_and_spacing(self):
        cases=(('Unit3','UNIT 3'),('Unit3A','UNIT 3a'),('Unit3.1','UNIT 3.1'),
               ('Unit3.1A','UNIT 3.1a'),('Unit3A.1','UNIT 3a.1'),('Unit3-4','UNIT 3-4'),
               ('Unit3+Unit30','UNIT 3+UNIT 30'),('Unit3/4','UNIT 3 / 4'),('Unit3&4','UNIT 3 & 4'))
        for n,(unit,supplement) in enumerate(cases):
            with self.subTest(original=unit,supplement=supplement):
                index=11+2*n;publisher='synthetic-compound-positive-'+str(n)
                original=self._school_append_candidate(index,unit+'课文读两遍，朗读录音上传班级作业区，明天完成。',
                    title='英语：'+unit+'朗读',due='2026-02-11',publisher=publisher)
                task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
                row=self._school_append_candidate(index+1,'只补'+supplement+'朗读：录音上传后确认上传成功。',
                    change='append',target=task_id,publisher=publisher,title='英语：朗读补充')
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual((brief['state'],brief['target_id']),('ready',task_id))
                self.assertEqual(brief['target_basis']['canonical_id'],original['id'])
                self._school_append_auto(row)
                with self.app.connect() as c:
                    task=next(t for t in self.app.tasks(c) if t['id']==task_id)
                    self.assertIn(original['body'],task['action']);self.assertIn('确认上传成功',task['action'])
                    self.assertEqual(task['agenda']['due_on'],'2026-02-11')
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],n+1)

    def test_school_append_model_objects_cannot_replace_the_source_or_target(self):
        explicit='只补Unit30朗读：录音上传后确认上传成功。'
        cases=((explicit,'英语：朗读补充','Unit3朗读录音上传后确认上传成功。'),
               (explicit,'英语：Unit3朗读补充','Unit30朗读录音上传后确认上传成功。'),
               ('只补朗读：录音上传后确认上传成功。','英语：朗读补充','Unit3朗读录音上传后确认上传成功。'))
        before={};canonical={}
        for n,(text,title,goal) in enumerate(cases):
            index=11+2*n;publisher='synthetic-modeled-object-negative-'+str(n)
            original=self._school_append_candidate(index,'Unit30课文读两遍，朗读录音上传班级作业区，明天完成。',
                title='英语：Unit30朗读（虚构负例'+str(n+1)+'）',due='2026-02-11',publisher=publisher)
            task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],n+1)
                before[task_id]=next(t for t in self.app.tasks(c) if t['id']==task_id)
                canonical[original['id']]=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
            row=self._school_append_candidate(index+1,text,change='append',target=task_id,title=title,goal=goal,publisher=publisher)
            with self.subTest(title=title,goal=goal,source=text):
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual(brief['state'],'review')
                self.assertNotIn('target_basis',brief);self.assertNotIn('input_basis',brief)
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual({t['id']:t for t in self.app.tasks(c)},before)
            for ident,row in canonical.items():
                self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?',(ident,)).fetchone()),row)

    def test_school_append_generic_or_correct_model_objects_keep_the_same_task(self):
        cases=(('只补朗读：录音上传后确认上传成功。','英语：朗读补充','录音上传后确认上传成功。'),
               ('只补Unit30朗读：录音上传后确认上传成功。','英语：Unit30朗读补充','Unit30朗读录音上传后确认上传成功。'))
        for n,(text,title,goal) in enumerate(cases):
            with self.subTest(title=title,goal=goal):
                index=11+2*n;publisher='synthetic-modeled-object-positive-'+str(n)
                original=self._school_append_candidate(index,'Unit30课文读两遍，朗读录音上传班级作业区，明天完成。',
                    title='英语：Unit30朗读（虚构正例'+str(n+1)+'）',due='2026-02-11',publisher=publisher)
                task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
                with self.app.connect() as c:before=next(t for t in self.app.tasks(c) if t['id']==task_id)
                row=self._school_append_candidate(index+1,text,change='append',target=task_id,title=title,goal=goal,publisher=publisher)
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual((brief['state'],brief['target_id']),('ready',task_id))
                self._school_append_auto(row)
                with self.app.connect() as c:
                    task=next(t for t in self.app.tasks(c) if t['id']==task_id)
                    self.assertIn(original['body'],task['action']);self.assertIn(goal,task['action'])
                    self.assertEqual((task['title'],task['agenda']['due_on']),(before['title'],'2026-02-11'))
                    self.assertTrue(task['source'].startswith(before['source']))
                    self.assertIn('message:synthetic-group:'+str(index+1),task['source'])
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],n+1)

    def test_school_append_rejects_unknown_publisher_other_child_and_competing_activity(self):
        original,task_id=self._school_append_original()
        delta='只补朗读：录音上传后确认上传成功。'
        for index,publisher in ((12,'synthetic-other-teacher'),(13,'')):
            row=self._school_append_candidate(index,delta,change='append',target=task_id,publisher=publisher)
            self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
        with self.assertRaises(agent.AgentError):
            self._school_append_candidate(14,delta,change='append',target=task_id,child='child-2')
        self._school_append_original(15,title='英语：另一份朗读')
        row=self._school_append_candidate(16,delta,change='append',target=task_id)
        self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
        with patch.object(agent.family_llm,'_chat_json') as model:
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now,0)['created'],0);model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT body FROM agent_items WHERE id=?',(original['id'],)).fetchone()[0],original['body'])

    def test_school_append_late_model_receipt_does_not_overwrite_parent_requirements(self):
        original,task_id=self._school_append_original()
        def parent_change():
            agent.family_task_focus.save(self.app,dict(id=task_id,version=0,request_key='synthetic-parent-late-change',mode='later',
                next_action='等家长核对',waiting_for='',review_on='2026-02-12',goal='家长另行核对后的原要求。'))
        row=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id,during_model=parent_change)
        with self.assertRaises(agent.AgentError): self._school_append_auto(row)
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(task['action'],'家长另行核对后的原要求。')
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?',(row['id'],)).fetchone()[0],'pending')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
        later=self._school_append_candidate(13,'只补朗读：增加自查步骤。',change='append',target=task_id)
        self.assertEqual(json.loads(later['plan'])['school_task']['state'],'review')

    def test_school_append_late_feedback_completed_and_explicit_parent_append_preserve_records(self):
        original,task_id=self._school_append_original()
        row=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id)
        feedback=self.app.save_task_feedback(dict(task_id=task_id,child='示例甲',day='2026-02-10',note='虚构原作答：正在核对。',request_key='synthetic-append-feedback'))
        with self.assertRaises(agent.AgentError): self._school_append_auto(row)
        self.app.save_task(dict(id=task_id,status='已完成',note='虚构家长此前已核对完成。'))
        reviewed=self._school_append_candidate(13,'只补朗读：新增上传成功确认步骤。',change='append',target=task_id)
        self.assertEqual(json.loads(reviewed['plan'])['school_task']['state'],'review')
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            update=dict(c.execute('SELECT * FROM task_updates WHERE id=?',(task_id,)).fetchone())
            saved=dict(c.execute('SELECT * FROM records WHERE id=?',(feedback['record_id'],)).fetchone())
        payload=dict(action='school_change',id=reviewed['id'],target_id=task_id,change='append',title=task['title'],body=reviewed['body'],
            due=task['agenda']['due_on'],expected_updated=reviewed['updated'],target_version=task['focus']['version'],target_updated=update['updated'])
        result=agent.apply_school_change(self.app,self.store,payload)
        self.assertTrue(result['completion_needs_review']);self.assertTrue(agent.apply_school_change(self.app,self.store,payload)['replayed'])
        with self.app.connect() as c:
            after=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertTrue(after['school_completion_needs_review']);self.assertIn(original['body'],after['action']);self.assertIn(reviewed['body'],after['action'])
            self.assertEqual(dict(c.execute('SELECT * FROM task_updates WHERE id=?',(task_id,)).fetchone()),update)
            self.assertEqual(dict(c.execute('SELECT * FROM records WHERE id=?',(feedback['record_id'],)).fetchone()),saved)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)

    def test_school_append_cannot_remove_prior_recitation_optional_or_deadline(self):
        original,task_id=self._school_append_original(extra='另须背诵课文。')
        for index,text,change,due in ((12,'只补朗读：不要求背诵。','append',''),
            (13,'只补朗读：本次改为选做。','append',''),(14,'更正朗读：取消录音上传。','update',''),
            (15,'只补朗读：后天确认录音上传成功。','append','2026-02-12')):
            row=self._school_append_candidate(index,text,change=change,target=task_id,due=due)
            brief=json.loads(row['plan'])['school_task']
            if index==15:
                self.assertEqual(brief['state'],'review')
                basis=next(t for t in agent.school_targets(self.app,self.store,'child-1') if t['id']==task_id)['append_basis']
                obj=dict(action='school_change',id=row['id'],target_id=task_id,change='append',title=basis['title'],
                    body=brief['goal'],due=due,expected_updated=row['updated'],target_version=basis['version'],target_updated=basis['updated'])
                with self.assertRaises(agent.AgentError):agent.apply_school_change(self.app,self.store,obj,school_auto=True)
            else: self.assertEqual(brief['state'],'review')
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(task['action'],original['body']);self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertFalse(c.execute("SELECT 1 FROM sqlite_master WHERE name='task_focus_history'").fetchone())

    def test_school_append_model_repeating_verified_due_keeps_original_deadline(self):
        original,task_id=self._school_append_original()
        row=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功，不要求背诵。',
            change='append',target=task_id,due='2026-02-11')
        brief=json.loads(row['plan'])['school_task']
        self.assertEqual(brief['state'],'ready');self.assertEqual(row['due'],'')
        self.assertEqual(brief['target_basis']['due'],'2026-02-11')
        self._school_append_auto(row)
        with self.app.connect() as c:
            tasks=self.app.tasks(c);self.assertEqual(len(tasks),1)
            task=tasks[0];self.assertEqual(task['id'],task_id)
            self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertIn('确认上传成功，不要求背诵',task['action'])
            self.assertIn('录音上传班级作业区',task['action'])
            self.assertEqual({x['ref'] for x in task['agenda']['publications']},
                {'message:'+self.source['id']+':11','message:'+self.source['id']+':12'})
            self.assertEqual(c.execute('SELECT body FROM agent_items WHERE id=?',(original['id'],)).fetchone()[0],original['body'])

    def test_school_append_inherited_due_exception_does_not_clear_real_uncertainty(self):
        original,task_id=self._school_append_original()
        for index,text,due,extra in (
            (12,'只补朗读：确认上传成功。','2026-02-12',{}),
            (13,'只补朗读：截止时间待定，请确认上传成功。','2026-02-11',{}),
            (14,'只补朗读：确认上传成功。','2026-02-11',dict(publisher='another-publisher')),
            (15,'只补朗读：确认上传成功。','2026-02-11',dict(unread=True)),
            (16,'只补朗读：明天确认上传成功。','2026-02-11',dict(goal='后天确认上传成功。'))):
            with self.subTest(index=index):
                row=self._school_append_candidate(index,text,change='append',target=task_id,due=due,**extra)
                self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
        with self.app.connect() as c:
            self.assertEqual(len(self.app.tasks(c)),1)
            self.assertEqual(self.app.tasks(c)[0]['action'],original['body'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)

    def test_school_append_textbook_excludes_only_explicit_nonreplacement_peer(self):
        original=self._school_append_candidate(11,'教材第38页第2、3题必做，明天交数学本。',
            title='数学：教材第38页第2、3题',due='2026-02-11',publisher='synthetic-math-b')
        task_id=self.store.act(dict(id=original['id'],action='accept'))['task_id']
        correction=self._school_append_candidate(12,'订正测验第5题，写完整过程。该任务不替代教材作业。',
            title='数学：订正测验第5题',publisher='synthetic-math-b')
        correction_id=self.store.act(dict(id=correction['id'],action='accept'))['task_id']
        text='仅补教材作业：先独立做，再按书中示例检查；不会的题先标记，不要照抄示例答案。'
        added=self._school_append_candidate(13,text,change='append',target=task_id,
            title='数学：教材补充',due='2026-02-11',publisher='synthetic-math-b')
        self.assertEqual(json.loads(added['plan'])['school_task']['state'],'ready')
        self._school_append_auto(added)
        with self.app.connect() as c:
            tasks={t['id']:t for t in self.app.tasks(c)};self.assertEqual(len(tasks),2)
            self.assertIn(text,tasks[task_id]['action']);self.assertEqual(tasks[task_id]['agenda']['due_on'],'2026-02-11')
            self.assertEqual(tasks[correction_id]['action'],correction['body'])
        peer=self._school_append_candidate(14,'完成教材第39页第1题。',title='数学：教材第39页第1题',publisher='synthetic-math-b')
        self.store.act(dict(id=peer['id'],action='accept'))
        ambiguous=self._school_append_candidate(15,text,change='append',target=task_id,
            title='数学：教材补充',due='2026-02-11',publisher='synthetic-math-b')
        self.assertEqual(json.loads(ambiguous['plan'])['school_task']['state'],'review')

    def test_school_append_current_message_does_not_reactivate_expired_target(self):
        original,task_id=self._school_append_original()
        self.now+=dt.timedelta(days=3)
        for index,due in ((12,''),(13,'2026-02-11')):
            with self.subTest(model_due=due):
                row=self._school_append_candidate(index,'只补朗读：确认上传成功。',change='append',target=task_id,due=due)
                self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
                with self.assertRaises(agent.AgentError):self._school_append_auto(row)
        with self.app.connect() as c:
            self.assertEqual(len(self.app.tasks(c)),1)
            self.assertEqual(self.app.tasks(c)[0]['action'],original['body'])
            self.assertEqual(self.app.tasks(c)[0]['agenda']['due_on'],'2026-02-11')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)

    def test_school_append_unparsed_date_guard_covers_empty_and_copied_model_due(self):
        original,task_id=self._school_append_original()
        for index,(due,text,goal) in enumerate(((due,text,goal) for due in ('','2026-02-11')
                for text,goal in (('只补朗读：后天确认上传成功。',None),
                    ('只补朗读：确认上传成功。','2月12日确认上传成功。'))),12):
            with self.subTest(due=due,text=text,goal=goal):
                row=self._school_append_candidate(index,text,change='append',target=task_id,due=due,goal=goal)
                brief=json.loads(row['plan'])['school_task']
                self.assertEqual(brief['state'],'review');self.assertNotIn('target_basis',brief)
        with self.app.connect() as c:
            self.assertEqual(len(self.app.tasks(c)),1)
            self.assertEqual(self.app.tasks(c)[0]['action'],original['body'])
            self.assertEqual(self.app.tasks(c)[0]['agenda']['due_on'],'2026-02-11')

    def test_school_append_rejects_original_corrected_or_recalled_after_collection(self):
        original,task_id=self._school_append_original()
        pending=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id)
        with self.app.connect() as c:
            payload=json.loads(c.execute("SELECT payload FROM agent_messages WHERE source_id='synthetic-group' AND id='11'").fetchone()[0])
        for index,changes in ((13,dict(text='更正：Unit 3课文只读一遍，不上传。')),
                              (14,dict(text='[已撤回，正文未读取]',kind='recalled',unread=True))):
            with self.app.connect() as c:
                c.execute("UPDATE agent_messages SET payload=? WHERE source_id='synthetic-group' AND id='11'",(json.dumps(dict(payload,**changes)),))
            with self.assertRaises(agent.AgentError): self._school_append_auto(pending)
            after=self._school_append_candidate(index,'只补朗读：确认上传成功。',change='append',target=task_id)
            self.assertEqual(json.loads(after['plan'])['school_task']['state'],'review')
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(task['action'],original['body'])
            canonical=c.execute('SELECT body,evidence FROM agent_items WHERE id=?',(original['id'],)).fetchone()
            self.assertEqual((canonical['body'],canonical['evidence']),(original['body'],original['evidence']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)

    def test_school_append_first_parent_approval_edits_requirements_stays_review_without_writes(self):
        original=self._school_append_candidate(11,'Unit 3课文朗读两遍，明天完成。',due='2026-02-11')
        approved='Unit 3课文朗读两遍，不录音、不上传。'
        task_id=self.store.act(dict(id=original['id'],action='accept',body=approved))['task_id']
        with self.app.connect() as c:
            before=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual((before['focus']['version'],before['focus']['goal']),(0,''))
            self.assertEqual(before['action'],approved)
            canonical=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
        added=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id)
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            result=agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
        self.assertEqual(result['created'],0)
        with self.app.connect() as c:
            after=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(after['action'],approved,'首次批准的手改要求不能因focus仍为0而被自动追加反向要求')
            row=c.execute('SELECT state,task_id,plan FROM agent_items WHERE id=?',(added['id'],)).fetchone()
            self.assertEqual((row['state'],row['task_id']),('pending',''))
            self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
            self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone()),canonical)
            self.assertEqual(after['source'],before['source'])
            self.assertEqual(after['focus'],before['focus'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_school_append_keeps_two_current_supplements_on_one_original(self):
        original,task_id=self._school_append_original()
        first=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id)
        self._school_append_auto(first)
        second=self._school_append_candidate(13,'只补朗读：确认上传后再检查音量清楚。',change='append',target=task_id)
        self.assertEqual(json.loads(second['plan'])['school_task']['state'],'ready')
        self._school_append_auto(second)
        with self.app.connect() as c:
            task=next(t for t in self.app.tasks(c) if t['id']==task_id)
            self.assertEqual(task['action'].count('补充要求：'),2)
            self.assertIn('确认上传成功',task['action']);self.assertIn('检查音量清楚',task['action'])
            self.assertEqual(task['agenda']['due_on'],'2026-02-11')
            self.assertTrue(all('message:synthetic-group:'+str(i) in task['source'] for i in (11,12,13)))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT body FROM agent_items WHERE id=?',(original['id'],)).fetchone()[0],original['body'])

    def test_school_append_after_explicit_parent_append_stays_review(self):
        original,task_id=self._school_append_original()
        first=self._school_append_candidate(12,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id)
        with patch.object(agent,'_now',return_value=self.now):
            agent.apply_school_change(self.app,self.store,agent._school_append_request(first,json.loads(first['plan'])['school_task']))
        with self.app.connect() as c: before=next(t for t in self.app.tasks(c) if t['id']==task_id)
        next_row=self._school_append_candidate(13,'只补朗读：确认上传后再检查音量清楚。',change='append',target=task_id)
        self.assertEqual(json.loads(next_row['plan'])['school_task']['state'],'review')
        with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
            agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
        with self.app.connect() as c:
            self.assertEqual(next(t for t in self.app.tasks(c) if t['id']==task_id),before)
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?',(next_row['id'],)).fetchone()[0],'pending')

    def test_school_append_rechecks_accepted_supplement_corrected_or_recalled_before_next_append(self):
        for index,kind,changes in ((11,'corrected',dict(text='更正朗读补充：不再要求录音上传成功确认。')),
                                    (21,'recalled',dict(text='[已撤回，正文未读取]',kind='recalled',unread=True))):
            with self.subTest(kind=kind):
                publisher='synthetic-history-'+kind
                original,task_id=self._school_append_original(index,title='英语：虚构'+kind+'场景朗读',publisher=publisher)
                accepted=self._school_append_candidate(index+1,'只补朗读：录音上传后确认上传成功。',change='append',target=task_id,publisher=publisher)
                self._school_append_auto(accepted)
                with self.app.connect() as c:
                    before=next(t for t in self.app.tasks(c) if t['id']==task_id)
                    canonical=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone())
                    receipt=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(accepted['id'],)).fetchone())
                    self.assertEqual((receipt['state'],receipt['task_id']),('accepted',task_id))
                    self.assertEqual(json.loads(receipt['plan'])['school_change_of'],original['id'])
                    message_id=str(index+1)
                    message=json.loads(c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',(self.source['id'],message_id)).fetchone()[0])
                    c.execute('UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?',(json.dumps(dict(message,**changes)),self.source['id'],message_id))
                    task_count=c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]
                pending=self._school_append_candidate(index+2,'只补朗读：确认上传后再检查音量清楚。',change='append',target=task_id,publisher=publisher)
                with patch.object(agent.family_llm,'_chat_json') as model,patch.object(agent,'_now',return_value=self.now):
                    result=agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
                self.assertEqual(result['created'],0)
                with self.app.connect() as c:
                    after=next(t for t in self.app.tasks(c) if t['id']==task_id)
                    self.assertEqual(after['action'],before['action'],'已接受的补充原消息失效后不能再向其要求追加')
                    row=c.execute('SELECT state,task_id,plan FROM agent_items WHERE id=?',(pending['id'],)).fetchone()
                    self.assertEqual((row['state'],row['task_id']),('pending',''))
                    self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
                    self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?',(original['id'],)).fetchone()),canonical)
                    self.assertEqual(dict(c.execute('SELECT * FROM agent_items WHERE id=?',(accepted['id'],)).fetchone()),receipt)
                    self.assertEqual(after['source'],before['source']);self.assertEqual(after['focus'],before['focus'])
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],task_count)
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_school_selection_discards_model_copy_of_existing_task(self):
        evidence=[dict(ref='message:synthetic-group:11',text='已签署',time=self.now.isoformat(),content_incomplete=False)]
        task=dict(id='task-1',title='语文：完成观察记录',goal='完成一份自己的观察记录。',due='',status='待跟进')
        proposal=school_proposal(title_quote='已处理',focus='school',due='',evidence=[dict(ref=evidence[0]['ref'])],learning_subject='',learning_goal_id='',
            task_title=task['title'],task_goal=task['goal'],task_advice='',task_state='ready',task_reason='模型整理',task_change='new',task_target_id=task['id'],task_purpose='learning')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            self.assertEqual(agent._select('school',evidence,school_goals=[],school_tasks=[task],as_of=self.now.date().isoformat()),[])
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[dict(proposal,task_goal='新增一项不同要求。')])):
            kept=agent._select('school',evidence,school_goals=[],school_tasks=[task],as_of=self.now.date().isoformat())
        self.assertEqual(len(kept),1);self.assertEqual(kept[0]['plan']['school_task']['state'],'review')
        cancelled=[dict(evidence[0],text='已取消')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[dict(proposal,title_quote=cancelled[0]['text'])])):
            kept=agent._select('school',cancelled,school_goals=[],school_tasks=[task],as_of=self.now.date().isoformat())
        self.assertEqual(len(kept),1)
        repeated=[dict(evidence[0],text='再做一次')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[dict(proposal,title_quote=repeated[0]['text'])])):
            kept=agent._select('school',repeated,school_goals=[],school_tasks=[task],as_of=self.now.date().isoformat())
        self.assertEqual(len(kept),1)
        dated=[dict(evidence[0],text='后天提交观察记录。')]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[dict(proposal,title_quote=dated[0]['text'],due='2026-02-12')])):
            kept=agent._select('school',dated,school_goals=[],school_tasks=[task],as_of=self.now.date().isoformat())
        self.assertEqual(len(kept),1);self.assertEqual(kept[0]['due'],'2026-02-12')

    def test_school_title_quote_falls_back_only_to_verified_source(self):
        ref = 'message:synthetic-group:11'
        source = '请带一本阅读材料，明天课堂使用。'
        proposal = school_proposal(title_quote='虚构' * 61, focus='school', due='', evidence=[dict(ref=ref)],
                        learning_subject='', learning_goal_id='')
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            items = agent._select('school', [dict(ref=ref, text=source)], school_goals=[], as_of='2026-02-10')
        self.assertEqual(items[0]['title'], '待核对：' + source)
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [dict(proposal, evidence=[dict(ref='message:other:11')])]}):
            with self.assertRaises(agent.AgentError):
                agent._select('school', [dict(ref=ref, text=source)], school_goals=[], as_of='2026-02-10')

    def test_school_feedback_and_old_today_do_not_become_new_homework(self):
        report='中秋假期作业反馈：\n左列：《秋天的怀念》学案。\n右列：阅读单。'
        waiting='试卷在孩子们自己手里，答题卡还没取回，下午拿到后发'
        claimed=dict(title='语文：完成学案',goal='完成学案',advice='',state='ready',reason='模型猜测')
        completed='上图是今日语文作业完成情况。\n第二列：《济南的冬天》读读写写抄写。'
        answer='今日阅读单答案：\n七、《父亲的病》\n答案：装腔作势。'
        for text in (report,waiting,completed,answer,'语文订正作业答案\n三、《二十四孝图》'):
            self.assertEqual(agent._school_brief(claimed,evidence=[dict(text=text)])['state'],'reference')
        self.assertEqual(agent._school_brief(claimed,evidence=[dict(text=report+'\n请今天订正。')])['state'],'ready')
        ref='message:synthetic-group:old'
        source='今天家庭作业就是完成数学资料33和34页。'
        proposal=school_proposal(title_quote=source,focus='school',due='',evidence=[dict(ref=ref)],learning_subject='',learning_goal_id='',
                      task_title='数学：完成资料33和34页',task_goal='完成资料33和34页',task_advice='',task_state='ready',task_reason='明确作业',task_purpose='learning')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])):
            item=agent._select('school',[dict(ref=ref,text=source,time='2026-09-23T18:19:39+08:00')],school_goals=[],as_of='2026-09-28')[0]
        self.assertEqual(item['due'],'2026-09-23')
        self.assertEqual(item['plan']['school_task']['state'],'review')

    def test_short_group_acknowledgements_never_become_school_tasks(self):
        receipts=[dict(ref='message:synthetic-group:'+str(i),text=text,time='2026-09-28T17:00:00+08:00')
                  for i,text in enumerate(('已上传','是的','收到。'))]
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('acknowledgements need no model')):
            self.assertEqual(agent._select('school',receipts,school_goals=[],as_of='2026-09-28'),[])
        action=dict(ref='message:synthetic-group:action',text='请明天带练习本。',time='2026-09-28T17:01:00+08:00')
        proposal=school_proposal(title_quote=action['text'],focus='school',due='',evidence=[dict(ref=action['ref'])],learning_subject='',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])) as model:
            self.assertEqual(len(agent._select('school',receipts+[action],school_goals=[],as_of='2026-09-28')),1)
        self.assertEqual(len(json.loads(model.call_args.args[0][1]['content'])['evidence']),1)

    def payload(self, expected='10', cursor='11', message='11', offset=0):
        stamp = (self.now + dt.timedelta(minutes=offset)).isoformat()
        return dict(source_id=self.source['id'], expected_cursor=expected, cursor=cursor,
                    checked_at=stamp, last_message_time=stamp, error='',
                    messages=[dict(id=message, time=stamp, kind='text', sender='示例老师', text='待核对原文：明天带阅读材料。', unread=False)])

    def record(self, note='孩子自述：愿意谈谈阅读。', source='家长记录', care_choice='', care_review_on=''):
        with self.app.connect() as c:
            return c.execute('INSERT INTO records(child,day,category,subject,title,note,source,created,care_choice,care_review_on) VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('示例甲', '2026-02-10', '学习进展', '语文', '待核对原文', note, source, self.now.isoformat(), care_choice, care_review_on)).lastrowid

    def model(self, messages, schema, name, timeout, *, data_path=None):
        self.assertEqual(data_path,self.app.DATA)
        # A model call must not hold a write transaction or make basic operations wait.
        with sqlite3.connect(self.app.DB, timeout=0.1) as c:
            c.execute('BEGIN IMMEDIATE'); c.rollback()
        value = json.loads(messages[-1]['content'])
        self.assertEqual(value['as_of'], self.now.astimezone(agent.TZ).date().isoformat())
        if name == 'family_agent_plan':
            quote = value['evidence'][0]['text'][:40]
            return {'proposal': dict(title='回看这次阅读', goal='能说出一次实际想法', action='一起说一说这次阅读中最想保留的一点。',
                why_now='这条记录保留了本次实际表达。', estimated_minutes=10, review_on=value['as_of'],
                evidence=[{'ref': value['evidence'][0]['ref'], 'quote': quote}])}
        if 'learning_goals' in value:
            return {'proposals': [school_proposal(evidence=[dict(ref=e['ref']) for e in value['evidence']])]}
        return {'proposals': [dict(title_quote='待核对原文', focus='school' if value['mode'] == 'school' else 'listen', due='',
            evidence=[{'ref': value['evidence'][0]['ref'], 'quote': '待核对原文'}])]}

    def test_school_backfill_is_bounded_preserves_decisions_and_does_not_invent_work(self):
        cases=[('clear','语文：完成虚构习作。'),('legend','第一列：虚构练习订正记录。\n第二列：虚构课堂默写成绩。'),
               ('unread','今天抄写任务[图片]'),('expired','2026-02-09前完成练习。'),('accepted','带虚构材料。'),('dismissed','交虚构回执。')]
        payload=self.payload();payload['messages']=[dict(id=str(i+11),time=self.now.isoformat(),kind='text',sender='示例老师',text=text,unread=name=='unread') for i,(name,text) in enumerate(cases)];payload['cursor']='16'
        self.store.ingest(payload);ids={}
        for i,(name,text) in enumerate(cases):
            key='synthetic-backfill:'+name;fp=self.store._job(key,name,self.now)
            item=dict(child_id='child-1',kind='school',title=name,body='旧说明',evidence=[dict(ref='message:synthetic-group:'+str(i+11),text=text)],due='2026-02-09' if name=='expired' else '')
            if name=='legend':item['plan']={'school_learning':{'subject':'语文','goal_id':''},'school_messages':[dict(source_id='synthetic-group',message_id=str(i+11))]}
            self.store._save(key,fp,[item],self.now+dt.timedelta(seconds=i))
            with self.app.connect() as c:ids[name]=c.execute('SELECT id FROM agent_items WHERE job_id=?',(key,)).fetchone()[0]
        for name in ('accepted','dismissed'):self.store.act(dict(id=ids[name],action='accept' if name=='accepted' else 'dismiss'))
        with self.app.connect() as c:before=[tuple(r) for r in c.execute("SELECT * FROM agent_items WHERE state!='pending' ORDER BY id")]
        order=[]
        def model(messages,*args,**kwargs):
            with sqlite3.connect(self.app.DB,timeout=.1) as c:c.execute('BEGIN IMMEDIATE');c.rollback()
            ctx=json.loads(messages[-1]['content']);order.append(ctx['candidate']);self.assertEqual(ctx['as_of'],'2026-02-10')
            self.assertTrue(ctx['evidence'][0]['text']);self.assertEqual(ctx['child_id'],'child-1')
            return dict(title='语文：完成虚构习作',goal='提交一篇自己的习作。',advice='可以先口述。',state='ready',reason='这是表格说明。' if ctx['candidate']=='legend' else '明确学校要求。',change='new',target_id='',purpose='learning',submission='',learning_subject='语文',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as mocked:
            for i in range(3):self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=i+1),1)['used'],1)
            self.assertEqual(agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=6),1)['used'],0)
            self.assertEqual(mocked.call_count,3)
        self.assertEqual(order,['expired','unread','clear'])
        with self.app.connect() as c:
            rows={r['id']:dict(r) for r in c.execute('SELECT * FROM agent_items')}
            self.assertEqual(before,[tuple(r) for r in c.execute("SELECT * FROM agent_items WHERE id IN (?,?) ORDER BY id",(ids['accepted'],ids['dismissed']))])
            tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks')];self.assertEqual(len(tasks),2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)
        self.assertEqual(rows[ids['clear']]['state'],'accepted');self.assertTrue(json.loads(rows[ids['clear']]['plan'])['school_task']['auto_added'])
        for name in ('unread','expired'):
            self.assertEqual(rows[ids[name]]['state'],'pending');self.assertEqual(json.loads(rows[ids[name]]['plan'])['school_task']['state'],'review')
        self.assertEqual(json.loads(rows[ids['unread']]['plan'])['school_task']['title'],'')
        self.assertNotIn('school_learning',json.loads(rows[ids['legend']]['plan']))
        import family_agenda
        inbox=family_agenda.snapshot(self.app,'2026-02-10','2026-02-10')['inbox']
        self.assertNotIn(ids['legend'],[r['id'] for r in inbox]);self.assertIn(ids['legend'],[r['id'] for r in self.store.snapshot()['items']])

    def test_new_school_notice_uses_one_selection_and_reference_creates_no_learning_goal(self):
        self.store.ingest(self.payload())
        def select(messages,schema,name,**kwargs):
            ctx=json.loads(messages[-1]['content']);self.assertEqual(ctx['mode'],'school')
            return {'proposals':[school_proposal(title_quote='待核对原文',focus='school',due='',learning_subject='',learning_goal_id='',
                task_title='带阅读材料',task_goal='带一份阅读材料到校。',task_advice='可以提前放入书包。',task_state='ready',task_reason='全班明确要求。',task_purpose='admin',evidence=[dict(ref=ctx['evidence'][0]['ref'])])]}
        with patch.object(agent.family_llm,'_chat_json',side_effect=select) as mocked:
            agent.run_once(self.app,self.now);self.assertEqual(mocked.call_count,1)
            agent.run_once(self.app,self.now+dt.timedelta(minutes=1));self.assertEqual(mocked.call_count,1)
        with self.app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],1)
        proposal=select([dict(content=json.dumps(dict(mode='school',evidence=[dict(ref='message:synthetic-group:11')])) )],None,None)
        proposal['proposals'][0].update(task_state='reference',learning_subject='语文',task_reason='成绩列说明。')
        with patch.object(agent.family_llm,'_chat_json',return_value=proposal):
            selected=agent._select('school',[dict(ref='message:synthetic-group:11',text='待核对原文：第一列是默写成绩。')],school_goals=[])
        self.assertNotIn('school_learning',selected[0]['plan'])

    def test_auto_collection_error_leaves_review_and_does_not_block_other_notices(self):
        self.store.ingest(self.payload());key='synthetic-auto-error';fp=self.store._job(key,{},self.now)
        brief=agent._school_brief(dict(title='准备材料',goal='带材料到校。',advice='',state='ready',reason='明确要求'))
        self.store._save(key,fp,[dict(child_id='child-1',kind='school',title='准备材料',body='带材料到校。',plan={'school_task':brief},evidence=[dict(ref='message:synthetic-group:11',text='准备材料')])],self.now)
        with patch.object(self.store,'act',side_effect=agent.AgentError('synthetic invalid task',400)) as action,patch.object(agent.family_llm,'_chat_json') as model:
            result=agent._refresh_school(self.app,self.store,self.now,1)
            self.assertEqual(result['failed'],1);self.assertEqual(result['created'],0)
            agent._refresh_school(self.app,self.store,self.now+dt.timedelta(minutes=1),1)
            self.assertEqual(action.call_count,1);model.assert_not_called()
        with self.app.connect() as c:
            plan=json.loads(c.execute('SELECT plan FROM agent_items WHERE job_id=?',(key,)).fetchone()[0]);self.assertEqual(plan['school_task']['state'],'review')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)

    def test_resource_request_is_reference_in_new_and_saved_notices_without_hiding_instructions(self):
        text='有没有家长能拍一下科学第8页的观察记录？谢谢'
        payload=self.payload();payload['messages'][0]['text']=text;self.store.ingest(payload)
        evidence=[dict(ref='message:synthetic-group:11',text=text,content_incomplete=False)]
        wrong=school_proposal(title_quote='科学第8页',focus='school',due='',learning_subject='科学',learning_goal_id='',
            task_title='科学：核对观察记录',task_goal='找到观察记录并完成。',task_advice='',task_state='ready',task_reason='提到课程。',task_purpose='learning',evidence=[dict(ref=evidence[0]['ref'])])
        with patch.object(agent.family_llm,'_chat_json',return_value={'proposals':[wrong]}):
            selected=agent._select('school',evidence,school_goals=[])
        self.assertEqual(selected[0]['plan']['school_task']['state'],'reference')
        self.assertNotIn('school_learning',selected[0]['plan'])
        key='synthetic-resource-request';fp=self.store._job(key,{},self.now)
        self.store._save(key,fp,[dict(child_id='child-1',kind='school',title='旧资料求助候选',body='旧说明',evidence=evidence,
            plan={'school_learning':{'subject':'科学','goal_id':''},'school_messages':[dict(source_id='synthetic-group',message_id='11')]})],self.now)
        with patch.object(agent.family_llm,'_chat_json') as model:
            result=agent._refresh_school(self.app,self.store,self.now,0);model.assert_not_called()
        self.assertEqual(result,dict(used=0,failed=0,created=0))
        import family_goals,family_agenda
        self.assertEqual(family_goals.Store(self.app,self.store).route_school(),0)
        self.assertEqual(family_agenda.snapshot(self.app,'2026-02-10','2026-02-10')['inbox'],[])
        with self.app.connect() as c:
            row=c.execute('SELECT * FROM agent_items WHERE job_id=?',(key,)).fetchone()
            self.assertEqual(json.loads(row['plan'])['school_task']['state'],'reference')
            self.assertNotIn('school_learning',json.loads(row['plan']))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(json.loads(c.execute('SELECT payload FROM agent_messages').fetchone()[0])['text'],text)
        ready=dict(title='科学：完成观察记录',goal='完成记录并带到课堂。',advice='',state='ready',reason='明确要求。')
        instruction='请同学们完成科学第8页的观察记录，明天带来。'
        for texts in ([instruction],[text,instruction],[text+'\n老师要求：完成观察记录。']):
            self.assertEqual(agent._school_brief(ready,evidence=[dict(text=t) for t in texts])['state'],'ready')
        self.assertEqual(agent._school_brief(ready,incomplete=True,evidence=[dict(text=text,unread=True)])['state'],'review')

    def _resource_request_selection(self,text,actions,*,unread=False,incomplete=False):
        ref='message:'+self.source['id']+':11'
        proposals=[school_proposal(evidence=[dict(ref=ref)],**action) for action in actions]
        evidence=[dict(ref=ref,text=text,time=self.now.isoformat(),kind='text',unread=unread,
                       content_incomplete=incomplete or unread)]
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)) as model:
            items=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(model.call_count,1,'selection uses one fixed fictional response')
        self.assertTrue(all(item['evidence']==[dict(ref=ref,text=text)] for item in items))
        return items

    def _collect_resource_request_items(self,text,items,*,unread=False):
        payload=self.payload();payload['messages'][0].update(text=text,unread=unread)
        self.store.ingest(payload)
        key='synthetic-resource-request-mixed';fp=self.store._job(key,dict(text=text),self.now)
        self.store._save(key,fp,[dict(item,child_id='child-1',kind='school') for item in items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('saved fictional selection needs no model')):
            first=agent._refresh_school(self.app,self.store,self.now,0)
            repeated=agent._refresh_school(self.app,self.store,self.now,0)
        self.assertEqual(repeated,dict(used=0,failed=0,created=0))
        with self.app.connect() as c:
            tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks ORDER BY due,title')]
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)
            self.assertTrue(all(t['original_status']=='待跟进' for t in tasks))
        self.assertEqual(first['created'],len(tasks))
        return tasks

    def test_resource_request_only_keeps_reference_without_tasks(self):
        text='谁有语文课本第5课照片，发一下。'
        items=self._resource_request_selection(text,[dict(title_quote='语文课本第5课',due='',learning_subject='语文',
            task_title='语文：朗读第5课',task_goal='朗读第5课两遍。',task_state='ready',
            task_reason='故意错误的固定回执，求助不能变成作业。',task_purpose='learning')])
        self.assertEqual(items[0]['plan']['school_task']['state'],'reference')
        self.assertNotIn('school_learning',items[0]['plan'])
        self.assertEqual(items[0]['due'],'','sending day is not an unstated deadline')
        self.assertEqual(self._collect_resource_request_items(text,items),[])

    def test_resource_request_direct_subject_action_survives_same_message(self):
        cases=[('谁有语文课本照片，发一下。','语文作业：明天朗读第5课两遍。','语文','语文：朗读第5课两遍'),
               ('有没有家长有数学练习册，拍一下？\n','数学作业：明天完成第8页第1至3题，第4题选做。','数学','数学：练习册第8页'),
               ('谁有英语课本照片，发到群；','英语：明天背诵Unit5，不用录音。','英语','英语：背诵Unit5')]
        for request,action,subject,title in cases:
            with self.subTest(subject=subject):
                items=self._resource_request_selection(request+action,[dict(title_quote=action,due='2026-02-11',
                    learning_subject=subject,task_title=title,task_goal=action,task_state='ready',
                    task_reason='科目和独立动作直接见原文，不需要老师要求或请同学们前缀。',task_purpose='learning')])
                self.assertEqual(len(items),1)
                item=items[0];brief=item['plan']['school_task']
                self.assertEqual((brief['state'],brief['purpose'],item['title'],item['body'],item['due']),
                                 ('ready','learning',title,action,'2026-02-11'))
                self.assertEqual(item['plan']['school_learning'],dict(subject=subject,goal_id=''))

    def test_resource_request_mixed_actions_keep_independent_tasks_and_dates(self):
        request='谁有语文课本照片，发一下。'
        reading='语文作业：2026-02-11朗读第5课两遍，不用录音。'
        math='数学作业：2026-02-12完成练习册第8页第1至3题，第4题选做，做完检查。'
        receipt='家长事务：2026-02-13签字交回独立活动回执，无需盖章。'
        text=request+'\n'+reading+'\n'+math+'\n'+receipt
        actions=[dict(title_quote=request,due='',task_title='课本照片求助',task_goal='询问课本照片。',
                      task_state='reference',task_reason='资料求助单独保留。',task_purpose='optional'),
                 dict(title_quote=reading,due='2026-02-11',learning_subject='语文',task_title='语文：朗读第5课',
                      task_goal=reading,task_state='ready',task_reason='独立朗读要求。',task_purpose='learning'),
                 dict(title_quote=math,due='2026-02-12',learning_subject='数学',task_title='数学：练习册第8页',
                      task_goal=math,task_state='ready',task_reason='独立做题要求。',task_purpose='learning'),
                 dict(title_quote=receipt,due='2026-02-13',task_title='事务：独立活动回执',task_goal=receipt,
                      task_state='ready',task_reason='独立回执，不是朗读或练习册的提交。',task_purpose='admin')]
        items=self._resource_request_selection(text,actions)
        self.assertEqual([i['plan']['school_task']['state'] for i in items],['reference','ready','ready','ready'])
        self.assertEqual([(i['title'],i['body'],i['due']) for i in items[1:]],
                         [(actions[i]['task_title'],actions[i]['task_goal'],actions[i]['due']) for i in range(1,4)])
        tasks=self._collect_resource_request_items(text,items)
        self.assertEqual([(t['title'],t['action'],t['due']) for t in tasks],
                         [(actions[i]['task_title'],actions[i]['task_goal'],actions[i]['due']) for i in range(1,4)])
        self.assertTrue(all(t['child']=='示例甲' and text in t['source'] for t in tasks))
        with self.app.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_items WHERE state='accepted'").fetchone()[0],3)
            reference=c.execute("SELECT plan FROM agent_items WHERE state='pending'").fetchone()
            self.assertEqual(json.loads(reference['plan'])['school_task']['state'],'reference')

    def test_resource_request_independent_admin_action_survives_same_message(self):
        cases=[('谁有活动回执文件，发一下。','家长事务：明天签字交回独立活动回执，无需盖章。'),
               ('谁有活动回执文件，发一下，','家长事务：明天签字并盖章后交回独立活动回执。')]
        for request,action in cases:
            with self.subTest(action=action):
                items=self._resource_request_selection(request+action,[dict(title_quote=action,due='2026-02-11',
                    task_title='事务：独立活动回执',task_goal=action,task_state='ready',
                    task_reason='正文直接声明独立行政要求。',task_purpose='admin')])
                self.assertEqual((items[0]['plan']['school_task']['state'],items[0]['plan']['school_task']['purpose']),('ready','admin'))
                self.assertEqual(items[0]['body'],action,'affirmative and negated stamping requirements remain distinct')
                self.assertNotIn('school_learning',items[0]['plan'])
        tasks=self._collect_resource_request_items(request+action,items)
        self.assertEqual([(t['title'],t['action'],t['due']) for t in tasks],
                         [('事务：独立活动回执',action,'2026-02-11')])

    def test_literal_independent_admin_date_cannot_borrow_or_truncate_an_action(self):
        quote='家长事务：2026-02-13签字交回独立活动回执，无需盖章。'
        evidence=[dict(text='2026-02-11朗读第5课两遍。\n'+quote,time=self.now.isoformat())]
        self.assertTrue(agent._school_dated_quote(quote,evidence,'2026-02-13',dict(goal=quote)))
        self.assertTrue(agent._school_dated_quote(quote,evidence,'2026-02-13',dict(goal='签字交回独立活动回执，无需盖章。')))
        for title,goal,due in [(quote,quote,'2026-02-11'),
                               (quote,quote.replace('独立活动回执','另一份报名表'),'2026-02-13'),
                               ('2026-02-13', '2026-02-13','2026-02-13'),
                               (quote[:-9],quote[:-9],'2026-02-13')]:
            with self.subTest(quote=title,goal=goal,due=due):
                self.assertFalse(agent._school_dated_quote(title,evidence,due,dict(goal=goal)))
        other=[dict(text=quote,time=self.now.isoformat()),dict(text=quote,time=self.now.isoformat())]
        self.assertFalse(agent._school_dated_quote(quote,other,'2026-02-13',dict(goal=quote)))

    def test_dated_admin_quote_distinguishes_named_receipts(self):
        quote='家长事务：2026-02-13签字交回防溺水回执，无需盖章。'
        evidence=[dict(text='2026-02-11朗读第5课两遍。\n'+quote,time=self.now.isoformat())]
        correct='签字交回防溺水回执，无需盖章。'
        wrong='签字交回外出活动回执，无需盖章。'
        self.assertTrue(agent._school_dated_quote(quote,evidence,'2026-02-13',dict(goal=correct)),
                        'the same named receipt may omit the administrative and date labels')
        self.assertFalse(agent._school_dated_quote(quote,evidence,'2026-02-13',dict(goal=wrong)),
                         'a shared receipt category cannot ground a different named receipt')
        for initial in ('和','并','将','把','请'):
            with self.subTest(name_initial=initial):
                named='签字交回'+initial+'美校园活动回执。'
                original='家长事务：2026-02-13'+named
                self.assertFalse(agent._school_dated_quote(original,[dict(text=original,time=self.now.isoformat())],
                                 '2026-02-13',dict(goal=named.replace(initial+'美','美'))),
                                 'a name initial is not a connector unless followed by another action')

    def test_dated_admin_object_mismatch_never_auto_collects_wrong_receipt(self):
        reading='语文作业：2026-02-11朗读第5课两遍。'
        quote='家长事务：2026-02-13签字交回防溺水回执，无需盖章。'
        text='谁有活动回执文件，发一下。\n'+reading+'\n'+quote
        cases=[('事务：防溺水回执','签字交回防溺水回执，无需盖章。','ready'),
               ('事务：外出活动回执','签字交回外出活动回执，无需盖章。','review')]
        for title,goal,state in cases:
            with self.subTest(goal=goal):
                items=self._resource_request_selection(text,[
                    dict(title_quote=reading,due='2026-02-11',learning_subject='语文',task_title='语文：朗读第5课',
                         task_goal=reading,task_state='ready',task_reason='固定正确的独立朗读。',task_purpose='learning'),
                    dict(title_quote=quote,due='2026-02-13',task_title=title,task_goal=goal,task_state='ready',
                         task_reason='固定行政回执，用实际对象核对日期身份。',task_purpose='admin')])
                self.assertEqual([i['plan']['school_task']['state'] for i in items],['ready',state])
                self.assertEqual((items[0]['body'],items[0]['due']),(reading,'2026-02-11'))
                self.assertEqual((items[1]['title'],items[1]['body'],items[1]['due']),(title,goal,'2026-02-13'))
        self.assertNotIn('外出活动回执',text,'the teacher never stated the incorrectly substituted receipt')
        tasks=self._collect_resource_request_items(text,items)
        self.assertEqual([(t['title'],t['action'],t['due']) for t in tasks],
                         [('语文：朗读第5课',reading,'2026-02-11')])
        with self.app.connect() as c:
            pending=c.execute("SELECT state,task_id,body,plan FROM agent_items WHERE title='事务：外出活动回执'").fetchone()
            self.assertEqual((pending['state'],pending['task_id'],pending['body']),('pending','',cases[1][1]))
            self.assertEqual(json.loads(pending['plan'])['school_task']['state'],'review')
            self.assertIn('原通知含多个日期',json.loads(pending['plan'])['school_task']['reason'])

    def test_resource_request_unread_or_unknown_material_keeps_review(self):
        cases=[('谁有语文课本照片，发一下。',True,True,'learning'),
               ('谁有数学作业照片，发一下。其他要求见未读图片。',False,True,'learning'),
               ('https://example.invalid/synthetic-homework',False,False,'unknown')]
        for text,unread,incomplete,purpose in cases:
            with self.subTest(text=text):
                items=self._resource_request_selection(text,[dict(title_quote=text[:30],due='',learning_subject='数学',
                    task_title='数学：完成练习',task_goal='完成第1至3题。',task_state='ready',
                    task_reason='故意猜测的固定回执，不能代替尚未读取的要求。',task_purpose=purpose)],
                    unread=unread,incomplete=incomplete)
                brief=items[0]['plan']['school_task']
                self.assertEqual(brief['state'],'review')
                self.assertEqual(items[0]['due'],'','unknown material cannot borrow the sending day as a deadline')
                self.assertNotIn('school_learning',items[0]['plan'])
                if purpose=='unknown':self.assertEqual((brief['title'],brief['goal']),('',''))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)

    def _recover_processed_resource_request_reference(self,*,expired=False):
        from test_school_history import SchoolHistoryTests
        request='谁有语文课本照片，发一下。'
        reading='语文作业：明天朗读第5课两遍。'
        text=request+reading;ref='message:'+self.source['id']+':11'
        payload=self.payload();payload['messages'][0]['text']=text
        self.store.ingest(payload)
        old_items=self._resource_request_selection(text,[dict(title_quote=request,due='',
            task_title='群内资料求助',task_goal='本条是在询问资料，尚未给出本家庭须完成的学校要求。',
            task_state='reference',task_reason='固定旧误判：整条混合消息被当成资料求助。',task_purpose='optional')])
        old_items[0]['plan']['school_selection_revision']=agent.SCHOOL_SELECTION_REVISION-1
        old_key='messages:synthetic-old-resource-reference'
        fp=self.store._job(old_key,dict(school_learning_policy=8,messages=payload['messages']),self.now)
        self.store._save(old_key,fp,[dict(item,child_id='child-1',kind='school') for item in old_items],self.now,
                         [(self.source['id'],'11')],school_context=(self.source,payload['messages']))
        with self.app.connect() as c:
            old=dict(c.execute('SELECT * FROM agent_items WHERE job_id=?',(old_key,)).fetchone())
            self.assertEqual((old['state'],json.loads(old['plan'])['school_task']['state']),('pending','reference'))
            self.assertNotIn('school_action_anchor',json.loads(old['plan']),'do not manufacture a literal anchor on the old generic reference')

        def protected():
            with self.app.connect() as c:
                return dict(sources=[dict(r) for r in c.execute('SELECT * FROM agent_sources ORDER BY id')],
                    messages=[dict(r) for r in c.execute('SELECT * FROM agent_messages ORDER BY source_id,id')],
                    old_job=dict(c.execute('SELECT * FROM agent_jobs WHERE id=?',(old_key,)).fetchone()),
                    old_item=dict(c.execute('SELECT * FROM agent_items WHERE id=?',(old['id'],)).fetchone()))

        before=protected()
        self.assertEqual((before['sources'][0]['cursor'],before['messages'][0]['processed']),('11',1))
        history=SchoolHistoryTests(methodName='runTest')
        history.fixture=self;history.app=self.app;history.store=self.store;history.calls=[]
        history.clock=self.now+dt.timedelta(days=2 if expired else 0)
        history.history_response=dict(proposals=[
            school_proposal(title_quote=request,action_quote=request,existing_item_id=old['id'],evidence=[dict(ref=ref)],
                task_title='群内资料求助',task_goal=request,task_state='reference',task_reason='原求助决定保留。',task_purpose='optional'),
            school_proposal(title_quote=reading,action_quote=reading,existing_item_id='',due='2026-02-11',evidence=[dict(ref=ref)],
                learning_subject='语文',task_title='语文：朗读第5课两遍',task_goal=reading,task_state='ready',
                task_reason='旧混合消息中的独立朗读要求，按原发送日换算明天。',task_purpose='learning')])
        with patch.object(agent,'_now',return_value=history.clock),patch.object(agent.family_llm,'_chat_json',side_effect=history._model) as model:
            scopes=agent._history_scopes(self.store,self.store._config())
            self.assertEqual(len(scopes),1,'an older selection revision opens only the bounded processed scope')
            first=agent._recheck_school_history(self.app,self.store,history.clock,1,scopes)
            self.assertEqual((first['used'],first['failed']),(1,0))
            # The ordinary tick runs the shared auto-collection after history
            # selection. A selection receipt alone is not a saved task.
            agent._refresh_school(self.app,self.store,history.clock,0)
            recovered=history._history_rows()
            self.assertEqual(len(recovered),1,'keep the old reference instead of duplicating it')
            row=recovered[0]
            self.assertEqual((row['body'],row['due'],row['state']),
                             (reading,'2026-02-11','pending' if expired else 'accepted'))
            self.assertEqual(json.loads(row['plan'])['school_action_anchor'],{ref:reading})
            self.assertEqual(protected(),before,'old job, processed message, cursor and reference decision stay byte-for-byte saved')
            repeated=agent._recheck_school_history(self.app,self.store,history.clock,1,
                agent._history_scopes(self.store,self.store._config()))
            self.assertEqual(repeated,dict(used=0,failed=0,created=0))
            self.assertEqual(model.call_count,1)
            self.assertEqual(history._history_rows(),recovered)
        with self.app.connect() as c:
            tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks')]
            self.assertEqual(len(tasks),0 if expired else 1)
            if tasks:
                self.assertEqual((tasks[0]['child'],tasks[0]['action'],tasks[0]['due'],tasks[0]['original_status']),
                                 ('示例甲',reading,'2026-02-11','待跟进'))
            else:
                self.assertEqual(json.loads(row['plan'])['school_task']['state'],'review')
                self.assertIn('原截止日期已过',json.loads(row['plan'])['school_task']['reason'])
                self.assertNotEqual(row['due'],history.clock.date().isoformat(),'expired homework must not be reassigned to today')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)
        self.assertEqual(protected(),before)

    def test_processed_resource_request_reference_recovers_reading_once(self):
        self._recover_processed_resource_request_reference()

    def test_processed_resource_request_reference_does_not_make_expired_reading_today(self):
        self._recover_processed_resource_request_reference(expired=True)

    def test_school_links_keep_purpose_unknowns_and_the_homework_submission_relation(self):
        ref='message:synthetic-group:11'
        base=dict(focus='school',due='',learning_subject='',learning_goal_id='',task_title='',task_goal='',task_advice='',task_state='review',
            task_reason='',task_change='new',task_target_id='',task_purpose='unknown',task_submission='',evidence=[dict(ref=ref)])
        def select(text,*models,incomplete=False):
            with patch.object(agent.family_llm,'_chat_json',return_value={'proposals':[dict(base,title_quote=text[:20],**m) for m in models]}):
                return agent._select('school',[dict(ref=ref,text=text,content_incomplete=incomplete)],school_goals=[],as_of='2026-02-10')
        # Pure sign-in and mandatory receipt: at most a school to-do, never a learning goal even if the model names a subject.
        for text,title in [('请各位家长点击链接完成今日到校签到 https://example.invalid/sign','完成到校签到'),('请全体家长今晚前填写防溺水回执并提交 https://example.invalid/receipt','填写防溺水回执')]:
            item=select(text,dict(task_title=title,task_goal=title+'。',task_state='ready',task_reason='全班明确要求。',task_purpose='admin',learning_subject='语文'))[0]
            brief=item['plan']['school_task'];self.assertEqual((brief['state'],brief['purpose'],brief['link_read']),('ready','admin',False))
            self.assertNotIn('school_learning',item['plan']);self.assertIn('链接页面未读取',brief['reason']);self.assertIn(brief['links'][0],item['evidence'][0]['text'])
        # Optional publicity stays material: never an automatic must-do or a goal.
        text='自愿参加：周末科普讲座，感兴趣的家庭可以了解 https://example.invalid/talk'
        item=select(text,dict(task_title='参加科普讲座',task_goal='周末参加科普讲座。',task_state='ready',task_purpose='optional',learning_subject='科学'))[0]
        self.assertEqual(item['plan']['school_task']['state'],'review');self.assertIn('不自动加入必做',item['plan']['school_task']['reason']);self.assertNotIn('school_learning',item['plan'])
        self.assertEqual(select(text,dict(task_title='科普讲座宣传',task_goal='自愿了解。',task_state='reference',task_purpose='optional'))[0]['plan']['school_task']['state'],'reference')
        # Homework written in the message text is extracted; the page behind the link is never claimed as read.
        text='语文：请阅读《示例寓言》第一章，明天课堂分享一个情节。材料见 https://example.invalid/read'
        item=select(text,dict(task_title='语文：阅读《示例寓言》第一章',task_goal='阅读第一章，明天课堂分享一个情节。',task_state='ready',task_reason='正文写明要求。',task_purpose='learning',learning_subject='语文'))[0]
        brief=item['plan']['school_task'];self.assertEqual((brief['state'],brief['links'],brief['link_read']),('ready',['https://example.invalid/read'],False))
        self.assertEqual(item['plan']['school_learning'],dict(subject='语文',goal_id=''));self.assertIn('只依据消息正文',brief['reason'])
        # An exercise known only by its address, bare short links and login links stay unknown whatever the model guesses.
        guess=dict(task_title='英语：完成打卡',task_goal='打开链接完成今日英语打卡。',task_state='ready',task_reason='老师发布。',task_purpose='learning',task_submission='打卡',learning_subject='英语')
        item=select('数学在线练习 https://example.invalid/quiz',dict(guess,task_purpose='unknown'))[0]
        self.assertEqual((item['plan']['school_task']['state'],item['plan']['school_task']['goal']),('review',''));self.assertNotIn('school_learning',item['plan'])
        for text in ['https://t.example/AbC12','t.example/AbC12','请登录后查看 https://example.invalid/login?next=hw','各位家长请点击链接：www.example.invalid/x']:
            item=select(text,guess)[0];brief=item['plan']['school_task']
            self.assertEqual((brief['state'],brief['purpose'],brief['title'],brief['goal']),('review','unknown','',''),text)
            self.assertNotIn('school_learning',item['plan']);self.assertNotIn('submission',brief);self.assertIn('用途和内容待核对',brief['reason'])
            self.assertTrue(item['title'].startswith('待核对：'));self.assertIn(text,item['evidence'][0]['text'])
        # Read aloud then check in: one item keeps the activity and its submission; a split check-in is not auto-added twice.
        text='今晚语文作业：朗读第5课课文三遍，录音后上传到班级小程序打卡 https://example.invalid/clock'
        learning=dict(task_title='语文：朗读第5课课文',task_goal='朗读第5课课文三遍。',task_state='ready',task_reason='正文写明作业。',task_purpose='learning',task_submission='录音后上传到班级小程序打卡。',learning_subject='语文')
        split=dict(task_title='班级小程序打卡',task_goal='在班级小程序打卡。',task_state='ready',task_reason='要求打卡。',task_purpose='admin')
        items=select(text,learning,split);brief=items[0]['plan']['school_task']
        self.assertEqual((brief['state'],brief['submission']),('ready','录音后上传到班级小程序打卡。'));self.assertIn('school_learning',items[0]['plan'])
        self.assertEqual(items[0]['body'],'朗读第5课课文三遍。\n提交要求：录音后上传到班级小程序打卡。')
        self.assertEqual(items[1]['plan']['school_task']['state'],'review');self.assertIn('避免重复',items[1]['plan']['school_task']['reason']);self.assertNotIn('school_learning',items[1]['plan'])
        item=select(text,dict(split,task_title='语文：朗读打卡',task_goal='朗读第5课课文三遍并打卡。'))[0]
        self.assertEqual(item['plan']['school_task']['state'],'review');self.assertIn('请核对是否含作业',item['plan']['school_task']['reason']);self.assertIn('朗读',item['body'])
        # Mixed attachment: the unread original keeps the existing gap; nothing is guessed from the link.
        item=select('[图片]\n今日作业见图，完成后打卡 https://example.invalid/clock',learning,incomplete=True)[0]
        self.assertEqual((item['plan']['school_task']['state'],item['plan']['school_task']['title']),('review',''));self.assertNotIn('school_learning',item['plan'])
        # Through the product entry: an unknown link waits for the parent with its original message; homework becomes one open task.
        payload=self.payload();payload['messages'][0]['text']='https://t.example/AbC12';self.store.ingest(payload)
        def model(messages,schema,name,**kwargs):
            entry=json.loads(messages[-1]['content'])['evidence'][0]
            return {'proposals':[dict(base,title_quote=entry['text'][:20],**dict(learning if '朗读' in entry['text'] else guess,learning_subject=''),evidence=[dict(ref=entry['ref'])])]}
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as mocked:
            agent.run_once(self.app,self.now);agent.run_once(self.app,self.now+dt.timedelta(minutes=1));self.assertEqual(mocked.call_count,1)
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
                row=c.execute("SELECT state,plan FROM agent_items WHERE kind='school'").fetchone()
                self.assertEqual((row['state'],json.loads(row['plan'])['school_task']['purpose']),('pending','unknown'))
                self.assertEqual(json.loads(c.execute('SELECT payload FROM agent_messages').fetchone()[0])['text'],'https://t.example/AbC12')
            later=self.payload(expected='11',cursor='12',message='12',offset=2);later['messages'][0]['text']=text;self.store.ingest(later)
            agent.run_once(self.app,self.now+dt.timedelta(minutes=3));agent.run_once(self.app,self.now+dt.timedelta(minutes=4));self.assertEqual(mocked.call_count,2)
        with self.app.connect() as c:
            tasks=c.execute('SELECT * FROM manual_tasks').fetchall();self.assertEqual(len(tasks),1)
            self.assertIn('提交要求：',tasks[0]['action']);self.assertIn('https://example.invalid/clock',tasks[0]['source']);self.assertEqual(tasks[0]['original_status'],'待跟进')

    def test_school_backfill_does_not_overwrite_parent_and_failed_retries_stop(self):
        self.store.ingest(self.payload());key='synthetic-race';fp=self.store._job(key,{},self.now)
        self.store._save(key,fp,[dict(child_id='child-1',kind='school',title='带材料',body='旧说明',evidence=[dict(ref='message:synthetic-group:11',text='带材料')])],self.now)
        with self.app.connect() as c:ident=c.execute('SELECT id FROM agent_items WHERE job_id=?',(key,)).fetchone()[0]
        def racing(*args,**kwargs):
            self.store.act(dict(id=ident,action='dismiss'))
            return dict(title='带材料',goal='准备材料',advice='',state='ready',reason='明确要求',change='new',target_id='',purpose='admin',submission='',learning_subject='',learning_goal_id='')
        with patch.object(agent.family_llm,'_chat_json',side_effect=racing):agent._refresh_school(self.app,self.store,self.now,1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?',(ident,)).fetchone()[0],'dismissed')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
        key='synthetic-failure';fp=self.store._job(key,{},self.now)
        self.store._save(key,fp,[dict(child_id='child-1',kind='school',title='待核对材料',body='旧说明',evidence=[dict(ref='message:synthetic-group:11',text='原文')])],self.now)
        with patch.object(agent.family_llm,'_chat_json',side_effect=agent.AgentError('synthetic error')) as mocked:
            for day in range(5):agent._refresh_school(self.app,self.store,self.now+dt.timedelta(days=day),1)
            self.assertEqual(mocked.call_count,3)

    def test_ingest_allowlist_cas_retry_immutability_and_failure_cursor(self):
        payload = self.payload()
        self.assertEqual(self.store.ingest(payload)['inserted'], 1)
        self.assertTrue(self.store.ingest(payload)['replayed'])
        with self.assertRaises(agent.AgentError) as raised: self.store.ingest(self.payload(cursor='12', message='12'))
        self.assertEqual(raised.exception.code, 'cursor_conflict')
        stale = self.payload(expected='11', offset=1); stale['messages'][0]['text'] = '改写原文'
        with self.assertRaises(agent.AgentError) as raised: self.store.ingest(stale)
        self.assertEqual(raised.exception.code, 'message_conflict')
        unknown = self.payload(expected='11', cursor='12', message='12', offset=1); unknown['source_id'] = 'not-authorized'
        with self.assertRaises(agent.AgentError): self.store.ingest(unknown)
        failure = self.payload(expected='11', offset=1); failure.update(messages=[], error='token=PRIVATE-SECRET /Users/private/path')
        self.store.ingest(failure)
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot['sources'][0]['cursor'], '11')
        self.assertEqual(snapshot['sources'][0]['last_success'], payload['checked_at'])
        self.assertNotIn('PRIVATE-SECRET', json.dumps(snapshot))
        self.assertNotIn('/Users/private/path', json.dumps(snapshot))
        empty = self.payload(expected='11', cursor='12', offset=2); empty['messages'] = []
        with self.assertRaises(agent.AgentError): self.store.ingest(empty)
        self.source['child_id'] = 'child-2'; self.config()
        with self.assertRaises(agent.AgentError) as raised: self.store.collector_plan()
        self.assertEqual(raised.exception.code, 'source_binding_conflict')

    def test_collection_windows_and_exact_due_boundaries(self):
        for attempted, expected in [('10:10', '11:00'), ('10:40', '11:10'), ('11:00', '11:30'),
                                    ('13:29', '13:59'), ('13:40', '14:40'), ('14:00', '15:00'),
                                    ('15:10', '16:00'), ('15:40', '16:10'), ('16:00', '16:30'),
                                    ('21:29', '21:59'), ('21:40', '22:40'), ('22:00', '23:00')]:
            with self.subTest(attempted=attempted):
                attempt = dt.datetime.fromisoformat('2026-02-10T' + attempted + ':00+08:00')
                due = agent.next_collection_at(attempt.isoformat())
                self.assertEqual(due.isoformat(), '2026-02-10T' + expected + ':00+08:00')
                payload = self.payload(expected='10', cursor='10'); payload.update(messages=[], checked_at=attempt.isoformat())
                with self.app.connect() as c:
                    c.execute('DELETE FROM agent_sources')
                self.store.ingest(payload)
                self.assertEqual(self.store.collector_plan(due - dt.timedelta(microseconds=1))['sources'], [])
                self.assertEqual(self.store.collector_plan(due)['sources'][0]['cursor'], '10')
                self.assertEqual(self.store.snapshot()['sources'][0]['next_collection_at'], due.isoformat())
        self.assertEqual(agent.next_collection_at('2026-02-10T23:40:00+08:00').isoformat(), '2026-02-11T00:40:00+08:00')
        self.assertEqual(agent.next_collection_at('2026-02-10T07:10:00+00:00').isoformat(), '2026-02-10T16:00:00+08:00')

    def test_parent_check_waits_for_matching_background_receipt_without_moving_cursor(self):
        self.store.ingest(self.payload())
        request_at = self.now + dt.timedelta(minutes=1)
        queued = self.store.request_collection_check(request_at)
        before = self.store.snapshot()['sources'][0]
        self.assertEqual((before['cursor'], before['last_attempt'], before['collection_check']['status']),
                         ('11', self.now.isoformat(), 'pending'))
        check_id = self.store.collector_plan(request_at)['sources'][0]['check_id']
        self.assertTrue(check_id)
        self.assertEqual(self.store.request_collection_check(request_at+dt.timedelta(minutes=1)), queued)
        # A read started before the click cannot acknowledge this request.
        old_read = self.payload(expected='11', cursor='11', offset=2); old_read['messages'] = []
        self.store.ingest(old_read)
        self.assertEqual(self.store.snapshot()['sources'][0]['collection_check']['status'], 'pending')
        failure = self.payload(expected='11', cursor='11', offset=3)
        failure.update(messages=[], error='cli_read_failed', check_id=check_id)
        self.store.ingest(failure)
        saved = self.store.snapshot()['sources'][0]
        self.assertEqual((saved['cursor'], saved['last_success'], saved['collection_check']['status']),
                         ('11', old_read['checked_at'], 'read_error'))
        retried = self.store.request_collection_check(request_at+dt.timedelta(minutes=5))
        self.assertNotEqual(retried['sources'][0]['requested_at'], queued['sources'][0]['requested_at'])
        next_id = self.store.collector_plan(request_at+dt.timedelta(minutes=5))['sources'][0]['check_id']
        self.assertNotEqual(next_id, check_id)
        fresh = self.payload(expected='11', cursor='11', offset=7)
        fresh.update(messages=[], check_id=next_id)
        self.store.ingest(fresh)
        self.assertEqual(self.store.snapshot()['sources'][0]['collection_check']['status'], 'success')
        self.assertEqual(self.store.collector_plan(request_at+dt.timedelta(minutes=8))['sources'], [])

    def test_collection_failures_are_throttled_without_rewriting_source_state(self):
        self.store.ingest(self.payload())
        failed = self.payload(expected='11', offset=20)
        failed.update(messages=[], error='wechat_cli_not_configured')
        self.store.ingest(failed)
        second = dict(id='qq:20002', platform='qq', child_id='child-2', name='虚构第二群', cursor='90', enabled=True)
        config = {'enabled': True, 'sources': [self.source, second]}
        path = self.data / 'agent.json'; path.write_text(json.dumps(config))
        with self.app.connect() as c:
            before = [tuple(row) for row in c.execute('SELECT * FROM agent_sources ORDER BY id')]
        self.assertEqual([s['id'] for s in self.store.collector_plan(self.now + dt.timedelta(minutes=79))['sources']], [second['id']])
        self.assertEqual([s['id'] for s in self.store.collector_plan(self.now + dt.timedelta(minutes=80))['sources']], [self.source['id'], second['id']])
        self.assertEqual(self.store.collector_plan(self.now - dt.timedelta(days=1))['sources'][0]['id'], second['id'])
        saved = self.store.snapshot()['sources'][0]
        self.assertEqual(saved['last_success'], self.now.isoformat())
        self.assertEqual(saved['last_attempt'], failed['checked_at'])
        self.assertEqual(saved['cursor'], '11'); self.assertTrue(saved['error'])
        with self.app.connect() as c:
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM agent_sources ORDER BY id')], before)
        second['enabled'] = False; path.write_text(json.dumps(config))
        self.assertEqual(self.store.collector_plan(self.now + dt.timedelta(minutes=79))['sources'], [])
        config['enabled'] = False; path.write_text(json.dumps(config))
        self.assertFalse(self.store.collector_plan(self.now)['enabled'])
        path.unlink(); self.assertEqual(self.store.collector_plan(self.now), {'enabled': False, 'sources': []})

    def test_collection_failure_reasons_preserve_success_and_hide_untrusted_details(self):
        self.store.ingest(self.payload())
        cases = [('wechat_cli_not_configured', '本机微信读取工具尚未接通'),
                 ('qq_cli_not_configured', '本机QQ读取工具尚未接通'),
                 ('cli_read_timeout', '本机读取工具响应超时'),
                 ('cli_read_failed', '本机读取工具未能完成读取'),
                 ('cli_response_invalid', '读取结果格式无法核对'),
                 ('cli_unavailable', '本机读取工具无法启动'),
                 ('qq_collection_timeout', '本次QQ读取超时'),
                 ('qq_continuity_unverified', 'QQ消息与上次读取位置尚未衔接'),
                 ('untrusted-secret <script> denied permission', '本次消息读取未通过核对')]
        for offset, (code, reason) in enumerate(cases, 1):
            failed = self.payload(expected='11', offset=offset)
            failed.update(messages=[], error=code)
            self.store.ingest(failed)
            saved = self.store.snapshot()['sources'][0]
            self.assertEqual(saved['error'], reason + '；本次未同步新消息，上次成功记录保留。')
            self.assertEqual(saved['last_success'], self.now.isoformat())
            self.assertEqual(saved['cursor'], '11')
            with self.app.connect() as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages').fetchone()[0], 1)
        self.store.ingest(self.payload(expected='11', cursor='12', message='12', offset=20))
        self.assertEqual(self.store.snapshot()['sources'][0]['error'], '')

    def test_incomplete_twelve_message_batch_recovers_in_smaller_batches(self):
        payload = self.payload(cursor='22')
        payload['messages'] = [dict(id=str(i), time=self.now.isoformat(), kind='text', sender='虚构老师',
                                    text='待核对原文：明天带阅读材料。', unread=False) for i in range(11, 23)]
        self.store.ingest(payload)
        old_key = 'messages:' + agent._hash([self.source['id'], [str(i) for i in range(11, 23)]])[:40]
        old_value = {'school_learning_policy': 7, 'messages': payload['messages']}
        for minutes in (0, 6, 17):
            now = self.now + dt.timedelta(minutes=minutes)
            fingerprint = self.store._job(old_key, old_value, now, model=True)
            self.assertTrue(fingerprint)
            self.store._fail(old_key, now, fingerprint=fingerprint, reason='虚构模型输出未完成')
        seen = []
        def select(messages, schema, name, *args, **kwargs):
            request=json.loads(messages[-1]['content']);evidence=request['evidence']
            self.assertEqual(request['mode'], 'school')
            self.assertLessEqual(len(evidence), 6)
            seen.append(len(evidence))
            return dict(proposals=[school_proposal(title_quote=e['text'][:120],evidence=[dict(ref=e['ref'])],
                task_state='review',task_reason='虚构夹具：具体材料要求待补充。') for e in evidence])
        with patch.object(agent.family_llm, '_chat_json', side_effect=select):
            agent.run_once(self.app, self.now + dt.timedelta(minutes=18))
            agent.run_once(self.app, self.now + dt.timedelta(minutes=19))
        self.assertEqual(seen, [6, 6])
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages WHERE processed=1').fetchone()[0], 12)
            self.assertEqual(c.execute('SELECT attempts FROM agent_jobs WHERE id=?', (old_key,)).fetchone()[0], 3)

    def test_worker_model_failure_backoff_dedup_corrected_input_and_idempotent_accept(self):
        self.store.ingest(self.payload()); ident = self.record()
        with patch.object(agent.family_llm, '_chat_json', side_effect=agent.family_llm.LLMUnavailable('offline')) as model:
            failed = agent.run_once(self.app, self.now)
            self.assertEqual(failed['failed'], 2)
            self.assertEqual(model.call_count, 2)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
            self.assertEqual(model.call_count, 2)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model) as model:
            done = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
            self.assertEqual(done['created'], 2)
            self.assertEqual(model.call_count, 2)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=7))
            self.assertEqual(model.call_count, 2)
            items = self.store.snapshot()['items']; school = next(row for row in items if row['kind'] == 'school')
            accepted = self.store.act(dict(id=school['id'], action='accept', title='家长核对后的准备', due='2026-02-12', body='按核对后的材料准备'))
            replay = self.store.act(dict(id=school['id'], action='accept', title='迟到的不同内容'))
            self.assertEqual(accepted, replay)
            with self.app.connect() as c:
                task = dict(c.execute('SELECT * FROM manual_tasks').fetchone())
                self.assertEqual(task['title'], '家长核对后的准备')
                self.assertLessEqual(len(task['id']), 30)
                self.assertIn('message:synthetic-group:11', task['source'])
                self.assertIn('待核对原文', task['source'])
                c.execute('UPDATE records SET note=? WHERE id=?', ('更正：当时是家长观察，孩子的意愿未询问。', ident))
            changed = agent.run_once(self.app, self.now + dt.timedelta(minutes=8))
            self.assertEqual(changed['created'], 1)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=9))
            self.assertEqual(model.call_count, 3)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
        for item in self.store.snapshot()['items']:
            self.assertNotIn('score', item); self.assertNotIn('已完成', item['body'])
            if item['kind'] == 'school': self.assertIn(item['body'], agent.FOCUS.values())

    def test_new_observations_do_not_wait_a_day_or_replace_prior_choices(self):
        first = self.record()
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model) as model:
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            original = self.store.snapshot()['items'][0]
            new = self.record(note='家长反映英语成绩不理想，考试日期、分数和试卷未知。')
            with self.app.connect() as c:
                c.execute("UPDATE records SET category='家长观察',subject='英语' WHERE id=?", (new,))
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=1))['created'], 1)
            self.assertEqual(model.call_count, 2)
            evidence = json.loads(model.call_args.args[0][-1]['content'])['evidence']
            self.assertIn('考试日期、分数和试卷未知', evidence[0]['text'])
            self.assertEqual(evidence[0]['ref'], 'record:' + str(new))
            self.assertEqual(next(x for x in self.store.snapshot()['items'] if x['id'] == original['id']), original)
            self.store.act(dict(id=original['id'], action='dismiss'))
            queued = [self.record(note='另一条虚构家长观察。') for _ in range(2)]
            # A backlog is drained within the existing tick budget, one request per child per tick.
            for minute in (2, 3):
                before = model.call_count
                self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=minute))['created'], 1)
                self.assertEqual(model.call_count - before, 1)
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=4))['created'], 0)
            self.assertEqual(model.call_count, 4)
        older = self.record(note='一条仍待核对的虚构观察。')
        no_action = self.record(note='只保存情况，没有适合的下一步。')
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposal': None}) as model:
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=5))['created'], 0)
            self.assertEqual(model.call_count, 1)
            self.assertFalse(any(x['record_id'] == no_action for x in self.store.snapshot()['items']))
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model) as model:
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=6))['created'], 1)
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=7))['created'], 0)
            self.assertEqual(model.call_count, 1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT state FROM agent_items WHERE id=?', (original['id'],)).fetchone()[0], 'dismissed')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0], 0)
            self.assertEqual(tuple(c.execute('SELECT score,total FROM records WHERE id=?', (new,)).fetchone()), (None, None))
            for ident in [first, new, *queued, older, no_action]:
                self.assertEqual(c.execute('SELECT attempts,done FROM agent_jobs WHERE id=?', ('record:' + str(ident),)).fetchone()[:], (1, 1))

    def test_revocation_before_ingest_write_rejects_inflight_batch(self):
        self.source['id'] = '100000001@chatroom'
        settings = self.app.settings_store()
        original_db = self.store._db
        for disable_agent in (True, False):
            self.config()

            @contextmanager
            def revoked_before_write():
                state = settings.snapshot()
                rows = [{key: source[key] for key in ['id', 'platform', 'child_id', 'name', 'enabled']}
                        for source in state['sources']]
                if not disable_agent: rows[0]['enabled'] = False
                settings.save_sources(dict(revision=state['revision'], enabled=not disable_agent, sources=rows))
                with original_db() as connection:
                    yield connection

            with patch.object(self.store, '_db', revoked_before_write):
                with self.assertRaises(agent.AgentError) as raised:
                    self.store.ingest(self.payload())
            self.assertEqual(raised.exception.code, 'source_disabled')
            with self.app.connect() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM agent_messages').fetchone()[0], 0)
                self.assertEqual(connection.execute('SELECT cursor FROM agent_sources').fetchone()[0], '10')

    def test_retry_limit_stops_same_fingerprint_until_manual_or_new_input(self):
        self.record()
        bad = {'proposal': {'title': '提高20分', 'goal': 'x', 'action': 'x', 'why_now': 'x',
                            'estimated_minutes': 10, 'review_on': '2026-02-10',
                            'evidence': [{'ref': 'record:1', 'quote': '提高20分'}]}}
        with patch.object(agent.family_llm, '_chat_json', return_value=bad) as model:
            for minutes in [0, 6, 17]: agent.run_once(self.app, self.now + dt.timedelta(minutes=minutes))
            self.assertEqual(model.call_count, 3)
            # Each tick creates a fresh Store; a reopened process must still honor the cap.
            reopened = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
            self.assertEqual(reopened.snapshot()['failed_jobs'], 1)
            agent.run_once(self.app, self.now + dt.timedelta(minutes=41))
            self.assertEqual(model.call_count, 3)
            self.assertIn('自动尝试上限', reopened.snapshot()['last_error'])
        with self.app.connect() as c:
            job = dict(c.execute('SELECT * FROM agent_jobs').fetchone())
            self.assertEqual(job['attempts'], agent.MAX_ATTEMPTS)
            self.assertIn('达到自动重试上限', job['error'])
            self.assertIn('人工重试', job['error'])
            self.assertIn('引用无法核对', job['error'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM records').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT note FROM records WHERE id=1').fetchone()[0], '孩子自述：愿意谈谈阅读。')
        self.assertEqual(self.store.snapshot()['failed_jobs'], 1)
        self.assertEqual(self.store.snapshot()['pending_count'], 0)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            self.store.act({'action': 'retry'})
            # A failure finishing after the parent's retry must not consume the restored budget.
            self.store._fail('record:1', self.now + dt.timedelta(minutes=41), fingerprint=job['fingerprint'])
            with self.app.connect() as c:
                self.assertEqual(dict(c.execute('SELECT attempts,error FROM agent_jobs WHERE id=?', ('record:1',)).fetchone()),
                                 {'attempts': 0, 'error': ''})
            # Manual retry is the explicit recovery path for the same fingerprint.
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=41))['created'], 1)
        self.store._fail('record:1', self.now + dt.timedelta(minutes=41), fingerprint=job['fingerprint'])
        self.store.act({'action': 'retry'})
        with self.app.connect() as c:
            self.assertEqual(dict(c.execute('SELECT attempts,done,error FROM agent_jobs WHERE id=?', ('record:1',)).fetchone()),
                             {'attempts': 1, 'done': 1, 'error': ''})
        with self.app.connect() as c:
            c.execute('UPDATE records SET note=? WHERE id=1', ('更正后的虚构观察。',))
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model) as model:
            # A changed source fingerprint gets a fresh automatic attempt budget.
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=42))['created'], 1)
            self.assertEqual(model.call_count, 1)

    def test_retry_limit_survives_process_exit_after_model_starts(self):
        self.record()
        marker = self.data / 'synthetic-model-calls'
        script = '''
import datetime as dt
import os
from pathlib import Path
import sys
import family_agent
import family_review

root, data, marker = map(Path, sys.argv[1:])
app = family_review.load_app(root, data)
def exit_during_model(*args, **kwargs):
    with marker.open('a') as stream:
        stream.write('call\\n')
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(17)
family_agent._plan_learning = exit_during_model
family_agent.run_once(app, dt.datetime(2026, 2, 10, 8, tzinfo=family_agent.TZ))
'''
        commands = [[sys.executable, '-c', script, str(self.root), str(self.data), str(marker)] for _ in range(4)]
        results = [subprocess.run(command, cwd=Path(__file__).resolve().parent, timeout=10) for command in commands]
        self.assertEqual([result.returncode for result in results], [17, 17, 17, 0])
        self.assertEqual(marker.read_text().splitlines(), ['call'] * agent.MAX_ATTEMPTS)
        with self.app.connect() as c:
            job = dict(c.execute('SELECT attempts,done FROM agent_jobs WHERE id=?', ('record:1',)).fetchone())
        self.assertEqual(job, {'attempts': agent.MAX_ATTEMPTS, 'done': 0})

    def test_due_review_offline_declined_deferred_and_feedback_correction(self):
        care = dict(id='synthetic-care', child='示例甲', topic='阅读', title='讨论一次阅读', evidence='虚构记录，仅为回看依据。',
                    action='一起谈谈孩子想讨论的内容。', review_on='2026-02-10', expires_on='2026-02-20')
        (self.data / '陪伴建议.json').write_text(json.dumps([care]))
        state = self.data / '陪伴提醒状态.json'; state.write_text('{}')
        with patch.object(agent.family_llm, '_chat_json', side_effect=AssertionError('due checks do not need a model')):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            with self.app.connect() as c:
                self.assertEqual(c.execute("SELECT attempts FROM agent_jobs WHERE id LIKE 'review:%'").fetchone()[0], 0)
            self.assertEqual(self.store.snapshot()['items'][0]['care_id'], care['id'])
            state.write_text(json.dumps({care['id']: {'status': 'declined'}}))
            agent.run_once(self.app, self.now)
            self.assertEqual(self.store.snapshot()['pending_count'], 0)
            feedback = self.record(note='只补充一次观察，不恢复原计划。', source='陪伴建议:' + care['id'], care_choice='暂不考虑')
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            item = self.store.snapshot()['items'][0]
            self.assertIn('不恢复原建议', item['body'])
            self.assertEqual(item['record_id'], feedback)
            self.store.act(dict(id=item['id'], action='dismiss'))
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            with self.app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?', ('更正当时观察的情境。', feedback))
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 0)
            # A newer explicit deferral hides the due prompt; textual feedback may still be checked.
            self.record(note='', source='陪伴建议:' + care['id'], care_choice='改天回看', care_review_on='2026-02-15')
            agent.run_once(self.app, self.now)
            self.assertIn('不恢复原建议', self.store.snapshot()['items'][0]['body'])
            with self.app.connect() as c: c.execute('UPDATE records SET note=?', ('',))
            agent.run_once(self.app, self.now)
            self.assertEqual(self.store.snapshot()['pending_count'], 0)
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=5))['created'], 1)

    def test_backed_off_batch_does_not_block_new_messages_and_quotes_keep_newlines(self):
        payload = self.payload(cursor='23')
        payload['messages'] = [{**payload['messages'][0], 'id': str(ident)} for ident in range(11, 24)]
        self.store.ingest(payload)
        with patch.object(agent.family_llm, '_chat_json', side_effect=agent.family_llm.LLMUnavailable('offline')):
            agent.run_once(self.app, self.now)
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            result = agent.run_once(self.app, self.now + dt.timedelta(minutes=1))
            final = agent.run_once(self.app, self.now + dt.timedelta(minutes=2))
        self.assertEqual((result['processed'], final['processed']), (6, 1))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages WHERE processed=0').fetchone()[0], 6)
        excerpt = '学校通知\n请带“阅读材料”'
        output = {'proposals': [dict(title_quote='请带“阅读材料”', focus='school', due='', evidence=[{'ref': 'message:synthetic:1', 'quote': excerpt}])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=output):
            items = agent._select('school', [{'ref': 'message:synthetic:1', 'text': excerpt}])
        self.assertEqual(items[0]['evidence'][0]['text'], excerpt)

    def test_citation_choices_are_scoped_to_each_request(self):
        evidence = [dict(ref='message:54321@chatroom:12', text='本周阅读通知。')]
        with patch.object(agent.family_llm, '_chat_json', return_value=dict(proposals=[])) as model:
            agent._select('school', evidence)
        refs = model.call_args.args[1]['properties']['proposals']['items']['properties']['evidence']['items']['properties']['ref']
        self.assertEqual(refs['enum'], [evidence[0]['ref']])
        self.assertNotIn('enum', agent.SCHEMA['properties']['proposals']['items']['properties']['evidence']['items']['properties']['ref'])
        other = [dict(ref='record:2', text='家长转述：孩子说想休息。')]
        with patch.object(agent.family_llm, '_chat_json', return_value=dict(proposal=None)) as model:
            agent._plan_learning(other)
        refs = model.call_args.args[1]['properties']['proposal']['anyOf'][1]['properties']['evidence']['items']['properties']['ref']
        self.assertEqual(refs['enum'], ['record:2'])
        self.assertNotIn('enum', agent.PLAN_SCHEMA['properties']['proposal']['anyOf'][1]['properties']['evidence']['items']['properties']['ref'])
        with self.assertRaises(agent.AgentError):
            agent._source_quote({evidence[0]['ref']: evidence[0]['text']}, 'message:5432112', evidence[0]['text'])
        self.assertEqual(agent._evidence_schema(agent.PLAN_SCHEMA,[None,{},dict(ref=1,text='x')]),agent.PLAN_SCHEMA)
        self.assertEqual(agent._evidence_schema(agent.PLAN_SCHEMA,evidence+[None,{}]),
                         agent._evidence_schema(agent.PLAN_SCHEMA,evidence))
        for entries in ([dict(ref='record:'+str(i),text='x') for i in range(65)],
                        [dict(ref='r'*2001,text='x')]):
            self.assertEqual(agent._evidence_schema(agent.PLAN_SCHEMA,entries),agent.PLAN_SCHEMA)

    def test_source_quotes_restore_no_break_spaces_without_accepting_rewrites(self):
        original = '学校通知\n1.\u00a0选一本书\n2.\u202f任选一段，示例\u2007A'
        quoted = original.translate(str.maketrans('\u00a0\u2007\u202f', '   '))
        result = {'proposals': [dict(title_quote='选一本书', focus='school', due='',
                  evidence=[dict(ref='message:synthetic:1', quote=quoted)])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=result):
            items = agent._select('school', [dict(ref='message:synthetic:1', text=original)])
        self.assertEqual(items[0]['evidence'][0]['text'], original)
        for bad in [quoted.replace('任选', '必须'), quoted.replace('一本', '两本'),
                    quoted.replace('\n2. ', ''), quoted.replace('，', ',')]:
            with self.assertRaises(agent.AgentError): agent._source_quote({'source': original}, 'source', bad)
        with self.assertRaises(agent.AgentError): agent._source_quote({'source': 'can not'}, 'source', 'cannot')
        with self.assertRaises(agent.AgentError): agent._source_quote({'source': original}, 'foreign', quoted)

    def test_school_collector_placeholder_requires_explicit_task_details(self):
        for title in ('[图片]', '待核对：[文件]', '[语音]', '[视频]', '[file：内容未读取，仅保留消息说明]'):
            self.assertTrue(agent._needs_task_details(title))
        self.assertFalse(agent._needs_task_details('请核对图片里的要求'))
        fp = self.store._job('placeholder-school', 'placeholder', self.now)
        evidence = [dict(ref='message:synthetic-group:20', text='图片内容尚未读取')]
        placeholder = dict(child_id='child-1', kind='school',
                           title='待核对：[image：内容未读取，仅保留消息说明]',
                           body=agent.FOCUS['school'], evidence=evidence, due='')
        self.store._save('placeholder-school', fp, [placeholder], self.now)
        item = self.store.snapshot()['items'][0]
        self.assertTrue(item['needs_task_details'])
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept'))
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept', title='带齐资料', body=agent.FOCUS['school']))
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept', title='核对资料', body='[图片]'))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 0)
        accepted = self.store.act(dict(id=item['id'], action='accept', title='找老师核对作业要求',
                                       body='先向老师确认图片里的作业要求，再按确认内容安排。'))
        replay = self.store.act(dict(id=item['id'], action='accept', title='另一标题', body='另一动作'))
        self.assertEqual(accepted, replay)
        with self.app.connect() as c:
            task = dict(c.execute('SELECT * FROM manual_tasks').fetchone())
            self.assertEqual(task['title'], '找老师核对作业要求')
            self.assertIn('message:synthetic-group:20', task['source'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0], 1)

        normal = dict(child_id='child-1', kind='school', title='明天带阅读材料',
                      body=agent.FOCUS['school'], evidence=[dict(ref='message:synthetic-group:21', text='请带阅读材料')], due='')
        fp = self.store._job('normal-school', 'normal', self.now)
        self.store._save('normal-school', fp, [normal], self.now)
        normal_item = next(row for row in self.store.snapshot()['items'] if row['title'] == normal['title'])
        self.assertFalse(normal_item['needs_task_details'])
        self.store.act(dict(id=normal_item['id'], action='accept'))

    def test_qq_placeholders_stay_unknown_until_parent_writes_specific_action(self):
        cases = [
            '[包含未读取的非文字内容]',
            '[已撤回，正文未读取]',
            '[包含未读取的非文字内容]\n[已撤回，正文未读取]',
            '[图片][包含未读取的非文字内容] [已撤回，正文未读取]',
            '[image：内容未读取，仅保留消息说明]',
        ]
        for index, source_text in enumerate(cases):
            self.assertTrue(agent._needs_task_details(source_text), source_text)
        self.assertFalse(agent._needs_task_details('请打印材料\n[包含未读取的非文字内容]'))
        self.assertFalse(agent._needs_task_details('请核对图片里的要求 [已撤回，正文未读取]'))

        # The model may quote a harmless-looking substring, but the complete cited
        # source is still only an unread/recalled placeholder.
        selected = None
        for index, source_text in enumerate(cases):
            ref = 'message:synthetic-group:qq-placeholder-' + str(index)
            quote = '说明' if '说明' in source_text else '未读取'
            result = {'proposals': [dict(title_quote=quote, focus='school', due='',
                                         evidence=[dict(ref=ref, quote=quote)])]}
            with patch.object(agent.family_llm, '_chat_json', return_value=result):
                selected = agent._select('school', [dict(ref=ref, text=source_text)], as_of='2026-02-10')
            self.assertEqual(selected[0]['title'], '待核对：[资料]')
            self.assertEqual(selected[0]['body'], agent.FOCUS['school'])

        fp = self.store._job('qq-placeholder', 'qq-placeholder', self.now)
        self.store._save('qq-placeholder', fp, [dict(child_id='child-1', kind='school',
                           title=selected[0]['title'], body=selected[0]['body'],
                           evidence=selected[0]['evidence'], due='')], self.now)
        item = next(row for row in self.store.snapshot()['items'] if row['title'] == '待核对：[资料]')
        with self.assertRaises(agent.AgentError):
            self.store.act(dict(id=item['id'], action='accept'))
        accepted = self.store.act(dict(id=item['id'], action='accept',
                                       title='先向老师核对原件',
                                       body='先向老师核对原件，再按确认后的具体要求安排。'))
        self.assertEqual(accepted['state'], 'accepted')
        with self.app.connect() as c:
            task = dict(c.execute('SELECT * FROM manual_tasks').fetchone())
        self.assertEqual(task['title'], '先向老师核对原件')

        normal_text = '请打印材料\n[包含未读取的非文字内容]'
        normal_ref = 'message:synthetic-group:qq-normal'
        normal_result = {'proposals': [dict(title_quote='请打印材料', focus='school', due='',
                                             evidence=[dict(ref=normal_ref, quote='请打印材料')])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=normal_result):
            normal = agent._select('school', [dict(ref=normal_ref, text=normal_text)], as_of='2026-02-10')
        self.assertEqual(normal[0]['title'], '待核对：请打印材料')

    def test_school_history_uses_beijing_date_and_preserves_current_or_uncertain_requirements(self):
        # The caller's UTC date is still September 8; this run is September 9 in China.
        self.now = dt.datetime(2026, 9, 8, 16, 15, tzinfo=dt.timezone.utc)
        old_time = '2026-03-09T09:00:00+08:00'
        cases = [('11', '一次性准备截止2026-03-10', '2026-03-10', old_time),
                 ('12', '未来活动截止2026-09-10', '2026-09-10', old_time),
                 ('13', '今天活动截止2026-09-09', '2026-09-09', old_time),
                 ('14', '长期阅读约定，请持续保留阅读记录。', '', old_time),
                 ('15', '时间仍待核对，请带阅读材料。', '', '')]
        payload = self.payload(cursor='15')
        payload['messages'] = [dict(id=ident, time=stamp, kind='text', sender='示例老师', text=text, unread=False)
                               for ident, text, due, stamp in cases]
        self.store.ingest(payload)
        # Existing parent decisions and their task must survive analysis of old messages.
        fp = self.store._job('prior-school', 'prior', self.now)
        item = dict(child_id='child-1', kind='school', title='已由家长核对的要求', body=agent.FOCUS['school'],
                    evidence=[dict(ref='message:synthetic-prior:1', text='虚构的早期依据')], due='2026-03-10')
        self.store._save('prior-school', fp, [item, {**item, 'title': '家长已忽略的要求'}], self.now)
        prior = self.store.snapshot()['items']
        self.store.act(dict(id=prior[0]['id'], action='accept'))
        self.store.act(dict(id=prior[1]['id'], action='dismiss'))
        with self.app.connect() as c:
            before_items = [dict(row) for row in c.execute('SELECT * FROM agent_items ORDER BY id')]
            before_tasks = [dict(row) for row in c.execute('SELECT * FROM manual_tasks ORDER BY id')]

        with patch.object(agent.family_llm, '_chat_json', side_effect=agent.family_llm.LLMUnavailable('offline')):
            self.assertEqual(agent.run_once(self.app, self.now)['failed'], 1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0], '15')

        def school_model(messages, schema, name, timeout, *, data_path=None):
            request = json.loads(messages[-1]['content'])
            self.assertEqual(request['as_of'], '2026-09-09')
            self.assertEqual([row['time'] for row in request['evidence']], [row[3] for row in cases])
            self.assertIn('按各条消息的发送日期理解', messages[0]['content'])
            return {'proposals': [school_proposal(title_quote=text, focus='school', due=due, learning_subject='', learning_goal_id='',
                evidence=[dict(ref='message:' + self.source['id'] + ':' + ident)])
                for ident, text, due, stamp in cases]}

        with patch.object(agent.family_llm, '_chat_json', side_effect=school_model) as model:
            result = agent.run_once(self.app, self.now + dt.timedelta(minutes=6))
            self.assertEqual((result['created'], result['processed']), (5, 5))
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(minutes=7))['created'], 0)
            self.assertEqual(model.call_count, 1)
        with self.app.connect() as c:
            stored = [dict(row) for row in c.execute('SELECT * FROM agent_messages ORDER BY id')]
            self.assertEqual([json.loads(row['payload'])['text'] for row in stored], [row[1] for row in cases])
            self.assertTrue(all(row['processed'] == 1 for row in stored))
            self.assertEqual(c.execute('SELECT cursor FROM agent_sources').fetchone()[0], '15')
            self.assertEqual([dict(row) for row in c.execute("SELECT * FROM agent_items WHERE job_id='prior-school' ORDER BY id")], before_items)
            self.assertEqual([dict(row) for row in c.execute('SELECT * FROM manual_tasks ORDER BY id')], before_tasks)
        pending = self.store.snapshot()['items']
        titles = [row['title'] for row in pending if row['state'] == 'pending']
        self.assertEqual(set(titles), {'待核对：' + row[1] for row in cases})
        expired=next(row for row in pending if row['title']=='待核对：'+cases[0][1])
        self.assertEqual(expired['due'],'2026-03-10');self.assertEqual(expired['plan']['school_task']['state'],'review')
        self.assertIn('原截止日期已过',expired['plan']['school_task']['reason'])

    def test_old_learning_evidence_is_not_filtered_by_school_expiry_rule(self):
        evidence = [dict(ref='record:synthetic-old', text='2026-03-10 阅读观察')]
        output = {'proposals': [dict(title_quote='阅读观察', focus='listen', due='2026-03-10',
                                    evidence=[dict(ref=evidence[0]['ref'], quote=evidence[0]['text'])])]}
        with patch.object(agent.family_llm, '_chat_json', return_value=output):
            self.assertEqual(len(agent._select('learning', evidence, as_of='2026-09-09')), 1)

    def test_school_relative_deadline_uses_original_beijing_send_date(self):
        evidence=[dict(ref='message:synthetic-group:11',text='完成观察记录，明天带来。',time='2026-02-09T16:30:00Z')]
        proposal=dict(title_quote='观察记录',focus='school',due='2026-02-11',evidence=[dict(ref=evidence[0]['ref'],quote='完成观察记录，明天带来。')])
        with patch.object(agent.family_llm,'_chat_json',return_value={'proposals':[proposal]}):
            self.assertEqual(agent._select('school',evidence,as_of='2026-02-10')[0]['due'],'2026-02-11')
            for rows in ([{**evidence[0],'time':''}],[{**evidence[0],'time':'2026-02-08T16:30:00Z'}],
                         [{**evidence[0],'text':'明天带来。后天提交。'}]):
                with self.assertRaises(agent.AgentError):agent._select('school',rows,as_of='2026-02-10')
            self.assertEqual(agent._select('school',evidence,as_of='2026-02-12')[0]['due'],'2026-02-11')

    def test_one_notice_with_several_dated_requirements_keeps_each_date_for_review(self):
        # A Monday notice: homework today, a unit test on Friday and supplies next Monday; each item keeps its own grounded date.
        sent='2026-02-09T16:05:00+08:00'  # Monday in Beijing time
        text='今天英语作业：抄写Unit 3单词。本周五（2月13日）英语单元测验，范围Unit 1到Unit 3。另外下周一美术课请带一盒水彩笔。'
        payload=self.payload(cursor='11');payload['messages'][0].update(text=text,time=sent);self.store.ingest(payload)
        def model(*args,**kwargs):
            base=school_proposal(title_quote=text,focus='school',learning_subject='',learning_goal_id='',task_goal=text,task_advice='',task_reason='明确要求。',task_change='new',task_target_id='',task_purpose='learning',evidence=[dict(ref='message:synthetic-group:11')])
            return {'proposals':[dict(base,due='',task_title='英语：抄写Unit 3单词',task_state='ready'),
                                 dict(base,due='2026-02-13',task_title='英语：Unit1–3单元测验（周五）',task_state='ready'),
                                 dict(base,due='2026-02-16',task_title='美术：下周一带一盒水彩笔',task_state='ready'),
                                 dict(base,due='2026-02-20',task_title='编造的下周五要求',task_state='ready')]}
        with patch.object(agent.family_llm,'_chat_json',side_effect=model):
            self.assertEqual(agent.run_once(self.app,self.now)['failed'],0)
        with self.app.connect() as c:rows={r['title']:dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
        self.assertEqual(rows['英语：抄写Unit 3单词']['state'],'pending');self.assertEqual(rows['英语：抄写Unit 3单词']['due'],'')
        self.assertIn('原消息早于今天',json.loads(rows['英语：抄写Unit 3单词']['plan'])['school_task']['reason'])
        for title,due in (('英语：Unit1–3单元测验（周五）','2026-02-13'),('美术：下周一带一盒水彩笔','2026-02-16')):
            self.assertEqual((rows[title]['state'],rows[title]['due']),('pending',due),title)
            brief=json.loads(rows[title]['plan'])['school_task'];self.assertEqual(brief['state'],'review');self.assertIn('含多个日期',brief['reason']);self.assertIn(due,brief['reason'])
        invented=rows['编造的下周五要求'];self.assertEqual(invented['due'],'');self.assertIn('未采用模型日期',json.loads(invented['plan'])['school_task']['reason'])

    def test_uncertain_school_date_stays_review_without_poisoning_valid_batch(self):
        payload=self.payload(cursor='13');payload['messages'][0]['text']='请准备阅读材料，日期另行通知。'
        payload['messages'].extend([dict(id='12',time=self.now.isoformat(),kind='text',sender='虚构老师',text='请填回执，截止时间：2026 年 2 月 12 日。',unread=False),
                                   dict(id='13',time=self.now.isoformat(),kind='text',sender='虚构老师',text='2026-02-11开始阅读活动，请准备阅读材料，提交日期另行通知。',unread=False)]);self.store.ingest(payload)
        def model(*args,**kwargs):
            return {'proposals':[school_proposal(title_quote=r['text'],focus='school',due=due,learning_subject='',learning_goal_id='',
                task_title=title,task_goal=r['text'],task_advice='',task_state='ready',task_reason='明确要求。',task_purpose='admin',evidence=[dict(ref='message:synthetic-group:'+r['id'])])
                for r,due,title in zip(payload['messages'],['2026-02-31','2026-02-12','2026-02-11'],['准备阅读材料','填写回执','活动准备'])]}
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            result=agent.run_once(self.app,self.now);self.assertEqual(result['failed'],0);self.assertEqual(called.call_count,1)
            agent.run_once(self.app,self.now+dt.timedelta(minutes=1));self.assertEqual(called.call_count,1)
        with self.app.connect() as c:
            rows={r['title']:dict(r) for r in c.execute("SELECT * FROM agent_items WHERE kind='school'")}
            self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0],3)
            tasks=[dict(r) for r in c.execute('SELECT * FROM manual_tasks')];self.assertEqual(len(tasks),1);self.assertEqual(tasks[0]['due'],'2026-02-12')
        pending=rows['准备阅读材料'];self.assertEqual(pending['state'],'pending');self.assertEqual(pending['due'],'')
        brief=json.loads(pending['plan'])['school_task'];self.assertEqual(brief['state'],'review');self.assertIn('未采用模型日期',brief['reason'])
        self.assertEqual(rows['填写回执']['state'],'accepted')
        self.assertEqual(rows['活动准备']['state'],'pending');self.assertEqual(rows['活动准备']['due'],'')

    def test_unread_media_remains_visible_after_processing_and_replay(self):
        payload = self.payload(); payload['messages'][0].update(kind='image', text='图片原件未读', unread=True)
        self.store.ingest(payload); self.store.ingest(payload)
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': []}):
            failed=agent.run_once(self.app,self.now)
            self.assertEqual((failed['failed'],failed['processed']),(1,0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0],0)
        pending=school_proposal(title_quote='图片原件未读',evidence=[dict(ref='message:'+self.source['id']+':11')],
            task_state='review',task_reason='图片原件内容尚未读取。')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[pending])) as model:
            self.assertEqual(agent.run_once(self.app,self.now+dt.timedelta(minutes=6))['processed'],1)
            self.assertEqual(agent.run_once(self.app,self.now+dt.timedelta(minutes=7))['processed'],0)
            self.assertEqual(model.call_count,1)
        self.assertEqual(self.store.snapshot()['sources'][0]['unread_count'], 1)
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT processed FROM agent_messages').fetchone()[0], 1)

    def test_older_record_correction_and_invalid_model_type(self):
        old_id = self.record()
        # More recent care feedback must not permanently hide the older learning record.
        for _ in range(201): self.record(note='', source='陪伴建议:synthetic-other')
        with patch.object(agent.family_llm, '_chat_json', side_effect=self.model):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            with self.app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?', ('更正旧观察。', old_id))
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
        self.record()
        bad = {'proposal': {'oops': 'invalid'}}
        with patch.object(agent.family_llm, '_chat_json', return_value=bad):
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=1))['state'], 'needs_attention')

    def test_title_uses_cited_record_or_verified_excerpt_not_model_claim(self):
        evidence = [{'ref': 'record:1', 'text': 'title: 一次虚构阅读\nnote: 孩子说这段不太明白。'}]
        proposal = dict(title_quote='一次虚构阅读', focus='clarify', due='',
                        evidence=[{'ref': 'record:1', 'quote': '孩子说这段不太明白。'}])
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            self.assertEqual(agent._select('learning', evidence)[0]['title'], '待核对：一次虚构阅读')
        proposal['title_quote'] = '已经完全掌握并提高20分'
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            item = agent._select('learning', evidence)[0]
        self.assertEqual(item['title'], '待核对：孩子说这段不太明白。')
        self.assertNotIn('提高20分', json.dumps(item, ensure_ascii=False))
        proposal['evidence'][0]['ref'] = 'record:unprovided'
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': [proposal]}):
            with self.assertRaises(agent.AgentError): agent._select('learning', evidence)

    def test_nonoverlap_crash_release_and_disabled_cli(self):
        with agent._lock(self.data / '.agent.lock') as locked:
            self.assertTrue(locked)
            self.assertEqual(agent.run_once(self.app, self.now)['state'], 'already_running')
        self.assertEqual(agent.run_once(self.app, self.now)['state'], 'ready')
        self.config(False); output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(agent.main(['--once', '--root', str(self.root), '--data', str(self.data)]), 0)
        self.assertEqual(output.getvalue(), '')

    def test_learning_plan_accept_feedback_due_deferral_dismiss_and_restart(self):
        # The correction tick is D+1 08:01, before the D+2 review; a 23:59
        # wall-clock start would make +1 minute legitimately create that review too.
        self.now = dt.datetime.now(agent.TZ).replace(hour=8,minute=0,second=0,microsecond=0)
        first = self.record(note='孩子自述：分数题想再说一遍。')
        calls = []

        def planner(evidence, profile, *, as_of, data_path):
            calls.append(evidence)
            return dict(title='再说一次分数题', goal='能说出一步理由', action='一起说一说这次分数题最关键的一步。',
                        why_now='记录中保留了孩子自己的表达。', estimated_minutes=8,
                        review_on=(dt.date.fromisoformat(as_of) + dt.timedelta(days=2)).isoformat(),
                        evidence=[dict(ref=evidence[0]['ref'], quote=evidence[0]['text'][:30])])

        contexts=[]
        def goal_planner(messages,schema,name,timeout,**kwargs):
            value=json.loads(messages[-1]['content']);contexts.append(value)
            p=planner(value['evidence'],value['profile'],as_of=value['as_of'],data_path=kwargs['data_path'])
            p.update(assessment='核对新反馈',hypotheses=[],resource='已有材料',mastery_check='独立说明一步',choice='核实')
            return {'proposal':p}

        with patch.object(agent, '_plan_learning', side_effect=planner) as model, patch.object(agent.family_llm,'_chat_json',side_effect=goal_planner) as goal_model:
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
            care = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'care')
            with self.assertRaises(agent.AgentError):
                self.store.act(dict(id=care['id'], action='accept', title='确认小尝试', body='一起说一说关键一步。',
                                     review_on='2026-02-31', estimated_minutes=8))
            accepted = self.store.act(dict(id=care['id'], action='accept', title='家长确认的一小步', body='一起说一说关键一步。',
                                            review_on=(self.now.date() + dt.timedelta(days=2)).isoformat(), estimated_minutes=8))
            self.assertEqual(self.store.act(dict(id=care['id'], action='accept', title='迟到标题')), accepted)
            task_id = accepted['task_id']
            with self.app.connect() as c:
                c.execute('INSERT INTO records(child,day,category,subject,title,note,source,created,related_record_id,followup_kind,assistance,practice_relation,comparison_note) '
                          'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          ('示例甲', (self.now.date() + dt.timedelta(days=1)).isoformat(), '学习进展', '语文', '分数题回看',
                           '孩子说：这次先想每份一样大。', '家长记录', self.now.isoformat(), first, '订正', '', '', ''))
                feedback_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=1))['created'], 1)
            self.assertEqual(goal_model.call_count, 1)
            self.assertEqual(contexts[0]['current_plan']['title'],'家长确认的一小步')
            with self.app.connect() as c:
                c.execute('UPDATE records SET note=? WHERE id=?', ('更正：这次实际先画图再说。', first))
            self.assertEqual(agent.run_once(self.app, self.now + dt.timedelta(days=1, minutes=1))['created'], 1)
            self.assertEqual(goal_model.call_count, 2)
            self.app.save_task(dict(id=task_id, status='已完成', note='虚构反馈：完成一次约定尝试。'))
            due_day = self.now.date() + dt.timedelta(days=2)
            self.assertGreaterEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(8), tzinfo=agent.TZ))['created'], 1)
            model_calls_before_defer = model.call_count
            review = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'review' and item['state'] == 'pending')
            self.assertIn('补充实际用时、结果和帮助', review['body'])
            care = next(item for item in self.store.snapshot()['items'] if item['id'] == care['id'])
            deferred = self.store.act(dict(id=care['id'], action='defer', review_on=(self.now.date() + dt.timedelta(days=5)).isoformat(),
                                            expected_updated=care['updated']))
            self.assertFalse(deferred.get('replayed'))
            self.assertTrue(self.store.act(dict(id=care['id'], action='defer', review_on=(self.now.date() + dt.timedelta(days=5)).isoformat(),
                                                expected_updated=care['updated'])).get('replayed'))
            with self.app.connect() as c:
                self.assertEqual(c.execute("SELECT state FROM agent_items WHERE id=?", (review['id'],)).fetchone()[0], 'superseded')
            due_day = self.now.date() + dt.timedelta(days=5)
            self.assertGreaterEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(8), tzinfo=agent.TZ))['created'], 1)
            self.assertEqual(model.call_count, model_calls_before_defer)
            review = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'review' and item['state'] == 'pending')
            self.store.act(dict(id=review['id'], action='dismiss'))
            self.assertEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(9), tzinfo=agent.TZ))['created'], 0)
        reopened = agent.Store(self.app.connect, self.app.profiles, self.data, app=self.app)
        self.assertEqual(agent.run_once(self.app, dt.datetime.combine(due_day, dt.time(9), tzinfo=agent.TZ))['created'], 0)

    def test_planned_review_respects_focus_without_date_and_update_order(self):
        self.now = dt.datetime.now(agent.TZ).replace(microsecond=0)
        self.record()
        review_dates = {}

        def planner(evidence, profile, *, as_of, data_path):
            review_dates['base'] = dt.date.fromisoformat(as_of) + dt.timedelta(days=2)
            return dict(title='一次小尝试', goal='说出一步理由', action='一起说出这次尝试的一步理由。',
                        why_now='记录保留了这次尝试。', estimated_minutes=5,
                        review_on=review_dates['base'].isoformat(),
                        evidence=[dict(ref=evidence[0]['ref'], quote=evidence[0]['text'][:20])])

        with patch.object(agent, '_plan_learning', side_effect=planner):
            self.assertEqual(agent.run_once(self.app, self.now)['created'], 1)
        care = next(item for item in self.store.snapshot()['items'] if item['kind'] == 'care')
        accepted = self.store.act(dict(id=care['id'], action='accept', review_on=review_dates['base'].isoformat(),
                                       estimated_minutes=5, title='确认小尝试', body='一起说出这次尝试的一步理由。'))
        task_id = accepted['task_id']
        with self.app.connect() as c:
            plan_changed = json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (care['id'],)).fetchone()[0])['approved_changed_at']
        def set_focus(mode, review_on, updated):
            with self.app.connect() as c:
                c.execute('''CREATE TABLE IF NOT EXISTS task_focus (
                    task_id TEXT PRIMARY KEY, mode TEXT NOT NULL, next_action TEXT NOT NULL,
                    waiting_for TEXT NOT NULL, review_on TEXT NOT NULL, version INTEGER NOT NULL, updated TEXT NOT NULL)''')
                c.execute('''INSERT INTO task_focus VALUES (?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                    mode=excluded.mode,next_action=excluded.next_action,waiting_for=excluded.waiting_for,
                    review_on=excluded.review_on,version=excluded.version,updated=excluded.updated''',
                          (task_id, mode, '', '等回复' if mode == 'waiting' else '', review_on, 1, updated))
        changed = (dt.datetime.fromisoformat(plan_changed) + dt.timedelta(microseconds=1)).isoformat()
        set_focus('waiting', '', changed)
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(review_dates['base'], dt.time(8), tzinfo=agent.TZ)), [])
        focus_date = review_dates['base'] + dt.timedelta(days=1)
        set_focus('later', focus_date.isoformat(), changed)
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(focus_date, dt.time(8), tzinfo=agent.TZ))[0]['review_on'], focus_date.isoformat())
        care = next(item for item in self.store.snapshot()['items'] if item['id'] == care['id'])
        defer_date = review_dates['base'] + dt.timedelta(days=2)
        self.store.act(dict(id=care['id'], action='defer', review_on=defer_date.isoformat(), expected_updated=care['updated']))
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(defer_date, dt.time(8), tzinfo=agent.TZ))[0]['review_on'], defer_date.isoformat())
        with self.app.connect() as c:
            approved_changed = json.loads(c.execute('SELECT plan FROM agent_items WHERE id=?', (care['id'],)).fetchone()[0])['approved_changed_at']
        latest_focus = (dt.datetime.fromisoformat(approved_changed) + dt.timedelta(microseconds=1)).isoformat()
        later_date = defer_date + dt.timedelta(days=1)
        set_focus('waiting', later_date.isoformat(), latest_focus)
        self.assertEqual(agent._planned_reviews(self.store, dt.datetime.combine(later_date, dt.time(8), tzinfo=agent.TZ))[0]['review_on'], later_date.isoformat())


    def test_combined_pure_school_acknowledgement_is_processed_without_a_model_or_task(self):
        payload=self.payload();payload['messages'][0]['text']='收到，谢谢老师。'
        self.store.ingest(payload)
        with patch.object(agent.family_llm,'_chat_json',side_effect=AssertionError('pure acknowledgement needs no model')) as model:
            result=agent.run_once(self.app,self.now)
            replay=agent.run_once(self.app,self.now+dt.timedelta(minutes=1))
        model.assert_not_called()
        self.assertEqual((result['processed'],result['created'],result['failed']),(1,0,0))
        self.assertEqual((replay['processed'],replay['created']),(0,0))
        with self.app.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_items').fetchone()[0],0)
            row=c.execute('SELECT payload,processed FROM agent_messages').fetchone()
        self.assertEqual((json.loads(row['payload'])['text'],row['processed']),('收到，谢谢老师。',1))

    def test_combined_pure_school_acknowledgement_does_not_block_an_action_batch(self):
        payload=self.payload(cursor='12');payload['messages'][0]['text']='收到，谢谢老师。'
        payload['messages'].append(dict(id='12',time=self.now.isoformat(),kind='text',sender='示例老师',
            text='明天交回活动回执。',unread=False))
        self.store.ingest(payload)
        ref='message:'+self.source['id']+':12'
        proposal=school_proposal(title_quote='明天交回活动回执',due='2026-02-11',
            evidence=[dict(ref=ref)],task_title='交回活动回执',task_goal='明天交回活动回执。',
            task_state='ready',task_reason='明确的新要求。',task_purpose='admin')
        def model(messages,*args,**kwargs):
            seen=json.loads(messages[-1]['content'])['evidence']
            self.assertEqual([(e['ref'],e['text']) for e in seen],[(ref,'明天交回活动回执。')])
            return dict(proposals=[proposal])
        with patch.object(agent.family_llm,'_chat_json',side_effect=model) as called:
            result=agent.run_once(self.app,self.now)
            agent.run_once(self.app,self.now+dt.timedelta(minutes=1))
        self.assertEqual((result['processed'],result['failed'],called.call_count),(2,0,1))
        with self.app.connect() as c:
            task,=c.execute('SELECT child,title,due,action,original_status,source FROM manual_tasks').fetchall()
            self.assertEqual(c.execute('SELECT SUM(processed) FROM agent_messages').fetchone()[0],2)
            item,=c.execute("SELECT state,evidence FROM agent_items WHERE kind='school'").fetchall()
        self.assertEqual(tuple(task)[:5],('示例甲','交回活动回执','2026-02-11','明天交回活动回执。','待跟进'))
        self.assertIn(ref,task['source']);self.assertNotIn('message:'+self.source['id']+':11',task['source'])
        self.assertEqual(item['state'],'accepted')
        self.assertEqual([e['ref'] for e in json.loads(item['evidence'])],[ref])

    def test_school_acknowledgement_followed_by_reading_keeps_the_action(self):
        ref='message:'+self.source['id']+':11'
        text='收到，明天朗读Unit 3课文两遍。'
        evidence=[dict(ref=ref,text=text,time=self.now.isoformat(),kind='text',content_incomplete=False)]
        proposal=school_proposal(title_quote='明天朗读Unit 3课文两遍',due='2026-02-11',
            evidence=[dict(ref=ref)],learning_subject='英语',task_title='英语：朗读Unit 3课文',
            task_goal='明天朗读Unit 3课文两遍。',task_state='ready',task_reason='收到之后还有明确行动。',
            task_purpose='learning')
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=[proposal])) as model:
            item,=agent._select('school',evidence,school_goals=[],as_of=self.now.date().isoformat())
        self.assertEqual(json.loads(model.call_args.args[0][-1]['content'])['evidence'],evidence)
        self.assertEqual((item['title'],item['body'],item['due']),
                         ('英语：朗读Unit 3课文','明天朗读Unit 3课文两遍。','2026-02-11'))
        self.assertEqual(item['plan']['school_task']['state'],'ready')
        self.assertEqual(item['evidence'],[dict(ref=ref,text=text)])

    def _two_dated_text_school_actions(self):
        # Exact title_quote values from the third bounded synthetic product-model call.
        first='message:'+self.source['id']+':M1';supplement='message:'+self.source['id']+':M4'
        sent='2026-10-05T16:10:00+08:00'
        text='请分别完成两项：明天（10月6日）Unit 3课文读两遍，朗读录音上传班级作业区；10月7日前完成练习卷第1–4题，做完检查。'
        extra='补充练习卷：第1–3题必做，第4题选做。做完检查后请家长签练习卷。朗读要求不变。'
        evidence=[dict(ref=first,text=text,time=sent,kind='text',content_incomplete=False,attachments=[]),
                  dict(ref=supplement,text=extra,time='2026-10-05T16:13:00+08:00',kind='text',content_incomplete=False,attachments=[])]
        proposals=[school_proposal(title_quote='明天（10月6日）Unit 3课文读两遍，朗读录音上传班级作业区',
            due='2026-10-06',evidence=[dict(ref=first)],learning_subject='英语',
            task_title='英语：Unit3课文读两遍并上传录音',
            task_goal='明天（10月6日）Unit 3课文读两遍，朗读录音上传班级作业区。',
            task_state='ready',task_reason='朗读动作与日期在同一原文片段。',task_purpose='learning',
            task_submission='朗读录音上传班级作业区'),
            school_proposal(title_quote='10月7日前完成练习卷第1–4题，做完检查',due='2026-10-07',
            evidence=[dict(ref=first),dict(ref=supplement)],learning_subject='英语',
            task_title='英语：练习卷第1-3题必做第4题选做',
            task_goal='10月7日前完成练习卷第1–3题必做，第4题选做；做完检查后请家长签练习卷。',
            task_state='ready',task_reason='原文明确练习截止，后续只补练习范围与签字。',task_purpose='learning')]
        return evidence,proposals

    def test_exact_action_date_quotes_keep_two_ready_text_tasks_and_exercise_supplement(self):
        evidence,proposals=self._two_dated_text_school_actions()
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-05')
        self.assertEqual([(item['title'],item['body'],item['due']) for item in items],
                         [(p['task_title'],p['task_goal'],p['due']) for p in proposals])
        self.assertEqual([item['plan']['school_task']['state'] for item in items],['ready','ready'])
        self.assertEqual([[e['ref'] for e in item['evidence']] for item in items],
                         [[evidence[0]['ref']],[evidence[0]['ref'],evidence[1]['ref']]])
        self.assertEqual(items[0]['plan']['school_task'].get('submission'),'朗读录音上传班级作业区')
        self.assertIn('第1–3题必做',items[1]['body']);self.assertIn('第4题选做',items[1]['body'])
        self.assertIn('做完检查后请家长签练习卷',items[1]['body'])
        self.assertNotIn('签练习卷',items[0]['body'])
        self.assertTrue(all(not e['attachments'] for e in evidence),'this control uses only complete text, not supposedly read files')

    def test_ambiguous_isolated_borrowed_or_inexact_action_date_quotes_stay_review(self):
        evidence,base=self._two_dated_text_school_actions()
        cases=[('whole notice',evidence[0]['text'],'2026-10-06'),
               ('isolated date','10月6日','2026-10-06'),
               ('date borrowed from exercise',base[0]['title_quote'],'2026-10-07'),
               ('exercise quote borrowed for reading',base[1]['title_quote'],'2026-10-07'),
               ('not an exact quote','明天（10月6日）Unit 3课文朗读两遍，朗读录音上传班级作业区','2026-10-06'),
               ('no quote','','2026-10-06')]
        for label,quote,due in cases:
            with self.subTest(case=label):
                proposals=[dict(base[0],title_quote=quote,due=due),dict(base[1])]
                with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
                    items=agent._select('school',evidence,school_goals=[],as_of='2026-10-05')
                self.assertEqual(items[0]['plan']['school_task']['state'],'review')
                self.assertEqual(items[0]['body'],base[0]['task_goal'],'a rejected date must preserve the read action')
                self.assertEqual(items[1]['plan']['school_task']['state'],'ready','one bad mapping must not block the other action')
                self.assertEqual(items[1]['due'],'2026-10-07')

    def test_exact_action_date_quote_does_not_clear_unread_attachment_guard(self):
        evidence,proposals=self._two_dated_text_school_actions()
        attachment='message:'+self.source['id']+':M5'
        evidence.append(dict(ref=attachment,text='练习卷题目附件尚未读全。',time='2026-10-05T16:14:00+08:00',
            kind='text',content_incomplete=True,attachments=[dict(name='synthetic-questions.pdf',mime='application/pdf')]))
        proposals[1]['evidence'].append(dict(ref=attachment))
        with patch.object(agent.family_llm,'_chat_json',return_value=dict(proposals=proposals)):
            items=agent._select('school',evidence,school_goals=[],as_of='2026-10-05')
        self.assertEqual(items[0]['plan']['school_task']['state'],'ready')
        self.assertEqual(items[1]['plan']['school_task']['state'],'review')
        self.assertEqual(items[1]['body'],proposals[1]['task_goal'])
        self.assertEqual(items[1]['due'],'2026-10-07')
        self.assertIn('已读正文要求已保留',items[1]['plan']['school_task']['reason'])
        self.assertEqual([e['ref'] for e in items[1]['evidence']],
                         [evidence[0]['ref'],evidence[1]['ref'],attachment])

    def test_dated_reading_quote_requires_the_same_unit_and_original_clause(self):
        evidence,proposals=self._two_dated_text_school_actions()
        brief=dict(goal='完成Unit3课文朗读两遍，录制朗读录音，上传至班级作业区')
        quote=proposals[0]['title_quote']
        self.assertTrue(agent._school_dated_quote(quote,evidence,'2026-10-06',brief))
        self.assertFalse(agent._school_dated_quote(quote,evidence,'2026-10-06',dict(goal=brief['goal'].replace('Unit3','Unit4'))))
        self.assertFalse(agent._school_dated_quote(quote,evidence,'2026-10-07',brief))
        lines=[dict(evidence[0],text='其他资料\n'+quote+'\n10月7日前完成练习卷')]
        self.assertTrue(agent._school_dated_quote(quote,lines,'2026-10-06',brief))
        self.assertFalse(agent._school_dated_quote(quote,[dict(evidence[0],text='请'+quote+'继续办理')],'2026-10-06',brief))

    def test_identical_relative_reading_quotes_on_different_send_days_do_not_choose_one(self):
        quote='明天Unit3课文读两遍'
        evidence=[dict(text=quote,time=day+'T16:10:00+08:00') for day in ('2026-10-05','2026-10-06')]
        brief=dict(goal='Unit3课文读两遍')
        for due in ('2026-10-06','2026-10-07'):
            self.assertFalse(agent._school_dated_quote(quote,evidence,due,brief))
        self.assertTrue(agent._school_dated_quote(quote,evidence[:1],'2026-10-06',brief))

    def test_paper_class_name_cannot_choose_between_two_papers_with_different_dates(self):
        first='10月6日前完成练习卷A第1–3题';second='10月7日前完成练习卷B第1–3题'
        evidence=[dict(text=first+'；'+second+'。',time='2026-10-05T16:00:00+08:00')]
        brief=dict(goal='完成练习卷B第1–3题')
        self.assertFalse(agent._school_dated_quote(first,evidence,'2026-10-06',brief))
        self.assertFalse(agent._school_dated_quote(second,evidence,'2026-10-07',brief),'coarse paper names cannot establish an exact identity')
        reference='10月6日前练习卷答案公布'
        self.assertFalse(agent._school_dated_quote(reference,[dict(text=reference,time=evidence[0]['time'])],
                                                  '2026-10-06',brief),'a dated material announcement is not an instruction to do the paper')


if __name__ == '__main__':
    unittest.main()

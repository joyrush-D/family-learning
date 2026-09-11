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

    def reply(self,messages,schema,name,timeout,**kwargs):
        self.assertEqual(name,'family_learning_plan');self.assertEqual(kwargs['data_path'],self.data)
        with sqlite3.connect(self.app.DB,timeout=.1) as c:c.execute('BEGIN IMMEDIATE');c.rollback()
        value=json.loads(messages[-1]['content']);self.last_input=value;e=value['evidence'][-1]
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
        g=self.goal();self.assertFalse(g['evidence_changed']);self.assertIsNone(g['pending'])
        self.feedback('第二次家长转述：同样练习很无聊，愿意换口头讲解。')
        self.assertTrue(self.goal()['evidence_changed']);g=self.evaluate()
        self.assertEqual(self.last_input['current_plan']['title'],'先核对一个判断过程')
        payload=dict(action='approve',id=self.ident,expected_version=g['version'],proposal_id=g['pending']['id'],context_hash=g['context_hash'],request_key='synthetic-repeat-approval')
        self.assertEqual(self.store.action(payload)['task_id'],original)
        self.assertTrue(self.store.action(payload)['replayed'])
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
            p.update(choice='暂停',why_now='本次有疲倦反馈；看过解释后答对原题不代表独立掌握。',
                     action='今天结束练习，保留原目标；休息后再安排一小步。')
            return answer
        self.model.side_effect=adjusted
        pending=self.evaluate()
        self.assertEqual(self.last_input['current_plan'],original)
        self.assertIn('看过讲解或答案',self.last_input['evidence'][-1]['text'])
        self.assertEqual(pending['pending']['choice'],'暂停')
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


if __name__=='__main__':unittest.main()

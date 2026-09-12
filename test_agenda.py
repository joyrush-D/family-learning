"""Synthetic inbox-to-calendar workflow, without a model or message collector."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
import family_agenda as agenda
import family_task_focus as focus


class AgendaTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);data=root/'private';data.mkdir()
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 七年级 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 英语作业 | 2026-09-14 | 待跟进 | 虚构通知 | 完成练习 |\n| T02 | 示例乙 | 打印作业纸 | 无明确截止 | 待跟进 | 家长记录 | 选择文件 |\n')
        p=patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3');p.start();self.addCleanup(p.stop)
        self.store=app.agent_store()
        (data/'agent.json').write_text(json.dumps(dict(enabled=True,sources=[dict(id='synthetic-class',child_id='child-1',platform='wechat',name='虚构班级',cursor='0',enabled=True)])))

    def organize(self,**values):
        return focus.save(app,dict(id='T01',version=0,request_key='synthetic-organize-01',mode='next',next_action='',waiting_for='',review_on='',category='homework',published_on='2026-09-12',due_on='2026-09-14',scheduled_on='',**values))

    def test_task_carries_until_closed_and_undated_stays_inbox(self):
        result=self.organize();self.assertEqual(result['focus']['version'],1)
        self.assertEqual(result['task']['agenda']['due_on'],'2026-09-14')
        self.assertTrue(self.organize()['request_replayed'])
        snap=app.calendar_snapshot('2026-09-11','2026-09-16')
        self.assertEqual([x['day'] for x in snap['agenda'] if x['id']=='T01'],['2026-09-12','2026-09-13','2026-09-14','2026-09-15','2026-09-16'])
        self.assertFalse(any(x['id']=='T02' for x in snap['agenda']))
        t=next(x for x in snap['inbox'] if x['id']=='T02');self.assertEqual(t['agenda']['category'],'todo');self.assertEqual(t['child_ids'],['child-2'])
        app.save_task(dict(id='T01',status='已完成',note='虚构家长核对完成'))
        tomorrow=(dt.datetime.now(app.dt.timezone(app.dt.timedelta(hours=8))).date()+dt.timedelta(days=1)).isoformat()
        self.assertFalse(any(x['id']=='T01' for x in app.calendar_snapshot(tomorrow,tomorrow)['agenda']))
        self.assertTrue(next(x for x in app.calendar_snapshot(tomorrow,tomorrow)['inbox'] if x['id']=='T01')['closed'])
        app.save_task(dict(id='T01',status='待跟进',note='虚构恢复'))
        self.assertTrue(any(x['id']=='T01' for x in app.calendar_snapshot(tomorrow,tomorrow)['agenda']))

    def test_date_evidence_not_collection_time_and_read_is_pure(self):
        self.assertEqual(agenda.sent_day('2026-09-11T18:00:00Z'),'2026-09-12')
        self.assertEqual(agenda.deadline('今晚完成作业','2026-09-12'),'2026-09-12')
        self.assertEqual(agenda.deadline('明天提交回执','2026-09-30'),'2026-10-01')
        for text in ['今天学习了第二课','2026-02-30前完成','今晚完成作业，明天提交回执']:
            self.assertEqual(agenda.deadline(text,'2026-09-12'),'')
        self.assertEqual(agenda.deadline('明天提交回执',''),'')
        today=dt.datetime.now(app.dt.timezone(app.dt.timedelta(hours=8))).date().isoformat()
        unknown=dict(agenda=dict(published_on='',due_on='2099-12-31',scheduled_on=''),closed=False)
        self.assertTrue(agenda.visible_on(unknown,today))
        app.calendar_snapshot('2026-09-12','2026-09-13')
        with app.connect() as c:before='\n'.join(c.iterdump())
        app.calendar_snapshot('2026-09-12','2026-09-13')
        with app.connect() as c:self.assertEqual(before,'\n'.join(c.iterdump()))

    def test_correction_and_legacy_focus_migration_preserve_deadline_original(self):
        self.organize()
        request=dict(id='T01',version=1,request_key='synthetic-correct-02',mode='later',next_action='',waiting_for='',review_on='2026-09-20',category='unknown',published_on='',due_on='',scheduled_on='2026-09-16')
        focus.save(app,request)
        t=app.tasks()[0];self.assertEqual(t['due'],'2026-09-14');self.assertEqual(t['agenda']['due_on'],'')
        self.assertEqual([x['day'] for x in app.calendar_snapshot('2026-09-12','2026-09-17')['agenda'] if x['id']=='T01'],['2026-09-16'])
        with self.assertRaises(focus.FocusError):focus.save(app,dict(request,request_key='synthetic-stale-03',due_on='2026-09-15'))
        with self.assertRaises(focus.FocusError):focus.save(app,dict(request,version=2,request_key='synthetic-invalid-04',scheduled_on='2026-02-30'))

    def test_school_inbox_publication_acceptance_has_no_duplicate(self):
        stamp='2026-09-12T16:00:00+08:00';now=dt.datetime.fromisoformat(stamp)
        self.store.ingest(dict(source_id='synthetic-class',expected_cursor='0',cursor='1',checked_at=stamp,last_message_time='2026-09-11T18:00:00Z',error='',messages=[dict(id='1',time='2026-09-11T18:00:00Z',kind='text',sender='示例老师',text='英语作业：今晚完成练习。',unread=False)]))
        self.store._save('synthetic-job','synthetic-fingerprint',[dict(child_id='child-1',kind='school',title='待核对：英语作业',body='核对今晚练习',evidence=[dict(ref='message:synthetic-class:1',text='英语作业：今晚完成练习。')])],now)
        s=app.calendar_snapshot('2026-09-12','2026-09-13');row=next(x for x in s['inbox'] if x['kind']=='school')
        self.assertEqual(row['agenda']['published_on'],'2026-09-12');self.assertEqual(row['agenda']['due_on'],'2026-09-12')
        self.assertEqual(row['child_ids'],['child-1'])
        result=self.store.act(dict(id=row['id'],action='accept'))
        s=app.calendar_snapshot('2026-09-12','2026-09-13')
        self.assertFalse(any(x['id']==row['id'] for x in s['inbox']))
        self.assertEqual(len([x for x in s['inbox'] if x['task_id']==result['task_id']]),1)
        accepted=next(x for x in s['inbox'] if x['task_id']==result['task_id']);self.assertEqual(accepted['agenda']['published_on'],'2026-09-12')
        with app.connect() as c:
            other=agenda.metadata(app,c,'child-2','英语作业','',['message:synthetic-class:1'])
        self.assertEqual(other['published_on'],'');self.assertEqual(other['due_on'],'')
        with app.connect() as c:
            payload=json.loads(c.execute("SELECT payload FROM agent_messages WHERE source_id=? AND id=?",('synthetic-class','1')).fetchone()[0])
            payload['text']='英语作业按课本要求，明天提交报名回执。'
            c.execute("UPDATE agent_messages SET payload=? WHERE source_id=? AND id=?",(json.dumps(payload),'synthetic-class','1'))
            separate=agenda.metadata(app,c,'child-1','英语作业','',['message:synthetic-class:1'])
        self.assertEqual(separate['due_on'],'')

    def test_wish_capture_promotion_and_retry_preserve_one_task(self):
        today=dt.datetime.now(app.dt.timezone(app.dt.timedelta(hours=8))).date().isoformat()
        obj=dict(child='示例甲',title='想做一份观察手册',action='留下一份自己的观察',due='2099-12-31',box='wish',category='homework',advice='先选择一种植物',request_key='synthetic-wish-capture-01')
        task=app.new_task(obj);ident=task['id']
        self.assertEqual(app.new_task(obj)['id'],ident)
        self.assertFalse(any(x['id']==ident for x in app.calendar_snapshot(today,today)['agenda']))
        self.assertFalse(any(x['id']==ident for x in app.study_store().snapshot('child-1',today)['available_tasks']))
        with self.assertRaises(app.family_study.StudyError):app.study_store().save_item(dict(child_id='child-1',day=today,request_key='synthetic-wish-study-reject',task_id=ident))
        with self.assertRaises(app.TaskError):app.new_task(dict(obj,title='重复请求的另一标题'))
        with app.connect() as c:before=c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0]
        with self.assertRaises(focus.FocusError):app.new_task(dict(obj,request_key='synthetic-invalid-create',category='bad'))
        with app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],before)
        result=focus.save(app,dict(id=ident,version=1,request_key='synthetic-wish-promotion',mode='next',next_action='先画出叶子的形状',waiting_for='',review_on='',box='inbox',title='完成植物观察手册',goal='一页图画和自己的观察',scheduled_on=today))
        self.assertEqual(result['task']['title'],'完成植物观察手册')
        self.assertEqual(result['task']['action'],'一页图画和自己的观察')
        self.assertEqual(result['task']['original_action'],obj['action'])
        snap=app.calendar_snapshot(today,today)
        self.assertEqual(len([x for x in snap['agenda'] if x['id']==ident]),1)
        self.assertEqual(app.new_task(obj)['focus']['box'],'inbox')  # An old capture retry cannot undo promotion.
        with app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM manual_tasks').fetchone()[0],before)

    def test_school_task_goal_and_advice_are_separate(self):
        agent=app.family_agent;text='语文习作：介绍一个熟悉的地方，写出两个特点。开头方式任选。不规定字数。'
        evidence=[dict(ref='message:synthetic-class:1',text=text,time='2026-09-12T12:00:00+08:00')]
        result=dict(proposals=[dict(title_quote='语文习作',focus='school',due='',learning_subject='语文',learning_goal_id='',evidence=[dict(ref=evidence[0]['ref'])],task_title='语文：完成地方介绍习作',task_goal='介绍一个熟悉地方，写出两个特点；开头任选，未规定字数。',task_advice='可以先说说最想介绍的两个特点。')])
        with patch.object(agent.family_llm,'_chat_json',return_value=result):
            selected=agent._select('school',evidence,dict(id='child-1'),as_of='2026-09-12',data_path=self.tmp.name,school_goals=[])[0]
        self.assertEqual(selected['title'],'语文：完成地方介绍习作')
        self.assertNotIn('可以',selected['body'])
        self.assertIn('可以',selected['plan']['school_task']['advice'])
        self.assertEqual(selected['evidence'][0]['text'],text)
        selected.update(child_id='child-1',kind='school')
        self.store._save('synthetic-brief-job','synthetic-brief-fp',[selected],dt.datetime.fromisoformat('2026-09-12T12:00:00+08:00'))
        row=next(x for x in self.store.snapshot()['items'] if x['kind']=='school')
        accepted=self.store.act(dict(id=row['id'],action='accept'))
        task=next(t for t in app.tasks() if t['id']==accepted['task_id'])
        self.assertEqual(task['action'],selected['body']);self.assertEqual(task['advice'],selected['plan']['school_task']['advice'])


if __name__=='__main__':unittest.main()

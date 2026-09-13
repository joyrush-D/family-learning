"""Synthetic homework capture, originals, model boundary and child/parent review."""
import base64
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import app
import family_child
import family_llm
import family_study


class HomeworkReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-homework-report-');self.root=Path(self.tmp.name);self.data=self.root/'private';self.data.mkdir()
        self.paths=patch.multiple(app,ROOT=self.root,DATA=self.data,DB=self.data/'family.sqlite3');self.paths.start()
        self.env=patch.dict(os.environ,{},clear=True);self.env.start()
        (self.root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.store=app.study_store();self.day=self.store._now().date().isoformat();self.calls=[]
        self.result=dict(items=[dict(title='数学：完成小练习册第3页',subject='数学',goal='完成第3页',excerpt='数小练3')],uncertainties=[])
        def model(messages,schema,name,*args,**kwargs):self.calls.append(dict(messages=messages,schema=schema,name=name));return self.result
        self.model=patch.object(family_llm,'_chat_json',side_effect=model);self.model.start()
        self.config=patch.object(family_llm,'configuration',return_value=('https://example.invalid','synthetic'));self.config.start()
        family_child.parent_state(app)
        self.secret='synthetic-session-'+uuid.uuid4().hex
        with family_child._db(app) as c:
            c.execute('INSERT INTO child_sessions VALUES (?,?,?)',(family_child._digest(self.secret),'child-1',9999999999))
        family_child.parent_action(app,'study',dict(child_id='child-1',enabled=True))

    def tearDown(self):
        self.config.stop();self.model.stop();self.env.stop();self.paths.stop();self.tmp.cleanup()

    def request(self,**fields):return dict(child_id='child-1',day=self.day,request_key=uuid.uuid4().hex,version=0,**fields)
    def report(self,**fields):return dict(text='数小练3',explanation='小练3指小练习册第3页，不是三遍。',excerpt='数小练3',goal='完成小练习册第3页',attachments=[],**fields)
    def counts(self):
        with app.connect() as c:return {name:c.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ['study_items','manual_tasks','records','task_updates']}
    def photo(self,owner=None):
        raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII=')
        attachment=app.save_upload(io.BytesIO(raw),len(raw),'synthetic.png')
        if owner:
            with app.connect() as c:
                c.execute('INSERT INTO child_uploads VALUES (?,?)',(attachment['id'],owner))
                c.execute('INSERT INTO reading_uploads VALUES (?,?)',(attachment['id'],owner))
        return attachment['id']
    def child(self,action,body):return family_child._study(app,self.secret,action,{k:v for k,v in body.items() if k!='child_id'})

    def test_draft_only_uses_selected_material_and_rejects_bad_model_output(self):
        photo=self.photo();body=dict(child_id='child-1',day=self.day,text='数小练3',explanation='第3页，不是三遍',attachments=[photo])
        before=self.counts();result=self.store.draft_report(body)
        self.assertEqual(result['draft'],self.result);self.assertEqual(self.counts(),before)
        call=self.calls[-1];self.assertEqual(call['name'],'family_homework_draft');self.assertIn('explanation',json.dumps(call['messages']))
        self.assertIn('缩写',call['messages'][0]['content']);self.assertNotIn('示例乙',json.dumps(call['messages'],ensure_ascii=False))
        for result in [dict(items='bad',uncertainties=[]),dict(items=[dict(title='虚构',subject='',goal='',excerpt='',minutes=10)],uncertainties=[]),dict(items=[],uncertainties=[5])]:
            self.result=result
            with self.assertRaises(family_llm.LLMDraftError):self.store.draft_report(body)
        self.assertEqual(self.counts(),before)
        with patch.object(family_llm,'extract_draft',side_effect=family_llm.LLMUnavailable('synthetic unavailable')):
            with self.assertRaises(family_llm.LLMUnavailable):self.store.draft_report(body)
        self.assertEqual(self.counts(),before)

    def test_child_report_originals_retry_parent_review_and_result_are_separate(self):
        photo=self.photo('child-1');report=self.report();report['attachments']=[photo]
        body=self.request(title='数学：小练习册第3页',subject='数学',planned_minutes=None,report=report)
        saved=self.child('item',body);ident=saved['saved_item_id'];item=next(i for i in saved['items'] if i['id']==ident)
        self.assertEqual(item['report']['actor'],'child');self.assertFalse(item['report']['confirmed_at']);self.assertEqual(item['report']['text'],'数小练3')
        self.assertEqual(self.child('item',body)['saved_item_id'],ident);self.assertEqual(self.counts(),dict(study_items=1,manual_tasks=1,records=0,task_updates=0))
        task=next(t for t in app.snapshot()['tasks'] if t['id']==ident);self.assertTrue(task['homework_report']['needs_review']);self.assertEqual(task['action'],report['goal'])
        with self.assertRaises(family_child.ChildError):self.child('action',self.request(id=ident,action='confirm_report'))
        confirm=dict(self.request(id=ident,action='confirm_report'),version=item['version']);result=self.store.action(confirm)
        item=next(i for i in result['items'] if i['id']==ident);self.assertTrue(item['report']['confirmed_at']);self.assertEqual(item['result'],'')
        self.assertEqual(self.counts()['records'],0);self.assertEqual(self.counts()['task_updates'],0)
        self.assertFalse(next(t for t in app.snapshot()['tasks'] if t['id']==ident)['homework_report']['needs_review'])
        # A delayed creation retry returns the current record after review, without another task or reverting progress.
        self.assertEqual(self.child('item',body)['items'][0]['report'],item['report']);self.assertEqual(self.counts()['study_items'],1)
        self.child('action',dict(self.request(id=ident,action='finish',result='完成'),version=item['version']))
        self.assertEqual(self.counts()['task_updates'],0)
        current=self.store.snapshot('child-1',self.day)['items'][0]
        self.store.action(dict(self.request(id=ident,action='finish',result='完成'),version=current['version']))
        self.assertEqual(self.counts()['task_updates'],1)
        reopened=app.study_store().snapshot('child-1',self.day)['items'][0]
        self.assertEqual(reopened['report']['attachments'],[photo]);self.assertEqual(reopened['report']['explanation'],report['explanation'])
        with patch.object(self.store,'_materials',side_effect=AssertionError('Saved replay must not reread originals')):
            self.assertEqual(self.store.save_item(body)['saved_item_id'],ident)
        self.assertEqual(self.child('item',body)['items'][0]['result_actor'],'parent')
        family_child.parent_action(app,'study',dict(child_id='child-1',enabled=False))
        with self.assertRaises(family_child.ChildError):self.child('item',body)

    def test_ownership_authorization_and_revocation_are_checked_before_and_after_model(self):
        other=self.photo('child-2');own=self.photo('child-1');parent=self.photo()
        for ident in [other,parent]:
            report=self.report();report['attachments']=[ident]
            with self.assertRaises((family_study.StudyError,app.family_reading.ReadingError)):
                self.child('item',self.request(title='虚构待核对功课',report=report))
        body=dict(day=self.day,text='虚构原话',explanation='',attachments=[own])
        result=self.child('draft',body);self.assertTrue(result['draft']['items'])
        def revoked(*args,**kwargs):
            family_child.parent_action(app,'study',dict(child_id='child-1',enabled=False));return self.result
        with patch.object(family_llm,'extract_draft',side_effect=revoked),self.assertRaises(family_child.ChildError):self.child('draft',body)
        with self.assertRaises(family_child.ChildError):self.child('item',self.request(title='未开放不能报功课'))
        self.assertEqual(self.counts()['study_items'],0)

    def test_parent_manual_fallback_and_untrusted_report_fields_leave_no_partial_task(self):
        report=self.report();photo=self.photo();report['attachments']=[photo]
        with patch.object(family_llm,'extract_draft',side_effect=AssertionError('manual input must not call model')):
            result=self.store.save_item(self.request(title='语文：朗读课文',report=report))
        item=result['items'][0];self.assertEqual(item['report']['actor'],'parent');self.assertTrue(item['report']['confirmed_at'])
        self.assertEqual(self.child('state',dict(day=self.day))['items'][0]['report'],{},'parent originals are not automatically shared to child')
        before=self.counts()
        for bad in [report|dict(actor='parent'),report|dict(confirmed_at='pretend'),report|dict(text='x'*6001),report|dict(attachments=[photo,photo]),report|dict(attachments=['../../private'])]:
            with self.assertRaises(family_study.StudyError):self.store.save_item(self.request(title='不应保存',report=bad))
        self.assertEqual(self.counts(),before)


if __name__=='__main__':unittest.main()

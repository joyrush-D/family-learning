"""Synthetic homework print scope checks; no household service, model or printer I/O."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
from test_print_http import PNG, PRINTER


class HomeworkPrintScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-homework-print-scope-')
        root=Path(self.temp.name);data=root/'private';data.mkdir()
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
        (root/'跟踪台账.md').write_text('')
        (data/'attachments').mkdir();(data/'attachments'/'synthetic.png').write_bytes(PNG)
        self.paths=patch.multiple(app,ROOT=root,DATA=data,DB=data/'test.sqlite3');self.paths.start()
        self.environment=patch.dict(app.os.environ,{'FAMILY_HOST':'family.example.invalid','FAMILY_USER':'parent@example.invalid'});self.environment.start()
        (data/'打印机配置.json').write_text(json.dumps({'printers':[PRINTER]}))
        self.pages=patch.object(app.family_print.PrintStore,'_page_count',return_value=1);self.pages.start()
        self.task=self.new_task('示例甲','synthetic-current')
        self.other_task=self.new_task('示例甲','synthetic-other-task')
        self.other_child=self.new_task('示例乙','synthetic-other-child')
        self.question=self.upload('synthetic-paper.png')
        self.teacher=self.upload('synthetic-teacher.png')
        self.answer=self.feedback(self.task,[self.question,self.teacher],'synthetic-current-answer')
        self.foreign_task=self.upload('synthetic-paper.png')
        self.feedback(self.other_task,[self.foreign_task],'synthetic-other-task-answer')
        self.foreign_child=self.upload('synthetic-paper.png')
        self.feedback(self.other_child,[self.foreign_child],'synthetic-other-child-answer')
        self.unbound=self.upload('synthetic-paper.png')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
        self.pages.stop();self.environment.stop();self.paths.stop();self.temp.cleanup()

    def new_task(self,child,key,**extra):
        return app.new_task(dict(child=child,title='虚构作业 '+key,category='homework',request_key=key,**extra))

    def upload(self,name,body=PNG):
        return app.save_upload(io.BytesIO(body),len(body),name)['id']

    def feedback(self,task,attachments,key):
        return app.save_task_feedback(dict(task_id=task['id'],child=task['child'],day='2026-10-01',request_key=key,attachments=attachments))

    @staticmethod
    def source(ident): return dict(type='upload',id=ident)

    def request(self,method,path,obj=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            conn.request(method,path,json.dumps(obj).encode() if obj is not None else None,{'X-Family-Token':app.TOKEN})
            response=conn.getresponse();body=response.read()
            return response.status,json.loads(body)
        finally: conn.close()

    def materials(self,task=None):
        return self.request('GET','/api/print/homework/materials?task_id='+(task or self.task)['id'])

    def pair(self,**extra):
        return dict(task_id=self.task['id'],request_key='synthetic-pair-print',question_sources=[self.source(self.question)],
                    guide_source=self.source(self.teacher),guide_text='',question_confirmed=True,guide_confirmed=True,printer=PRINTER['name'])|extra

    def dump(self):
        with app.connect_read_only() as c: return '\n'.join(c.iterdump())

    def test_current_report_feedback_and_source_identity_are_read_only(self):
        paper=self.upload('synthetic-reported-paper.png')
        reported=app.study_store().save_item(dict(child_id='child-1',day='2026-10-01',request_key='synthetic-reported-paper',version=0,
            title='虚构电子试卷',subject='语文',planned_minutes=None,report=dict(text='',explanation='',goal='完成这份试卷',attachments=[paper])))
        report_task=next(t for t in app.tasks() if t['id']==reported['saved_item_id'])
        answer=self.feedback(report_task,[self.question],'synthetic-report-answer')
        generated=self.upload('作业批改参考-'+str(self.answer['record_id'])+'.txt',b'Synthetic previous AI check')
        result=self.feedback(self.task,[self.question,self.teacher,generated],'synthetic-saved-check')
        with app.connect() as c:
            c.execute("UPDATE records SET followup_kind='作业检查',related_record_id=? WHERE id=?",(self.answer['record_id'],result['record_id']))
        legacy=self.upload('作业批改参考-'+str(self.answer['record_id'])+'.txt',b'Synthetic legacy AI check')
        legacy_result=self.feedback(self.task,[legacy],'synthetic-legacy-check')
        with app.connect() as c:
            c.execute('UPDATE records SET note=? WHERE id=?',('家长核对的作业批改参考；完整逐题意见见文字附件。原作答反馈 #'+str(self.answer['record_id'])+'。',legacy_result['record_id']))
        before=self.dump()
        with patch.object(app,'print_store') as store,patch.object(app.family_llm,'homework_reference_draft') as model:
            status,value=self.materials();report_status,report_value=self.materials(report_task)
        self.assertEqual((status,report_status),(200,200))
        self.assertEqual(value['task'],dict(id=self.task['id'],child='示例甲'))
        self.assertEqual({f['source']['id'] for f in value['files']},{self.question,self.teacher})
        self.assertEqual({f['source']['id'] for f in report_value['files']},{paper,self.question})
        self.assertEqual(next(f for f in report_value['files'] if f['source']['id']==paper)['origin'],'reported_homework')
        self.assertEqual(value['school_error'],'')
        self.assertEqual(self.dump(),before);store.assert_not_called();model.assert_not_called()
        with app.connect_read_only() as c:
            context=app.homework_review_context(c,report_task['id'],answer['record_id'])
        self.assertEqual(context['allowed'][self.question]['origin'],'saved_answer')

    def test_foreign_unbound_and_old_check_sources_reject_before_any_print_write(self):
        generated=self.upload('作业批改参考-'+str(self.answer['record_id'])+'.txt',b'Synthetic previous AI check')
        result=self.feedback(self.task,[generated],'synthetic-generated-result')
        with app.connect() as c:
            c.execute("UPDATE records SET followup_kind='作业检查',related_record_id=? WHERE id=?",(self.answer['record_id'],result['record_id']))
        forbidden=[self.source(i) for i in (self.foreign_task,self.foreign_child,self.unbound,generated)]
        forbidden.append(dict(type='attachment',name='synthetic.png'))
        before=self.dump()
        with patch.object(app,'print_store') as store,patch.object(app.family_llm,'homework_reference_draft') as model:
            for source in forbidden:
                for body in (self.pair(question_sources=[source]),self.pair(guide_source=source)):
                    status,value=self.request('POST','/api/print/homework',body)
                    self.assertEqual(status,403,value);self.assertEqual(value['code'],'review_source_not_allowed')
                status,value=self.request('POST','/api/print/homework/draft',dict(purpose='reference',task_id=self.task['id'],question_sources=[source]))
                self.assertEqual(status,403,value)
            self.assertEqual(self.request('POST','/api/print/homework',self.pair(task_id='missing'))[0],404)
        store.assert_not_called();model.assert_not_called();self.assertEqual(self.dump(),before)
        self.assertFalse((app.DATA/'print').exists())

    def test_school_revocation_preserves_only_independent_saved_materials(self):
        school_file=self.upload('synthetic-school-paper.png')
        app.agent_store()
        school=dict(id='synthetic-school',platform='qq',child_id='child-1',name='虚构学校来源',enabled=True)
        message=dict(id='synthetic-message',time='2026-10-01T12:00:00+08:00',kind='text',sender='虚构老师',text='虚构作业原件',unread=False)
        with app.connect() as c:
            c.execute('INSERT INTO agent_sources (id,binding,cursor) VALUES (?,?,?)',(school['id'],json.dumps(['qq','child-1'],separators=(',',':')),''))
            c.execute('INSERT INTO agent_messages (source_id,id,payload) VALUES (?,?,?)',(school['id'],message['id'],json.dumps(message)))
            c.execute('INSERT INTO agent_message_attachments VALUES (?,?,?)',(school['id'],message['id'],school_file))
        with patch.object(app.family_agent.Store,'_config',return_value=dict(enabled=True,sources=[school])):
            task=self.new_task('示例甲','synthetic-school-task',source='message:synthetic-school:synthetic-message')
            empty_task=self.new_task('示例甲','synthetic-school-empty-task',source='message:synthetic-school:synthetic-message')
            self.feedback(task,[self.question],'synthetic-school-saved-answer')
            status,value=self.materials(task);self.assertEqual(status,200,value)
            self.assertEqual({f['source']['id'] for f in value['files']},{school_file,self.question})
            school['enabled']=False;before=self.dump()
            with patch.object(app,'print_store') as store,patch.object(app.family_llm,'homework_reference_draft') as model:
                status,value=self.materials(task);empty_status,empty=self.materials(empty_task)
                self.assertEqual(status,200,value);self.assertEqual(empty_status,200,empty)
                self.assertEqual({f['source']['id'] for f in value['files']},{self.question})
                self.assertTrue(value['school_error']);self.assertEqual(empty['files'],[]);self.assertTrue(empty['school_error'])
                body=self.pair(task_id=task['id'],guide_source=self.source(school_file))
                self.assertEqual(self.request('POST','/api/print/homework',body)[0],403)
                body=dict(purpose='reference',task_id=task['id'],question_sources=[self.source(school_file)])
                self.assertEqual(self.request('POST','/api/print/homework/draft',body)[0],403)
            store.assert_not_called();model.assert_not_called();self.assertEqual(self.dump(),before)

    def test_pair_lost_receipt_retries_same_request_without_duplicate_jobs(self):
        original=app.family_print.PrintStore.enqueue;calls=[]
        def lose_second_receipt(store,body):
            calls.append(body['idempotency_key']);job=original(store,body)
            if len(calls)==2: raise app.family_print.PrintError('Synthetic lost receipt','synthetic_receipt_lost',503)
            return job
        with patch.object(app.family_print.PrintStore,'enqueue',lose_second_receipt):
            status,value=self.request('POST','/api/print/homework',self.pair());self.assertEqual(status,503,value)
            queued=app.print_store().list_jobs();self.assertEqual(len(queued),2)
            status,value=self.request('POST','/api/print/homework',self.pair());self.assertEqual(status,200,value)
        self.assertEqual(calls[:2],calls[2:]);self.assertNotEqual(calls[0],calls[1])
        self.assertEqual({j['id'] for j in queued},{value['jobs']['question']['id'],value['jobs']['guide']['id']})
        self.assertEqual(len(app.print_store().list_jobs()),2)

    def test_material_unlinked_during_conversion_does_not_enqueue_and_retries_original_key(self):
        original=app.family_print.PrintStore.prepare_guide
        def unlink_during_conversion(store,*args,**kwargs):
            prepared=original(store,*args,**kwargs)
            with app.connect_read_only() as c:
                row=dict(c.execute('SELECT * FROM records WHERE id=?',(self.answer['record_id'],)).fetchone())
            app.save_record(dict(id=row['id'],child=row['child'],day=row['day'],category=row['category'],
                                 title=row['title'],source=row['source'],note='虚构资料已解除，待重新核对',attachments=[]))
            return prepared
        body=self.pair(guide_source=None,guide_text='Synthetic parent reference')
        with patch.object(app.family_print.PrintStore,'prepare_guide',unlink_during_conversion):
            status,value=self.request('POST','/api/print/homework',body)
            self.assertEqual(status,403,value)
        self.assertEqual(app.print_store().list_jobs(),[])
        self.feedback(self.task,[self.question,self.teacher],'synthetic-reattach-current')
        status,value=self.request('POST','/api/print/homework',body);self.assertEqual(status,200,value)
        status,retry=self.request('POST','/api/print/homework',body);self.assertEqual(status,200,retry)
        self.assertEqual(value['jobs'],retry['jobs']);self.assertEqual(len(app.print_store().list_jobs()),2)

    def test_reference_model_failure_and_legacy_independent_draft_remain_retryable(self):
        body=dict(purpose='reference',task_id=self.task['id'],question_sources=[self.source(self.question)])
        with patch.object(app.family_llm,'homework_reference_draft',side_effect=app.family_llm.LLMDraftError('Synthetic model unavailable')):
            self.assertEqual(self.request('POST','/api/print/homework/draft',body)[0],503)
        with patch.object(app.family_llm,'homework_reference_draft',return_value=dict(text='Synthetic reviewed draft',items=1,coverage='one page')) as model:
            status,value=self.request('POST','/api/print/homework/draft',body)
            self.assertEqual(status,200,value);self.assertEqual(model.call_count,1)
            status,value=self.request('POST','/api/print/homework/draft',dict(question_source=dict(type='attachment',name='synthetic.png')))
            self.assertEqual(status,200,value);self.assertEqual(model.call_count,2)
        self.assertEqual(app.print_store().list_jobs(),[])


if __name__=='__main__': unittest.main()

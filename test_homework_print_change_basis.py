"""Synthetic print-check basis acceptance: a later school correction or cancellation never turns the earlier two
checks into a current confirmation. No household data, model, print bridge or printer process; jobs stay in a temp store."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
from test_print_http import PNG, PRINTER


class HomeworkPrintChangeBasisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-print-change-basis-')
        root=Path(self.temp.name);data=root/'private';data.mkdir();self.data=data
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
        (root/'跟踪台账.md').write_text('')
        self.paths=patch.multiple(app,ROOT=root,DATA=data,DB=data/'test.sqlite3');self.paths.start()
        self.environment=patch.dict(app.os.environ,{'FAMILY_HOST':'family.example.invalid','FAMILY_USER':'parent@example.invalid'});self.environment.start()
        (data/'打印机配置.json').write_text(json.dumps({'printers':[PRINTER]}))
        self.pages=patch.object(app.family_print.PrintStore,'_page_count',return_value=1);self.pages.start()
        self.task=app.new_task(dict(child='示例甲',title='数学：完成练习三第1至5题',action='完成数学练习三第1至5题。11月5日交。',category='homework',request_key='synthetic-change-basis'))
        self.other=app.new_task(dict(child='示例乙',title='数学：虚构另一孩子的练习',category='homework',request_key='synthetic-change-basis-other'))
        self.question=self.upload('虚构练习三-原要求1至5题.png');self.guide=self.upload('虚构家长参考.png')
        app.save_task_feedback(dict(task_id=self.task['id'],child='示例甲',day='2026-11-04',request_key='synthetic-original-files',attachments=[self.question,self.guide]))
        self.foreign=self.upload('虚构另一孩子的题目.png')
        app.save_task_feedback(dict(task_id=self.other['id'],child='示例乙',day='2026-11-04',request_key='synthetic-other-files',attachments=[self.foreign]))
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
        self.pages.stop();self.environment.stop();self.paths.stop();self.temp.cleanup()

    def upload(self,name): return app.save_upload(io.BytesIO(PNG),len(PNG),name)['id']

    def request(self,method,path,obj=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            conn.request(method,path,json.dumps(obj).encode() if obj is not None else None,{'X-Family-Token':app.TOKEN})
            response=conn.getresponse();return response.status,json.loads(response.read())
        finally: conn.close()

    def materials(self,task=None):
        status,value=self.request('GET','/api/print/homework/materials?task_id='+(task or self.task)['id']);self.assertEqual(status,200,value)
        self.assertEqual(set(value['task']),{'id','child'});self.assertRegex(value['print_basis'],'^[a-f0-9]{64}$');return value

    def pair(self,basis,**extra):
        return dict(task_id=self.task['id'],request_key='synthetic-original-number',question_sources=[dict(type='upload',id=self.question)],
                    guide_source=dict(type='upload',id=self.guide),guide_text='',question_confirmed=True,guide_confirmed=True,
                    printer=PRINTER['name'],confirmed_basis=basis)|extra

    def snapshot(self,family=True):
        """Print rows (preparations, jobs, receipts) and every stored byte (originals, preparation PDFs), plus family rows unless a
        simulated school change is itself between the two reads. Database files are compared by their rows, not their pages."""
        with app.print_store()._db() as c:
            printed=[[tuple(r) for r in c.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in ('print_preparations','print_jobs')]
        files={str(p.relative_to(self.data)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(self.data.rglob('*'))
               if p.is_file() and not any(mark in p.name for mark in ('.sqlite3','.db','-wal','-shm','-journal'))}
        if not family: return printed,files
        with app.connect_read_only() as c: return '\n'.join(c.iterdump()),printed,files

    def jobs(self):
        with app.connect_read_only() as c:
            return [dict(r) for r in c.execute("SELECT id,status FROM print_jobs ORDER BY rowid")] if c.execute("SELECT 1 FROM sqlite_master WHERE name='print_jobs'").fetchone() else []

    def school_change(self,title=None,action=None,cancel=False):
        # The same saved effects as a confirmed school update/cancel: requirement words, appended original, closed status.
        with app.connect() as c:
            c.execute('UPDATE manual_tasks SET source=source||? WHERE id=?',('\n\nmessage:synthetic-group:'+('13\n取消练习三' if cancel else '12\n更正：只做1至3题'),self.task['id']))
            if title: c.execute('UPDATE manual_tasks SET title=?,action=? WHERE id=?',(title,action,self.task['id']))
            c.commit()
        if cancel: app.save_task(dict(id=self.task['id'],status='不适用',note='虚构：老师取消练习三',expected_updated=''))

    def test_correction_refuses_old_checks_with_zero_writes_then_new_checks_print_once(self):
        old=self.materials()
        self.school_change('数学：练习三改做第1至3题','只做练习三第1至3题，交回日不变。');before=self.snapshot()
        status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis']))
        self.assertEqual((status,value['code']),(409,'print_basis_changed'),value);self.assertIn('原打印编号保留',value['error'])
        self.assertEqual(self.snapshot(),before,'the old checks prepare and queue nothing')
        new=self.materials();self.assertNotEqual(new['print_basis'],old['print_basis']);self.assertEqual(new['task_title'],'数学：练习三改做第1至3题')
        status,value=self.request('POST','/api/print/homework',self.pair(new['print_basis']));self.assertEqual(status,200,value)
        status,retry=self.request('POST','/api/print/homework',self.pair(new['print_basis']));self.assertEqual(status,200,retry)
        self.assertEqual(retry['jobs'],value['jobs']);self.assertEqual(len(self.jobs()),2)

    def test_cancellation_and_cross_child_or_invalid_basis_are_refused(self):
        old=self.materials();other=self.materials(self.other)
        for body in (self.pair(other['print_basis']),self.pair('0'*64),
                     self.pair(old['print_basis'],task_id=self.other['id'],question_sources=[dict(type='upload',id=self.foreign)])):
            status,value=self.request('POST','/api/print/homework',body);self.assertEqual((status,value.get('code')),(409,'print_basis_changed'),value)
        for body in (self.pair(None),self.pair('not-a-basis'),self.pair(old['print_basis'].upper())):
            status,value=self.request('POST','/api/print/homework',body);self.assertEqual((status,value.get('code')),(409,'print_basis_required'),value)
        self.school_change(cancel=True);before=self.snapshot()
        status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis']));self.assertEqual((status,value['code']),(409,'print_basis_changed'),value)
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.jobs(),[])
        self.assertNotEqual(self.materials()['print_basis'],old['print_basis'],'history stays readable; its basis is the cancelled version')

    def test_unrelated_feedback_keeps_basis_and_a_new_request_without_basis_writes_nothing(self):
        old=self.materials()
        app.save_task_feedback(dict(task_id=self.task['id'],child='示例甲',day='2026-11-04',request_key='synthetic-unrelated-note',note='虚构：做了第1题'))
        self.assertEqual(self.materials()['print_basis'],old['print_basis'],'ordinary feedback or a refresh is not a requirement change')
        legacy=self.pair(None,request_key='synthetic-legacy-number');legacy.pop('confirmed_basis');before=self.snapshot()
        status,value=self.request('POST','/api/print/homework',legacy)
        self.assertEqual((status,value['code']),(409,'print_basis_required'),value);self.assertIn('原打印编号保留',value['error'])
        self.assertEqual(self.snapshot(),before,'an older page without the basis prepares, renders and queues nothing');self.assertEqual(self.jobs(),[])
        status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis']));self.assertEqual(status,200,value)

    def test_change_while_dialog_is_open_queues_nothing(self):
        old=self.materials();prepare=app.family_print.PrintStore.prepare;calls=[]
        def racing(store,*args,**kwargs):
            out=prepare(store,*args,**kwargs)
            if not calls: app.save_task(dict(id=self.task['id'],status='不适用',note='虚构：另一位家长同时标为无需处理',expected_updated=''))
            calls.append(1);return out
        with patch.object(app.family_print.PrintStore,'prepare',racing):
            status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis']))
        self.assertEqual((status,value['code']),(409,'print_basis_changed'),value);self.assertEqual(self.jobs(),[],'no job is queued with the old checks')

    def test_lost_receipt_retries_the_same_number_and_keeps_old_pdf_and_receipt(self):
        old=self.materials();status,first=self.request('POST','/api/print/homework',self.pair(old['print_basis']));self.assertEqual(status,200,first)
        store=app.print_store();job=store.claim('fictional-bridge-01',PRINTER['name'],'fictional-claim-01')
        store.report(job['id'],job['claim_token'],'submitted','fictional-1');store.report(job['id'],job['claim_token'],'spooler_completed','fictional-1')
        status,retry=self.request('POST','/api/print/homework',self.pair(old['print_basis']));self.assertEqual(status,200,retry)
        self.assertEqual([j['id'] for j in retry['jobs']['questions']]+[retry['jobs']['guide']['id']],[j['id'] for j in first['jobs']['questions']]+[first['jobs']['guide']['id']])
        before=self.snapshot(family=False);kept=self.jobs();self.assertIn('spooler_completed',[j['status'] for j in kept])
        self.school_change('数学：练习三改做第1至3题','只做练习三第1至3题，交回日不变。')
        status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis']));self.assertEqual((status,value['code']),(409,'print_basis_changed'),value)
        status,value=self.request('POST','/api/print/homework',self.pair(self.materials()['print_basis']));self.assertEqual(status,409,value)
        self.assertEqual(self.snapshot(family=False),before,'old preparation PDFs, originals and the fictional spooler receipt stay byte-for-byte; nothing reprints')
        self.assertEqual(self.jobs(),kept)

    def test_no_basis_reads_back_only_a_complete_matching_receipt_and_never_fills_a_missing_half(self):
        old=self.materials();status,first=self.request('POST','/api/print/homework',self.pair(old['print_basis']));self.assertEqual(status,200,first)
        legacy=self.pair(None);legacy.pop('confirmed_basis');before=self.snapshot()
        status,value=self.request('POST','/api/print/homework',legacy);self.assertEqual(status,200,value)
        self.assertEqual(value['jobs'],first['jobs'],'an older page retrying the same original number reads its complete receipt back')
        for changed in (dict(copies=2),dict(question_sources=[dict(type='upload',id=self.guide)],guide_source=dict(type='upload',id=self.question))):
            status,value=self.request('POST','/api/print/homework',legacy|changed);self.assertEqual((status,value['code']),(409,'print_basis_required'),value)
        self.assertEqual(self.snapshot(),before)
        enqueue=app.family_print.PrintStore.enqueue;calls=[]
        def lost_second(store,*args,**kwargs):
            calls.append(1)
            if len(calls)==2: raise app.family_print.PrintError('虚构：第二个任务排队前连接中断','storage_unavailable',503)
            return enqueue(store,*args,**kwargs)
        with patch.object(app.family_print.PrintStore,'enqueue',lost_second):
            status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis'],request_key='synthetic-half-number'))
        self.assertEqual(status,503,value);self.assertEqual(len(self.jobs()),3);before=self.snapshot()
        status,value=self.request('POST','/api/print/homework',legacy|dict(request_key='synthetic-half-number'))
        self.assertEqual((status,value['code']),(409,'print_basis_required'),value)
        self.assertEqual(self.snapshot(),before,'without the basis the missing guide half, its PDF and any new job stay uncreated')
        status,value=self.request('POST','/api/print/homework',self.pair(old['print_basis'],request_key='synthetic-half-number'));self.assertEqual(status,200,value)
        self.assertEqual(len(self.jobs()),4,'the page that read the basis completes the same original number once')
        self.school_change('数学：练习三改做第1至3题','只做练习三第1至3题，交回日不变。');before=self.snapshot()
        status,value=self.request('POST','/api/print/homework',legacy);self.assertEqual((status,value['code']),(409,'print_basis_required'),value)
        self.assertEqual(self.snapshot(),before)


if __name__=='__main__': unittest.main()

"""Synthetic read-only material listing for any same-child task and the PDF page-group card; no model, render or service."""
from http.client import HTTPConnection
import json
import socket
import threading
from types import SimpleNamespace
from urllib.parse import quote
import unittest
from unittest.mock import patch

import app
from test_print_http import PNG, PRINTER
import test_homework_print_scope as scope  # module import: its own tests are not collected twice here

HomeworkPrintScopeTests=scope.HomeworkPrintScopeTests

PDF='application/pdf'


class TaskMaterialListingTests(unittest.TestCase):
    setUp=HomeworkPrintScopeTests.setUp
    tearDown=HomeworkPrintScopeTests.tearDown
    new_task=HomeworkPrintScopeTests.new_task
    upload=HomeworkPrintScopeTests.upload
    feedback=HomeworkPrintScopeTests.feedback
    request=HomeworkPrintScopeTests.request
    materials=HomeworkPrintScopeTests.materials
    dump=HomeworkPrintScopeTests.dump

    def todo(self,child,key):
        return app.new_task(dict(child=child,title='虚构签字通知 '+key,category='todo',request_key=key))

    def test_a_notice_lists_its_own_originals_read_only_and_keeps_the_homework_gates(self):
        notice=self.todo('示例甲','synthetic-notice');form=self.upload('synthetic-form.png')
        self.feedback(notice,[form],'synthetic-notice-photo')
        other=self.todo('示例乙','synthetic-other-notice');foreign=self.upload('synthetic-other-form.png')
        self.feedback(other,[foreign],'synthetic-other-notice-photo')
        before=self.dump()
        status,value=self.materials(notice)
        self.assertEqual(status,200,value)
        self.assertEqual((value['category'],value['print_basis'],value['task']['child']),('todo',None,'示例甲'))
        self.assertEqual([(f['source']['id'],f['origin'],f['state']) for f in value['files']],[(form,'same_task','saved')])
        status,value=self.materials(other)
        self.assertEqual((status,[f['source']['id'] for f in value['files']],value['task']['child']),(200,[foreign],'示例乙'))
        # Printing and the parent reference keep the homework-only gate: a notice is never made homework.
        status,value=self.request('POST','/api/print/homework',dict(task_id=notice['id'],request_key='synthetic-notice-print',
                                  question_sources=[self.source(form)],question_confirmed=True,printer=PRINTER['name'],confirmed_basis={}))
        self.assertEqual((status,value.get('code')),(403,'review_source_not_allowed'),value)
        with app.connect_read_only() as c:
            with self.assertRaises(app.family_print.PrintError) as refused: app.homework_material_context(c,notice['id'])
        self.assertEqual(refused.exception.status if hasattr(refused.exception,'status') else 403,403)
        self.assertEqual(self.dump(),before)  # listing writes nothing

    def test_an_oral_item_without_attachment_shows_no_invented_original(self):
        oral=self.todo('示例甲','synthetic-oral-item')
        status,value=self.materials(oral)
        self.assertEqual((status,value['files'],value['school_error']),(200,[],''))
        status,value=self.request('GET','/api/print/homework/materials?task_id=missing-task')
        self.assertEqual(status,404)

    source=staticmethod(HomeworkPrintScopeTests.source)


def document(**extra):
    note=dict(upload_id='u-pdf',title='虚构春游通知',note='周五带水壶，签回执。',uncertainties=['听力音频未随附','第2页表格模糊'],
              requirements=['签回执','听录音'],uncertainty_scopes=[dict(uncertainty='听力音频未随附',requirements=['听录音'],kind='resource')])
    return dict(dict(state='ready',upload_id='u-pdf',page_count=2,processed_pages=[1,2],pending_pages=[],complete=True,requirements_complete=True,
                     batches=[dict(pages=[1,2],draft=dict(originals=[note]),updated='2026-11-02T08:00:00+08:00')],explanation=''),**extra)


class PdfMaterialCardTests(unittest.TestCase):
    def test_a_fully_read_pdf_shows_its_pages_and_keeps_resources_apart_from_unclear_reading(self):
        state=app.pdf_material_state(document())
        self.assertEqual((state['state'],state['label'],state['scope']),('partial','已整理全部2页，有看不清的地方','共2页，已整理第1–2页'))
        self.assertEqual((state['unclear'],state['missing'],state['summary']),(['第2页表格模糊'],['听力音频未随附'],'周五带水壶，签回执。'))
        clear=document();clear['batches'][0]['draft']['originals'][0]['uncertainties']=['听力音频未随附']
        self.assertEqual((app.pdf_material_state(clear)['state'],app.pdf_material_state(clear)['label']),('ready','已整理全部2页'))

    def test_a_partial_pending_failed_or_unstructured_pdf_never_claims_the_whole_original(self):
        part=app.pdf_material_state(document(state='pending',page_count=5,processed_pages=[1,2,3],pending_pages=[4,5],complete=False,
                                             requirements_complete=False,explanation='逐批整理'))
        self.assertEqual((part['state'],part['label'],part['scope'],part['explanation']),('partial','已整理3/5页','共5页，已整理第1–3页，第4–5页未整理','逐批整理'))
        waiting=app.pdf_material_state(document(state='pending',page_count=None,processed_pages=[],pending_pages=[],complete=False,batches=[],requirements_complete=False))
        self.assertEqual((waiting['state'],waiting['label'],waiting['scope'],waiting['summary']),('pending','等待后台整理','尚未整理任何页',''))
        failed=app.pdf_material_state(document(state='error',page_count=4,processed_pages=[1,2],pending_pages=[3,4],complete=False,requirements_complete=False))
        self.assertEqual((failed['state'],failed['scope']),('error','共4页，已整理第1–2页，第3–4页未整理'))
        unstructured=app.pdf_material_state(document(requirements_complete=False))
        self.assertEqual((unstructured['state'],unstructured['label']),('partial','已读全部2页，行动要求待整理'))
        self.assertEqual(app.material_page_words([1,2,3,5,7,8]),'1–3、5、7–8')

    def test_states_prefer_the_page_groups_for_a_page_original_and_the_draft_for_an_image(self):
        context=dict(school=[(dict(id='s'),dict(id='m'),['u-pdf','u-img'])],allowed={'u-pdf':dict(mime=PDF),'u-img':dict(mime='image/png')})
        draft=dict(state='ready',draft=dict(originals=[dict(upload_id='u-img',title='虚构图片',note='图片提要',uncertainties=[])]),upload_ids=['u-img','u-pdf'])
        with patch.object(app,'agent_store',return_value=SimpleNamespace()), patch('family_media.draft_view',return_value=draft), \
             patch('family_pdf_material.view',return_value=document()):
            states=app.homework_material_states(None,context)
        self.assertEqual((states['u-pdf']['scope'],states['u-img']['label'],states['u-img']['summary']),('共2页，已整理第1–2页','已整理','图片提要'))
        refused=dict(state='unavailable',explanation='PDF原件与图片或其他格式原件混在同一条通知，本次未整理。')
        with patch.object(app,'agent_store',return_value=SimpleNamespace()), patch('family_media.draft_view',return_value=draft), \
             patch('family_pdf_material.view',return_value=refused):
            states=app.homework_material_states(None,context)
        self.assertEqual((states['u-pdf']['state'],states['u-pdf']['explanation']),('unread',refused['explanation']))
        self.assertEqual(states['u-img']['label'],'已整理')
        with patch.object(app,'agent_store',return_value=SimpleNamespace()), patch('family_media.draft_view',side_effect=RuntimeError), \
             patch('family_pdf_material.view',side_effect=RuntimeError):
            states=app.homework_material_states(None,context)
        self.assertEqual({k:v['label'] for k,v in states.items()},{'u-pdf':'原件已保存','u-img':'原件已保存'})


class UploadReceiptTests(unittest.TestCase):
    """The upload request key: a retry after a lost receipt reads the stored original back; never matched by name or hash alone."""
    setUp=HomeworkPrintScopeTests.setUp
    tearDown=HomeworkPrintScopeTests.tearDown
    new_task=HomeworkPrintScopeTests.new_task
    upload=HomeworkPrintScopeTests.upload
    feedback=HomeworkPrintScopeTests.feedback

    def post(self,body,name='synthetic-photo.png',key=None,declared=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        try:
            conn.putrequest('POST','/api/upload')
            headers={'X-Family-Token':app.TOKEN,'X-File-Name':quote(name),'Content-Type':'application/octet-stream',
                     'Content-Length':str(len(body) if declared is None else declared),**({'X-Request-Key':key} if key is not None else {})}
            for header,value in headers.items(): conn.putheader(header,value)
            conn.endheaders();conn.send(body)
            if declared is not None: conn.sock.shutdown(socket.SHUT_WR)  # the body ends before its declared length
            response=conn.getresponse();return response.status,json.loads(response.read() or b'{}')
        finally: conn.close()

    def uploads(self):
        with app.connect_read_only() as c: return [dict(r) for r in c.execute('SELECT id,name,size,mime,request_key FROM uploads ORDER BY id')]

    def stored(self): return sorted(p.name for p in (app.DATA/'uploads').iterdir() if not p.name.startswith('.'))

    def test_a_lost_receipt_reads_the_stored_original_back_and_another_selection_is_another_original(self):
        before=len(self.uploads());key='synthetic-upload-key-0001'
        status,first=self.post(PNG,key=key)
        self.assertEqual((status,first['attachment']['replayed']),(200,False),first)
        rows,files=self.uploads(),self.stored()
        status,again=self.post(PNG,key=key)  # the client never saw the first receipt
        self.assertEqual((status,again['attachment']['id'],again['attachment']['replayed']),(200,first['attachment']['id'],True))
        self.assertEqual((self.uploads(),self.stored(),len(rows)),(rows,files,before+1))
        row=next(r for r in rows if r['id']==first['attachment']['id'])
        self.assertEqual((row['name'],row['size'],row['mime'],row['request_key']),('synthetic-photo.png',len(PNG),'image/png',key))
        self.assertEqual((app.DATA/'uploads'/row['id']).read_bytes(),PNG)
        ids={first['attachment']['id']}|{self.post(PNG,key='synthetic-upload-key-0002')[1]['attachment']['id']}|{self.post(PNG)[1]['attachment']['id'] for _ in range(2)}
        self.assertEqual((len(ids),len(self.uploads())),(4,before+4))  # same name and bytes: other key or no key is another original
        self.assertEqual(sum(r['request_key'] is None for r in self.uploads()),before+2)

    def test_the_same_key_with_other_bytes_or_name_or_a_bad_key_writes_nothing(self):
        key='synthetic-upload-key-0003';_,first=self.post(PNG,key=key);rows,files=self.uploads(),self.stored()
        for body,name in [(PNG+b'synthetic-other-bytes','synthetic-photo.png'),(PNG,'synthetic-renamed.png')]:
            status,value=self.post(body,name=name,key=key)
            self.assertEqual((status,value.get('code')),(409,'upload_key_conflict'),value)
        # Each malformed key is refused as a key error with a stable reason (never the file error, never the key echoed), zero writes.
        for bad in ['','short','a'*15,'a'*65,'synthetic key with space','synthetic/key/with/slash']:
            status,value=self.post(PNG,key=bad)
            self.assertEqual((status,value),(400,{'error':'上传标识格式不正确，本次没有保存。','code':'upload_key_invalid'}),repr(bad))
            self.assertTrue(not bad or bad not in json.dumps(value,ensure_ascii=False),repr(bad))
            self.assertEqual((self.uploads(),self.stored()),(rows,files),repr(bad))
        # A real file error with a valid key keeps the old file wording and writes nothing either.
        status,value=self.post(PNG,name='bad/name.png',key='synthetic-upload-key-0007')
        self.assertEqual((status,value),(400,{'error':'文件为空、文件名不正确或内容与支持的类型不符'}))
        self.assertEqual((self.uploads(),self.stored()),(rows,files))
        self.assertEqual((app.DATA/'uploads'/first['attachment']['id']).read_bytes(),PNG)

    def test_a_failure_before_storing_then_the_same_key_stores_exactly_one_original(self):
        key='synthetic-upload-key-0004';rows,files=self.uploads(),self.stored()
        status,_=self.post(PNG[:12],key=key,declared=len(PNG))
        self.assertEqual((status,self.uploads(),self.stored()),(400,rows,files))
        status,value=self.post(PNG,key=key)
        self.assertEqual((status,value['attachment']['replayed'],len(self.uploads())),(200,False,len(rows)+1))

    def test_concurrent_requests_with_one_key_store_at_most_one_original(self):
        before=len(self.uploads());same=[];mixed=[]
        def wave(target,bodies,key):  # 4 at once stays within the test server's listen backlog: every request is answered
            start=threading.Barrier(len(bodies))
            def run(body): start.wait();target.append(self.post(body,key=key))
            threads=[threading.Thread(target=run,args=(body,)) for body in bodies]
            for t in threads: t.start()
            for t in threads: t.join()
        wave(same,[PNG]*4,'synthetic-upload-key-0005');wave(mixed,[PNG,PNG+b'synthetic-x']*2,'synthetic-upload-key-0006')
        self.assertEqual((len(same),len(mixed)),(4,4))
        self.assertEqual(({s for s,_ in same},len({v['attachment']['id'] for _,v in same})),({200},1))
        won={v['attachment']['id'] for s,v in mixed if s==200}
        self.assertEqual((len(won),{s for s,_ in mixed}<={200,409}),(1,True),mixed)
        self.assertEqual(len(self.uploads()),before+2)


del HomeworkPrintScopeTests  # reused methods only; the scope suite runs in its own module


if __name__ == '__main__':
    unittest.main()

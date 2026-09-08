"""python3 test_reading.py: temporary synthetic SQLite only; no app/model/network."""
from concurrent.futures import ThreadPoolExecutor
import base64
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import quote

from family_reading import ReadingError, Store, validate_record_attachments


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-reading-')
        self.db=Path(self.tmp.name)/'family.sqlite3'
        self.children=[dict(id='child-1',name='示例甲'),dict(id='child-2',name='示例乙')]
        self.sources=[dict(id='T01',child='示例甲',title='虚构学校阅读',original_status='待跟进'),
                      dict(id='T02',child='示例乙',title='虚构另一任务',original_status='待跟进')]
        with self.connect() as c:
            c.execute('CREATE TABLE uploads (id TEXT PRIMARY KEY,name TEXT,mime TEXT)')
            c.execute("CREATE TABLE records (id INTEGER PRIMARY KEY,child TEXT,title TEXT,attachments TEXT DEFAULT '[]')")
            c.execute("INSERT INTO records (child,title) VALUES ('示例甲','普通记录不计阅读印章')")
            c.executemany('INSERT INTO uploads VALUES (?,?,?)',[
                ('a'*32,'synthetic.wav','audio/wav'),('b'*32,'synthetic.png','image/png'),('c'*32,'synthetic.txt','text/plain')])
        self.counter=0
        self.store=Store(self.connect,lambda:self.children,lambda:self.sources)
    def tearDown(self): self.tmp.cleanup()
    def connect(self):
        c=sqlite3.connect(self.db,timeout=10);c.row_factory=sqlite3.Row;return c
    def payload(self,row=None,**extra):
        self.counter+=1
        data=dict(child_id='child-1',request_key='synthetic-request-'+str(self.counter))
        if row: data.update(id=row['id'],version=row['version'],child_id=row['child_id'])
        data.update(extra);return data
    def call(self,action,row=None,**extra):
        result=self.store.mutate(action,self.payload(row,**extra))
        return result.get('task',result.get('redemption'))
    def draft(self,**extra):
        data=dict(book='虚构森林故事',edition='虚构第一版',scope='第一章',method='语音',
                  criteria='用自己的话分享一处发现',stamps=1,source_task_id='T01',planned_on='2026-09-10')
        data.update(extra);return self.call('create',**data)
    def submitted(self,**extra):
        task=self.draft(**extra);task=self.call('start',task,note='虚构孩子选择开始')
        return self.call('submit',task,work_text='虚构作品：我发现角色换了一种方法。',attachments=[])
    def awarded(self,**extra):
        return self.call('confirm',self.submitted(**extra),note='虚构家长核对了实际阅读和表达')
    def balance(self,child='child-1'):
        return next(b for b in self.store.snapshot()['balances'] if b['child_id']==child)
    def test_empty_legacy_initialization_and_input_boundaries(self):
        self.assertEqual(self.store.snapshot()['tasks'],[])
        self.assertEqual(self.balance()['earned'],0)
        with self.connect() as c: self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],1)
        task=self.call('create',book='');self.assertEqual(task['state'],'草案')
        with self.assertRaises(ReadingError): self.call('start',task,note='虚构开始')
        for changes in [dict(child_id='unknown'),dict(child_id=[]),dict(stamps=True),dict(stamps=0),dict(stamps=21),
                        dict(book=None),dict(scope='x'*1001),dict(planned_on='2026-02-30'),dict(request_key='short')]:
            with self.subTest(changes=changes):
                with self.assertRaises(ReadingError): self.draft(**changes)
        with self.assertRaises(ReadingError): self.call('unknown_action')
    def test_agreement_start_pause_and_history(self):
        task=self.draft();task=self.call('edit',task,scope='前两节',stamps=2)
        with self.assertRaises(ReadingError): self.call('start',task)
        task=self.call('start',task,note='虚构孩子主动开始')
        for changes in [dict(scope='全书'),dict(stamps=3,reason='不能自动提高'),dict(stamps=1,reason='不能自动降低')]:
            with self.assertRaises(ReadingError): self.call('edit',task,**changes)
        before=self.store.snapshot()
        for field in ['book','scope','method','criteria']:
            with self.assertRaises(ReadingError): self.call('edit',task,**{field:'', 'reason':'测试不能清空既有约定'})
        self.assertEqual(self.store.snapshot(),before)
        task=self.call('edit',task,scope='第一节',reason='虚构共同决定减轻负担')
        self.assertEqual(task['history'][-1]['previous']['scope'],'前两节')
        paused=self.call('pause',task,reason='虚构想休息一下')
        self.assertEqual(paused['resume_state'],'进行中')
        resumed=self.call('resume',paused)
        self.assertEqual(resumed['state'],'进行中');self.assertEqual(resumed['scope'],'第一节')
        with self.assertRaises(ReadingError): self.call('edit',resumed,child_id='child-2',reason='不能换孩子')
    def test_source_task_same_child_and_no_automatic_completion(self):
        before=json.dumps(self.sources,ensure_ascii=False)
        for source in ['T02','missing']:
            with self.assertRaises(ReadingError): self.draft(source_task_id=source)
        task=self.awarded();self.assertEqual(task['source_task_id'],'T01')
        self.assertEqual(json.dumps(self.sources,ensure_ascii=False),before)
        with self.connect() as c: self.assertEqual(c.execute('SELECT count(*) FROM records').fetchone()[0],1)
    def test_audio_or_image_without_text_and_bidirectional_attachment_ownership(self):
        task=self.call('start',self.draft(),note='虚构开始')
        for ids in [['d'*32],['../x'],['a'*32]*21,None]:
            with self.assertRaises(ReadingError): self.call('submit',task,work_text='',attachments=ids)
        with self.assertRaises(ReadingError): self.call('submit',task,work_text='',attachments=[])
        task=self.call('submit',task,work_text='',attachments=['a'*32,'a'*32])
        self.assertEqual(task['attachments'],['a'*32])
        task=self.call('confirm',task,note='虚构家长已听原音核对')
        self.assertEqual(task['award']['amount'],1)
        other=self.call('start',self.draft(child_id='child-2',source_task_id='T02'),note='虚构开始')
        with self.assertRaises(ReadingError): self.call('submit',other,attachments=['a'*32])
        with self.connect() as c:
            with self.assertRaises(ReadingError): validate_record_attachments(c,'child-2',['a'*32])
            validate_record_attachments(c,'child-1',['a'*32])
            c.execute('INSERT INTO records (child,title,attachments) VALUES (?,?,?)',('示例甲','虚构现有照片',json.dumps(['b'*32])))
        with self.assertRaises(ReadingError): self.call('submit',other,attachments=['b'*32])
        image=self.call('start',self.draft(),note='虚构开始')
        image=self.call('submit',image,work_text='',attachments=['b'*32])
        self.assertEqual(image['state'],'待确认')
        with self.connect() as c:
            self.assertIsNone(c.execute('SELECT child_id FROM reading_uploads WHERE upload_id=?',('c'*32,)).fetchone())
    def test_confirm_current_version_and_repeat_request(self):
        task=self.submitted();old=dict(task)
        task=self.call('submit',task,work_text='虚构已纠正转写')
        with self.assertRaises(ReadingError): self.call('confirm',old,note='不能确认旧版本')
        payload=self.payload(task,note='虚构核对当前作品')
        result=self.store.mutate('confirm',payload)
        self.assertEqual(self.store.mutate('confirm',payload),result)
        with self.assertRaises(ReadingError): self.store.mutate('confirm',dict(payload,note='不同请求'))
        task=self.call('confirm',result['task'],note='虚构再次核对')
        self.assertEqual(self.balance()['earned'],1)
        with self.assertRaises(ReadingError): self.call('edit',task,scope='不能静默换题',reason='测试')
        more=self.call('request_more',task,reason='虚构想听一个补充例子')
        self.assertEqual(self.balance()['available'],1)
        more=self.call('submit',more,work_text='虚构补充例子')
        task=self.call('confirm',more,note='虚构再次核对补充')
        self.assertEqual(self.balance()['earned'],1)
        self.assertEqual(task['award']['granted_on'],result['task']['award']['granted_on'])
    def test_pending_work_cannot_change_agreement_via_pause(self):
        task=self.submitted()
        with self.assertRaises(ReadingError): self.call('edit',task,scope='另一章',reason='测试')
        paused=self.call('pause',task,reason='虚构稍后核对')
        with self.assertRaises(ReadingError): self.call('edit',paused,scope='另一章',reason='测试')
        restored=self.call('resume',paused)
        self.assertEqual(restored['state'],'待确认');self.assertEqual(restored['work_text'],task['work_text'])
    def test_unoccupied_revoke_and_reconfirm_reuse_original_award(self):
        task=self.awarded(stamps=3)
        with self.assertRaises(ReadingError): self.call('revoke',task)
        revoked=self.call('revoke',task,reason='虚构确认依据需更正')
        self.assertEqual(revoked['state'],'已完成')
        self.assertEqual(revoked['award']['status'],'已撤销')
        self.assertEqual(self.balance()['earned'],3);self.assertEqual(self.balance()['available'],0)
        self.assertEqual(revoked['history'][-1]['previous']['award']['status'],'已获得')
        restored=self.call('confirm',revoked,note='虚构重新核实原作品')
        self.assertEqual(restored['award']['granted_on'],task['award']['granted_on'])
        self.assertEqual(self.balance()['earned'],3);self.assertEqual(self.balance()['available'],3)
    def test_reserve_fifo_cancel_fulfill_and_correction(self):
        first=self.awarded(stamps=2);second=self.awarded(stamps=1)
        payload=self.payload(reward='虚构周末活动选择',cost=3,planned_on='2026-09-12',note='虚构家长与孩子事先约定')
        redemption=self.store.mutate('reserve',payload)['redemption']
        self.assertEqual(redemption['allocations'],[dict(task_id=first['id'],amount=2),dict(task_id=second['id'],amount=1)])
        self.assertEqual(self.store.mutate('reserve',payload)['redemption'],redemption)
        self.assertEqual(self.balance()['reserved'],3);self.assertEqual(self.balance()['available'],0)
        with self.assertRaises(ReadingError): self.call('reserve',reward='不能重复花',cost=1,note='虚构约定')
        with self.assertRaises(ReadingError): self.call('fulfill',redemption)
        cancelled=self.call('cancel_redemption',redemption,reason='虚构共同改期')
        self.assertEqual(cancelled['state'],'已取消');self.assertEqual(self.balance()['available'],3)
        with self.assertRaises(ReadingError): self.call('fulfill',cancelled,note='不能兑现已取消项')
        new=self.call('reserve',reward='虚构另一次约定',cost=3,note='虚构约定')
        done=self.call('fulfill',new,note='虚构记录：家长已提供约定活动选择')
        self.assertEqual(self.balance()['spent'],3);self.assertEqual(self.balance()['reserved'],0)
        with self.assertRaises(ReadingError): self.call('cancel_redemption',done,reason='不能自动退款')
        corrected=self.call('correct_redemption',done,reason='虚构补充实际兑现说明')
        self.assertEqual(corrected['state'],'已兑现');self.assertTrue(corrected['correction_note'])
        self.assertEqual(self.balance()['spent'],3)
    def test_spent_award_correction_never_consumes_later_awards(self):
        for earn_before_correction in [False,True]:
            with self.subTest(earn_before_correction=earn_before_correction):
                # Separate children keep the two orderings independent.
                child='child-2' if earn_before_correction else 'child-1';source='T02' if earn_before_correction else 'T01'
                old=self.awarded(child_id=child,source_task_id=source,stamps=3)
                reserved=self.call('reserve',child_id=child,reward='虚构选择权',cost=3,note='虚构事先约定')
                self.call('fulfill',reserved,note='虚构已实际兑现')
                if earn_before_correction: self.awarded(child_id=child,source_task_id=source)
                corrected=self.call('revoke',old,reason='虚构更正旧确认，已兑现须家长处理')
                self.assertEqual(corrected['award']['status'],'需家长处理')
                if not earn_before_correction: self.awarded(child_id=child,source_task_id=source)
                self.assertEqual(self.balance(child)['available'],1)
                self.assertEqual(self.balance(child)['earned'],4)
                self.assertEqual(self.balance(child)['spent'],3)
    def test_partial_reservation_retains_whole_old_award_only(self):
        old=self.awarded(stamps=3);new=self.awarded(stamps=1)
        redemption=self.call('reserve',reward='虚构活动',cost=1,note='虚构约定')
        corrected=self.call('revoke',old,reason='虚构更正被部分预留的旧奖励')
        self.assertEqual(corrected['award']['status'],'需家长处理')
        self.assertEqual(self.balance()['available'],3)
        self.call('cancel_redemption',redemption,reason='虚构取消')
        corrected=self.call('revoke',corrected,reason='预留已取消，核对后撤销旧奖项')
        self.assertEqual(corrected['award']['status'],'已撤销')
        self.assertEqual(self.balance()['available'],1)
        task=next(t for t in self.store.snapshot()['tasks'] if t['id']==new['id'])
        self.assertEqual(task['award']['status'],'已获得')
    def test_concurrent_confirmation_and_double_spending(self):
        task=self.submitted(stamps=3);payload=self.payload(task,note='虚构并发重复确认')
        stores=[Store(self.connect,lambda:self.children,lambda:self.sources) for _ in range(4)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda store:store.mutate('confirm',payload),stores))
        self.assertTrue(all(result==results[0] for result in results))
        self.assertEqual(self.balance()['earned'],3)
        requests=[self.payload(reward='虚构并发兑换',cost=3,note='虚构约定') for _ in range(2)]
        def reserve(pair):
            store,data=pair
            try: return store.mutate('reserve',data)
            except ReadingError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(reserve,zip(stores,requests)))
        self.assertEqual(sum(isinstance(result,dict) for result in results),1)
        self.assertIn('insufficient_balance',results)
        self.assertEqual(self.balance()['available'],0)
        with self.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM reading_awards').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM reading_redemptions').fetchone()[0],1)
    def test_profile_rename_keeps_stable_child_id_and_balance(self):
        task=self.awarded();self.children[0]['name']='示例甲的新称呼'
        state=self.store.snapshot();current=next(t for t in state['tasks'] if t['id']==task['id'])
        self.assertEqual(current['child_id'],'child-1');self.assertEqual(current['child'],'示例甲的新称呼')
        self.assertEqual(self.balance()['available'],1)
        current=self.call('request_more',current,reason='虚构更名后补充')
        self.assertEqual(current['child'],'示例甲的新称呼')


class ReadingHTTPTests(unittest.TestCase):
    """Real Handler on loopback; every file, database and model reply is synthetic."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-reading-http-')
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        with patch.dict(os.environ,{'FAMILY_DATA':str(root/'private')},clear=True):
            spec=importlib.util.spec_from_file_location('synthetic_reading_http_app',Path(__file__).with_name('app.py'))
            self.app=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.app)
        self.app.ROOT=root;self.app.TOKEN='synthetic-reading-http-token'
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.app.reading_store()
        self.png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        self.uploads=[]
        for i in range(3):
            blob=self.png+(b'' if i==0 else b'synthetic-extra-'+str(i).encode())
            self.uploads.append(self.app.save_upload(io.BytesIO(blob),len(blob),quote('synthetic-'+str(i)+'.png')))
        self.counter=0
        self.server=ThreadingHTTPServer(('127.0.0.1',0),self.app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop_server)
    def stop_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
    def request(self,path,obj,token=True,host='localhost'):
        headers={'Content-Type':'application/json','Host':host}
        if token: headers['X-Family-Token']=self.app.TOKEN if token is True else token
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            conn.request('POST',path,json.dumps(obj,ensure_ascii=False).encode(),headers)
            response=conn.getresponse();return response.status,json.loads(response.read())
        finally: conn.close()
    def call(self,action,row=None,**extra):
        self.counter+=1
        obj=dict(child_id='child-1',request_key='synthetic-http-request-'+str(self.counter))
        if row: obj.update(id=row['id'],version=row['version'],child_id=row['child_id'])
        obj.update(extra)
        status,result=self.request('/api/reading/'+action,obj)
        self.assertEqual(status,200,result)
        return result.get('task',result.get('redemption'))
    def submitted(self,child_id='child-1',attachments=None):
        task=self.call('create',child_id=child_id,book='虚构纸船故事',edition='虚构版',scope='第一段',
                       method='图画加讲解',criteria='分享一个自己注意到的细节',stamps=1)
        task=self.call('start',task,note='虚构孩子表示开始')
        return self.call('submit',task,work_text='虚构已核对作品：我画了纸船靠岸。',
                         attachments=[self.uploads[0]['id']] if attachments is None else attachments)
    def database_state(self):
        with sqlite3.connect(self.app.DB) as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {t:c.execute('SELECT * FROM "'+t+'" ORDER BY rowid').fetchall() for t in tables}
    def test_reading_routes_require_token_and_host(self):
        before=self.database_state()
        for action in Store.TASK_ACTIONS|Store.REDEMPTION_ACTIONS|{'feedback'}:
            for options in [dict(token=False),dict(token='invalid-synthetic-token'),dict(host='untrusted.example')]:
                with self.subTest(action=action,options=options):
                    self.assertEqual(self.request('/api/reading/'+action,{},**options)[0],403)
        self.assertEqual(self.request('/api/reading/not_an_action',{})[0],400)
        self.assertEqual(self.database_state(),before)
    def test_record_and_reading_attachment_checks_are_bidirectional_and_atomic(self):
        self.submitted()
        record=dict(child='示例乙',day='2026-09-10',category='学习进展',title='虚构作品记录',
                    attachments=[self.uploads[0]['id']])
        before=self.database_state()
        original=validate_record_attachments
        def checked(connection,child_id,ids):
            self.assertTrue(connection.in_transaction)
            return original(connection,child_id,ids)
        with patch.object(self.app.family_reading,'validate_record_attachments',side_effect=checked) as validation:
            self.assertEqual(self.request('/api/record',record)[0],400)
            validation.assert_called_once()
        self.assertEqual(self.database_state(),before)
        self.assertEqual(self.request('/api/record',dict(record,child='示例甲'))[0],200)
        with self.app.connect() as c: ident=c.execute('SELECT id FROM records').fetchone()[0]
        before=self.database_state()
        # Omitting attachments during an edit must still validate the retained originals.
        self.assertEqual(self.request('/api/record',dict(record,id=ident,attachments=[self.uploads[0]['id']]))[0],400)
        changed=dict(record,id=ident);changed.pop('attachments')
        self.assertEqual(self.request('/api/record',changed)[0],400)
        self.assertEqual(self.database_state(),before)
        self.assertEqual(self.request('/api/record',dict(record,attachments=[self.uploads[1]['id']]))[0],200)
        own=self.submitted(attachments=[])
        before=self.database_state()
        obj=dict(child_id=own['child_id'],id=own['id'],version=own['version'],request_key='synthetic-mixed-owner-request',
                 work_text='',attachments=[self.uploads[2]['id'],self.uploads[1]['id']])
        self.assertEqual(self.request('/api/reading/submit',obj)[0],400)
        self.assertEqual(self.database_state(),before)  # First upload binding rolls back with the rejected second one.
    def test_feedback_validates_identity_version_and_uses_only_saved_material(self):
        task=self.submitted();body=dict(id=task['id'],child_id=task['child_id'],version=task['version'])
        expected=dict(feedback=['虚构反馈：可以继续讲这个细节。'],questions=['虚构追问：你还注意到什么？'],limits=['仅看了虚构作品。'])
        before=self.database_state()
        with patch.object(self.app.family_llm,'reading_feedback',return_value=expected) as feedback:
            for bad in [dict(body,child_id='child-2'),dict(body,id='read-missing'),dict(body,version=True),dict(body,version=task['version']-1)]:
                self.assertIn(self.request('/api/reading/feedback',bad)[0],(400,409))
            feedback.assert_not_called()
            status,result=self.request('/api/reading/feedback',dict(body,attachments=[self.uploads[1]['id']],
                work_text='不能覆盖已保存作品',agreement={'book':'不能覆盖已保存约定'},excerpt='虚构篇目片段。'))
            self.assertEqual(status,200);self.assertEqual(result,dict(feedback=expected,version=task['version']))
            feedback.assert_called_once_with({k:task[k] for k in ['book','edition','scope','method','criteria']},
                task['work_text'],[dict(mime='image/png',data=self.png)],'虚构篇目片段。')
        self.assertEqual(self.database_state(),before)
        newer=self.call('submit',task,work_text='虚构修改后的作品')
        with patch.object(self.app.family_llm,'reading_feedback') as feedback:
            self.assertEqual(self.request('/api/reading/feedback',body)[0],409)
            feedback.assert_not_called()
        self.assertGreater(newer['version'],task['version'])
    def test_feedback_model_failure_is_safe_and_does_not_write(self):
        task=self.submitted();before=self.database_state()
        class Offline:
            def open(self,*args,**kwargs): raise URLError('SYNTHETIC_PRIVATE_KEY /synthetic/private-response')
        with patch.object(self.app.family_llm,'build_opener',return_value=Offline()),patch.dict(os.environ,{
                'FAMILY_LLM_BASE_URL':'http://127.0.0.1:1/v1','FAMILY_LLM_MODEL':'synthetic-model',
                'FAMILY_LLM_API_KEY':'SYNTHETIC_PRIVATE_KEY'},clear=True):
            status,result=self.request('/api/reading/feedback',dict(child_id=task['child_id'],id=task['id'],version=task['version']))
        self.assertEqual(status,503)
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY',json.dumps(result))
        self.assertNotIn('/synthetic/private-response',json.dumps(result))
        self.assertEqual(self.database_state(),before)


if __name__=='__main__': unittest.main()

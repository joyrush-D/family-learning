"""python3 test_profiles.py: temporary fictional households; no model or device calls."""
from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import app


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-profiles-')
        self.old=app.ROOT,app.DATA,app.DB
        app.ROOT=Path(self.tmp.name);app.DATA=app.ROOT/'private';app.DATA.mkdir();app.DB=app.DATA/'test.sqlite3'
        (app.DATA/'uploads').mkdir()
        (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 示例甲（虚构） | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        (app.ROOT/'跟踪台账.md').write_text('| T01 | 示例甲 | 虚构阅读 | 2026-09-10 | 待跟进 | 虚构来源 | 交流发现 |\n| T02 | 示例乙 | 他孩虚构事项 | 无明确截止 | 待跟进 | 虚构来源 | 核对 |\n')
        for name in ['消息来源.md','学习与成长.md']:
            (app.ROOT/name).write_text('示例甲的虚构原文，不能因改名而批量替换。')
        (app.DATA/'采集状态.json').write_text(json.dumps({'wechat:synthetic':{'child':'示例甲','cursor':17}},ensure_ascii=False))
        (app.DATA/'陪伴建议.json').write_text(json.dumps([dict(id='synthetic-care',child='示例甲',topic='学习',title='虚构建议',
            evidence='虚构依据',action='交流发现',review_on='2026-09-10',expires_on='2026-09-20')],ensure_ascii=False))
        (app.DATA/'陪伴提醒状态.json').write_text('{"synthetic-care":{"status":"declined"}}')
        self.upload='a'*32;other='b'*32
        with app.connect() as c:
            for ident in [self.upload,other]:
                c.execute('INSERT INTO uploads VALUES (?,?,?,?,?)',(ident,'synthetic.png',15,'image/png','2026-09-08'))
                (app.DATA/'uploads'/ident).write_bytes(b'SYNTHETIC_IMAGE')
        self.record(attachments=[self.upload])
        self.record(related_record_id=1,followup_kind='独立复测')
        self.record(child='示例乙',attachments=[other])
        self.record(id=1,note='虚构记录的已有更正',attachments=[self.upload])
        self.manual=app.new_task(dict(child='示例甲',title='虚构手动待办'))
        app.save_task(dict(id='T01',status='已完成',note='虚构完成依据'))
        self.counter=0
        self.reading=self.read_call('create',book='虚构故事',scope='第一章',method='语音',criteria='交流一个发现',stamps=3,source_task_id='T01')
        self.reading=self.read_call('start',self.reading,note='虚构开始依据')
        self.reading=self.read_call('submit',self.reading,work_text='虚构作品',attachments=[self.upload])
        self.reading=self.read_call('confirm',self.reading,note='虚构家长确认')
        app.snapshot()  # Initialize existing stores before comparing logical DB contents.

    def tearDown(self):
        app.ROOT,app.DATA,app.DB=self.old;self.tmp.cleanup()

    def record(self,**changes):
        obj=dict(child='示例甲',day='2026-09-07',category='学习进展',subject='数学',title='虚构学习记录',note='仅测试',source='家长观察')
        obj.update(changes);app.save_record(obj)

    def change(self,**changes):
        obj=dict(child_id='child-1',name='示例新称呼',grade='五年级',classroom='二班',version=0,reason='虚构档案更正')
        obj.update(changes);return app.save_profile(obj)

    def read_call(self,action,row=None,**changes):
        self.counter+=1;obj=dict(child_id='child-1',request_key='synthetic-profile-reading-'+str(self.counter))
        if row: obj.update(id=row['id'],version=row['version'])
        obj.update(changes);result=app.reading_store().mutate(action,obj)
        return result.get('task',result.get('redemption'))

    def database(self):
        with app.connect() as c: return '\n'.join(c.iterdump())

    def table(self,name):
        with app.connect() as c: return [tuple(r) for r in c.execute('SELECT * FROM '+name)]

    def test_rename_preserves_relations_history_rewards_and_original_files(self):
        before=app.snapshot()
        tables=['revisions','task_updates','task_history','uploads','reading_tasks','reading_awards','reading_events','reading_redemptions','reading_uploads']
        old_tables={t:self.table(t) for t in tables}
        raw={p:p.read_bytes() for p in app.ROOT.rglob('*') if p.is_file() and p!=app.DB}
        profile=self.change()
        self.assertEqual((profile['id'],profile['version'],profile['label']),('child-1',1,'示例新称呼（虚构）'))
        self.assertEqual(profile['history'][0]['previous'],dict(name='示例甲',grade='四年级',classroom=''))
        after=app.snapshot()
        for table in tables: self.assertEqual(self.table(table),old_tables[table],table)
        self.assertEqual({p:p.read_bytes() for p in raw},raw)
        for previous in before['records']:
            current=next(r for r in after['records'] if r['id']==previous['id'])
            self.assertEqual(current,previous|{'child':'示例新称呼' if previous['child']=='示例甲' else previous['child']})
        self.assertTrue(all(t['child']=='示例新称呼' for t in after['tasks'] if t['id'] in ['T01',self.manual['id']]))
        self.assertEqual(after['care']['items'][0]['child'],'示例新称呼')
        self.assertEqual(after['care']['items'][0]['review_status'],'declined')
        self.assertEqual(after['sync']['wechat:synthetic'],dict(child='示例新称呼',cursor=17))
        self.assertEqual(after['reading']['tasks'][0]['child'],'示例新称呼')
        self.assertEqual(after['reading']['balances'][0]['available'],3)
        self.assertEqual([c['energy'] for c in after['rewards']['children']],[c['energy'] for c in before['rewards']['children']])

    def test_alias_inputs_queries_and_attachments_remain_same_child(self):
        self.change()
        self.record(source='陪伴建议:synthetic-care',attachments=[self.upload])
        self.assertEqual(app.new_task(dict(child='示例甲',title='旧客户端虚构待办'))['child'],'示例新称呼')
        evidence,_=app.query_evidence('示例甲','阅读与学习进展')
        self.assertTrue(evidence);self.assertTrue(all(r['child']=='示例新称呼' for r in evidence))
        self.assertNotIn('他孩虚构事项',json.dumps(evidence,ensure_ascii=False))
        self.assertTrue(any(r['kind']=='reading' for r in evidence))
        with patch.object(app.family_llm,'answer_question',return_value=dict(answer='虚构查询结果',citation_ids=[evidence[0]['id']])) as model:
            app.ask_family(dict(child='示例甲',question='阅读与学习进展'))
            self.assertEqual(model.call_args.args[0],'示例新称呼')
        with self.assertRaises(ValueError): self.record(child='示例乙',attachments=[self.upload])
        with self.assertRaises(ValueError): self.record(child='示例乙',source='陪伴建议:synthetic-care')
        task=self.read_call('create',book='虚构第二本',scope='第一章',method='图画',criteria='交流发现',source_task_id='T01')
        task=self.read_call('start',task,note='虚构开始')
        task=self.read_call('submit',task,attachments=[self.upload])
        self.assertEqual(task['child'],'示例新称呼')

    def test_aliases_cannot_move_to_another_child_and_same_child_can_reuse(self):
        self.change()
        for name in ['示例甲','示例新称呼']:
            before=self.database()
            with self.assertRaises(app.ProfileError) as error: self.change(child_id='child-2',name=name)
            self.assertEqual(error.exception.status,409);self.assertEqual(self.database(),before)
        self.change(name='示例第三称呼',version=1)
        self.change(name='示例甲',version=2)
        self.assertTrue(all(app.child_names()[n]=='示例甲' for n in ['示例甲','示例新称呼','示例第三称呼']))
        self.assertEqual(app.profiles()[0]['version'],3)

    def test_versions_and_no_change_do_not_create_history(self):
        self.change(name='示例甲')
        before=self.database()
        with self.assertRaises(app.ProfileError) as error: self.change(name='示例甲',grade='六年级')
        self.assertEqual(error.exception.status,409);self.assertEqual(self.database(),before)
        same=self.change(name='示例甲',version=1)
        self.assertEqual(same['version'],1);self.assertEqual(self.database(),before)
        self.change(name='示例甲',grade='六年级',version=1)
        self.assertEqual(app.profiles()[0]['version'],2)

    def test_failure_rolls_back_aliases_profile_history_and_both_current_tables(self):
        with app.connect() as c:
            c.execute("CREATE TRIGGER synthetic_failure BEFORE UPDATE ON manual_tasks BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        before=self.database()
        with self.assertRaises(sqlite3.Error): self.change()
        self.assertEqual(self.database(),before)
        self.assertEqual(app.profiles()[0]['name'],'示例甲')

    def test_invalid_profile_and_unclaimed_source_do_not_merge_data(self):
        for fields in [dict(name=''),dict(name='示例乙'),dict(name='坏|称呼'),dict(name='坏\n称呼'),dict(name='例（备注）'),
                       dict(reason=''),dict(version=True),dict(version=-1),dict(version='0'),dict(child_id='missing')]:
            before=self.database()
            with self.subTest(fields=fields),self.assertRaises(ValueError): self.change(**fields)
            self.assertEqual(self.database(),before)
        with (app.ROOT/'跟踪台账.md').open('a') as f:
            f.write('| T03 | 未核对称呼 | 虚构待办 | 无明确截止 | 待跟进 | 虚构来源 | 核对 |\n')
        with self.assertRaises(app.ProfileError): self.change(name='未核对称呼')

    def test_concurrent_stale_task_input_is_serialized_with_rename(self):
        entered=threading.Event();release=threading.Event();original=app.child_names
        def names(c=None):
            result=original(c)
            if threading.current_thread().name.startswith('synthetic-save'):
                entered.set()
                if not release.wait(3): raise AssertionError('synthetic barrier timed out')
            return result
        with patch.object(app,'child_names',side_effect=names),ThreadPoolExecutor(max_workers=1,thread_name_prefix='synthetic-save') as writes,ThreadPoolExecutor(max_workers=1) as renames:
            saved=writes.submit(app.new_task,dict(child='示例甲',title='并发虚构待办'))
            self.assertTrue(entered.wait(3));renamed=renames.submit(self.change);release.set()
            task=saved.result(5);renamed.result(5)
        self.assertEqual(next(t for t in app.tasks() if t['id']==task['id'])['child'],'示例新称呼')
        self.assertTrue(all(r['child']!='示例甲' for r in app.snapshot()['records']))

    def test_reading_obtains_profile_only_after_transaction_lock(self):
        # Gate the reading DB open, allowing a rename before its transaction starts.
        # Reading must resolve the new profile after it acquires the write lock.
        store=app.reading_store();opened=threading.Event();release=threading.Event();original=store._db
        def gated():
            c=original();opened.set()
            if not release.wait(3): raise AssertionError('synthetic barrier timed out')
            return c
        task=self.read_call('create',book='虚构并发任务',scope='第一章',method='图画',criteria='交流发现')
        task=self.read_call('start',task,note='虚构开始')
        with patch.object(store,'_db',side_effect=gated),ThreadPoolExecutor(max_workers=1) as worker:
            future=worker.submit(store.mutate,'submit',dict(child_id='child-1',request_key='synthetic-reading-race',id=task['id'],version=task['version'],attachments=[self.upload]))
            self.assertTrue(opened.wait(3));self.change();release.set();result=future.result(5)
        self.assertEqual(result['task']['child'],'示例新称呼')

    def test_http_profile_host_token_validation_and_conflict(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(payload,token=True,host='localhost'):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':host,'Content-Type':'application/json'}
            if token: headers['X-Family-Token']=app.TOKEN
            client.request('POST','/api/profile',json.dumps(payload),headers)
            response=client.getresponse();body=json.loads(response.read());client.close();return response.status,body
        payload=dict(child_id='child-1',name='示例新称呼',grade='五年级',classroom='二班',version=0,reason='虚构HTTP核对')
        try:
            before=self.database()
            self.assertEqual(request(payload,token=False)[0],403)
            self.assertEqual(request(payload,host='untrusted.invalid')[0],403)
            self.assertEqual(self.database(),before)
            status,result=request(payload);self.assertEqual(status,200);self.assertEqual(result['profile']['version'],1)
            changed=self.database();status,result=request(payload)
            self.assertEqual(status,409);self.assertEqual(result['code'],'profile_version_conflict')
            self.assertEqual(self.database(),changed)
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__=='__main__': unittest.main()

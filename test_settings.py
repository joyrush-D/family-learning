"""Synthetic first-run/settings/worker/HTTP flow: python3 test_settings.py."""
import http.client
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import family_agent
import family_collect
import family_llm
import family_review
import family_settings
import init_family


class SettingsTests(unittest.TestCase):
    def test_incomplete_environment_is_visible_without_unlocking_or_leaking(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-model-environment-') as directory, patch.dict(os.environ,{},clear=True):
            root=Path(directory);data=root/'private';data.mkdir()
            with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
                store=app.settings_store(); empty=store.model_state()
                self.assertEqual(empty['error'],'');self.assertFalse(empty['configured'])
                saved=dict(revision=empty['revision'],base_url='http://127.0.0.1:32123/v1',model='synthetic-file-model',api_key='SYNTHETIC-FILE-KEY')
                store.save_model(saved);before=(data/'model.json').read_bytes()
                cases=[{'FAMILY_LLM_API_KEY':'SYNTHETIC-ENV-KEY'},
                       {'FAMILY_LLM_REASONING_EFFORT':'none'},
                       {'FAMILY_LLM_BASE_URL':'http://127.0.0.1:32124/v1'},
                       {'FAMILY_LLM_MODEL':'synthetic-env-model'},
                       {'FAMILY_LLM_BASE_URL':'http://user:SYNTHETIC-URL-SECRET@localhost/v1','FAMILY_LLM_MODEL':'synthetic-env-model'}]
                for env in cases:
                    with self.subTest(fields=sorted(env)),patch.dict(os.environ,env,clear=True):
                        state=store.model_state()
                        self.assertEqual(state['origin'],'environment')
                        self.assertFalse(state['configured']);self.assertTrue(state['error'],'invalid deployment configuration must explain why it cannot be used')
                        for secret in ('SYNTHETIC-ENV-KEY','SYNTHETIC-FILE-KEY','SYNTHETIC-URL-SECRET'):
                            self.assertNotIn(secret,json.dumps(state))
                        with self.assertRaises(family_settings.SettingsError) as failure:store.save_model(saved)
                        self.assertEqual(failure.exception.status,409)
                        self.assertEqual((data/'model.json').read_bytes(),before)
                        with self.assertRaises(family_llm.LLMUnavailable):family_llm.configuration(data)
                self.assertTrue(store.model_state()['configured']);self.assertEqual(store.model_state()['origin'],'file')

    def test_first_visit_household_bindings_model_and_access(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-settings-') as directory, patch.dict(os.environ,{},clear=True):
            root=Path(directory); data=root/'private';data.mkdir()
            with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
                self.assertEqual(app.snapshot()['children'],[])
                # Visiting first does not prevent the existing CLI initializer, nor erase its empty DB.
                before=app.DB.stat().st_ino
                init_family.initialize(root,[('示例甲','四年级')])
                self.assertEqual(app.DB.stat().st_ino,before)
                store=app.settings_store(); state=store.snapshot()
                second=dict(name='示例乙',grade='初一',classroom='',request_key='synthetic-profile-create-02')
                child=store.create_child(second)['profile']; self.assertEqual(child['id'],'child-2')
                self.assertEqual(store.create_child(second)['profile']['id'],child['id'])
                with self.assertRaises(family_settings.SettingsError): store.create_child({**second,'name':'示例丙'})
                changed=app.save_profile(dict(child_id=child['id'],name='示例新称呼',grade='初二',classroom='示例班',version=1,reason='虚构更正'))
                self.assertEqual(changed['version'],2)
                with self.assertRaises(family_settings.SettingsError): store.create_child({**second,'request_key':'synthetic-profile-create-03'})
                groups=[dict(id='wechat:100000001@chatroom',platform='wechat',child_id='child-1',name='虚构主要班级群',enabled=True),
                        dict(id='qq:200000001',platform='qq',child_id=child['id'],name='虚构第二班级群',enabled=True)]
                def save(rows,enabled=True,revision=None):
                    return store.save_sources(dict(revision=revision or store.snapshot()['revision'],enabled=enabled,sources=rows))
                state=save(groups); self.assertEqual(len(app.agent_store().collector_plan()['sources']),2)
                first=app.agent_store().collector_plan()['sources'][0]
                self.assertEqual(first['cursor'],'0')
                envelope=dict(ok=True,tool='messages',command='history',data=dict(freshness=dict(message_source='live_message_db'),query=dict(chat='100000001@chatroom',limit=200,offset=0,order='asc',display_order='query',returned=0,has_more=False),messages=[]))
                self.assertEqual(family_collect.wechat_page(envelope,first),([],'0',''))
                old=state['revision'];stamp='2026-09-08T18:00:00+08:00'
                app.agent_store().ingest(dict(source_id=groups[0]['id'],expected_cursor='0',cursor='17',checked_at=stamp,last_message_time=stamp,error='',
                    messages=[dict(id='17',time=stamp,kind='text',sender='虚构老师',text='虚构阅读通知。',unread=False)]))
                groups[0]['enabled']=False
                state=save(groups);self.assertEqual(state['sources'][0]['cursor'],'17')
                self.assertEqual(len(app.agent_store().collector_plan()['sources']),1)
                with self.assertRaises(family_settings.SettingsError): save(groups,False,old)
                with self.assertRaises(family_settings.SettingsError): save(groups[1:])
                with self.assertRaises(family_settings.SettingsError): save([{**groups[0],'child_id':child['id']},groups[1]])
                state=save(groups,False)
                self.assertEqual(family_agent.run_once(app)['state'],'disabled')
                groups[0]['enabled']=True;state=save(groups)
                with app.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_messages').fetchone()[0],1)
                model=dict(revision=state['model']['revision'],base_url='http://127.0.0.1:32123/v1',model='synthetic-model',api_key='SYNTHETIC-KEY')
                configured=store.save_model(model)['model']
                self.assertTrue(configured['has_api_key']);self.assertNotIn('SYNTHETIC-KEY',json.dumps(store.snapshot()))
                self.assertEqual(stat.S_IMODE((data/'model.json').stat().st_mode),0o600)
                self.assertTrue(app.snapshot()['llm']['configured'])
                with self.assertRaises(family_settings.SettingsError): store.save_model({**model,'revision':configured['revision'],'base_url':'http://127.0.0.1:32124/v1','api_key':''})
                # A standalone process with --root/--data uses this family's saved endpoint and key.
                captured=[]
                class Opener:
                    def open(self,request,timeout):
                        captured.append((request.full_url,request.get_header('Authorization'),json.loads(request.data)))
                        return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"proposals":[]}'}}]}).encode())
                loaded=family_review.load_app(root,data)
                with patch.object(family_llm,'build_opener',return_value=Opener()):
                    self.assertEqual(family_agent.run_once(loaded)['processed'],1)
                self.assertEqual(captured[0][0],model['base_url']+'/chat/completions')
                self.assertEqual(captured[0][1],'Bearer SYNTHETIC-KEY')
                self.assertEqual(captured[0][2]['model'],'synthetic-model')
                with patch.dict(os.environ,{'FAMILY_LLM_BASE_URL':'http://127.0.0.1:32125/v1','FAMILY_LLM_MODEL':'environment-model'}):
                    self.assertEqual(store.model_state()['origin'],'environment');self.assertFalse(store.model_state()['has_api_key'])
                    with self.assertRaises(family_settings.SettingsError): store.save_model(model)
                cleared=store.save_model({**model,'revision':configured['revision'],'api_key':'','clear_api_key':True})['model']
                self.assertFalse(cleared['has_api_key'])
                server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                def call(method,path,body=None,token=True,host='localhost'):
                    connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                    headers={'Host':host,'Content-Type':'application/json'}
                    if token: headers['X-Family-Token']=app.TOKEN
                    connection.request(method,path,json.dumps(body) if body is not None else None,headers)
                    response=connection.getresponse();raw=response.read();connection.close()
                    return response.status,json.loads(raw)
                try:
                    self.assertEqual(call('GET','/api/settings')[0],200)
                    with patch.object(family_llm,'_chat_json',return_value={'ok':True}) as model_call:
                        self.assertEqual(call('POST','/api/settings/model/test',{})[0],200)
                        self.assertEqual(model_call.call_args.kwargs['data_path'],data)
                        self.assertNotIn('示例',json.dumps(model_call.call_args.args,ensure_ascii=False))
                        self.assertEqual(call('POST','/api/settings/model/test',{},token=False)[0],403)
                        self.assertEqual(call('POST','/api/settings/model/test',{'text':'虚构家庭材料'})[0],400)
                        self.assertEqual(model_call.call_count,1)
                    with patch.object(family_llm,'_chat_json',side_effect=family_llm.LLMDraftError('连接超时')):
                        self.assertEqual(call('POST','/api/settings/model/test',{})[0],503)
                    self.assertEqual(call('GET','/api/settings',host='unknown.invalid')[0],403)
                    self.assertEqual(call('POST','/api/settings/child',second,token=False)[0],403)
                    self.assertNotEqual(call('GET','/child/api/settings')[0],200)
                    self.assertEqual(call('POST','/api/settings/model',dict(revision=cleared['revision'],base_url='not-url',model='bad'))[0],400)
                finally: server.shutdown();server.server_close();thread.join()

    def test_web_only_first_child_and_failed_write_preserve_configuration(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-web-first-') as directory, patch.dict(os.environ,{},clear=True):
            root=Path(directory);data=root/'private';data.mkdir()
            with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
                store=app.settings_store()
                child=store.create_child(dict(name='示例家庭孩子',grade='',classroom='',request_key='synthetic-web-first-child'))['profile']
                self.assertEqual(child['id'],'child-1');self.assertEqual(app.snapshot()['children'][0]['name'],'示例家庭孩子')
                self.assertTrue(all((root/(name+'.md')).is_file() for name in ['家庭运行规则','消息来源','跟踪台账','学习与成长']))
                with self.assertRaises(ValueError): init_family.initialize(root,[('其它示例','初一')])
                before=store.snapshot()['revision']
                with patch.object(family_settings.os,'replace',side_effect=OSError('synthetic disk failure')):
                    with self.assertRaises(OSError): store.save_sources(dict(revision=before,enabled=True,sources=[]))
                self.assertEqual(store.snapshot()['revision'],before);self.assertFalse(store.snapshot()['enabled'])


if __name__=='__main__': unittest.main()

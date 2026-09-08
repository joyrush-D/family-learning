"""Synthetic HTTP after-school workflow; no actual family, model, or device calls."""
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import app

class StudyHTTPTest(unittest.TestCase):
    def test_workflow_access_ownership_and_persistence(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-study-http-') as tmp:
            root=Path(tmp);private=root/'private';private.mkdir()
            (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
            with patch.multiple(app,ROOT=root,DATA=private,DB=private/'family.sqlite3'), patch.dict(app.os.environ,{'FAMILY_HOST':'family.example.invalid','FAMILY_USER':'parent@example.invalid'}), patch.object(app.family_llm,'_chat_json',side_effect=AssertionError('No model in time-account API')):
                server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                def request(path,obj=None,headers=None):
                    c=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
                    try:
                        c.request('GET' if obj is None else 'POST',path,None if obj is None else json.dumps(obj),headers or {})
                        r=c.getresponse();return r.status,json.loads(r.read())
                    finally:c.close()
                today=app.dt.datetime.now(app.family_study.TZ).date().isoformat();query='/api/study?child_id=child-1&day='+today
                def post(path,obj,who='child-1'):
                    return request('/api/study/'+path,dict(child_id=who,day=today,request_key=uuid.uuid4().hex,**obj),{'X-Family-Token':app.TOKEN,'Content-Type':'application/json'})
                try:
                    code,state=request(query);self.assertEqual(code,200);self.assertEqual(state['items'],[]);self.assertIsNone(state['summary']['available_minutes'])
                    self.assertEqual(request('/api/study/item',{})[0],403)
                    self.assertEqual(request(query,headers={'Host':'family.example.invalid'})[0],403)
                    self.assertEqual(request('/api/study?child_id=child-1&child_id=child-2&day='+today)[0],400)
                    code,saved=post('day',dict(version=0,start_time='17:00',stop_time='21:00',bed_time='21:30'));self.assertEqual(code,200,saved)
                    code,saved=post('item',dict(title='虚构数学五题',subject='数学',planned_minutes=20));self.assertEqual(code,200,saved);item=saved['items'][0]
                    self.assertEqual(post('action',dict(id=item['id'],version=item['version'],action='start'),'child-2')[0],404)
                    code,started=post('action',dict(id=item['id'],version=item['version'],action='start'));self.assertEqual(code,200,started);item=started['items'][0]
                    self.assertEqual(request(query)[1]['items'][0]['running_since'],item['running_since'])
                    key=uuid.uuid4().hex;finish=dict(child_id='child-1',day=today,id=item['id'],version=item['version'],request_key=key,action='finish',result='完成',actual_minutes=18,note='五题核对有一题需要订正',assistance='少量提示')
                    headers={'X-Family-Token':app.TOKEN,'Content-Type':'application/json'}
                    code,done=request('/api/study/action',finish,headers);self.assertEqual(code,200,done)
                    self.assertEqual(request('/api/study/action',finish,headers)[0],200)
                    state=request('/api/state')[1];self.assertEqual(len(state['records']),1);record=state['records'][0];self.assertIn('18.0',record['note'])
                    self.assertEqual(state['tasks'][0]['update']['status'],'已完成')
                    obj={k:record[k] for k in ['id','child','day','category','subject','title','note','source','assistance','attachments']}
                    code,error=request('/api/record',{**obj,'note':'不应覆盖时间账'},headers);self.assertEqual(code,409,error);self.assertEqual(error['code'],'study_record_owned')
                    self.assertEqual(request('/api/record',obj,headers)[0],200,'unchanged owned fields permit original-file workflow')
                    self.assertEqual(len(request('/api/state')[1]['records']),1)
                    self.assertEqual(request('/api/study?child_id=child-2&day='+today)[1]['items'],[])
                    invitation=app.family_child.parent_action(app,'invite',{'child_id':'child-1'})
                    code,child=request('/child/api/login',{'invite':invitation['invite']},{'Content-Type':'application/json'});self.assertEqual(code,200,child)
                    self.assertIn(request('/child/api/study')[0],[401,404],'parent time accounts are not exposed by child namespace')
                    with app.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM study_items').fetchone()[0],1)
                finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()

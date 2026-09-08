"""python3 test_task_focus.py: isolated fictional follow-up choices and access checks."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

import family_task_focus as focus


def reject(call, code=None):
    try: call()
    except focus.FocusError as error:
        if code: assert error.code==code,(error.code,code)
    else: raise AssertionError('Invalid task arrangement accepted')


with tempfile.TemporaryDirectory(prefix='synthetic-task-focus-') as folder, patch.dict(os.environ,{},clear=True):
    root=Path(folder).resolve();data=root/'private';data.mkdir()
    with patch.dict(os.environ,{'FAMILY_DATA':str(data)}):
        import app
    with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 虚构学校事项 | 2026-09-09 | 待跟进 | 虚构通知 | 原始提交要求 |\n'
            '| T02 | 示例甲 | 虚构归档事项 | 2026-09-10 | 已归档（仅留存） | 虚构通知 | 原始要求 |\n')
        # Visiting or reading a default does not persist a guessed arrangement.
        initial=app.snapshot()
        with app.connect() as c:
            before='\n'.join(c.iterdump())
            assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='task_focus'").fetchone()
        assert app.tasks()[0]['focus']==focus.default()
        with app.connect() as c: assert '\n'.join(c.iterdump())==before
        n=[0]
        def request(**fields):
            n[0]+=1
            return dict(id='T01',version=0,request_key='synthetic-focus-'+str(n[0]),mode='next',next_action='',waiting_for='',review_on='')|fields
        for bad in ['2026-02-30','20260909','2026-W37-3','2026-9-09','0000-01-01']:
            reject(lambda:focus.save(app,request(mode='later',review_on=bad)))
        for bad in [True,-1,1.5,'0']:
            reject(lambda:focus.save(app,request(version=bad)))
        reject(lambda:focus.save(app,request(mode='waiting')))
        reject(lambda:focus.save(app,request(mode='unknown')))
        reject(lambda:focus.save(app,request(next_action='x'*2001)))
        reject(lambda:focus.save(app,request(waiting_for='x'*201)))
        reject(lambda:focus.save(app,request(id='missing')),'task_missing')
        reject(lambda:focus.save(app,request(id='T02')),'task_focus_closed')
        with app.connect() as c: assert '\n'.join(c.iterdump())==before
        first=request(mode='waiting',waiting_for='虚构老师确认时间',next_action='收到回复后核对',review_on='2026-09-10')
        saved=focus.save(app,first)
        assert saved['focus']['version']==1 and saved['focus']['mode']=='waiting'
        assert saved['task']['due']=='2026-09-09' and saved['task']['action']=='原始提交要求'
        assert focus.save(app,first)['request_replayed']
        reject(lambda:focus.save(app,first|dict(waiting_for='另一人')),'task_focus_request_conflict')
        reject(lambda:focus.save(app,request(mode='later')),'task_focus_conflict')
        second=request(version=1,mode='later',next_action='核对学校新通知')
        assert focus.save(app,second)['focus']['review_on']==''
        # Lost receipt from an earlier request returns current state, never replays its old choice.
        assert focus.save(app,first)['focus']['mode']=='later'
        assert focus.save(app,first)['focus']['version']==2
        with app.connect() as c:
            assert c.execute('SELECT COUNT(*) FROM task_focus_history').fetchone()[0]==2
            assert c.execute('SELECT COUNT(*) FROM records').fetchone()[0]==0
            assert c.execute('SELECT COUNT(*) FROM task_history').fetchone()[0]==0
            assert c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0]==0
        # Follow-up choices do not silently stop timers or change the family's planned calendar.
        study=app.study_store()
        study.save_item(dict(child_id='child-1',day='2026-09-08',request_key='synthetic-study-item',task_id='T01',planned_minutes=20))
        item=study.snapshot('child-1','2026-09-08')['items'][0]
        study.action(dict(child_id='child-1',day='2026-09-08',request_key='synthetic-study-start',id=item['id'],version=item['version'],action='start'))
        def rows(table):
            with app.connect() as c: return [tuple(row) for row in c.execute('SELECT * FROM '+table)]
        preserved={name:rows(name) for name in ('study_items','study_days','calendar_events','records','task_updates','task_history')}
        third=request(version=2,mode='waiting',waiting_for='虚构同伴答复',review_on='2026-09-12')
        focus.save(app,third)
        assert {name:rows(name) for name in preserved}==preserved
        assert app.tasks()[0]['due']=='2026-09-09' and app.tasks()[0]['action']=='原始提交要求'
        app.save_profile(dict(child_id='child-1',version=0,name='示例新称呼',grade='四年级',classroom='',reason='虚构更名'))
        task=app.tasks()[0]
        assert task['id']=='T01' and task['child']=='示例新称呼' and task['focus']['version']==3
        for status in ('已完成','不参加','不适用'):
            app.save_task(dict(id='T01',status=status,note='虚构家庭决定'))
            reject(lambda:focus.save(app,request(version=3)),'task_focus_closed')
            assert focus.save(app,third)['focus']['version']==3
            app.save_task(dict(id='T01',status='待跟进',note='虚构恢复'))
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        reply_headers={}
        def call(path,body=None,token=True,headers=None):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
            values={'Host':'localhost','Content-Type':'application/json'}
            if token: values['X-Family-Token']=app.TOKEN
            values.update(headers or {})
            connection.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,values)
            response=connection.getresponse();raw=response.read();reply_headers.clear();reply_headers.update(response.getheaders());connection.close()
            return response.status,json.loads(raw)
        try:
            assert call('/child/api/state',token=False)[0]==401
            assert call('/api/task/focus',request(version=3),token=False)[0]==403
            assert call('/api/task/focus',request(version=3),headers={'Host':'untrusted.invalid'})[0]==403
            assert call('/child/api/task/focus',request(version=3))[0]==404
            import family_child
            invite=family_child.parent_action(app,'invite',dict(child_id='child-1'))
            login=call('/child/api/login',dict(invite=invite['invite']),token=False)
            assert login[0]==200
            child_headers={'Cookie':reply_headers['Set-Cookie'].split(';',1)[0],'X-Child-CSRF':login[1]['csrf']}
            assert call('/api/task/focus',request(version=3),token=False,headers=child_headers)[0]==403
            assert call('/child/api/task/focus',request(version=3),token=False,headers=child_headers)[0]==404
            with patch.dict(os.environ,{'FAMILY_HOST':'synthetic-family.invalid','FAMILY_USER':'synthetic@example.invalid'}):
                assert call('/api/task/focus',request(version=3),headers={'Host':'synthetic-family.invalid'})[0]==403
                result=call('/api/task/focus',request(version=3),headers={'Host':'synthetic-family.invalid','Tailscale-User-Login':'synthetic@example.invalid'})
                assert result[0]==200 and result[1]['focus']['version']==4
            state=call('/api/state')[1]
            task=next(t for t in state['tasks'] if t['id']=='T01')
            assert task['focus']['mode']=='next' and task['focus']['waiting_for']==task['focus']['review_on']==''
            assert call('/api/task/focus',request(version=3))[0]==409
        finally: server.shutdown();server.server_close();worker.join()
        competing=[request(version=4,mode='later',review_on='2026-09-15'),request(version=4,mode='waiting',waiting_for='虚构老师回复')]
        def submit(obj):
            try: return focus.save(app,obj)['focus']['version']
            except focus.FocusError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(submit,competing))
        assert outcomes.count(5)==1 and outcomes.count('task_focus_conflict')==1
        expected=app.tasks()[0]['focus']
        import family_backup
        archive=family_backup.create(root,Path('private/backups/synthetic-focus.zip'))
        restored=family_backup.restore(archive,root/'restored')
        with patch.multiple(app,ROOT=restored,DATA=restored/'private',DB=restored/'private/family.sqlite3'):
            assert app.tasks()[0]['focus']==expected
            assert focus.save(app,third)['focus']==expected
            with app.connect() as c: assert c.execute('SELECT COUNT(*) FROM task_focus_history').fetchone()[0]==5

print('PASS: task follow-up defaults, validation, retry, CAS, stable IDs, source/time preservation and parent-only HTTP access')

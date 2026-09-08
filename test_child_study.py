"""python3 test_child_study.py: fictional child time accounts, provenance and access races."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch

import app
import family_backup
import family_child as child
import family_study as study


with tempfile.TemporaryDirectory(prefix='synthetic-child-study-') as folder, patch.dict(os.environ,{},clear=True):
    root=Path(folder).resolve();data=root/'private';data.mkdir()
    today=dt.datetime.now(study.TZ).date().isoformat()
    yesterday=(dt.date.fromisoformat(today)-dt.timedelta(days=1)).isoformat()
    tomorrow=(dt.date.fromisoformat(today)+dt.timedelta(days=1)).isoformat()
    with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 虚构数学功课 | '+today+' | 待跟进 | GROUP_PRIVATE_CANARY | 先做练习一，再核对例题 |\n'
            '| T02 | 示例乙 | OTHER_CHILD_PRIVATE_CANARY | '+today+' | 待跟进 | GROUP_PRIVATE_CANARY | 另一孩子要求 |\n'
            '| T03 | 示例甲 | UNASSIGNED_PRIVATE_CANARY | '+today+' | 待跟进 | GROUP_PRIVATE_CANARY | 尚未安排 |\n')
        store=app.study_store();serial=[0]
        def req(**fields):
            serial[0]+=1
            return dict(day=today,request_key='synthetic-child-study-'+str(serial[0]),**fields)
        def parent_item(task_id,child_id='child-1',day=today):
            return store.save_item(dict(req(task_id=task_id,planned_minutes=20),child_id=child_id,day=day))['items'][-1]
        assigned=parent_item('T01');other=parent_item('T02','child-2')
        def parent_row(ident):
            with app.connect() as c: return dict(c.execute('SELECT * FROM study_items WHERE id=?',(ident,)).fetchone())
        def parent_action(ident,action,**fields):
            row=parent_row(ident)
            return store.action(dict(req(id=ident,version=row['version'],action=action,**fields),child_id=row['child_id'],day=row['day']))
        parent_action(assigned['id'],'finish',result='需要帮助',note='PARENT_NOTE_PRIVATE_CANARY')
        original_record=parent_row(assigned['id'])['record_id']
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def http(path,obj=None,session=None,csrf=True,parent=False,headers=None):
            values={'Host':'localhost','Content-Type':'application/json'}|dict(headers or {})
            if parent: values['X-Family-Token']=app.TOKEN
            if session:
                values['Cookie']=session['cookie']
                if csrf: values['X-Child-CSRF']=session['csrf']
            conn=HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST' if obj is not None else 'GET',path,json.dumps(obj) if obj is not None else None,values)
            reply=conn.getresponse();raw=reply.read();info=dict(reply.getheaders());code=reply.status;conn.close()
            return code,json.loads(raw),info
        def login(ident):
            invitation=child.parent_action(app,'invite',dict(child_id=ident))
            code,state,headers=http('/child/api/login',dict(invite=invitation['invite']))
            assert code==200
            return dict(cookie=headers['Set-Cookie'].split(';',1)[0],csrf=state['csrf'])
        first=login('child-1');second=login('child-2')
        def call(action,obj,session=first,**kwargs): return http('/child/api/study/'+action,obj,session,**kwargs)
        def state(session=first,day=today):
            result=call('state',dict(day=day),session);assert result[0]==200,result
            return result[1]
        def action(ident,operation,**fields):
            row=parent_row(ident)
            return call('action',dict(req(id=ident,version=row['version'],action=operation,**fields),day=row['day']))
        try:
            assert child.parent_state(app)['children'][0]['study_enabled'] is False
            assert call('state',dict(day=today))[0]==403
            assert http('/api/child-access/study',dict(child_id='child-1',enabled=True),first)[0]==403
            assert http('/api/child-access/study',dict(child_id='child-1',enabled='yes'),parent=True)[0]==400
            assert http('/api/child-access/study',dict(child_id='child-1',enabled=True),parent=True)[0]==200
            assert http('/child/api/state',session=first)[1]['study_enabled'] is True
            assert child.parent_state(app)['children'][0]['study_enabled'] is True
            assert call('state',dict(day=today),csrf=False)[0]==403
            assert call('state',dict(day=today),headers={'Host':'untrusted.invalid'})[0]==403
            assert call('state',dict(day=today,child_id='child-2'))[0]==400
            assert call('state',dict(day=tomorrow))[0]==400
            snapshot=state();item=snapshot['items'][0]
            assert item['id']==assigned['id'] and item['editable'] and item['result_actor']=='parent' and item['note']==''
            assert item['source_task_action']=='先做练习一，再核对例题' and item['source_task_due']==today
            text=json.dumps(snapshot)
            for hidden in ('CANARY','record_id','task_id','available_tasks','week','child_id',app.TOKEN): assert hidden not in text,hidden
            assert call('item',req(task_id='T03',planned_minutes=10))[0]==400
            assert call('item',dict(req(title='虚构补记功课'),day=yesterday))[0]==400
            assert call('action',req(id=other['id'],version=1,action='start'))[0]==404
            assert call('action',req(id=assigned['id'],version=item['version'],action='close_day'))[0]==400
            assert call('action',req(id=assigned['id'],version=item['version'],action='finish',result='完成',result_actor='parent'))[0]==400
            assert http('/api/study/action',req(child_id='child-1',id=assigned['id'],version=item['version'],action='finish',result='完成'),first)[0]==403
            assert action(assigned['id'],'start')[0]==200
            assert action(assigned['id'],'pause')[0]==200
            report=req(id=assigned['id'],version=parent_row(assigned['id'])['version'],action='finish',result='完成',actual_minutes=12,note='虚构：自己做完了')
            result=call('action',report)
            assert result[0]==200,result
            assert call('action',report)[0]==200
            row=parent_row(assigned['id']);assert row['result_actor']=='child' and row['record_id']==original_record
            with app.connect() as c:
                assert c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0]==0
                assert '孩子自述，待家长核对' in c.execute('SELECT note FROM records WHERE id=?',(original_record,)).fetchone()[0]
                assert any('PARENT_NOTE_PRIVATE_CANARY' in r[0] for r in c.execute('SELECT previous FROM revisions WHERE record_id=?',(original_record,)))
            assert call('action',report|dict(note='其它文字'))[0]==409
            assert call('action',req(id=assigned['id'],version=0,action='manual',actual_minutes=20))[0]==409
            assert action(assigned['id'],'manual',actual_minutes=13)[0]==200
            parent_action(assigned['id'],'finish',result='完成',note='虚构家长核对完成')
            row=parent_row(assigned['id']);assert row['result_actor']=='parent' and row['record_id']==original_record
            with app.connect() as c: assert c.execute('SELECT status FROM task_updates WHERE id=?',('T01',)).fetchone()[0]=='已完成'
            assert state()['items'][0]['editable'] is False
            assert action(assigned['id'],'manual',actual_minutes=1)[0]==409
            assert call('item',req(id=assigned['id'],version=row['version'],planned_minutes=1))[0]==409
            # Parent correction to a partial result allows a new child attempt and retains revisions.
            parent_action(assigned['id'],'finish',result='做了一部分',note='PARENT_CORRECTION_PRIVATE_CANARY')
            assert state()['items'][0]['editable']
            assert action(assigned['id'],'finish',result='需要帮助')[0]==200
            assert state()['items'][0]['note']==''
            created=req(title='虚构自主阅读',subject='语文',planned_minutes=15)
            result=call('item',created);assert result[0]==200,result
            added=next(r for r in result[1]['items'] if r['id']!=assigned['id'])
            assert call('item',created)[0]==200
            assert call('item',req(id=added['id'],version=added['version'],planned_minutes=18))[0]==200
            assert action(added['id'],'finish',result='做了一部分',note='虚构孩子记录')[0]==200
            linked=parent_row(added['id'])['record_id']
            with app.connect() as c: c.execute('UPDATE records SET note=? WHERE id=?',('PARENT_EXTERNAL_EDIT_PRIVATE_CANARY',linked))
            before=parent_row(added['id'])
            assert action(added['id'],'manual',actual_minutes=4)[0]==409
            assert parent_row(added['id'])==before
            # A parent's subsequent dismissal blocks every child write, including estimated time.
            app.save_task(dict(id='T01',status='不参加',note='虚构家长决定'))
            assert action(assigned['id'],'finish',result='完成')[0]==409
            assert call('item',req(id=assigned['id'],version=parent_row(assigned['id'])['version'],planned_minutes=12))[0]==409
            # Completing the original checklist item must also stop its active child timer.
            result=call('item',req(title='虚构家长清单核对',planned_minutes=10));assert result[0]==200
            closing=next(r for r in result[1]['items'] if r['title']=='虚构家长清单核对')
            assert action(closing['id'],'start')[0]==200
            running=parent_row(closing['id'])
            decision=dict(id=running['task_id'],status='已完成',note='虚构家长在清单核对完成')
            assert http('/api/task',decision,parent=True)[0]==200
            stopped=parent_row(closing['id'])
            assert stopped['running_since'] is None and stopped['status']=='paused'
            assert stopped['version']>running['version'] and stopped['elapsed_seconds']>=running['elapsed_seconds']
            assert http('/api/task',decision,parent=True)[0]==200 and parent_row(closing['id'])==stopped
            assert action(closing['id'],'start')[0]==409
            # Authorization changes after initial HTTP/session lookup are rechecked under the writer lock.
            waiting=threading.Event();resume=threading.Event();original=study.Store.save_item
            def delayed(self,obj):
                if self.actor=='child': waiting.set();assert resume.wait(5)
                return original(self,obj)
            pending=req(title='必须拒绝的虚构功课')
            with patch.object(study.Store,'save_item',delayed),ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(call,'item',pending);assert waiting.wait(5)
                child.parent_action(app,'study',dict(child_id='child-1',enabled=False));resume.set()
                assert future.result()[0]==403
            assert call('item',pending)[0]==403
            child.parent_action(app,'study',dict(child_id='child-1',enabled=True))
            waiting.clear();resume.clear()
            with patch.object(study.Store,'save_item',delayed),ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(call,'item',pending);assert waiting.wait(5)
                child.parent_action(app,'revoke',dict(child_id='child-1'));resume.set()
                assert future.result()[0]==401
            assert http('/child/api/state',session=second)[0]==200
            assert not any(t['title']==pending['title'] for t in app.tasks())
            # Existing history is available only for its owning child; new past items remain denied.
            historical=parent_item('T03',day=yesterday)
            first=login('child-1')
            past=call('state',dict(day=yesterday),first)
            assert past[0]==200 and [r['id'] for r in past[1]['items']]==[historical['id']]
        finally: server.shutdown();server.server_close();thread.join()
        expected=parent_row(assigned['id'])['result_actor']
        archive=family_backup.create(root,Path('private/backups/child-study.zip'))
        restored=family_backup.restore(archive,root/'restored')
        with patch.multiple(app,ROOT=restored,DATA=restored/'private',DB=restored/'private/family.sqlite3'):
            assert app.study_store().snapshot('child-1',today)['items'][0]['result_actor']==expected
            assert child.parent_state(app)['children'][0]['study_enabled'] is True
            with app.connect() as c: assert c.execute('SELECT COUNT(*) FROM child_sessions').fetchone()[0]==0

print('PASS: child homework sessions, explicit access/revoke races, isolation, idempotency, self-report/parent confirmation and restore')

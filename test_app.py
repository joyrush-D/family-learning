"""Run python3 test_app.py. Uses only synthetic data in a temporary directory."""
import http.client
import json
import sqlite3
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch
import app
import family_backup

with tempfile.TemporaryDirectory() as tmp:
    app.ROOT=Path(tmp).resolve();app.DATA=app.ROOT/'private';app.DATA.mkdir();app.DB=app.DATA/'family.sqlite3'
    (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
    (app.ROOT/'跟踪台账.md').write_text('| T01 | 示例甲 | 阅读 | 无截止 | 待核查 | 示例来源 | 核查 |\n')
    app.save_record(dict(child='示例甲',day='2026-09-07',category='成绩',subject='数学',title='单元复测',score='85',total='100',note='虚构数据'))
    for extra in [dict(score='101'),dict(score='NaN'),dict(child='未知'),dict(day='2026-02-30')]:
        try:app.save_record(dict(child='示例甲',day='2026-09-07',category='成绩',subject='数学',title='测验',score='85',total='100',**{})|extra)
        except ValueError:pass
        else:raise AssertionError('invalid input accepted')
    try:app.save_task(dict(id='T01',status='已完成'))
    except ValueError:pass
    else:raise AssertionError('completion needs evidence')
    app.save_record(dict(id=1,child='示例甲',day='2026-09-07',category='成绩',subject='数学',title='核对后的单元复测',score='86',total='100'))
    assert app.snapshot()['records'][0]['score']==86
    with app.connect() as c: assert c.execute('SELECT count(*) FROM revisions').fetchone()[0]==1
    app.save_task(dict(id='T01',status='已完成',note='家长已核查'))
    s=app.snapshot();assert len(s['records'])==1 and s['tasks'][0]['update']['status']=='已完成'
    app.save_task(dict(id='T01',status='待跟进',note='复查'))
    assert app.snapshot()['tasks'][0]['update']['status']=='待跟进'
    history=app.snapshot()['tasks'][0]['history']
    assert [h['status'] for h in history]==['待跟进','已完成']
    assert history[1]['note']=='家长已核查'
    app.save_task(dict(id='T01',status='待跟进',note='复查'))
    assert len(app.snapshot()['tasks'][0]['history'])==2
    with app.connect() as c:
        c.execute('DELETE FROM task_history')
    app.save_task(dict(id='T01',status='进行中',note='补充进展'))
    assert [h['note'] for h in app.snapshot()['tasks'][0]['history']]==['补充进展','复查']
    (app.DATA/'陪伴建议.json').write_text('{invalid')
    assert app.snapshot()['care']['error'] and app.snapshot()['tasks']
    (app.DATA/'陪伴建议.json').write_text('[]')
    assert app.care_notes()==dict(items=[],error='')
    candidate=dict(child='示例甲',title='手动记录的虚构通知',due='',source='',action='')
    for extra in [dict(child='未知'),dict(title=' '),dict(title='a'*201),dict(due='a'*201),
                  dict(due=None),dict(source={}),dict(action='a'*4001),dict(action=None)]:
        try: app.new_task(candidate|extra)
        except ValueError: pass
        else: raise AssertionError('invalid manual task accepted')
    manual=app.new_task(candidate|dict(id='T01'))
    assert manual['id'].startswith('MANUAL-') and len(manual['id'])==27
    assert manual['due']=='无明确截止' and manual['source']=='家长录入'
    assert {t['id'] for t in app.tasks()}=={'T01',manual['id']}
    original_token_hex=app.secrets.token_hex
    app.secrets.token_hex=lambda count:manual['id'][7:]
    try:
        try: app.new_task(candidate|dict(title='不能覆盖原待办'))
        except sqlite3.IntegrityError: pass
        else: raise AssertionError('duplicate ID overwrote manual task')
    finally: app.secrets.token_hex=original_token_hex
    assert app.tasks()[0]=={**manual,'focus':app.family_task_focus.default()}
    app.save_task(dict(id=manual['id'],status='已完成',note='虚构确认'))
    app.save_task(dict(id=manual['id'],status='待跟进',note='虚构复查'))
    assert [h['status'] for h in app.snapshot()['tasks'][0]['history']]==['待跟进','已完成']
    # Dismiss is an explicit, reversible decision, not learning progress or completion.
    state=app.snapshot();previous=state['tasks'][0]['update']['updated']
    for invalid in ('不参加','不适用'):
        try: app.save_task(dict(id=manual['id'],status=invalid,note=''))
        except app.TaskError: pass
        else: raise AssertionError('dismiss requires an explicit decision note')
    dismissed=dict(id=manual['id'],status='不参加',note='虚构家长决定本次不参加',expected_updated=previous)
    app.save_task(dismissed)
    changed=app.snapshot()
    assert changed['records']==state['records'] and changed['rewards']==state['rewards']
    assert changed['tasks'][0]['update']['status']=='不参加'
    app.save_task(dismissed)
    assert app.snapshot()['tasks']==changed['tasks']
    try: app.save_task(dict(id=manual['id'],status='已完成',note='虚构旧页面操作',expected_updated=previous))
    except app.TaskError as error: assert error.status==409 and error.code=='task_conflict'
    else: raise AssertionError('stale completion overwrote a dismiss decision')
    assert app.snapshot()['tasks']==changed['tasks']
    for question in ('哪些不参加？','哪些已搁置？'):
        evidence,_=app.query_evidence('示例甲',question)
        assert next(row for row in evidence if row['kind']=='task')['target_id']==manual['id']
    app.save_task(dict(id=manual['id'],status='不适用',note='虚构无需处理',expected_updated=changed['tasks'][0]['update']['updated']))
    evidence,_=app.query_evidence('示例甲','哪些无需处理？')
    assert next(row for row in evidence if row['kind']=='task')['target_id']==manual['id']
    app.save_task(dict(id=manual['id'],status='待跟进',note='虚构明确恢复'))
    assert app.task_status(dict(original_status='不参加'))=='不参加'

    # Prior record versions are readable independently of current names and files.
    upload_ids=['a'*32,'b'*32,'c'*32]
    (app.DATA/'uploads').mkdir(exist_ok=True)
    with app.connect() as c:
        for ident in upload_ids:
            raw=b'SYNTHETIC_IMAGE'
            (app.DATA/'uploads'/ident).write_bytes(raw)
            c.execute('INSERT INTO uploads VALUES (?,?,?,?,?)',(ident,'synthetic.png',len(raw),'image/png','2026-09-08'))
    edit=dict(id=1,child='示例甲',day='2026-09-07',category='成绩',subject='数学',title='虚构多次更正',total='100',attachments=upload_ids)
    app.save_record(edit|dict(score='87'))
    app.save_record(edit|dict(score='87.5'))
    app.save_profile(dict(child_id='child-1',name='示例新称呼',grade='五年级',classroom='',version=0,reason='虚构称呼更正'))
    app.save_record(edit|dict(child='示例新称呼',score='88',attachments=[upload_ids[0]]))
    (app.DATA/'uploads'/upload_ids[1]).unlink()
    with app.connect() as c:
        c.execute('DELETE FROM uploads WHERE id=?',(upload_ids[2],))
        legacy=dict(c.execute('SELECT * FROM records WHERE id=1').fetchone());legacy.pop('attachments')
        legacy['title']='虚构早期版本未记录附件字段'
        c.execute('INSERT INTO revisions (record_id,previous,changed) VALUES (?,?,?)',(1,json.dumps(legacy,ensure_ascii=False),'2026-09-08T08:30:00'))
        c.execute('INSERT INTO revisions (record_id,previous,changed) VALUES (?,?,?)',(1,'{broken','2026-09-08T08:31:00'))
    app.save_record(dict(child='示例新称呼',day='2026-09-08',category='家长观察',title='另一条虚构记录'))
    def database():
        with app.connect() as c: return '\n'.join(c.iterdump())
    history_before=database()
    versions=app.record_history(1)
    assert versions['record_id']==1 and versions['current']['score']==88
    assert versions['child_context']==dict(child_id='child-1',name='示例新称呼')
    assert versions['complete'] and versions['unreadable_count']==1 and len(versions['history'])==6
    assert [r['id'] for r in versions['history']]==sorted([r['id'] for r in versions['history']],reverse=True)
    assert versions['history'][0]['previous'] is None and versions['history'][0]['error']
    assert versions['history'][0]['changed']=='2026-09-08T08:31:00'
    assert versions['history'][1]['previous']['attachments_recorded'] is False
    assert versions['history'][1]['previous']['attachments']==[]
    previous=[r['previous'] for r in versions['history'][2:]]
    assert [r['score'] for r in previous]==[87.5,87,86,85]
    assert [r['child'] for r in previous]==['示例新称呼','示例甲','示例甲','示例甲']
    assert previous[1]['attachments']==upload_ids
    attachments={r['id']:r for r in versions['attachments']}
    assert attachments[upload_ids[0]]['available']
    assert not attachments[upload_ids[1]]['available'] and attachments[upload_ids[1]]['name']=='synthetic.png'
    assert not attachments[upload_ids[2]]['available'] and attachments[upload_ids[2]]['size'] is None
    assert all(attachments[i]['error'] for i in upload_ids[1:])
    assert '另一条虚构记录' not in json.dumps(versions,ensure_ascii=False)
    assert app.record_history(2)['history']==[] and app.record_history(999) is None
    assert database()==history_before

    with patch('socket.getfqdn',side_effect=AssertionError('Local startup must not resolve reverse DNS')):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    assert server.server_name=='127.0.0.1' and server.server_port==server.server_address[1]>0
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        # The HTTP bundle isolates every classic script from page globals.
        modules={'app.js':b'const syntheticApp=1;',
                 'reading.js':b'const syntheticReading=syntheticApp+1;',
                 'calendar.js':b'const syntheticCalendar=syntheticReading+1;',
                 'child-access.js':b'const syntheticAccess=syntheticCalendar+1;',
                 'learning.js':b'const syntheticLearning=syntheticAccess+1;',
                 'study.js':b'const syntheticStudy=syntheticLearning+1;',
                 'settings.js':b'const syntheticSettings=1;',
                 'guided.js':b'const syntheticGuided=syntheticLearning+1;'}
        for name,content in modules.items(): (app.ROOT/name).write_bytes(content)
        def get_raw(path,headers=None):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('GET',path,headers=headers or {})
            reply=client.getresponse();body=reply.read();kind=reply.getheader('Content-Type');client.close()
            return reply.status,body,kind
        expected=b'(()=>{\n'+b'\n;\n'.join(modules.values())+b'\n})();\n'
        assert get_raw('/app.bundle.js')==(200,expected,'text/javascript; charset=utf-8')
        assert get_raw('/app.bundle.js',{'Host':'untrusted.invalid'})[0]==403
        (app.ROOT/'calendar.js').unlink()
        status,body,_=get_raw('/app.bundle.js')
        assert status==500 and json.loads(body)['error'] and b'syntheticApp' not in body
        assert get_raw('/app.js')==(200,modules['app.js'],'text/javascript; charset=utf-8')
        (app.ROOT/'calendar.js').write_bytes(modules['calendar.js'])
        original_read_bytes=Path.read_bytes
        def denied_module(path):
            if path.name=='reading.js': raise PermissionError('synthetic private path must not leak')
            return original_read_bytes(path)
        with patch.object(Path,'read_bytes',denied_module):
            status,body,_=get_raw('/app.bundle.js')
            assert status==500 and b'synthetic private path' not in body and b'syntheticApp' not in body
        assert get_raw('/app.bundle.js')[1]==expected
        for name,content in modules.items(): assert get_raw('/'+name)[1]==content
        (app.ROOT/'startup.js').write_bytes(b'// synthetic startup monitor')
        assert get_raw('/startup.js')==(200,b'// synthetic startup monitor','text/javascript; charset=utf-8')
        for token,status in [('',403),(app.TOKEN,200)]:
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('POST','/api/task/new',json.dumps(candidate),
                           {'Content-Type':'application/json','X-Family-Token':token})
            reply=client.getresponse();body=json.loads(reply.read());client.close()
            assert reply.status==status
            if status==200: assert body['ok'] and body['task']['id']!=manual['id']
        def get(path,headers=None):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('GET',path,headers=headers or {})
            reply=client.getresponse();body=json.loads(reply.read());client.close()
            return reply.status,body
        prior=next(t for t in app.snapshot()['tasks'] if t['id']=='T01')['update']['updated']
        app.save_task(dict(id='T01',status='不参加',note='虚构HTTP并发决定',expected_updated=prior))
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        client.request('POST','/api/task',json.dumps(dict(id='T01',status='已完成',note='虚构旧表单完成',expected_updated=prior)),
                       {'Content-Type':'application/json','X-Family-Token':app.TOKEN})
        reply=client.getresponse();body=json.loads(reply.read());client.close()
        assert reply.status==409 and body['code']=='task_conflict'
        assert next(t for t in app.snapshot()['tasks'] if t['id']=='T01')['update']['status']=='不参加'
        # A failed connector-state file must not take down core household data.
        app.reading_store().mutate('create',dict(child_id='child-1',request_key='synthetic-source-fallback',book='虚构来源故障期间阅读'))
        sync_file=app.DATA/'采集状态.json'
        baseline=app.snapshot();unchanged=database()
        assert baseline['sync']=={} and baseline['sync_error']=='' and baseline['reading']['tasks']
        valid_sync={'synthetic-source':{'child':'示例甲','cursor':17},'malformed-entry':None,'another-bad-entry':[]}
        sync_file.write_text(json.dumps(valid_sync,ensure_ascii=False))
        status,body=get('/api/state')
        assert status==200 and body['sync_error']==''
        assert body['sync']==valid_sync|{'synthetic-source':{'child':'示例新称呼','cursor':17}}
        def assert_source_fallback():
            status,body=get('/api/state')
            assert status==200 and body['sync']=={} and body['sync_error']
            assert 'synthetic private path' not in json.dumps(body,ensure_ascii=False)
            for field in ('records','tasks','reading'): assert body[field]==baseline[field],field
            assert database()==unchanged
        for malformed in (b'{broken',b'[]',b'null',b'42',b'"state"',b'true',b'\xff'):
            sync_file.write_bytes(malformed)
            assert_source_fallback()
        sync_file.write_text('{}')
        original_read_text=Path.read_text
        def denied_sync(path,*args,**kwargs):
            if path==sync_file: raise PermissionError('synthetic private path must not leak')
            return original_read_text(path,*args,**kwargs)
        with patch.object(Path,'read_text',denied_sync): assert_source_fallback()
        sync_file.write_text('{broken')
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        client.request('POST','/api/record',json.dumps(dict(child='示例新称呼',day='2026-09-08',category='家长观察',
                       title='虚构来源故障时仍可手动保存',note='仅用于隔离HTTP回归')),
                       {'Content-Type':'application/json','X-Family-Token':app.TOKEN})
        reply=client.getresponse();saved=json.loads(reply.read());client.close()
        assert reply.status==200 and saved['ok']
        status,body=get('/api/state')
        assert status==200 and body['sync_error']
        assert any(r['title']=='虚构来源故障时仍可手动保存' and r['note']=='仅用于隔离HTTP回归' for r in body['records'])
        sync_file.write_text('{}')
        assert get('/api/state')[1]['sync_error']==''
        sync_file.unlink()
        assert get('/api/state')[1]['sync_error']==''
        history_before=database()
        status,body=get('/api/record/history/1')
        assert status==200 and body==versions  # Existing authenticated GET boundary, no write token.
        assert get('/api/record/history/1',{'Host':'untrusted.invalid'})[0]==403
        with patch.dict(app.os.environ,{'FAMILY_HOST':'synthetic-family.invalid','FAMILY_USER':'synthetic@example.invalid'}):
            assert get('/api/record/history/1',{'Host':'synthetic-family.invalid'})[0]==403
            assert get('/api/record/history/1',{'Host':'synthetic-family.invalid','Tailscale-User-Login':'other@example.invalid'})[0]==403
            assert get('/api/record/history/1',{'Host':'synthetic-family.invalid','Tailscale-User-Login':'synthetic@example.invalid'})[0]==200
        for suffix in ['', '0','-1','01','true','1.0','1/extra','9223372036854775808','%31']:
            assert get('/api/record/history/'+suffix)[0]==400
        assert get('/api/record/history')[0]==400
        assert get('/api/record/history/999')[0]==404
        assert get('/api/record/history/2')[1]['history']==[]
        assert database()==history_before
    finally:
        server.shutdown();server.server_close();worker.join()
    expected=app.snapshot()['tasks']
    assert len(expected)==3
    archive=family_backup.create(app.ROOT,Path('private/backups/test.zip'))
    restored=family_backup.restore(archive,app.ROOT/'restored')
    app.ROOT=restored;app.DATA=restored/'private';app.DB=app.DATA/'family.sqlite3'
    assert app.snapshot()['tasks']==expected
print('PASS: records, tasks, manual notification validation/auth, readable record revisions with original names and attachment gaps, read-only history and backup restore')

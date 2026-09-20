"""Run python3 test_task_feedback.py. Temporary synthetic files/SQLite; no household services or models."""
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch


def dump(app):
    with app.connect() as connection: return '\n'.join(connection.iterdump())

def refused(app, body, code, status=None):
    before=dump(app)
    try: app.save_task_feedback(body)
    except (app.RecordError,app.TaskError) as error:
        assert error.code==code and (status is None or error.status==status),(error.code,error.status,str(error))
    else: raise AssertionError('expected '+code)
    assert dump(app)==before,'a refused submission must leave saved data unchanged'


with tempfile.TemporaryDirectory(prefix='synthetic-task-feedback-') as folder:
    root=Path(folder); data=root/'private'; data.mkdir()
    with patch.dict(os.environ, {'FAMILY_DATA':str(data)}):
        import app
    with patch.multiple(app, ROOT=root, DATA=data, DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 女 | 8岁 | 二年级 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 虚构听写 | 本周 | 待跟进 | 虚构学校通知 | 虚构要求 |\n'
                                   '| T02 | 示例乙 | 虚构写作 | 本周 | 待跟进 | 虚构学校通知 | 虚构要求 |\n')
        def upload(name,content):
            return app.save_upload(io.BytesIO(content),len(content),name)['id']
        audio=upload('synthetic-voice.txt',b'synthetic original one');photo=upload('synthetic-photo.txt',b'synthetic original two')
        other=upload('synthetic-other.txt',b'synthetic other child original')
        key='synthetic-feedback-0001'
        body=dict(task_id='T01',child='示例甲',day='2026-09-20',request_key=key,attachments=[audio])

        # Media only: no invented note/transcript, linked to the task, and the task is not completed.
        first=app.save_task_feedback(body)
        assert first['ok'] and not first['replayed'] and not first['completion_changed']
        assert first['record']['source']=='事项:T01' and first['feedback']['note']==first['feedback']['transcript']==''
        assert [a['id'] for a in first['feedback']['attachments']]==[audio] and first['feedback']['attachments'][0]['url']=='/upload/'+audio
        assert first['task']['update'] is None and first['task']['history']==[] and first['task']['feedback_ids']==[first['record_id']]
        saved=next(r for r in app.snapshot()['records'] if r['id']==first['record_id'])
        assert saved['category']=='学习进展' and saved['title']=='反馈：虚构听写' and saved['attachments']==[audio] and saved['transcript_state']==''

        # Retry returns the same record even if the task was retitled meanwhile; a changed body under the same key is refused.
        (root/'跟踪台账.md').write_text((root/'跟踪台账.md').read_text().replace('虚构听写','虚构听写（改）'))
        before=dump(app);again=app.save_task_feedback(dict(body))
        assert again['replayed'] and again['record_id']==first['record_id'] and dump(app)==before
        refused(app,body|dict(note='虚构不同内容'),'request_conflict',409)
        refused(app,body|dict(complete=True,expected_updated=''),'request_conflict',409)

        # Missing/wrong-child task, missing/other-child media, empty feedback and transcript rules.
        refused(app,body|dict(task_id='T99',request_key='synthetic-feedback-0002'),'task_missing',404)
        refused(app,body|dict(child='示例乙',request_key='synthetic-feedback-0003'),'record_task_mismatch',409)
        refused(app,body|dict(task_id='T02',request_key='synthetic-feedback-0004'),'record_task_mismatch',409)
        refused(app,dict(task_id='T01',child='示例甲',day='2026-09-20',request_key='synthetic-feedback-0005'),'feedback_empty',400)
        refused(app,body|dict(request_key='synthetic-feedback-0006',transcript='虚构转写'),'invalid_record')
        refused(app,dict(task_id='T01',child='示例甲',day='2026-09-20',request_key='synthetic-feedback-0007',transcript='虚构转写',transcript_state='待核对'),'invalid_record')
        refused(app,body|dict(request_key='synthetic-feedback-0008',complete='yes'),'invalid_record')
        before=dump(app)
        try: app.save_task_feedback(body|dict(request_key='synthetic-feedback-0009',attachments=['f'*32]))
        except ValueError as error: assert '附件不存在' in str(error) and dump(app)==before
        else: raise AssertionError('missing upload accepted')
        app.save_task_feedback(dict(task_id='T02',child='示例乙',day='2026-09-20',request_key='synthetic-feedback-0010',attachments=[other],category='家长观察'))
        refused(app,body|dict(request_key='synthetic-feedback-0011',attachments=[other]),'feedback_media_other_child',409)

        # Correction keeps the original and history; the same correction again is not a conflict; a stale one changes nothing.
        created=first['feedback']['created']
        fix=dict(task_id='T01',child='示例甲',record_id=first['record_id'],expected_created=created,
                 note='虚构：第三个字写错',transcript='虚构转写：这个词听不出',transcript_state='待核对')
        fixed=app.save_task_feedback(fix)
        assert not fixed['replayed'] and fixed['feedback']['created']!=created and fixed['feedback']['transcript_state']=='待核对'
        assert [a['id'] for a in fixed['feedback']['attachments']]==[audio] and fixed['feedback']['day']=='2026-09-20'
        before=dump(app);same=app.save_task_feedback(dict(fix))
        assert same['replayed'] and dump(app)==before
        refused(app,fix|dict(transcript='虚构旧页面改动',transcript_state='已核对'),'feedback_conflict',409)
        refused(app,fix|dict(expected_created=fixed['feedback']['created'],attachments=[photo]),'feedback_original_required',400)
        refused(app,fix|dict(task_id='T02',child='示例乙'),'feedback_task_mismatch',409)
        checked=app.save_task_feedback(fix|dict(expected_created=fixed['feedback']['created'],transcript='虚构转写：这个词听不出来',transcript_state='已核对',attachments=[audio,photo]))
        assert checked['feedback']['transcript_state']=='已核对' and [a['id'] for a in checked['feedback']['attachments']]==[audio,photo]
        with app.connect() as c:
            history=[json.loads(r['previous']) for r in c.execute('SELECT previous FROM revisions WHERE record_id=? ORDER BY id',(first['record_id'],))]
        assert [h['transcript'] for h in history]==['','虚构转写：这个词听不出'] and all(audio in h['attachments'] for h in history)
        visible=app.record_history(first['record_id'])
        assert visible['current']['transcript']=='虚构转写：这个词听不出来'
        assert visible['history'][0]['previous']['transcript']=='虚构转写：这个词听不出'
        assert visible['history'][0]['previous']['transcript_state']=='待核对'
        # The ordinary record dialog leaves a saved transcript alone.
        app.save_record(dict(id=first['record_id'],child='示例甲',day='2026-09-20',category='学习进展',title='反馈：虚构听写',note='虚构普通更正',source='事项:T01'))
        assert next(r for r in app.snapshot()['records'] if r['id']==first['record_id'])['transcript']=='虚构转写：这个词听不出来'

        # Explicit completion and feedback are saved together or not at all.
        done=body|dict(request_key='synthetic-feedback-0020',attachments=[photo],complete=True)
        refused(app,done,'task_conflict',409)
        app.save_task(dict(id='T01',status='进行中',note='虚构别处更新'))
        refused(app,done|dict(expected_updated=''),'task_conflict',409)
        with patch.object(app.family_study,'task_changed',side_effect=app.sqlite3.OperationalError('synthetic failure')):
            before=dump(app)
            try: app.save_task_feedback(done|dict(expected_updated=app.snapshot()['tasks'][0]['update']['updated']))
            except app.sqlite3.Error: pass
            else: raise AssertionError('failure not raised')
            assert dump(app)==before,'feedback must not remain when completion failed'
        current=next(t for t in app.snapshot()['tasks'] if t['id']=='T01')['update']['updated']
        completed=app.save_task_feedback(done|dict(expected_updated=current))
        assert completed['completion_changed'] and completed['task']['update']['status']=='已完成'
        assert completed['task']['update']['note']==app.TASK_CHECK_NOTE and completed['record_id'] in completed['task']['feedback_ids']

        # A task reopened elsewhere is not completed again by a retry; a completed task takes more feedback without reopening.
        stamp=completed['task']['update']['updated']
        app.save_task(dict(id='T01',status='待跟进',note='虚构别处撤销',expected_updated=stamp))
        retry=app.save_task_feedback(done|dict(expected_updated=current))
        assert retry['replayed'] and not retry['completion_changed'] and retry['task']['update']['status']=='待跟进'
        app.save_task(dict(id='T01',status='已完成',note='虚构完成依据'))
        before_task=next(t for t in app.snapshot()['tasks'] if t['id']=='T01')
        more=app.save_task_feedback(body|dict(request_key='synthetic-feedback-0021',attachments=[],note='虚构：完成后再补充'))
        after_task=next(t for t in app.snapshot()['tasks'] if t['id']=='T01')
        assert not more['completion_changed'] and after_task['update']==before_task['update'] and after_task['history']==before_task['history']
        noop=app.save_task_feedback(body|dict(request_key='synthetic-feedback-0022',attachments=[],note='虚构：已完成再确认',complete=True))
        assert not noop['completion_changed'] and noop['task']['update']==before_task['update']

        # Retrying an identical correction cannot reapply completion after a separate reopening.
        correction=dict(task_id='T01',child='示例甲',record_id=more['record_id'],
                        expected_created=more['feedback']['created'],note='虚构更正',complete=True)
        corrected=app.save_task_feedback(correction)
        app.save_task(dict(id='T01',status='待跟进',note='虚构更正后撤销完成'))
        before=dump(app); replay=app.save_task_feedback(correction)
        assert replay['replayed'] and not replay['completion_changed'] and dump(app)==before

        # Exercise the HTTP dispatch and CSRF boundary, using only a temporary loopback server.
        import http.client
        import threading
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            def post(token):
                client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    client.request('POST','/api/task/feedback',json.dumps(body),
                                   {'Content-Type':'application/json','X-Family-Token':token})
                    response=client.getresponse(); return response.status,json.loads(response.read())
                finally: client.close()
            assert post('invalid-token')[0]==403
            status,result=post(app.snapshot()['token'])
            assert status==200 and result['replayed'] and result['record_id']==first['record_id']
        finally: server.shutdown();server.server_close();worker.join()

        # Ordinary task and record paths keep working.
        app.save_task(dict(id='T02',status='已完成',note=app.TASK_CHECK_NOTE))
        try: app.save_record(dict(child='示例乙',day='2026-09-20',category='学习进展',title='虚构跨孩',source='事项:T01'))
        except app.RecordError as error: assert error.code=='record_task_mismatch'
        else: raise AssertionError('cross-child record accepted')

print('PASS: task-linked media-only feedback, retry, correction history, validation, atomic explicit completion, no reopen')

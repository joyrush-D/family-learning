"""Run python3 test_study.py. Synthetic, isolated time accounts; no family services."""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import family_study


def reject(call, code=None):
    try: call()
    except family_study.StudyError as error:
        if code: assert error.code == code, (error.code, code)
    else: raise AssertionError('Invalid change accepted')


with tempfile.TemporaryDirectory(prefix='synthetic-study-') as temporary:
    root=Path(temporary); data=root/'private'; data.mkdir()
    with patch.dict(os.environ, {'FAMILY_DATA':str(data)}):
        import app
    with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 虚构学校功课 | 2026-09-08 | 待跟进 | 虚构学校通知 | 虚构要求 |\n'
            '| T02 | 示例乙 | 虚构另一孩子功课 | 2026-09-08 | 待跟进 | 虚构来源 | 虚构要求 |\n'
            '| T03 | 示例甲 | 虚构归档事项 | 2026-09-08 | 已归档（仅留存） | 虚构来源 | 虚构要求 |\n')
        store=family_study.Store(app); now=[dt.datetime(2026,9,8,18,0,tzinfo=family_study.TZ)]
        store._now=lambda:now[0]
        counter=[0]
        def request(**fields):
            counter[0]+=1
            return dict(child_id='child-1',day='2026-09-08',request_key='synthetic-request-'+str(counter[0]),**fields)
        def item(ident): return next(r for r in store.snapshot('child-1','2026-09-08')['items'] if r['id']==ident)
        def action(ident, operation, **fields):
            return store.action(request(id=ident,version=item(ident)['version'],action=operation,**fields))
        empty=store.snapshot('child-1','2026-09-08')
        assert empty['items']==empty['week']==[] and empty['day']['version']==0
        assert empty['active_item'] is None
        assert empty['summary']['available_minutes'] is None and empty['summary']['remaining_available_minutes'] is None
        assert [t['id'] for t in empty['available_tasks']]==['T01']
        reject(lambda:store.snapshot('missing','2026-09-08'))
        reject(lambda:store.save_day(request(start_time='23:00',stop_time='01:00',bed_time='02:00')))
        reject(lambda:store.save_day(request(start_time='18:00',stop_time='21:30',bed_time='21:00')))
        setup=request(version=0,start_time='18:00',stop_time='21:00',bed_time='21:30')
        assert store.save_day(setup)['day']['version']==1
        assert store.save_day(setup)['day']['version']==1
        reject(lambda:store.save_day(setup|{'stop_time':'20:30'}),'study_request_conflict')
        event=dict(id='a'*32,version=0,child_ids=['child-1'],title='虚构晚餐',category='family',day='2026-09-08',
            start_time='18:30',end_time='19:00',location='',note='',status='confirmed',repeat='none',until='')
        calendar=app.calendar_store(); calendar.save(event)
        calendar.save(event|dict(id='b'*32,title='虚构重叠安排',start_time='18:45',end_time='19:15'))
        calendar.save(event|dict(id='c'*32,child_ids=['child-2'],start_time='18:00',end_time='21:00'))
        calendar.save(event|dict(id='d'*32,status='cancelled',start_time='18:00',end_time='21:00'))
        calendar.save(event|dict(id='e'*32,title='虚构钟点待补',end_time=''))
        snapshot=store.snapshot('child-1','2026-09-08')
        assert snapshot['summary']['available_minutes']==135 and snapshot['summary']['remaining_available_minutes']==135
        assert '未填完整钟点' in snapshot['summary']['source_gap']
        now[0]+=dt.timedelta(hours=1)
        assert store.snapshot('child-1','2026-09-08')['summary']['remaining_available_minutes']==105
        now[0]=dt.datetime(2026,9,8,21,15,tzinfo=family_study.TZ)
        assert store.snapshot('child-1','2026-09-08')['summary']['remaining_available_minutes']==0
        now[0]=dt.datetime(2026,9,8,18,0,tzinfo=family_study.TZ)
        reject(lambda:store.save_item(request(task_id='T02',planned_minutes=20)))
        reject(lambda:store.save_item(request(task_id='T03',planned_minutes=20)),'study_task_closed')
        for invalid in (True,-1,1441,float('inf'),'20'):
            reject(lambda value=invalid:store.save_item(request(title='虚构非法功课',planned_minutes=value)))
        create=request(task_id='T01',subject='数学',planned_minutes=20)
        first=store.save_item(create)['items'][0]; ident=first['id']
        assert first['actual_minutes'] is None and first['time_source']=='' and first['version']==1
        assert first['source_task_action']=='虚构要求' and first['source_task_due']=='2026-09-08'
        assert first['source_task_next_action']==''
        # Requirements are read from the current source, without rewriting the timer or calendar.
        source_file=root/'跟踪台账.md'; source_text=source_file.read_text()
        before_calendar=calendar.snapshot('2026-09-08','2026-09-08')
        with app.connect() as c: before='\n'.join(c.iterdump())
        source_file.write_text(source_text.replace('虚构学校功课 | 2026-09-08','虚构学校功课 | 2026-09-10').replace('虚构要求 |','虚构最新要求：先读题，再写答案 |',1))
        current_tasks=app.tasks
        with patch.object(app,'tasks',lambda c: [t|{'focus':{'next_action':'虚构下一步：圈出已知条件'}} if t['id']=='T01' else t for t in current_tasks(c)]):
            latest=item(ident)
        assert latest['source_task_action']=='虚构最新要求：先读题，再写答案' and latest['source_task_due']=='2026-09-10'
        assert latest['source_task_next_action']=='虚构下一步：圈出已知条件'
        assert latest['elapsed_seconds']==first['elapsed_seconds'] and latest['version']==first['version']
        source_file.write_text(source_text.replace('| T01 | 示例甲 |','| T01 | 示例乙 |'))
        missing=item(ident)
        assert missing['source_task_status']=='待核对'
        assert all(missing[key] is None for key in ('source_task_action','source_task_due','source_task_next_action'))
        source_file.write_text(source_text.replace(source_text.splitlines()[0]+'\n',''))
        assert item(ident)['source_task_action'] is None
        source_file.write_text(source_text)
        assert calendar.snapshot('2026-09-08','2026-09-08')==before_calendar
        with app.connect() as c: assert '\n'.join(c.iterdump())==before
        assert store.save_item(create)['items'][0]['id']==ident
        reject(lambda:store.save_item(request(task_id='T01',planned_minutes=20)),'study_task_duplicate')
        added=store.save_item(request(title='虚构阅读功课',subject='语文',planned_minutes=None))
        other=next(r for r in added['items'] if r['id']!=ident)['id']
        with app.connect() as c:
            assert c.execute('SELECT count(*) FROM manual_tasks').fetchone()[0]==1
        start=request(id=ident,version=1,action='start')
        assert store.action(start)['items'][0]['status']=='running'
        now[0]+=dt.timedelta(minutes=5)
        assert store.action(start)['items'][0]['version']==2
        assert item(ident)['actual_minutes']==5
        reject(lambda:action(other,'start'),'study_already_running')
        reject(lambda:store.save_item(create),'study_conflict')
        # New Store / database reopen retains server time; reads never append time or history.
        restarted=family_study.Store(app); restarted._now=lambda:now[0]
        assert restarted.snapshot('child-1','2026-09-08')['items'][0]['actual_minutes']==5
        with app.connect() as c: before='\n'.join(c.iterdump())
        restarted.snapshot('child-1','2026-09-08')
        with app.connect() as c: assert '\n'.join(c.iterdump())==before
        action(ident,'pause'); now[0]+=dt.timedelta(minutes=15)
        assert item(ident)['actual_minutes']==5
        reject(lambda:store.action(start),'study_conflict')
        action(ident,'start'); now[0]+=dt.timedelta(minutes=7)
        finishing=request(id=ident,version=item(ident)['version'],action='finish',result='做了一部分',assistance='少量提示',note='虚构：最后一题需要再看')
        finished=store.action(finishing); record_id=item(ident)['record_id']
        assert item(ident)['actual_minutes']==12 and finished['summary']['unfinished_count']==2
        assert store.action(finishing)['items'][0]['record_id']==record_id
        with app.connect() as c:
            assert c.execute('SELECT count(*) FROM records').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM task_updates WHERE id=?',('T01',)).fetchone()[0]==0
        action(ident,'start'); now[0]+=dt.timedelta(minutes=8)
        action(ident,'finish',result='完成',note='虚构：家庭确认写完')
        assert item(ident)['actual_minutes']==20 and item(ident)['record_id']==record_id
        with app.connect() as c:
            assert c.execute('SELECT count(*) FROM records').fetchone()[0]==1
            assert c.execute('SELECT count(*) FROM revisions').fetchone()[0]==1
            assert c.execute('SELECT status FROM task_updates WHERE id=?',('T01',)).fetchone()[0]=='已完成'
        action(ident,'finish',result='需要帮助',note='虚构：更正，仍有一题')
        with app.connect() as c: assert c.execute('SELECT status FROM task_updates WHERE id=?',('T01',)).fetchone()[0]=='进行中'
        assert store.snapshot('child-1','2026-09-08')['summary']['needs_reestimate_count']==1
        assert store.snapshot('child-1','2026-09-08')['summary']['unknown_remaining_count']==2
        # Pure time corrections do not override a later independent task decision.
        with app.connect() as c: original_record=dict(c.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone())
        app.save_task(dict(id='T01',status='不适用',note='虚构外部任务更正'))
        with app.connect() as c: assert dict(c.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone())==original_record
        assert item(ident)['source_task_status']=='不适用'
        assert store.snapshot('child-1','2026-09-08')['summary']['unfinished_count']==1
        assert store.snapshot('child-1','2026-09-08')['summary']['planned_minutes']==0
        reject(lambda:action(ident,'start'),'study_task_dismissed')
        reject(lambda:action(ident,'finish',result='完成'),'study_task_dismissed')
        action(ident,'manual',actual_minutes=0)
        with app.connect() as c: assert c.execute('SELECT status FROM task_updates WHERE id=?',('T01',)).fetchone()[0]=='不适用'
        assert item(ident)['actual_minutes']==0 and item(ident)['time_source']=='manual'
        app.save_task(dict(id='T01',status='待跟进',note='虚构明确恢复原待办'))
        action(ident,'start'); now[0]+=dt.timedelta(minutes=1); action(ident,'pause')
        assert item(ident)['actual_minutes']==1 and item(ident)['time_source']=='mixed'
        # Only owned record fields are guarded; separate parent edits are never silently replaced.
        with app.connect() as c:
            c.execute('UPDATE records SET note=? WHERE id=?',('虚构家长在学习页单独更正',record_id))
            before='\n'.join(c.iterdump())
        reject(lambda:action(ident,'manual',actual_minutes=2),'study_record_changed')
        with app.connect() as c: assert '\n'.join(c.iterdump())==before
        # Long/cross-day spans remain visible but unverified until explicit manual reconciliation.
        action(other,'start'); now[0]+=dt.timedelta(hours=5)
        assert item(other)['elapsed_seconds']==18000 and item(other)['actual_minutes'] is None and item(other)['time_needs_review']
        action(other,'pause')
        assert item(other)['elapsed_seconds']==18000
        action(other,'manual',actual_minutes=25)
        action(other,'start'); now[0]=dt.datetime(2026,9,9,0,10,tzinfo=family_study.TZ)
        assert item(other)['actual_minutes'] is None and item(other)['time_needs_review']
        overnight=store.snapshot('child-1','2026-09-09')
        assert overnight['items']==[] and overnight['active_item']['id']==other
        assert overnight['active_item']['day']=='2026-09-08' and overnight['active_item']['time_needs_review']
        assert store.snapshot('child-2','2026-09-09')['active_item'] is None
        action(other,'pause'); action(other,'manual',actual_minutes=40)
        assert item(other)['actual_minutes']==40
        reject(lambda:action(other,'start'))
        # The other child may run concurrently; same-child competing starts have one winner.
        now[0]=dt.datetime(2026,9,8,20,0,tzinfo=family_study.TZ)
        third=store.save_item(request(title='虚构第三项',planned_minutes=15))['items'][-1]['id']
        starts=[request(id=i,version=item(i)['version'],action='start') for i in (other,third)]
        def compete(payload):
            try: store.action(payload); return 'started'
            except family_study.StudyError as error: return error.code
        with ThreadPoolExecutor(max_workers=2) as executor: outcomes=list(executor.map(compete,starts))
        assert sorted(outcomes)==['started','study_already_running']
        with app.connect() as c: assert c.execute('SELECT count(*) FROM study_items WHERE running_since IS NOT NULL').fetchone()[0]==1
        active=next(r for r in store.snapshot('child-1','2026-09-08')['items'] if r['running_since'])
        reject(lambda:store.action(request(action='close_day',version=1)))
        action(active['id'],'pause')
        close=request(action='close_day',version=1)
        closed=store.action(close)
        assert closed['day']['closed_at']==now[0].isoformat() and closed['day']['bed_time']=='21:30'
        assert store.action(close)['day']['version']==2
        action(third,'start')
        assert store.snapshot('child-1','2026-09-08')['day']['closed_at']==''
        reject(lambda:store.action(close),'study_conflict')
        action(third,'pause')
        # Week reports only actual recorded dates, and unknown minutes are not counted as zero.
        week=store.snapshot('child-1','2026-09-08')['week']
        assert len(week)==1 and week[0]['day']=='2026-09-08'
        assert store.snapshot('child-2','2026-09-08')['week']==[]
        (data/'日历来源.json').write_text('{invalid')
        broken=store.snapshot('child-1','2026-09-08')
        assert broken['summary']['source_gap'] and len(broken['items'])==3
        assert store.snapshot('child-1','0001-01-01')['week']==[]
        # The record prefix must fit the existing record form while retaining the full task title.
        long_title='虚构功课'*50
        long_item=store.save_item(request(title=long_title,subject='数学',planned_minutes=10))['items'][-1]
        action(long_item['id'],'finish',result='完成',actual_minutes=8)
        assert item(long_item['id'])['title']==long_title
        with app.connect() as c:
            record=dict(c.execute('SELECT * FROM records WHERE id=?',(item(long_item['id'])['record_id'],)).fetchone())
        assert len(record['title'])==200 and record['title'].endswith('…')
        content=b'Synthetic homework original.'
        upload=app.save_upload(io.BytesIO(content),len(content),'synthetic-long-title.txt')
        payload={key:record[key] for key in ('child','day','category','subject','title','note','source','assistance')}
        saved=app.save_record(dict(payload,id=record['id'],attachments=[upload['id']]))
        assert saved['record_id']==record['id']
        action(long_item['id'],'manual',actual_minutes=9)
        with app.connect() as c:
            assert c.execute('SELECT attachments FROM records WHERE id=?',(record['id'],)).fetchone()[0]=='["'+upload['id']+'"]'

        # Dismissing pauses the timer atomically, retains work, and invalidates stale actions.
        pending=store.save_item(request(title='虚构可选择的活动功课',planned_minutes=15))['items'][-1]
        action(pending['id'],'start'); now[0]+=dt.timedelta(minutes=3)
        stale=request(id=pending['id'],version=item(pending['id'])['version'],action='finish',result='完成')
        before_rewards=app.snapshot()['rewards']
        with app.connect() as c: before_records=c.execute('SELECT count(*) FROM records').fetchone()[0]
        class Clock(dt.datetime):
            @classmethod
            def now(cls,tz=None): return now[0].astimezone(tz)
        dismissal=dict(id=pending['task_id'],status='不参加',note='虚构家长决定不参加',expected_updated='')
        with patch.object(app.dt,'datetime',Clock): app.save_task(dismissal)
        paused=item(pending['id'])
        assert paused['status']=='paused' and paused['running_since'] is None and paused['actual_minutes']==3
        assert paused['source_task_status']=='不参加' and paused['version']==stale['version']+1
        assert app.snapshot()['rewards']==before_rewards
        with app.connect() as c: assert c.execute('SELECT count(*) FROM records').fetchone()[0]==before_records
        reject(lambda:store.action(stale),'study_conflict')
        reject(lambda:action(pending['id'],'start'),'study_task_dismissed')
        reject(lambda:action(pending['id'],'finish',result='完成'),'study_task_dismissed')
        with app.connect() as c: before='\n'.join(c.iterdump())
        app.save_task(dismissal)
        with app.connect() as c: assert '\n'.join(c.iterdump())==before
        app.save_task(dict(id=pending['task_id'],status='待跟进',note='虚构家长明确恢复'))
        reject(lambda:store.action(stale),'study_conflict')
        action(pending['id'],'start'); now[0]+=dt.timedelta(minutes=2); action(pending['id'],'pause')
        assert item(pending['id'])['actual_minutes']==5

        # A shared school event retains the other child's time; completed tasks still occupy its slot.
        (data/'日历来源.json').write_text(json.dumps(dict(events=[dict(
            id='synthetic-shared-event',child_ids=['child-1','child-2'],title='虚构共享学校活动',
            category='school',day='2026-09-08',start_time='19:30',end_time='20:00',status='confirmed',
            source='虚构学校来源',task_id=pending['task_id'])]),ensure_ascii=False))
        calendar.save(event|dict(id='c'*32,version=1,status='cancelled'))
        store.save_day(request(version=0,start_time='18:00',stop_time='21:00',bed_time='21:30')|{'child_id':'child-2'})
        assert store.snapshot('child-1','2026-09-08')['summary']['available_minutes']==105
        assert store.snapshot('child-2','2026-09-08')['summary']['available_minutes']==150
        app.save_task(dict(id=pending['task_id'],status='不参加',note='虚构本次不参加'))
        assert store.snapshot('child-1','2026-09-08')['summary']['available_minutes']==135
        assert store.snapshot('child-2','2026-09-08')['summary']['available_minutes']==150
        assert calendar.snapshot('2026-09-08','2026-09-08')['events'][-1]['status']=='confirmed'
        app.save_task(dict(id=pending['task_id'],status='已完成',note='虚构核对完成，仅测试客观学校时段'))
        assert store.snapshot('child-1','2026-09-08')['summary']['available_minutes']==105

print('PASS: isolated homework plan, calendar budgets, durable timers, dismiss/pause/restore, stale actions, shared events and preserved result records')

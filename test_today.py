"""Run python3 test_today.py. Temporary synthetic files/SQLite; no household services."""
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch


class FixedDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 8, 12, tzinfo=tz)


with tempfile.TemporaryDirectory(prefix='synthetic-today-') as folder:
    root=Path(folder); data=root/'private'
    with patch.dict(os.environ, {'FAMILY_DATA':str(data)}):
        import app
    with patch.multiple(app, ROOT=root, DATA=data, DB=data/'family.sqlite3'), patch.object(app.dt, 'datetime', FixedDatetime):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        (root/'跟踪台账.md').write_text('| T01 | 示例甲 | 虚构待办 | 下周再核对 | 待跟进 | 虚构学校通知 | 虚构要求 |\n')
        app.save_record(dict(child='示例甲', day='2026-09-07', category='学习进展', title='虚构原记录'))
        app.save_task(dict(id='T01', status='已完成', note='虚构确认依据'))
        store=app.calendar_store()
        event=dict(id='a'*32, version=0, child_ids=['child-1'], title='虚构当日安排', category='activity',
                   day='2026-09-08', start_time='17:00', end_time='', location='', note='',
                   status='confirmed', repeat='none', until='')
        store.save(event)
        store.save(event | dict(id='b'*32, title='虚构重复安排', day='2026-09-01', repeat='weekly'))
        store.save(event | dict(id='c'*32, title='虚构明日安排', day='2026-09-09'))
        store.save(event | dict(id='d'*32, title='虚构已结束重复', day='2026-09-01', repeat='weekly', until='2026-09-07'))
        source=data/'日历来源.json'
        source.write_text(json.dumps(dict(events=[dict(id='synthetic-school', child_ids=['child-1'],
            title='虚构学校安排', category='school', day='2026-09-08', status='confirmed',
            source='虚构出处', task_id='T01')], timetables=[dict(id='synthetic-table', child_id='child-1',
            effective_from='2026-09-01', title='虚构课表', source='虚构原件', week=[
                dict(weekday=2, sessions=[dict(slot='第一节', title='虚构数学')]),
                dict(weekday=3, sessions=[dict(slot='第二节', title='虚构语文')])])]), ensure_ascii=False))
        state=app.snapshot(); agenda=state['today_calendar']
        assert state['today']=='2026-09-08' and agenda['source_error']==''
        assert {e['id'] for e in agenda['events']}=={'a'*32, 'b'*32, 'source:synthetic-school'}
        assert all(e['day']==state['today'] for e in agenda['events'])
        repeated=next(e for e in agenda['events'] if e['id']=='b'*32)
        assert repeated['series_day']=='2026-09-01' and repeated['repeat']=='weekly'
        assert len(agenda['timetables'])==1 and agenda['timetables'][0]['day']==state['today']
        assert agenda['timetables'][0]['sessions']==[dict(slot='第一节', title='虚构数学')]
        assert state['tasks'][0]['due']=='下周再核对' and state['tasks'][0]['update']['status']=='已完成'
        with app.connect() as connection: before='\n'.join(connection.iterdump())
        assert app.snapshot()==state
        with app.connect() as connection: assert '\n'.join(connection.iterdump())==before

        source.write_text('{invalid')
        broken=app.snapshot()
        assert broken['today_calendar']['source_error'] and not broken['today_calendar']['timetables']
        assert {e['id'] for e in broken['today_calendar']['events']}=={'a'*32, 'b'*32}
        assert broken['tasks']==state['tasks'] and broken['records']==state['records']
        for error in [app.family_calendar.CalendarError('synthetic private detail'), OSError('synthetic private detail'),
                      sqlite3.DatabaseError('synthetic private detail'), json.JSONDecodeError('synthetic private detail', '', 0),
                      UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'synthetic private detail'),
                      TypeError('synthetic private detail'), RecursionError('synthetic private detail')]:
            with patch.object(app, 'calendar_store', side_effect=error):
                failed=app.snapshot()
            assert failed['today_calendar']['events']==failed['today_calendar']['timetables']==[]
            assert '不能据此判断今天没有安排' in failed['today_calendar']['source_error']
            assert 'synthetic private detail' not in failed['today_calendar']['source_error']
            assert failed['tasks']==state['tasks'] and failed['records']==state['records']

        app.save_record(dict(child='示例甲', day='2026-09-08', category='学习进展', title='虚构刚保存记录'))
        app.save_task(dict(id='T01', status='待跟进', note='虚构再次核对'))
        store.save(event | dict(version=1, title='虚构刚调整安排'))
        refreshed=app.snapshot()
        assert refreshed['records'][0]['title']=='虚构刚保存记录'
        assert refreshed['tasks'][0]['update']['status']=='待跟进'
        assert next(e for e in refreshed['today_calendar']['events'] if e['id']=='a'*32)['title']=='虚构刚调整安排'

print('PASS: today-only calendar, weekly expansion, timetable, read-only state, isolated errors and immediate saved data')

"""Run python3 test_oral_teacher_dates.py. Synthetic, isolated; explicit teacher complete/handback days on manual capture."""
import datetime as dt
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
        return error
    raise AssertionError('Invalid change accepted')


with tempfile.TemporaryDirectory(prefix='synthetic-oral-dates-') as temporary:
    root=Path(temporary); data=root/'private'; data.mkdir()
    with patch.dict(os.environ, {'FAMILY_DATA':str(data)}):
        import app
        import family_agenda
    with patch.multiple(app,ROOT=root,DATA=data,DB=data/'family.sqlite3'):
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        (root/'跟踪台账.md').write_text('')
        store=family_study.Store(app); store._now=lambda:dt.datetime(2026,9,8,18,0,tzinfo=family_study.TZ)
        counter=[0]
        def request(day='2026-09-08', child='child-1', **fields):
            counter[0]+=1
            return dict(child_id=child,day=day,request_key='synthetic-oral-'+str(counter[0]).rjust(4,'0'),**fields)
        def rows(): return {r[0]:r for r in sqlite3.connect(data/'family.sqlite3').execute('SELECT id,report,version FROM study_items')}
        def agenda(ident, start='2026-09-08', end='2026-09-20'):
            items=[x for x in family_agenda.snapshot(app,start,end)['inbox'] if x['id']==ident]
            assert len(items)==1, items
            return items[0]

        # OD-A1: both explicit teacher days persist apart from the recording (study) day; future days are allowed.
        words='语文：小练3，周四前做完，下周一交给老师'
        create=request(title='语文小练3',subject='语文',planned_minutes=20,
            report=dict(text=words,explanation='',excerpt='',goal='小练习册第3页全部完成',attachments=[],complete_on='2026-09-10',handback_on='2026-09-14'))
        saved=store.save_item(create); ident=saved['saved_item_id']
        report=next(i for i in saved['items'] if i['id']==ident)['report']
        assert (report['complete_on'],report['handback_on'],report['text'],report['goal'])==('2026-09-10','2026-09-14',words,'小练习册第3页全部完成')
        m=agenda(ident)['agenda']
        assert (m['complete_on'],m['due_on'],m['due_kind'],m['scheduled_on'])==('2026-09-10','2026-09-14','handback','2026-09-08'), m
        # Only one known day never invents the other.
        only=store.save_item(request(title='数学口算',report=dict(text='口算本第8页，周五交',goal='',attachments=[],complete_on='',handback_on='2026-09-11')))['saved_item_id']
        m=agenda(only)['agenda']
        assert (m['complete_on'],m['due_on'],m['due_kind'],m['scheduled_on'])==('','2026-09-11','handback','2026-09-08'), m

        # OD-A2: blank stays unknown although the words contain a day; old clients without the keys stay unknown.
        blank=store.save_item(request(title='英语抄写',report=dict(text='英语抄写，9月12日交',goal='',attachments=[],complete_on='',handback_on='')))['saved_item_id']
        legacy=store.save_item(request(title='科学预习',report=dict(text='科学预习',goal='',attachments=[])))['saved_item_id']
        for ident_unknown in (blank,legacy):
            m=agenda(ident_unknown)['agenda']
            assert (m['complete_on'],m['due_on'],m['scheduled_on'])==('','','2026-09-08'), m
        assert 'handback_on' not in rows()[legacy][1]
        # Impossible or malformed days reject with zero writes.
        before=rows()
        for bad in ('2026-02-30','2026/09/10','明天',20260910,None):
            reject(lambda:store.save_item(request(title='坏日期',report=dict(text='x',goal='',attachments=[],complete_on='',handback_on=bad))))
        reject(lambda:store.save_item(request(title='坏键',report=dict(text='x',goal='',attachments=[],due_on='2026-09-10'))))
        assert rows()==before

        # OD-A3: lost-receipt replay of the same create keeps one task; parent plan and a later correction survive replay.
        assert store.save_item(create)['saved_item_id']==ident and rows()==before
        import family_task_focus
        # A parent's explicit plan keeps scheduling priority and never becomes, or erases, a teacher day.
        family_task_focus.save(app,dict(id=ident,version=0,request_key='synthetic-oral-plan-0001',mode='next',next_action='',
            waiting_for='',review_on='',category='homework',scheduled_on='2026-09-09'))
        m=agenda(ident)['agenda']
        assert (m['complete_on'],m['due_on'],m['due_kind'],m['scheduled_on'])==('2026-09-10','2026-09-14','handback','2026-09-09'), m
        assert rows()[ident]==before[ident]
        version=rows()[ident][2]
        correct=request(id=ident,version=version,teacher_dates=dict(handback_on='2026-09-15'))
        store.save_item(correct)
        report=__import__('json').loads(rows()[ident][1])
        assert (report['complete_on'],report['handback_on'],report['text'])==('2026-09-10','2026-09-15',words)
        assert report['date_history'][-1]['handback_on']=='2026-09-14' and report['date_history'][-1]['complete_on']=='2026-09-10'
        after=rows()
        assert store.save_item(create)['saved_item_id']==ident and store.save_item(correct) and rows()==after
        # A stale correction rejects without writes.
        reject(lambda:store.save_item(request(id=ident,version=version,teacher_dates=dict(complete_on=''))),'study_conflict')
        reject(lambda:store.save_item(request(id=ident,version=version+1,teacher_dates=dict(complete_on='2026-13-01'))))
        assert rows()==after
        # Explicit clear keeps history; cleared teacher day reads unknown again.
        store.save_item(request(id=ident,version=version+1,teacher_dates=dict(complete_on='')))
        m=agenda(ident)['agenda']
        assert (m['complete_on'],m['due_on'],m['due_kind'],m['scheduled_on'])==('','2026-09-15','handback','2026-09-09'), m
        assert [h['complete_on'] for h in __import__('json').loads(rows()[ident][1])['date_history']]==['2026-09-10','2026-09-10']
        # Cross-child ownership stays rejected.
        reject(lambda:store.save_item(dict(request(id=ident,version=version+2,teacher_dates=dict(handback_on='2026-09-16')),child_id='child-2')))
        # A child cannot use the parent's teacher-day correction.
        child=family_study.Store(app,authorize=lambda c,i:None); child._now=store._now
        reject(lambda:child.save_item(request(id=ident,version=version+2,teacher_dates=dict(handback_on='2026-09-16'))))

        # OD-A4: future, due and overdue views keep the same task and teacher days.
        for day in ('2026-09-08','2026-09-11','2026-09-15','2026-09-18'):
            assert family_agenda.visible_on(agenda(ident),day), day
        assert not family_agenda.visible_on(agenda(blank),'2026-09-12')
print('test_oral_teacher_dates: ok')

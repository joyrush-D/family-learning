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

        # OD-A4: capture, future, due and overdue days list the same one task with its teacher days; blank is no deadline.
        listed=family_agenda.snapshot(app,'2026-09-08','2026-09-20')['agenda']
        def days(task): return [x['day'] for x in listed if x['id']==task]
        assert days(only)==['2026-09-%02d'%d for d in range(8,21)], days(only)
        assert days(ident)==['2026-09-%02d'%d for d in range(9,21)], days(ident)
        assert all((x['agenda']['due_on'],x['agenda']['due_kind'])==('2026-09-15','handback') for x in listed if x['id']==ident)
        assert days(blank)==days(legacy)==['2026-09-08'], (days(blank),days(legacy))
        assert family_agenda.visible_on(dict(agenda(only),agenda=dict(agenda(only)['agenda'],complete_on='2026-09-30')),'2026-09-30')

        # Root OD-QA-1: only a teacher complete day, handback unknown. The open task stays listed after that day until a
        # parent closes it; no handback/deadline is invented from the complete day.
        complete_only=store.save_item(request(title='语文抄写',report=dict(text='示例原话：10日前完成，交回时间未知',goal='抄写短句',attachments=[],complete_on='2026-09-10',handback_on='')))['saved_item_id']
        listed=family_agenda.snapshot(app,'2026-09-08','2026-09-20')['agenda']
        assert days(complete_only)==['2026-09-%02d'%d for d in range(8,21)], days(complete_only)
        assert all((x['agenda']['complete_on'],x['agenda']['due_on'],x['agenda']['due_kind'])==('2026-09-10','','') for x in listed if x['id']==complete_only)
        closed=dict(agenda(complete_only),closed=True,closed_on='2026-09-12')
        assert family_agenda.visible_on(closed,'2026-09-10') and family_agenda.visible_on(closed,'2026-09-12')
        assert not any(family_agenda.visible_on(closed,'2026-09-%02d'%d) for d in (11,13,14,20))
        # A blank teacher day still carries nothing forward.
        assert days(blank)==['2026-09-08']

        # Root OD-QA-2: the generic task form round-trips the displayed teacher handback day as due_on; that copy is not a
        # second parent deadline, so a later clear/correction of the teacher day reads the same in Today and the calendar.
        import json
        def task(ident):
            with app.connect() as c: return next(t for t in app.tasks(c) if t['id']==ident)
        def focus_payload(ident, key, **changes):
            t=task(ident); f=t['focus']
            return dict(dict(id=ident,version=f['version'],request_key='synthetic-oral-focus-'+key,mode=f['mode'],next_action='先核对原要求',
                waiting_for=f['waiting_for'],review_on=f['review_on'],category=t['agenda']['category'],published_on=t['agenda']['published_on'],
                due_on=t['agenda']['due_on'],scheduled_on=t['agenda']['scheduled_on'],box=f['box'],title=t['title'],goal=t['action']),**changes)
        def same_views(ident, start='2026-09-08', end='2026-09-20'):
            today=task(ident)['agenda']; calendar=agenda(ident,start,end)['agenda']
            assert {k:today[k] for k in ('due_on','due_kind','complete_on','scheduled_on')}=={k:calendar[k] for k in ('due_on','due_kind','complete_on','scheduled_on')}, (today,calendar)
            return today
        copied=store.save_item(request(title='数学口算第2页',report=dict(text='示例原话：16日交回',goal='口算第2页',attachments=[],complete_on='',handback_on='2026-09-16')))['saved_item_id']
        payload=focus_payload(copied,'0001')
        assert payload['due_on']=='2026-09-16'
        family_task_focus.save(app,payload)
        m=same_views(copied)
        assert (m['due_on'],m['due_kind'],m['scheduled_on'])==('2026-09-16','handback','2026-09-08'), m
        assert task(copied)['focus']['due_on']=='', task(copied)['focus']
        # Same request replays as a no-op; a stale form version rejects without writes.
        frozen=task(copied)['focus']
        assert family_task_focus.save(app,payload)['request_replayed'] and task(copied)['focus']==frozen
        try: family_task_focus.save(app,dict(payload,request_key='synthetic-oral-focus-0002'))
        except family_task_focus.FocusError as error: assert (error.status,error.code)==(409,'task_focus_conflict')
        else: raise AssertionError('stale focus accepted')
        assert task(copied)['focus']==frozen
        # Clearing the teacher handback day leaves no deadline anywhere; words, history and plan stay.
        store.save_item(request(id=copied,version=rows()[copied][2],teacher_dates=dict(handback_on='')))
        m=same_views(copied)
        assert (m['due_on'],m['due_kind'],m['complete_on'],m['scheduled_on'])==('','','','2026-09-08'), m
        report=json.loads(rows()[copied][1])
        assert (report['handback_on'],report['text'],report['date_history'][-1]['handback_on'])==('','示例原话：16日交回','2026-09-16')
        listed=family_agenda.snapshot(app,'2026-09-08','2026-09-20')['agenda']
        assert days(copied)==['2026-09-08'], days(copied)
        # A later explicit teacher day after the round-trip shows as that teacher day only.
        store.save_item(request(id=copied,version=rows()[copied][2],teacher_dates=dict(handback_on='2026-09-17')))
        m=same_views(copied)
        assert (m['due_on'],m['due_kind'])==('2026-09-17','handback'), m
        # The parent's own different plan and own different date in the same generic form stay the parent's.
        planned=store.save_item(request(title='英语听写',report=dict(text='示例原话：16日交回',goal='',attachments=[],complete_on='',handback_on='2026-09-16')))['saved_item_id']
        family_task_focus.save(app,focus_payload(planned,'0003',scheduled_on='2026-09-09',due_on='2026-09-18'))
        assert (task(planned)['focus']['scheduled_on'],task(planned)['focus']['due_on'])==('2026-09-09','2026-09-18')
        m=same_views(planned)
        assert (m['due_on'],m['due_kind'],m['scheduled_on'])==('2026-09-16','handback','2026-09-09'), m
        store.save_item(request(id=planned,version=rows()[planned][2],teacher_dates=dict(handback_on='')))
        m=same_views(planned)
        assert (m['due_on'],m['scheduled_on'])==('2026-09-18','2026-09-09') and m['due_kind']!='handback', m
        # Root race (ROOT-RACE-FROZEN payloads): a task form opened while the teacher handback day was 22 must not save that
        # old day as the parent's deadline after another session corrected it to 23; clearing it then leaves no deadline.
        race_store=family_study.Store(app); race_store._now=lambda:dt.datetime(2026,10,17,18,0,tzinfo=family_study.TZ)
        def race_create(key):
            return dict(child_id='child-1',day='2026-10-17',title='虚构数学口算',request_key=key,
                report=dict(text='虚构原话：22日交回',goal='口算虚构第2页',attachments=[],complete_on='',handback_on='2026-10-22'))
        def standard(ident, key, due_on, scheduled_on, version=0):
            return dict(id=ident,version=version,request_key=key,mode='next',next_action='先核对原要求',waiting_for='',review_on='',category='homework',
                published_on='',due_on=due_on,scheduled_on=scheduled_on,box='inbox',title='虚构数学口算',goal='口算虚构第2页')
        def revise(ident, key, day):
            return race_store.save_item(dict(child_id='child-1',day='2026-10-17',id=ident,version=rows()[ident][2],request_key=key,teacher_dates=dict(handback_on=day)))
        raced=race_store.save_item(race_create('independent-oral-clear-handback-0002'))['saved_item_id']
        opened=standard(raced,'independent-oral-focus-0001','2026-10-22','2026-10-17')
        assert task(raced)['focus']['version']==0 and task(raced)['agenda']['due_on']=='2026-10-22'
        revise(raced,'independent-oral-race-revise-0001','2026-10-23')
        m=task(raced)['agenda']
        assert (m['due_on'],m['due_kind'],m['scheduled_on'])==('2026-10-23','handback','2026-10-17'), m
        try: family_task_focus.save(app,opened)
        except family_task_focus.FocusError as error: assert (error.status,error.code)==(409,'task_focus_conflict'), error.code
        else: raise AssertionError('stale task form saved the old teacher day')
        assert task(raced)['focus']['due_on']==''
        revise(raced,'independent-oral-race-clear-0002','')
        m=task(raced)['agenda']
        assert (m['due_on'],m['due_kind'],m['scheduled_on'])==('','','2026-10-17'), m
        report=json.loads(rows()[raced][1])
        assert (report['text'],report['goal'],[h['handback_on'] for h in report['date_history']])==('虚构原话：22日交回','口算虚构第2页',['2026-10-22','2026-10-23'])
        # The parent's genuinely different due 24 / plan 19 in the same stale form is saved after reading the latest version.
        genuine=race_store.save_item(race_create('independent-oral-true-parent-create'))['saved_item_id']
        stale=standard(genuine,'independent-oral-true-parent-0001','2026-10-24','2026-10-19')
        revise(genuine,'independent-oral-true-revise-0001','2026-10-23')
        try: family_task_focus.save(app,stale)
        except family_task_focus.FocusError as error: assert error.code=='task_focus_conflict', error.code
        else: raise AssertionError('stale task form accepted')
        family_task_focus.save(app,dict(stale,version=task(genuine)['focus']['version'],request_key='independent-oral-true-parent-0002'))
        revise(genuine,'independent-oral-true-clear-0002','')
        m=task(genuine)['agenda']
        assert (m['due_on'],m['scheduled_on'])==('2026-10-24','2026-10-19') and m['due_kind']!='handback', m
        # A choice saved before the correction stays; its lost-receipt retry still reads back the same success.
        early=race_store.save_item(race_create('independent-oral-early-create'))['saved_item_id']
        sent=standard(early,'independent-oral-early-focus-0001','2026-10-24','2026-10-19')
        family_task_focus.save(app,sent)
        revise(early,'independent-oral-early-revise-0001','2026-10-23')
        assert family_task_focus.save(app,sent)['request_replayed']
        revise(early,'independent-oral-early-clear-0002','')
        m=task(early)['agenda']
        assert (m['due_on'],m['scheduled_on'])==('2026-10-24','2026-10-19'), m
        # A finished item stays closed whether or not its teacher day can still be corrected; the task form cannot reopen it.
        done=race_store.save_item(dict(race_create('independent-oral-close-create'),report=dict(text='虚构原话：20日完成',goal='口算虚构第3页',attachments=[],complete_on='2026-10-20',handback_on='')))['saved_item_id']
        race_store.action(dict(child_id='child-1',day='2026-10-17',id=done,version=rows()[done][2],request_key='independent-oral-close-0001',action='finish',result='完成',assistance='',note='',actual_minutes=2))
        try: race_store.save_item(dict(child_id='child-1',day='2026-10-17',id=done,version=rows()[done][2],request_key='independent-oral-close-fix-0001',teacher_dates=dict(complete_on='2026-10-21')))
        except family_study.StudyError: pass
        try: family_task_focus.save(app,standard(done,'independent-oral-close-focus-0001','','2026-10-17',task(done)['focus']['version']))
        except family_task_focus.FocusError as error: assert error.code=='task_focus_closed', error.code
        else: raise AssertionError('closed item reopened by the task form')
print('test_oral_teacher_dates: ok')

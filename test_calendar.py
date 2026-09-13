"""Synthetic calendar regression: temporary SQLite/files and loopback HTTP only."""
from concurrent.futures import ThreadPoolExecutor
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import family_calendar


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-calendar-')
        self.old=app.ROOT,app.DATA,app.DB
        app.ROOT=Path(self.tmp.name); app.DATA=app.ROOT/'private'; app.DATA.mkdir(); app.DB=app.DATA/'family.sqlite3'
        (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.store=app.calendar_store()
        self.source=app.DATA/'日历来源.json'

    def test_timetable_import_is_confirmed_dated_owned_and_retryable(self):
        self.write_sources()
        obj=dict(id='b'*32,version=0,child_id='child-1',title='虚构核对课表',effective_from='2026-09-14',effective_until='2026-09-21',note='虚构来源',attachments=[],week=[dict(weekday=1,sessions=[dict(slot='第一节',title='数学')])])
        saved=self.store.save_timetable(obj,app.timetable_uploads)
        self.assertEqual(saved['version'],1)
        self.assertEqual(self.store.save_timetable(obj,app.timetable_uploads)['version'],1)
        self.assertEqual(len(self.store.saved_timetables()),1)
        before=self.store.snapshot('2026-09-08','2026-09-08')['timetables'];self.assertEqual(before[0]['sessions'][0]['title'],'虚构数学')
        after=self.store.snapshot('2026-09-14','2026-09-14')['timetables'];self.assertEqual(len(after),1);self.assertEqual(after[0]['sessions'][0]['title'],'数学')
        self.assertEqual(self.store.snapshot('2026-09-22','2026-09-22')['timetables'],[]) # No reappearance of expired legacy timetable.
        for wrong in [dict(obj,title='变更'),dict(obj,version=1,child_id='child-2'),dict(obj,id='c'*32,effective_from=''),dict(obj,id='c'*32,attachments=['d'*32]),dict(obj,id='c'*32,week=[dict(weekday=1,sessions=[dict(slot='第一节',title='语文'),dict(slot='第一节',title='英语')])])]:
            with self.assertRaises(ValueError): self.store.save_timetable(wrong,app.timetable_uploads)
        self.assertEqual(len(self.store.saved_timetables()),1)
        fresh=self.store.save_timetable(dict(obj,version=1,title='更正后的课表'),app.timetable_uploads)
        self.assertEqual(fresh['version'],2)

    def test_timetable_draft_does_not_save_or_invent_dates(self):
        import family_llm
        draft=dict(week=[dict(weekday=3,sessions=[dict(slot='下午第一节',title='英语')])],uncertainties=['适用学期待核对'])
        with patch.object(family_llm,'configuration',return_value=('https://example.invalid','synthetic')),patch.object(family_llm,'_chat_json',return_value=draft) as request:
            result=app.timetable_draft(dict(child_id='child-1',text='虚构课表：周三下午第一节英语',attachments=[]))
        self.assertEqual(result['draft'],draft);self.assertEqual(self.store.saved_timetables(),[])
        self.assertEqual(request.call_args.args[2],'family_timetable_draft')
        self.assertNotIn('effective_from',result['draft'])
        with patch.object(family_llm,'extract_draft') as model:
            with self.assertRaises(ValueError):app.timetable_draft(dict(child_id='missing',text='虚构',attachments=[]))
            model.assert_not_called()

    def tearDown(self):
        app.ROOT,app.DATA,app.DB=self.old; self.tmp.cleanup()

    def request(self,**extra):
        obj=dict(id='a'*32,version=0,child_ids=['child-1'],title='虚构周末观察',category='activity',
                 day='2026-09-12',start_time='09:00',end_time='10:00',location='虚构公园',note='虚构约定',
                 status='tentative',repeat='none',until='')
        obj.update(extra); return obj

    def dump(self):
        with app.connect() as c: return '\n'.join(c.iterdump())

    def sources(self):
        return dict(events=[dict(id='school-day',child_ids=['child-2'],title='虚构学校材料上交',category='school',
            day='2026-09-09',start_time='',end_time='',location='',note='钟点待核对',status='confirmed',source='虚构教师通知',task_id='T01')],
            timetables=[dict(id='synthetic-table',child_id='child-1',effective_from='2026-09-08',effective_until='',
                title='虚构课表',source='虚构班级原图',attachment='虚构课表.png',note='只列课次，未提供钟点或单双周',
                week=[dict(weekday=1,sessions=[dict(slot='第一节',title='虚构语文')]),
                      dict(weekday=2,sessions=[dict(slot='第二节',title='虚构数学')])])])

    def write_sources(self,obj=None):
        self.source.write_text(json.dumps(self.sources() if obj is None else obj,ensure_ascii=False))

    def test_round_trip_shared_children_and_status_do_not_touch_tasks(self):
        obj=self.request(child_ids=['child-2','child-1'],start_time='16:10',end_time='',category='school')
        row=self.store.save(obj)
        self.assertEqual(row['version'],1); self.assertEqual(row['child_ids'],['child-1','child-2'])
        self.assertTrue(row['editable']); self.assertEqual(row['source'],'')
        result=self.store.snapshot('2026-09-12','2026-09-12')
        self.assertEqual(set(result),{'events','timetables','source_error'})
        self.assertEqual(result['events'],[row]); self.assertEqual(result['source_error'],'')
        self.store.save(self.request(version=1,child_ids=obj['child_ids'],status='cancelled'))
        self.assertEqual(self.store.snapshot('2026-09-12','2026-09-12')['events'][0]['status'],'cancelled')
        with app.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM task_updates').fetchone()[0],0)

    def test_dates_times_and_payload_boundaries_leave_data_unchanged(self):
        before=self.dump()
        bad=[dict(day='2026-02-29'),dict(day='2026-9-12'),dict(day=None),dict(start_time='24:00'),
             dict(start_time='',end_time='10:00'),dict(start_time='10:00',end_time='10:00'),
             dict(start_time='23:00',end_time='01:00'),dict(start_time='9:00'),dict(child_ids=[]),
             dict(child_ids=['missing-child']),dict(child_ids=['child-1','child-1']),dict(child_ids=['child-1',{}]),
             dict(title=' '*4),dict(note='a'*4001),dict(category='automatic'),dict(status='invalid'),
             dict(repeat='unsupported'),dict(repeat='none',until='2026-10-01'),dict(repeat='weekly',until='2026-09-11'),
             dict(version=True),dict(id='source:school-day'),dict(source='pretend-school-source')]
        for extra in bad:
            with self.subTest(extra=extra),self.assertRaises(family_calendar.CalendarError): self.store.save(self.request(**extra))
        self.assertEqual(self.dump(),before)
        self.store.save(self.request(day='2028-02-29',start_time='',end_time=''))

    def test_single_plan_completion_and_repeat_guard(self):
        result=self.store.save(self.request(status='completed'))
        self.assertEqual(result['status'],'completed')
        with self.assertRaises(family_calendar.CalendarError):self.store.save(self.request(version=1,status='completed',repeat='weekly'))

    def test_query_window_is_inclusive_and_bounded(self):
        self.store.save(self.request(day='2026-09-30'))
        self.assertEqual(len(self.store.snapshot('2026-08-31','2026-09-30')['events']),1)
        for start,end in [('2026-08-30','2026-09-30'),('2026-09-30','2026-09-29'),('bad','2026-09-30'),('2026-09-01','2026-09-31')]:
            with self.subTest(start=start,end=end),self.assertRaises(family_calendar.CalendarError): self.store.snapshot(start,end)

    def test_weekly_series_boundary_and_whole_series_edit(self):
        obj=self.request(day='2026-08-29',repeat='weekly',until='2026-09-19')
        self.store.save(obj)
        events=self.store.snapshot('2026-09-01','2026-09-30')['events']
        self.assertEqual([r['day'] for r in events],['2026-09-05','2026-09-12','2026-09-19'])
        self.assertTrue(all(r['series_day']=='2026-08-29' and r['id']=='a'*32 for r in events))
        self.assertEqual(self.store.snapshot('2026-08-01','2026-08-28')['events'],[])
        self.store.save(dict(obj,version=1,day='2026-08-30',until=''))
        self.assertEqual([r['day'] for r in self.store.snapshot('2026-09-01','2026-09-30')['events']],
                         ['2026-09-06','2026-09-13','2026-09-20','2026-09-27'])
        self.store.save(self.request(id='b'*32,day='9999-12-31',repeat='weekly',until=''))
        self.assertIn('9999-12-31',[r['day'] for r in self.store.snapshot('9999-12-31','9999-12-31')['events']])

    def test_repeat_rules_extra_times_and_legacy_clients_preserve_one_series(self):
        cases=[('daily',[],['2026-09-14','2026-09-15','2026-09-16','2026-09-17','2026-09-18','2026-09-19','2026-09-20']),
               ('weekends',[],['2026-09-19','2026-09-20']),
               ('weekly',[1,3,5],['2026-09-14','2026-09-16','2026-09-18'])]
        for n,(mode,days,expected) in enumerate(cases):
            ident=str(n+1)*32
            obj=self.request(id=ident,day='2026-09-14',repeat=mode,until='2026-09-20',repeat_days=days)
            saved=self.store.save(obj);self.assertEqual(self.store.save(obj),saved)
            rows=[r for r in self.store.snapshot('2026-09-13','2026-09-21')['events'] if r['id']==ident]
            self.assertEqual([r['day'] for r in rows],expected)
        monthly=self.request(id='d'*32,day='2026-01-30',repeat='monthly',repeat_days=[31],until='2026-03-31',start_time='07:00',end_time='07:10',extra_times=[dict(id='e'*16,start_time='19:00',end_time='19:10')])
        first=self.store.save(monthly)
        self.assertEqual([r for r in self.store.snapshot('2026-02-01','2026-02-28')['events'] if r['id'].startswith('d')],[])
        rows=[r for r in self.store.snapshot('2026-03-01','2026-03-31')['events'] if r['id'].startswith('d')]
        self.assertEqual([(r['day'],r['start_time']) for r in rows],[('2026-03-31','07:00'),('2026-03-31','19:00')])
        self.assertEqual(rows[1]['series_id'],'d'*32);self.assertEqual(rows[1]['series_start_time'],'07:00')
        with self.assertRaises(family_calendar.CalendarError):self.store.save({k:v for k,v in dict(monthly,version=1).items() if k not in family_calendar.REPEAT_FIELDS})
        self.assertEqual(self.store.save(monthly),first)
        changed=dict(monthly,version=1,title='虚构改名')
        self.store.save(changed)
        self.assertEqual(self.store.snapshot('2026-03-31','2026-03-31')['events'][-1]['id'],rows[-1]['id'])
        before=self.dump()
        for extra in [dict(repeat_days=[True]),dict(repeat_days=[0]),dict(repeat_days=[31,31]),
                      dict(extra_times=[dict(id='e'*16,start_time='07:05',end_time='07:20')]),
                      dict(extra_times=[dict(id='e'*16,start_time='19:00',end_time='18:00')]),
                      dict(until='2026-01-30'),dict(status='completed')]:
            with self.assertRaises(family_calendar.CalendarError): self.store.save(dict(monthly,version=2,**extra))
        self.assertEqual(self.dump(),before)

    def test_legacy_series_retry_survives_new_columns(self):
        import hashlib
        obj=self.request(repeat='weekly');first=self.store.save(obj)
        legacy=hashlib.sha256(family_calendar._json(dict(id=obj['id'],version=0,**{k:v for k,v in self.store._fields(obj,{'child-1','child-2'}).items() if k not in family_calendar.REPEAT_FIELDS})).encode()).hexdigest()
        with app.connect() as c:
            c.execute('UPDATE calendar_events SET last_request_hash=? WHERE id=?',(legacy,obj['id']))
            # Recreate the pre-upgrade table, then run the real additive migration twice.
            columns=[r[1] for r in c.execute('PRAGMA table_info(calendar_events)') if r[1] not in (*family_calendar.REPEAT_FIELDS,'occurrence')]
            c.execute('CREATE TABLE calendar_legacy AS SELECT '+','.join(columns)+' FROM calendar_events')
            c.execute('DROP TABLE calendar_events');c.execute('ALTER TABLE calendar_legacy RENAME TO calendar_events')
        expanded=self.store.snapshot('2026-09-12','2026-09-12')['events'];self.assertEqual(expanded[0]['occurrence']['version'],0);self.assertEqual(expanded[0]['occurrence']['day'],'2026-09-12');self.assertEqual([dict(e,occurrence={}) for e in expanded],[first])
        with ThreadPoolExecutor(max_workers=2) as pool: migrated=list(pool.map(lambda _:app.calendar_store(),range(2)))
        self.store=migrated[0];app.calendar_store()
        self.assertEqual(self.store.save(obj),first)
        expanded=self.store.snapshot('2026-09-12','2026-09-12')['events'];self.assertEqual(expanded[0]['occurrence']['version'],0);self.assertEqual(expanded[0]['occurrence']['day'],'2026-09-12');self.assertEqual([dict(e,occurrence={}) for e in expanded],[first])

    def test_lost_response_retry_and_conflicting_version(self):
        obj=self.request(); first=self.store.save(obj); saved=self.dump()
        self.assertEqual(self.store.save(obj),first); self.assertEqual(self.dump(),saved)
        with self.assertRaises(family_calendar.CalendarError) as cm: self.store.save(dict(obj,title='不同请求'))
        self.assertEqual(cm.exception.status,409); self.assertEqual(self.dump(),saved)
        changed=dict(obj,version=1,title='虚构更正',status='confirmed'); second=self.store.save(changed)
        self.assertEqual(second['version'],2); saved=self.dump()
        self.assertEqual(self.store.save(changed),second); self.assertEqual(self.dump(),saved)
        with self.assertRaises(family_calendar.CalendarError): self.store.save(obj)
        self.assertEqual(self.dump(),saved)

    def test_concurrent_same_request_and_competing_updates(self):
        obj=self.request()
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(self.store.save,[obj,obj]))
        self.assertEqual(results[0],results[1])
        def edit(title):
            try:return self.store.save(dict(obj,version=1,title=title))['version']
            except family_calendar.CalendarError as e:return e.status
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(edit,['虚构调整甲','虚构调整乙']))
        self.assertEqual(sorted(results),[2,409])
        with app.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM calendar_events').fetchone()[0],1)

    def test_sources_read_only_timetable_effective_range_and_no_guessed_times(self):
        self.write_sources(); before=self.source.read_bytes(); database=self.dump()
        result=self.store.snapshot('2026-09-07','2026-09-15')
        self.assertEqual(self.source.read_bytes(),before); self.assertEqual(self.dump(),database)
        source=result['events'][0]
        self.assertEqual((source['id'],source['editable'],source['task_id']),('source:school-day',False,'T01'))
        self.assertEqual(source['child_ids'],['child-2']); self.assertEqual(source['start_time'],'')
        tables=result['timetables']; self.assertEqual([r['day'] for r in tables],['2026-09-08','2026-09-14','2026-09-15'])
        self.assertTrue(all(t['child_id']=='child-1' and 'start_time' not in t for t in tables))
        self.assertEqual(tables[0]['sessions'],[dict(slot='第二节',title='虚构数学')])
        data=self.sources(); data['timetables'][0]['effective_until']='2026-09-08'; self.write_sources(data)
        self.assertEqual(len(self.store.snapshot('2026-09-07','2026-09-15')['timetables']),1)
        with self.assertRaises(family_calendar.CalendarError): self.store.save(self.request(id=source['id']))

    def test_occurrence_changes_only_one_day_and_slot_with_history_and_exact_retry(self):
        parent=self.store.save(self.request(repeat='daily',until='2026-09-14',status='confirmed',extra_times=[dict(id='1'*16,start_time='18:00',end_time='18:20')]))
        body=dict(series_id=parent['id'],series_version=1,origin_day='2026-09-12',slot_id='1'*16,version=0,
                  day='2026-10-03',start_time='17:00',end_time='17:20',status='confirmed',note='虚构反馈：本次改到周末')
        saved=self.store.save_occurrence(body);before=self.dump()
        self.assertEqual(self.store.save_occurrence(body),saved);self.assertEqual(self.dump(),before)
        original=self.store.snapshot('2026-09-12','2026-09-14')['events']
        self.assertEqual(len(original),5);self.assertFalse(any(e['day']=='2026-09-12' and e['start_time']=='18:00' for e in original))
        moved=self.store.snapshot('2026-10-03','2026-10-03')['events'];self.assertEqual(len(moved),1);self.assertEqual(moved[0]['id'],saved['id'])
        finished=self.store.save_occurrence(dict(body,version=1,status='completed',note='虚构完成依据'))
        self.assertEqual(len(finished['occurrence']['history']),2);self.assertEqual(finished['occurrence']['original']['start_time'],'18:00')
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT version,status FROM calendar_events WHERE id=?',(parent['id'],)).fetchone()[:],(1,'confirmed'))
        fresh=app.calendar_store().snapshot('2026-10-03','2026-10-03')['events'][0]
        self.assertEqual(fresh['status'],'completed');self.assertEqual(fresh['occurrence']['history'][0]['day'],'2026-10-03')
        with self.assertRaises(family_calendar.CalendarError):self.store.save(dict(self.request(),id=saved['id'],version=2))

    def test_occurrence_rejects_missing_slots_stale_series_and_cross_scope_fields(self):
        parent=self.store.save(self.request(repeat='weekly',until='2026-10-12'))
        body=dict(series_id=parent['id'],series_version=1,origin_day='2026-09-12',slot_id='',version=0,day='2026-09-12',start_time='09:00',end_time='10:00',status='cancelled',note='虚构本次不参加')
        before=self.dump()
        for bad in [dict(body,origin_day='2026-09-13'),dict(body,slot_id='2'*16),dict(body,series_id='source:school'),dict(body,series_version=0),dict(body,child_ids=['child-2']),dict(body,status='finished'),dict(body,end_time='08:00')]:
            with self.assertRaises(family_calendar.CalendarError):self.store.save_occurrence(bad)
        self.assertEqual(self.dump(),before)
        with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(self.store.save_occurrence,[body,body]))
        self.assertEqual(out[0],out[1]);self.assertEqual(len(out[0]['occurrence']['history']),1)
        self.store.save(dict(self.request(),version=1,repeat='weekly',until='2026-10-12',child_ids=['child-2'],start_time='10:00',end_time='11:00'))
        # A changed template does not reassign a parent's already-recorded occurrence.
        row=app.calendar_store().snapshot('2026-09-12','2026-09-12')['events'][0]
        self.assertEqual(row['child_ids'],['child-1']);self.assertEqual(row['status'],'cancelled');self.assertEqual(row['start_time'],'09:00')
        self.assertEqual(self.store.save_occurrence(body)['id'],row['id'])
        with self.assertRaises(family_calendar.CalendarError):self.store.save_occurrence(dict(body,version=1,status='confirmed'))
        restored=self.store.save_occurrence(dict(body,version=1,series_version=2,status='confirmed'))
        self.assertEqual(restored['child_ids'],['child-1']);self.assertEqual(len(restored['occurrence']['history']),2)

    def test_occurrence_subscription_excludes_original_and_keeps_replacement_uid(self):
        import datetime as dt
        parent=self.store.save(self.request(day='2026-09-12',repeat='daily',status='confirmed',start_time='00:30',end_time='00:45'))
        body=dict(series_id=parent['id'],series_version=1,origin_day='2026-09-12',slot_id='',version=0,day='2026-09-20',start_time='01:00',end_time='01:15',status='confirmed',note='PRIVATE_OCCURRENCE_NOTE')
        saved=self.store.save_occurrence(body)
        def feed():return family_calendar.render_ics(self.store.subscription_events(),app.profiles(),dt.datetime.now(dt.timezone.utc),'synthetic').decode().replace('\r\n ','')
        text=feed();self.assertIn('EXDATE;TZID=Asia/Shanghai:20260912T003000',text);self.assertIn('DTSTART:20260919T170000Z',text)
        self.assertEqual(text.count('BEGIN:VEVENT'),2);self.assertNotIn('PRIVATE_OCCURRENCE_NOTE',text)
        uids=[line for line in text.splitlines() if line.startswith('UID:')]
        self.store.save_occurrence(dict(body,version=1,status='cancelled'))
        self.assertEqual([line for line in feed().splitlines() if line.startswith('UID:')],uids);self.assertIn('STATUS:CANCELLED',feed())
        self.assertEqual(self.store.snapshot('2026-09-20','2026-09-20')['events'][-1]['occurrence']['day'],'2026-09-12')

    def test_occurrence_backup_and_corrupt_history_fail_without_overwrite(self):
        import copy
        import sqlite3
        parent=self.store.save(self.request(repeat='daily',until='2026-09-14'))
        body=dict(series_id=parent['id'],series_version=1,origin_day=parent['day'],slot_id='',version=0,
                  day=parent['day'],start_time='',end_time='',status='completed',note='虚构家长确认')
        saved=self.store.save_occurrence(body);before=self.dump()
        backup=app.DATA/'synthetic-backup.sqlite3'
        with app.connect() as c,sqlite3.connect(backup) as dst:c.backup(dst)
        restored=family_calendar.Store(lambda:sqlite3.connect(backup),app.profiles,app.DATA)
        self.assertEqual(restored.snapshot(parent['day'],parent['day']),self.store.snapshot(parent['day'],parent['day']))
        with self.assertRaises(family_calendar.CalendarError):self.store.save(self.request(version=1,repeat='none'))
        self.assertEqual(self.dump(),before)
        for mutate in [lambda o:o.update(slot_id=[]),lambda o:o.update(slot_id='f'),lambda o:o.update(history=[]),
                       lambda o:o['history'][0].update(child_ids=['child-2']),lambda o:o['history'][0].update(note='被改写'),
                       lambda o:o['original'].update(day='2026-01-01'),None]:
            origin=copy.deepcopy(saved['occurrence'])
            if mutate:mutate(origin)
            else:origin=[]
            with app.connect() as c:c.execute('UPDATE calendar_events SET occurrence=? WHERE id=?',(json.dumps(origin),saved['id']))
            broken=self.dump()
            for action in [lambda:self.store.snapshot(parent['day'],parent['day']),self.store.subscription_events,
                           lambda:self.store.save_occurrence(dict(body,version=1,status='confirmed'))]:
                with self.assertRaises(family_calendar.CalendarError) as caught:action()
                self.assertEqual(caught.exception.code,'calendar_data_error')
                self.assertEqual(self.dump(),broken)
            with app.connect() as c:c.execute('UPDATE calendar_events SET occurrence=? WHERE id=?',(family_calendar._json(saved['occurrence']),saved['id']))
        self.assertEqual(self.dump(),before)

    def test_invalid_source_is_explicit_and_manual_calendar_survives(self):
        self.store.save(self.request())
        fixtures=[]
        wrong=self.sources(); wrong['events'][0]['child_ids']=['unknown']; fixtures.append(wrong)
        wrong=self.sources(); wrong['timetables'][0]['child_id']='unknown'; fixtures.append(wrong)
        wrong=self.sources(); wrong['timetables'][0]['attachment']='../../account.json'; fixtures.append(wrong)
        wrong=self.sources(); wrong['timetables'][0]['week'][0]['weekday']=True; fixtures.append(wrong)
        wrong=self.sources(); wrong['timetables'][0]['week']*=2; fixtures.append(wrong)
        wrong=self.sources(); wrong['events']*=2; fixtures.append(wrong)
        wrong=self.sources(); wrong['events'][0]['day']='2026-02-30'; fixtures.append(wrong)
        for data in fixtures:
            self.write_sources(data); result=self.store.snapshot('2026-09-01','2026-09-30')
            self.assertTrue(result['source_error']); self.assertEqual(len(result['events']),1); self.assertEqual(result['timetables'],[])
            self.assertNotIn(str(app.DATA),result['source_error'])
        for raw in ['{broken','x'*(1024*1024+1)]:
            self.source.write_text(raw); self.assertTrue(self.store.snapshot('2026-09-01','2026-09-30')['source_error'])
        self.source.unlink(); self.source.symlink_to(app.ROOT/'not-authorized.json')
        self.assertTrue(self.store.snapshot('2026-09-01','2026-09-30')['source_error'])

    def test_stable_child_id_survives_profile_name_change(self):
        self.store.save(self.request())
        app.save_profile(dict(child_id='child-1',name='示例新称呼',grade='五年级',classroom='示例班',version=0,reason='虚构家长更正'))
        self.assertEqual(self.store.snapshot('2026-09-12','2026-09-12')['events'][0]['child_ids'],['child-1'])

    def test_http_auth_errors_retry_and_static_route(self):
        (app.ROOT/'calendar.js').write_text('// synthetic calendar asset')
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def call(method,path,obj=None,token=True,host='127.0.0.1'):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':host}
            if token: headers['X-Family-Token']=app.TOKEN
            body=json.dumps(obj).encode() if obj is not None else None
            c.request(method,path,body,headers); r=c.getresponse(); data=r.read(); status=r.status;c.close()
            return status,data
        try:
            with patch.dict(os.environ,{},clear=True):
                before=self.dump()
                self.assertEqual(call('POST','/api/calendar/save',self.request(),token=False)[0],403)
                self.assertEqual(call('POST','/api/calendar/save',self.request(),host='untrusted.invalid')[0],403)
                self.assertEqual(call('GET','/api/calendar?start=2026-09-01&end=2026-09-30',host='untrusted.invalid')[0],403)
                self.assertEqual(self.dump(),before)
                code,raw=call('POST','/api/calendar/save',self.request()); self.assertEqual(code,200)
                self.assertEqual(json.loads(raw)['event']['version'],1)
                self.assertEqual(call('POST','/api/calendar/save',self.request()),(code,raw))
                self.assertEqual(call('POST','/api/calendar/save',self.request(title='冲突新值'))[0],409)
                code,raw=call('GET','/api/calendar?start=2026-09-01&end=2026-09-30')
                self.assertEqual(code,200);self.assertEqual(len(json.loads(raw)['events']),1)
                for path in ['/api/calendar','/api/calendar?start=2026-09-01&start=2026-09-02&end=2026-09-30',
                             '/api/calendar?start=2026-09-01&end=2026-10-02']:
                    self.assertEqual(call('GET',path)[0],400)
                self.assertEqual(call('GET','/calendar.js'),(200,b'// synthetic calendar asset'))
        finally: server.shutdown();server.server_close();worker.join()

    def test_subscription_http_auth_privacy_decisions_and_read_only(self):
        self.store.save(self.request(status='confirmed'))
        self.write_sources()
        (app.ROOT/'跟踪台账.md').write_text('| T01 | 示例乙 | 虚构学校要求 | 待核对 | 待跟进 | 私有来源 | 私有细节 |\n')
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def get(path='/calendar.ics',host='127.0.0.1',login=''):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            c.request('GET',path,headers={'Host':host,'Tailscale-User-Login':login})
            r=c.getresponse();result=r.status,dict(r.getheaders()),r.read();c.close();return result
        try:
            with patch.dict(os.environ,{'FAMILY_HOST':'family.invalid','FAMILY_USER':'parent@example.invalid','FAMILY_CALENDAR_ID':'synthetic-family'},clear=True):
                before=self.dump()
                code,headers,body=get(host='family.invalid',login='parent@example.invalid')
                self.assertEqual(code,200);self.assertEqual(headers['Content-Type'],'text/calendar; charset=utf-8')
                self.assertEqual(headers['Cache-Control'],'no-store')
                text=body.decode().replace('\r\n ','')
                self.assertEqual(text.count('BEGIN:VEVENT'),2)
                for private in ['虚构约定','虚构教师通知','钟点待核对','私有细节','虚构课表','DESCRIPTION:','ATTACH:','VALARM']:
                    self.assertNotIn(private,text)
                self.assertEqual(get(host='family.invalid')[0],403)
                self.assertEqual(get(host='untrusted.invalid')[0],403)
                self.assertNotIn(b'BEGIN:VCALENDAR',get('/child/calendar.ics')[2])
                self.assertEqual(get('/calendar.ics?child_id=child-1',host='family.invalid',login='parent@example.invalid')[0],400)
                self.assertEqual(self.dump(),before)
                uids=[line for line in text.splitlines() if line.startswith('UID:')]
                app.save_profile(dict(child_id='child-2',name='示例新称呼',grade='初一',classroom='示例班',version=0,reason='虚构更正'))
                app.save_task(dict(id='T01',status='不参加',note='虚构决定',expected_updated=''))
                before=self.dump();updated=get(host='family.invalid',login='parent@example.invalid')[2].decode().replace('\r\n ','')
                self.assertIn('STATUS:CANCELLED',updated)
                self.assertIn('示例新称呼',updated)
                self.assertEqual(uids,[line for line in updated.splitlines() if line.startswith('UID:')])
                self.assertEqual(self.dump(),before)
                ledger=app.ROOT/'跟踪台账.md';original=ledger.read_text();ledger.unlink()
                self.assertEqual(get(host='family.invalid',login='parent@example.invalid')[0],503)  # Missing original task must not undo nonparticipation.
                ledger.write_text(original)
                wrong_child=self.sources();wrong_child['events'][0]['child_ids']=['child-1'];self.write_sources(wrong_child)
                self.assertEqual(get(host='family.invalid',login='parent@example.invalid')[0],503)
                self.source.write_text('{invalid')
                code,headers,body=get(host='family.invalid',login='parent@example.invalid');self.assertEqual(code,503)
                self.assertNotIn(b'BEGIN:VCALENDAR',body)
        finally: server.shutdown();server.server_close();worker.join()


if __name__=='__main__': unittest.main()

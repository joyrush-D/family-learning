"""Fictional read-only ICS regressions; no live family files or native calendar."""
import datetime as dt
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import family_calendar as calendar


PROFILES=[dict(id='child-a',name='示例甲'),dict(id='child-b',name='示例乙')]
NOW=dt.datetime(2026,12,31,23,59,59,tzinfo=dt.timezone(dt.timedelta(hours=8)))


def event(**changes):
    row=dict(id='a'*32,version=1,child_ids=['child-a'],title='虚构观察活动',category='activity',
             day='2027-01-01',start_time='07:30',end_time='08:00',location='示例公园',
             note='PRIVATE_NOTE_CANARY',status='confirmed',repeat='none',until='',task_id='')
    row.update(changes)
    return row


def render(rows,profiles=PROFILES,**kwargs):
    return calendar.render_ics(rows,profiles,NOW,'synthetic-deployment.invalid',**kwargs)


def lines(raw):
    return raw.decode('utf-8').replace('\r\n ','').split('\r\n')


def uid(raw):
    return next(line for line in lines(raw) if line.startswith('UID:'))


class CalendarICSRenderTests(unittest.TestCase):
    def test_confirmed_utc_and_unknown_clock_never_invent_busy_time(self):
        result=lines(render([event()]))
        self.assertIn('DTSTART:20261231T233000Z',result)
        self.assertIn('DTEND:20270101T000000Z',result)
        self.assertIn('DTSTAMP:20261231T155959Z',result)
        self.assertIn('TRANSP:OPAQUE',result)
        self.assertIn('SUMMARY:示例甲 · 虚构观察活动',result)
        no_end=lines(render([event(end_time='')]))
        self.assertFalse(any(line.startswith('DTEND') for line in no_end))
        unknown=lines(render([event(start_time='',end_time='')]))
        self.assertIn('DTSTART;VALUE=DATE:20270101',unknown)
        self.assertIn('SUMMARY:[时间待定] 示例甲 · 虚构观察活动',unknown)
        self.assertIn('TRANSP:TRANSPARENT',unknown)
        self.assertFalse(any(line.startswith(('DTEND','VALARM','TRIGGER')) for line in unknown))
        # All-day DATE is valid at date.max without calculating an overflowing end.
        self.assertIn('DTSTART;VALUE=DATE:99991231',lines(render([event(day='9999-12-31',start_time='',end_time='')])))

    def test_status_and_per_child_participation_keep_same_uid(self):
        row=event(child_ids=['child-a','child-b'],task_id='T-SYNTHETIC')
        original=render([row])
        partly=render([row],task_states={'T-SYNTHETIC':{'child-a':'不参加','child-b':'已完成'}})
        self.assertEqual(uid(partly),uid(original))
        self.assertIn('SUMMARY:示例乙 · 虚构观察活动',lines(partly))
        self.assertIn('STATUS:CONFIRMED',lines(partly))
        cancelled=render([row],task_states={'T-SYNTHETIC':{'child-a':'不参加','child-b':'不适用'}})
        self.assertEqual(uid(cancelled),uid(original))
        self.assertIn('STATUS:CANCELLED',lines(cancelled))
        self.assertIn('TRANSP:TRANSPARENT',lines(cancelled))
        self.assertIn('SUMMARY:[已取消] 示例甲、示例乙 · 虚构观察活动',lines(cancelled))
        renamed=render([row],profiles=[dict(id='child-a',name='示例新称呼'),PROFILES[1]],
                       task_states={'T-SYNTHETIC':{'child-a':'不参加','child-b':'不适用'}})
        self.assertIn('SUMMARY:[已取消] 示例新称呼、示例乙 · 虚构观察活动',lines(renamed))
        tentative=render([dict(row,status='tentative')])
        self.assertIn('STATUS:TENTATIVE',lines(tentative))
        self.assertIn('TRANSP:TRANSPARENT',lines(tentative))
        self.assertIn('SUMMARY:[暂定] 示例甲、示例乙 · 虚构观察活动',lines(tentative))
        self.assertEqual(uid(tentative),uid(original))
        cancelled=render([dict(row,status='cancelled')])
        self.assertIn('STATUS:CANCELLED',lines(cancelled))
        self.assertEqual(uid(cancelled),uid(original))
        self.assertNotIn('全家',cancelled.decode())

    def test_weekly_one_original_series_until_and_whole_series_reschedule(self):
        row=event(day='2026-01-02',series_day='2026-01-02',repeat='weekly',until='2027-02-01')
        original=render([row]); result=lines(original)
        self.assertEqual(result.count('BEGIN:VEVENT'),1)
        self.assertIn('DTSTART:20260101T233000Z',result)
        self.assertIn('RRULE:FREQ=WEEKLY;UNTIL=20270131T233000Z',result)
        moved=render([dict(row,day='2026-01-03',series_day='2026-01-03',title='虚构改期',version=2)])
        self.assertEqual(uid(original),uid(moved))
        self.assertIn('DTSTART:20260102T233000Z',lines(moved))
        all_day=lines(render([dict(row,start_time='',end_time='')]))
        self.assertIn('RRULE:FREQ=WEEKLY;UNTIL=20270201',all_day)
        self.assertIn('RRULE:FREQ=WEEKLY',lines(render([dict(row,until='')])) )
        with self.assertRaises(calendar.CalendarError): render([row,dict(row,day='2026-01-09')])
        with self.assertRaises(calendar.CalendarError): render([dict(row,day='2026-01-09')])

    def test_names_reschedule_and_namespace_do_not_leak_private_data(self):
        row=event(id='source:PRIVATE_SOURCE_ID',source='PRIVATE_MESSAGE_CANARY',
                  attachment='PRIVATE_IMAGE_CANARY',score='PRIVATE_SCORE_CANARY',mood='PRIVATE_MOOD_CANARY')
        raw=render([row])
        renamed=render([dict(row,day='2027-02-01')],profiles=[dict(id='child-a',name='示例新名字')])
        self.assertEqual(uid(raw),uid(renamed))
        different=calendar.render_ics([row],PROFILES,NOW,'another-synthetic.invalid')
        self.assertNotEqual(uid(raw),uid(different))
        for private in ['PRIVATE_','synthetic-deployment.invalid','source:','DESCRIPTION:','ATTACH:','VALARM']:
            self.assertNotIn(private,raw.decode())

    def test_utf8_folding_text_escaping_and_no_property_injection(self):
        title='虚构🌱'*40+',分号;斜线\\换行\nBEGIN:VALARM'
        raw=render([event(title=title,location='虚构,地点;一区\\角落\n次行')])
        self.assertTrue(raw.endswith(b'\r\n'))
        self.assertNotIn(b'\n',raw.replace(b'\r\n',b''))
        self.assertNotIn(b'\r',raw.replace(b'\r\n',b''))
        physical=raw.split(b'\r\n')
        self.assertTrue(all(len(line)<=75 for line in physical))
        for line in physical: line.decode('utf-8')
        self.assertTrue(any(line.startswith(b' ') for line in physical))
        unfolded=lines(raw)
        self.assertIn('SUMMARY:示例甲 · '+calendar._ics_text(title),unfolded)
        self.assertIn('LOCATION:虚构\\,地点\\;一区\\\\角落\\n次行',unfolded)
        self.assertNotIn('BEGIN:VALARM',unfolded)

    def test_invalid_data_fails_whole_feed_instead_of_empty_or_partial_success(self):
        invalid=[dict(day='2027-02-29'),dict(start_time='24:00'),dict(child_ids=['missing']),
                 dict(child_ids=['child-a','child-a']),dict(id='\n'),dict(title=''),dict(status='done'),
                 dict(repeat='daily'),dict(until='2026-01-01'),dict(title='bad\ud800'),
                 dict(day='0001-01-01',start_time='01:00',end_time='02:00')]
        for change in invalid:
            with self.subTest(change=change),self.assertRaises(calendar.CalendarError): render([event(**change)])
        for profiles in [None,[PROFILES[0],PROFILES[0]],[dict(id='child-a',name='')],[dict(id='unknown',name='示例甲')]]:
            with self.subTest(profiles=profiles),self.assertRaises(calendar.CalendarError): render([event()],profiles=profiles)
        for overlay in [[],{'T':[]},{'T':{'missing':'不参加'}},{'T':{'child-a':[]}},{'T':{'child-a':'maybe'}}]:
            with self.subTest(overlay=overlay),self.assertRaises(calendar.CalendarError): render([event()],task_states=overlay)
        with self.assertRaises(calendar.CalendarError): render([event(),event()])
        with self.assertRaises(calendar.CalendarError): render([event(id=str(n)) for n in range(1001)])
        with self.assertRaises(calendar.CalendarError): calendar.render_ics([],PROFILES,NOW.replace(tzinfo=None),'synthetic')
        self.assertEqual(lines(render([])).count('BEGIN:VEVENT'),0)


class CalendarICSStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-calendar-ics-')
        self.path=Path(self.temp.name); self.db=self.path/'synthetic.sqlite3'
        self.connect=lambda:sqlite3.connect(self.db)
        self.store=calendar.Store(self.connect,lambda:PROFILES,self.path)

    def tearDown(self): self.temp.cleanup()

    def save(self,**changes):
        row=event(**changes)
        return self.store.save({key:value for key,value in row.items() if key in calendar.FIELDS or key in {'id','version'}}|{'version':0})

    def dump(self):
        with self.connect() as c: return '\n'.join(c.iterdump())

    def source(self,**changes):
        row=event(id='school-synthetic',source='PRIVATE_SOURCE_CANARY',**changes)
        return {key:value for key,value in row.items() if key in set(calendar.FIELDS)-{'repeat','until'} or key in {'id','source','task_id'}}

    def write_source(self,obj):
        (self.path/'日历来源.json').write_text(json.dumps(obj,ensure_ascii=False))

    def test_all_dates_original_series_and_cancellations_are_read_only(self):
        self.save(day='2000-01-01',repeat='weekly',until='2000-02-01',status='cancelled')
        self.save(id='b'*32,day='2030-01-01',status='tentative')
        self.write_source({'events':[self.source()], 'timetables':[dict(id='synthetic-table',child_id='child-a',
            effective_from='2026-01-01',title='PRIVATE_TIMETABLE_CANARY',source='PRIVATE_TABLE_SOURCE',
            week=[dict(weekday=1,sessions=[dict(slot='第一节',title='PRIVATE_COURSE_CANARY')])])]})
        before=self.dump(); source_before=(self.path/'日历来源.json').read_bytes()
        rows=self.store.subscription_events()
        self.assertEqual(len(rows),3)
        self.assertEqual([row['day'] for row in rows],['2000-01-01','2030-01-01','2027-01-01'])
        self.assertEqual(rows[0]['series_day'],'2000-01-01')
        self.assertEqual(rows[0]['status'],'cancelled')
        raw=render(rows)
        self.assertEqual(lines(raw).count('BEGIN:VEVENT'),3)
        self.assertNotIn('PRIVATE_',raw.decode())
        self.assertEqual(self.dump(),before)
        self.assertEqual((self.path/'日历来源.json').read_bytes(),source_before)

    def test_uninitialized_database_remains_uninitialized_and_sql_error_propagates(self):
        empty=self.path/'empty.sqlite3'; connect=lambda:sqlite3.connect(empty)
        store=calendar.Store(connect,lambda:PROFILES,self.path,initialize=False)
        self.assertEqual(store.subscription_events(),[])
        with connect() as c:
            self.assertEqual(c.execute('SELECT name FROM sqlite_master').fetchall(),[])
            c.execute('CREATE TABLE calendar_events (wrong TEXT)')
        with self.assertRaises(sqlite3.OperationalError): store.subscription_events()

    def test_unreadable_or_invalid_source_never_yields_partial_feed(self):
        self.save()
        source=self.path/'日历来源.json'
        for obj in [{'events':[self.source(child_ids=['unknown'])]}, {'events':[self.source(),self.source()]},
                    {'timetables':[{'invalid':'shape'}]}]:
            self.write_source(obj)
            with self.assertRaises(calendar.CalendarError) as caught: self.store.subscription_events()
            self.assertEqual(caught.exception.code,'calendar_source_unavailable')
        source.write_text('{broken')
        with self.assertRaises(calendar.CalendarError): self.store.subscription_events()
        source.unlink(); source.symlink_to(self.path/'missing.json')
        with self.assertRaises(calendar.CalendarError): self.store.subscription_events()

    def test_known_ceiling_checks_combined_sources_without_truncation(self):
        self.save()
        # Bulk fictional rows avoid 1,000 writes through the production API.
        with self.connect() as c:
            row=c.execute('SELECT * FROM calendar_events').fetchone()
            columns=[info[1] for info in c.execute('PRAGMA table_info(calendar_events)')]
            insert='INSERT INTO calendar_events VALUES ('+','.join('?' for _ in columns)+')'
            for number in range(999):
                values=list(row);values[0]=f'{number:032x}';c.execute(insert,values)
        self.assertEqual(len(self.store.subscription_events()),1000)
        before=self.dump()
        self.write_source({'events':[self.source()]})
        with self.assertRaises(calendar.CalendarError) as caught: self.store.subscription_events()
        self.assertEqual(caught.exception.code,'calendar_limit')
        self.assertEqual(self.dump(),before)
        (self.path/'日历来源.json').unlink()
        self.save(id='b'*32)
        with self.assertRaises(calendar.CalendarError): self.store.subscription_events()


if __name__=='__main__': unittest.main()

"""python3 test_calendar_draft.py: fictional date/query/draft HTTP checks; no real models."""
import copy
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import family_calendar
import family_llm


class CalendarLanguageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-calendar-language-')
        self.root=Path(self.tmp.name).resolve();self.data=self.root/'private';self.data.mkdir()
        self.config=patch.multiple(app,ROOT=self.root,DATA=self.data,DB=self.data/'family.sqlite3');self.config.start()
        self.env=patch.dict(os.environ,{},clear=True);self.env.start()
        (self.root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        self.output=None;self.calls=[]
        def model(messages,schema,name,*args,**kwargs):
            context=json.loads(messages[-1]['content']);self.calls.append((name,context,schema))
            if self.output is not None:return copy.deepcopy(self.output)
            if name=='family_learning_answer':return dict(answer='仅根据虚构范围内已录安排回答。',citation_ids=[i['id'] for i in context['evidence']])
            return dict(intent='create',title='虚构游泳',category='activity',day=context['exact_day'],child_ids=context['allowed_child_ids'],
                        start_time='',end_time='',location='',note='',repeat='none',until='',needs_review=[])
        self.model=patch.object(family_llm,'_chat_json',side_effect=model);self.model.start()
    def tearDown(self):
        self.model.stop();self.env.stop();self.config.stop();self.tmp.cleanup()
    def dump(self):
        # A draft may record its model usage, but must not change any family business row.
        with app.connect() as c:
            return '\n'.join(s for s in c.iterdump() if not s.startswith(('CREATE TABLE llm_usage_ledger ', 'INSERT INTO "llm_usage_ledger"')))
    def event(self,**fields):
        value=dict(id='a'*32,version=0,child_ids=['child-1'],title='虚构游泳',category='activity',day='2026-12-31',
                   start_time='15:00',end_time='',location='虚构场地',note='带好毛巾',status='tentative',repeat='none',until='')
        return app.calendar_store().save(value|fields)
    def draft(self,text='示例甲明天下午去游泳',child_ids=None):
        return app.calendar_draft_from_text(dict(text=text,child_ids=[] if child_ids is None else child_ids))
    def test_date_ranges_cross_year_sunday_midnight_and_explicit_priority(self):
        sunday=dt.datetime(2027,1,3,23,59,tzinfo=dt.timezone(dt.timedelta(hours=8)))
        expected={'本周末有什么安排':('2027-01-02','2027-01-03'),'下周末有什么安排':('2027-01-09','2027-01-10'),
                  '明天有什么安排':('2027-01-04','2027-01-04'),'明天要带什么去学校？':('2027-01-04','2027-01-04'),'下周有什么安排':('2027-01-04','2027-01-10'),
                  '2026-12-31到2027-01-02有什么安排':('2026-12-31','2027-01-02')}
        for question,bounds in expected.items():
            result=app.calendar_query_range(question,now=sunday)
            self.assertEqual((result['start'],result['end']),bounds);self.assertFalse(result['defaulted'])
        next_day=sunday+dt.timedelta(minutes=2)
        self.assertEqual(app.calendar_query_range('明天的安排',now=next_day)['start'],'2027-01-05')
        self.assertEqual(app.calendar_query_range('明天安排','2026-12-31','2027-01-01',now=sunday)['start'],'2026-12-31')
        self.assertTrue(app.calendar_query_range('比较2026-01-01与2026-09-30两次成绩',now=sunday)['defaulted'])
        self.assertTrue(app.calendar_query_range('今天的数学3/4分数题掌握得怎么样？',now=sunday)['defaulted'])
        recent=app.calendar_query_range('最近一周有什么安排？',now=sunday)
        self.assertEqual((recent['start'],recent['end']),('2026-12-28','2027-01-03'))
        recent=app.calendar_query_range('最近一周有什么安排？',now=dt.datetime(2026,12,31,12,tzinfo=sunday.tzinfo))
        self.assertEqual((recent['start'],recent['end']),('2026-12-25','2026-12-31'))
        self.assertTrue(app.calendar_query_range('最近一周有什么学习进展？',now=sunday)['defaulted'])
        for args in [('下月安排',None,None),('2026-02-30安排',None,None),('安排','2026-01-01',None),('安排','2026-01-01','2026-02-01')]:
            with self.assertRaises((ValueError,OverflowError)):app.calendar_query_range(*args,now=sunday)
    def test_uninitialized_query_is_read_only_and_missing_sources_are_explicit(self):
        before=self.dump();result=app.ask_family(dict(child='示例甲',question='本周末有什么安排'))
        self.assertEqual(self.dump(),before);self.assertEqual(self.calls,[])
        self.assertIn('学校日历与课表来源尚未录入',result['coverage']);self.assertIn('不代表没有安排或空闲',result['answer'])
        with app.connect() as c:self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='calendar_events'").fetchone())
    def test_calendar_and_timetable_evidence_is_owned_dated_and_citable(self):
        self.event(day='2026-12-26',repeat='weekly',until='2027-01-16')
        self.event(id='b'*32,day='2027-01-02',status='cancelled',title='虚构已取消安排')
        self.event(id='c'*32,child_ids=['child-2'],day='2027-01-02',title='OTHER_CHILD_PRIVATE_CANARY')
        self.event(id='d'*32,day='2027-02-01',title='OUTSIDE_RANGE_PRIVATE_CANARY')
        source=dict(events=[],timetables=[dict(id='table-'+('x'*80),child_id='child-1',effective_from='2026-12-01',effective_until='',
            title='虚构课表',source='虚构原图',attachment='',note='节次已核对，钟点尚未核对',week=[dict(weekday=6,sessions=[dict(slot='第一节',title='虚构阅读课')])])])
        (self.data/'日历来源.json').write_text(json.dumps(source,ensure_ascii=False))
        before=self.dump();result=app.ask_family(dict(child='示例甲',question='这段日历有什么安排',start='2027-01-01',end='2027-01-10'))
        self.assertEqual(before,self.dump());self.assertEqual(result['calendar_range'],dict(start='2027-01-01',end='2027-01-10',defaulted=False))
        evidence=self.calls[-1][1]['evidence'];text=json.dumps(evidence,ensure_ascii=False)
        self.assertNotIn('CANARY',text);self.assertIn('已取消',text);self.assertIn('未提供对应钟点',text)
        repeated=[r for r in evidence if r['target_id']=='a'*32]
        self.assertEqual({r['day'] for r in repeated},{'2027-01-02','2027-01-09'})
        self.assertEqual(len({r['id'] for r in evidence}),len(evidence));self.assertTrue(all(len(r['id'])<=100 for r in evidence))
        self.assertTrue(any(r['kind']=='timetable' for r in result['citations']))
        for citation in result['citations']:self.assertIn(citation,evidence)
        self.output=dict(answer='伪造来源',citation_ids=['calendar:fake'])
        with self.assertRaises(family_llm.LLMDraftError):app.ask_family(dict(child='示例甲',question='日历',start='2027-01-01',end='2027-01-10'))
    def test_failed_source_and_truncated_calendar_are_not_empty_success(self):
        for number in range(24):self.event(id=f'{number:032x}',title='虚构安排'+str(number),day='2027-01-02')
        (self.data/'日历来源.json').write_text('{bad')
        before=self.dump();result=app.ask_family(dict(child='示例甲',question='安排',start='2027-01-01',end='2027-01-03'))
        self.assertEqual(before,self.dump());self.assertIn('日历缺口',result['coverage']);self.assertIn('已读同孩安排24项',result['coverage'])
        self.assertLess(len(result['citations']),24);self.assertIn('未纳入',result['coverage'])
        with patch.object(family_calendar.Store,'snapshot',side_effect=app.sqlite3.OperationalError('synthetic private error')):
            evidence,coverage=app.query_evidence('示例甲','日历安排','2027-01-01','2027-01-03')
        self.assertIn('日历资料读取失败',coverage);self.assertNotIn('synthetic private error',coverage)
    def test_draft_missing_fields_relative_date_and_no_database_write(self):
        before=self.dump();result=self.draft('周末去游泳')
        self.assertEqual(result['draft']['child_ids'],[]);self.assertEqual(result['draft']['day'],'')
        self.assertEqual(result['draft']['status'],'tentative');self.assertNotIn('id',result['draft']);self.assertNotIn('version',result['draft'])
        self.assertTrue(result['needs_review']);self.assertEqual(self.dump(),before)
        result=self.draft();tomorrow=(dt.date.fromisoformat(result['reference_date'])+dt.timedelta(days=1)).isoformat()
        self.assertEqual(result['draft']['day'],tomorrow);self.assertEqual(result['draft']['child_ids'],['child-1'])
        self.assertEqual(result['draft']['start_time'],'');self.assertEqual(self.dump(),before)
        self.assertEqual(self.draft('示例乙明天游泳',['child-1'])['draft']['child_ids'],[])
        self.assertEqual(self.draft('周六下午三点带两个孩子去公园')['draft']['child_ids'],['child-1','child-2'])
        self.assertEqual(self.draft('周六下午三点带两个孩子去公园',['child-1'])['draft']['child_ids'],[])
        self.assertEqual(self.draft('明天全家去公园')['draft']['child_ids'],['child-1','child-2'])
        self.assertEqual(self.draft('每周六示例甲游泳')['draft']['day'],'')
        for phrase in ['把周六游泳改到周日','取消周末游泳']:
            count=len(self.calls);result=self.draft(phrase)
            self.assertIsNone(result['draft']);self.assertIn(result['intent'],('edit','cancel'));self.assertEqual(len(self.calls),count)
    def test_untrusted_model_fields_children_dates_and_clocks_are_rejected(self):
        valid=self.draft()['draft'];valid.pop('status');valid.update(intent='create',needs_review=[])
        before=self.dump()
        for changed in [dict(child_ids=['child-2']),dict(child_ids=['unknown']),dict(child_ids=['child-1','child-1']),dict(day='2026-02-30'),
                        dict(day='2099-01-01'),dict(start_time='25:00'),dict(start_time='15:00',end_time='14:00'),dict(status='confirmed'),
                        dict(repeat='weekly'),dict(title='x'*201),dict(needs_review='guess'),dict(intent='save')]:
            self.output=valid|changed
            with self.subTest(changed=changed),self.assertRaises(family_llm.LLMDraftError):self.draft()
        self.output=valid|dict(intent='edit');self.assertIsNone(self.draft()['draft'])
        self.assertEqual(self.dump(),before)
    def test_http_auth_draft_review_then_original_save_with_parent_edits(self):
        app.calendar_store();before=self.dump()
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(path,body,token=True,host='localhost'):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port)
            headers={'Content-Type':'application/json','Host':host}
            if token:headers['X-Family-Token']=app.TOKEN
            c.request('POST',path,json.dumps(body),headers);r=c.getresponse();raw=r.read();code=r.status;c.close();return code,json.loads(raw)
        try:
            body=dict(text='周末去游泳',child_ids=[])
            self.assertEqual(post('/api/calendar/draft',body,token=False)[0],403)
            self.assertEqual(post('/api/calendar/draft',body,host='untrusted.invalid')[0],403)
            self.assertEqual(post('/child/api/calendar/draft',body)[0],404)
            for bad in [body|dict(child_ids=['unknown']),body|dict(text=''),body|dict(save=True)]:self.assertEqual(post('/api/calendar/draft',bad)[0],400)
            code,result=post('/api/calendar/draft',body);self.assertEqual(code,200);self.assertEqual(self.dump(),before)
            edited=result['draft']|dict(id='f'*32,version=0,child_ids=['child-1'],day='2027-01-02',start_time='16:00',note='家长已修改时间和要求')
            code,saved=post('/api/calendar/save',edited);self.assertEqual(code,200);self.assertEqual(saved['event']['start_time'],'16:00')
            self.assertEqual(post('/api/calendar/save',edited),(code,saved))
            with app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM calendar_events').fetchone()[0],1)
            self.assertEqual(post('/api/ask',dict(child='示例甲',question='日历',start='2027-01-01'))[0],400)
            self.assertEqual(post('/api/ask',dict(child='示例甲',question='日历',start=None,end=None))[0],400)
            self.assertEqual(post('/api/ask',dict(child='示例甲',question='下周末安排'),token=False)[0],403)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

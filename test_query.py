"""python3 test_query.py: synthetic temporary data and loopback model HTTP only."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app
import family_llm


class Model(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.calls.append(body)
        mode=self.server.mode
        if mode=='error':
            self.send_response(500);self.end_headers()
            self.wfile.write(b'SYNTHETIC_PRIVATE_RESPONSE synthetic-api-secret');return
        context=json.loads(body['messages'][-1]['content'])
        result={'answer':'虚构资料显示已登记订正，仍需核对独立复测。','citation_ids':[context['evidence'][0]['id']]}
        if isinstance(mode,dict): result=mode
        content=json.dumps(result,ensure_ascii=False) if mode!='bad_json' else 'SYNTHETIC_PRIVATE_RESPONSE invalid'
        wire=json.dumps({'choices':[{'finish_reason':'length' if mode=='length' else 'stop','message':{'content':content}}]}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(wire)


class QueryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=ThreadingHTTPServer(('127.0.0.1',0),Model)
        cls.worker=threading.Thread(target=cls.model.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.model.shutdown();cls.model.server_close();cls.worker.join()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-query-')
        self.old=(app.ROOT,app.DATA,app.DB)
        app.ROOT=Path(self.tmp.name);app.DATA=app.ROOT/'private';app.DATA.mkdir();app.DB=app.DATA/'family.sqlite3'
        (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        (app.ROOT/'跟踪台账.md').write_text('| T01 | 示例甲 | 数学订正待办 | 2026-09-10 | 待跟进 | 虚构通知 | 核对订正 |\n| T02 | 示例乙 | ONLY_OTHER_CHILD_TASK | 2026-09-10 | 待跟进 | 虚构通知 | 保留隐私 |\n')
        self.record(title='虚构原题',category='成绩',score='0',total='100')
        self.record(title='虚构订正',related_record_id=1,followup_kind='订正')
        self.record(title='虚构独立复测',related_record_id=2,followup_kind='独立复测')
        self.record(child='示例乙',title='ONLY_OTHER_CHILD_RECORD')
        app.save_task(dict(id='T01',status='已完成',note='虚构家长核对：已订正，尚需核对复测'))
        care=[dict(id='synthetic-care-'+str(i),child=child,topic='学习',title=title,
                   evidence='虚构记录依据',action='一起回顾',review_on='2026-01-02',expires_on='2026-01-03')
              for i,child,title in [(1,'示例甲','虚构过期建议'),(2,'示例乙','ONLY_OTHER_CHILD_CARE')]]
        (app.DATA/'陪伴建议.json').write_text(json.dumps(care,ensure_ascii=False))
        # These unrelated files must never enter a model query.
        (app.DATA/'采集状态.json').write_text('{"secret":"ONLY_SYNC_SECRET"}')
        (app.ROOT/'消息来源.md').write_text('ONLY_ACCOUNT_CONFIG')
        self.model.calls=[];self.model.mode='ok'
        self.env=patch.dict(os.environ,dict(FAMILY_LLM_BASE_URL=f'http://127.0.0.1:{self.model.server_port}/v1',
            FAMILY_LLM_MODEL='synthetic-model',FAMILY_LLM_API_KEY='synthetic-api-secret'),clear=True)
        self.env.start()
    def tearDown(self):
        self.env.stop();app.ROOT,app.DATA,app.DB=self.old;self.tmp.cleanup()
    def record(self,**extra):
        value=dict(child='示例甲',day='2026-09-01',category='学习进展',subject='数学',title='虚构记录',note='虚构记录说明',source='虚构家长核对')
        value.update(extra);app.save_record(value)
    def ask(self,**extra):
        value=dict(child='示例甲',question='这次数学订正后有没有独立复测？');value.update(extra)
        return app.ask_family(value)
    def database(self):
        with app.connect() as c: return '\n'.join(c.iterdump())
    def reading_call(self,action,row=None,**extra):
        self.reading_counter=getattr(self,'reading_counter',0)+1
        obj=dict(child_id='child-1',request_key='synthetic-reading-query-'+str(self.reading_counter))
        if row: obj.update(id=row['id'],version=row['version'],child_id=row['child_id'])
        obj.update(extra);result=app.reading_store().mutate(action,obj)
        return result.get('task',result.get('redemption'))
    def reading_award(self,child_id='child-1',book='虚构阅读故事'):
        task=self.reading_call('create',child_id=child_id,book='HISTORY_READING_ONLY',scope='第一章',method='语音',criteria='分享自己的发现',stamps=3)
        task=self.reading_call('edit',task,book=book)
        task=self.reading_call('start',task,note='虚构开始依据')
        task=self.reading_call('submit',task,work_text='虚构作品：我发现了角色改变主意的原因。')
        return self.reading_call('confirm',task,note='虚构家长确认作品与实际阅读')
    def test_isolation_status_chain_and_server_owned_citations(self):
        before=self.database();result=self.ask();self.assertEqual(self.database(),before)
        self.assertEqual(set(result),{'answer','citations','coverage','calendar_range'})
        body=self.model.calls[-1];context=json.loads(body['messages'][-1]['content'])
        wire=json.dumps(body,ensure_ascii=False)
        for secret in ['ONLY_OTHER_CHILD','ONLY_SYNC_SECRET','ONLY_ACCOUNT_CONFIG',app.TOKEN,'synthetic-api-secret','示例乙']:
            self.assertNotIn(secret,wire)
        self.assertEqual(body['response_format']['type'],'json_schema')
        self.assertTrue(body['response_format']['json_schema']['strict'])
        self.assertNotIn('tools',body)
        evidence={i['id']:i for i in context['evidence']}
        self.assertTrue({'record:1','record:2','record:3','task:T01','care:synthetic-care-1'}<=set(evidence))
        self.assertIn('实得分：0',evidence['record:1']['detail'])
        self.assertIn('关联原记录：虚构原题',evidence['record:2']['detail'])
        self.assertIn('关联原记录：未关联',evidence['record:1']['detail'])
        self.assertIn('实得分：未记录',evidence['record:2']['detail'])
        self.assertNotIn('关联原记录ID',evidence['record:2']['detail'])
        self.assertIn('跟进类型：独立复测',evidence['record:3']['detail'])
        self.assertIn('当前状态：已完成',evidence['task:T01']['detail'])
        self.assertIn('尚需核对复测',evidence['task:T01']['detail'])
        self.assertIn('已过期',evidence['care:synthetic-care-1']['detail'])
        self.assertIn('当前北京时间',result['coverage'])
        self.assertEqual(result['citations'][0],evidence[result['citations'][0]['id']])
        self.assertEqual(set(result['citations'][0]),{'id','kind','target_id','title','child','day','detail'})
    def test_no_data_does_not_call_model_even_unconfigured(self):
        with app.connect() as c:
            c.execute('DELETE FROM records');c.execute('DELETE FROM task_updates')
        (app.ROOT/'跟踪台账.md').write_text('');(app.DATA/'陪伴建议.json').write_text('[]')
        with patch.dict(os.environ,{},clear=True): result=self.ask()
        self.assertEqual(result['citations'],[]);self.assertIn('没有这个孩子的可用资料',result['answer'])
        self.assertEqual(self.model.calls,[])
        # Initializing reading tables creates two zero wallets, not query evidence.
        app.reading_store()
        before=self.database()
        with patch.dict(os.environ,{},clear=True): result=self.ask(question='阅读印章有多少？')
        self.assertEqual(result['citations'],[]);self.assertEqual(self.model.calls,[])
        self.assertEqual(self.database(),before)
        self.reading_award('child-2','ONLY_OTHER_CHILD_READING')
        result=self.ask(question='阅读任务情况')
        self.assertEqual(result['citations'],[]);self.assertEqual(self.model.calls,[])
    def test_fabricated_citation_and_structures_rejected(self):
        before=self.database()
        for mode in [dict(answer='虚构答案',citation_ids=['record:999']),
                     dict(answer='虚构答案',citation_ids=['record:4']),
                     dict(answer='虚构答案',citation_ids=[{'id':'record:1'}]),
                     dict(answer='虚构答案',citation_ids=['record:1','record:1']),
                     dict(answer='虚构答案',citation_ids=['record:1'],citations=[{'child':'示例乙'}]),
                     dict(answer=123,citation_ids=['record:1'])]:
            with self.subTest(mode=mode):
                self.model.mode=mode
                with self.assertRaises(family_llm.LLMDraftError): self.ask()
        self.assertEqual(self.database(),before)
    def test_answer_without_citations_cannot_assert_fact(self):
        self.model.mode=dict(answer='无依据断言：全部完成',citation_ids=[])
        result=self.ask();self.assertEqual(result['citations'],[])
        self.assertNotIn('全部完成',result['answer']);self.assertIn('不足以回答',result['answer'])
    def test_bounded_candidates_fields_and_chain_gaps(self):
        for i in range(205):
            self.record(title='虚构追加'+str(i),day='2026-09-02',note='虚构长说明'*750,
                        related_record_id=1,followup_kind='补充观察')
        evidence,coverage=app.query_evidence('示例甲','数学订正')
        self.assertLessEqual(len(evidence),20)
        self.assertLess(len(json.dumps(evidence,ensure_ascii=False)),18000)
        self.assertIn('200/208',coverage);self.assertIn('候选范围已截断',coverage)
        self.assertIn('字段或上下文已截断',coverage);self.assertIn('订正链未全部纳入',coverage)
        self.assertIn('未检索到不等于历史不存在',coverage)
        self.ask();self.assertLess(len(self.model.calls[-1]['messages'][-1]['content']),20000)
    def test_input_and_model_errors_leave_records_unchanged(self):
        before=self.database()
        for value in [dict(child='未知'),dict(child=[]),dict(question=''),dict(question='x'*1001),dict(question=42)]:
            with self.assertRaises(ValueError): self.ask(**value)
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(family_llm.LLMUnavailable): self.ask()
        for mode in ['error','bad_json','length']:
            self.model.mode=mode
            with self.assertRaises(family_llm.LLMDraftError) as error: self.ask()
            self.assertNotIn('synthetic-api-secret',str(error.exception))
            self.assertNotIn('SYNTHETIC_PRIVATE_RESPONSE',str(error.exception))
        self.assertEqual(self.database(),before)
    def test_family_waiting_and_review_choices_are_in_answer_evidence(self):
        app.save_task(dict(id='T01',status='待跟进',note='虚构恢复'))
        app.family_task_focus.save(app,dict(id='T01',version=0,request_key='synthetic-query-focus',mode='waiting',next_action='核对集合地点',waiting_for='等示例老师确认',review_on='2026-09-10'))
        evidence,coverage=app.query_evidence('示例甲','有哪些事项在等待，下一步是什么？')
        task=next(x for x in evidence if x['id']=='task:T01')
        self.assertIn('等待条件，不应说成现在即可执行',task['detail'])
        self.assertIn('核对集合地点',task['detail'])
        self.assertIn('等示例老师确认',task['detail'])
        self.assertIn('2026-09-10',task['detail'])
        self.assertIn('回看日期不是学校截止时间',task['detail'])

    def test_task_state_priority_before_candidate_limit_and_coverage(self):
        today=app.dt.datetime.now(app.dt.timezone(app.dt.timedelta(hours=8))).date().isoformat()
        lines=[f'| T{i:03} | 示例甲 | 虚构本周旧事项 | 2020-01-01 | 待跟进 | 虚构来源 | 核对 |' for i in range(1,206)]
        lines.extend([
            f'| T206 | 示例甲 | 虚构本周必须跟进 | {today} | 已完成 | 虚构来源 | 复查 |',
            '| T207 | 示例甲 | 虚构不适用事项 | 本周不确定 | 待跟进 | 虚构来源 | 核查 |',
            '| T208 | 示例甲 | 虚构未知日期事项 | 下周某天 | 待核查 | 虚构来源 | 核查 |',
            '| T209 | 示例甲 | 虚构归档事项 | 2020-01-01 | 已归档（旧通知） | 虚构来源 | 留存 |'])
        (app.ROOT/'跟踪台账.md').write_text('\n'.join(lines))
        with app.connect() as c:
            c.executemany('INSERT OR REPLACE INTO task_updates VALUES (?,?,?,?)',
                [(f'T{i:03}','已完成','虚构完成依据','2020-01-01T00:00:00+08:00') for i in range(1,206)]+
                [('T206','进行中','虚构重新打开事项',today+'T08:00:00+08:00'),
                 ('T207','不适用','虚构原因',today+'T08:00:00+08:00')])
        evidence,coverage=app.query_evidence('示例甲','本周还要做什么待办？')
        task_items=[item for item in evidence if item['kind']=='task']
        self.assertEqual(task_items[0]['target_id'],'T206')
        self.assertIn('task:T208',{item['id'] for item in task_items})
        self.assertIn('当前状态：进行中',task_items[0]['detail'])
        unknown=next(item for item in task_items if item['target_id']=='T208')
        self.assertEqual(unknown['day'],'下周某天')
        self.assertIn('候选截断9项',coverage)
        self.assertIn('当前未完成（含待核查）共2项，本次纳入2项、未纳入0项',coverage)
        self.assertIn('当前状态：待跟进',unknown['detail'])
        self.assertIn('原始状态：待核查',unknown['detail'])
        completed,_=app.query_evidence('示例甲','本周哪些事项已完成？')
        self.assertIn('当前状态：已完成',next(item for item in completed if item['kind']=='task')['detail'])
        not_applicable,_=app.query_evidence('示例甲','哪些事项不适用？')
        self.assertEqual(next(item for item in not_applicable if item['kind']=='task')['target_id'],'T207')
        archived,_=app.query_evidence('示例甲','虚构归档事项')
        archive=next(item for item in archived if item['id']=='task:T209')
        self.assertIn('当前状态：已归档',archive['detail'])
        self.assertIn('原始状态：已归档（旧通知）',archive['detail'])
    def test_reading_queries_prioritize_stable_child_current_evidence(self):
        reading=self.reading_award()
        self.reading_award('child-2','ONLY_OTHER_CHILD_READING')
        pending=self.reading_call('reserve',reward='虚构约定活动',cost=1,note='虚构事先约定')
        done=self.reading_call('reserve',reward='虚构已提供活动',cost=1,note='虚构事先约定')
        done=self.reading_call('fulfill',done,note='虚构实际兑现依据')
        self.reading_call('correct_redemption',done,reason='虚构补充兑现说明')
        self.reading_call('reserve',child_id='child-2',reward='ONLY_OTHER_CHILD_REDEMPTION',cost=3,note='虚构约定')
        for i in range(24): self.record(title='虚构旧学习记录'+str(i))
        before=self.database()
        with patch.object(app.family_reading.Store,'snapshot',side_effect=AssertionError('query must not read the whole reading snapshot')):
            result=self.ask(question='阅读作品进展如何，有多少印章，哪些奖励待兑现？')
        self.assertEqual(self.database(),before)
        context=json.loads(self.model.calls[-1]['messages'][-1]['content'])
        self.assertLessEqual(len(context['evidence']),20)
        self.assertTrue(context['evidence'][0]['kind'].startswith('reading'))
        evidence={item['id']:item for item in context['evidence']}
        for key in ['reading:'+reading['id'],'reading_balance:child-1','reading_redemption:'+pending['id']]: self.assertIn(key,evidence)
        self.assertIn('当前状态：已完成',evidence['reading:'+reading['id']]['detail'])
        self.assertIn('家长当前反馈：虚构家长确认',evidence['reading:'+reading['id']]['detail'])
        self.assertIn('作品文字：虚构作品',evidence['reading:'+reading['id']]['detail'])
        self.assertIn('奖项状态：已获得',evidence['reading:'+reading['id']]['detail'])
        balance=evidence['reading_balance:child-1']
        self.assertEqual(balance['target_id'],'child-1')
        for text in ['历史首次获得3枚','待兑现预留1枚','已兑现使用1枚','当前可用1枚']: self.assertIn(text,balance['detail'])
        self.assertIn('当前兑现状态：待兑现',evidence['reading_redemption:'+pending['id']]['detail'])
        wire=json.dumps(context,ensure_ascii=False)
        for secret in ['HISTORY_READING_ONLY','ONLY_OTHER_CHILD','示例乙','child-2','attachments','reading_events']:
            self.assertNotIn(secret,wire)
        self.assertIn('余额汇总该孩子全部奖项和兑现记录',result['coverage'])
        self.assertNotIn('奖励兑付专用记录尚未纳入',result['coverage'])
        # Renaming the profile does not lose stable-ID reading records.
        rules=app.ROOT/'家庭运行规则.md';rules.write_text(rules.read_text().replace('示例甲','示例甲新称呼'))
        self.ask(child='示例甲新称呼',question='阅读印章余额')
        renamed=json.loads(self.model.calls[-1]['messages'][-1]['content'])
        self.assertTrue(all(item['child']=='示例甲新称呼' for item in renamed['evidence']))
        self.assertIn('reading:'+reading['id'],{item['id'] for item in renamed['evidence']})
    def test_reading_fabricated_reference_and_context_truncation(self):
        task=self.reading_award();other=self.reading_award('child-2','ONLY_OTHER_CHILD_READING')
        self.model.mode=dict(answer='伪造跨孩子引用',citation_ids=['reading:'+other['id']])
        with self.assertRaises(family_llm.LLMDraftError): self.ask(question='阅读任务情况')
        self.model.mode='ok'
        self.reading_call('request_more',task,reason='虚构请补充')
        with app.connect() as c:
            c.execute('UPDATE reading_tasks SET work_text=? WHERE id=?',('虚构长作品'*700,task['id']))
            columns=[r['name'] for r in c.execute('PRAGMA table_info(reading_tasks)')]
            original=dict(c.execute('SELECT * FROM reading_tasks WHERE id=?',(task['id'],)).fetchone())
            for i in range(205):
                row=dict(original,id='read-synthetic-extra-'+str(i),updated='2026-09-09T12:00:00+08:00')
                c.execute('INSERT INTO reading_tasks ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row[k] for k in columns))
        result=self.ask(question='阅读作品情况')
        context=json.loads(self.model.calls[-1]['messages'][-1]['content'])
        self.assertLessEqual(len(context['evidence']),20)
        self.assertLess(len(self.model.calls[-1]['messages'][-1]['content']),20000)
        self.assertIn('200/206',result['coverage'])
        self.assertIn('阅读或兑现候选范围已截断',result['coverage'])
        self.assertIn('字段或上下文已截断',result['coverage'])
    def test_care_failure_coverage_and_no_cross_child_llm_function(self):
        (app.DATA/'陪伴建议.json').write_text('{invalid')
        result=self.ask();self.assertIn('陪伴建议读取失败',result['coverage'])
        with self.assertRaises(ValueError):
            family_llm.answer_question('示例甲','问题',[dict(id='record:4',child='示例乙')],'虚构范围')
    def test_http_auth_errors_and_read_only_success(self):
        server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        before=self.database()
        def post(token=app.TOKEN,host='localhost',question='数学订正的进展？'):
            client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            client.request('POST','/api/ask',json.dumps(dict(child='示例甲',question=question)),
                {'Content-Type':'application/json','X-Family-Token':token,'Host':host})
            response=client.getresponse();body=json.loads(response.read());client.close()
            return response.status,body
        try:
            self.assertEqual(post(token='')[0],403);self.assertEqual(post(host='untrusted.invalid')[0],403)
            self.assertEqual(self.model.calls,[])
            status,body=post();self.assertEqual(status,200);self.assertTrue(body['citations'])
            self.assertEqual(post(question='x'*1001)[0],400)
            self.model.mode='error';status,body=post();self.assertEqual(status,503)
            self.assertEqual(set(body),{'error'});self.assertNotIn('synthetic-api-secret',body['error'])
            self.assertEqual(self.database(),before)
        finally: server.shutdown();server.server_close();worker.join()


if __name__=='__main__': unittest.main()

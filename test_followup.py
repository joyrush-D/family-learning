"""Run python3 test_followup.py. Synthetic records in a temporary legacy database."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import app


def record(**changes):
    return dict(child='示例甲', day='2026-09-07', category='学习进展',
                subject='数学', title='虚构学习记录', note='仅测试') | changes


with tempfile.TemporaryDirectory() as tmp:
    app.ROOT=Path(tmp);app.DATA=Path(tmp);app.DB=Path(tmp)/'legacy.sqlite3'
    (app.ROOT/'家庭运行规则.md').write_text(
        '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n'
        '| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
    with sqlite3.connect(app.DB) as c:
        c.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, child TEXT, day TEXT, category TEXT, subject TEXT, title TEXT, note TEXT, source TEXT, score REAL, total REAL, created TEXT)')
        c.execute('INSERT INTO records VALUES (1,?,?,?,?,?,?,?,?,?,?)',
                  ('示例甲','2026-09-07','成绩','数学','虚构原卷','待核对','测试',70,100,'2026-09-07'))
    original=app.snapshot()['records'][0]
    assert original['related_record_id'] is None and original['followup_kind']==''
    assert original['attachments']==[] and original['score']==70
    app.connect().close()  # A second connection must not repeat the migration.
    app.save_record(record(title='虚构订正',related_record_id=1,followup_kind='订正'))
    app.save_record(record(title='虚构复测',related_record_id=2,followup_kind='独立复测'))
    app.save_record(record(child='示例乙'))
    records={r['id']:r for r in app.snapshot()['records']}
    assert records[2]['related_record_id']==1 and records[3]['related_record_id']==2
    assert records[3]['followup_kind']=='独立复测'
    assert records[4]['related_record_id'] is None and records[4]['followup_kind']==''

    for changes in [
        dict(related_record_id=999), dict(related_record_id=4),
        dict(id=2,related_record_id=2), dict(id=1,related_record_id=3),
        dict(id=1,child='示例乙'), dict(id=2,child='示例乙'),
        dict(related_record_id=True), dict(related_record_id=1.0),
        dict(related_record_id='1'), dict(related_record_id=0),
        dict(related_record_id=-1), dict(related_record_id=2**63),
        dict(followup_kind='自动判定已掌握'), dict(followup_kind=None),
    ]:
        try: app.save_record(record(**changes))
        except ValueError: pass
        else: raise AssertionError('invalid relationship accepted: '+repr(changes))
    assert {r['id']:r for r in app.snapshot()['records']}==records
    with app.connect() as c:
        assert c.execute('SELECT count(*) FROM revisions').fetchone()[0]==0

    app.save_record(record(id=2,title='旧客户端只修改标题'))
    edited={r['id']:r for r in app.snapshot()['records']}[2]
    assert edited['related_record_id']==1 and edited['followup_kind']=='订正'
    with app.connect() as c:
        previous=json.loads(c.execute('SELECT previous FROM revisions').fetchone()[0])
        assert previous['related_record_id']==1 and previous['followup_kind']=='订正'
    app.save_record(record(id=2,followup_kind='补充观察'))
    assert {r['id']:r for r in app.snapshot()['records']}[2]['related_record_id']==1
    app.save_record(record(id=2,related_record_id=None,followup_kind=''))
    cleared={r['id']:r for r in app.snapshot()['records']}[2]
    assert cleared['related_record_id'] is None and cleared['followup_kind']==''

print('PASS: legacy migration, followup chain, same-child and cycle guards, old-client edits and revisions')


class CareFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-care-')
        self.old=app.ROOT,app.DATA,app.DB
        app.ROOT=app.DATA=Path(self.tmp.name);app.DB=app.DATA/'test.sqlite3'
        (app.ROOT/'家庭运行规则.md').write_text(
            '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n'
            '| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        today=app.dt.datetime.now(app.dt.timezone(app.dt.timedelta(hours=8))).date()
        self.today=today.isoformat()
        self.before=(today-app.dt.timedelta(days=1)).isoformat()
        self.after=(today+app.dt.timedelta(days=1)).isoformat()
        self.expires=(today+app.dt.timedelta(days=7)).isoformat()
        self.items=[dict(id='synthetic-care-'+str(i),child=child,topic='学习',title='虚构陪伴建议'+str(i),
                         evidence='虚构依据',action='一起交流一个发现',review_on=self.today,expires_on=expires)
                    for i,child,expires in [(1,'示例甲',self.expires),(2,'示例乙',self.expires),(3,'示例甲',self.before)]]
        (app.DATA/'陪伴建议.json').write_text(json.dumps(self.items,ensure_ascii=False))

    def tearDown(self):
        app.ROOT,app.DATA,app.DB=self.old;self.tmp.cleanup()

    def states(self,value):
        (app.DATA/'陪伴提醒状态.json').write_text(json.dumps(value,ensure_ascii=False))

    def database(self):
        with app.connect() as c: return '\n'.join(c.iterdump())

    def test_same_child_current_and_retained_history_and_edit_guards(self):
        source='陪伴建议:synthetic-care-1'
        app.save_record(record(source=source,note='愿意试试'))
        app.save_record(record(source='陪伴建议:synthetic-care-3',note='补充虚构历史反馈'))
        app.save_record(record(id=1,source=source,note='晚些再看，日期待确定'))
        with app.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM revisions').fetchone()[0],1)
        before=self.database()
        for changes in [dict(child='示例乙',source=source),dict(id=1,child='示例乙',source=source),
                        dict(source='陪伴建议:synthetic-missing'),dict(id=1,source='陪伴建议:synthetic-care-2'),
                        dict(source='陪伴建议:')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError): app.save_record(record(**changes))
            self.assertEqual(self.database(),before)

    def test_missing_state_and_pending_keep_compatibility_without_text_inference(self):
        care=app.care_notes();self.assertEqual(care['error'],'')
        self.assertTrue(all(i['review_status']=='' for i in care['items']))
        app.save_record(record(source='陪伴建议:synthetic-care-1',note='暂不考虑'))
        self.assertEqual(app.care_notes(),care)  # Free text is for the routine Agent to review.
        self.states({'synthetic-care-1':{'status':'awaiting_parent_feedback','next_review_on':self.after}})
        pending=app.care_notes()['items'][0]
        self.assertEqual(pending['review_status'],'awaiting_parent_feedback')
        self.assertEqual(pending['review_on'],self.today)

    def test_declined_and_deferred_query_evidence_before_and_on_review_date(self):
        for date,phrase in [(self.after,'尚未到回看日期'),(self.today,'回看日期已到'),(self.before,'回看日期已到')]:
            with self.subTest(date=date):
                self.states({'synthetic-care-1':{'status':'deferred','next_review_on':date},
                             'synthetic-care-3':{'status':'declined'}})
                care=app.care_notes();self.assertEqual(care['error'],'')
                self.assertEqual(care['items'][0]['review_on'],date)
                self.assertEqual(care['items'][0]['expires_on'],self.expires)
                evidence,coverage=app.query_evidence('示例甲','已有陪伴建议反馈如何？')
                mapping={i['id']:i for i in evidence}
                self.assertIn(phrase,mapping['care:synthetic-care-1']['detail'])
                self.assertIn('家长暂不考虑，已停止推荐',mapping['care:synthetic-care-3']['detail'])
                self.assertIn('已过期',mapping['care:synthetic-care-3']['detail'])
                self.assertIn('暂不考虑1条、延期1条',coverage)
                self.assertNotIn('示例乙',json.dumps(evidence,ensure_ascii=False))
        beyond=(app.dt.date.fromisoformat(self.expires)+app.dt.timedelta(days=1)).isoformat()
        self.states({'synthetic-care-1':{'status':'deferred','next_review_on':beyond}})
        self.assertEqual(app.care_notes()['items'][0]['expires_on'],self.expires)

    def test_bad_reminder_state_keeps_suggestions_and_reports_uncertainty(self):
        for invalid in [[],None,{'synthetic-care-1':None},
                        {'synthetic-care-1':{'status':'unknown'}},
                        *({'synthetic-care-1':{'status':'deferred','next_review_on':date}}
                          for date in [None,'明天','2026-02-30','20260909','2026-09-09T00:00:00'])]:
            with self.subTest(invalid=invalid):
                self.states(invalid);care=app.care_notes()
                self.assertEqual(len(care['items']),3);self.assertTrue(care['error'])
                self.assertEqual(care['items'][0]['review_status'],'')
                self.assertEqual(care['items'][0]['review_on'],self.today)
        (app.DATA/'陪伴提醒状态.json').write_text('{broken')
        care=app.care_notes();self.assertEqual(len(care['items']),3);self.assertTrue(care['error'])
        evidence,coverage=app.query_evidence('示例甲','陪伴建议')
        self.assertEqual(sum(i['kind']=='care' for i in evidence),2)
        self.assertIn('提醒状态暂时无法核对',coverage)
        self.assertNotIn('本次不含建议资料',coverage)
        # A malformed sibling status must not erase a valid explicit disposition.
        self.states({'synthetic-care-1':{'status':'declined'},'synthetic-care-2':{'status':'unknown'}})
        self.assertEqual(app.care_notes()['items'][0]['review_status'],'declined')
        (app.DATA/'陪伴建议.json').write_text('{broken')
        before=self.database()
        with self.assertRaises(ValueError): app.save_record(record(source='陪伴建议:synthetic-care-1'))
        self.assertEqual(self.database(),before)


class LearningContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-learning-context-')
        self.old=app.ROOT,app.DATA,app.DB
        app.ROOT=app.DATA=Path(self.tmp.name);app.DB=app.DATA/'legacy.sqlite3'
        (app.ROOT/'家庭运行规则.md').write_text(
            '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n'
            '| child-2 | 示例乙 | 男 | 13岁 | 初一 |\n')
        old=dict(id=1,child='示例甲',day='2024-09-07',category='成绩',subject='数学',title='虚构旧卷',
                 note='虚构旧记录',source='虚构原始来源',score=70,total=100,created='2024-09-07',followup_kind='独立复测')
        with sqlite3.connect(app.DB) as c:
            c.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, child TEXT, day TEXT, category TEXT, subject TEXT, title TEXT, note TEXT, source TEXT, score REAL, total REAL, created TEXT, followup_kind TEXT)')
            c.execute('INSERT INTO records VALUES ('+','.join('?' for _ in old)+')',tuple(old.values()))
            c.execute('CREATE TABLE revisions (id INTEGER PRIMARY KEY, record_id INTEGER, previous TEXT, changed TEXT)')
            c.execute('INSERT INTO revisions VALUES (1,1,?,?)',(json.dumps(old),'2024-09-08'))
        app.connect().close()

    def tearDown(self):
        app.ROOT,app.DATA,app.DB=self.old;self.tmp.cleanup()

    def database(self):
        with app.connect() as c: return '\n'.join(c.iterdump())

    def context(self,ident=1):
        with app.connect() as c: return dict(c.execute('SELECT * FROM records WHERE id=?',(ident,)).fetchone())

    def test_legacy_unknown_history_does_not_infer_independence(self):
        app.connect().close()
        row=self.context()
        self.assertEqual([row[k] for k in ['care_choice','care_review_on','request_key','request_hash']],['','','',''])
        self.assertEqual(row['followup_kind'],'独立复测')
        self.assertEqual([row[k] for k in ['assistance','practice_relation','comparison_note']],['','',''])
        before=self.database();history=app.record_history(1)
        self.assertEqual(history['current']['assistance'],'')
        previous=history['history'][0]['previous']
        self.assertEqual([previous[k] for k in ['care_choice','care_review_on']],[None,None])
        self.assertEqual([previous[k] for k in ['assistance','practice_relation','comparison_note']],[None,None,None])
        evidence,coverage=app.query_evidence('示例甲','复测情况')
        detail=next(r['detail'] for r in evidence if r['id']=='record:1')
        self.assertIn('帮助情况：未记录（不能推定独立）',detail)
        self.assertIn('与直接关联记录的材料关系：未记录（不能推定可比较）',detail)
        self.assertIn('旧的独立复测标签本身不能证明独立完成',coverage)
        self.assertEqual(self.database(),before)

    def test_old_client_preserves_explicit_clear_and_invalid_edit_is_atomic(self):
        values=dict(assistance='少量提示',practice_relation='相近的新题或新片段',comparison_note='虚构同一知识点；难度是否相近待核对')
        app.save_record(record(id=1,**values))
        app.save_record(record(id=1,title='虚构旧客户端更正'))
        self.assertEqual({k:self.context()[k] for k in values},values)
        history=app.record_history(1)
        self.assertEqual({k:history['history'][0]['previous'][k] for k in values},values)
        self.assertEqual(history['history'][-1]['previous']['assistance'],None)
        before=self.database()
        for changes in [dict(assistance='自动推断独立'),dict(assistance=None),dict(assistance=1),
                        dict(practice_relation='可直接比较'),dict(practice_relation=[]),dict(practice_relation=None),
                        dict(comparison_note=None),dict(comparison_note='字'*1001),dict(comparison_note='无\x00效')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                app.save_record(record(id=1,title='不应覆盖',**changes))
            self.assertEqual(self.database(),before)
        app.save_record(record(id=1,assistance=''))
        self.assertEqual(self.context()['assistance'],'')
        self.assertEqual(self.context()['practice_relation'],values['practice_relation'])
        app.save_record(record(id=1,practice_relation='',comparison_note=''))
        self.assertEqual([self.context()[k] for k in values],['','',''])
        history=app.record_history(1)
        self.assertEqual(history['history'][1]['previous']['assistance'],'少量提示')
        # A malformed new field does not erase otherwise-readable old versions.
        with app.connect() as c:
            damaged=dict(history['current'],assistance={'invalid':'type'})
            c.execute('INSERT INTO revisions (record_id,previous,changed) VALUES (1,?,?)',(json.dumps(damaged),'2026-09-08'))
        history=app.record_history(1)
        self.assertEqual(history['unreadable_count'],1)
        self.assertIsNone(history['history'][0]['previous'])
        self.assertIsNotNone(history['history'][-1]['previous'])

    def test_retest_context_survives_query_links_and_same_child_guards(self):
        app.save_record(record(id=1,day='2024-09-07',source='虚构原始来源',assistance='看过讲解或答案',
                               comparison_note='虚构先看过讲解，不能视为独立'))
        for index in range(14):
            app.save_record(record(title='虚构普通观察'+str(index),day='2025-09-07'))
        app.save_record(record(title='只检索这次复测',related_record_id=1,followup_kind='复测',
                               assistance='独立尝试',practice_relation='范围或难度不同',comparison_note='虚构新范围，不能只比分数',
                               source='虚构家长观察来源'))
        app.save_record(record(child='示例乙',title='另一孩子资料不得串入',assistance='逐步帮助'))
        before=self.database()
        with self.assertRaises(ValueError):
            app.save_record(record(child='示例乙',related_record_id=1,followup_kind='复测',assistance='独立尝试'))
        self.assertEqual(self.database(),before)
        evidence,coverage=app.query_evidence('示例甲','只检索这次复测')
        current=next(r for r in evidence if r['title']=='只检索这次复测')
        original=next(r for r in evidence if r['id']=='record:1')
        self.assertIn('帮助情况：独立尝试',current['detail'])
        self.assertIn('与直接关联记录的材料关系：范围或难度不同',current['detail'])
        self.assertIn('可比较条件说明：虚构新范围，不能只比分数',current['detail'])
        self.assertIn('来源：虚构家长观察来源',current['detail'])
        self.assertIn('帮助情况：看过讲解或答案',original['detail'])
        self.assertIn('来源：虚构原始来源',original['detail'])
        self.assertIn('不由分数变化推断掌握或前后可比较',coverage)
        self.assertNotIn('另一孩子资料不得串入',json.dumps(evidence,ensure_ascii=False))
        self.assertEqual(self.context(16)['followup_kind'],'复测')
        self.assertEqual(self.context()['followup_kind'],'独立复测')
        self.assertEqual(self.database(),before)


class CareChoiceTests(unittest.TestCase):
    setUp=CareFeedbackTests.setUp
    tearDown=CareFeedbackTests.tearDown
    database=CareFeedbackTests.database
    states=CareFeedbackTests.states

    def body(self,key='synthetic_choice_request_001',**changes):
        return record(day=self.today,category='家长观察',source='陪伴建议:synthetic-care-1',note='',
                      care_choice='愿意试试',care_review_on='',request_key=key) | changes

    def save(self,body): return app.save_record(body,care_only=True)

    def test_explicit_append_order_plain_edit_and_query_do_not_claim_completion(self):
        self.states({'synthetic-care-1':{'status':'deferred','next_review_on':self.after}})
        first_body=self.body()
        first=self.save(first_body)
        self.assertEqual(first['care']['review_status'],'accepted')
        self.assertEqual(first['care']['review_on'],self.today)
        self.assertEqual(first['care']['expires_on'],self.expires)
        stopped=self.save(self.body('synthetic_choice_request_002',care_choice='暂不考虑'))
        self.assertGreater(stopped['record_id'],first['record_id'])
        edit={key:value for key,value in first_body.items() if key not in ['request_key','care_choice','care_review_on']}
        app.save_record(edit | dict(id=first['record_id'],title='虚构旧标题更正',note='只是更正文字，不重新作出选择'))
        self.assertEqual(app.care_notes()['items'][0]['review_status'],'declined')
        self.assertEqual(app.care_notes()['items'][0]['choice_record_id'],stopped['record_id'])
        history=app.record_history(first['record_id'])
        self.assertEqual(history['current']['care_choice'],'愿意试试')
        self.assertEqual(history['history'][0]['previous']['care_choice'],'愿意试试')
        before=self.database()
        for changes in [dict(care_choice='暂不考虑'),dict(care_choice=''),dict(care_review_on=self.after),
                        dict(child='示例乙',source='陪伴建议:synthetic-care-2'),dict(source='陪伴建议:synthetic-care-3')]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                app.save_record(edit | dict(id=first['record_id']) | changes)
            self.assertEqual(self.database(),before)
        evidence,_=app.query_evidence('示例甲','已有陪伴建议如何安排？')
        detail=next(item['detail'] for item in evidence if item['id']=='care:synthetic-care-1')
        self.assertIn('已停止推荐',detail)
        resumed=self.save(self.body('synthetic_choice_request_003'))
        evidence,_=app.query_evidence('示例甲','已有陪伴建议如何安排？')
        self.assertIn('不表示已执行或已有成效',next(item['detail'] for item in evidence if item['id']=='care:synthetic-care-1'))
        self.assertEqual(resumed['care']['review_on'],self.today)
        self.assertTrue(all(child['energy']==0 for child in app.snapshot()['rewards']['children']))

    def test_replay_conflict_alias_and_current_source_guards(self):
        body=self.body()
        saved=self.save(body)
        replay=self.save(body)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['record_id'],saved['record_id'])
        later=self.save(self.body('synthetic_choice_request_002',care_choice='改天回看',care_review_on=self.after))
        replay=self.save(body)
        self.assertEqual(replay['record']['care_choice'],'愿意试试')
        self.assertEqual(replay['care']['choice_record_id'],later['record_id'])
        before=self.database()
        with self.assertRaises(app.RecordError) as error: self.save(body | dict(note='同一标识换成其他内容'))
        self.assertEqual(error.exception.status,409)
        self.assertTrue(error.exception.request_known)
        self.assertFalse(error.exception.not_saved)
        self.assertEqual(self.database(),before)
        # A profile alias keeps the same stable child in the request fingerprint.
        with app.connect() as c: c.execute('INSERT INTO profile_aliases VALUES (?,?)',('示例旧称','child-1'))
        replay=self.save(body | dict(child='示例旧称'))
        self.assertEqual(replay['record_id'],saved['record_id'])
        before=self.database()
        self.items[0]['child']='示例乙'
        (app.DATA/'陪伴建议.json').write_text(json.dumps(self.items,ensure_ascii=False))
        replay=self.save(body)
        self.assertTrue(replay['replayed'])
        self.assertIsNone(replay['care'])
        self.assertTrue(replay['care_error'])
        self.assertEqual(self.database(),before)
        (app.DATA/'陪伴建议.json').unlink()
        self.assertEqual(self.save(body)['record_id'],saved['record_id'])
        self.assertEqual(self.database(),before)

    def test_dates_source_failure_and_choice_conversion_are_atomic(self):
        app.connect().close()
        before=self.database()
        for changes in [dict(care_choice='自动完成'),dict(care_choice=None),dict(care_choice=[]),
                        dict(care_choice='改天回看',care_review_on=self.today),dict(care_choice='改天回看',care_review_on=self.before),
                        dict(care_choice='改天回看',care_review_on='2026-W37-4'),dict(care_choice='改天回看',care_review_on='2026-02-30'),
                        dict(care_choice='改天回看',care_review_on=''),dict(care_review_on=self.after),
                        dict(source='家长观察'),dict(child='示例乙'),dict(request_key=''),dict(request_key='bad'),
                        dict(category='学习进展'),dict(care_choice='',note='',attachments=[]),dict(id=0)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError): self.save(self.body(**changes))
            self.assertEqual(self.database(),before)
        (app.DATA/'陪伴提醒状态.json').write_text('{broken')
        with self.assertRaises(app.RecordError): self.save(self.body())
        self.assertEqual(self.database(),before)
        self.states({})
        with self.assertRaises(app.RecordError) as invalid:
            self.save(self.body(care_choice='改天回看',care_review_on=self.today))
        self.assertTrue(invalid.exception.not_saved)
        self.assertFalse(invalid.exception.request_known)
        plain=self.save(self.body(care_choice='',note='暂不考虑？这里只是转述，决定未明。'))
        self.assertEqual(plain['care']['review_status'],'')
        edit=self.body(care_choice='暂不考虑') | dict(id=plain['record_id'])
        edit.pop('request_key')
        before=self.database()
        with self.assertRaises(app.RecordError): app.save_record(edit)
        self.assertEqual(self.database(),before)
        expired=self.save(self.body('synthetic_expired_request_001',source='陪伴建议:synthetic-care-3'))
        self.assertEqual(expired['care']['expires_on'],self.before)


if __name__=='__main__': unittest.main()

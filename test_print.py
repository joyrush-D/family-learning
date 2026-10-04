"""Isolated synthetic files and mocked CUPS; never prints anything."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zlib
import family_print as printing
import family_llm
import print_bridge


def png(width=2, height=2, color=6):
    def chunk(kind, body):
        return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    channels={0:1,2:3,4:2,6:4}[color]
    body=(b'\x00'+bytes([30,60,90,255][:channels])*width)*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,color,0,0,0))+chunk(b'IDAT',zlib.compress(body))+chunk(b'IEND',b'')


class HomeworkCauseTests(unittest.TestCase):
    """Fixed synthetic reading receipts test validation, not image/model accuracy."""

    def draft(self, *, review, **changes):
        item=dict(label='虚构甲卷第1题',question='虚构甲卷第1题：2+3=?',student_answer='4',
                  answer=('教师参考：' if review else 'AI自行推导：')+'5',judgment='incorrect',
                  error_reason='卷面作答4与核对答案5不同。',possible_cause='',
                  steps='先独立重算2+3，再对照核对答案。',uncertainty='')
        if review:item['question_kind']='objective'
        item.update(changes)
        raw=dict(items=[item],coverage='仅虚构甲卷第1题，其余未检查。')
        original=json.loads(json.dumps(raw))
        kwargs=dict(review=review)
        if review:
            kwargs.update(reference_documents=[dict(name='synthetic-teacher.txt',text='虚构甲卷第1题：5')],
                          image_labels=['虚构甲卷第1题'])
        with patch.object(family_llm,'_chat_json',return_value=raw) as model:
            draft=family_llm.homework_reference_draft(dict(mime='image/png',data=png()),**kwargs)
        self.assertEqual(model.call_count,1)
        self.assertEqual(raw,original,'validation must not rewrite the transport receipt')
        return draft

    def test_review_preserves_wrong_answer_without_inferred_cause(self):
        for cause in ('','可能重算时发生偏差，须请孩子说明。'):
            with self.subTest(possible_cause=cause):
                draft=self.draft(review=True,possible_cause=cause)
                question=draft['questions'][0]
                self.assertEqual((draft['wrong_items'],draft['unknown_items']),(1,0))
                self.assertEqual(question['judgment'],'incorrect')
                self.assertEqual(question['answer'],'教师参考：5')
                self.assertEqual(question['student_answer'],'4')
                self.assertEqual(question['error_reason'],'卷面作答4与核对答案5不同。')
                self.assertEqual(question['possible_cause'],cause)
                self.assertEqual(question['steps'],'先独立重算2+3，再对照核对答案。')
                self.assertEqual(question['uncertainty'],'')
                self.assertIn('错误依据：'+question['error_reason'],draft['text'])

    def test_print_reference_preserves_wrong_answer_without_inferred_cause(self):
        draft=self.draft(review=False)
        question=draft['questions'][0]
        self.assertEqual((draft['wrong_items'],draft['unknown_items']),(1,0))
        self.assertEqual(question['judgment'],'incorrect')
        self.assertEqual(question['answer'],'AI自行推导：5')
        self.assertEqual(question['error_reason'],'卷面作答4与核对答案5不同。')
        self.assertEqual(question['possible_cause'],'')
        self.assertEqual(question['steps'],'先独立重算2+3，再对照核对答案。')
        self.assertIn('错误依据：'+question['error_reason'],draft['text'])

    def test_wrong_answer_still_requires_observable_evidence(self):
        cases={'missing_answer':dict(student_answer=''),
               'missing_reference':dict(answer=''),
               'reference_conflict':dict(uncertainty='教师参考与可见题面冲突，待核对。'),
               'missing_error_evidence':dict(error_reason='')}
        for review in (False,True):
            for name,changes in cases.items():
                with self.subTest(review=review,missing=name):
                    draft=self.draft(review=review,possible_cause='可能重算时发生偏差，须请孩子说明。',**changes)
                    question=draft['questions'][0]
                    self.assertEqual((draft['wrong_items'],draft['unknown_items']),(0,1))
                    self.assertEqual(question['judgment'],'unknown')
                    self.assertEqual(question['error_reason'],'')
                    self.assertEqual(question['possible_cause'],'')
                    self.assertEqual(question['steps'],'')
                    self.assertTrue(question['uncertainty'])
                    self.assertNotIn('错误依据：',draft['text'])
                    if review and name=='reference_conflict':
                        self.assertEqual(question['answer'],'教师参考：5')


class PrintTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name)
        (self.data/'attachments').mkdir();(self.data/'uploads').mkdir()
        def connect():
            c=sqlite3.connect(self.data/'test.sqlite3');c.row_factory=sqlite3.Row
            c.execute('CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY,name TEXT)')
            return c
        self.connect=connect
        self.store=printing.PrintStore(self.data,connect)
        self.counter=patch.object(self.store,'_page_count',return_value=1);self.counter.start()
        (self.data/'attachments'/'sample.png').write_bytes(png())
        self.source={'type':'attachment','name':'sample.png'}

    def tearDown(self):
        self.counter.stop();self.tmp.cleanup()

    def prepared(self,key='prepare_key_1'):
        return self.store.prepare(self.source,key)

    def job(self,key='print_key_1',**overrides):
        prep=self.prepared()
        obj=dict(preparation_id=prep['id'],pdf_sha256=prep['pdf_sha256'],idempotency_key=key,confirmed=True,printer='Synthetic_Printer',pages='all',copies=1,sides='one-sided',color='monochrome')
        obj.update(overrides)
        return self.store.enqueue(obj)

    def test_original_and_preview_hashes_and_idempotency(self):
        first=self.prepared();second=self.prepared()
        self.assertEqual(first,second)
        pdf,name=self.store.preview(first['id'])
        self.assertEqual(name,'sample.pdf');self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertEqual(hashlib.sha256(pdf).hexdigest(),first['pdf_sha256'])
        self.assertEqual(hashlib.sha256(png()).hexdigest(),first['source_sha256'])
        (self.data/'attachments'/'sample.png').write_bytes(png(3))
        with self.assertRaises(printing.PrintError):self.prepared()
        self.assertNotEqual(self.prepared('prepare_key_2')['id'],first['id'])

    def test_homework_pair_is_two_jobs_and_retry_does_not_reprint(self):
        (self.data/'attachments'/'guide.png').write_bytes(png(3))
        task=dict(id='TASK-1',title='虚构练习')
        request=dict(task_id='TASK-1',request_key='homework_pair_123',question_source=self.source,
                     guide_source=dict(type='attachment',name='guide.png'),guide_text='',
                     question_confirmed=True,guide_confirmed=True,printer='Synthetic_Printer')
        first=self.store.homework_pair(request,task)
        self.assertNotEqual(first['question']['id'],first['guide']['id'])
        self.assertEqual(first,self.store.homework_pair(request,task))
        self.assertEqual(len(self.store.list_jobs()),2)
        with self.assertRaises(printing.PrintError):
            self.store.homework_pair({**request,'guide_source':self.source},task)
        with self.assertRaises(printing.PrintError):
            self.store.homework_pair({**request,'request_key':'homework_pair_other','expected_question_sha256':'0'*64},task)
        self.assertEqual(len(self.store.list_jobs()),2)

    def test_ordered_pages_keep_one_request_and_detect_changed_packet(self):
        (self.data/'attachments'/'page2.png').write_bytes(png(3))
        (self.data/'attachments'/'guide.png').write_bytes(png(4))
        pages=[self.source,dict(type='attachment',name='page2.png')]
        images,digest=self.store.images_for_draft(pages)
        self.assertEqual(digest,printing.packet_sha([image['sha256'] for image in images]))
        request=dict(task_id='TASK-1',request_key='homework_packet_123',question_sources=pages,
                     guide_source=dict(type='attachment',name='guide.png'),guide_text='',
                     expected_question_sha256=digest,question_confirmed=True,guide_confirmed=True,
                     printer='Synthetic_Printer')
        first=self.store.homework_pair(request,dict(id='TASK-1',title='虚构双页练习'))
        self.assertEqual(len(first['questions']),2)
        self.assertEqual(first,self.store.homework_pair(request,dict(id='TASK-1',title='虚构双页练习')))
        self.assertEqual(len(self.store.list_jobs()),3)
        with self.assertRaises(printing.PrintError):
            self.store.homework_pair(request|{'question_sources':list(reversed(pages))},dict(id='TASK-1',title='虚构双页练习'))
        with self.assertRaises(printing.PrintError):
            self.store.homework_pair(request|{'request_key':'homework_packet_changed','question_sources':list(reversed(pages))},dict(id='TASK-1',title='虚构双页练习'))
        self.assertEqual(len(self.store.list_jobs()),3)
        with self.assertRaises(printing.PrintError):self.store.images_for_draft([pages[0],pages[0]])

    def test_prepared_only_reference_and_ordered_packet_can_change_without_rewriting_pdf(self):
        for name,width in [('guide.png',3),('replacement.png',4),('page2.png',5)]:
            (self.data/'attachments'/name).write_bytes(png(width))
        task=dict(id='TASK-1',title='虚构准备恢复')
        guide=dict(type='attachment',name='guide.png');replacement=dict(type='attachment',name='replacement.png')
        page2=dict(type='attachment',name='page2.png')
        for kind in ('guide','packet'):
            with self.subTest(kind=kind):
                request=dict(task_id=task['id'],request_key='synthetic_prepared_only_'+kind,
                    question_sources=[self.source] if kind=='guide' else [self.source,page2],
                    guide_source=guide,guide_text='',question_confirmed=True,guide_confirmed=True,printer='Synthetic_Printer')
                count=len(self.store.list_jobs())
                with self.assertRaises(printing.PrintError) as error:
                    self.store.homework_pair(request,task,before_queue=lambda: (_ for _ in ()).throw(printing.PrintError('Synthetic unlinked','review_source_not_allowed',403)))
                self.assertEqual(error.exception.status,403);self.assertEqual(len(self.store.list_jobs()),count)
                with self.connect() as c: old={r['id']:dict(r) for r in c.execute('SELECT * FROM print_preparations')}
                old_pdf={ident:self.store.preview(ident)[0] for ident in old}
                revised=request|({'guide_source':replacement} if kind=='guide' else {'question_sources':[page2,replacement]})
                jobs=self.store.homework_pair(revised,task)
                self.assertEqual(jobs,self.store.homework_pair(revised,task))
                self.assertEqual(len(self.store.list_jobs()),count+len(revised['question_sources'])+1)
                with self.connect() as c:
                    for ident,row in old.items():
                        self.assertEqual(dict(c.execute('SELECT * FROM print_preparations WHERE id=?',(ident,)).fetchone()),row)
                        self.assertEqual(self.store.preview(ident)[0],old_pdf[ident])

    def test_lost_partial_receipt_keeps_enqueue_roles_when_materials_change(self):
        (self.data/'attachments'/'guide.png').write_bytes(png(3))
        (self.data/'attachments'/'replacement.png').write_bytes(png(4))
        task=dict(id='TASK-1',title='虚构丢回执')
        request=dict(task_id=task['id'],request_key='synthetic_lost_partial',question_sources=[self.source],
            guide_source=dict(type='attachment',name='guide.png'),guide_text='',question_confirmed=True,
            guide_confirmed=True,printer='Synthetic_Printer')
        original=self.store.enqueue
        def lose_receipt(body):
            original(body)
            raise printing.PrintError('Synthetic lost receipt','synthetic_receipt_lost',503)
        with patch.object(self.store,'enqueue',side_effect=lose_receipt),self.assertRaises(printing.PrintError):
            self.store.homework_pair(request,task)
        first=self.store.list_jobs();self.assertEqual(len(first),1)
        replacement=dict(type='attachment',name='replacement.png')
        with self.assertRaises(printing.PrintError) as error:
            self.store.homework_pair(request|dict(question_sources=[replacement]),task)
        self.assertEqual(error.exception.status,409);self.assertEqual(self.store.list_jobs(),first)
        recovered=self.store.homework_pair(request,task)
        self.assertEqual(recovered['question']['id'],first[0]['id']);self.assertEqual(len(self.store.list_jobs()),2)
        with self.assertRaises(printing.PrintError) as error:
            self.store.homework_pair(request|dict(guide_source=replacement),task)
        self.assertEqual(error.exception.status,409);self.assertEqual(len(self.store.list_jobs()),2)
        self.assertEqual(recovered,self.store.homework_pair(request,task))

    def test_matching_legacy_preparations_keep_original_ids_and_enqueue_keys(self):
        (self.data/'attachments'/'guide.png').write_bytes(png(3))
        task=dict(id='TASK-1',title='虚构旧请求')
        request=dict(task_id=task['id'],request_key='synthetic_legacy_pair',question_sources=[self.source],
            guide_source=dict(type='attachment',name='guide.png'),guide_text='',question_confirmed=True,
            guide_confirmed=True,printer='Synthetic_Printer')
        subkey=lambda role:printing._hash((request['request_key']+':'+role).encode())[:32]
        question=self.store.prepare(self.source,subkey('question_prepare'))
        guide=self.store.prepare(request['guide_source'],subkey('guide_prepare'))
        with patch.object(self.store,'_convert',side_effect=AssertionError('legacy preparation must not be reconverted')):
            jobs=self.store.homework_pair(request,task)
            self.assertEqual(jobs['question']['preparation_id'],question['id'])
            self.assertEqual(jobs['guide']['preparation_id'],guide['id'])
            self.assertEqual(jobs,self.store.homework_pair(request,task))
        with self.connect() as c:
            self.assertEqual({r['idem'] for r in c.execute('SELECT idem FROM print_jobs')},
                {subkey('question_enqueue'),subkey('guide_enqueue')})
            self.assertEqual({r['id'] for r in c.execute('SELECT id FROM print_preparations')},{question['id'],guide['id']})

    def test_new_text_reference_retry_is_stable_across_zip_clock_changes(self):
        captured=[]
        def convert(body,name,directory):captured.append(body);return printing.image_pdf(png())
        with patch.object(self.store,'_convert',side_effect=convert):
            with patch.object(printing.zipfile.time,'localtime',return_value=(2026,10,3,1,2,4,5,276,0)):
                first=self.store.prepare_guide('虚构题目','第1题：B','synthetic_stable_text')
            with patch.object(printing.zipfile.time,'localtime',return_value=(2027,10,3,1,2,8,6,276,0)):
                second=self.store.prepare_guide('虚构题目','第1题：B','synthetic_stable_text')
        self.assertEqual(first,second);self.assertEqual(len(captured),1)
        with zipfile.ZipFile(io.BytesIO(captured[0])) as archive:
            self.assertTrue(all(info.date_time==(1980,1,1,0,0,0) for info in archive.infolist()))

    def test_homework_pair_refuses_unreviewed_reference(self):
        request=dict(task_id='TASK-1',request_key='homework_pair_456',question_source=self.source,
                     guide_source=None,guide_text='',question_confirmed=True,guide_confirmed=False,
                     printer='Synthetic_Printer')
        with self.assertRaises(printing.PrintError):
            self.store.homework_pair(request,dict(id='TASK-1',title='虚构练习'))
        self.assertEqual(self.store.list_jobs(),[])

    def test_homework_reference_draft_stays_reviewable(self):
        item=dict(label='第1题',question='虚构题面',student_answer='C',answer='B',judgment='incorrect',
                  error_reason='题干问未提及，C在原文中出现。',possible_cause='可能漏看否定词，需请孩子说明。',
                  steps='先圈出否定词，再逐项找原文依据。',uncertainty='')
        result=dict(items=[item,dict(item,label='第2题',student_answer='',judgment='unknown',
                                     error_reason='',possible_cause='',uncertainty='卷面未见作答')],coverage='仅此一页')
        with patch.object(family_llm,'_chat_json',return_value=result):
            draft=family_llm.homework_reference_draft(dict(mime='image/png',data=png()))
        self.assertIn('待核对',draft['text']);self.assertIn('第1题',draft['text']);self.assertIn('可能漏看否定词',draft['text'])
        self.assertIn('第2题',draft['text']);self.assertIn('未判定',draft['text'])
        self.assertEqual((draft['wrong_items'],draft['unknown_items']),(1,1))
        with patch.object(family_llm,'_model_image',return_value=dict(mime='image/jpeg',data=b'preview')) as preview, patch.object(family_llm,'_chat_json',return_value=result) as chat:
            family_llm.homework_reference_draft(dict(mime='image/png',data=png()))
        preview.assert_called_once()
        self.assertIn('data:image/jpeg;base64,',chat.call_args.args[0][1]['content'][2]['image_url']['url'])
        with patch.object(family_llm,'_model_image',return_value=dict(mime='image/jpeg',data=b'preview')), patch.object(family_llm,'_chat_json',return_value=result) as chat:
            family_llm.homework_reference_draft([dict(mime='image/png',data=png()),dict(mime='image/png',data=png(3))])
        self.assertEqual(sum(part['type']=='image_url' for part in chat.call_args.args[0][1]['content']),2)
        with patch.object(family_llm,'_chat_json',return_value={'items':[dict(result['items'][0],answer='错\x00误')],'coverage':'仅此一页'}),self.assertRaises(family_llm.LLMDraftError):
            family_llm.homework_reference_draft(dict(mime='image/png',data=png()))
        for conflict in (dict(item,student_answer=''),dict(item,judgment='unknown'),dict(item,uncertainty='下一页选项缺失')):
            with patch.object(family_llm,'_chat_json',return_value={'items':[conflict],'coverage':'仅此一页'}):
                draft=family_llm.homework_reference_draft(dict(mime='image/png',data=png()))
            self.assertEqual((draft['wrong_items'],draft['unknown_items']),(0,1))
            self.assertIn('未判定',draft['text'])
            self.assertNotIn('错误依据：',draft['text'])
            if conflict['uncertainty']=='下一页选项缺失':self.assertIn('参考答案：待核对',draft['text'])

    def test_answer_review_keeps_five_images_together_without_expanding_print_packets(self):
        sources=[]
        for n in range(8):
            name='synthetic-page-%d.png'%n
            (self.data/'attachments'/name).write_bytes(png(n+2))
            sources.append(dict(type='attachment',name=name))
        with self.assertRaises(printing.PrintError): self.store.images_for_draft(sources[:5])
        images,fingerprint=self.store.images_for_draft(sources,limit=family_llm.MAX_HOMEWORK_REVIEW_IMAGES)
        self.assertEqual(len(images),8)
        self.assertEqual(fingerprint,printing.packet_sha([image['sha256'] for image in images]))
        with self.assertRaises(printing.PrintError):self.store.images_for_draft(sources+[sources[0]],limit=8)
        with self.assertRaises(printing.PrintError):self.store.images_for_draft([sources[0],sources[0]],limit=8)
        item=dict(label='第1题',question='虚构题面',student_answer='B',answer='B',judgment='correct',question_kind='objective',
                  error_reason='',possible_cause='',steps='',uncertainty='')
        with patch.object(family_llm,'_chat_json',return_value=dict(items=[item],coverage='仅第1题，其余未核对')) as chat:
            draft=family_llm.homework_reference_draft([dict(mime=i['mime'],data=i['data']) for i in images],review=True)
        self.assertEqual(sum(p['type']=='image_url' for p in chat.call_args.args[0][1]['content']),8)
        self.assertIn('其余未核对',draft['coverage'])
        with patch.object(family_llm,'_chat_json',side_effect=AssertionError('invalid input must not call a model')):
            for args in (dict(images=images),dict(images=images+[images[0]],review=True)):
                # Only mime/data are part of the model input, not the internal file fingerprint.
                args['images']=[dict(mime=i['mime'],data=i['data']) for i in args['images']]
                with self.assertRaises(ValueError):family_llm.homework_reference_draft(**args)

    def test_pdf_tampering_prevents_confirmation(self):
        prep=self.prepared();(self.data/'print'/(prep['id']+'.pdf')).write_bytes(b'%PDF-replaced')
        with self.assertRaises(printing.PrintError):self.job()
        self.assertEqual(self.store.list_jobs(),[])

    def test_attachment_path_and_url_rejected(self):
        for source in [{'type':'attachment','name':'../other.pdf'},{'type':'attachment','name':'/etc/passwd'},{'type':'url','url':'https://example.com/a.pdf'},{'type':'attachment','name':'sample.png','path':'/etc/passwd'}]:
            with self.subTest(source=source),self.assertRaises(printing.PrintError):self.store.prepare(source,'prepare_key_a')
        (self.data/'attachments'/'link.png').symlink_to(self.data/'attachments'/'sample.png')
        with self.assertRaises(printing.PrintError):self.store.prepare({'type':'attachment','name':'link.png'},'prepare_key_a')

    def test_upload_must_exist_in_database(self):
        ident='a'*32;(self.data/'uploads'/ident).write_bytes(png())
        with self.assertRaises(printing.PrintError):self.store.prepare({'type':'upload','id':ident},'prepare_key_a')
        with self.connect() as c:c.execute('INSERT INTO uploads VALUES (?,?)',(ident,'virtual.png'))
        self.assertEqual(self.store.prepare({'type':'upload','id':ident},'prepare_key_a')['name'],'virtual.png')

    def test_source_limit_and_conversion_fallback(self):
        with patch.object(printing,'MAX_SOURCE',8),self.assertRaises(printing.PrintError):self.prepared()
        (self.data/'attachments'/'office.docx').write_bytes(b'PK\x03\x04')
        with patch.object(self.store,'soffice',None),self.assertRaises(printing.PrintError) as error:
            self.store.prepare({'type':'attachment','name':'office.docx'},'prepare_office')
        self.assertEqual(error.exception.code,'preview_unavailable')
        self.assertFalse(list((self.data/'print').glob('.prepare-*')))

    def test_page_and_copy_limits(self):
        self.assertEqual(printing.page_selection('3,1-2,2',5),('1-3',3))
        for pages in ['0','-1','1-0','2-1','1,','1-99999999','1;2','1 2','01','all,1',None,[]]:
            with self.subTest(pages=pages),self.assertRaises(printing.PrintError):printing.page_selection(pages,5)
        for copies in [True,0,11,1.5,'2']:
            with self.subTest(copies=copies),self.assertRaises(printing.PrintError):self.job(copies=copies)
        for options in [dict(confirmed=False),dict(printer='-x'),dict(printer=''),dict(sides=[]),dict(color='invalid'),dict(pages='2')]:
            with self.subTest(options=options),self.assertRaises(printing.PrintError):self.job(**options)

    def test_confirm_idempotency_and_conflict(self):
        first=self.job();self.assertEqual(first,self.job())
        with self.assertRaises(printing.PrintError):self.job(copies=2)
        self.assertEqual(len(self.store.list_jobs()),1)
        self.assertNotIn('claim_token',first)

    def test_claim_not_requeued_after_offline_and_reports(self):
        job=self.job();claim=self.store.claim('synthetic-bridge','Synthetic_Printer','claim_key_1')
        self.assertEqual(claim,self.store.claim('synthetic-bridge','Synthetic_Printer','claim_key_1'))
        self.assertIsNone(self.store.claim('synthetic-bridge','Synthetic_Printer','claim_key_2'))
        with self.assertRaises(printing.PrintError):self.store.cancel(job['id'])
        with self.assertRaises(printing.PrintError):self.store.claimed_pdf(job['id'],'wrong')
        for invalid in ['无效凭据', None, []]:
            with self.assertRaises(printing.PrintError) as error:self.store.claimed_pdf(job['id'],invalid)
            self.assertEqual(error.exception.status,403)
            with self.assertRaises(printing.PrintError) as error:self.store.report(job['id'],invalid,'failed')
            self.assertEqual(error.exception.status,403)
        with self.assertRaises(printing.PrintError):self.store.report(job['id'],claim['claim_token'],'received','Synthetic_Printer-7')
        self.store.report(job['id'],claim['claim_token'],'submitted','Synthetic_Printer-7')
        self.store.report(job['id'],claim['claim_token'],'spooler_completed','Synthetic_Printer-7')
        self.assertEqual(self.store.list_jobs()[0]['status'],'spooler_completed')
        self.store.confirm_received(job['id'],'Synthetic parent confirmed paper collected')
        # Retried report may acknowledge, but cannot regress a parent's confirmation.
        result=self.store.report(job['id'],claim['claim_token'],'submitted','Synthetic_Printer-7')
        self.assertEqual(result['status'],'received')

    def test_unknown_submission_stays_uncertain(self):
        job=self.job();claim=self.store.claim('synthetic-bridge','Synthetic_Printer','claim_key_1')
        self.store.report(job['id'],claim['claim_token'],'uncertain',note='Synthetic timeout')
        self.assertIsNone(self.store.claim('synthetic-bridge','Synthetic_Printer','claim_key_2'))
        with self.assertRaises(printing.PrintError):self.store.report(job['id'],claim['claim_token'],'submitted','Synthetic_Printer-8')

    def test_queued_cancel_is_idempotent(self):
        job=self.job();self.store.cancel(job['id']);self.store.cancel(job['id'])
        self.assertIsNone(self.store.claim('synthetic-bridge','Synthetic_Printer','claim_key_1'))

    def test_png_checksum_and_pixels(self):
        self.assertTrue(printing.image_pdf(png()).startswith(b'%PDF-'))
        broken=bytearray(png());broken[30]^=1
        with self.assertRaises(printing.PrintError):printing.image_pdf(bytes(broken))
        with self.assertRaises(printing.PrintError):printing.image_pdf(b'\xff\xd8\xff\xd9')

    @unittest.skipUnless(shutil.which('pdfinfo'),'pdfinfo unavailable')
    def test_real_pdf_page_count_of_synthetic_image(self):
        self.counter.stop()
        prep=self.prepared();self.assertEqual(prep['page_count'],1)
        self.counter.start()


class BridgeTests(unittest.TestCase):
    prepared=PrintTests.prepared
    job=PrintTests.job

    def setUp(self):
        PrintTests.setUp(self)
        self.bridge=print_bridge.Bridge('http://127.0.0.1:18765','x'*32,'Synthetic_Printer',self.data/'bridge')
        self.sent=[]
        def request(path,body=None,claim=None,pdf=False):
            if path.endswith('/claim'):return {'job':self.store.claim(body['bridge_id'],body['printer'],body['request_key'])}
            if '/pdf/' in path:return self.store.claimed_pdf(path.rsplit('/',1)[-1],claim)[0]
            self.sent.append(body)
            return {'job':self.store.report(body['job_id'],body['claim_token'],body['status'],body['cups_job_id'],body['note'])}
        self.bridge.request=request
        self.configured=patch.object(self.bridge,'_configured',return_value=True);self.configured.start()

    def tearDown(self):
        self.configured.stop();self.bridge.close();PrintTests.tearDown(self)

    def test_bridge_success_does_not_mean_physical_completion(self):
        self.job()
        response=subprocess.CompletedProcess([],0,b'request id is Synthetic_Printer-12 (1 file(s))',b'')
        with patch.object(print_bridge.subprocess,'run',return_value=response) as run:
            self.assertEqual(self.bridge.run_once(),'submitted')
            self.assertEqual(run.call_count,1)
            self.assertIn('sides=one-sided',run.call_args.args[0])
            self.assertIn('media=A4',run.call_args.args[0])
            self.assertIn('fit-to-page',run.call_args.args[0])
            with patch.object(print_bridge,'cups_state',return_value=9):
                self.assertEqual(self.bridge.run_once(),'spooler_completed')
            self.assertEqual(run.call_count,1)
        self.assertEqual(self.store.list_jobs()[0]['status'],'spooler_completed')

    def test_timeout_never_reprints(self):
        self.job()
        with patch.object(print_bridge.subprocess,'run',side_effect=subprocess.TimeoutExpired('lp',30)) as run:
            self.assertEqual(self.bridge.run_once(),'uncertain')
            self.assertEqual(self.bridge.run_once(),'idle')
            self.assertEqual(run.call_count,1)

    def test_localized_cups_output_uses_queue_identifier(self):
        self.job()
        response=subprocess.CompletedProcess([],0,'请求标识为 Synthetic_Printer-12（1 个文件）'.encode(),b'')
        with patch.object(print_bridge.subprocess,'run',return_value=response):
            self.assertEqual(self.bridge.run_once(),'submitted')
        self.assertEqual(self.store.list_jobs()[0]['cups_job_id'],'Synthetic_Printer-12')
        for text in ['Other_Printer-12','Other_Synthetic_Printer-12','Synthetic_Printer-12-x','Synthetic_Printer-12 Synthetic_Printer-13','Synthetic_Printer-0']:
            self.assertIsNone(print_bridge.cups_submission_id(text.encode(),'Synthetic_Printer'))
        for code in [0,1]:
            response=subprocess.CompletedProcess([],code,'打印机Synthetic_Printer闲置'.encode(),b'')
            with patch.object(print_bridge.subprocess,'run',return_value=response) as run:
                self.assertEqual(print_bridge.Bridge._configured(self.bridge),code==0)
                self.assertEqual(run.call_args.args[0],['/usr/bin/lpstat','-h','localhost','-p','Synthetic_Printer'])

    def test_crash_window_never_reprints(self):
        self.job();job=self.store.claim('local-family-print','Synthetic_Printer','claim_before_crash')
        self.bridge._save(job,'submitting')
        with patch.object(print_bridge.subprocess,'run') as run:
            self.assertEqual(self.bridge.run_once(),'uncertain');run.assert_not_called()

    def test_offline_keeps_confirmed_job_queued(self):
        self.job()
        with patch.object(self.bridge,'_configured',return_value=False):self.assertEqual(self.bridge.run_once(),'printer_unavailable')
        self.assertEqual(self.store.list_jobs()[0]['status'],'queued')

    def test_bridge_rejects_nonloopback_and_redirects(self):
        for url in ['https://example.com','http://127.0.0.1@example.com','http://127.0.0.1/path','file:///tmp']:
            with self.assertRaises(printing.PrintError):print_bridge.Bridge(url,'x'*32,'Synthetic_Printer',self.data/'bad')
        self.assertIsNone(print_bridge.NoRedirect().redirect_request(None,None,302,'',{},'http://example.com'))

    def test_parallel_bridge_rejected(self):
        with self.assertRaises(printing.PrintError):
            print_bridge.Bridge('http://127.0.0.1:18765','x'*32,'Synthetic_Printer',self.data/'bridge')

    def test_lost_submission_ack_never_resubmits(self):
        self.job();original=self.bridge._report
        response=subprocess.CompletedProcess([],0,b'request id is Synthetic_Printer-12 (1 file(s))',b'')
        def lose_ack(*args,**kwargs):
            original(*args,**kwargs)
            raise printing.PrintError('Synthetic lost acknowledgement')
        with patch.object(print_bridge.subprocess,'run',return_value=response) as run:
            with patch.object(self.bridge,'_report',side_effect=lose_ack),self.assertRaises(printing.PrintError):self.bridge.run_once()
            with patch.object(print_bridge,'cups_state',return_value=None):self.assertEqual(self.bridge.run_once(),'submitted')
            self.assertEqual(run.call_count,1)

    def test_ipp_reads_exact_job_state(self):
        for state in [3,5,7,8,9]:
            payload=b'\x01\x01\x00\x00\x00\x00\x00\x01\x02\x23\x00\x09job-state\x00\x04'+struct.pack('>I',state)+b'\x03'
            with patch.object(print_bridge.http.client,'HTTPConnection') as connection:
                response=connection.return_value.getresponse.return_value
                response.status=200;response.read.return_value=payload
                self.assertEqual(print_bridge.cups_state('Synthetic_Printer-12'),state)
                connection.assert_called_once_with('127.0.0.1',631,timeout=10)
                request=connection.return_value.request.call_args.args
                self.assertEqual(request[2][2:4],b'\x00\x09')
                self.assertIn(b'ipp://localhost/jobs/12',request[2])


import io
import sys
import time
import warnings
import zipfile

FAKE = """#!%s
import json, os, sys, time
mode, log, pdf = %r, %r, %r
args = sys.argv[1:]; outdir = args[args.index('--outdir') + 1]
xcu = os.path.join(args[0].split('file://', 1)[1], 'user', 'registrymodifications.xcu')
json.dump(dict(argv=args, outdir=outdir, xcu=open(xcu).read() if os.path.exists(xcu) else '', source=open(args[-1], 'rb').read(2).decode('latin-1')), open(log, 'w'))
if mode == 'sleep': time.sleep(10)
elif mode == 'fail': sys.exit(3)
elif mode == 'text': open(os.path.join(outdir, 'source.pdf'), 'wb').write(b'not a pdf')
elif mode == 'big': open(os.path.join(outdir, 'source.pdf'), 'wb').write(b'%%PDF-1.4\\n' + b'0' * 9000)
elif mode == 'ok': open(os.path.join(outdir, 'source.pdf'), 'wb').write(open(pdf, 'rb').read())
"""


def office_zip(extra=(),method=zipfile.ZIP_DEFLATED):
    out=io.BytesIO()
    with warnings.catch_warnings(),zipfile.ZipFile(out,'w',method) as z:
        warnings.simplefilter('ignore')  # A duplicate member is written on purpose.
        for name,text in [('[Content_Types].xml','<Types/>'),('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>'),('_rels/.rels','<Relationships/>'),*extra]:z.writestr(name,text)
    return out.getvalue()


class OfficeConversionTests(unittest.TestCase):
    """The shared Office->PDF path keeps the print contract; soffice is a synthetic script, never LibreOffice."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name).resolve()
        (self.data/'attachments').mkdir();(self.data/'uploads').mkdir()
        self.pdf=printing.image_pdf(png());(self.data/'expected.pdf').write_bytes(self.pdf)
        (self.data/'attachments'/'office.docx').write_bytes(office_zip())
        def connect():
            c=sqlite3.connect(self.data/'test.sqlite3');c.execute('CREATE TABLE IF NOT EXISTS uploads (id TEXT PRIMARY KEY,name TEXT)');return c
        self.store=printing.PrintStore(self.data,connect,soffice=str(self.fake('ok')))
        patch.object(self.store,'_page_count',return_value=1).start();self.addCleanup(patch.stopall)

    def fake(self,mode):
        path=self.data/('fake-%s.py'%mode);path.write_text(FAKE%(sys.executable,mode,str(self.data/(mode+'.json')),str(self.data/'expected.pdf')));path.chmod(0o755);return path

    def prepare(self,key):
        return self.store.prepare({'type':'attachment','name':'office.docx'},key)

    def test_shared_conversion_keeps_print_contract(self):
        body=self.prepare('office_ok');self.assertEqual(body['pdf_sha256'],hashlib.sha256(self.pdf).hexdigest())
        log=json.loads((self.data/'ok.json').read_text())
        self.assertEqual(log['argv'][1:5],['--headless','--convert-to','pdf','--outdir']);self.assertTrue(log['argv'][0].startswith('-env:UserInstallation=file:///'))
        self.assertEqual((Path(log['argv'][-1]).name,log['source']),('source.docx','PK'));self.assertIn('MacroSecurityLevel',log['xcu']);self.assertIn('<value>3</value>',log['xcu'])
        self.assertFalse(list(self.data.glob('print/.prepare-*')))
        for mode,message in (('fail','Office转换未生成PDF'),('none','Office转换未生成PDF'),('text','预览PDF内容不正确')):
            with patch.object(self.store,'soffice',str(self.fake(mode))),self.assertRaises(printing.PrintError) as error:self.prepare('office_'+mode)
            self.assertIn(message,str(error.exception),mode)
        with patch.object(self.store,'soffice',str(self.fake('sleep'))),patch.object(printing,'OFFICE_TIMEOUT',1),self.assertRaises(printing.PrintError) as error:self.prepare('office_sleep')
        self.assertEqual((error.exception.code,error.exception.status),('preview_unavailable',503));self.assertIn('Office转换失败',str(error.exception))
        self.assertFalse(list(self.data.glob('print/.prepare-*')))

    def test_office_check_refuses_external_macro_and_traversal_for_every_caller(self):
        cases=(('external',[('word/_rels/document.xml.rels','<Relationships><Relationship Id="r1" Type="t" Target="https://example.invalid" TargetMode="External"/></Relationships>')],'external'),
               ('macro',[('word/vbaProject.bin','x')],'unsupported'),('traversal',[('../x.xml','<a/>')],'unsupported'),
               ('duplicate',[('word/document.xml','<b/>')],'unreadable'),('entity',[('word/_rels/x.rels','<!DOCTYPE d [<!ENTITY a "x">]><r/>')],'unreadable'),
               ('entries',[('p%d.xml'%i,'<a/>') for i in range(3)],'too_large'))
        for name,members,reason in cases:
            with self.subTest(name),self.assertRaises(printing.OfficeError) as error:
                printing.office_check(office_zip(members),dict(printing.OFFICE_LIMITS,entries=4) if name=='entries' else printing.OFFICE_LIMITS)
            self.assertEqual(error.exception.reason,reason,name)
        with self.assertRaises(printing.OfficeError) as error:printing.office_check(b'\xd0\xcf\x11\xe0 not a zip',printing.OFFICE_LIMITS)
        self.assertEqual(error.exception.reason,'unreadable')
        names,parts=printing.office_check(office_zip(),printing.OFFICE_LIMITS);self.assertEqual((len(names),list(parts)),(3,['_rels/.rels']))
        (self.data/'attachments'/'office.docx').write_bytes(office_zip(cases[0][1]))
        with self.assertRaises(printing.PrintError) as error:self.prepare('office_external')
        self.assertIn('含外部资源',str(error.exception));self.assertFalse((self.data/'ok.json').exists())

    def test_office_check_streams_every_member_so_a_bad_crc_never_reaches_soffice(self):
        body=office_zip([('word/media/image1.png',b'\x89PNG\r\n\x1a\n'+b'X'*10000)],zipfile.ZIP_STORED)
        self.assertEqual(printing.office_check(body,printing.OFFICE_LIMITS)[0][-1],'word/media/image1.png')
        with zipfile.ZipFile(io.BytesIO(body)) as z:info=z.getinfo('word/media/image1.png')
        n,x=struct.unpack('<HH',body[info.header_offset+26:info.header_offset+30]);corrupt=bytearray(body);corrupt[info.header_offset+30+n+x+9000]^=1;corrupt=bytes(corrupt)
        with self.assertRaises(printing.OfficeError) as error:printing.office_check(corrupt,printing.OFFICE_LIMITS)
        self.assertEqual(error.exception.reason,'unreadable')
        (self.data/'attachments'/'office.docx').write_bytes(corrupt)
        with self.assertRaises(printing.PrintError) as error:self.prepare('office_crc')
        self.assertIn('Office内容无法读取',str(error.exception));self.assertFalse((self.data/'ok.json').exists())

    def test_office_convert_keeps_preparation_and_output_reading_inside_one_timeout(self):
        with tempfile.TemporaryDirectory() as d,self.assertRaises(printing.OfficeError) as error:
            printing.office_convert(office_zip(),'.docx',Path(d).resolve(),str(self.fake('ok')),timeout=0,limit=printing.MAX_PDF,read=printing._read_file)
        self.assertEqual(error.exception.reason,'timeout');self.assertFalse((self.data/'ok.json').exists())  # No process starts on a spent budget.
        clock=time.monotonic;offset=[0]
        def slow_read(path,limit):offset[0]=61;return printing._read_file(path,limit)
        with tempfile.TemporaryDirectory() as d,patch.object(printing.time,'monotonic',side_effect=lambda:clock()+offset[0]),self.assertRaises(printing.OfficeError) as error:
            printing.office_convert(office_zip(),'.docx',Path(d).resolve(),str(self.fake('ok')),timeout=60,limit=printing.MAX_PDF,read=slow_read)
        self.assertEqual(error.exception.reason,'timeout');self.assertTrue((self.data/'ok.json').exists())


if __name__ == '__main__':
    unittest.main()

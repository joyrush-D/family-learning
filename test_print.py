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
import print_bridge


def png(width=2, height=2, color=6):
    def chunk(kind, body):
        return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    channels={0:1,2:3,4:2,6:4}[color]
    body=(b'\x00'+bytes([30,60,90,255][:channels])*width)*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,color,0,0,0))+chunk(b'IDAT',zlib.compress(body))+chunk(b'IEND',b'')


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


if __name__=='__main__':unittest.main()

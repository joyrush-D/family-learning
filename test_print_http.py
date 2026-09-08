"""Isolated HTTP checks with fictional data; never invokes a real printer."""
import base64
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import app


PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
BRIDGE_TOKEN='synthetic-bridge-token-only-for-tests-12345'
PRINTER=dict(name='Synthetic_Printer',label='虚构打印机',color=False,duplex=False)


class PrintHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name);data=root/'private';data.mkdir()
        (root/'家庭运行规则.md').write_text('| child-example | 示例甲 | 男 | 10岁 | 四年级 |\n')
        (data/'attachments').mkdir();(data/'attachments'/'synthetic.png').write_bytes(PNG)
        self.paths=patch.multiple(app,ROOT=root,DATA=data,DB=data/'test.sqlite3');self.paths.start()
        self.environment=patch.dict(app.os.environ,{'FAMILY_HOST':'family.example.invalid',
            'FAMILY_USER':'parent@example.invalid','FAMILY_PRINT_BRIDGE_TOKEN':BRIDGE_TOKEN})
        self.environment.start()
        self.pages=patch.object(app.family_print.PrintStore,'_page_count',return_value=1);self.pages.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.parent={'X-Family-Token':app.TOKEN}
        self.bridge={'Authorization':'Bearer '+BRIDGE_TOKEN}
        self.source=dict(type='attachment',name='synthetic.png')

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
        self.pages.stop();self.environment.stop();self.paths.stop();self.temp.cleanup()

    def request(self,method,path,obj=None,headers=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        try:
            conn.request(method,path,json.dumps(obj).encode() if obj is not None else None,headers or {})
            response=conn.getresponse()
            return response.status,dict(response.getheaders()),response.read()
        finally: conn.close()

    def post(self,path,obj,headers=None):
        return self.request('POST',path,obj,self.parent if headers is None else headers)

    def config(self,printers=None):
        (app.DATA/'打印机配置.json').write_text(json.dumps({'printers':[PRINTER] if printers is None else printers}))

    def prepared(self):
        status,_,body=self.post('/api/print/prepare',dict(source=self.source,idempotency_key='synthetic_prepare'))
        self.assertEqual(status,200,body)
        return json.loads(body)['preparation']

    def options(self,prep=None,**extra):
        prep=prep or self.prepared()
        return dict(preparation_id=prep['id'],pdf_sha256=prep['pdf_sha256'],
                    idempotency_key='synthetic_enqueue',confirmed=True,printer=PRINTER['name'],
                    copies=1,pages='all',sides='one-sided',color='monochrome')|extra

    def queued(self):
        self.config()
        status,_,body=self.post('/api/print/enqueue',self.options())
        self.assertEqual(status,200,body)
        return json.loads(body)['job']

    def test_config_is_strict_and_never_claims_online(self):
        state=app.snapshot()
        self.assertEqual(state['printing'],dict(printers=[],error='',jobs=[]))
        self.assertEqual(state['rewards']['children'][0]['energy'],0)
        self.config();self.assertEqual(app.snapshot()['printing']['printers'],[PRINTER])
        malformed=['{',json.dumps({'printers':[PRINTER],'online':True}),
            json.dumps({'printers':[PRINTER,PRINTER]}),json.dumps({'printers':[PRINTER|{'color':1}]}),
            json.dumps({'printers':[PRINTER|{'duplex':'true'}]}),json.dumps({'printers':[PRINTER|{'name':'-bad'}]}),
            json.dumps({'printers':[PRINTER|{'label':'bad\nlabel'}]}),' {"printers":[],"printers":[]}']
        for raw in malformed:
            (app.DATA/'打印机配置.json').write_text(raw)
            printing=app.snapshot()['printing']
            self.assertEqual(printing['printers'],[])
            self.assertTrue(printing['error'])
            self.assertNotIn('online',printing)
            self.assertEqual(self.post('/api/print/enqueue',self.options())[0],503)
        app.save_record(dict(child='示例甲',day='2000-01-01',category='学习进展',
                             title='虚构记录',source='孩子自述'))
        self.assertEqual(app.snapshot()['rewards']['children'][0]['energy'],10)

    def test_parent_auth_prepare_idempotency_and_pdf_headers(self):
        body=dict(source=self.source,idempotency_key='synthetic_prepare')
        for headers in [{},{'X-Family-Token':'wrong'},self.parent|{'Host':'untrusted.invalid'}]:
            self.assertEqual(self.post('/api/print/prepare',body,headers)[0],403)
        prep=self.prepared();self.assertEqual(prep,self.prepared())
        status,headers,pdf=self.request('GET',prep['preview_url'])
        self.assertEqual(status,200)
        self.assertEqual(headers['Content-Type'],'application/pdf')
        self.assertTrue(headers['Content-Disposition'].startswith('inline;'))
        self.assertEqual(headers['X-Frame-Options'],'SAMEORIGIN')
        self.assertIn("frame-ancestors 'self'",headers['Content-Security-Policy'])
        self.assertEqual(hashlib.sha256(pdf).hexdigest(),prep['pdf_sha256'])
        self.assertEqual(hashlib.sha256(PNG).hexdigest(),prep['source_sha256'])
        self.assertTrue((app.DATA/'print'/(prep['id']+'.pdf')).is_file())
        for path in [prep['preview_url'],'/api/state','/api/print/jobs']:
            self.assertEqual(self.request('GET',path,headers={'Host':'family.example.invalid'})[0],403)
            authorized={'Host':'family.example.invalid','Tailscale-User-Login':'parent@example.invalid'}
            self.assertEqual(self.request('GET',path,headers=authorized)[0],200)
        for path in ['/api/state','/api/print/jobs']:
            self.assertEqual(self.request('GET',path)[1]['X-Frame-Options'],'DENY')
        for source in [dict(type='url',url='https://example.invalid/file.pdf'),dict(type='attachment',name='../test.sqlite3')]:
            self.assertEqual(self.post('/api/print/prepare',body|{'source':source})[0],400)
        self.assertEqual(self.request('GET','/api/print/preview/../test.sqlite3')[0],404)
        (app.DATA/'print'/(prep['id']+'.pdf')).write_bytes(b'%PDF-synthetic-tampering')
        self.assertEqual(self.request('GET',prep['preview_url'])[0],409)

    def test_confirmed_hash_authorized_capabilities_and_repeat_clicks(self):
        options=self.options()
        self.assertEqual(self.post('/api/print/enqueue',options)[0],403)
        self.config()
        for headers in [{},self.parent|{'Host':'untrusted.invalid'},self.bridge]:
            self.assertEqual(self.post('/api/print/enqueue',options,headers)[0],403)
        for override,status in [({'printer':'Unknown_Printer'},403),({'color':'color'},400),
                ({'sides':'two-sided-long-edge'},400),({'sides':[]},400),
                ({'pdf_sha256':'0'*64},409),({'confirmed':False},400)]:
            self.assertEqual(self.post('/api/print/enqueue',options|override)[0],status)
        status,_,body=self.post('/api/print/enqueue',options)
        self.assertEqual(status,200);job=json.loads(body)['job']
        self.assertEqual(json.loads(self.post('/api/print/enqueue',options)[2])['job'],job)
        self.assertEqual(self.post('/api/print/enqueue',options|{'copies':2})[0],409)
        jobs=json.loads(self.request('GET','/api/print/jobs')[2])['jobs']
        self.assertEqual(jobs,[job]);self.assertNotIn('claim_token',job)
        self.assertEqual(self.post('/api/print/received',dict(job_id=job['id'],note='虚构确认'))[0],409)
        cancelled=self.post('/api/print/cancel',dict(job_id=job['id']))
        self.assertEqual(cancelled[0],200)
        self.assertEqual(json.loads(cancelled[2])['job']['status'],'cancelled')
        self.assertEqual(self.post('/api/print/cancel',dict(job_id=job['id']))[0],200)

    def test_bridge_separate_auth_claim_pdf_report_and_parent_confirmation(self):
        job=self.queued()
        claim_request=dict(bridge_id='synthetic_bridge',printer=PRINTER['name'],request_key='synthetic_claim')
        for headers in [{},self.parent,{'Authorization':'Bearer wrong'},self.bridge|{'Host':'untrusted.invalid'}]:
            self.assertEqual(self.post('/api/print/bridge/claim',claim_request,headers)[0],403)
        with patch.dict(app.os.environ,{'FAMILY_PRINT_BRIDGE_TOKEN':''}):
            self.assertEqual(self.post('/api/print/bridge/claim',claim_request,self.bridge)[0],403)
        self.assertEqual(self.post('/api/print/bridge/claim',claim_request|{'printer':'Unknown_Printer'},self.bridge)[0],403)
        status,_,body=self.post('/api/print/bridge/claim',claim_request,self.bridge)
        self.assertEqual(status,200);claimed=json.loads(body)['job']
        self.assertEqual(claimed['id'],job['id']);self.assertTrue(claimed['claim_token'])
        self.assertEqual(json.loads(self.post('/api/print/bridge/claim',claim_request,self.bridge)[2])['job'],claimed)
        for path in ['/api/state','/api/print/jobs']:
            response=self.request('GET',path)[2]
            for secret in ['claim_token',claimed['claim_token'],BRIDGE_TOKEN,'bridge_id']:
                self.assertNotIn(secret.encode(),response)
        for headers in [self.parent,self.bridge,self.bridge|{'X-Print-Claim':'wrong'},
                        self.parent|{'X-Print-Claim':claimed['claim_token']}]:
            self.assertEqual(self.request('GET',claimed['pdf_url'],headers=headers)[0],403)
        status,headers,pdf=self.request('GET',claimed['pdf_url'],headers=self.bridge|{'X-Print-Claim':claimed['claim_token']})
        self.assertEqual(status,200);self.assertEqual(hashlib.sha256(pdf).hexdigest(),job['pdf_sha256'])
        self.assertEqual(headers['X-Frame-Options'],'DENY')
        self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
        report=dict(job_id=job['id'],claim_token=claimed['claim_token'],status='submitted',cups_job_id='Synthetic_Printer-1')
        self.assertEqual(self.post('/api/print/bridge/report',report,self.parent)[0],403)
        self.assertEqual(self.post('/api/print/bridge/report',report|{'claim_token':'非ASCII'},self.bridge)[0],403)
        status,_,body=self.post('/api/print/bridge/report',report,self.bridge)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['job']['status'],'submitted')
        self.assertNotIn(b'claim_token',body)
        status,_,body=self.post('/api/print/bridge/report',report|{'status':'spooler_completed'},self.bridge)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['job']['status'],'spooler_completed')
        self.assertEqual(self.post('/api/print/received',dict(job_id=job['id']))[0],400)
        received=dict(job_id=job['id'],note='虚构家长确认拿到纸张')
        self.assertEqual(self.post('/api/print/received',received,self.bridge)[0],403)
        status,_,body=self.post('/api/print/received',received)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['job']['status'],'received')
        self.assertEqual(json.loads(self.post('/api/print/bridge/report',report,self.bridge)[2])['job']['status'],'received')
        self.assertEqual(self.request('GET',claimed['pdf_url'],headers=self.bridge|{'X-Print-Claim':claimed['claim_token']})[0],403)

    def test_static_whitelist_and_correct_types(self):
        (app.ROOT/'vendor').mkdir()
        paths={'/ui.css':'text/css','/growth-world.js':'text/javascript',
               '/vendor/three.module.min.js':'text/javascript','/vendor/three.core.min.js':'text/javascript'}
        for path,kind in paths.items():
            (app.ROOT/path.lstrip('/')).write_text('/* fictional static fixture */')
            status,headers,_=self.request('GET',path)
            self.assertEqual(status,200);self.assertTrue(headers['Content-Type'].startswith(kind))
            self.assertEqual(headers['X-Frame-Options'],'DENY')
        (app.ROOT/'vendor'/'unlisted.js').write_text('/* must not be served */')
        for path in ['/vendor/unlisted.js','/private/test.sqlite3','/vendor/../private/test.sqlite3']:
            self.assertEqual(self.request('GET',path)[0],404)


if __name__=='__main__': unittest.main()

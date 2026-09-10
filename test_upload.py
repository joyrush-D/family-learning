"""Run python3 test_upload.py; synthetic files and database stay in a temporary directory."""
import base64
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
from urllib.parse import quote
from urllib.error import URLError
from unittest.mock import patch
import zipfile
import wave

import app

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')

with tempfile.TemporaryDirectory() as tmp:
    app.ROOT=Path(tmp);app.DATA=Path(tmp)/'private';app.DATA.mkdir();app.DB=app.DATA/'test.sqlite3'
    (app.ROOT/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n',encoding='utf-8')
    with sqlite3.connect(app.DB) as c:
        c.execute('CREATE TABLE records (id INTEGER PRIMARY KEY, child TEXT, day TEXT, category TEXT, subject TEXT, title TEXT, note TEXT, source TEXT, score REAL, total REAL, created TEXT)')
        c.execute("INSERT INTO records (child,day,category,title) VALUES ('示例甲','2026-09-07','家长观察','旧版记录')")
    assert app.snapshot()['records'][0]['attachments']==[]

    def upload(name,body):
        return app.save_upload(io.BytesIO(body),len(body),quote(name,safe=''))

    first=upload('示例卷子.png',PNG)
    second=upload('示例卷子.png',PNG)
    assert first['id']!=second['id'] and first['size']==len(PNG) and first['mime']=='image/png'
    assert (app.DATA/'uploads'/first['id']).read_bytes()==PNG
    assert not (app.DATA/'uploads'/'示例卷子.png').exists()
    assert len(app.snapshot()['uploads'])==2
    before=set((app.DATA/'uploads').iterdir())
    for name,body,size in [('../escape.png',PNG,len(PNG)),('..\\escape.png',PNG,len(PNG)),
                           ('bad\nname.png',PNG,len(PNG)),('bad.svg',b'<svg/>',6),
                           ('fake.png',b'<html><script>alert(1)</script></html>',40),
                           ('fake.txt',b'<svg onload="alert(1)"/>',24),
                           ('empty.txt',b'',0),('large.txt',b'x',app.MAX_UPLOAD+1),
                           ('truncated.txt',b'x',2),('binary.txt',b'\x00\xff',2)]:
        try: app.save_upload(io.BytesIO(body),size,quote(name,safe=''))
        except ValueError: pass
        else: raise AssertionError('unsafe or invalid upload accepted: '+name)
    assert set((app.DATA/'uploads').iterdir())==before
    # A failed storage operation must roll back metadata and remove the staging file.
    replace=app.os.replace
    try:
        def fail_replace(*args): raise OSError('synthetic storage failure')
        app.os.replace=fail_replace
        try: upload('retry.png',PNG)
        except OSError: pass
        else: raise AssertionError('storage failure was not reported')
    finally: app.os.replace=replace
    assert set((app.DATA/'uploads').iterdir())==before and len(app.snapshot()['uploads'])==2
    token_hex=app.secrets.token_hex
    try:
        app.secrets.token_hex=lambda _:first['id']
        try: upload('collision.png',PNG)
        except sqlite3.IntegrityError: pass
        else: raise AssertionError('duplicate identifier accepted')
    finally: app.secrets.token_hex=token_hex
    assert (app.DATA/'uploads'/first['id']).read_bytes()==PNG
    with io.BytesIO() as blob:
        with zipfile.ZipFile(blob,'w') as z:
            z.writestr('[Content_Types].xml','<Types/>');z.writestr('word/document.xml','<document/>')
        assert upload('示例文档.docx',blob.getvalue())['mime'].endswith('wordprocessingml.document')
        try: upload('fake.pptx',blob.getvalue())
        except ValueError: pass
        else: raise AssertionError('office format mismatch accepted')

    record=dict(child='示例甲',day='2026-09-07',category='学习进展',title='附件记录',attachments=[first['id']])
    app.save_record(record)
    created=app.snapshot()['records'][0];assert created['attachments']==[first['id']]
    for invalid in [['f'*32],['../escape'],first['id'],[5]]:
        try: app.save_record(dict(record,attachments=invalid))
        except ValueError: pass
        else: raise AssertionError('invalid attachment reference accepted')
    record.pop('attachments');app.save_record(dict(record,id=created['id'],title='只改标题'))
    assert app.snapshot()['records'][0]['attachments']==[first['id']]
    app.save_record(dict(record,id=created['id'],attachments=[]))
    assert app.snapshot()['records'][0]['attachments']==[]
    with app.connect() as c:
        previous=json.loads(c.execute('SELECT previous FROM revisions ORDER BY id DESC LIMIT 1').fetchone()[0])
        assert json.loads(previous['attachments'])==[first['id']]

    server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    def request(method,path,body=None,headers=None):
        conn=HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        try:
            conn.request(method,path,body,headers or {})
            r=conn.getresponse();return r.status,dict(r.getheaders()),r.read()
        finally: conn.close()
    try:
        headers={'X-Family-Token':app.TOKEN,'X-File-Name':quote('照片.png')}
        status,_,body=request('POST','/api/upload',PNG,headers)
        assert status==200
        received=json.loads(body)['attachment'];assert received['name']=='照片.png'
        status,response_headers,body=request('GET',received['url'])
        assert status==200 and body==PNG
        assert response_headers['Content-Type']=='image/png' and response_headers['Content-Disposition'].startswith('inline;')
        assert response_headers['X-Content-Type-Options']=='nosniff'
        status,_,body=request('POST','/api/upload',b'%PDF-1.4\n%%EOF',dict(headers,**{'X-File-Name':'test.pdf'}))
        assert status==200
        status,response_headers,_=request('GET',json.loads(body)['attachment']['url'])
        assert status==200 and response_headers['Content-Disposition'].startswith('attachment;')
        assert request('POST','/api/upload',PNG,{'X-File-Name':'test.png'})[0]==403
        assert request('POST','/api/upload',PNG,dict(headers,Host='untrusted.example'))[0]==403
        assert request('POST','/api/upload',None,dict(headers,**{'Content-Length':str(app.MAX_UPLOAD+1)}))[0]==413
        assert request('POST','/api/upload',None,dict(headers,**{'Content-Length':'invalid'}))[0]==400
        for path in ['/upload/../../test.sqlite3','/upload/%2e%2e%2ftest.sqlite3','/upload/'+'a'*32]:
            assert request('GET',path)[0]==404
        status,_,body=request('GET','/api/state')
        assert status==200 and all(isinstance(r['attachments'],list) for r in json.loads(body)['records'])
        records_before=app.snapshot()['records']
        draft=dict(title='虚构数学记录',subject='数学',score=85,total=100,note='仅为待核对草稿',uncertainties=['订正情况未知'])
        draft_body=json.dumps(dict(child_id='child-1',text='只整理本次虚构资料',attachments=[first['id']])).encode()
        with patch.object(app.family_llm,'extract_draft',return_value=draft) as extract:
            assert request('POST','/api/draft',draft_body)[0]==403
            assert request('POST','/api/draft',draft_body,dict(headers,**{'X-Family-Token':'wrong'}))[0]==403
            assert request('POST','/api/draft',draft_body,dict(headers,Host='untrusted.example'))[0]==403
            for ids in [['f'*32],['../uploads'],[first['id']]*4]:
                assert request('POST','/api/draft',json.dumps(dict(child_id='child-1',attachments=ids)).encode(),headers)[0]==400
            for child_id in ['', 'unknown', 123]:
                assert request('POST','/api/draft',json.dumps(dict(child_id=child_id,text='虚构资料')).encode(),headers)[0]==400
            extract.assert_not_called()
            status,_,body=request('POST','/api/draft',draft_body,headers)
            assert status==200 and json.loads(body)==dict(draft=draft,child_id='child-1',child_name='示例甲')
            extract.assert_called_once_with('只整理本次虚构资料',[dict(mime='image/png',data=PNG)],target_child='示例甲',data_path=app.DATA)
        assert app.snapshot()['records']==records_before
        class Offline:
            def open(self,*args,**kwargs): raise URLError('SYNTHETIC_PRIVATE_KEY /sensitive/raw-response')
        with patch.object(app.family_llm,'build_opener',return_value=Offline()),patch.dict(app.os.environ,{
                'FAMILY_LLM_BASE_URL':'http://127.0.0.1:1/v1','FAMILY_LLM_MODEL':'synthetic-model',
                'FAMILY_LLM_API_KEY':'SYNTHETIC_PRIVATE_KEY','FAMILY_LLM_REASONING_EFFORT':''}):
            status,_,body=request('POST','/api/draft',draft_body,headers)
            assert status==503 and '手动记录' in json.loads(body)['error']
            assert b'SYNTHETIC_PRIVATE_KEY' not in body and b'/sensitive/raw-response' not in body
        assert app.snapshot()['records']==records_before

        pcm=b'\x00\x00'*320
        with io.BytesIO() as blob:
            with wave.open(blob,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)
            wav=blob.getvalue()
        status,_,body=request('POST','/api/upload',wav,dict(headers,**{'X-File-Name':quote('虚构录音.wav')}))
        assert status==200
        audio=json.loads(body)['attachment']
        upload('另一个未选中的录音.wav',wav+b'synthetic-unselected')
        audio_body=json.dumps(dict(attachment=audio['id'])).encode()
        transcript='虚构文字：订正情况待核对。'
        with patch.object(app.family_llm,'transcribe_audio',return_value=transcript) as transcribe:
            assert request('POST','/api/transcribe',audio_body)[0]==403
            assert request('POST','/api/transcribe',audio_body,dict(headers,**{'X-Family-Token':'wrong'}))[0]==403
            assert request('POST','/api/transcribe',audio_body,dict(headers,Host='untrusted.example'))[0]==403
            for ident in [None,[],{},'','../uploads','f'*32,first['id']]:
                assert request('POST','/api/transcribe',json.dumps(dict(attachment=ident)).encode(),headers)[0]==400
            transcribe.assert_not_called()
            status,_,body=request('POST','/api/transcribe',audio_body,headers)
            assert status==200 and json.loads(body)==dict(text=transcript)
            transcribe.assert_called_once_with(wav,'audio/wav')
        assert app.snapshot()['records']==records_before
        assert request('GET',audio['url'])[2]==wav
        with patch.object(app.family_llm,'build_opener',return_value=Offline()),patch.dict(app.os.environ,{
                'FAMILY_ASR_URL':'http://127.0.0.1:1/v1/audio/transcriptions',
                'FAMILY_ASR_API_KEY':'SYNTHETIC_PRIVATE_KEY','FAMILY_ASR_MODEL':'base'}):
            status,_,body=request('POST','/api/transcribe',audio_body,headers)
            assert status==503 and '手动记录' in json.loads(body)['error']
            assert b'SYNTHETIC_PRIVATE_KEY' not in body and b'/sensitive/raw-response' not in body

        webm=b'\x1a\x45\xdf\xa3webm synthetic mocked bytes http://untrusted.invalid/media'
        browser_audio=upload('虚构浏览器录音.webm',webm)
        browser_body=json.dumps(dict(attachment=browser_audio['id'])).encode()
        converted=subprocess.CompletedProcess([],0,stdout=pcm,stderr=b'')
        with patch.object(app.subprocess,'run',return_value=converted) as convert,patch.object(app.family_llm,'transcribe_audio',return_value=transcript) as transcribe:
            status,_,body=request('POST','/api/transcribe',browser_body,headers)
            assert status==200 and json.loads(body)==dict(text=transcript)
            argv=convert.call_args.args[0];options=convert.call_args.kwargs
            assert argv[0]=='ffmpeg' and argv[argv.index('-protocol_whitelist')+1]=='pipe'
            assert argv[argv.index('-i')+1]=='pipe:0' and argv[-1]=='pipe:1'
            assert all('://' not in arg for arg in argv)
            assert options['input']==webm and options['check'] is True and options['timeout']==45
            transformed,mime=transcribe.call_args.args
            assert mime=='audio/wav'
            with wave.open(io.BytesIO(transformed),'rb') as w:
                assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,16000)
                assert w.readframes(w.getnframes())==pcm
        failure=subprocess.CalledProcessError(1,['ffmpeg'],stderr=b'SYNTHETIC_PRIVATE_KEY /sensitive/raw-response')
        with patch.object(app.subprocess,'run',side_effect=failure),patch.object(app.family_llm,'transcribe_audio') as transcribe:
            status,_,body=request('POST','/api/transcribe',browser_body,headers)
            assert status==503 and '原件仍保留' in json.loads(body)['error']
            assert b'SYNTHETIC_PRIVATE_KEY' not in body and b'/sensitive/raw-response' not in body
            transcribe.assert_not_called()
        for invalid_pcm in [b'',b'\x00\x00'*(180*16000+1)]:
            with patch.object(app.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout=invalid_pcm)),patch.object(app.family_llm,'transcribe_audio') as transcribe:
                assert request('POST','/api/transcribe',browser_body,headers)[0]==400
                transcribe.assert_not_called()
        assert request('GET',browser_audio['url'])[2]==webm and request('GET',audio['url'])[2]==wav
        assert app.snapshot()['records']==records_before
    finally:
        server.shutdown();server.server_close()

print('PASS: upload/draft/transcription HTTP, auth, selected originals, bounded pipe-only conversion, redaction and no record writes')

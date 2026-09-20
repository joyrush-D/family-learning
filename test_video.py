"""Synthetic media only. Run python3 -m unittest test_video (FFmpeg/ffprobe for real containers)."""
import io
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import app


class VideoTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);data=root/'private';data.mkdir()
        for key,value in [('ROOT',root),('DATA',data),('DB',data/'test.sqlite3')]:
            p=patch.object(app,key,value);p.start();self.addCleanup(p.stop)
        (root/'家庭运行规则.md').write_text('| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n')
        with app.connect(): pass

    def upload(self,name,body):
        return app.save_upload(io.BytesIO(body),len(body),name)

    def test_probe_is_local_bounded_and_errors_do_not_store_or_disclose(self):
        body=b'\x00\x00\x00\x18ftypisomsynthetic'
        for failure in [FileNotFoundError(),subprocess.TimeoutExpired('ffprobe',15),
                        subprocess.CalledProcessError(1,'ffprobe',stderr=b'PRIVATE_CANARY'),
                        subprocess.CompletedProcess([],0,stdout=b'PRIVATE_CANARY'),
                        subprocess.CompletedProcess([],0,stdout=b'{"streams":[]}')]:
            with patch.object(app.subprocess,'run',side_effect=failure if isinstance(failure,Exception) else None,
                              return_value=failure) as probe:
                with self.assertRaises(ValueError) as caught:self.upload('synthetic.mp4',body)
                self.assertNotIn('PRIVATE_CANARY',str(caught.exception))
                args=probe.call_args.args[0];kwargs=probe.call_args.kwargs
                self.assertEqual(args[args.index('-protocol_whitelist')+1],'pipe')
                self.assertEqual(args[args.index('-i')+1],'pipe:0')
                self.assertEqual(kwargs['timeout'],15);self.assertTrue(kwargs['check']);self.assertEqual(kwargs['input'],body)
            with app.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM uploads').fetchone()[0],0)
            self.assertEqual(list((app.DATA/'uploads').iterdir()),[])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'optional FFmpeg tools unavailable')
    def test_actual_containers_ranges_originals_and_model_isolation(self):
        def media(name,video):
            path=app.ROOT/name
            args=['ffmpeg','-nostdin','-v','error','-f','lavfi','-i',
                  'color=c=blue:s=160x90:r=10' if video else 'anullsrc=r=16000:cl=mono','-t','1']
            args+=['-c:v','libvpx-vp9' if name.endswith('.webm') else 'libx264'] if video else ['-c:a','libopus' if name.endswith(('.webm','.ogg')) else 'aac']
            subprocess.run(args+[str(path)],check=True,capture_output=True,timeout=15)
            return path.read_bytes()
        saved={}
        for name,video,mime in [('clip.mp4',True,'video/mp4'),('clip.mov',True,'video/quicktime'),
                                ('clip.webm',True,'video/webm'),('audio.webm',False,'audio/webm'),
                                ('audio.m4a',False,'audio/mp4'),('audio.ogg',False,'audio/ogg')]:
            raw=media(name,video);item=self.upload(name,raw);saved[name]=(item,raw)
            self.assertEqual(item['mime'],mime)
            self.assertEqual((app.DATA/'uploads'/item['id']).read_bytes(),raw)
        for name,raw in [('fake.mp4',b'\x00\x00\x00\x18ftypisomfake'),
                         ('fake.webm',b'\x1a\x45\xdf\xa3webm fake'),
                         ('hidden.m4a',saved['clip.mp4'][1]),('fake.mov',saved['audio.webm'][1])]:
            with self.assertRaises(ValueError):self.upload(name,raw)
        item,raw=saved['clip.webm']
        with patch.object(app.family_llm,'transcribe_audio') as asr,patch.object(app.family_llm,'extract_draft') as llm:
            with self.assertRaises(ValueError):app.transcribe_material({'attachment':item['id']})
            with self.assertRaises(ValueError):app.draft_from_material({'child_id':'child-1','attachments':[item['id']]})
            # A legacy WebM row incorrectly labelled as audio also cannot reach ASR.
            with app.connect() as c:c.execute('UPDATE uploads SET mime=? WHERE id=?',('audio/webm',item['id']))
            with self.assertRaises(ValueError):app.transcribe_material({'attachment':item['id']})
            asr.assert_not_called();llm.assert_not_called()
            with app.connect() as c:c.execute('UPDATE uploads SET mime=? WHERE id=?',('video/webm',item['id']))
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        def get(range_=None,host=None,path=None):
            conn=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                headers={}
                if range_ is not None:headers['Range']=range_
                if host:headers['Host']=host
                conn.request('GET',path or item['url'],headers=headers);r=conn.getresponse()
                return r.status,dict(r.getheaders()),r.read()
            finally:conn.close()
        try:
            status,headers,received=get();self.assertEqual((status,received),(200,raw))
            self.assertEqual(headers['Content-Type'],'video/webm');self.assertTrue(headers['Content-Disposition'].startswith('inline;'))
            self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
            for request,start,end in [('bytes=0-1',0,1),('bytes=5-',5,len(raw)-1),('bytes=-12',len(raw)-12,len(raw)-1),('bytes=0-999999',0,len(raw)-1)]:
                status,h,b=get(request);self.assertEqual((status,b),(206,raw[start:end+1]));self.assertEqual(h['Content-Range'],f'bytes {start}-{end}/{len(raw)}')
                self.assertEqual(int(h['Content-Length']),len(b))
            for request in ['bytes=999999-','bytes=8-4','bytes=-0','bytes=-','bytes=0-1,4-5','garbage']:
                status,h,b=get(request);self.assertEqual((status,b),(416,b''));self.assertEqual(h['Content-Range'],f'bytes */{len(raw)}')
            self.assertEqual(get('bytes=0-1',host='untrusted.invalid')[0],403)
            self.assertEqual(get('bytes=0-1',path='/child'+item['url'])[0],401)
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()

"""All fictional, temporary originals; no model/network/provider/printer calls."""
from pathlib import Path
import hashlib
import json
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

import family_media
import family_pdf
import family_preview
from family_print import PrintError
from family_reading import Store,ReadingError


def image():
    def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,3,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\x78\xaa\xcc'*2)*3))+chunk(b'IEND',b'')


class Covers(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.data=Path(self.temp.name);(self.data/'uploads').mkdir();self.db=self.data/'family.sqlite3';self.n=0
        self.profiles=[dict(id='child-a',name='示例甲'),dict(id='child-b',name='示例乙')]
        with self.connect() as c:
            c.execute('CREATE TABLE uploads(id TEXT PRIMARY KEY,name TEXT,mime TEXT,size INTEGER)')
            c.execute("CREATE TABLE records(id INTEGER PRIMARY KEY,child TEXT,attachments TEXT DEFAULT '[]')")
        self.store=Store(self.connect,lambda:self.profiles,lambda:[],cover_original=lambda c,i:family_preview.read_upload(self.data,c,i))
    def tearDown(self):self.temp.cleanup()
    def connect(self):
        c=sqlite3.connect(self.db);c.row_factory=sqlite3.Row;return c
    def upload(self,ident,body,mime,name):
        (self.data/'uploads'/ident).write_bytes(body)
        with self.connect() as c:c.execute('INSERT INTO uploads VALUES(?,?,?,?)',(ident,name,mime,len(body)))
        return hashlib.sha256(body).hexdigest()
    def obj(self,row=None,**extra):
        self.n+=1;value=dict(child_id='child-a',request_key='fictional-cover-'+str(self.n))
        if row:value.update(id=row['id'],version=row['version'])
        return value|extra
    def test_cover_create_reopen_clear_version_hash_and_child_guards(self):
        ident='a'*32;body=image();sha=self.upload(ident,body,'image/png','fictional-cover.png')
        payload=self.obj(book='虚构故事',cover_upload_id=ident,cover_sha256=sha)
        task=self.store.mutate('create',payload)['task'];self.assertEqual(self.store.mutate('create',payload)['task'],task)
        reopened=self.store.snapshot()['tasks'][0];self.assertEqual(reopened['cover_upload_id'],ident);self.assertIn('child_id=child-a',reopened['cover']['url'])
        self.assertEqual(self.store.cover(dict(id=task['id'],child_id='child-a',version=1)),(body,'image/png'))
        with self.assertRaises(ReadingError):self.store.cover(dict(id=task['id'],child_id='child-b',version=1))
        before=self.store.snapshot()
        for change in [dict(cover_sha256='0'*64),dict(child_id='child-b'),dict(cover_upload_id='missing',cover_sha256=sha)]:
            with self.assertRaises((ReadingError,PrintError)):self.store.mutate('edit',self.obj(task,**change))
        self.assertEqual(self.store.snapshot(),before)
        with self.assertRaises(ReadingError):self.store.mutate('create',self.obj(child_id='child-b',cover_upload_id=ident,cover_sha256=sha))
        cleared=self.store.mutate('edit',self.obj(task,cover_upload_id='',cover_sha256=''))['task'];self.assertIsNone(cleared['cover']);self.assertEqual((self.data/'uploads'/ident).read_bytes(),body)
        with self.assertRaises(ReadingError) as err:self.store.cover(dict(id=task['id'],child_id='child-a',version=1))
        self.assertEqual(err.exception.status,409)
    def test_cover_disallows_non_image_and_changed_original(self):
        ident='b'*32;sha=self.upload(ident,b'fictional plain text','text/plain','fictional.txt')
        with self.assertRaises(ReadingError):self.store.mutate('create',self.obj(cover_upload_id=ident,cover_sha256=sha))
        ident='c'*32;body=image();sha=self.upload(ident,body,'image/png','cover.png');task=self.store.mutate('create',self.obj(cover_upload_id=ident,cover_sha256=sha))['task']
        (self.data/'uploads'/ident).write_bytes(body[:-1]+b'x')
        with self.assertRaises(ReadingError) as err:self.store.cover(dict(id=task['id'],child_id='child-a',version=1))
        self.assertEqual(err.exception.status,409)
    def test_first_page_cache_original_identity_failure_retry_and_no_print_rows(self):
        ident='d'*32;body=b'%PDF-fictional';self.upload(ident,body,'application/pdf','fictional.pdf');png=image();self.assertEqual(family_pdf._validate_png(png),(2,3))
        with self.connect() as c:
            with patch('family_pdf.render_pages',return_value=dict(pages=[dict(data=png)])) as render:
                first,key=family_preview.first_page(self.data,c,ident);self.assertEqual(first,png);self.assertEqual(family_preview.first_page(self.data,c,ident),(png,key));self.assertEqual(render.call_count,1)
                cache=self.data/'original-previews'/(key+'.png');cache.write_bytes(b'broken');self.assertEqual(family_preview.first_page(self.data,c,ident),(png,key));self.assertEqual(render.call_count,2)
            (self.data/'original-previews'/(key+'.png')).unlink()
            with patch('family_pdf.render_pages',side_effect=family_pdf.PDFError('fake failure')):
                with self.assertRaises(PrintError):family_preview.first_page(self.data,c,ident)
            with patch('family_pdf.render_pages',return_value=dict(pages=[dict(data=png)])):self.assertEqual(family_preview.first_page(self.data,c,ident),(png,key))
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")};self.assertNotIn('print_preparations',tables);self.assertNotIn('print_jobs',tables)
        self.assertEqual((self.data/'uploads'/ident).read_bytes(),body)
    def test_complex_office_refused_before_conversion(self):
        for ident,mime,name in [('e'*32,family_media.DOCX_MIME,'blocked.docx'),('f'*32,family_media.PPTX_MIME,'blocked.pptx')]:
            self.upload(ident,b'PK fictional unsafe archive',mime,name)
            with self.connect() as c,patch('family_print.office_convert') as converter:
                with self.assertRaises(PrintError):family_preview.first_page(self.data,c,ident)
                converter.assert_not_called()
    def test_explicit_retry_rebuilds_an_undecodable_cache_without_changing_the_original(self):
        ident='7'*32;body=b'%PDF-fictional-refresh';self.upload(ident,body,'application/pdf','fictional-refresh.pdf');png=image()
        def chunk(kind,value):return struct.pack('>I',len(value))+kind+value+struct.pack('>I',zlib.crc32(kind+value)&0xffffffff)
        broken=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',2,3,8,2,0,0,0))+chunk(b'IDAT',b'not-a-zlib-stream')+chunk(b'IEND',b'')
        self.assertEqual(family_pdf._validate_png(broken),(2,3))
        with self.connect() as c,patch('family_pdf.render_pages',return_value=dict(pages=[dict(data=png)])) as render:
            _,key=family_preview.first_page(self.data,c,ident);cache=self.data/'original-previews'/(key+'.png');cache.write_bytes(broken)
            self.assertEqual(family_preview.first_page(self.data,c,ident),(broken,key));self.assertEqual(render.call_count,1)
            self.assertEqual(family_preview.first_page(self.data,c,ident,refresh=True),(png,key));self.assertEqual(render.call_count,2)
            self.assertEqual(cache.read_bytes(),png);self.assertEqual(family_preview.first_page(self.data,c,ident),(png,key));self.assertEqual(render.call_count,2)
        self.assertEqual((self.data/'uploads'/ident).read_bytes(),body)
    def test_failed_refresh_preserves_cache_and_original_then_same_operation_recovers(self):
        ident='8'*32;body=b'%PDF-fictional-retry';self.upload(ident,body,'application/pdf','fictional-retry.pdf');png=image()
        with self.connect() as c:
            with patch('family_pdf.render_pages',return_value=dict(pages=[dict(data=png)])):
                _,key=family_preview.first_page(self.data,c,ident)
            cache=self.data/'original-previews'/(key+'.png')
            with patch('family_pdf.render_pages',side_effect=family_pdf.PDFError('fictional failure')):
                with self.assertRaises(PrintError):family_preview.first_page(self.data,c,ident,refresh=True)
            self.assertEqual(cache.read_bytes(),png);self.assertEqual((self.data/'uploads'/ident).read_bytes(),body)
            with patch('family_pdf.render_pages',return_value=dict(pages=[dict(data=png)])) as render:
                self.assertEqual(family_preview.first_page(self.data,c,ident,refresh=True),(png,key));self.assertEqual(render.call_count,1)
    def test_original_path_symlink_and_unsupported_format_guard(self):
        ident='9'*32;self.upload(ident,b'fictional legacy','application/msword','old.doc')
        with self.connect() as c:
            with self.assertRaises(PrintError):family_preview.first_page(self.data,c,ident)
            (self.data/'uploads'/ident).unlink();(self.data/'uploads'/ident).symlink_to(self.db)
            with self.assertRaises(PrintError):family_preview.read_upload(self.data,c,ident)


if __name__=='__main__':unittest.main()

"""Synthetic tests for bounded WeChat image handling; never uses a real CLI or family data."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib
import struct
import io
import warnings
import zipfile

import family_agent as agent
import family_media as media
import family_review


def png(width=96, height=64):
    rows = b''.join(b'\0' + bytes((40, 180, 220)) * width for _ in range(height))
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


_W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_TYPES = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
_RELS = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>'
_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/'


def docx(body, extra=(), document=None, method=zipfile.ZIP_DEFLATED):
    """A synthetic DOCX built in memory; extra members follow the three required parts."""
    xml = document if document is not None else (
        '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="%s" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><w:body>%s<w:sectPr/></w:body></w:document>' % (_W_NS, body))
    out = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(out, 'w', method) as z:
        warnings.simplefilter('ignore')  # A duplicate member is written on purpose.
        for name, text in [('[Content_Types].xml', _TYPES), ('word/document.xml', xml),
                           ('_rels/.rels', _RELS % ('<Relationship Id="rId1" Type="%sofficeDocument" Target="word/document.xml"/>' % _REL_TYPE)), *extra]:
            z.writestr(name, text)
    return out.getvalue()


def para(text, run=''):
    return '<w:p><w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (run, text)


def styles(inner, target='styles.xml'):
    return [('word/' + target, '<?xml version="1.0" encoding="UTF-8"?><w:styles xmlns:w="%s">%s</w:styles>' % (_W_NS, inner)),
            ('word/_rels/document.xml.rels', _RELS % ('<Relationship Id="rId2" Type="%sstyles" Target="%s"/>' % (_REL_TYPE, target)))]


DOCX_BODY = ('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/><w:strike w:val="0"/></w:rPr><w:t>虚构学校·英语仿写要求</w:t></w:r></w:p>'
             '<w:p><w:r><w:t xml:space="preserve">第一步：</w:t></w:r><w:r><w:tab/><w:t>阅读范文</w:t><w:br/><w:t>第二步：仿写五句</w:t></w:r></w:p><w:p/>'
             '<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/></w:tblGrid><w:tr><w:tc><w:tcPr/><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc>'
             '<w:tc><w:p><w:r><w:t>要求</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>字数</w:t></w:r></w:p></w:tc>'
             '<w:tc><w:p><w:r><w:t>不少于</w:t></w:r></w:p><w:p><w:r><w:t>50词</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
             '<w:p><w:hyperlink w:anchor="end"><w:r><w:t>café ✓ 完成后交给老师</w:t></w:r></w:hyperlink></w:p>')
DOCX_TEXT = '虚构学校·英语仿写要求\n第一步：\t阅读范文\n第二步：仿写五句\n项目 | 要求\n字数 | 不少于 / 50词\ncafé ✓ 完成后交给老师'
_HIDDEN = '<w:style w:type="character" w:styleId="Quiet"><w:rPr><w:vanish/></w:rPr></w:style>'


def unreadable_docx():
    """name -> (bytes, expected code): every one must fail before any model call."""
    entity = ('<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "虚构实体">]><w:document xmlns:w="%s"><w:body>'
              '<w:p><w:r><w:t>&a;</w:t></w:r></w:p></w:body></w:document>' % _W_NS)
    plain, stored = docx(para('虚构正文')), docx(para('虚构正文'), method=zipfile.ZIP_STORED)
    no, bad = 'draft_docx_unsupported', 'draft_docx_rejected'
    return dict(
        picture=(docx(para('见图') + '<w:p><w:r><w:drawing/></w:r></w:p>'), no),
        picture_file=(docx(para('见图'), [('word/media/image1.png', 'synthetic')]), no),
        formula=(docx('<w:p><m:oMath><m:r><m:t>x+1</m:t></m:r></m:oMath></w:p>' + para('解方程')), no),
        hidden=(docx(para('隐藏', '<w:rPr><w:vanish/></w:rPr>') + para('可见')), no),
        struck=(docx(para('已取消的要求', '<w:rPr><w:strike/></w:rPr>') + para('可见')), no),
        revision=(docx('<w:p><w:ins><w:r><w:t>修订</w:t></w:r></w:ins></w:p>'), no),
        field=(docx('<w:p><w:fldSimple w:instr="DATE"><w:r><w:t>日期</w:t></w:r></w:fldSimple></w:p>'), no),
        comment=(docx('<w:p><w:r><w:t>正文</w:t><w:commentReference w:id="0"/></w:r></w:p>'), no),
        nested_table=(docx('<w:tbl><w:tr><w:tc><w:tbl><w:tr><w:tc>%s</w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl>' % para('内层')), no),
        header=(docx(para('正文') + '<w:sectPr><w:headerReference w:type="default"/></w:sectPr>'), no),
        empty=(docx('<w:p/>'), no),
        style_hidden=(docx(para('答案：B', '<w:rPr><w:rStyle w:val="Quiet"/></w:rPr>') + para('可见'), styles(_HIDDEN)), no),
        style_based_on=(docx('<w:p><w:pPr><w:pStyle w:val="Child"/></w:pPr><w:r><w:t>已取消</w:t></w:r></w:p>', styles(
            '<w:style w:type="paragraph" w:styleId="Base"><w:rPr><w:dstrike/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="Child"><w:basedOn w:val="Base"/></w:style>')), no),
        style_default=(docx(para('正文'), styles('<w:docDefaults><w:rPrDefault><w:rPr><w:vanish/></w:rPr></w:rPrDefault></w:docDefaults>')), no),
        style_default_paragraph=(docx(para('正文'), styles('<w:style w:type="paragraph" w:default="1" w:styleId="a"><w:rPr><w:strike/></w:rPr></w:style>')), no),
        style_other_part=(docx(para('答案：B', '<w:rPr><w:rStyle w:val="Quiet"/></w:rPr>'), styles(_HIDDEN, 'custom.xml')), no),
        style_part_missing=(docx(para('正文'), styles(_HIDDEN)[1:]), no),
        not_zip=(b'synthetic bytes, not an archive', bad), truncated=(plain[:-40], bad),
        bad_crc=(stored.replace('虚构正文'.encode(), '虚构改动'.encode()), bad),
        external=(docx(para('正文'), [('word/_rels/document.xml.rels', _RELS % (
            '<Relationship Id="rId9" Type="%shyperlink" Target="https://example.invalid/x" TargetMode="External"/>' % _REL_TYPE))]), bad),
        duplicate=(docx(para('第一份'), [('word/document.xml', '<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>' % (_W_NS, para('第二份')))]), bad),
        duplicate_case=(docx(para('第一份'), [('WORD/DOCUMENT.XML', 'x')]), bad),
        entity=(docx('', document=entity), bad), utf16=(docx('', document=('<w:document xmlns:w="%s"/>' % _W_NS).encode('utf-16')), bad),
        invalid_utf8=(docx('', document=b'<w:document xmlns:w="' + _W_NS.encode() + b'"><w:body><w:p><w:r><w:t>\xff\xfe</w:t></w:r></w:p></w:body></w:document>'), bad),
        macro=(docx(para('正文'), [('word/vbaProject.bin', 'x')]), bad),
        oversize_member=(docx(para('正文'), [('word/big.xml', '0' * (media.DOCX_LIMITS['member'] + 1))]), bad),
        oversize_text=(docx(para('字' * (media.DOCX_LIMITS['chars'] + 1))), 'draft_text_too_long'))


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='synthetic-media-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()
        self.root, self.data = root, root / 'private'
        self.data.mkdir()
        (root / '家庭运行规则.md').write_text(
            '| child-1 | 示例甲 | 男 | 10岁 | 四年级 |\n'
            '| child-2 | 示例乙 | 女 | 11岁 | 五年级 |\n')
        self.app = family_review.load_app(root, self.data)
        self.store = agent.Store(self.app.connect, self.app.profiles, self.data)
        self.now = dt.datetime(2026, 2, 10, 8, tzinfo=agent.TZ)
        self.source = dict(id='wechat:12345@chatroom', platform='wechat', child_id='child-1',
                           name='虚构班级', cursor='10', enabled=True)
        self.write_config()

    def write_config(self, enabled=True, child_id=None):
        source = {**self.source, 'child_id': child_id or self.source['child_id']}
        (self.data / 'agent.json').write_text(json.dumps({'enabled': enabled, 'sources': [source]}))

    def message(self, ident='1', kind='image', unread=True, offset=0):
        stamp = (self.now + dt.timedelta(minutes=offset)).isoformat()
        return dict(id=ident, time=stamp, kind=kind, sender='虚构老师', text='虚构图片原件', unread=unread)

    def ingest(self, message):
        stamp = message['time']
        with self.store._db() as c:
            row = c.execute('SELECT cursor FROM agent_sources WHERE id=?', (self.source['id'],)).fetchone()
        expected = row['cursor'] if row else self.source['cursor']
        return self.store.ingest(dict(source_id=self.source['id'], expected_cursor=expected,
            cursor=str(int(expected) + 1), checked_at=stamp, last_message_time=stamp,
            error='', messages=[message]))

    def settings(self):
        return {'since': self.now - dt.timedelta(days=1), 'wechat_cli': '/dev/null',
                'wechat_config': '/dev/null', 'ffmpeg': '/dev/null'}

    def image(self):
        body = png()
        return {'data': body, 'width': 96, 'height': 64, 'first_frame_only': True}

    def db_rows(self, sql, args=()):
        with self.store._db() as c:
            return [dict(row) for row in c.execute(sql, args)]

    def media_id(self, message):
        return hashlib.sha256(json.dumps(['wechat-first-frame', self.source['id'],
            self.source['child_id'], message['id']]).encode()).hexdigest()[:32]

    def seed_job(self, message, state='pending'):
        with self.store._db() as c:
            c.execute('INSERT OR REPLACE INTO agent_media(source_id,message_id,state) VALUES(?,?,?)',
                      (self.source['id'], message['id'], state))

    def seed_upload(self, ident='a' * 32, body=None):
        body = body or png()
        directory = self.data / 'uploads'; directory.mkdir(mode=0o700, exist_ok=True)
        (directory / ident).write_bytes(body)
        with self.store._db() as c:
            c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',
                      (ident, 'synthetic.png', len(body), 'image/png', self.now.isoformat()))
        return ident

    def test_image_saved_once_replay_detach_and_payload_unchanged(self):
        message = self.message(); self.ingest(message)
        before = self.db_rows('SELECT child,day,title,note,source FROM records') + self.db_rows('SELECT * FROM manual_tasks')
        calls = []
        def fetch(settings, source, value):
            calls.append(value['id']); return self.image()
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=fetch):
            self.assertEqual(media.run_one(self.app, self.store, self.now)['state'], 'saved')
            self.assertEqual(media.run_one(self.app, self.store, self.now + dt.timedelta(minutes=1))['state'], 'idle')
        self.assertEqual(calls, ['1'])
        job = self.db_rows('SELECT * FROM agent_media')[0]
        self.assertEqual((job['state'], job['attempts']), ('saved', 1))
        self.assertEqual(len(self.db_rows('SELECT * FROM agent_message_attachments')), 1)
        self.assertEqual(self.db_rows('SELECT payload FROM agent_messages')[0]['payload'], json.dumps(message, ensure_ascii=False, sort_keys=True, separators=(',', ':')))
        self.assertEqual(self.db_rows('SELECT child,day,title,note,source FROM records') + self.db_rows('SELECT * FROM manual_tasks'), before)
        self.store.message_attachment({'child_id': 'child-1', 'source_id': self.source['id'], 'message_id': '1',
                                       'attachment_id': job['upload_id'], 'action': 'detach'}, lambda row: dict(row))
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])
        self.assertTrue((self.data / 'uploads' / job['upload_id']).exists())
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=AssertionError('detached image refetched')):
            self.assertEqual(media.run_one(self.app, self.store, self.now + dt.timedelta(minutes=2))['state'], 'idle')
        self.assertEqual(self.db_rows('SELECT state FROM agent_media')[0]['state'], 'dismissed')

    def test_three_failures_backoff_and_cap(self):
        message = self.message('retry'); self.ingest(message); calls = []
        def failed(settings, source, value):
            calls.append(value['id']); raise media.MediaError('synthetic_fetch_failed')
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=failed):
            for minutes in (0, 5, 10):
                self.assertEqual(media.run_one(self.app, self.store, self.now + dt.timedelta(minutes=minutes))['state'], 'error')
            self.assertEqual(media.run_one(self.app, self.store, self.now + dt.timedelta(minutes=15))['state'], 'idle')
        self.assertEqual(calls, ['retry', 'retry', 'retry'])
        row = self.db_rows('SELECT state,attempts FROM agent_media')[0]
        self.assertEqual((row['state'], row['attempts']), ('error', 3))
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])

    def test_disabled_mismatch_wrong_child_and_manual_link_block_save(self):
        message = self.message('disabled'); self.ingest(message)
        self.write_config(False)
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=AssertionError('disabled source fetched')):
            self.assertEqual(media.run_one(self.app, self.store, self.now)['state'], 'disabled')
        self.write_config(True, child_id='child-2')
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=AssertionError('mismatched source fetched')):
            self.assertEqual(media.run_one(self.app, self.store, self.now)['state'], 'error')
        self.assertEqual(self.db_rows('SELECT * FROM agent_media'), [])

        with self.store._db() as c: c.execute('DELETE FROM agent_messages WHERE id=?', ('disabled',))
        self.write_config(True); manual = self.message('manual'); self.ingest(manual)
        upload = self.seed_upload('b' * 32)
        self.store.message_attachment({'child_id': 'child-1', 'source_id': self.source['id'], 'message_id': 'manual',
                                       'attachment_id': upload, 'action': 'attach'}, lambda row: dict(row))
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=AssertionError('manual link refetched')):
            self.assertEqual(media.run_one(self.app, self.store, self.now)['state'], 'idle')
        self.assertEqual(self.db_rows('SELECT state FROM agent_media WHERE message_id=?', ('manual',))[0]['state'], 'skipped')

    def test_revocation_during_save_and_wrong_child_save_leave_no_link(self):
        message = self.message('revoke'); self.ingest(message); calls = []
        def revoke_then_return(settings, source, value):
            calls.append(value['id']); self.write_config(False); return self.image()
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=revoke_then_return):
            self.assertEqual(media.run_one(self.app, self.store, self.now)['state'], 'error')
        self.assertEqual(calls, ['revoke']); self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])
        self.assertEqual(self.db_rows('SELECT state FROM agent_media')[0]['state'], 'error')

        self.write_config(True); wrong = self.message('wrong'); self.ingest(wrong); self.seed_job(wrong)
        with self.assertRaises(media.MediaError):
            media.save(self.app, self.store, {**self.source, 'child_id': 'child-2'}, wrong, self.image(), self.now)
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])

    def test_link_and_db_failures_do_not_overwrite_or_associate(self):
        message = self.message('linkfail'); self.ingest(message); self.seed_job(message)
        directory = self.data / 'uploads'; target = directory / self.media_id(message)
        original = b'prior-file'; directory.mkdir(mode=0o700, exist_ok=True); target.write_bytes(original)
        with self.assertRaises(media.MediaError):
            media.save(self.app, self.store, self.source, message, self.image(), self.now)
        self.assertEqual(target.read_bytes(), original); self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])

        target.unlink(); message = self.message('dbfail', offset=1); self.ingest(message); self.seed_job(message)
        with patch.object(media.os, 'link', side_effect=OSError('synthetic link failure')):
            with self.assertRaises(OSError): media.save(self.app, self.store, self.source, message, self.image(), self.now)
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])
        self.assertFalse((directory / self.media_id(message)).exists())

        message = self.message('dberror', offset=2); self.ingest(message); self.seed_job(message)
        with patch.object(self.store, '_message_upload', side_effect=sqlite3.OperationalError('synthetic db failure')):
            with self.assertRaises(sqlite3.OperationalError): media.save(self.app, self.store, self.source, message, self.image(), self.now)
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_attachments'), [])
        self.assertFalse((directory / self.media_id(message)).exists())

    def test_leftover_identical_file_is_reused_without_duplicate(self):
        message = self.message('crash'); self.ingest(message); self.seed_job(message)
        body = self.image()['data']; directory = self.data / 'uploads'; directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / self.media_id(message); target.write_bytes(body)
        with patch.object(media, 'fetch', side_effect=AssertionError('leftover file was refetched')):
            result = media.save(self.app, self.store, self.source, message, self.image(), self.now)
        self.assertEqual(result['state'], 'saved'); self.assertEqual(len(list(directory.iterdir())), 1)
        self.assertEqual(len(self.db_rows('SELECT * FROM uploads')), 1)
        with patch.object(media, 'config', return_value=self.settings()), patch.object(media, 'fetch', side_effect=AssertionError('saved image refetched')):
            self.assertEqual(media.run_one(self.app, self.store, self.now + dt.timedelta(minutes=1))['state'], 'idle')

    def test_missing_media_config_does_not_stop_text_agent(self):
        message = self.message('text', kind='text', unread=False); self.ingest(message)
        self.assertEqual(media.run_one(self.app, self.store, self.now)['state'], 'disabled')
        self.assertIsNone(self.store.message(dict(child_id='child-1', source_id=self.source['id'], message_id='text'), lambda row: dict(row))['media'])
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': []}):
            result = agent.run_once(self.app, self.now)
        self.assertGreaterEqual(result['processed'], 1)
        self.assertEqual(self.db_rows('SELECT processed FROM agent_messages')[0]['processed'], 1)

    def test_original_view_reports_current_collection_without_fetch_or_writes(self):
        message = self.message(); self.ingest(message)
        identity = dict(child_id='child-1', source_id=self.source['id'], message_id=message['id'])
        read = lambda: self.store.message(identity, lambda row: dict(row))['media']
        with patch.object(media, 'fetch', side_effect=AssertionError('opening a notice must not collect')):
            self.assertIn('未启用', read()['explanation'])
            self.assertEqual(self.db_rows('SELECT * FROM agent_media'), [])
            with patch.object(media, 'config', return_value=self.settings()):
                self.assertIn('尚未取得', read()['explanation'])
            with patch.object(media, 'config', return_value={**self.settings(), 'since': self.now + dt.timedelta(days=1)}):
                self.assertIn('时间范围', read()['explanation'])
            self.seed_job(message, 'error')
            with self.store._db() as c:
                c.execute("UPDATE agent_media SET attempts=1,error='process_timeout'")
            before = self.db_rows('SELECT * FROM agent_media')
            self.assertIn('未启用', read()['explanation'])
            self.assertIn('超时', read()['explanation'])
            self.assertEqual(read()['attempts'], 1)
            with patch.object(media, 'config', return_value=self.settings()):
                self.assertIn('超时', read()['explanation'])
                self.assertNotIn('未启用', read()['explanation'])
            with patch.object(media, 'config', side_effect=ValueError('PRIVATE_CONFIG_CANARY')):
                self.assertIn('配置待修复', read()['explanation'])
                self.assertNotIn('PRIVATE_CONFIG_CANARY', json.dumps(read()))
            self.write_config(enabled=False)
            self.assertIn('已暂停', read()['explanation'])
            self.write_config()
            self.assertEqual(self.db_rows('SELECT * FROM agent_media'), before)
            with patch.object(media, 'config', return_value=self.settings()):
                for state, error, expected in [('error', 'media_original_unavailable', '未在本机找到'),
                                               ('error', 'PRIVATE_ERROR_CANARY', '重试上限'),
                                               ('pending', '', '尚未取得')]:
                    with self.store._db() as c:
                        c.execute('UPDATE agent_media SET state=?,attempts=3,error=?', (state, error))
                    snapshot = self.db_rows('SELECT * FROM agent_media')
                    self.assertIn(expected, read()['explanation'])
                    self.assertNotIn('PRIVATE_ERROR_CANARY', json.dumps(read()))
                    self.assertEqual(self.db_rows('SELECT * FROM agent_media'), snapshot)
            upload = self.seed_upload()
            view = self.store.message_attachment({**identity, 'attachment_id': upload, 'action': 'attach'}, lambda row: dict(row))
            self.assertFalse(view['media']['explanation'])
            self.assertEqual([row['id'] for row in view['attachments']], [upload])

    def test_fetch_requires_exact_identity_original_variant_and_clean_helper_env(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-wx-') as directory:
            root = Path(directory).resolve(); attach = root / 'db' / 'msg' / 'attach'; attach.mkdir(parents=True)
            cli = root / 'wechat-cli'; cli.write_bytes(b'cli')
            config_path = root / 'wechat.json'; key = '0123456789abcdef'
            config_bytes = json.dumps({'image_key': key, 'image_xor_key': 7,
                'db_root': str(root / 'db')}).encode()
            config_path.write_bytes(config_bytes); config_path.chmod(0o600)
            settings = {'wechat_cli': str(cli), 'wechat_config': str(config_path),
                        'wechat_config_sha256': hashlib.sha256(config_bytes).hexdigest(),
                        'ffmpeg': '/usr/bin/false', 'since': self.now - dt.timedelta(days=1)}
            chat = '12345@chatroom'; source = {**self.source, 'id': 'wechat:' + chat}
            message = self.message('7'); message['time'] = '2026-03-01T00:00:00+08:00'
            original_body = b'encrypted-original'; original_md5 = 'a' * 32
            chat_root = attach / hashlib.md5(chat.encode()).hexdigest()
            month_dir = chat_root / '2026-03' / 'Img'; month_dir.mkdir(parents=True)
            original = month_dir / (original_md5 + '.dat'); original.write_bytes(original_body)
            previous_month = chat_root / '2026-02' / 'Img'; previous_month.mkdir(parents=True)
            (previous_month / (original_md5 + '.dat')).write_bytes(b'wrong-month')
            response = {
                'ok': True, 'data': {'query': {'chat': chat, 'type': 'image'}, 'media': [{
                    'id': {'talker': chat, 'local_id': 7}, 'kind': 'image', 'time_iso': message['time'],
                    'resources': [
                        {'resource_family': 'image', 'variant_code': 1, 'md5': 'b' * 32, 'size': 9},
                        {'resource_family': 'image', 'variant_code': 2, 'md5': original_md5,
                         'size': len(original_body)},
                    ],
                }]}}
            real_read = media.read_file
            captured_paths = []
            def invoke(value=response):
                process = Mock(return_value=json.dumps(value).encode())
                captured_paths.clear()
                def read(path, limit=media.MAX_BYTES, private=False):
                    if Path(path) == cli: return b'cli'
                    if Path(path) == config_path: return config_bytes
                    captured_paths.append(Path(path))
                    return real_read(path, limit, private)
                with patch.object(media, 'CLI_SHA256', hashlib.sha256(b'cli').hexdigest()), \
                     patch.object(media, 'read_file', side_effect=read), \
                     patch.object(media, 'bounded_process', process), \
                     patch.object(media, 'decrypt_v2', return_value=b'wxgf') as decrypt, \
                     patch.object(media, 'wxgf_first_frame', return_value={'data': b'png', 'width': 1, 'height': 1, 'first_frame_only': True}), \
                     patch.dict(media.os.environ, {'WX_KEY_BIN': 'inherited-secret', 'WX_MCP_CONFIG': 'alternate-config',
                                                   'WECHAT_CLI_IMAGE_KEY': 'inherited-image-key', 'WX_MCP_IMAGE_KEY': 'inherited-mcp-key'}, clear=False):
                    result = media.fetch(settings, source, message)
                    self.assertEqual(decrypt.call_args.args[0], original_body)
                    args = process.call_args.args[0]
                    self.assertEqual(args[-7:], ['--limit', '1', '--include-local-paths', 'false',
                                                  '--include-debug', 'true', '--strict-read-only'])
                    env = process.call_args.args[1]
                    self.assertEqual(env['WX_KEY_BIN'], '/usr/bin/false')
                    self.assertEqual(env['WECHAT_CLI_CONFIG'], str(config_path))
                    self.assertEqual(env['WX_MCP_CONFIG'], str(config_path))
                    self.assertNotIn('inherited-secret', env.values())
                    self.assertNotIn('WECHAT_CLI_IMAGE_KEY', env)
                    self.assertNotIn('WX_MCP_IMAGE_KEY', env)
                return result, process

            result, process = invoke()
            self.assertEqual(result['data'], b'png'); self.assertEqual(process.call_count, 1)
            self.assertEqual(captured_paths, [original])
            for mutate, code in (
                    (lambda value: value['data']['media'][0]['id'].update(talker='other@chatroom'), 'media_message_mismatch'),
                    (lambda value: value['data']['media'][0]['id'].update(local_id=8), 'media_message_mismatch'),
                    (lambda value: value['data']['media'][0].update(kind='video'), 'media_message_mismatch'),
                    (lambda value: value['data']['media'][0].update(time_iso='2025-01-01T00:00:00+08:00'), 'media_message_mismatch'),
            ):
                bad = json.loads(json.dumps(response)); mutate(bad)
                with self.assertRaises(media.MediaError) as raised:
                    invoke(bad)
                self.assertEqual(raised.exception.code, code)

            outside = root / 'outside.dat'; outside.write_bytes(b'encrypted-outside')
            original.unlink(); original.symlink_to(outside)
            with self.assertRaises(media.MediaError) as raised: invoke()
            self.assertEqual(raised.exception.code, 'media_path_rejected')
            original.unlink()

            # A valid-looking file in another chat's directory is never a fallback.
            other_chat = attach / hashlib.md5(b'54321@chatroom').hexdigest() / '2026-03' / 'Img'
            other_chat.mkdir(parents=True)
            other_file = other_chat / (original_md5 + '.dat'); other_file.write_bytes(original_body)
            with self.assertRaises(media.MediaError) as raised:
                invoke()
            self.assertEqual(raised.exception.code, 'media_original_unavailable')
            self.assertNotIn(other_file, captured_paths)
            other_file.unlink(); other_chat.rmdir(); (other_chat.parent).rmdir(); (other_chat.parent.parent).rmdir()
            original.write_bytes(original_body)

            # Multiple deterministic suffixes with the same size remain ambiguous.
            alternate = month_dir / (original_md5 + '_h.dat'); alternate.write_bytes(original_body)
            with self.assertRaises(media.MediaError) as raised: invoke()
            self.assertEqual(raised.exception.code, 'media_original_unavailable')
            alternate.unlink()

            for mutate in (
                    lambda value: value['data']['media'][0].update(resources=[]),
                    lambda value: value['data']['media'][0]['resources'][1].update(md5='not-an-md5'),
                    lambda value: value['data']['media'][0]['resources'][1].update(size=len(original_body) + 1),
            ):
                bad = json.loads(json.dumps(response)); mutate(bad)
                with self.assertRaises(media.MediaError) as raised: invoke(bad)
                self.assertEqual(raised.exception.code, 'media_original_unavailable')

            # The CLI hash and private configuration are checked before any metadata call.
            with patch.object(media, 'CLI_SHA256', '0' * 64), patch.object(media, 'bounded_process') as process:
                with self.assertRaises(media.MediaError) as raised: media.fetch(settings, source, message)
                self.assertEqual(raised.exception.code, 'media_cli_unverified'); process.assert_not_called()
            changed = {**settings, 'wechat_config_sha256': '0' * 64}
            with patch.object(media, 'CLI_SHA256', hashlib.sha256(b'cli').hexdigest()), patch.object(media, 'bounded_process') as process:
                with self.assertRaises(media.MediaError) as raised: media.fetch(changed, source, message)
                self.assertEqual(raised.exception.code, 'media_config_changed'); process.assert_not_called()


    def test_background_draft_preserves_facts_reuses_model_budget_and_hides_stale_originals(self):
        import family_llm
        message=self.message();self.ingest(message);ident=self.seed_upload()
        self.store.message_attachment(dict(child_id='child-1',source_id=self.source['id'],message_id='1',
            attachment_id=ident,action='attach'),lambda row:dict(row))
        result=dict(title='虚构听写结果',subject='英语',score=None,total=None,note='表中目标行标记F；数值未知。',uncertainties=['具体错词尚未提供'])
        original=self.db_rows('SELECT payload FROM agent_messages');before=self.db_rows('SELECT * FROM records')
        with patch.object(family_llm,'extract_draft',return_value=result) as model, patch.object(family_llm,'_chat_json',return_value={'proposals':[]}):
            agent.run_once(self.app,self.now)
            model.assert_called_once();self.assertEqual(model.call_args.kwargs['target_child'],'示例甲')
            self.assertEqual(model.call_args.kwargs['data_path'],self.data)
            view=self.store.message(dict(child_id='child-1',source_id=self.source['id'],message_id='1'),dict)['material_draft']
            self.assertEqual(view['state'],'ready');self.assertEqual(view['draft'],result);self.assertEqual(view['upload_ids'],[ident])
            agent.run_once(self.app,self.now+dt.timedelta(minutes=1));self.assertEqual(model.call_count,1)
            self.assertEqual(self.db_rows('SELECT * FROM records'),before);self.assertEqual(self.db_rows('SELECT * FROM manual_tasks'),[])
            self.assertEqual(self.db_rows('SELECT payload FROM agent_messages'),original)
            file=self.data/'uploads'/ident;body=file.read_bytes();file.write_bytes(body[:-1]+bytes([body[-1]^1]))
            self.assertEqual(self.store.message(dict(child_id='child-1',source_id=self.source['id'],message_id='1'),dict)['material_draft']['state'],'pending')
            self.store.message_attachment(dict(child_id='child-1',source_id=self.source['id'],message_id='1',attachment_id=ident,action='detach'),dict)
            self.assertIsNone(self.store.message(dict(child_id='child-1',source_id=self.source['id'],message_id='1'),dict)['material_draft'])
            self.assertEqual(model.call_count,1)  # Opening/removing never calls a model.

    def test_draft_retries_are_bounded_and_only_the_selected_failed_job_is_retried(self):
        import family_llm
        message=self.message();self.ingest(message);ident=self.seed_upload()
        self.store.message_attachment(dict(child_id='child-1',source_id=self.source['id'],message_id='1',attachment_id=ident,action='attach'),dict)
        with patch.object(family_llm,'extract_draft',side_effect=family_llm.LLMDraftError('synthetic failure')) as model:
            for minute in [0,1,6,7,17,40]:media.prepare_draft(self.store,self.now+dt.timedelta(minutes=minute))
            self.assertEqual(model.call_count,3)
        view=self.store.message(dict(child_id='child-1',source_id=self.source['id'],message_id='1'),dict)['material_draft'];self.assertEqual(view['state'],'error')
        other=self.store._job('other-job',{},self.now,model=True);self.store._fail('other-job',self.now,fingerprint=other)
        self.store.act(dict(action='retry',id=view['job_id']))
        rows=self.db_rows('SELECT id,attempts FROM agent_jobs')
        self.assertEqual(next(r['attempts'] for r in rows if r['id']==view['job_id']),0)
        self.assertEqual(next(r['attempts'] for r in rows if r['id']=='other-job'),1)
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_drafts'),[])

    def test_draft_rechecks_source_and_attachment_ownership_after_inference(self):
        import family_llm
        message=self.message();self.ingest(message);ident=self.seed_upload()
        self.store.message_attachment(dict(child_id='child-1',source_id=self.source['id'],message_id='1',attachment_id=ident,action='attach'),dict)
        result=dict(title='虚构草稿',subject='',score=None,total=None,note='待核对',uncertainties=[])
        def change(*args,**kwargs):
            self.store.message_attachment(dict(child_id='child-1',source_id=self.source['id'],message_id='1',attachment_id=ident,action='detach'),dict)
            return result
        with patch.object(family_llm,'extract_draft',side_effect=change):
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=1))
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_drafts'),[])
        self.store.message_attachment(dict(child_id='child-1',source_id=self.source['id'],message_id='1',attachment_id=ident,action='attach'),dict)
        self.write_config(enabled=False)
        with patch.object(family_llm,'extract_draft') as model:
            self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=10))['used'],0);model.assert_not_called()
        self.assertEqual(self.store.message(dict(child_id='child-1',source_id=self.source['id'],message_id='1'),dict)['material_draft']['state'],'unavailable')
        with self.assertRaises(agent.AgentError):self.store.message(dict(child_id='child-2',source_id=self.source['id'],message_id='1'),dict)

    def school_fragment(self, text):
        import base64, family_qq_capture as qq
        self.source=dict(id='qq:123456',platform='qq',child_id='child-1',name='虚构QQ班级',cursor='100',enabled=True);self.write_config()
        reply=qq.save_fragment(self.store,dict(source_id=self.source['id'],child_id='child-1',captured_at='2026-02-10T08:06:00+08:00',
            text='截图本机文字识别（可能有误，请对照原图）：\n'+text,png=base64.b64encode(png()).decode()))
        return dict(child_id='child-1',source_id=self.source['id'],message_id=reply['message_id'])

    def link(self, keys, ident, action='attach'):
        self.store.message_attachment(keys|dict(attachment_id=ident,action=action),dict)

    def facts(self):
        with self.store._db() as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('agent_message_drafts','agent_jobs') ORDER BY name")]
            return {t:[tuple(r) for r in c.execute('SELECT * FROM "'+t+'"')] for t in tables}

    def test_school_material_reads_only_linked_extra_originals_once_and_leaves_facts(self):
        import family_llm
        keys=self.school_fragment('英语：按所附范文完成仿写。');view=lambda:self.store.message(keys,dict)['material_draft']
        with self.store._db() as c:
            c.execute("INSERT INTO manual_tasks(id,child,title,due,original_status,source,action) VALUES('task-1','child-1','虚构学校任务','2026-02-11','待完成','Agent建议:agent-x','家长已确认完成')")
            c.execute("INSERT INTO task_updates VALUES('task-1','已完成','家长确认',?)",(self.now.isoformat(),))
        result=dict(title='虚构仿写资料',note='范文与题目为参考材料；未见孩子作答。',uncertainties=['发送日期未知'])
        with patch.object(family_llm,'extract_draft',return_value=result) as model:
            self.assertIsNone(view());self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=0,failed=0))
            self.link(keys,self.seed_upload('d'*32,png()))  # The same capture uploaded again is not an original.
            self.assertIsNone(view());self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=0,failed=0));model.assert_not_called()
            extra=self.seed_upload('b'*32,png(64,96));self.link(keys,extra)
            self.assertEqual((view()['state'],view()['kind']),('pending','school_material'))
            facts=self.facts();saved=self.db_rows('SELECT payload FROM agent_messages')
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=0))
            text,images=model.call_args.args[:2];context=json.loads(text)
            self.assertEqual(context['source_message'],json.loads(saved[0]['payload']))
            self.assertEqual(context['source_message']['time'],'');self.assertIn('captured_at',context['source_message'])
            self.assertEqual([i['data'] for i in images],[png(64,96)])  # Neither copy of the capture is sent as an original.
            self.assertIs(model.call_args.kwargs['school_material'],True);self.assertEqual(model.call_args.kwargs['target_child'],'示例甲')
            ready=view();self.assertEqual((ready['state'],ready['kind'],ready['draft'],ready['upload_ids']),('ready','school_material',result,[extra]))
            self.assertEqual(json.loads(self.db_rows('SELECT payload FROM agent_message_drafts')[0]['payload'])['kind'],'school_material')
            self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=1)),dict(used=0,failed=0));self.assertEqual(model.call_count,1)
            self.assertEqual(self.facts(),facts);self.assertEqual(self.db_rows('SELECT payload FROM agent_messages'),saved)
            with self.assertRaises(agent.AgentError):self.store.message(keys|dict(child_id='child-2'),dict)
            self.write_config(enabled=False);self.assertEqual(view()['state'],'unavailable')
            self.write_config();self.assertEqual(view()['state'],'ready')
            legacy=dict(title='虚构旧草稿',subject='英语',score=95,total=100,note='旧结构',uncertainties=[])
            with self.store._db() as c:c.execute('UPDATE agent_message_drafts SET payload=?',(json.dumps(legacy),))
            self.assertEqual(view()['state'],'pending')  # A saved draft of another type is never shown.
            second=self.seed_upload('c'*32,png(32,48));self.link(keys,second);self.assertEqual(view()['state'],'pending')
            self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=2)),dict(used=1,failed=0))
            self.assertEqual(len(model.call_args.args[1]),2);self.assertEqual(view()['upload_ids'],[extra,second])
            self.link(keys,second,'detach');self.assertEqual(view()['state'],'pending')
            file=self.data/'uploads'/('e'*32);file.write_bytes(b'%PDF-synthetic')
            with self.store._db() as c:
                c.execute('INSERT INTO uploads(id,name,size,mime,created) VALUES(?,?,?,?,?)',('e'*32,'synthetic.pdf',14,'application/pdf',self.now.isoformat()))
            self.link(keys,'e'*32);calls=model.call_count
            self.assertEqual((view()['state'],view()['kind']),('unavailable','school_material'));self.assertIn('PDF',view()['explanation'])
            self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=3)),dict(used=0,failed=0));self.assertEqual(model.call_count,calls)
            self.link(keys,'e'*32,'detach');self.link(keys,extra,'detach');self.assertIsNone(view())  # Capture only: nothing is shown again.
        self.assertEqual(self.db_rows('SELECT * FROM records'),[]);self.assertEqual(len(self.db_rows('SELECT * FROM manual_tasks')),1)

    def test_school_material_rejects_fact_fields_and_changes_during_inference(self):
        import family_llm
        result=dict(title='虚构成绩表资料',note='成绩表属于参考材料。',uncertainties=[])
        keys=self.school_fragment('数学：订正所附试卷。');self.link(keys,self.seed_upload('b'*32,png(64,96)));facts=self.facts()
        for minute,bad in [(0,result|dict(score=95,total=100)),(6,dict(title='虚构',subject='数学',score=95,total=100,note='旧结构',uncertainties=[]))]:
            with patch.object(family_llm,'extract_draft',return_value=bad):
                self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=minute)),dict(used=1,failed=1))
        view=self.store.message(keys,dict)['material_draft'];self.assertEqual((view['state'],view['kind']),('error','school_material'))
        self.link(keys,'b'*32,'detach')
        changes=dict(detach=lambda k,i:self.link(k,i,'detach'),disable=lambda k,i:self.write_config(enabled=False),
                     rebind=lambda k,i:self.write_config(child_id='child-2'))
        for index,(name,change) in enumerate(changes.items()):
            self.write_config();keys=self.school_fragment('虚构通知：'+name);ident=self.seed_upload(str(index)*32,png(40+index,50));self.link(keys,ident)
            def during(*args,change=change,keys=keys,ident=ident,**kwargs):
                change(keys,ident);return result
            with patch.object(family_llm,'extract_draft',side_effect=during) as model:
                self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=1),name);model.assert_called_once()
            try:self.assertNotEqual((self.store.message(keys,dict)['material_draft'] or {}).get('state'),'ready',name)
            except agent.AgentError:pass
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_drafts'),[]);self.write_config()
        setup=('uploads','agent_messages','agent_message_attachments','agent_sources','agent_media')  # Changed by this test's own links.
        self.assertEqual({k:v for k,v in self.facts().items() if k not in setup},{k:v for k,v in facts.items() if k not in setup})

    def seed_docx(self, ident, body, name='虚构仿写要求.docx'):
        self.seed_upload(ident, body)
        with self.store._db() as c:
            c.execute('UPDATE uploads SET name=?,mime=? WHERE id=?', (name, media.DOCX_MIME, ident))
        return ident

    def test_docx_text_reads_utf8_paragraphs_and_table_rows_or_fails_closed(self):
        self.assertEqual(media.docx_text(docx(DOCX_BODY)), DOCX_TEXT)
        self.assertEqual(media.docx_text(docx(para('字' * media.DOCX_LIMITS['chars']))), '字' * media.DOCX_LIMITS['chars'])
        # A style that hides text but is not in effect for the body does not block reading; an explicit "off" is plain text.
        self.assertEqual(media.docx_text(docx(para('可见', '<w:rPr><w:rStyle w:val="Plain"/></w:rPr>'), styles(
            _HIDDEN + '<w:style w:type="character" w:styleId="Plain"><w:rPr><w:strike w:val="0"/></w:rPr></w:style>'))), '可见')
        for name, (body, code) in unreadable_docx().items():
            with self.subTest(name):
                with self.assertRaises(media.MediaError) as caught: media.docx_text(body)
                self.assertEqual(caught.exception.code, code)

    def test_school_material_docx_only_reaches_model_apart_from_notice(self):
        import family_llm
        keys=self.school_fragment('英语：按所附文档完成仿写。');view=lambda:self.store.message(keys,dict)['material_draft']
        result=dict(title='虚构仿写要求',note='文档列出仿写步骤与字数要求；未见孩子作答。',uncertainties=['发送日期未知'])
        with patch.object(family_llm,'extract_draft',return_value=result) as model:
            self.assertIsNone(view());self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=0,failed=0));model.assert_not_called()  # Screenshot alone.
            ident=self.seed_docx('f'*32,docx(DOCX_BODY));self.link(keys,ident)
            self.assertEqual((view()['state'],view()['kind']),('pending','school_material'));facts=self.facts()
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=1,failed=0));model.assert_called_once()
            text,images=model.call_args.args[:2];context=json.loads(text)
            self.assertEqual(images,[]);self.assertEqual(set(context),{'source_message','source_name'})
            self.assertNotIn('仿写五句',text);self.assertNotIn('docx',text)  # The notice stays apart from the original's name and text.
            self.assertEqual(model.call_args.kwargs['documents'],[dict(name='虚构仿写要求.docx',text=DOCX_TEXT)])
            self.assertIs(model.call_args.kwargs['school_material'],True);self.assertEqual(model.call_args.kwargs['target_child'],'示例甲')
            ready=view();self.assertEqual((ready['state'],ready['kind'],ready['draft'],ready['upload_ids']),('ready','school_material',result,[ident]))
            self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=1)),dict(used=0,failed=0));self.assertEqual(model.call_count,1)
            self.assertEqual(self.facts(),facts)
            extra=self.seed_upload('b'*32,png(64,96));self.link(keys,extra);self.assertEqual(view()['state'],'pending')  # A new original is a new draft.
            self.assertEqual(media.prepare_draft(self.store,self.now+dt.timedelta(minutes=2)),dict(used=1,failed=0))
            self.assertEqual([i['data'] for i in model.call_args.args[1]],[png(64,96)]);self.assertEqual(len(model.call_args.kwargs['documents']),1)
        self.assertEqual(self.db_rows('SELECT * FROM records'),[])

    def test_unreadable_or_misplaced_docx_never_reaches_model(self):
        import family_llm
        with patch.object(family_llm,'extract_draft') as model:
            for index,(name,(body,code)) in enumerate(unreadable_docx().items()):
                keys=self.school_fragment('虚构通知：'+name);ident=self.seed_docx(format(index,'032x'),body);self.link(keys,ident)
                good=self.seed_upload(format(index+256,'032x'),png(40+index,50));self.link(keys,good)  # A readable image is not sent alone either.
                view=self.store.message(keys,dict)['material_draft']
                self.assertEqual((view['state'],view['kind'],'draft' in view),('unavailable','school_material',False),name)
                self.assertIn('12000字' if code=='draft_text_too_long' else '本次未读取任何原件',view['explanation'],name)
                self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=0,failed=0),name)
                self.link(keys,ident,'detach');self.link(keys,good,'detach')
            keys=self.school_fragment('虚构通知：两份文档合计过长')  # Each readable, together beyond the text limit: never cut to fit.
            for ident in ('e'*32,'d'*32):self.link(keys,self.seed_docx(ident,docx(para('字'*6000+ident[0]))))
            view=self.store.message(keys,dict)['material_draft'];self.assertEqual(view['state'],'unavailable');self.assertIn('12000字',view['explanation'])
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=0,failed=0))
            self.source=dict(id='wechat:12345@chatroom',platform='wechat',child_id='child-1',name='虚构班级',cursor='10',enabled=True);self.write_config()
            self.ingest(self.message());keys=dict(child_id='child-1',source_id=self.source['id'],message_id='1')
            self.link(keys,self.seed_docx('c'*32,docx(DOCX_BODY)))  # Ordinary learning material accepts images only.
            view=self.store.message(keys,dict)['material_draft'];self.assertEqual(view['state'],'unavailable');self.assertIn('JPG、PNG、WebP',view['explanation'])
            self.assertEqual(media.prepare_draft(self.store,self.now),dict(used=0,failed=0));model.assert_not_called()
        self.assertEqual(self.db_rows('SELECT * FROM agent_message_drafts'),[]);self.assertEqual(self.db_rows('SELECT * FROM records'),[])


import sys
import family_print

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


def rezip(body,name,data):
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(body)) as src,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():dst.writestr(info.filename,data if info.filename==name else src.read(info))
    return out.getvalue()


class DocxPdfTests(unittest.TestCase):
    """docx_pdf renders one real DOCX through a synthetic soffice script; nothing is stored, queued or fetched."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='synthetic-docx-pdf-');self.addCleanup(self.tmp.cleanup);self.data=Path(self.tmp.name).resolve()
        self.pdf=family_print.image_pdf(png());(self.data/'expected.pdf').write_bytes(self.pdf)
        rels=_RELS%('<Relationship Id="rId5" Type="%simage" Target="media/image1.png"/>'%_REL_TYPE)
        self.body=docx(DOCX_BODY+'<w:p><w:r><w:drawing/></w:r></w:p><w:p><m:oMath><m:r><m:t>x+1</m:t></m:r></m:oMath></w:p>',
                       [('word/media/image1.png',png()),('word/media/photo.JPG',b'\xff\xd8\xff\xe0synthetic'),('word/_rels/document.xml.rels',rels)])

    def fake(self,mode):
        path=self.data/('fake-%s.py'%mode);path.write_text(FAKE%(sys.executable,mode,str(self.data/(mode+'.json')),str(self.data/'expected.pdf')));path.chmod(0o755);return str(path)

    def test_docx_pdf_renders_pictures_tables_and_formulas_in_a_throwaway_profile(self):
        with self.assertRaises(media.MediaError) as caught:media.docx_text(self.body)  # The text reader still refuses pictures.
        self.assertEqual(caught.exception.code,'draft_docx_unsupported')
        self.assertEqual(media.docx_pdf(self.body,soffice=self.fake('ok')),self.pdf)
        log=json.loads((self.data/'ok.json').read_text())
        self.assertFalse(Path(log['outdir']).exists());self.assertEqual((Path(log['argv'][-1]).name,log['source']),('source.docx','PK'))
        self.assertEqual(log['argv'][1:5],['--headless','--convert-to','pdf','--outdir']);self.assertIn('<value>3</value>',log['xcu'])
        self.assertTrue(log['argv'][0].startswith('-env:UserInstallation=file:///'+log['outdir'].lstrip('/')))
        self.assertEqual(media.docx_text(docx(DOCX_BODY)),DOCX_TEXT)  # Plain text reading is unchanged.
        with patch('shutil.which',return_value=None),self.assertRaises(media.MediaError) as caught:media.docx_pdf(self.body)
        self.assertEqual(caught.exception.code,'process_unavailable')
        for mode,code in (('fail','process_failed'),('none','process_failed'),('text','process_failed')):
            with self.assertRaises(media.MediaError) as caught:media.docx_pdf(self.body,soffice=self.fake(mode))
            self.assertEqual(caught.exception.code,code,mode)
        with patch.object(media,'MAX_BYTES',8000),self.assertRaises(media.MediaError) as caught:media.docx_pdf(self.body,soffice=self.fake('big'))
        self.assertEqual(caught.exception.code,'process_output_limit')
        with patch.object(media,'DOCX_PDF_TIMEOUT',1),self.assertRaises(media.MediaError) as caught:media.docx_pdf(self.body,soffice=self.fake('sleep'))
        self.assertEqual(caught.exception.code,'process_timeout')

    def test_docx_pdf_refuses_binary_macro_object_external_and_damaged_inputs_without_a_process(self):
        cases={name:(body,code) for name,(body,code) in unreadable_docx().items() if code=='draft_docx_rejected' and name!='oversize_member'}
        bad,no='draft_docx_rejected','draft_docx_unsupported'
        cases.update(empty=(b'',bad),too_large=(b'PK'+b'\0'*media.MAX_BYTES,'media_too_large'),
                     ole_binary=(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'+b'\0'*64,bad),
                     embedding=(docx(para('正文'),[('word/embeddings/oleObject1.bin',b'\xd0\xcf\x11\xe0')]),bad),
                     activex=(docx(para('正文'),[('word/activeX/activeX1.xml','<x/>')]),bad),
                     executable=(docx(para('正文'),[('word/media/run.exe',b'MZ')]),bad),
                     fake_png=(docx(para('正文'),[('word/media/image1.png',b'\xd7\xcd\xc6\x9a wmf')]),bad),
                     object_element=(docx('<w:p><w:r><w:object><o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" ProgID="Package"/></w:object></w:r></w:p>'+para('正文')),bad),
                     macro_type=(rezip(docx(para('正文')),'[Content_Types].xml',_TYPES.replace('document.main+xml','document.macroEnabled.main+xml')),bad),
                     oversize_member=(docx(para('正文'),[('word/big.xml','0'*(media.DOCX_PDF_LIMITS['member']+1))]),bad),
                     too_many=(docx(para('正文'),[('word/p%d.xml'%i,'<a/>') for i in range(media.DOCX_PDF_LIMITS['entries'])]),bad),
                     wmf=(docx(para('图'),[('word/media/image2.wmf',b'\xd7\xcd\xc6\x9a')]),no),
                     font=(docx(para('正文'),[('word/fonts/font1.odttf',b'x')]),no))
        with patch('subprocess.Popen') as popen:
            for name,(body,code) in cases.items():
                with self.subTest(name):
                    with self.assertRaises(media.MediaError) as caught:media.docx_pdf(body,soffice=self.fake('ok'))
                    self.assertEqual(caught.exception.code,code)
            popen.assert_not_called()
        self.assertFalse((self.data/'ok.json').exists())


if __name__ == '__main__':
    unittest.main()

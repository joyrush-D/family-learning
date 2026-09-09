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

import family_agent as agent
import family_media as media
import family_review


def png(width=96, height=64):
    rows = b''.join(b'\0' + bytes((40, 180, 220)) * width for _ in range(height))
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')


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
        with patch.object(agent.family_llm, '_chat_json', return_value={'proposals': []}):
            result = agent.run_once(self.app, self.now)
        self.assertGreaterEqual(result['processed'], 1)
        self.assertEqual(self.db_rows('SELECT processed FROM agent_messages')[0]['processed'], 1)

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


if __name__ == '__main__':
    unittest.main()

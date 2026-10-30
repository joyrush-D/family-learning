"""A school source's failed read keeps its own fixed reason along CLI -> collector -> Store.ingest -> snapshot.

All accounts, groups, tokens and messages are fictional. The QQ reader's transport is a fake opener; the real
family_qq_napcat.py subprocess runs only on fictional config files that fail before any request; no real service,
model, collector process, household path or device is used. --serve-failed / --serve-recovered serve the whole fictional
2026-11-04 day (test_image_original_date_scope's six school items and the child's own oral correction) with one more
QQ source of the same child whose latest read failed (then recovered) through the real collector round.
"""
import base64
import copy
import datetime as dt
import http.client
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import family_agent as agent
import family_collect as collect
import family_qq_napcat as napcat
import test_agent as fixtures
from test_collect import qq_envelope, qq_event, qq_ready

ROOT = Path(__file__).resolve().parent
QQ = dict(id='qq:10002', platform='qq', child_id='child-1', name='虚构QQ班级群', cursor='100', enabled=True)
SECRET = b'FICTIONAL-TOKEN-SECRET-0123456789 /Users/fictional/private/qq-napcat.json group 10002 account 20001'
SUFFIX = '；本次未同步新消息，上次成功记录保留。'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRZkAAAAASUVORK5CYII=')
EXPECTED = {'private_config_required': '本机QQ读取配置文件不可用', 'invalid_config': '本机QQ读取配置未通过核对',
            'bridge_invalid': '本机QQ读取配置未通过核对', 'onebot_config_invalid': '本机QQ接口配置未通过核对',
            'qq_source_unavailable': '本机QQ接口已响应，但未确认配置的账号与班级群',
            'qq_endpoint_refused': '本机QQ接口未接受连接', 'qq_endpoint_disconnected': '本机QQ接口连接中断，未返回结果',
            'qq_endpoint_auth_rejected': '本机QQ接口拒绝了本次访问授权'}
UNPROVEN = ('扫码', '登录', '过期', '权限')  # no fixed code proves any of these


def envelope(code):
    return (json.dumps({'status': 'error', 'error': code}) + '\n').encode()


class StoreClient:
    """The collector's app calls answered in process by the real Store, as app.py's two plan routes and ingest do."""
    def __init__(self, store, at=None):
        self.store, self.at, self.posts = store, at, []

    def request(self, path, body=None, token='', deadline=None):
        assert path in ('/api/agent/collector', '/api/agent/fragment/plan'), path
        return self.store.collector_plan(self.at, fragment=path.endswith('/fragment/plan'))

    def ingest(self, body, deadline=None):
        self.posts.append(copy.deepcopy(body))
        return self.store.ingest(body)


class QQOnlyClient(StoreClient):
    """The served day's own WeChat source is not read again; only the added QQ source is."""
    def request(self, path, body=None, token='', deadline=None):
        plan = super().request(path)
        return dict(plan, sources=[s for s in plan['sources'] if s['id'] == QQ['id']])


def fake_cli(code=None, rows=(), stdout=None, returncode=1):
    """subprocess.run for the real cli_json: a fixed failure (or given bytes), else status + one native page."""
    calls = []

    def run(args, **kwargs):
        assert kwargs['stdin'] is subprocess.DEVNULL and kwargs['capture_output'] and kwargs['check'] is False
        calls.append(list(args[1:3] if args[0] == sys.executable else args[:2]))
        if code or stdout is not None:
            return subprocess.CompletedProcess(args, returncode, envelope(code) if stdout is None else stdout, SECRET)
        value = qq_ready() if args[2] == 'status' else qq_envelope([dict(r, group_id='10002') for r in rows])
        return subprocess.CompletedProcess(args, 0, json.dumps(value).encode(), b'')
    return run, calls


def rows(*seqs):
    return [qq_event(seq, ident=str(99 + seq), text='虚构QQ群通知 %d' % seq) for seq in seqs]


class SourceFailureContractTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AgentTests(methodName='runTest'); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store, self.app, self.data = self.fixture.store, self.fixture.app, self.fixture.data
        self.wechat = dict(self.fixture.source, id='10001@chatroom')
        self.sources([QQ, self.wechat])
        self.config = dict(app_url='http://127.0.0.1:8765', qq_cli=str(ROOT / 'family_qq_napcat.py'), wechat_cli='/fictional/wechat-cli')

    def sources(self, rows_):
        (self.data / 'agent.json').write_text(json.dumps({'enabled': True, 'sources': rows_}))

    def round(self, run, *, later=True, **kwargs):
        client = StoreClient(self.store, dt.datetime.now(agent.TZ) + dt.timedelta(hours=2) if later else None)
        with patch.object(collect.subprocess, 'run', side_effect=run):
            return collect.run_once(self.config, client, **kwargs), client

    def state(self):
        with self.app.connect() as c:
            return ([tuple(r) for r in c.execute('SELECT source_id,id,payload,processed FROM agent_messages ORDER BY source_id,id')],
                    [tuple(r) for r in c.execute('SELECT * FROM agent_message_attachments ORDER BY message_id')],
                    [tuple(r) for r in c.execute('SELECT * FROM agent_jobs ORDER BY id')])

    def source(self, ident=QQ['id']):
        return next(s for s in self.store.snapshot()['sources'] if s['id'] == ident)

    def seed(self):
        """One natural QQ success saving message 101, then an original attached to it."""
        run, _ = fake_cli(rows=rows(1, 2))
        results, _ = self.round(run, later=False)
        self.assertEqual(results[0]['status'], 'ingested', results)
        upload = self.app.save_upload(io.BytesIO(PNG), len(PNG), 'fictional-qq-notice.png')
        self.store.message_attachment(dict(child_id='child-1', source_id=QQ['id'], message_id='101',
                                           attachment_id=upload['id'], action='attach'), self.app.upload_info)
        saved = self.source()
        self.assertEqual((saved['cursor'], saved['error']), ('101', ''))
        return saved

    def test_each_fixed_reader_code_reaches_only_its_qq_source_and_keeps_saved_state(self):
        self.sources([QQ])
        before = self.seed(); kept = self.state()
        for code in sorted(collect.QQ_PRODUCER_ERRORS):
            with self.subTest(code=code):
                run, calls = fake_cli(code)
                results, client = self.round(run)
                self.assertEqual(calls, [[str(ROOT / 'family_qq_napcat.py'), 'status']])  # one read, no retry
                self.assertEqual((results[0]['status'], results[0]['error']), ('read_error', code))
                body, = client.posts
                self.assertEqual((body['messages'], body['expected_cursor'], body['cursor'], body['error']), ([], '101', '101', code))
                saved = self.source()
                self.assertEqual(saved['error'], EXPECTED[code] + SUFFIX)
                self.assertFalse([w for w in UNPROVEN if w in saved['error']], saved['error'])
                self.assertEqual((saved['cursor'], saved['last_success'], saved['last_message_time']),
                                 ('101', before['last_success'], before['last_message_time']))
                self.assertEqual(self.state(), kept)
                self.assertNotIn('FICTIONAL-TOKEN-SECRET', json.dumps(self.store.snapshot(), ensure_ascii=False))

    def test_a_wechat_source_never_takes_a_qq_reader_code(self):
        self.store.ingest(dict(source_id=self.wechat['id'], expected_cursor='10', cursor='10', checked_at=dt.datetime.now(agent.TZ).isoformat(),
                               last_message_time='', messages=[], error=''))
        for code in ('qq_endpoint_refused', 'private_config_required'):
            with self.subTest(code=code):
                self.sources([self.wechat])
                run, calls = fake_cli(code)
                results, client = self.round(run)
                self.assertEqual(calls, [['/fictional/wechat-cli', 'history']])
                self.assertEqual(client.posts[0]['error'], 'cli_read_failed')
                self.assertEqual(self.source(self.wechat['id'])['error'], '本机读取工具未能完成读取' + SUFFIX)
                # Even a fixed QQ code posted for WeChat gets only the shared text.
                self.store.ingest(dict(source_id=self.wechat['id'], expected_cursor='10', cursor='10', checked_at=dt.datetime.now(agent.TZ).isoformat(),
                                       last_message_time='', messages=[], error=code))
                self.assertEqual(self.source(self.wechat['id'])['error'], '本次消息读取未通过核对' + SUFFIX)

    def test_unknown_malformed_extra_oversized_or_secret_outputs_stay_generic(self):
        self.sources([QQ]); self.seed()
        padded = b'{"status":"error","error":"qq_endpoint_refused"}' + b' ' * collect.MAX_PRODUCER_ERROR
        cases = [(envelope('needs_scan_login'), 1), (envelope('qq_login_expired'), 1), (envelope('qq_read_failed'), 1),
                 (b'{"status":"error","error":"qq_endpoint_refused","detail":"' + SECRET + b'"}', 1),
                 (b'{"status":"error","error":"qq_endpoint_refused"', 1), (b'\xff\xfe' + SECRET, 1), (padded, 1),
                 (envelope('qq_endpoint_refused'), 2), (envelope('qq_endpoint_refused'), -9),
                 (b'{"status":"failed","error":"qq_endpoint_refused"}', 1), (b'{"status":"error","error":["qq_endpoint_refused"]}', 1),
                 (b'["error","qq_endpoint_refused"]', 1), (b'', 1), (SECRET, 1),
                 (json.dumps({'status': 'error', 'error': SECRET.decode()}).encode(), 1)]
        for stdout, code in cases:
            with self.subTest(stdout=stdout[:60], code=code):
                result = subprocess.CompletedProcess([], code, stdout, envelope('qq_endpoint_refused'))  # stderr is never read
                with patch.object(collect.subprocess, 'run', return_value=result):
                    with self.assertRaisesRegex(collect.CollectError, '^cli_read_failed$') as raised:
                        collect.cli_json(['fictional'], timeout=1)
                self.assertNotIsInstance(raised.exception, collect.ProducerError)
                run, calls = fake_cli(stdout=stdout, returncode=code)
                results, _ = self.round(run)
                self.assertEqual((results[0]['error'], len(calls)), ('cli_read_failed', 1))
                saved = self.source()
                self.assertEqual(saved['error'], '本机读取工具未能完成读取' + SUFFIX)
                self.assertNotIn('FICTIONAL', json.dumps(self.store.snapshot(), ensure_ascii=False))
        # A successful exit is still parsed only as the reader's normal reply; a fixed error envelope there is no success.
        run, _ = fake_cli(stdout=envelope('qq_endpoint_refused'), returncode=0)
        self.assertEqual(self.round(run)[0][0]['error'], 'qq_status_failed')

    def test_parent_check_completes_read_error_once_and_next_natural_read_resumes_the_old_cursor(self):
        self.sources([QQ]); before = self.seed()
        self.store.request_collection_check(dt.datetime.now(agent.TZ))
        plan = self.store.collector_plan()['sources']
        self.assertEqual([(s['id'], s['cursor']) for s in plan], [(QQ['id'], '101')]); check_id = plan[0]['check_id']
        kept = self.state()
        run, calls = fake_cli('qq_endpoint_refused')
        results, client = self.round(run, later=False)
        self.assertEqual((len(calls), client.posts[0]['check_id'], results[0]['status']), (1, check_id, 'read_error'))
        saved = self.source()
        self.assertEqual((saved['collection_check']['status'], saved['collection_check']['completed_at']),
                         ('read_error', client.posts[0]['checked_at']))
        self.assertEqual((saved['cursor'], saved['last_success'], self.state()), ('101', before['last_success'], kept))
        # Not dispatched again: the check is answered and the source waits for its own natural window.
        self.assertEqual(self.store.collector_plan(dt.datetime.now(agent.TZ) + dt.timedelta(minutes=1))['sources'], [])
        run, calls = fake_cli(rows=rows(2, 3))
        results, client = self.round(run)
        body, = client.posts
        self.assertEqual((body['expected_cursor'], body['cursor'], [m['id'] for m in body['messages']], body['check_id']),
                         ('101', '102', ['102'], ''))
        self.assertEqual((results[0]['status'], len(calls)), ('ingested', 2))
        now = self.source()
        self.assertEqual((now['cursor'], now['error'], now['collection_check']['status']), ('102', '', 'read_error'))
        self.assertGreater(now['last_success'], before['last_success'])
        messages, attachments, jobs = self.state()
        self.assertEqual((messages[:len(kept[0])], attachments, jobs), (kept[0], kept[1], kept[2]))
        self.assertEqual([m[1] for m in messages], ['101', '102'])

    def test_collect_once_failure_posts_no_messages_and_keeps_the_cursor(self):
        self.sources([QQ]); before = self.seed(); kept = self.state()
        cfg = dict(source_id=QQ['id'], app_url='http://127.0.0.1:8765', group_id='10002')
        run, calls = fake_cli('qq_endpoint_disconnected')
        client = StoreClient(self.store, dt.datetime.now(agent.TZ) + dt.timedelta(hours=2))
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'FAMILY_DATA': folder}), \
                patch.object(collect, 'QQ_MAX_PAGES', collect.QQ_MAX_PAGES), patch.object(collect, 'Client', return_value=client), \
                patch.object(collect.subprocess, 'run', side_effect=run):
            result = napcat.collect_once(cfg)
        self.assertEqual(result, dict(status='read_error', messages=0, inserted=0, error='qq_endpoint_disconnected'))
        self.assertEqual(len(calls), 1)
        body, = client.posts
        self.assertEqual((body['messages'], body['expected_cursor'], body['cursor']), ([], '101', '101'))
        saved = self.source()
        self.assertEqual((saved['error'], saved['cursor'], saved['last_success'], self.state()),
                         (EXPECTED['qq_endpoint_disconnected'] + SUFFIX, '101', before['last_success'], kept))

    def test_real_reader_config_failures_reach_the_store_without_any_request(self):
        self.sources([QQ]); self.seed()
        with tempfile.TemporaryDirectory(prefix='fictional-qq-') as folder:
            folder = Path(folder); cfg, onebot = folder / 'qq.json', folder / 'onebot.json'
            onebot.write_text(json.dumps({'network': {'httpServers': [{'port': 3001, 'token': 'f' * 30}]}})); onebot.chmod(0o600)
            cfg.write_text(json.dumps(dict(endpoint='http://127.0.0.1:13000', onebot_config=str(onebot), app_url='http://127.0.0.1:8765',
                                           source_id=QQ['id'], account_id='20001', bridge={})))
            for mode, code in ((0o644, 'private_config_required'), (0o600, 'onebot_config_invalid')):
                with self.subTest(code=code):
                    cfg.chmod(mode)
                    env = {'FAMILY_QQ_NAPCAT_CONFIG': str(cfg), 'HOME': str(folder)}
                    with self.assertRaises(collect.ProducerError) as raised:
                        collect.cli_json([sys.executable, str(ROOT / 'family_qq_napcat.py'), 'status'], env, timeout=20)
                    self.assertEqual((str(raised.exception), raised.exception.code), ('cli_read_failed', code))
                    with patch.dict(os.environ, env):
                        client = StoreClient(self.store, dt.datetime.now(agent.TZ) + dt.timedelta(hours=2))
                        results = collect.run_once(self.config, client)
                    self.assertEqual(results[0]['error'], code)
                    self.assertEqual(self.source()['error'], EXPECTED[code] + SUFFIX)


class NativeTransportTests(unittest.TestCase):
    CFG = dict(endpoint='http://127.0.0.1:13000', token='f' * 30, account_id='20001', group_id='10002')

    def opener(self, *outcomes):
        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append((request.full_url, timeout))
                outcome = outcomes[len(calls) - 1]
                if isinstance(outcome, BaseException): raise outcome
                body = io.BytesIO(json.dumps(outcome).encode()); body.status = 200
                body.geturl = lambda: request.full_url
                return body
        return patch.object(napcat.urllib.request, 'build_opener', return_value=Opener()), calls

    def test_one_request_failure_has_its_fixed_code_without_any_retry(self):
        url = self.CFG['endpoint'] + '/get_login_info'
        cases = [(urllib.error.URLError(ConnectionRefusedError(61, 'refused')), 'qq_endpoint_refused'),
                 (ConnectionRefusedError(61, 'refused'), 'qq_endpoint_refused'),
                 (http.client.RemoteDisconnected('Remote end closed connection without response'), 'qq_endpoint_disconnected'),
                 (urllib.error.URLError(ConnectionResetError(54, 'reset')), 'qq_endpoint_disconnected'),
                 (BrokenPipeError(32, 'pipe'), 'qq_endpoint_disconnected'),
                 (urllib.error.HTTPError(url, 401, 'Unauthorized', {}, None), 'qq_endpoint_auth_rejected'),
                 (urllib.error.HTTPError(url, 403, 'Forbidden', {}, None), 'qq_endpoint_auth_rejected'),
                 (urllib.error.HTTPError(url, 500, 'Server Error', {}, None), 'qq_read_failed'),
                 (urllib.error.URLError(socket.timeout('timed out')), 'qq_read_failed'),
                 (urllib.error.URLError('unknown'), 'qq_read_failed')]
        for raised, code in cases:
            with self.subTest(raised=type(raised).__name__, code=code):
                patched, calls = self.opener(raised, AssertionError('a second request'))
                with patched, self.assertRaisesRegex(collect.CollectError, '^' + code + '$'):
                    napcat.status(self.CFG)
                self.assertEqual(calls, [(url, 8)])  # one request, the original 8-second limit, no retry
                if code != 'qq_read_failed': self.assertIn(code, collect.QQ_PRODUCER_ERRORS)

    def test_a_valid_reply_without_the_configured_account_and_group_stays_source_unavailable(self):
        ok = lambda data: dict(status='ok', retcode=0, data=data)
        for login, groups in (({'user_id': 20009}, [{'group_id': 10002}]), ({'user_id': 20001}, [{'group_id': 10003}])):
            patched, calls = self.opener(ok(login), ok(groups))
            with patched, self.assertRaisesRegex(collect.CollectError, '^qq_source_unavailable$'):
                napcat.status(self.CFG)
            self.assertEqual(len(calls), 2)
        patched, _ = self.opener(ok({'user_id': 20001}), ok([{'group_id': 10002}]))
        with patched:
            self.assertEqual(collect.qq_status(napcat.status(self.CFG), '10002'), 'message_id')  # success validation unchanged
        self.assertFalse([w for w in UNPROVEN if w in agent._QQ_READ_REASONS['qq_source_unavailable']])
        self.assertEqual(set(agent._QQ_READ_REASONS), set(collect.QQ_PRODUCER_ERRORS))


def collect_failure(case, recovered):
    """Add one QQ source of child-1 to the served day: a natural success, a failed read, and optionally a natural success."""
    path = case.fixture.data / 'agent.json'
    sources = json.loads(path.read_text())['sources'] + [QQ]
    path.write_text(json.dumps({'enabled': True, 'sources': sources}))
    config = dict(app_url='http://127.0.0.1:8765', qq_cli=str(ROOT / 'family_qq_napcat.py'))
    # The served day's own clock (case.now, 2026-11-04 20:00 Asia/Shanghai, when its WeChat source was read): each QQ
    # receipt is stamped and planned at its own earlier fictional moment, at least one 30-minute window apart, so every
    # source of this child is due, failed or fresh by that one clock and the browser can be held at it.
    rounds = [('18:30', fake_cli(rows=[qq_event(1, ident='100')])[0], 'ingested'),
              ('19:05', fake_cli('qq_endpoint_refused')[0], 'read_error')]
    if recovered: rounds.append(('19:40', fake_cli(rows=[qq_event(1, ident='100')])[0], 'ingested'))
    for hm, run, status in rounds:
        moment = dt.datetime.fromisoformat(case.now.date().isoformat() + 'T' + hm + ':00+08:00')
        assert moment < case.now

        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None, _moment=moment):
                return _moment.astimezone(tz) if tz else _moment.replace(tzinfo=None)
        client = QQOnlyClient(case.store, moment)
        with patch.object(collect.subprocess, 'run', side_effect=run), patch.object(collect.dt, 'datetime', Clock):
            results = collect.run_once(config, client)
        assert [(r['source_id'], r['status']) for r in results] == [(QQ['id'], status)], results


def serve(port, recovered):
    import test_daily_list_frozen as frozen
    import test_image_original_date_scope as image
    case = image.ImageOriginalChainTests('test_new_save_lists_both_image_actions_on_their_own_days'); case.setUp()
    try:
        case._whole_day(False)
        collect_failure(case, recovered)
        frozen.serve_store(case, port, 'Source failure whole day served')
    finally:
        case.doCleanups()


if __name__ == '__main__':
    if sys.argv[1:2] in (['--serve-failed'], ['--serve-recovered']): serve(int(sys.argv[2]), sys.argv[1] == '--serve-recovered')
    else: unittest.main()

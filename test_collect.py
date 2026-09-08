"""Synthetic CLI envelopes and local transport; never uses family accounts."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import family_collect as collect


CHAT = '10001@chatroom'
SOURCE = dict(id=CHAT, platform='wechat', child_id='child-1', name='示例班级', cursor='10')
CONFIG = dict(app_url='http://127.0.0.1:8765/', wechat_cli='/fictional/wechat-cli', qq_cli='/fictional/qq-read.py')
TIME = '2026-02-10T08:00:00+08:00'


def event(ident=11, kind='text', text='虚构学校通知'):
    return dict(id=dict(local_id=ident, talker=CHAT), time_iso=TIME, kind=kind, sender='示例老师', text=text)


def page(events=None, after=10, has_more=False):
    events = [event()] if events is None else events
    query = dict(chat=CHAT, limit=200, offset=0, order='asc', display_order='query', returned=len(events), has_more=has_more)
    if after:
        query['after_message'] = 'local_id:' + str(after)
    if events:
        first, last = events[0]['id']['local_id'], events[-1]['id']['local_id']
        query.update(talker=CHAT, cursor=dict(oldest_local_id=first, newest_local_id=last,
                     next_before_message=first, next_after_message=last))
        if has_more:
            query['next_offset'] = len(events)
    data = dict(freshness=dict(message_source='live_message_db'), query=query)
    if events:
        data['messages'] = events
    return dict(ok=True, tool='messages', command='history', data=data)


class FakeClient:
    def __init__(self, sources=None, fail=False):
        self.sources = [copy.deepcopy(SOURCE)] if sources is None else sources
        self.posts = []
        self.fail = fail

    def request(self, path):
        assert path == '/api/agent/collector'
        return dict(enabled=True, sources=copy.deepcopy(self.sources))

    def ingest(self, body):
        self.posts.append(copy.deepcopy(body))
        if self.fail:
            raise collect.CollectError('app_request_failed')
        source = next(row for row in self.sources if row['id'] == body['source_id'])
        assert body['expected_cursor'] == source['cursor']
        if not body['error']:
            source['cursor'] = body['cursor']
        return dict(ok=True)


class CollectorTests(unittest.TestCase):
    def test_once_interval_failures_and_normal_stop(self):
        success = [{'status': 'ingested'}]
        for argv in (['--config', 'synthetic.json'], ['--config', 'synthetic.json', '--once']):
            with patch.object(collect, 'load_config', return_value=CONFIG) as load, patch.object(collect, 'run_once', return_value=success) as run, patch.object(collect.time, 'sleep', side_effect=AssertionError('Once must not wait')), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(collect.main(argv), 0)
                load.assert_called_once_with('synthetic.json')
                run.assert_called_once_with(CONFIG)
        with patch.object(collect, 'load_config', return_value=CONFIG), patch.object(collect, 'run_once', return_value=[{'status': 'read_error'}]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.main(['--config', 'synthetic.json', '--once']), 1)
        with patch.object(collect, 'load_config', side_effect=collect.CollectError('private_config_required')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(collect.main(['--config', 'synthetic.json', '--once']), 1)
        for argv in (['--interval', '0'], ['--interval', '59'], ['--interval', '86401'], ['--interval', '0.5'], ['--interval', '300', '--once']):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_result:
                collect.main(['--config', 'synthetic.json', *argv])
            self.assertEqual(exit_result.exception.code, 2)
        for stop_signal in (collect.signal.SIGINT, collect.signal.SIGTERM):
            handlers, registrations, pauses = {}, [], []
            originals = {s: collect.signal.getsignal(s) for s in (collect.signal.SIGINT, collect.signal.SIGTERM)}
            def install(signum, handler):
                prior = handlers.get(signum, originals[signum])
                handlers[signum] = handler
                registrations.append(signum)
                return prior
            def wait(seconds):
                pauses.append(seconds)
                if len(pauses) == 3:
                    handlers[stop_signal](stop_signal, None)
            output = io.StringIO()
            with patch.object(collect.signal, 'signal', side_effect=install), patch.object(collect.time, 'sleep', side_effect=wait), patch.object(collect, 'load_config', side_effect=[collect.CollectError('private_config_required'), CONFIG, CONFIG]) as load, patch.object(collect, 'run_once', side_effect=[collect.CollectError('app_request_failed'), success]) as run, contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit_result:
                collect.main(['--config', 'synthetic.json', '--interval', '300'])
            self.assertEqual(exit_result.exception.code, 0)
            self.assertEqual(pauses, [300, 300, 300])
            self.assertEqual((load.call_count, run.call_count), (3, 2))
            self.assertEqual(handlers, originals)
            self.assertEqual(registrations, [collect.signal.SIGINT, collect.signal.SIGTERM] * 2)
            self.assertEqual([json.loads(line) for line in output.getvalue().splitlines()], [
                {'error': 'private_config_required'}, {'error': 'app_request_failed'}, {'sources': success}])

    def test_missing_wechat_cli_is_reported_without_crashing(self):
        client=FakeClient()
        rows=collect.run_once({'app_url':CONFIG['app_url'],'qq_cli':CONFIG['qq_cli']},client,lambda args: self.fail('should not call missing CLI'))
        self.assertEqual(rows[0]['error'],'wechat_cli_not_configured')
        self.assertEqual(client.sources[0]['cursor'],'10')

    def test_real_wechat_shape_quote_media_and_zero_page(self):
        quote = event(12, 'quote', '收到')
        quote['quote'] = dict(kind='text', text='虚构家长转述', sender='示例家长',
                                         source_id=dict(local_id=11, talker=CHAT))
        media = event(13, 'file', '示例附件.wps')
        media['files'] = [dict(path='/unread/private/file.wps')]
        result, cursor, latest = collect.wechat_page(page([event(), quote, media]), SOURCE)
        self.assertEqual(cursor, '13')
        self.assertEqual(latest, TIME)
        self.assertFalse(result[0]['unread'])
        self.assertIn('不代表当前发送者确认', result[1]['text'])
        self.assertIn('虚构家长转述', result[1]['text'])
        self.assertFalse(result[1]['unread'])
        self.assertTrue(result[2]['unread'])
        self.assertIn('内容未读取', result[2]['text'])
        self.assertNotIn('/unread/', json.dumps(result))
        quote['quote']['source_id']['talker'] = '20002@chatroom'
        result, _, _ = collect.wechat_page(page([quote]), SOURCE)
        self.assertTrue(result[0]['unread'])
        self.assertNotIn('虚构家长转述', result[0]['text'])
        result, _, _ = collect.wechat_page(page([event(text='甲' * 9000)]), SOURCE)
        self.assertEqual(len(result[0]['text']), 8000)
        self.assertTrue(result[0]['unread'])
        empty = page([])
        self.assertNotIn('cursor', empty['data']['query'])
        self.assertNotIn('messages', empty['data'])
        self.assertEqual(collect.wechat_page(empty, SOURCE), ([], '10', ''))
        self.assertEqual(collect.wechat_page(page(), {**SOURCE, 'cursor': 'local_id:10'})[1], 'local_id:11')

    def test_byte_bounded_prefix_progress_and_oversized_single_message(self):
        client = FakeClient([{**SOURCE, 'cursor': 'local_id:10'}])
        calls = []
        def many(args):
            start = int(args[args.index('--after-message') + 1])
            calls.append(start)
            # An earlier long message must not prevent later ordinary notifications.
            envelope = page([event(n, text=('甲' * 20000 if n == 11 else '乙' * 8000))
                             for n in range(start + 1, 211)], after=start)
            envelope['data']['freshness']['last_message_time'] = '2026-02-12 12:00:00'
            return envelope
        while int(client.sources[0]['cursor'].removeprefix('local_id:')) < 210:
            rows = collect.run_once(CONFIG, client, many)
            self.assertEqual(rows[0]['status'], 'ingested')
            body = client.posts[-1]
            self.assertLessEqual(len(json.dumps(body['messages'], ensure_ascii=False,
                                     separators=(',', ':')).encode()), collect.MAX_BATCH_BYTES)
            self.assertLess(len(json.dumps(body, ensure_ascii=False).encode()), 1024 * 1024)
            self.assertEqual(body['cursor'], 'local_id:' + body['messages'][-1]['id'])
            self.assertEqual(body['last_message_time'], TIME)
            self.assertLess(len(client.posts), 20)
        all_messages = [message for body in client.posts for message in body['messages']]
        self.assertEqual([message['id'] for message in all_messages], [str(n) for n in range(11, 211)])
        self.assertTrue(all_messages[0]['unread'])
        self.assertIn('正文过长', all_messages[0]['text'])
        self.assertTrue(all(a < b for a, b in zip(calls, calls[1:])))
        self.assertEqual(collect.ingest_page([], 'local_id:210'), ([], 'local_id:210', ''))

    def test_initial_and_backlogged_sources_ingest_earliest_pages_without_skipping(self):
        for prefix in ('', 'local_id:'):
            for initial in (0, 10):
                with self.subTest(prefix=prefix, initial=initial):
                    client = FakeClient([{**SOURCE, 'cursor': prefix + str(initial)}], fail=True)
                    calls = []
                    def history(args):
                        self.assertEqual(args[:7], [CONFIG['wechat_cli'], 'history', CHAT, '--view', 'agent', '--order', 'asc'])
                        self.assertEqual(args[-3:], ['--limit', '200', '--strict-read-only'])
                        self.assertNotIn('--since-local-id', args)
                        self.assertNotIn('--since-time', args)
                        start = int(args[args.index('--after-message') + 1]) if '--after-message' in args else 0
                        if '--after-message' in args:
                            self.assertGreater(start, 0)
                        calls.append(start)
                        end = min(start + 200, 450)
                        return page([event(ident) for ident in range(start + 1, end + 1)], after=start, has_more=end < 450)
                    self.assertEqual(collect.run_once(CONFIG, client, history)[0]['status'], 'ingest_unconfirmed')
                    self.assertEqual(client.sources[0]['cursor'], prefix + str(initial))
                    client.fail = False
                    while int(client.sources[0]['cursor'].removeprefix('local_id:')) < 450:
                        self.assertEqual(collect.run_once(CONFIG, client, history)[0]['status'], 'ingested')
                        self.assertLess(len(client.posts), 6)
                    self.assertEqual(calls, [initial, initial, initial + 200, initial + 400])
                    accepted = [message['id'] for body in client.posts[1:] for message in body['messages']]
                    self.assertEqual(accepted, [str(ident) for ident in range(initial + 1, 451)])
                    self.assertEqual(client.sources[0]['cursor'], prefix + '450')
                    self.assertEqual(collect.run_once(CONFIG, client, history)[0]['messages'], 0)
                    self.assertEqual(client.sources[0]['cursor'], prefix + '450')
                    self.assertEqual(client.posts[-1]['last_message_time'], '')
        empty = FakeClient([{**SOURCE, 'cursor': '0'}])
        self.assertEqual(collect.run_once(CONFIG, empty, lambda args: page([], after=0))[0]['status'], 'ingested')
        self.assertEqual(empty.sources[0]['cursor'], '0')
        self.assertEqual(collect.run_once(CONFIG, empty, lambda args: page([event(1)], after=0))[0]['messages'], 1)
        self.assertEqual(empty.sources[0]['cursor'], '1')

    def test_positional_anchor_can_move_backwards_without_sorting_byte_limited_pages(self):
        # The CLI query position, not numeric ID or timestamp order, defines
        # which messages follow an anchor. All content is fictional.
        ids = [100 - n // 2 if n % 2 == 0 else 1000 + n // 2 for n in range(90)]
        client = FakeClient([{**SOURCE, 'cursor': 'local_id:200'}])
        calls = []
        def history(args):
            anchor = int(args[args.index('--after-message') + 1])
            calls.append(anchor)
            start = 0 if anchor == 200 else ids.index(anchor) + 1
            return page([event(ident, text='甲' * 8000) for ident in ids[start:start + 200]], after=anchor)
        for _ in range(10):
            result = collect.run_once(CONFIG, client, history)
            self.assertEqual(result[0]['status'], 'ingested')
            body = client.posts[-1]
            self.assertLessEqual(len(json.dumps(body['messages'], ensure_ascii=False,
                                     separators=(',', ':')).encode()), collect.MAX_BATCH_BYTES)
            if not body['messages']:
                break
            self.assertEqual(body['cursor'], 'local_id:' + body['messages'][-1]['id'])
        else:
            self.fail('Positional pages did not finish')
        self.assertGreater(len(client.posts), 2, 'The 700KiB bound must split the source page')
        self.assertTrue(any(after < before for before, after in zip(calls, calls[1:])))
        self.assertEqual([int(message['id']) for body in client.posts for message in body['messages']], ids)
        self.assertEqual(calls, [200] + [int(body['messages'][-1]['id']) for body in client.posts if body['messages']])
        self.assertEqual(client.sources[0]['cursor'], 'local_id:' + str(ids[-1]))
        self.assertEqual(collect.wechat_page(page([event(9)], after=10), SOURCE)[1], '9')

    def test_binding_order_and_live_failures_never_advance(self):
        invalid = []
        wrong_query = page(); wrong_query['data']['query']['chat'] = '20002@chatroom'; invalid.append(wrong_query)
        wrong_message = page(); wrong_message['data']['messages'][0]['id']['talker'] = '20002@chatroom'; invalid.append(wrong_message)
        cached = page(); cached['data']['freshness']['message_source'] = 'cache'; invalid.append(cached)
        advanced = page(); advanced['data']['query']['cursor']['next_after_message'] = 99; invalid.append(advanced)
        wrong_type = page(); wrong_type['data']['messages'][0]['kind'] = {}; invalid.append(wrong_type)
        wrong_time = page(); wrong_time['data']['messages'][0]['time_iso'] = '2026-02-10 08:00:00'; invalid.append(wrong_time)
        for changes in (dict(order='desc'), dict(display_order='asc'), dict(offset=200), dict(after_message='local_id:12'),
                        dict(talker='20002@chatroom'), dict(returned=2), dict(next_offset=999)):
            wrong_page = page(); wrong_page['data']['query'].update(changes); invalid.append(wrong_page)
        old_tail = page(); old_tail.update(tool='read_events', command='tail'); invalid.append(old_tail)
        missing_messages = page(); del missing_messages['data']['messages']; invalid.append(missing_messages)
        unknown_empty = page([]); unknown_empty['data']['query']['has_more'] = True; invalid.append(unknown_empty)
        missing_quote = page([event(kind='quote')]); invalid.append(missing_quote)
        invalid.extend([page([event(10)]), page([event(), event()])])
        for envelope in invalid:
            with self.subTest(envelope=envelope):
                client = FakeClient()
                rows = collect.run_once(CONFIG, client, lambda args: envelope)
                self.assertEqual(rows[0]['status'], 'read_error')
                body = client.posts[0]
                self.assertEqual((body['expected_cursor'], body['cursor'], body['messages']), ('10', '10', []))
                self.assertTrue(body['error'])
                self.assertEqual(body['last_message_time'], '')
                self.assertTrue(collect.iso_time(body['checked_at']))

    def test_allowlist_commands_and_send_failure_retry(self):
        calls = []
        def cli(args):
            calls.append(args)
            return page()
        client = FakeClient(fail=True)
        result = collect.run_once(CONFIG, client, cli)
        self.assertEqual(result[0]['status'], 'ingest_unconfirmed')
        self.assertEqual(client.sources[0]['cursor'], '10')
        client.fail = False
        collect.run_once(CONFIG, client, cli)
        self.assertEqual(client.sources[0]['cursor'], '11')
        expected = [CONFIG['wechat_cli'], 'history', CHAT, '--view', 'agent', '--order', 'asc', '--after-message', '10',
                    '--limit', '200', '--strict-read-only']
        self.assertEqual(calls, [expected, expected])
        self.assertEqual(client.posts[0]['messages'], client.posts[1]['messages'])
        for source in ({**SOURCE, 'id': '--other'}, {**SOURCE, 'id': '20002'}, {**SOURCE, 'platform': 'shell'}):
            with self.assertRaises(collect.CollectError):
                collect.run_once(CONFIG, FakeClient([source]), cli)
        self.assertEqual(len(calls), 2)
        missing_cursor = FakeClient([{**SOURCE, 'cursor': ''}])
        collect.run_once(CONFIG, missing_cursor, cli)
        self.assertEqual(missing_cursor.posts[0]['error'], 'wechat_cursor_required')
        self.assertEqual(len(calls), 2)
        with self.assertRaises(collect.CollectError):
            collect.run_once(CONFIG, FakeClient([SOURCE, SOURCE]), cli)
        # A response may be lost after commit: the next plan must use the server's cursor.
        committed = FakeClient()
        original_ingest = committed.ingest
        def lose_response(body):
            original_ingest(body)
            raise collect.CollectError('app_request_failed')
        committed.ingest = lose_response
        self.assertEqual(collect.run_once(CONFIG, committed, cli)[0]['status'], 'ingest_unconfirmed')
        self.assertEqual(committed.sources[0]['cursor'], '11')
        committed.ingest = original_ingest
        advanced_calls = []
        def following(args):
            advanced_calls.append(args)
            return page([event(12)], after=11)
        collect.run_once(CONFIG, committed, following)
        self.assertEqual(advanced_calls[0][advanced_calls[0].index('--after-message') + 1], '11')
        self.assertEqual([m['id'] for body in committed.posts for m in body['messages']], ['11', '12'])

    def test_qq_unavailable_and_native_anchor_continuity(self):
        source = dict(id='qq:10002', platform='qq', child_id='child-2', name='示例群', cursor='100')
        status = dict(status='ok', retcode=0, data=dict(online=None, good=False,
                      allowed_group_id='10002', capabilities=dict(status=True, history=False)))
        calls = []
        def offline(args):
            calls.append(args)
            return status
        client = FakeClient([source.copy()])
        collect.run_once(CONFIG, client, offline)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][-1], 'status')
        self.assertEqual(client.posts[0]['error'], 'qq_history_unavailable')
        self.assertEqual(client.posts[0]['cursor'], '100')
        status['data']['allowed_group_id'] = '10003'
        with self.assertRaisesRegex(collect.CollectError, 'source_mismatch'):
            collect.qq_status(status, '10002')

        def message(ident, gap=False):
            return dict(group_id='10002', message_id=str(ident), message_seq=str(ident - 90), time=1000,
                        sender=dict(nickname='示例老师'), message=[dict(type='text', data=dict(text='虚构原文'))],
                        raw_message='虚构原文', unread_elements=[dict(content_read=False)] if gap else [],
                        recalled=False, content_complete=not gap)
        envelope = dict(status='ok', retcode=0, data=dict(group_id='10002', messages=[message(101, True), message(100)],
                        count=2, coverage='returned_native_page_only', complete_history=False,
                        media_content_read=False, next_before_id='100'))
        rows, cursor, latest = collect.qq_page(envelope, source)
        self.assertEqual(cursor, '101')
        self.assertEqual([row['id'] for row in rows], ['101'])
        self.assertTrue(rows[0]['unread'])
        for unverified in ('', '10:39:47', '99'):
            with self.assertRaisesRegex(collect.CollectError, 'qq_continuity_unverified'):
                collect.qq_page(envelope, {**source, 'cursor': unverified})
        envelope['data']['messages'][0]['group_id'] = '10003'
        with self.assertRaisesRegex(collect.CollectError, 'source_mismatch'):
            collect.qq_page(envelope, source)

    def test_private_config_and_transport_boundaries(self):
        for value in ('https://example.invalid', 'http://192.0.2.1:8765/', 'http://user:secret@localhost/',
                      'http://localhost/?secret=1', 'http://localhost/family/', 'file:///tmp/app'):
            with self.assertRaises(collect.CollectError):
                collect.app_url(value)
        self.assertEqual(collect.app_url('http://[::1]:8765/'), 'http://[::1]:8765')
        with tempfile.TemporaryDirectory(prefix='fictional-collector-') as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({**CONFIG, 'wechat_cli': __file__, 'qq_cli': __file__}))
            path.chmod(0o600)
            self.assertEqual(collect.load_config(path)['app_url'], CONFIG['app_url'].rstrip('/'))
            path.chmod(0o644)
            with self.assertRaises(collect.CollectError):
                collect.load_config(path)
        with self.assertRaises(collect.CollectError):
            collect.NoRedirect().redirect_request(None, None, 302, '', {}, 'http://other/')
        client = collect.Client(CONFIG['app_url'])
        requests = []
        token = 'fictional-token-' + 'x' * 32
        class Opener:
            def open(self, request, timeout):
                requests.append(request)
                value = (dict(token=token) if request.full_url.endswith('/api/state')
                         else dict(ok=True, replayed=False, inserted=0, cursor='10'))
                result = io.BytesIO(json.dumps(value).encode())
                result.getcode = lambda: 200
                result.geturl = lambda: request.full_url
                return result
        client.opener = Opener()
        self.assertTrue(client.ingest(dict(messages=[], cursor='10'))['ok'])
        self.assertEqual([request.full_url.split('/')[-1] for request in requests], ['state', 'ingest'])
        self.assertEqual(requests[1].get_header('X-family-token'), token)
        self.assertNotIn(token, requests[1].full_url)


if __name__ == '__main__':
    unittest.main()

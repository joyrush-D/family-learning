#!/usr/bin/env python3
"""Read only server-authorized chats through local CLIs, then ingest one page.

Run once with --config PRIVATE_JSON --once, or stay alive with --interval 300.
The server owns cursors; this command never edits family files or a database.
"""
import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


MAX_RESPONSE = 8 * 1024 * 1024
MAX_TEXT = 8000
MAX_BATCH_BYTES = 700 * 1024  # Leave space below the server's 1MiB normalized-message limit.
TIMEZONE = dt.timezone(dt.timedelta(hours=8))


class CollectError(Exception):
    """Only fixed diagnostic codes, never command output or credentials."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CollectError('redirect_rejected')


def checked(condition, code='invalid_response'):
    if not condition:
        raise CollectError(code)


def app_url(value):
    checked(isinstance(value, str), 'invalid_app_url')
    try:
        url = urllib.parse.urlsplit(value)
        loopback = url.hostname == 'localhost' or ipaddress.ip_address(url.hostname).is_loopback
        port = url.port
    except (ValueError, TypeError):
        raise CollectError('loopback_url_required') from None
    checked(url.scheme == 'http' and loopback and not url.username and not url.password
            and not url.query and not url.fragment and (port is None or port > 0)
            and url.path in ('', '/'), 'loopback_url_required')
    return value.rstrip('/')


def load_config(path):
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as source:
            info = os.fstat(source.fileno())
            checked(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                    and info.st_size <= 8192, 'private_config_required')
            config = json.loads(source.read(8193))
        checked(isinstance(config, dict) and set(config) <= {'app_url', 'wechat_cli', 'qq_cli'}
                and {'app_url'} <= set(config), 'invalid_config')
        config['app_url'] = app_url(config['app_url'])
        for key in ('wechat_cli', 'qq_cli'):
            if key not in config:
                continue
            value = config[key]
            checked(isinstance(value, str) and Path(value).is_absolute()
                    and Path(value).is_file(), 'invalid_cli_path')
        return config
    except (OSError, ValueError, TypeError):
        raise CollectError('private_config_required') from None


def numeric(value, allow_zero=True):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{1,32}', value) is not None and (allow_zero or int(value) > 0)


def source_chat(source):
    checked(isinstance(source, dict), 'invalid_source')
    platform, ident = source.get('platform'), source.get('id')
    checked(platform in ('wechat', 'qq') and isinstance(ident, str), 'invalid_source')
    chat = ident.removeprefix(platform + ':')
    pattern = r'[0-9]{5,32}@chatroom' if platform == 'wechat' else r'[0-9]{5,20}'
    checked(re.fullmatch(pattern, chat) is not None and isinstance(source.get('child_id'), str)
            and source['child_id'] and isinstance(source.get('cursor'), str), 'invalid_source')
    return chat


def iso_time(value, local=False):
    checked(isinstance(value, str), 'invalid_message_time')
    try:
        moment = dt.datetime.fromisoformat(value)
        if local and moment.tzinfo is None:
            moment = moment.replace(tzinfo=TIMEZONE)
        checked(moment.tzinfo is not None, 'invalid_message_time')
        return moment.isoformat()
    except ValueError:
        raise CollectError('invalid_message_time') from None


def bounded(text):
    checked(isinstance(text, str), 'invalid_message_text')
    if len(text) <= MAX_TEXT:
        return text, False
    marker = '\n[正文过长，后续内容未读取]'
    return text[:MAX_TEXT - len(marker)] + marker, True


def ingest_page(messages, cursor):
    """Fit an ordered prefix; unsubmitted messages remain behind the server cursor."""
    batch, size = [], 2
    for message in messages:
        length = len(json.dumps(message, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        if size + length + bool(batch) > MAX_BATCH_BYTES:
            break
        batch.append(message)
        size += length + (len(batch) > 1)
    # Every normalized individual message is bounded well below this limit.
    checked(not messages or batch, 'message_exceeds_ingest_limit')
    if not batch:
        return [], cursor, ''
    new_cursor = ('local_id:' if cursor.startswith('local_id:') else '') + batch[-1]['id']
    return batch, new_cursor, batch[-1]['time']


def wechat_message(event, chat):
    checked(isinstance(event, dict) and event.get('type') == 'message')
    message = event.get('message')
    checked(isinstance(message, dict) and isinstance(message.get('id'), dict))
    ident = message['id']
    checked(ident.get('talker') == chat, 'source_mismatch')
    checked(type(ident.get('local_id')) is int and 0 < ident['local_id'] < 10 ** 32)
    checked(event.get('cursor') == 'local_id:' + str(ident['local_id']), 'cursor_mismatch')
    kind, sender = message.get('kind'), message.get('sender', '')
    checked(isinstance(kind, str) and re.fullmatch(r'[a-z_]{1,40}', kind) is not None
            and isinstance(sender, str), 'invalid_message_type')
    text = message.get('text', '')
    checked(isinstance(text, str))
    unread = kind not in ('text', 'quote')
    if kind == 'quote':
        quote = message.get('quote')
        checked(isinstance(quote, dict), 'quote_missing')
        reference = quote.get('source_id', {})
        checked(isinstance(reference, dict), 'invalid_quote_source')
        if reference.get('talker') not in (None, chat):
            # Do not ingest another chat's embedded content under this authorization.
            text += '\n[引用来源不是本授权群，引用内容未读取]'
            unread = True
        else:
            quoted = quote.get('text', '')
            checked(isinstance(quoted, str) and isinstance(quote.get('sender', ''), str))
            text = ('当前发送者正文：' + text + '\n引用内容（转述参考，不代表当前发送者确认）：\n'
                    + quoted + '\n引用发送者：' + quote.get('sender', '')[:200])
            unread = quote.get('kind') != 'text' or reference.get('talker') != chat
            if unread:
                text += '\n[引用原件或来源关联尚未完整读取]'
    elif unread:
        text = '[' + kind + '：内容未读取，仅保留消息说明]\n' + text
    text, truncated = bounded(text)
    timestamp = iso_time(message.get('time_iso'))
    checked(iso_time(event.get('event_time')) == timestamp, 'message_time_mismatch')
    return dict(id=str(ident['local_id']), time=timestamp, kind=kind,
                sender=sender[:200], text=text, unread=unread or truncated)


def wechat_page(envelope, source):
    chat = source_chat(source)
    cursor = source['cursor'].removeprefix('local_id:')
    checked(numeric(cursor), 'wechat_cursor_required')
    checked(isinstance(envelope, dict) and envelope.get('ok') is True
            and envelope.get('tool') == 'read_events' and envelope.get('command') == 'tail', 'wechat_read_failed')
    data = envelope.get('data')
    checked(isinstance(data, dict) and isinstance(data.get('freshness'), dict)
            and data['freshness'].get('message_source') == 'live_message_db', 'wechat_live_read_required')
    query = data.get('query')
    checked(isinstance(query, dict) and query.get('chat') == chat, 'source_mismatch')
    checked(query.get('limit') == 200 and query.get('mode') == 'messages')
    events = data.get('events')
    checked(isinstance(events, list) and len(events) <= 200)
    checked('returned' not in query or type(query['returned']) is int and query['returned'] == len(events))
    messages = [wechat_message(event, chat) for event in events]
    previous = int(cursor)
    for message in messages:
        checked(int(message['id']) > previous, 'non_monotonic_cursor')
        previous = int(message['id'])
    expected = 'local_id:' + str(previous)
    checked(data.get('cursor') == expected if messages else data.get('cursor') in ('', expected), 'cursor_mismatch')
    new_cursor = expected if source['cursor'].startswith('local_id:') else str(previous)
    # Database freshness is not the end of this page's successfully ingested content.
    return messages, new_cursor, messages[-1]['time'] if messages else ''


def qq_status(envelope, chat):
    checked(isinstance(envelope, dict) and envelope.get('status') == 'ok'
            and type(envelope.get('retcode')) is int and envelope['retcode'] == 0, 'qq_status_failed')
    data = envelope.get('data')
    checked(isinstance(data, dict) and data.get('allowed_group_id') == chat, 'source_mismatch')
    checked(isinstance(data.get('capabilities'), dict)
            and data['capabilities'].get('history') is True, 'qq_history_unavailable')


def qq_page(envelope, source):
    chat, cursor = source_chat(source), source['cursor']
    checked(isinstance(envelope, dict) and envelope.get('status') == 'ok'
            and type(envelope.get('retcode')) is int and envelope['retcode'] == 0, 'qq_read_failed')
    data = envelope.get('data')
    checked(isinstance(data, dict) and data.get('group_id') == chat, 'source_mismatch')
    rows = data.get('messages')
    checked(isinstance(rows, list) and len(rows) <= 20 and type(data.get('count')) is int
            and data['count'] == len(rows) and data.get('coverage') == 'returned_native_page_only'
            and data.get('complete_history') is False and data.get('media_content_read') is False)
    messages = []
    for row in rows:
        checked(isinstance(row, dict) and row.get('group_id') == chat, 'source_mismatch')
        checked(numeric(row.get('message_id'), False) and numeric(row.get('message_seq')))
        checked(type(row.get('time')) is int and 0 <= row['time'] < 253402300800
                and type(row.get('recalled')) is bool and type(row.get('content_complete')) is bool)
        parts, gaps = row.get('message'), row.get('unread_elements')
        checked(isinstance(parts, list) and isinstance(gaps, list) and len(parts) + len(gaps) <= 100)
        checked(all(isinstance(part, dict) and part.get('type') == 'text'
                    and isinstance(part.get('data'), dict) and isinstance(part['data'].get('text'), str) for part in parts))
        checked(all(isinstance(gap, dict) and gap.get('content_read') is False for gap in gaps))
        checked(row.get('raw_message') == ''.join(part['data']['text'] for part in parts)
                and row['content_complete'] == (not row['recalled'] and not gaps)
                and (not row['recalled'] or not parts and not gaps))
        sender = row.get('sender', {})
        checked(isinstance(sender, dict))
        sender_name = sender.get('card') or sender.get('nickname') or ''
        checked(isinstance(sender_name, str))
        text = row['raw_message']
        if row['recalled']:
            text = '[已撤回，正文未读取]'
        elif gaps:
            text += '\n[包含未读取的非文字内容]'
        text, truncated = bounded(text)
        messages.append(dict(id=row['message_id'], time=dt.datetime.fromtimestamp(row['time'], TIMEZONE).isoformat(),
            kind='recalled' if row['recalled'] else 'text', sender=sender_name[:200], text=text,
            unread=not row['content_complete'] or truncated))
    ids = [message['id'] for message in messages]
    checked(len(set(ids)) == len(ids), 'duplicate_message_id')
    checked(data.get('next_before_id') == min(ids, key=int, default=None), 'cursor_mismatch')
    # ponytail: one native page; a missing anchor requires explicit history reconciliation.
    checked(numeric(cursor, False) and cursor in ids, 'qq_continuity_unverified')
    messages = sorted((message for message in messages if int(message['id']) > int(cursor)), key=lambda message: int(message['id']))
    return messages, messages[-1]['id'] if messages else cursor, messages[-1]['time'] if messages else ''


def cli_json(args):
    try:
        result = subprocess.run(args, capture_output=True, timeout=45, check=False)
        checked(result.returncode == 0, 'cli_read_failed')
        checked(len(result.stdout) <= MAX_RESPONSE, 'cli_response_too_large')
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise CollectError('cli_read_failed') from None


class Client:
    def __init__(self, url):
        self.url = app_url(url)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, body=None, token=''):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Family-Token'] = token
        url = self.url + path
        request = urllib.request.Request(url, data=None if body is None else json.dumps(body, ensure_ascii=False).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                checked(response.getcode() == 200 and response.geturl() == url, 'app_request_failed')
                raw = response.read(MAX_RESPONSE + 1)
                checked(len(raw) <= MAX_RESPONSE, 'app_response_too_large')
            value = json.loads(raw)
            checked(isinstance(value, dict), 'app_invalid_response')
            return value
        except (OSError, ValueError, urllib.error.URLError):
            raise CollectError('app_request_failed') from None

    def ingest(self, body):
        state = self.request('/api/state')
        token = state.get('token')
        checked(isinstance(token, str) and re.fullmatch(r'[A-Za-z0-9_-]{24,200}', token) is not None, 'app_token_missing')
        reply = self.request('/api/agent/ingest', body, token)
        checked(reply.get('ok') is True and type(reply.get('replayed')) is bool
                and type(reply.get('inserted')) is int and 0 <= reply['inserted'] <= len(body['messages'])
                and reply.get('cursor') == body['cursor'], 'ingest_unconfirmed')
        return reply


def run_once(config, client=None, read_cli=cli_json):
    client = client or Client(config['app_url'])
    settings = client.request('/api/agent/collector')
    checked(type(settings.get('enabled')) is bool, 'invalid_collector_settings')
    if not settings['enabled']:
        return [{'status': 'disabled'}]
    sources = settings.get('sources')
    checked(isinstance(sources, list) and len(sources) <= 32, 'invalid_collector_settings')
    chats = [source_chat(source) for source in sources]
    checked(len({source['id'] for source in sources}) == len(sources)
            and len({(source['platform'], chat) for source, chat in zip(sources, chats)}) == len(sources), 'duplicate_source')
    results = []
    for source, chat in zip(sources, chats):
        body = dict(source_id=source['id'], expected_cursor=source['cursor'], cursor=source['cursor'],
                    checked_at='', last_message_time='', messages=[], error='')
        try:
            if source['platform'] == 'wechat':
                checked(bool(config.get('wechat_cli')), 'wechat_cli_not_configured')
                cursor = source['cursor'].removeprefix('local_id:')
                checked(numeric(cursor), 'wechat_cursor_required')
                envelope = read_cli([config['wechat_cli'], 'tail', chat, '--since-local-id', cursor,
                                     '--limit', '200', '--strict-read-only'])
                messages, new_cursor, latest = wechat_page(envelope, source)
            else:
                checked(bool(config.get('qq_cli')), 'qq_cli_not_configured')
                qq_status(read_cli([sys.executable, config['qq_cli'], 'status']), chat)
                checked(numeric(source['cursor'], False), 'qq_continuity_unverified')
                messages, new_cursor, latest = qq_page(read_cli([sys.executable, config['qq_cli'], 'history']), source)
            messages, new_cursor, latest = ingest_page(messages, source['cursor'])
            body.update(messages=messages, cursor=new_cursor, last_message_time=latest)
        except CollectError as error:
            body['error'] = str(error)
        body['checked_at'] = dt.datetime.now(TIMEZONE).isoformat()
        try:
            client.ingest(body)
            results.append(dict(source_id=source['id'], status='read_error' if body['error'] else 'ingested',
                                messages=len(body['messages']), error=body['error']))
        except CollectError:
            # No local cursor: an unacknowledged POST is reconciled by server CAS on the next run.
            results.append(dict(source_id=source['id'], status='ingest_unconfirmed'))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, help='仅本机可读的JSON配置文件（权限0600）')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--once', action='store_true', help='执行一轮；默认同样仅执行一轮')
    mode.add_argument('--interval', type=int, help='保持同一采集进程，每轮结束后间隔60至86400秒再次读取')
    args = parser.parse_args(argv)
    if args.interval is not None and not 60 <= args.interval <= 86400:
        parser.error('--interval 必须为60至86400之间的整数秒')
    previous = {}
    if args.interval is not None:
        # AppData consent can be scoped to the responsible process's lifetime.
        # Keep this parent alive; never change or bypass the user's TCC decision.
        def stop(signum, frame):
            raise SystemExit(0)
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, stop)
    try:
        while True:
            try:
                # Reload the private configuration and server allowlist each round.
                results = run_once(load_config(args.config))
                print(json.dumps({'sources': results}, ensure_ascii=False), flush=True)
                failed = int(any(row['status'] in ('read_error', 'ingest_unconfirmed') for row in results))
            except CollectError as error:
                print(json.dumps({'error': str(error)}, ensure_ascii=False), flush=True)
                failed = 1
            if args.interval is None:
                return failed
            time.sleep(args.interval)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == '__main__':
    raise SystemExit(main())

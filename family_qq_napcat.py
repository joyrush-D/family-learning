#!/usr/bin/env python3
"""Read one authorized QQ group from a loopback NapCat OneBot endpoint.

The optional collect command uses the existing Family Agent ingest contract.
The private config and message bodies never belong in the public repository.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import urllib.request

if Path(__file__).resolve().parent.name == 'private':
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import family_collect as collect


def private_json(path):
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
        info = os.fstat(stream.fileno())
        collect.checked(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
                        and info.st_size <= 8192, 'private_config_required')
        return json.load(stream)


def config():
    path = Path(os.environ.get('FAMILY_QQ_NAPCAT_CONFIG', Path(__file__).resolve().parent / 'private' / 'qq-napcat.json'))
    cfg = private_json(path)
    collect.checked(isinstance(cfg, dict) and set(cfg) == {'endpoint', 'onebot_config', 'app_url', 'source_id', 'account_id', 'bridge'},
                    'invalid_config')
    collect.checked(cfg['endpoint'] == 'http://127.0.0.1:13000'
                    and cfg['app_url'] == 'http://127.0.0.1:8765'
                    and isinstance(cfg['source_id'], str)
                    and re.fullmatch(r'qq:[0-9]{5,20}', cfg['source_id'])
                    and collect.numeric(cfg['account_id'], False), 'invalid_config')
    cfg['group_id'] = cfg['source_id'][3:]
    onebot = private_json(cfg['onebot_config'])
    servers = onebot.get('network', {}).get('httpServers', [])
    collect.checked(len(servers) == 1 and servers[0].get('port') == 3000
                    and isinstance(servers[0].get('token'), str) and len(servers[0]['token']) >= 24,
                    'onebot_config_invalid')
    cfg['token'] = servers[0]['token']
    bridge = cfg['bridge']
    collect.checked(isinstance(bridge, dict)
                    and set(bridge) == {'legacy_id', 'native_id', 'time', 'text_sha256', 'sender_sha256'}
                    and collect.numeric(bridge['legacy_id'], False)
                    and collect.numeric(bridge['native_id'], False)
                    and type(bridge['time']) is int
                    and all(isinstance(bridge[key], str) and re.fullmatch(r'[0-9a-f]{64}', bridge[key])
                            for key in ('text_sha256', 'sender_sha256')), 'bridge_invalid')
    return cfg


def request(cfg, action, body=None):
    req = urllib.request.Request(cfg['endpoint'] + '/' + action,
        data=None if body is None else json.dumps(body, separators=(',', ':')).encode(),
        headers={'Authorization': 'Bearer ' + cfg['token'], 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), collect.NoRedirect())
    with opener.open(req, timeout=8) as response:
        collect.checked(response.status == 200 and response.geturl() == req.full_url, 'qq_read_failed')
        raw = response.read(collect.MAX_RESPONSE + 1)
    collect.checked(len(raw) <= collect.MAX_RESPONSE, 'qq_response_too_large')
    value = json.loads(raw)
    collect.checked(isinstance(value, dict) and value.get('status') == 'ok' and value.get('retcode') == 0,
                    'qq_read_failed')
    return value.get('data')


def status(cfg):
    account = request(cfg, 'get_login_info')
    groups = request(cfg, 'get_group_list')
    collect.checked(isinstance(account, dict) and str(account.get('user_id')) == cfg['account_id']
                    and isinstance(groups, list)
                    and any(str(row.get('group_id')) == cfg['group_id'] for row in groups if isinstance(row, dict)),
                    'qq_source_unavailable')
    return {'status': 'ok', 'retcode': 0, 'data': {'allowed_group_id': cfg['group_id'],
            'capabilities': {'history': True}, 'online': True, 'history_cursor': 'message_id'}}


def history(cfg, before=''):
    collect.checked(not before or collect.numeric(before, False), 'qq_cursor_unsupported')
    anchor = cfg['bridge']['native_id'] if before == cfg['bridge']['legacy_id'] else before
    query = {'group_id': int(cfg['group_id']), 'count': 20}
    if anchor:
        query.update(message_seq=anchor, reverseOrder=True)
    data = request(cfg, 'get_group_msg_history', query)
    rows = data.get('messages') if isinstance(data, dict) else None
    collect.checked(isinstance(rows, list) and len(rows) <= 20, 'qq_read_failed')
    normalized = []
    for row in rows:
        collect.checked(isinstance(row, dict) and str(row.get('group_id')) == cfg['group_id'], 'source_mismatch')
        native_id, seq = str(row.get('message_id', '')), str(row.get('real_seq', ''))
        collect.checked(collect.numeric(native_id, False) and collect.numeric(seq, False)
                        and type(row.get('time')) is int and isinstance(row.get('message'), list)
                        and len(row['message']) <= 100, 'qq_read_failed')
        sender = row.get('sender')
        collect.checked(isinstance(sender, dict), 'qq_read_failed')
        name = sender.get('card') or sender.get('nickname') or ''
        collect.checked(isinstance(name, str), 'qq_read_failed')
        parts, gaps = [], []
        for part in row['message']:
            collect.checked(isinstance(part, dict) and isinstance(part.get('type'), str)
                            and isinstance(part.get('data'), dict), 'qq_read_failed')
            if part['type'] == 'text':
                value = part['data'].get('text')
                collect.checked(isinstance(value, str), 'qq_read_failed')
                parts.append({'type': 'text', 'data': {'text': value}})
            else:
                gaps.append({'type': part['type'], 'content_read': False})
        raw = ''.join(part['data']['text'] for part in parts)
        if native_id == cfg['bridge']['native_id']:
            bridge = cfg['bridge']
            digest = lambda value: hashlib.sha256(value.encode()).hexdigest()
            collect.checked(row['time'] == bridge['time'] and digest(raw) == bridge['text_sha256']
                            and digest(name) == bridge['sender_sha256'], 'bridge_message_changed')
            ident = bridge['legacy_id']
        else:
            ident = native_id
        recalled = row.get('recalled', False)
        collect.checked(type(recalled) is bool, 'qq_read_failed')
        if recalled:
            parts, gaps, raw = [], [], ''
        normalized.append({'group_id': cfg['group_id'], 'message_id': ident, 'message_seq': seq,
                           'time': row['time'], 'recalled': recalled, 'content_complete': not (recalled or gaps),
                           'message': parts, 'unread_elements': gaps, 'raw_message': raw,
                           'sender': collect.qq_native_sender(sender)})
    ids = [row['message_id'] for row in normalized]
    return {'status': 'ok', 'retcode': 0, 'data': {'group_id': cfg['group_id'], 'messages': normalized,
            'count': len(normalized), 'coverage': 'returned_native_page_only',
            'complete_history': False, 'media_content_read': False,
            'next_before_id': min(ids, key=int, default=None)}}


def collect_once(cfg):
    lock = Path(os.environ.get('FAMILY_DATA', Path(__file__).resolve().parent / 'private')) / '.qq-napcat.lock'
    with os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR, 0o600), 'r+') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        client = collect.Client(cfg['app_url'])
        plan = client.request('/api/agent/fragment/plan')
        sources = plan.get('sources') if isinstance(plan, dict) and plan.get('enabled') is True else None
        collect.checked(isinstance(sources, list), 'invalid_collector_settings')
        source = next((row for row in sources if row.get('id') == cfg['source_id']), None)
        collect.checked(source is not None and collect.source_chat(source) == cfg['group_id'], 'source_mismatch')
        deadline = time.monotonic() + collect.QQ_ROUND_SECONDS
        body = dict(source_id=source['id'], expected_cursor=source['cursor'], cursor=source['cursor'],
                    checked_at='', last_message_time='', messages=[], error='', check_id=source.get('check_id', ''))
        try:
            # ponytail: 20 bounded pages cover the verified current gap; a larger outage still fails closed.
            collect.QQ_MAX_PAGES = 20
            messages, cursor, latest = collect.qq_history({'qq_cli': str(Path(__file__).resolve())}, source,
                collect.cli_json, deadline - collect.QQ_RECEIPT_SECONDS)
            messages, cursor, latest = collect.ingest_page(messages, source['cursor'])
            body.update(messages=messages, cursor=cursor, last_message_time=latest)
        except collect.CollectError as error:
            body['error'] = str(error)
        body['checked_at'] = dt.datetime.now(collect.TIMEZONE).isoformat()
        reply = client.ingest(body, deadline=deadline)
        return {'status': 'read_error' if body['error'] else 'ingested', 'messages': len(body['messages']),
                'inserted': reply['inserted'], 'error': body['error']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('status', 'history', 'collect'))
    parser.add_argument('--before', default='')
    args = parser.parse_args()
    cfg = config()
    result = status(cfg) if args.command == 'status' else history(cfg, args.before) if args.command == 'history' else collect_once(cfg)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, collect.CollectError) as error:
        print(json.dumps({'status': 'error', 'error': str(error) if isinstance(error, collect.CollectError) else 'qq_read_failed'}))
        raise SystemExit(1)

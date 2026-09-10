#!/usr/bin/env python3
"""Read one explicitly authorized QQ group from a separately installed LLBot v8.1.10."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 8 * 1024 * 1024
DEFAULT_CONFIG = Path(__file__).with_name('family_qq_llbot.json')


class ReadError(Exception):
    pass


def check(ok, reason):
    if not ok:
        raise ReadError(reason)


def decimal(value, maximum=2**53 - 1):
    return (isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,19}', value)
            and int(value) <= maximum)


def private_text(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as source:
        info = os.fstat(source.fileno())
        check(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
              and info.st_uid == os.getuid() and info.st_size <= 4096, 'private_file_required')
        return source.read(4097).decode('utf-8').strip()


def validate_config(config):
    check(isinstance(config, dict) and set(config) == {'url', 'token_file', 'allowed_groups'}, 'invalid_config')
    check(isinstance(config['url'], str) and re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', config['url'])
          and 1 <= int(config['url'].rsplit(':', 1)[1]) <= 65535, 'loopback_required')
    check(isinstance(config['token_file'], str) and Path(config['token_file']).is_absolute(), 'invalid_token_path')
    groups = config['allowed_groups']
    check(isinstance(groups, list) and 0 < len(groups) <= 32 and all(decimal(g) for g in groups)
          and len(set(groups)) == len(groups), 'invalid_groups')
    return config


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ReadError('redirect_rejected')


def get_json(config, path):
    # Only run() constructs paths; no arbitrary URL, command, POST or message-send input.
    token = private_text(config['token_file'])
    check(16 <= len(token) <= 512, 'webui_password_required')
    url = config['url'] + path
    request = urllib.request.Request(url, method='GET', headers={
        'X-Webui-Token': hashlib.sha256(token.encode()).hexdigest()})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=15) as response:
        check(response.status == 200 and response.geturl() == url, 'http_failure')
        raw = response.read(MAX_BYTES + 1)
    check(len(raw) <= MAX_BYTES, 'response_too_large')
    value = json.loads(raw)
    check(isinstance(value, dict) and value.get('success') is True
          and isinstance(value.get('data'), dict), 'api_failure')
    return value['data']


def read_native(config, command, group=None, before=None, read=None):
    validate_config(config)
    check(command in {'status', 'history'}, 'invalid_command')
    if command == 'history':
        check(group in config['allowed_groups'], 'group_not_authorized')
        check(before is None or decimal(before), 'invalid_sequence')
    else:
        check(group is None and before is None, 'invalid_arguments')
    read = read or (lambda path: get_json(config, path))
    auth = read('/api/auth-token/status')
    check(auth.get('applicable') is True and type(auth.get('online')) is bool
          and type(auth.get('hasToken')) is bool and auth.get('validation')
          in {'idle', 'validating', 'valid', 'invalid', 'error'}, 'invalid_auth_state')
    if command == 'status':
        return {k: auth[k] for k in ['online', 'hasToken', 'validation']}
    check(auth['hasToken'] and auth['validation'] == 'valid', 'auth_token_required')
    check(auth['online'], 'qq_not_online')
    params = {'chatType': '2', 'peerId': group, 'limit': '20'}
    if before is not None:
        params['beforeMsgSeq'] = before
    data = read('/api/webqq/messages?' + urllib.parse.urlencode(params))
    rows = data.get('messages')
    check(isinstance(rows, list) and len(rows) <= 20 and type(data.get('hasMore')) is bool, 'invalid_page')
    seqs = []
    for row in rows:
        check(isinstance(row, dict) and type(row.get('chatType')) is int and row['chatType'] == 2
              and type(row.get('peerUin')) is int and str(row['peerUin']) == group, 'group_mismatch')
        seq = row.get('msgSeq')
        check(type(seq) is int and 0 < seq <= 2**53 - 1 and (before is None or seq <= int(before)), 'invalid_sequence')
        seqs.append(seq)
    check(len(seqs) == len(set(seqs)), 'duplicate_sequence')
    return {'group_id': group, 'messages': rows, 'has_more_hint': data['hasMore'],
            'next_before_seq': str(min(seqs)) if seqs else None,
            'complete_history': False, 'attachments_downloaded': False,
            'collector_compatible': False}


def check_reader():
    config = {'url': 'http://127.0.0.1:15703', 'token_file': '/unused', 'allowed_groups': ['10002']}
    calls = []
    def read(path):
        calls.append(path)
        if path == '/api/auth-token/status':
            return {'applicable': True, 'online': True, 'hasToken': True, 'validation': 'valid'}
        return {'messages': [{'chatType': 2, 'peerUin': 10002, 'msgSeq': 7}], 'hasMore': False}
    page = read_native(config, 'history', '10002', '8', read)
    assert page['next_before_seq'] == '7' and not page['collector_compatible']
    assert calls == ['/api/auth-token/status', '/api/webqq/messages?chatType=2&peerId=10002&limit=20&beforeMsgSeq=8']
    def rejected(fn, reason):
        try:
            fn()
        except ReadError as e:
            assert str(e) == reason
        else:
            raise AssertionError(reason)
    for group, before, reason in [('10003', None, 'group_not_authorized'), ('10002', '8&peerId=10003', 'invalid_sequence')]:
        rejected(lambda: read_native(config, 'history', group, before, read), reason)
    assert len(calls) == 2  # Invalid scope/input never reaches an HTTP request.
    rejected(lambda: read_native(config, 'send', read=read), 'invalid_command')
    rejected(lambda: validate_config({**config, 'url': 'https://example.invalid'}), 'loopback_required')
    rejected(lambda: read_native(config, 'history', '10002', read=lambda _: {
        'applicable': True, 'online': False, 'hasToken': False, 'validation': 'idle'}), 'auth_token_required')
    def wrong_group(path):
        return read(path) if '?' not in path else {'messages': [{'chatType': 2, 'peerUin': 10003, 'msgSeq': 7}], 'hasMore': False}
    rejected(lambda: read_native(config, 'history', '10002', read=wrong_group), 'group_mismatch')
    rejected(lambda: NoRedirect().redirect_request(None, None, None, None, None, 'http://example.invalid'), 'redirect_rejected')



def normalize(page):
    group=page['group_id'];messages=[]
    for raw in page['messages']:
        ident=raw.get('msgId');seq=raw.get('msgSeq');when=raw.get('msgTime');elements=raw.get('elements')
        check(isinstance(ident,str) and ident.isdecimal() and 0<int(ident)<10**32,'invalid_message_id')
        check(raw.get('chatType')==2 and str(raw.get('peerUin'))==group,'group_mismatch')
        check(type(seq) is int and 0<seq<=2**53-1 and type(when) is int and 0<when<253402300800,'invalid_sequence')
        check(isinstance(elements,list) and len(elements)<=100,'invalid_elements')
        parts=[];gaps=[]
        for element in elements:
            check(isinstance(element,dict) and type(element.get('elementType')) is int,'invalid_element')
            kind=element['elementType']
            if kind==1:
                content=element.get('textElement',{}).get('content')
                check(isinstance(content,str),'invalid_text')
                parts.append(dict(type='text',data=dict(text=content)))
            else:
                gaps.append(dict(element_type=kind,content_read=False))
        text=''.join(p['data']['text'] for p in parts);check(len(text)<=20000,'text_too_long')
        nickname=raw.get('sendNickName','');card=raw.get('sendMemberName','')
        check(isinstance(nickname,str) and isinstance(card,str),'invalid_sender')
        messages.append(dict(group_id=group,message_id=ident,message_seq=str(seq),time=when,
            sender=dict(nickname=nickname,card=card),message=parts,raw_message=text,
            unread_elements=gaps,recalled=False,content_complete=not gaps))
    check(len(messages)<=20 and len({m['message_id'] for m in messages})==len(messages),'invalid_page')
    return dict(status='ok',retcode=0,data=dict(group_id=group,messages=messages,count=len(messages),
        coverage='returned_native_page_only',complete_history=False,media_content_read=False,
        next_before_id=min((m['message_id'] for m in messages),key=int,default=None)))

def run(config,command,before=None):
    validate_config(config);check(len(config['allowed_groups'])==1,'single_authorized_group_required')
    group=config['allowed_groups'][0]
    if command=='status':
        check(before is None,'invalid_arguments');auth=read_native(config,'status')
        return dict(status='ok',retcode=0,data=dict(allowed_group_id=group,online=auth['online'],
            capabilities=dict(history=auth['online'] and auth['hasToken'] and auth['validation']=='valid'),
            transport='llbot_mac_direct',history_cursor='message_seq'))
    check(command=='history','invalid_command')
    return normalize(read_native(config,'history',group,before))

def self_check():
    raw=dict(msgId='90000000000000003',msgSeq=17,msgTime=1700000000,chatType=2,peerUin=10002,
             sendNickName='',sendMemberName='示例老师',elements=[dict(elementType=1,textElement=dict(content='虚构通知')),dict(elementType=2,picElement={})])
    page=dict(group_id='10002',messages=[raw]);result=normalize(page)['data'];row=result['messages'][0]
    assert row['message_id']==raw['msgId'] and row['message_seq']=='17' and row['raw_message']=='虚构通知'
    assert not row['content_complete'] and row['unread_elements']==[dict(element_type=2,content_read=False)]
    for changed in [dict(raw,peerUin=10003),dict(raw,msgSeq=True),dict(raw,msgId='invalid'),dict(raw,elements=[dict(elementType=1,textElement={})])]:
        try:normalize(dict(page,messages=[changed]))
        except ReadError:pass
        else:raise AssertionError('invalid native row accepted')
    check_reader()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['status', 'history', 'self-check'])
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--before')
    args = parser.parse_args()
    try:
        if args.command == 'self-check':
            self_check(); value = {'ok': True}
        else:
            value = run(json.loads(private_text(args.config)), args.command, args.before)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (ReadError, OSError, ValueError, TypeError, KeyError, AttributeError, urllib.error.URLError) as error:
        print(json.dumps({'ok': False, 'error': str(error) if isinstance(error, ReadError) else 'local_read_failed'}))
        sys.exit(1)

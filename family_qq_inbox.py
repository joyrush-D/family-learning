"""Explicitly configured QQ screenshot inbox. Imports one image per Agent tick.

Capture: python3 family_qq_inbox.py --data /absolute/private
Retry/import is performed by the existing Family Agent, not a developer session.
Include the group heading in every selection; unknown groups stay in the inbox.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tempfile
import unicodedata

from family_collect import checked, CollectError
from family_media import read_file
from family_settings import atomic_json
from family_wechat_media import validate_png, MediaError


def settings(data):
    data = Path(data).resolve(strict=True)
    path = data / 'qq-inbox.json'
    if not path.exists() and not path.is_symlink(): return None
    value = json.loads(read_file(path, limit=8192, private=True))
    checked(isinstance(value, dict) and set(value) == {'enabled', 'source_id'}
            and type(value['enabled']) is bool and isinstance(value['source_id'], str)
            and re.fullmatch(r'qq:[0-9]{5,20}', value['source_id']), 'qq_inbox_config_invalid')
    return value


def directory(data):
    path = Path(data).resolve(strict=True) / 'qq-inbox'
    path.mkdir(mode=0o700, exist_ok=True)
    checked(not path.is_symlink(), 'qq_inbox_path_invalid')
    return path


def status(data):
    """Read-only UI projection; browsing never captures or recognizes anything."""
    local = settings(data)
    if not local or not local['enabled']: return None
    folder = Path(data) / 'qq-inbox'
    checked(not folder.is_symlink(), 'qq_inbox_path_invalid')
    receipt = Path(data) / 'qq-inbox-receipt.json'
    last = json.loads(read_file(receipt, limit=8192, private=True)) if receipt.exists() else {}
    return dict(source_id=local['source_id'], pending=sum(1 for p in folder.glob('*.png') if not p.name.endswith('.partial.png')),
                state=last.get('state', 'waiting'), error=last.get('error', ''), checked_at=last.get('checked_at', ''))


def recognize(path, data):
    checked(sys.platform == 'darwin', 'qq_inbox_mac_required')
    source = Path(__file__).resolve().with_name('qq_screenshot_text.swift')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    executable = Path(data) / ('qq-ocr-' + digest)
    checked(not executable.is_symlink(), 'qq_inbox_path_invalid')
    if not executable.exists():
        result = subprocess.run(['/usr/bin/xcrun', 'swiftc', '-O', str(source), '-o', str(executable)],
                                capture_output=True, timeout=60)
        checked(result.returncode == 0, 'qq_inbox_ocr_build_failed')
        executable.chmod(0o700)
    result = subprocess.run([str(executable), str(path)], capture_output=True, timeout=25)
    checked(result.returncode == 0 and len(result.stdout) <= 40000, 'qq_inbox_ocr_failed')
    lines = json.loads(result.stdout)
    checked(isinstance(lines, list) and all(isinstance(s, str) for s in lines), 'qq_inbox_ocr_failed')
    text = '\n'.join(lines)
    checked(0 < len(text) <= 5700, 'qq_inbox_text_empty_or_too_long')
    return text


def normalized(text):
    return ''.join(unicodedata.normalize('NFKC', text).split())


def run_one(app, store, now):
    """Failures keep the file; receipt backoff also survives a process restart."""
    from family_agent import _lock, AgentError
    from family_qq_capture import save_fragment
    import base64
    local = settings(store.data)
    if not local or not local['enabled']: return dict(state='disabled')
    with _lock(store.data / '.qq-inbox.lock') as locked:
        if not locked: return dict(state='already_running')
        receipt_path = store.data / 'qq-inbox-receipt.json'
        sources = store._config()['sources']
        source = next((s for s in sources if s['id'] == local['source_id'] and s['enabled'] and s['platform'] == 'qq'), None)
        checked(source is not None, 'qq_inbox_source_disabled')
        folder = directory(store.data)
        # ponytail: one bounded inbox per family; archive old captures to keep scans small.
        files = sorted(p for p in folder.glob('*.png') if not p.name.endswith('.partial.png'))
        for path in files:
            digest = ''
            retry_path = path.with_suffix('.retry.json')
            try:
                old = json.loads(read_file(retry_path, limit=8192, private=True)) if retry_path.exists() else {}
                if old.get('retry_at', '') > now.isoformat(): continue
                body = read_file(path, limit=1024*1024)
                checked(max(validate_png(body).values()) <= 2048, 'qq_inbox_image_too_large')
                digest = hashlib.sha256(body).hexdigest()
                # Receipt first: a crash during OCR cannot retry every minute.
                receipt = dict(state='error', digest=digest, file=path.name, checked_at=now.isoformat(),
                               retry_at=(now+dt.timedelta(minutes=30)).isoformat(), error='qq_inbox_interrupted')
                atomic_json(receipt_path, receipt)
                atomic_json(retry_path, receipt)
                with tempfile.TemporaryDirectory(dir=store.data, prefix='.qq-ocr-') as work:
                    immutable = Path(work) / 'capture.png'; immutable.write_bytes(body)
                    text = recognize(immutable, store.data)
                checked(normalized(source['name']) in normalized(text), 'qq_inbox_group_heading_missing')
                checked(settings(store.data) == local, 'qq_inbox_config_changed')
                captured = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()
                result = save_fragment(store, dict(source_id=source['id'], child_id=source['child_id'],
                    captured_at=captured, text='截图本机文字识别（可能有误，请对照原图）：\n'+text,
                    png=base64.b64encode(body).decode()))
                archive = folder / '已处理'; archive.mkdir(mode=0o700, exist_ok=True)
                checked(not archive.is_symlink(), 'qq_inbox_path_invalid')
                target = archive / (digest+'.png')
                checked(read_file(path) == body, 'qq_inbox_file_changed')
                if target.exists(): checked(read_file(target) == body, 'qq_inbox_archive_conflict')
                else: os.link(path, target)
                path.unlink()
                retry_path.unlink(missing_ok=True)
                receipt.update(state='fragment_saved', error='', retry_at='', message_id=result['message_id'],
                               inserted=result['inserted'], cursor_advanced=False)
                atomic_json(receipt_path, receipt)
                return receipt
            except (OSError, ValueError, CollectError, MediaError, AgentError, subprocess.SubprocessError):
                # Never log OCR text, subprocess stderr, message contents or credentials.
                failure = dict(state='error', file=path.name, checked_at=now.isoformat(),
                    retry_at=(now+dt.timedelta(minutes=30)).isoformat(), error='截图未入库：请核对群标题、PNG大小和本机文字识别环境；原图保留。')
                failure['digest'] = digest
                atomic_json(receipt_path, failure)
                atomic_json(retry_path, failure)
                return failure
        return dict(state='waiting', pending=len(files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, type=Path)
    args = parser.parse_args()
    local = settings(args.data)
    checked(local and local['enabled'], 'qq_inbox_not_enabled')
    path = directory(args.data) / ('截图-'+str(time.time_ns())+'.png')
    temporary = path.with_suffix('.partial.png')
    try:
        result = subprocess.run(['/usr/sbin/screencapture', '-x', '-i', str(temporary)], timeout=180)
        if result.returncode or not temporary.exists(): return 1
        subprocess.run(['/usr/bin/sips', '-Z', '2048', str(temporary)], check=True, capture_output=True, timeout=20)
        checked(len(read_file(temporary, limit=1024*1024)) > 0, 'qq_inbox_image_too_large')
        temporary.chmod(0o600); os.replace(temporary, path)
        print('截图已收集；Agent将在后台整理，请到一起成长核对。')
        return 0
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())

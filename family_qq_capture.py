"""QQ window observations: incomplete evidence, separate from native message cursors."""
import base64
import datetime as dt
import hashlib
import json
import math
import os
import plistlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from family_collect import CollectError, checked, source_chat
from family_media import read_file
from family_wechat_media import MediaError, validate_png, bounded_process


KIND = 'qq_window_fragment'
NOTICE = 'QQ群窗口片段：仅本次可见内容，不是老师附件原件。发言人、发布时间和完整内容仍需核对。'


def save_fragment(store, obj):
    from family_agent import AgentError, _time, _now, _json
    if not isinstance(obj, dict) or set(obj) != {'source_id', 'child_id', 'captured_at', 'text', 'png'}:
        raise AgentError('QQ窗口片段提交结构不正确')
    if (not isinstance(obj['source_id'], str) or not re.fullmatch(r'qq:[0-9]{5,20}', obj['source_id'])
            or not isinstance(obj['child_id'], str) or not 1 <= len(obj['child_id']) <= 80
            or not isinstance(obj['text'], str) or len(obj['text']) > 6000
            or not isinstance(obj['png'], str) or len(obj['png']) > 1400000):
        raise AgentError('QQ窗口片段内容不正确或过大')
    captured = _time(obj['captured_at'])
    if dt.datetime.fromisoformat(captured) > _now() + dt.timedelta(minutes=1):
        raise AgentError('采集时间不能在未来')
    try:
        body = base64.b64decode(obj['png'], validate=True)
        dims = validate_png(body)
        if len(body) > 1024 * 1024 or max(dims.values()) > 2048:
            raise ValueError()
    except (ValueError, MediaError):
        raise AgentError('QQ窗口图片无法核对') from None
    digest = hashlib.sha256(_json([KIND, obj['source_id'], obj['child_id'], obj['text'],
                                  hashlib.sha256(body).hexdigest()]).encode()).hexdigest()
    ident = 'fragment-' + digest[:40]; upload_id = digest[:32]
    message = dict(id=ident, kind=KIND, time='', sender='', text=NOTICE + '\n' + obj['text'],
                   unread=True, captured_at=captured)
    reply = dict(ok=True, message_id=ident, coverage='window_fragment', cursor_advanced=False)
    directory = store.data / 'uploads'; target = directory / upload_id
    temporary = None; published = False
    try:
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            config = store._config(c)
            source = next((s for s in config['sources'] if s['id'] == obj['source_id']
                           and s['child_id'] == obj['child_id'] and s['platform'] == 'qq' and s['enabled']), None)
            if not config['enabled'] or source is None:
                raise AgentError('QQ来源未获授权或归属已变更', 403, 'source_disabled')
            old = c.execute('SELECT * FROM agent_sources WHERE id=?', (source['id'],)).fetchone()
            binding = store._binding(source, old)
            previous = c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?',
                                 (source['id'], ident)).fetchone()
            if previous:
                saved = json.loads(previous['payload'])
                if saved | {'captured_at': captured} != message:
                    raise AgentError('窗口片段内容冲突', 409, 'fragment_conflict')
                # A retry cannot undo a parent's removal or silently restore missing files.
                return reply | dict(replayed=True, inserted=0)
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            if directory.resolve(strict=True) != directory:
                raise AgentError('原件保存路径无法核对')
            name = 'QQ群窗口片段-' + digest[:12] + '（非附件原件）.png'
            upload = c.execute('SELECT * FROM uploads WHERE id=?', (upload_id,)).fetchone()
            if upload and (upload['name'] != name or upload['size'] != len(body) or upload['mime'] != 'image/png'):
                raise AgentError('窗口图片与既有文件冲突', 409, 'fragment_conflict')
            if target.exists() or target.is_symlink():
                if read_file(target) != body:
                    raise AgentError('窗口图片内容冲突', 409, 'fragment_conflict')
            else:
                with tempfile.NamedTemporaryFile(dir=directory, prefix='.qq-', delete=False) as f:
                    temporary = Path(f.name); f.write(body); f.flush(); os.fsync(f.fileno())
                os.link(temporary, target)
                published = True
            c.execute('INSERT OR IGNORE INTO uploads(id,name,size,mime,created) VALUES (?,?,?,?,?)',
                      (upload_id, name, len(body), 'image/png', captured))
            store._message_upload(c, source['child_id'], upload_id)
            if old is None:
                c.execute('INSERT INTO agent_sources(id,binding,cursor) VALUES(?,?,?)',
                          (source['id'], binding, source['cursor']))
            c.execute('INSERT INTO agent_messages(source_id,id,payload) VALUES(?,?,?)', (source['id'], ident, _json(message)))
            c.execute('INSERT INTO agent_message_attachments VALUES(?,?,?)', (source['id'], ident, upload_id))
            c.execute('UPDATE agent_sources SET unread_count=unread_count+1 WHERE id=?', (source['id'],))
        return reply | dict(replayed=False, inserted=1)
    except Exception:
        if published: target.unlink(missing_ok=True)
        raise
    finally:
        if temporary: temporary.unlink(missing_ok=True)


def settings(directory):
    path = Path(directory) / 'qq-cua.json'
    if not path.exists() and not path.is_symlink(): return None
    value = json.loads(read_file(path, limit=8192, private=True))
    checked(isinstance(value, dict) and set(value) in ({'enabled', 'source_id'}, {'enabled', 'source_id', 'host_app'})
            and type(value['enabled']) is bool and isinstance(value['source_id'], str)
            and re.fullmatch(r'qq:[0-9]{5,20}', value['source_id']), 'qq_capture_config_invalid')
    if 'host_app' in value:
        checked(isinstance(value['host_app'], str) and 0 < len(value['host_app']) <= 4096
                and '\0' not in value['host_app'] and Path(value['host_app']).is_absolute(), 'qq_capture_config_invalid')
    return value


def run_one(app, store, now):
    """Reuse the Agent cycle, with independent QQ-window cadence and bounded child lifetime."""
    from family_agent import _lock, _time, _now, next_collection_at
    from family_backup import no_links
    from family_settings import atomic_json
    from family_qq_cua import HOST_ID, screen_locked
    try:
        import family_qq_inbox
        inbox = family_qq_inbox.settings(store.data)
        if inbox and inbox['enabled']:
            return family_qq_inbox.run_one(app, store, now)
        local = settings(store.data)
        if not local or not local['enabled']: return dict(state='disabled')
        if not local.get('host_app'): return dict(state='manual_only')
        checked(sys.platform == 'darwin', 'qq_capture_platform')
        with store._db() as c:
            config = store._config(c)
            source = next((s for s in config['sources'] if s['id'] == local['source_id']
                           and s['enabled'] and s['platform'] == 'qq'), None)
            if not config['enabled'] or source is None: return dict(state='source_disabled')
            store._binding(source, c.execute('SELECT * FROM agent_sources WHERE id=?', (source['id'],)).fetchone())
        host = no_links(Path(local['host_app']))
        info = plistlib.loads(read_file(host/'Contents/Info.plist', limit=32768))
        checked(info.get('CFBundleIdentifier') == HOST_ID and info.get('CFBundleExecutable') == 'FamilyCollector'
                and info.get('FamilyQQPreflight') is True and info.get('FamilyRoot') == str(app.ROOT)
                and info.get('FamilyConfig') == str(store.data/'collector.json'), 'qq_host_installation_mismatch')
        executable = no_links(host/'Contents/MacOS/FamilyCollector')
        checked(executable.is_file() and os.access(executable, os.X_OK), 'qq_host_installation_mismatch')
        target = no_links(store.data/'qq-cua-attempt.json')
        with _lock(no_links(store.data/'.qq-cua-cycle.lock')) as locked:
            if not locked: return dict(state='already_running')
            binding = dict(source_id=source['id'], child_id=source['child_id'], host_app=str(host))
            if target.exists():
                old = json.loads(read_file(target, limit=8192, private=True))
                checked(isinstance(old, dict), 'qq_attempt_unreadable')
                if all(old.get(k) == v for k, v in binding.items()):
                    checked(old.get('state') in ('running','screen_locked','fragment_saved','permission_required',
                                                'not_collected','not_confirmed'), 'qq_attempt_unreadable')
                    due = next_collection_at(_time(old.get('started_at')))
                    if now < due: return dict(state='not_due', next_at=due.isoformat(), last_state=old.get('state', 'unknown'))
            # Persist before invoking: a failed/terminated attempt cannot run again every Agent tick.
            attempt = binding | dict(started_at=now.isoformat(), state='running')
            atomic_json(target, attempt)
            try:
                if screen_locked():
                    attempt['state'] = 'screen_locked'
                else:
                    # Fixed native app identity/paths; no shell, no QQ restart and no model environment.
                    env = {k: os.environ[k] for k in ('HOME','USER','LOGNAME','TMPDIR','LANG','LC_ALL') if k in os.environ}
                    env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
                    problem = None
                    # The parent owns this workspace, so timeout also removes partial window files.
                    with tempfile.TemporaryDirectory(prefix='.qq-cycle-', dir=store.data) as workspace:
                        env['FAMILY_QQ_WORKDIR'] = workspace
                        try: bounded_process([str(executable)], env, timeout=50, max_stdout=8192)
                        except MediaError as error: problem = error.code
                    receipt = json.loads(read_file(store.data/'qq-cua-preflight.json', limit=8192, private=True))
                    stamp = dt.datetime.fromisoformat(_time(receipt.get('checked_at')))
                    checked(now <= stamp <= _now()+dt.timedelta(minutes=1) and receipt.get('host_bundle_id') == HOST_ID
                            and receipt.get('source_id') == source['id'] and receipt.get('messages_ingested') == 0
                            and receipt.get('cursor_advanced') is False, 'qq_receipt_unconfirmed')
                    if receipt.get('status') == 'fragment_saved':
                        checked(problem is None and receipt.get('coverage') == 'window_fragment'
                                and type(receipt.get('observations_inserted')) is int
                                and receipt['observations_inserted'] in (0,1), 'qq_receipt_unconfirmed')
                        attempt.update(state='fragment_saved', observations_inserted=receipt['observations_inserted'])
                    else:
                        attempt['state'] = receipt.get('status') if receipt.get('status') in ('permission_required','screen_locked','not_collected') else 'not_confirmed'
            except (OSError, ValueError, TypeError, KeyError, CollectError):
                attempt['state'] = 'not_confirmed'
            attempt['finished_at'] = _now().isoformat()
            atomic_json(target, attempt)
            return dict(state=attempt['state'], next_at=next_collection_at(now.isoformat()).isoformat())
    except (OSError, ValueError, TypeError, KeyError, CollectError):
        # Source/config/host failure cannot stop ordinary study follow-up or expose private paths.
        return dict(state='configuration_error')


def rect(value):
    if not isinstance(value, dict): return None
    parts = [value.get(k) for k in ('x', 'y', 'w', 'h')]
    return parts if all(type(n) in (int, float) and math.isfinite(n) for n in parts) and parts[2] >= 2 and parts[3] >= 3 else None


def inside(a, b):
    return a and b and a[0] >= b[0] and a[1] >= b[1] and a[0]+a[2] <= b[0]+b[2] and a[1]+a[3] <= b[1]+b[3]


def layout(state, source, identity=True):
    """Use visible geometry, not flattened AX order or numbers embedded in messages."""
    bounds = state['window_bounds']
    window = rect(dict(x=bounds['x'], y=bounds['y'], w=bounds['width'], h=bounds['height']))
    checked(window and state.get('screenshot_frame_valid') is True, 'qq_window_unreadable')
    elements = [e for e in state['elements'] if inside(rect(e.get('frame')), window)]
    def one(role, label, predicate=lambda e: True):
        found = [e for e in elements if e['role'] == role and e.get('label') == label and predicate(e)]
        checked(len(found) == 1, 'qq_layout_unverified')
        return found[0]
    header = one('AXButton', source['name'], lambda e: e['frame']['y'] < window[1]+120)
    toolbar = one('AXToolbar', '更多', lambda e: abs(e['frame']['y']-header['frame']['y']) < 20)
    more = one('AXButton', '更多', lambda e: e['parent_index'] == toolbar['element_index'])
    editor = one('AXTextArea', source['name'])
    checked(editor.get('value') in (None, '', '按住 ⌃ ⌥，使用语音输入文字'), 'qq_user_composing')
    composer = one('AXToolbar', '会话', lambda e: abs(e['frame']['x']-editor['frame']['x']) < 2)
    checked(header['frame']['x'] >= editor['frame']['x'] and header['frame']['y'] < composer['frame']['y']
            and composer['frame']['y']+composer['frame']['h'] <= editor['frame']['y']+2, 'qq_layout_unverified')
    if not identity: return more, None, ''
    members = one('AXStaticText', '群聊成员')
    panel_name = one('AXStaticText', source['name'], lambda e: e['frame']['x'] >= members['frame']['x']
                     and toolbar['frame']['y']+toolbar['frame']['h'] < e['frame']['y'] < members['frame']['y'])
    number = one('AXStaticText', source_chat(source), lambda e: e['frame']['x'] >= panel_name['frame']['x']
                 and panel_name['frame']['y']+panel_name['frame']['h'] <= e['frame']['y'] < members['frame']['y'])
    one('AXButton', '分享', lambda e: e['frame']['x'] > number['frame']['x']
        and abs(e['frame']['y']-panel_name['frame']['y']) < 20)
    x = editor['frame']['x']; y = toolbar['frame']['y']+toolbar['frame']['h']+8
    right = min(x+editor['frame']['w'], members['frame']['x']-8)
    viewport = [x, y, right-x, composer['frame']['y']-y]
    checked(inside(viewport, window) and viewport[2] >= 120 and viewport[3] >= 100, 'qq_viewport_unverified')
    texts = [e.get('value') or e.get('label') for e in elements
             if e['role'] == 'AXStaticText' and inside(rect(e.get('frame')), viewport)]
    text = '\n'.join(t for t in texts if isinstance(t, str) and t)
    checked(len(text) <= 6000, 'qq_fragment_too_large')
    return more, viewport, text


def crop_window(state, viewport, target):
    """Discard sidebar, member roster and composer pixels before any model/upload."""
    source = Path(state['screenshot_file_path'])
    dims = validate_png(read_file(source))
    checked(dims == dict(width=state['screenshot_width'], height=state['screenshot_height']), 'qq_frame_mismatch')
    b = state['window_bounds']; sx = dims['width']/b['width']; sy = dims['height']/b['height']
    checked(abs(sx-sy) < .01 and sx > 0, 'qq_frame_mismatch')
    left, top = math.ceil((viewport[0]-b['x'])*sx), math.ceil((viewport[1]-b['y'])*sy)
    right = math.floor((viewport[0]+viewport[2]-b['x'])*sx)
    bottom = math.floor((viewport[1]+viewport[3]-b['y'])*sy)
    checked(0 <= left < right <= dims['width'] and 0 <= top < bottom <= dims['height'], 'qq_crop_outside_window')
    subprocess.run(['/usr/bin/sips', '--cropToHeightWidth', str(bottom-top), str(right-left),
                    '--cropOffset', str(top), str(left), str(source), '--out', str(target)],
                   capture_output=True, timeout=10, check=True)
    body = read_file(target, limit=1024*1024)
    checked(validate_png(body) == dict(width=right-left, height=bottom-top), 'qq_crop_unverified')
    return body


async def capture(driver, source, directory):
    from cua_driver import (ListAppsInput, ListWindowsInput, GetWindowStateInput,
                            ClickInput, ActionTarget, ClickPosition, ClickButton, InputDeliveryMode)
    from family_qq_cua import screen_locked
    checked(not screen_locked(), 'screen_locked')
    apps = await driver.list_apps(ListAppsInput())
    qq = [a for a in apps.apps if a.running and a.bundle_id == 'com.tencent.qq' and a.launch_path == '/Applications/QQ.app']
    checked(len(qq) == 1, 'official_qq_not_unique_or_not_running')
    windows = await driver.list_windows(ListWindowsInput(pid=qq[0].pid, on_screen_only=True))
    windows = [w for w in windows.windows if w.pid == qq[0].pid and w.layer == 0 and w.bounds.width > 200 and w.bounds.height > 150]
    checked(len(windows) == 1, 'qq_window_not_unique')
    w = windows[0]
    async def read():
        checked(not screen_locked(), 'screen_locked')
        state = await driver.get_window_state(GetWindowStateInput(pid=w.pid, window_id=w.window_id,
            session=None, query=None, include_accessibility_tree=True, include_screenshot=True,
            screenshot_out_file=str(directory/'window.png'), max_elements=1500, max_depth=60, max_dimension=1600))
        checked(not screen_locked(), 'screen_locked_during_capture')
        checked(state.pid == w.pid and state.window_id == w.window_id, 'qq_window_changed')
        return json.loads(json.dumps(vars(state), default=vars))
    async def click(more):
        checked(not screen_locked(), 'screen_locked')
        await driver.click(ClickInput(target=ActionTarget.WINDOW(w.pid, w.window_id),
            position=ClickPosition.ELEMENT(more['element_token']), delivery_mode=InputDeliveryMode.BACKGROUND,
            session=None, button=ClickButton.LEFT, count=1))
    state = await read()
    # ponytail: read only the already-selected authorized group; switching/history needs coexistence tests.
    more, _, _ = layout(state, source, identity=False)
    opened = False
    try:
        try: _, viewport, text = layout(state, source)
        except CollectError:
            await click(more); opened = True
            state = await read()
            _, viewport, text = layout(state, source)
        body = crop_window(state, viewport, directory/'fragment.png')
        checked(not screen_locked(), 'screen_locked_during_capture')
        return text, body
    finally:
        if opened and not screen_locked():
            # Reacquire and verify identity; never toggle a different chat's controls.
            current = await read()
            more, _, _ = layout(current, source)
            await click(more)


async def capture_once(config, data, local):
    from cua_driver import CuaDriver
    from family_collect import Client
    from family_qq_cua import permissions, screen_locked, native_host_id, HOST_ID
    client = Client(config['app_url']); deadline = time.monotonic()+40
    plan = client.request('/api/agent/fragment/plan', deadline=deadline)
    checked(plan.get('enabled') is True, 'qq_source_disabled')
    sources = [s for s in plan['sources'] if s['id'] == local['source_id'] and s['platform'] == 'qq']
    checked(len(sources) == 1, 'qq_source_disabled_or_not_due')
    source = sources[0]; source_chat(source)
    from family_backup import no_links
    workspace = no_links(Path(os.environ.get('FAMILY_QQ_WORKDIR', str(data))))
    checked(workspace == data or (workspace.parent == data and workspace.name.startswith('.qq-cycle-')
                                 and workspace.is_dir()), 'qq_workspace_invalid')
    driver = CuaDriver.create()
    try:
        with tempfile.TemporaryDirectory(prefix='.qq-capture-', dir=workspace) as temporary:
            text, body = await capture(driver, source, Path(temporary))
            checked(settings(data) == local, 'qq_capture_config_changed')
            access = permissions(await driver.call_tool('check_permissions', '{"prompt":false,"probe_direct_capture":false}'))
            checked(all(access[k] for k in ('accessibility', 'screen_recording'))
                    and native_host_id() == HOST_ID and not screen_locked(), 'qq_host_not_ready')
            current = client.request('/api/agent/fragment/plan', deadline=deadline)
            checked(current.get('enabled') is True and source in current['sources'], 'qq_source_changed')
            token = client.request('/api/state', deadline=deadline)['token']
            obj = dict(source_id=source['id'], child_id=source['child_id'], text=text,
                       captured_at=dt.datetime.now(dt.timezone.utc).isoformat(), png=base64.b64encode(body).decode())
            reply = client.request('/api/agent/fragment', obj, token, deadline=deadline)
            checked(reply.get('ok') is True and reply.get('cursor_advanced') is False
                    and reply.get('coverage') == 'window_fragment' and type(reply.get('replayed')) is bool
                    and type(reply.get('inserted')) is int and reply['inserted'] == (0 if reply['replayed'] else 1)
                    and isinstance(reply.get('message_id'), str) and re.fullmatch(r'fragment-[a-f0-9]{40}', reply['message_id']), 'qq_fragment_unconfirmed')
            return dict(status='fragment_saved', observations_inserted=reply['inserted'], coverage='window_fragment')
    finally:
        await driver.shutdown()

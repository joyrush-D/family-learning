"""QQ Cua host readiness check and explicitly configured window evidence capture.

Run from the named native app to check its real background permissions. A check
from a developer terminal does not establish the app's permissions. The default
is preflight only. Optional private/qq-cua.json enables one authorized
group's visible fragment; this never advances native message cursors.
"""
import argparse
import asyncio
import ctypes
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import plistlib
import re
import subprocess

from family_backup import no_links
from family_collect import CollectError, load_config
from family_settings import atomic_json


SDK_VERSION = '0.26.0'
HOST_ID = 'local.family-learning.qq-reader'


def native_host_id():
    """Read the actual process bundle, not an environment label or SDK hint."""
    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    cf.CFBundleGetMainBundle.restype = ctypes.c_void_p
    cf.CFBundleGetIdentifier.argtypes = [ctypes.c_void_p]
    cf.CFBundleGetIdentifier.restype = ctypes.c_void_p
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    bundle = cf.CFBundleGetMainBundle()
    ident = cf.CFBundleGetIdentifier(bundle) if bundle else None
    buffer = ctypes.create_string_buffer(200)
    if not ident or not cf.CFStringGetCString(ident, buffer, len(buffer), 0x08000100):
        return ''
    return buffer.value.decode('utf-8')


def screen_locked():
    result = subprocess.run(['/usr/sbin/ioreg', '-n', 'Root', '-d1', '-a'],
                            capture_output=True, check=True, timeout=5)
    root = plistlib.loads(result.stdout)
    if not isinstance(root, dict) or type(root.get('IOConsoleLocked')) is not bool:
        raise CollectError('lock_state_unknown')
    return root['IOConsoleLocked']


def permissions(result):
    try:
        data = json.loads(result.structured_json)
    except (AttributeError, TypeError, ValueError):
        raise CollectError('qq_host_permissions_unknown') from None
    if result.is_error or not isinstance(data, dict) or any(
            type(data.get(key)) is not bool for key in ('accessibility', 'screen_recording')):
        raise CollectError('qq_host_permissions_unknown')
    source = data.get('source')
    host = source.get('host_bundle_id') if isinstance(source, dict) else None
    host = host if isinstance(host, str) and re.fullmatch(r'[A-Za-z0-9._-]{1,160}', host) else ''
    return {**{key: data[key] for key in ('accessibility', 'screen_recording')}, 'sdk_host_bundle_id': host}


async def check_host():
    # Only the pinned, already installed SDK is used. Never install it or prompt
    # for access here; absent/changed dependencies remain an explicit failure.
    try:
        installed = version('cua-driver')
    except PackageNotFoundError:
        raise CollectError('qq_sdk_not_installed') from None
    if installed != SDK_VERSION:
        raise CollectError('qq_sdk_version_unverified')
    from cua_driver import CuaDriver
    driver = CuaDriver.create()
    try:
        result = permissions(await driver.call_tool('check_permissions',
            '{"prompt":false,"probe_direct_capture":false}'))
        result['host_bundle_id'] = native_host_id()
        result['screen_locked'] = screen_locked()
        result['sdk_version'] = installed
        result['status'] = ('host_identity_unverified' if result['host_bundle_id'] != HOST_ID
                            else 'permission_required' if not all(result[k] for k in ('accessibility', 'screen_recording'))
                            else 'screen_locked' if result['screen_locked'] else 'host_ready')
        return result
    finally:
        await driver.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path, help='已有本机采集配置；默认只检查，可按私有配置读取授权QQ窗口')
    args = parser.parse_args(argv)
    try:
        config = no_links(args.config.expanduser())
        collector = load_config(config)
        target = no_links(config.parent / 'qq-cua-preflight.json')
    except (OSError, ValueError, CollectError):
        print(json.dumps({'status': 'not_checked', 'error': 'private_config_required'}))
        return 1
    result = {}
    try:
        from family_qq_capture import settings, capture_once
        local = settings(config.parent)
        result = asyncio.run(asyncio.wait_for(check_host(), timeout=20))
        if local and local['enabled']: result['source_id'] = local['source_id']
        if result['status'] == 'host_ready':
            if local and local['enabled']:
                result.update(asyncio.run(asyncio.wait_for(capture_once(collector, config.parent, local), timeout=40)))
    except CollectError as error:
        result.update(status='not_collected' if result else 'not_checked', error=str(error))
    except TimeoutError:
        result.update(status='not_collected' if result else 'not_checked', error='qq_read_timeout')
    except Exception:
        # Native errors may contain application/window text or machine paths.
        result.update(status='not_collected' if result else 'not_checked', error='qq_read_unavailable')
    result.update(checked_at=datetime.now(timezone.utc).isoformat(), messages_ingested=0,
                  cursor_advanced=False, permission_prompted=False)
    try:
        atomic_json(target, result)
    except (OSError, ValueError):
        print(json.dumps({'status': 'not_checked', 'error': 'qq_receipt_not_saved'}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] in ('host_ready', 'fragment_saved') else 1


if __name__ == '__main__':
    raise SystemExit(main())

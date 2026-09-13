"""Readiness checks use synthetic responses; no chat access or permission prompts."""
import asyncio
import json
from pathlib import Path
import plistlib
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import family_qq_cua as qq


def check():
    for access, recording, expected in [(True, True, 'host_ready'), (False, True, 'permission_required'),
                                       (True, False, 'permission_required'), (False, False, 'permission_required')]:
        driver = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(is_error=False,
            structured_json=json.dumps(dict(accessibility=access, screen_recording=recording,
                                           source=dict(host_bundle_id=qq.HOST_ID))))), shutdown=AsyncMock())
        sdk = SimpleNamespace(CuaDriver=SimpleNamespace(create=lambda: driver))
        with patch.dict(sys.modules, cua_driver=sdk), patch.object(qq, 'version', return_value=qq.SDK_VERSION), \
                patch.object(qq, 'screen_locked', return_value=False), patch.object(qq, 'native_host_id', return_value=qq.HOST_ID):
            result = asyncio.run(qq.check_host())
        assert result['status'] == expected
        driver.call_tool.assert_awaited_once_with('check_permissions', '{"prompt":false,"probe_direct_capture":false}')
        driver.shutdown.assert_awaited_once()
    with patch.dict(sys.modules, cua_driver=sdk), patch.object(qq, 'version', return_value=qq.SDK_VERSION), \
            patch.object(qq, 'screen_locked', return_value=False), patch.object(qq, 'native_host_id', return_value='org.python.python'):
        assert asyncio.run(qq.check_host())['status'] == 'host_identity_unverified'
    with patch.dict(sys.modules, cua_driver=sdk), patch.object(qq, 'version', return_value='0.0.0'):
        try:
            asyncio.run(qq.check_host())
        except qq.CollectError as error:
            assert str(error) == 'qq_sdk_version_unverified'
        else:
            raise AssertionError('Changed SDK cannot be declared ready')
    for raw in ('{}', '[]', 'invalid', '{"accessibility":"true","screen_recording":true}'):
        try:
            qq.permissions(SimpleNamespace(is_error=False, structured_json=raw))
        except qq.CollectError as error:
            assert str(error) == 'qq_host_permissions_unknown'
        else:
            raise AssertionError('Unknown permission must not become ready')
    for locked in (True, False, None):
        with patch.object(qq.subprocess, 'run', return_value=SimpleNamespace(
                stdout=plistlib.dumps({} if locked is None else {'IOConsoleLocked': locked}))):
            try:
                result = qq.screen_locked()
            except qq.CollectError as error:
                assert locked is None and str(error) == 'lock_state_unknown'
            else:
                assert result is locked
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary).resolve()
        config = directory / 'collector.json'
        config.write_text('{"app_url":"http://127.0.0.1:8765"}')
        config.chmod(0o600)
        original = config.read_bytes()
        result = directory / 'qq-cua-preflight.json'
        for value, code in [(dict(status='host_ready'), 0), (dict(status='permission_required'), 1),
                            (RuntimeError('must never leak window text'), 1)]:
            mock = AsyncMock(side_effect=value) if isinstance(value, Exception) else AsyncMock(return_value=value)
            with patch.object(qq, 'check_host', mock):
                assert qq.main(['--config', str(config)]) == code
            saved = json.loads(result.read_text())
            assert saved['messages_ingested'] == 0 and not saved['cursor_advanced'] and not saved['permission_prompted']
            assert 'must never leak' not in result.read_text()
            assert result.stat().st_mode & 0o777 == 0o600 and config.read_bytes() == original
        result.unlink()
        elsewhere = directory / 'unchanged'; elsewhere.write_text('unchanged')
        result.symlink_to(elsewhere)
        with patch.object(qq, 'check_host', AsyncMock()) as check_host:
            assert qq.main(['--config', str(config)]) == 1
            check_host.assert_not_called()
        assert elsewhere.read_text() == 'unchanged'
    print('PASS: exact permissions, fail-closed lock, prompt-free check, private receipt and sanitized errors')


if __name__ == '__main__':
    check()

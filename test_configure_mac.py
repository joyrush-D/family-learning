"""Synthetic Mac configuration check: no real launchd or family configuration."""
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import tempfile
from unittest.mock import patch

import configure_mac as setup


def refuses(operation):
    try:
        operation()
    except (OSError, ValueError, setup.CollectError):
        return
    raise AssertionError('Expected refusal')


def check():
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        root = base / '示例应用 <a&b>'
        root.mkdir()
        for name in ('app.py', 'family_agent.py', 'family_collect.py', 'family_backup.py'):
            (root / name).write_text('# Synthetic; never execute.\n')
        wechat = base / 'wechat <&> cli'
        wechat.write_text('# Synthetic; never execute.\n')
        wechat.chmod(0o700)
        qq = base / 'qq <&> cli.py'
        qq.write_text('# Synthetic; never execute.\n')
        with patch.object(setup.shutil, 'which', return_value=None):
            with patch.object(setup.sys, 'version_info', (3, 9)):
                refuses(lambda: setup.plan(root))
            prepared = setup.plan(root, wechat_cli=str(wechat), qq_cli=str(qq))
            assert prepared['collector_enabled'] and prepared['mobile_url'] is None
            destination = setup.output(prepared, base / '检查输出 <&>')
            for path in destination.rglob('*'):
                assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
            config = json.loads((destination / 'private/collector.json').read_text())
            assert config == {'app_url': 'http://127.0.0.1:8765', 'wechat_cli': str(wechat), 'qq_cli': str(qq)}
            for kind, interval in (('web', None), ('agent', 60), ('collector', None), ('backup', None)):
                raw = (destination / ('LaunchAgents/' + setup.LABEL + '.' + kind + '.plist')).read_bytes()
                plist = plistlib.loads(raw)
                assert b'&amp;' in raw and b'&lt;' in raw
                assert plist['WorkingDirectory'] == str(root)
                assert plist['ProgramArguments'][0] == str(Path(setup.sys.executable).resolve())
                assert plist['ProgramArguments'][1] == str(root / ('app.py' if kind == 'web' else 'family_' + kind.replace('collector', 'collect') + '.py'))
                assert plist['EnvironmentVariables']['FAMILY_DATA'] == str(root / 'private')
                assert all(key not in plist['EnvironmentVariables'] for key in
                           ('FAMILY_CHILD_SECURE', 'FAMILY_CHILD_COOKIE_PATH', 'FAMILY_CHILD_PUBLIC_URL',
                            'FAMILY_CALENDAR_ID'))
                assert plist.get('StartInterval') == interval and plist['RunAtLoad']
                if kind == 'collector':
                    assert plist['ProgramArguments'][-2:] == ['--interval', '300'] and '--once' not in plist['ProgramArguments']
                    assert plist['KeepAlive'] == {'SuccessfulExit': False} and plist['ThrottleInterval'] == 300
                elif kind == 'web':
                    assert plist['KeepAlive'] is True and plist['ThrottleInterval'] == 10
                elif kind == 'backup':
                    assert plist['ProgramArguments'][-3:] == ['--root', str(root), 'daily']
                    assert plist['StartCalendarInterval'] == {'Hour': 2, 'Minute': 0}
                    assert 'KeepAlive' not in plist and 'ThrottleInterval' not in plist
                else:
                    assert plist['ProgramArguments'][-1] == '--once' and 'KeepAlive' not in plist
                assert plist['Umask'] == 0o077 and 'shell' not in plist
            refuses(lambda: setup.output(prepared, destination))
            marker = destination / 'private/collector.json'
            original = marker.read_bytes()
            refuses(lambda: setup.exclusive_write(marker, b'overwritten'))
            assert marker.read_bytes() == original
            refuses(lambda: setup.plan(root, 'https://example.invalid'))
            refuses(lambda: setup.plan(root, 'http://127.0.0.1:8765/path'))
            refuses(lambda: setup.plan(root, wechat_cli=str(base / 'missing')))
            wechat.chmod(0o600)
            refuses(lambda: setup.plan(root, wechat_cli=str(wechat)))
            wechat.chmod(0o700)
            absent = setup.plan(root)
            assert not absent['collector_enabled']
            disabled = plistlib.loads(absent['files']['LaunchAgents/' + setup.LABEL + '.collector.plist'])
            assert disabled['Disabled'] and not disabled['RunAtLoad']
            assert setup.plan(root, qq_cli=str(qq))['collector_enabled']
            # Default mode only prints a plan; it creates no application files or processes.
            before = sorted(str(p.relative_to(root)) for p in root.rglob('*'))
            with patch.object(setup.subprocess, 'run', side_effect=AssertionError('No process in dry run')), contextlib.redirect_stdout(io.StringIO()):
                assert setup.main(['--root', str(root)]) == 0
                with patch.object(setup.sys, 'platform', 'linux'):
                    refuses(lambda: setup.install(prepared))
            assert before == sorted(str(p.relative_to(root)) for p in root.rglob('*'))
            fake_home = base / 'synthetic-home'
            fake_home.mkdir()
            agents = fake_home / 'Library/LaunchAgents'
            agents.mkdir(parents=True)
            private = root / 'private'
            private.mkdir(mode=0o700)
            with patch.object(setup.sys, 'platform', 'darwin'), patch.object(setup.os, 'getuid', return_value=501), patch.object(Path, 'home', return_value=fake_home):
                existing = private / 'collector.json'
                existing.write_text('existing configuration')
                with patch.object(setup.subprocess, 'run', side_effect=AssertionError('Reject before launching')):
                    refuses(lambda: setup.install(prepared))
                assert existing.read_text() == 'existing configuration'
                existing.unlink()
                legacy = agents / (setup.LABEL + '.plist')
                legacy.write_text('existing tunnel')
                with patch.object(setup.subprocess, 'run', side_effect=AssertionError('Reject legacy service')):
                    refuses(lambda: setup.install(prepared))
                assert legacy.read_text() == 'existing tunnel'
                legacy.unlink()
                calls = []

                def launchctl(args, **kwargs):
                    calls.append(args)
                    code = 113 if args[1] == 'print' and args[2].count('/') > 1 else 0
                    return subprocess.CompletedProcess(args, code)

                with patch.object(setup.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                    refuses(lambda: setup.install(prepared))
                assert not existing.exists() and not list(agents.iterdir())
                with patch.object(setup.subprocess, 'run', side_effect=launchctl), patch.object(setup.socket, 'socket') as busy:
                    busy.return_value.__enter__.return_value.bind.side_effect = OSError('Synthetic occupied port')
                    refuses(lambda: setup.install(prepared))
                assert not existing.exists() and not list(agents.iterdir())
                calls.clear()
                with patch.object(setup.subprocess, 'run', side_effect=launchctl), patch.object(setup.socket, 'socket'):
                    setup.install(absent)
                assert len([args for args in calls if args[1] == 'bootstrap']) == 3
                assert not any(args[1] == 'bootout' for args in calls)
                assert not any(args[1] == 'bootstrap' and args[-1].endswith('.collector.plist') for args in calls)
                assert stat.S_IMODE(existing.stat().st_mode) == 0o600
                for file in agents.iterdir():
                    assert stat.S_IMODE(file.stat().st_mode) == 0o600
                    file.unlink()
                existing.unlink()
                calls.clear()

                def fails_agent(args, **kwargs):
                    result = launchctl(args, **kwargs)
                    if args[1] == 'bootstrap' and args[-1].endswith('.agent.plist'):
                        result.returncode = 5
                    return result

                with patch.object(setup.subprocess, 'run', side_effect=fails_agent), patch.object(setup.socket, 'socket'):
                    refuses(lambda: setup.install(prepared))
                assert not existing.exists() and not list(agents.iterdir())
                assert len([args for args in calls if args[1] == 'bootout']) == 2
                calls.clear()

                def fails_backup(args, **kwargs):
                    result = launchctl(args, **kwargs)
                    if args[1] == 'bootstrap' and args[-1].endswith('.backup.plist'):
                        result.returncode = 5
                    return result

                with patch.object(setup.subprocess, 'run', side_effect=fails_backup), patch.object(setup.socket, 'socket'):
                    refuses(lambda: setup.install(prepared))
                assert len([args for args in calls if args[1] == 'bootstrap']) == 4
                assert len([args for args in calls if args[1] == 'bootout']) == 4
                assert not existing.exists() and not list(agents.iterdir())
            assert not any(args[-1].endswith('/local.family-learning.plist') for args in calls)

            mobile = setup.plan(root, mobile_url='https://box.example.invalid/family')
            assert mobile['mobile_url'] == 'https://box.example.invalid/family'
            web = plistlib.loads(mobile['files']['LaunchAgents/' + setup.LABEL + '.web.plist'])
            assert web['EnvironmentVariables']['FAMILY_CHILD_SECURE'] == '1'
            assert web['EnvironmentVariables']['FAMILY_CHILD_COOKIE_PATH'] == '/family/child/'
            assert web['EnvironmentVariables']['FAMILY_CHILD_PUBLIC_URL'] == 'https://box.example.invalid/family/child/'
            assert web['EnvironmentVariables']['FAMILY_CALENDAR_ID'] == 'local-family-learning'
            assert all(key not in web['EnvironmentVariables'] for key in ('FAMILY_LLM_API_KEY', 'FAMILY_USER'))
            assert 'password' not in repr(mobile)
            for invalid in ('http://box.example.invalid/family', 'https://box.example.invalid/family?x=1',
                            'https://user:pass@box.example.invalid/family', ' https://box.example.invalid',
                            'https://127.0.0.1/family', 'https://bad_host.example.invalid/family',
                            'https://box.example.invalid/../family'):
                refuses(lambda value=invalid: setup.plan(root, mobile_url=value))
            root_mobile = setup.plan(root, mobile_url='https://box.example.invalid/')
            root_web = plistlib.loads(root_mobile['files']['LaunchAgents/' + setup.LABEL + '.web.plist'])
            assert root_web['EnvironmentVariables']['FAMILY_CHILD_COOKIE_PATH'] == '/child/'
            assert root_web['EnvironmentVariables']['FAMILY_CHILD_PUBLIC_URL'] == 'https://box.example.invalid/child/'
            destination = setup.output(mobile, base / '手机入口输出 <&>')
            credentials_path = destination / 'private/手机访问凭据.json'
            access_path = destination / 'private/access.json'
            credentials = json.loads(credentials_path.read_text())
            assert credentials['base_url'] == mobile['mobile_url'] and credentials['username'] == 'family'
            assert len(credentials['password']) >= 24 and credentials['password'].encode() not in access_path.read_bytes()
            assert stat.S_IMODE(credentials_path.stat().st_mode) == stat.S_IMODE(access_path.stat().st_mode) == 0o600
            with contextlib.redirect_stdout(io.StringIO()) as printed, patch.object(setup.secrets, 'token_urlsafe', side_effect=AssertionError('No credential in dry run')):
                assert setup.main(['--root', str(root), '--mobile-url', mobile['mobile_url']]) == 0
            assert credentials['password'] not in printed.getvalue()
            mobile_refuse = setup.plan(root, mobile_url=mobile['mobile_url'])
            (root / 'private/access.json').write_text('existing access')
            with patch.object(setup.subprocess, 'run', side_effect=AssertionError('Reject before launching')):
                refuses(lambda: setup.install(mobile_refuse))
            (root / 'private/access.json').unlink()
            mobile_calls = []
            def fails_mobile(args, **kwargs):
                mobile_calls.append(args)
                result = launchctl(args, **kwargs)
                if args[1] == 'bootstrap' and args[-1].endswith('.agent.plist'):
                    result.returncode = 5
                return result
            with patch.object(setup.subprocess, 'run', side_effect=fails_mobile), patch.object(setup.socket, 'socket'), \
                    patch.object(setup.sys, 'platform', 'darwin'), patch.object(setup.os, 'getuid', return_value=501), \
                    patch.object(Path, 'home', return_value=fake_home):
                refuses(lambda: setup.install(mobile_refuse))
            assert len([args for args in mobile_calls if args[1] == 'bootstrap']) == 2
            assert len([args for args in mobile_calls if args[1] == 'bootout']) == 2
            assert not (root / 'private/access.json').exists()
            assert not (root / 'private/手机访问凭据.json').exists()
    print('PASS: Mac setup dry run, XML paths, permissions, missing CLI, old-service refusal and isolated install rollback')


if __name__ == '__main__':
    check()

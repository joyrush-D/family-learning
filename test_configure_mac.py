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
        for name in ('app.py', 'family_agent.py', 'family_collect.py'):
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
            assert prepared['collector_enabled']
            destination = setup.output(prepared, base / '检查输出 <&>')
            for path in destination.rglob('*'):
                assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
            config = json.loads((destination / 'private/collector.json').read_text())
            assert config == {'app_url': 'http://127.0.0.1:8765', 'wechat_cli': str(wechat), 'qq_cli': str(qq)}
            for kind, interval in (('web', None), ('agent', 60), ('collector', None)):
                raw = (destination / ('LaunchAgents/' + setup.LABEL + '.' + kind + '.plist')).read_bytes()
                plist = plistlib.loads(raw)
                assert b'&amp;' in raw and b'&lt;' in raw
                assert plist['WorkingDirectory'] == str(root)
                assert plist['ProgramArguments'][0] == str(Path(setup.sys.executable).resolve())
                assert plist['ProgramArguments'][1] == str(root / ('app.py' if kind == 'web' else 'family_' + kind.replace('collector', 'collect') + '.py'))
                assert plist['EnvironmentVariables']['FAMILY_DATA'] == str(root / 'private')
                assert plist.get('StartInterval') == interval and plist['RunAtLoad']
                if kind == 'collector':
                    assert plist['ProgramArguments'][-2:] == ['--interval', '300'] and '--once' not in plist['ProgramArguments']
                    assert plist['KeepAlive'] == {'SuccessfulExit': False} and plist['ThrottleInterval'] == 300
                elif kind == 'web':
                    assert plist['KeepAlive'] is True and plist['ThrottleInterval'] == 10
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
                assert len([args for args in calls if args[1] == 'bootstrap']) == 2
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
                assert not any(args[-1].endswith('/local.family-learning.plist') for args in calls)
    print('PASS: Mac setup dry run, XML paths, permissions, missing CLI, old-service refusal and isolated install rollback')


if __name__ == '__main__':
    check()

"""Build/run a synthetic native collector, without chat access, launchd or TCC changes."""
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import family_collector_mac as package


def check():
    if sys.platform != 'darwin':
        print('SKIP: native collector check requires macOS and Apple command line tools')
        return
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        root = base / '虚构应用 <&> 空格'
        root.mkdir()
        private = root / 'private'
        private.mkdir()
        config = private / 'collector.json'
        config.write_text(json.dumps({'app_url': 'http://127.0.0.1:8765', 'wechat_cli': '/usr/bin/true'}))
        config.chmod(0o600)
        original = config.read_bytes()
        for name in ('app.py', 'family_agent.py', 'family_backup.py'):
            (root / name).write_text('# Synthetic, never executed.\n')
        (root / 'family_collect.py').write_text('''import json, os, signal, subprocess, sys, time
from pathlib import Path
stop = False
def stopping(*_):
    global stop
    stop = True
signal.signal(signal.SIGTERM, stopping)
child_code = """import signal, time
from pathlib import Path
def stop(*_):
    Path('private/child-stopped').write_text('stopped')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
Path('private/child-ready').write_text('ready')
while True: time.sleep(.02)
"""
child = subprocess.Popen([sys.executable, '-c', child_code])
Path('private/receipt.json').write_text(json.dumps(dict(args=sys.argv[1:], cwd=os.getcwd(),
    pythonpath=os.environ.get('PYTHONPATH'), pythonhome=os.environ.get('PYTHONHOME'),
    no_user_site=os.environ.get('PYTHONNOUSERSITE'), pid=os.getpid(), ppid=os.getppid(), child=child.pid)))
while not stop: time.sleep(.02)
child.wait(timeout=3)
Path('private/parent-stopped').write_text('stopped')
raise SystemExit(13)
''')
        output = base / '本机构建'
        app = package.build(root, config, output)
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        plist = plistlib.loads((output / (package.LABEL + '.collector.plist')).read_bytes())
        binary = app / 'Contents/MacOS/FamilyCollector'
        assert info['CFBundleIdentifier'] == package.BUNDLE_ID
        assert plist['ProgramArguments'] == [str(binary)] and plist['RunAtLoad'] and not plist['Disabled']
        assert plist['KeepAlive'] == {'SuccessfulExit': False}
        assert info['FamilyConfig'] == str(config) and config.read_bytes() == original
        try:
            package.build(root, config, output)
        except FileExistsError:
            pass
        else:
            raise AssertionError('Must not overwrite an existing app')
        assert config.read_bytes() == original
        assert subprocess.run([str(binary), '--arbitrary-command'], capture_output=True, timeout=5).returncode == 78
        process = subprocess.Popen([str(binary)], stdin=subprocess.DEVNULL,
            env=dict(os.environ, PYTHONHOME='/invalid-synthetic-python', PYTHONPATH='/invalid-synthetic-path'))
        try:
            deadline = time.monotonic() + 8
            while not (private / 'child-ready').exists() or not (private / 'receipt.json').exists():
                assert process.poll() is None and time.monotonic() < deadline, 'Collector failed to start'
                time.sleep(.02)
            receipt = json.loads((private / 'receipt.json').read_text())
            assert receipt['args'] == ['--config', str(config), '--interval', '300']
            assert receipt['cwd'] == str(root) and receipt['ppid'] == process.pid
            assert receipt['pythonpath'] is None and receipt['pythonhome'] is None
            assert receipt['no_user_site'] == '1'
            assert subprocess.run([str(binary)], capture_output=True, timeout=3).returncode == 0
            assert json.loads((private / 'receipt.json').read_text()) == receipt, 'No duplicate collector'
            process.send_signal(signal.SIGTERM)
            assert process.wait(timeout=6) == 13, 'Preserve the collector exit status'
            assert (private / 'parent-stopped').exists() and (private / 'child-stopped').exists()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
        with patch.object(package.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'synthetic-build')):
            try:
                package.build(root, config, base / 'failed-build')
            except subprocess.CalledProcessError:
                pass
            else:
                raise AssertionError('Build failure must be reported')
        assert not (base / 'failed-build').exists() and config.read_bytes() == original
        link = base / 'linked-config'
        link.symlink_to(config)
        try:
            package.build(root, link, base / 'bad-link')
        except ValueError:
            pass
        else:
            raise AssertionError('Symlink configuration must be refused')
        assert not (base / 'bad-link').exists()
        private.rename(base / 'moved-private')
        try:
            package.build(root, base / 'moved-private/collector.json', base / 'uninitialized-app')
        except ValueError:
            pass
        else:
            raise AssertionError('Missing application log/lock directory must be refused')
        assert not (base / 'uninitialized-app').exists()
    print('PASS: native app, fixed command, private configuration, signal/child cleanup and failed build')


if __name__ == '__main__':
    check()

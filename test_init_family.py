"""python3 test_init_family.py — fictional temporary data only."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from init_family import initialize


def rejected(call):
    try:
        call()
    except (ValueError, OSError):
        return
    raise AssertionError('Unsafe or invalid initialization was accepted')


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp).resolve()
    app_root = root / 'example'
    app_root.mkdir()
    initialize(app_root, [('示例甲', '四年级'), ('示例乙', '初一')])
    assert (app_root / 'private/uploads').is_dir()
    assert (app_root / 'private/attachments').is_dir()
    assert (app_root / '家庭运行规则.md').stat().st_mode & 0o777 == 0o600
    env = dict(os.environ, FAMILY_DATA=str(app_root / 'private'))
    subprocess.run([sys.executable, '-c', '''
from pathlib import Path
import sys
import app
app.ROOT = Path(sys.argv[1])
assert [(c['name'], c['grade']) for c in app.profiles()] == [('示例甲', '四年级'), ('示例乙', '初一')]
assert app.tasks() == []
state = app.snapshot()
assert state['records'] == [] and state['uploads'] == [] and state['care']['items'] == []
app.save_record(dict(child='示例乙', day='2026-01-01', category='学习进展', title='虚构持久化检查'))
''', str(app_root)], env=env, check=True)
    with sqlite3.connect(app_root / 'private/family.sqlite3') as db:
        assert db.execute('SELECT child,title FROM records').fetchall() == [('示例乙', '虚构持久化检查')]
    before = (app_root / '家庭运行规则.md').read_bytes()
    rejected(lambda: initialize(app_root, [('另一虚构姓名', '二年级')]))
    assert (app_root / '家庭运行规则.md').read_bytes() == before

    blank = root / 'blank'
    blank.mkdir()
    for invalid in ([], [('甲', '')], [('甲|乙', '一年级')], [('甲\n乙', '一年级')], [('甲（备注）', '一年级')], [('甲', '一年级'), ('甲', '二年级')]):
        rejected(lambda: initialize(blank, invalid))
        assert list(blank.iterdir()) == []
    (blank / 'private').mkdir()
    (blank / 'private/keep.txt').write_bytes(b'keep')
    rejected(lambda: initialize(blank, [('示例丙', '二年级')]))
    assert (blank / 'private/keep.txt').read_bytes() == b'keep'

    interactive = root / 'interactive'
    interactive.mkdir()
    (interactive / 'private').mkdir()
    script = str(Path(__file__).with_name('init_family.py'))
    subprocess.run([sys.executable, script, '--root', str(interactive)], input='示例丁\n五年级\n\n', text=True, capture_output=True, check=True)
    assert '| child-1 | 示例丁 | 未填写 | 未填写 | 五年级 |' in (interactive / '家庭运行规则.md').read_text()
    cli = root / 'cli'
    cli.mkdir()
    subprocess.run([sys.executable, script, '--root', str(cli), '--child', '示例戊', '三年级'], capture_output=True, check=True)
    assert (cli / '跟踪台账.md').is_file()

print('Initialization checks passed: CLI, interactive input, app readers, persistent record and no overwrite.')

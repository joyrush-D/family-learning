"""DeepTutor LearningService的子进程客户端（只给“新题再试”的登记/判定用）。

由隔离的py>=3.11+pydantic2解释器（FAMILY_DEEPTUTOR_PYTHON）以`python -I`运行deeptutor_sidecar.py：
清空环境（不设HOME、不碰用户目录；临时数据只在FAMILY_DEEPTUTOR_TMP或系统临时目录下的
family-deeptutor里，用DeepTutor原DEEPTUTOR_HOME参数显式指向）、无网络、一次请求一行JSON、带超时。没配置或运行失败时只降级当前这一步，原错题、诊断、
引导和每日待办照常可用；家庭SQLite仍是唯一主数据，子进程的临时目录用完即弃。"""
import json, os, subprocess, tempfile
from pathlib import Path

SIDECAR = Path(__file__).resolve().parent / 'deeptutor_sidecar.py'
TIMEOUT = 30


class DeepTutorUnavailable(RuntimeError):
    pass


def python():
    path = os.environ.get('FAMILY_DEEPTUTOR_PYTHON', '')
    return path if path and Path(path).is_file() and os.access(path, os.X_OK) else ''


def status():
    return {'available': bool(python()), 'message': '' if python() else '新题判定组件未配置；可以先做诊断和看说明，复测稍后再记'}


def work_root():
    """sidecar临时数据的显式根目录（不是HOME）：每次调用在其下建一次性目录，用完即删。"""
    root = Path(os.environ.get('FAMILY_DEEPTUTOR_TMP') or Path(tempfile.gettempdir()) / 'family-deeptutor')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def call(op, snapshot, **request):
    py = python()
    if not py: raise DeepTutorUnavailable('新题判定组件未配置，这一步没有保存；原错题和诊断照常保留，配置后可用同一提交重试')
    with tempfile.TemporaryDirectory(prefix='call-', dir=work_root()) as work:
        try:
            proc = subprocess.run([py, '-I', '-B', str(SIDECAR)], input=json.dumps(dict(request, op=op, snapshot=snapshot or None, work_dir=work)) + '\n',
                                  capture_output=True, text=True, timeout=TIMEOUT, cwd=work,
                                  env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'DEEPTUTOR_HOME': work})
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeepTutorUnavailable('新题判定组件没有及时完成，这一步没有保存，可以重试') from exc
    try: out = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError): out = {}
    if not out.get('ok'):
        raise DeepTutorUnavailable('新题判定组件返回错误（%s），这一步没有保存，可以重试' % (out.get('error') or 'no output'))
    return out

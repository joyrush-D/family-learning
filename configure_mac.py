"""Configure this application on an existing Mac; never install other software.

No arguments: inspect a plan without writing files or starting services.
--output-dir NEW_DIRECTORY: generate private artifacts for review only.
--install: install new login LaunchAgents; refuse existing services/configuration.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys
from urllib.parse import urlsplit

from family_backup import no_links
from family_collect import app_url, CollectError


LABEL = 'local.family-learning'


def cli_path(value, *, executable=False):
    if not value:
        return None
    path = Path(value).expanduser().resolve(strict=True)
    if not path.is_file() or not os.access(path, os.R_OK) or executable and not os.access(path, os.X_OK):
        raise ValueError('CLI 必须是本机可读文件，微信 CLI 还必须可执行')
    return str(path)


def plan(root, url='http://127.0.0.1:8765', wechat_cli=None, qq_cli=None):
    if sys.version_info < (3, 10):
        raise ValueError('需要 Python 3.10 或以上版本；请使用已安装的新版本运行本命令')
    root = Path(root).expanduser().resolve(strict=True)
    if not root.is_dir() or not all((root / name).is_file() for name in ('app.py', 'family_agent.py', 'family_collect.py')):
        raise ValueError('应用目录缺少 app.py、family_agent.py 或 family_collect.py')
    url = app_url(url)
    if urlsplit(url).hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('本机完整安装使用 http://127.0.0.1:端口 或 http://localhost:端口')
    python = str(Path(sys.executable).resolve(strict=True))
    wechat = cli_path(wechat_cli or shutil.which('wechat-cli'), executable=True)
    qq = cli_path(qq_cli)
    config = {'app_url': url}
    if wechat:
        config['wechat_cli'] = wechat
    if qq:
        config['qq_cli'] = qq
    enabled = bool(wechat or qq)
    private = no_links(root / 'private')
    path = os.pathsep.join(dict.fromkeys([str(Path(p).parent) for p in (python, wechat, qq) if p] +
                                       ['/opt/homebrew/bin', '/usr/local/bin', '/usr/bin', '/bin', '/usr/sbin', '/sbin']))
    files = {'private/collector.json': (json.dumps(config, ensure_ascii=False, indent=2) + '\n').encode()}
    for kind, script, interval in (('web', 'app.py', None), ('agent', 'family_agent.py', 60), ('collector', 'family_collect.py', 300)):
        arguments = [python, str(root / script)]
        if kind == 'agent':
            arguments += ['--root', str(root), '--data', str(private), '--once']
        if kind == 'collector':
            arguments += ['--config', str(private / 'collector.json'), '--interval', str(interval)]
        plist = dict(Label=LABEL + '.' + kind, ProgramArguments=arguments, WorkingDirectory=str(root),
                     RunAtLoad=kind != 'collector' or enabled, ProcessType='Background', Umask=0o077,
                     EnvironmentVariables={'PATH': path, 'PYTHONUNBUFFERED': '1', 'FAMILY_DATA': str(private),
                                           'PORT': str(urlsplit(url).port or 80)},
                     StandardOutPath=str(private / (kind + '.stdout.log')),
                     StandardErrorPath=str(private / (kind + '.stderr.log')))
        if kind == 'collector':
            plist.update(KeepAlive={'SuccessfulExit': False}, ThrottleInterval=interval)
        elif interval:
            plist['StartInterval'] = interval
        else:
            plist.update(KeepAlive=True, ThrottleInterval=10)
        if kind == 'collector' and not enabled:
            plist['Disabled'] = True
        files['LaunchAgents/' + plist['Label'] + '.plist'] = plistlib.dumps(plist)
    return {'root': root, 'url': url, 'collector_enabled': enabled, 'files': files}


def exclusive_write(path, content):
    path = no_links(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as target:
        target.write(content)
        target.flush()
        os.fsync(target.fileno())


def output(plan, directory):
    directory = no_links(Path(directory).expanduser())
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in plan['files'].items():
        exclusive_write(directory / name, content)
    return directory


def install(plan):
    if sys.platform != 'darwin' or os.getuid() == 0:
        raise ValueError('--install 只支持已登录的 macOS 普通用户；不要使用 sudo')
    agents = no_links(Path.home() / 'Library/LaunchAgents')
    private = no_links(plan['root'] / 'private')
    targets = {private / 'collector.json': plan['files']['private/collector.json']}
    targets.update({agents / Path(name).name: content for name, content in plan['files'].items() if name.startswith('LaunchAgents/')})
    labels = [LABEL, LABEL + '.web', LABEL + '.agent', LABEL + '.collector']
    if any(p.exists() or p.is_symlink() for p in [*targets, agents / (LABEL + '.plist')]):
        raise ValueError('已有家庭服务或 collector.json；不会覆盖、卸载或改动，请先核对原安装')
    domain = 'gui/' + str(os.getuid())
    run = lambda *args: subprocess.run(['/bin/launchctl', *args], capture_output=True, timeout=20, check=False)
    if run('print', domain).returncode:
        raise ValueError('当前用户没有可用的图形登录会话')
    for label in labels:
        result = run('print', domain + '/' + label)
        if result.returncode == 0:
            raise ValueError('已有家庭服务运行；不会替换或卸载')
        if result.returncode not in (3, 113):
            raise ValueError('无法确认旧服务状态，未进行安装')
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', urlsplit(plan['url']).port or 80))
        except OSError:
            raise ValueError('应用端口已占用或不可用；不会替换已有应用或隧道') from None
    written, attempted = [], []
    try:
        for target, content in targets.items():
            exclusive_write(target, content)
            written.append(target)
        for kind in ('web', 'agent', 'collector'):
            if kind == 'collector' and not plan['collector_enabled']:
                continue
            target = agents / (LABEL + '.' + kind + '.plist')
            attempted.append(target)
            if run('bootstrap', domain, str(target)).returncode:
                raise ValueError('新服务加载失败；正在撤销本次安装的服务文件，已有家庭资料保留')
    except BaseException as error:
        rollback_failed = False
        for target in reversed(attempted):
            try:
                rollback_failed |= run('bootout', domain, str(target)).returncode not in (0, 3, 113)
            except (OSError, subprocess.TimeoutExpired):
                rollback_failed = True
        if rollback_failed:
            raise ValueError('新服务加载失败且撤销未确认；保留本次配置，请核对 launchctl 状态，未处理其他旧服务') from error
        for target in written:
            if not target.is_symlink() and target.read_bytes() == targets[target]:
                target.unlink()
        raise
    return agents


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--output-dir', type=Path, help='新目录：仅生成检查文件，不安装或加载')
    mode.add_argument('--install', action='store_true', help='明确安装并加载本应用的 macOS 登录服务')
    parser.add_argument('--wechat-cli', help='已安装可执行文件；默认用 which 探测 wechat-cli')
    parser.add_argument('--qq-cli', help='已安装的兼容 QQ 只读 Python 脚本')
    parser.add_argument('--app-url', default='http://127.0.0.1:8765')
    args = parser.parse_args(argv)
    try:
        prepared = plan(args.root, args.app_url, args.wechat_cli, args.qq_cli)
        if args.install:
            print('本应用服务已安装：' + str(install(prepared)))
        elif args.output_dir:
            print('仅生成供检查：' + str(output(prepared, args.output_dir)))
        else:
            print('仅查看计划，未写入文件或启动服务：\n' + '\n'.join(prepared['files']))
        print('网页：' + prepared['url'] + '；Agent 每分钟检查。首次进入网页配置孩子、群归属并明确启用 Agent。')
        print('采集进程保持运行，每轮结束后等 5 分钟再检查；CLI 路径存在不代表登录或消息已读取。' if prepared['collector_enabled'] else
              '消息采集待配置：没有可用 CLI，collector 未加载；网页、手动记录和 Agent 服务仍可用。')
        print('登录后运行；Mac 休眠、关机或退出登录时不能持续工作。未安装或登录任何第三方应用。')
        return 0
    except (OSError, ValueError, CollectError, subprocess.TimeoutExpired) as error:
        print('配置未完成：' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

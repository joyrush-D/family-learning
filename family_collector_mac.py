"""Build a local Mac app identity for the existing collector; never grant access or start it.

Requires the already-installed Apple command line tools. Output is private and
machine-specific, not a signed/notarized binary release for other households.
"""
import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

from configure_mac import LABEL, exclusive_write, plan
from family_backup import no_links
from family_collect import CollectError, load_config


BUNDLE_ID = LABEL + '.collector-host'
APP_NAME = 'FamilyCollector.app'

# A native parent gives macOS a product identity. exec() would replace that parent
# with Python. Keep the parent alive and forward termination to its own group.
HOST_SOURCE = r'''
#include <CoreFoundation/CoreFoundation.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
static volatile sig_atomic_t stopping = 0;
static void stop(int signum) {
    (void)signum;
    if (stopping) return;
    stopping = 1;
    kill(-getpid(), SIGTERM);
}
static int path(CFStringRef key, char *buffer) {
    CFTypeRef value = CFBundleGetValueForInfoDictionaryKey(CFBundleGetMainBundle(), key);
    return value && CFGetTypeID(value) == CFStringGetTypeID()
        && CFStringGetFileSystemRepresentation(value, buffer, PATH_MAX) && buffer[0] == '/';
}
int main(int argc, char **argv) {
    (void)argv;
    char python[PATH_MAX], root[PATH_MAX], config[PATH_MAX], script[PATH_MAX], lock_path[PATH_MAX];
    if (argc != 1 || getuid() == 0 || !path(CFSTR("FamilyPython"), python)
        || !path(CFSTR("FamilyRoot"), root) || !path(CFSTR("FamilyConfig"), config)
        || snprintf(script, sizeof(script), "%s/family_collect.py", root) >= (int)sizeof(script)
        || chdir(root) || access(python, X_OK) || access(script, R_OK) || access(config, R_OK)
        || (getpgrp() != getpid() && setpgid(0, 0))) {
        fputs("Family collector: invalid installation; nothing started.\n", stderr);
        return 78;
    }
    umask(0077);
    if (snprintf(lock_path, sizeof(lock_path), "%s/private/.collector-host.lock", root) >= (int)sizeof(lock_path)) return 78;
    int lock = open(lock_path, O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0600);
    struct stat info;
    if (lock < 0 || fstat(lock, &info) || !S_ISREG(info.st_mode) || info.st_uid != getuid()) return 78;
    if (flock(lock, LOCK_EX | LOCK_NB)) return errno == EWOULDBLOCK ? 0 : 71;
    unsetenv("PYTHONHOME");
    unsetenv("PYTHONPATH");
    setenv("PYTHONNOUSERSITE", "1", 1);
    setenv("PYTHONUNBUFFERED", "1", 1);
    struct sigaction action = {0};
    action.sa_handler = stop;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    char *arguments[] = {python, script, "--config", config, "--interval", "300", NULL};
    pid_t pid;
    int error = posix_spawn(&pid, python, NULL, NULL, arguments, environ);
    if (error) {
        fputs("Family collector: Python could not start.\n", stderr);
        return 71;
    }
    if (stopping) kill(-getpid(), SIGTERM);
    int status;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR) continue;
        stop(SIGTERM);
        return 71;
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
'''


def build(root, config_path, output):
    if sys.platform != 'darwin' or os.getuid() == 0:
        raise ValueError('请使用已登录的 macOS 普通用户构建，不使用 sudo')
    root = no_links(Path(root).expanduser())
    config_path = no_links(Path(config_path).expanduser())
    config = load_config(config_path)
    prepared = plan(root, config['app_url'], config.get('wechat_cli'), config.get('qq_cli'))
    if not (root / 'private').is_dir():
        raise ValueError('应用私有目录尚未初始化，请先核对原安装')
    output = no_links(Path(output).expanduser())
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    app = output / APP_NAME
    try:
        source = output / 'collector-host.c'
        exclusive_write(source, HOST_SOURCE.encode())
        info = dict(CFBundleIdentifier=BUNDLE_ID, CFBundleName='一起成长消息采集',
                    CFBundleDisplayName='一起成长消息采集', CFBundleExecutable='FamilyCollector',
                    CFBundlePackageType='APPL', CFBundleVersion='1', LSBackgroundOnly=True,
                    FamilyPython=str(Path(sys.executable).resolve(strict=True)),
                    FamilyRoot=str(root), FamilyConfig=str(config_path))
        exclusive_write(app / 'Contents/Info.plist', plistlib.dumps(info))
        binary = app / 'Contents/MacOS/FamilyCollector'
        binary.parent.mkdir(mode=0o700)
        subprocess.run(['/usr/bin/xcrun', 'clang', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-framework', 'CoreFoundation', str(source), '-o', str(binary)],
                       check=True, capture_output=True, timeout=60)
        binary.chmod(0o700)
        # ponytail: local ad-hoc signing; rebuilding may require consent again.
        # A distributable binary needs a stable developer identity/notarization.
        subprocess.run(['/usr/bin/codesign', '--sign', '-', str(app)],
                       check=True, capture_output=True, timeout=30)
        subprocess.run(['/usr/bin/codesign', '--verify', '--strict', str(app)],
                       check=True, capture_output=True, timeout=30)
        source.unlink()
        plist = plistlib.loads(prepared['files']['LaunchAgents/' + LABEL + '.collector.plist'])
        enabled = bool(config.get('wechat_cli') or config.get('qq_cli'))
        plist.update(ProgramArguments=[str(binary)], AssociatedBundleIdentifiers=[BUNDLE_ID],
                     RunAtLoad=enabled, Disabled=not enabled)
        exclusive_write(output / (LABEL + '.collector.plist'), plistlib.dumps(plist))
        return app
    except BaseException:
        shutil.rmtree(output)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--config', type=Path, help='已有私有采集配置，默认应用目录内 private/collector.json')
    parser.add_argument('--output-dir', type=Path, required=True, help='新的固定存放目录，不能覆盖已有内容')
    args = parser.parse_args(argv)
    try:
        app = build(args.root, args.config or args.root / 'private/collector.json', args.output_dir)
        print('已构建但未启动或授权：' + str(app))
        return 0
    except (OSError, ValueError, CollectError, subprocess.SubprocessError):
        print('构建未完成；核对现有采集配置、Python 和 Apple 命令行工具，未更改运行服务。', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

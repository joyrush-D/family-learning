"""Home LAN HTTPS: a private family CA and server certificate issued with the system openssl CLI.

The application serves TLS itself; nothing is uploaded and no public certificate authority is involved.
Phones trust the family CA once (Apple profile install), after which browser recording and calendar
subscriptions work on the home network. Certificates stay in private/tls and never enter backups.
"""
import argparse
import hashlib
import ipaddress
import os
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

from family_backup import no_links

DIRECTORY = 'tls'
CA_DAYS = 3650
LEAF_DAYS = 820  # Apple rejects TLS leaf certificates valid for more than 825 days.
NAMES = ('ca.key', 'ca.crt', 'server.key', 'server.crt')
_LAN_NETWORKS = tuple(ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
_LOCAL_NAME = re.compile(r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+local$', re.ASCII)
_ROOT_CONFIG = """[req]
distinguished_name=dn
prompt=no
x509_extensions=v3_ca
[dn]
CN=Family Learning Home CA {suffix}
[v3_ca]
basicConstraints=critical,CA:TRUE
keyUsage=critical,keyCertSign,cRLSign
subjectKeyIdentifier=hash
"""
_LEAF_CONFIG = """[req]
distinguished_name=dn
prompt=no
req_extensions=v3_req
[dn]
CN={common_name}
[v3_req]
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectKeyIdentifier=hash
subjectAltName={alt_names}
"""


class TLSError(ValueError):
    """Safe message about certificate material or the openssl command."""


def lan_host(value):
    """A home network IP address or a .local name that may receive a family certificate."""
    if not isinstance(value, str) or not 0 < len(value) <= 253:
        return False
    try:
        return any(ipaddress.ip_address(value) in network for network in _LAN_NETWORKS)
    except ValueError:
        return bool(_LOCAL_NAME.fullmatch(value.lower()))


def validate_hosts(hosts):
    if not isinstance(hosts, (list, tuple)) or not hosts:
        raise TLSError('请至少提供一个家庭内网 IP 或 .local 名称')
    cleaned = []
    for host in hosts:
        if not lan_host(host):
            raise TLSError('证书只签发给家庭内网 IP（10/172.16/192.168 段）或 .local 名称')
        host = host.lower()
        if host not in cleaned:
            cleaned.append(host)
    if len(cleaned) > 8:
        raise TLSError('一份证书最多包含 8 个地址')
    return cleaned


def paths(data):
    directory = no_links(Path(data) / DIRECTORY)
    return {name: directory / name for name in NAMES}


def openssl_binary():
    found = shutil.which('openssl') or ('/usr/bin/openssl' if os.access('/usr/bin/openssl', os.X_OK) else None)
    if not found:
        raise TLSError('未找到 openssl 命令；macOS 自带 /usr/bin/openssl，Linux 请安装 openssl 后重试')
    return found


def _run(arguments, cwd):
    try:
        result = subprocess.run([openssl_binary(), *arguments], cwd=cwd, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise TLSError('openssl 未能完成签发') from error
    if result.returncode:
        raise TLSError('openssl 签发失败，证书未更改')
    return result.stdout


def _write_private(target, content):
    target = no_links(target)
    with tempfile.NamedTemporaryFile('wb', dir=target.parent, prefix='.' + target.name + '.', delete=False) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(handle.name, 0o600)
    os.replace(handle.name, target)


def _alt_names(hosts):
    parts = []
    for host in hosts:
        try:
            ipaddress.ip_address(host)
            parts.append('IP:' + host)
        except ValueError:
            parts.append('DNS:' + host)
    return ','.join(parts)


def issue(data, hosts):
    """Create the family CA when missing, then issue a fresh server certificate for these hosts."""
    hosts = validate_hosts(hosts)
    files = paths(data)
    directory = files['ca.key'].parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    present = {name for name, path in files.items() if path.exists() or path.is_symlink()}
    if any(files[name].is_symlink() for name in NAMES):
        raise TLSError('证书目录不能包含符号链接')
    if {'ca.key', 'ca.crt'} & present and {'ca.key', 'ca.crt'} - present:
        raise TLSError('证书目录不完整：家庭 CA 的密钥和证书必须同时存在；请核对后再签发')
    with tempfile.TemporaryDirectory(prefix='family-tls-') as scratch:
        work = Path(scratch)
        os.chmod(work, 0o700)
        created_ca = False
        if not {'ca.key', 'ca.crt'} <= present:
            (work / 'ca.cnf').write_text(_ROOT_CONFIG.format(suffix=secrets.token_hex(4)), encoding='utf-8')
            _run(['ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', 'ca.key'], work)
            _run(['req', '-new', '-x509', '-key', 'ca.key', '-days', str(CA_DAYS), '-config', 'ca.cnf', '-sha256', '-out', 'ca.crt'], work)
            created_ca = True
        else:
            shutil.copyfile(files['ca.key'], work / 'ca.key')
            shutil.copyfile(files['ca.crt'], work / 'ca.crt')
        (work / 'server.cnf').write_text(_LEAF_CONFIG.format(common_name=hosts[0], alt_names=_alt_names(hosts)), encoding='utf-8')
        _run(['ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', 'server.key'], work)
        _run(['req', '-new', '-key', 'server.key', '-config', 'server.cnf', '-out', 'server.csr'], work)
        _run(['x509', '-req', '-in', 'server.csr', '-CA', 'ca.crt', '-CAkey', 'ca.key', '-set_serial', '0x' + secrets.token_hex(16),
              '-days', str(LEAF_DAYS), '-sha256', '-extfile', 'server.cnf', '-extensions', 'v3_req', '-out', 'server.crt'], work)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            context.load_cert_chain(str(work / 'server.crt'), str(work / 'server.key'))
        except ssl.SSLError as error:
            raise TLSError('签发的证书无法加载，未写入证书目录') from error
        if created_ca:
            _write_private(files['ca.key'], (work / 'ca.key').read_bytes())
            _write_private(files['ca.crt'], (work / 'ca.crt').read_bytes())
        _write_private(files['server.key'], (work / 'server.key').read_bytes())
        _write_private(files['server.crt'], (work / 'server.crt').read_bytes())
    return dict(status(data), created_ca=created_ca)


def _certificate_text(path):
    return _run(['x509', '-in', str(path), '-noout', '-text', '-enddate'], path.parent).decode('utf-8', 'replace')


def status(data):
    """Read hosts and expiry from the issued certificate without loading private keys into the caller."""
    files = paths(data)
    missing = [name for name in NAMES if not files[name].is_file()]
    if missing:
        return dict(issued=False, hosts=[], expires='', ca_sha256='', directory=str(files['ca.crt'].parent), missing=missing)
    text = _certificate_text(files['server.crt'])
    hosts = []
    match = re.search(r'Subject Alternative Name:\s*\n\s*(.+)', text)
    for item in (match.group(1).split(',') if match else []):
        kind, _, value = item.strip().partition(':')
        if kind in ('IP Address', 'IP', 'DNS') and value:
            hosts.append(value.strip().lower())
    expires = re.search(r'notAfter=(.+)', text)
    return dict(issued=True, hosts=hosts, expires=expires.group(1).strip() if expires else '',
                ca_sha256=hashlib.sha256(files['ca.crt'].read_bytes()).hexdigest(), directory=str(files['ca.crt'].parent), missing=[])


def covers(data, host):
    try:
        return host.lower() in status(data)['hosts']
    except TLSError:
        return False


def server_context(data):
    """TLS context for the LAN listener; fails clearly when certificates were never issued."""
    files = paths(data)
    if not files['server.crt'].is_file() or not files['server.key'].is_file():
        raise TLSError('尚未签发家庭证书；先运行 python3 family_tls.py --data private issue --host 家庭电脑内网IP')
    for name in ('server.key', 'ca.key'):
        if files[name].is_file() and os.stat(files[name]).st_mode & 0o077:
            raise TLSError('证书私钥权限过宽，请改为仅本用户可读（chmod 600）')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(str(files['server.crt']), str(files['server.key']))
    except (ssl.SSLError, OSError) as error:
        raise TLSError('家庭证书无法加载，请重新签发') from error
    return context


def ca_certificate(data):
    """PEM bytes of the family CA for phone installation, or None before issuing."""
    path = paths(data)['ca.crt']
    if not path.is_file():
        return None
    return path.read_bytes()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parent / 'private', help='应用私有目录')
    commands = parser.add_subparsers(dest='command', required=True)
    issuing = commands.add_parser('issue', help='签发或续签家庭内网证书；家庭 CA 已存在时沿用')
    issuing.add_argument('--host', action='append', required=True, help='家庭电脑的内网 IP 或 .local 名称，可重复')
    commands.add_parser('status', help='显示已签发证书包含的地址和到期日')
    args = parser.parse_args(argv)
    try:
        if args.command == 'issue':
            result = issue(args.data, args.host)
            print(('已创建家庭 CA 并' if result['created_ca'] else '沿用已有家庭 CA，') + '签发证书：' + '、'.join(result['hosts']) + '；到期 ' + result['expires'])
            print('手机首次访问需安装并信任家庭 CA：' + str(paths(args.data)['ca.crt']) + '（也可在手机打开家庭 HTTPS 地址下的 /family-ca.crt）')
            print('CA SHA-256：' + result['ca_sha256'])
        else:
            result = status(args.data)
            if not result['issued']:
                print('尚未签发家庭证书；缺少：' + '、'.join(result['missing']))
                return 1
            print('证书地址：' + '、'.join(result['hosts']) + '；到期 ' + result['expires'] + '；CA SHA-256：' + result['ca_sha256'])
        return 0
    except (TLSError, OSError, ValueError) as error:
        print('证书未完成：' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

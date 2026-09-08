"""Explicitly confirmed PDF print jobs. No printer I/O happens in this module."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import struct
import subprocess
import tempfile
import zipfile
import zlib
import xml.etree.ElementTree as ET

MAX_SOURCE = 20 * 1024 * 1024
MAX_PDF = 50 * 1024 * 1024
MAX_PAGES = 200
MAX_COPIES = 10
SIDES = {'one-sided', 'two-sided-long-edge', 'two-sided-short-edge'}
COLORS = {'monochrome', 'color'}


class PrintError(ValueError):
    def __init__(self, message, code='invalid_print_request', status=400):
        super().__init__(message)
        self.code, self.status = code, status


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,128}', value):
        raise PrintError('打印请求标识不正确')
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise PrintError('打印记录不存在', 'not_found', 404)
    return value


def printer_name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,126}', value):
        raise PrintError('请先选择已配置的打印机')
    return value


def page_selection(value, count):
    if type(count) is not int or not 1 <= count <= MAX_PAGES:
        raise PrintError('PDF页数不在支持范围内')
    if value == 'all':
        return '1' if count == 1 else '1-' + str(count), count
    if not isinstance(value, str) or len(value) > 1000 or not re.fullmatch(r'[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*', value):
        raise PrintError('页码请使用1-3,5的格式')
    pages = set()
    for part in value.split(','):
        ends = [int(n) for n in part.split('-')]
        first, last = ends[0], ends[-1]
        if not 1 <= first <= last <= count:
            raise PrintError('所选页码超出PDF范围')
        pages.update(range(first, last + 1))
    # Canonical ranges make equivalent repeat confirmations idempotent.
    runs = []
    for n in sorted(pages):
        if runs and runs[-1][1] + 1 == n:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ','.join(str(a) if a == b else f'{a}-{b}' for a, b in runs), len(pages)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def _read_file(path, limit):
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as f:
            import stat
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise PrintError('附件不存在', 'not_found', 404)
            data = f.read(limit + 1)
    except OSError:
        raise PrintError('附件无法读取', 'file_unavailable', 404) from None
    if not 0 < len(data) <= limit:
        raise PrintError('文件为空或超过打印大小限制')
    return data


def _jpeg(data):
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise PrintError('JPEG内容不完整')
    pos = 2
    while pos < len(data):
        if data[pos] != 255:
            break
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            break
        marker = data[pos]; pos += 1
        if marker in (0xd8, 0xd9) or 0xd0 <= marker <= 0xd7:
            continue
        if pos + 2 > len(data):
            break
        length = int.from_bytes(data[pos:pos+2], 'big')
        if length < 2 or pos + length > len(data):
            break
        if marker in (0xc0, 0xc1, 0xc2) and length >= 8:
            bits, height, width, channels = struct.unpack('>BHHB', data[pos+2:pos+8])
            if bits != 8 or channels not in (1, 3):
                raise PrintError('暂不支持该JPEG色彩格式，请下载原件')
            return width, height, '/DeviceGray' if channels == 1 else '/DeviceRGB', '/DCTDecode', data
        pos += length
    raise PrintError('无法读取JPEG尺寸')


def _png(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise PrintError('PNG内容不正确')
    pos, chunks, header, ended = 8, [], None, False
    while pos + 12 <= len(data):
        n = int.from_bytes(data[pos:pos+4], 'big')
        kind, body = data[pos+4:pos+8], data[pos+8:pos+8+n]
        if pos + n + 12 > len(data) or zlib.crc32(kind + body) & 0xffffffff != int.from_bytes(data[pos+8+n:pos+12+n], 'big'):
            raise PrintError('PNG内容校验失败')
        if kind == b'IHDR': header = body
        elif kind == b'IDAT': chunks.append(body)
        elif kind == b'IEND': ended = True; break
        elif kind in (b'acTL', b'tRNS'):
            raise PrintError('此PNG格式暂不能预览，请下载原件')
        pos += n + 12
    if not ended or header is None or len(header) != 13:
        raise PrintError('PNG内容不完整')
    width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', header)
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color)
    if not channels or depth != 8 or compression or filtering or interlace or not 0 < width * height <= 16_000_000:
        raise PrintError('暂支持常见8位非交错PNG，请下载原件')
    stride = width * channels
    expected = height * (stride + 1)
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(b''.join(chunks), expected + 1)
    except zlib.error:
        raise PrintError('PNG像素无法读取') from None
    if len(pixels) != expected or not decoder.eof:
        raise PrintError('PNG像素大小不正确')
    output, previous = bytearray(), bytearray(stride)
    for y in range(height):
        start = y * (stride + 1); method = pixels[start]
        row = bytearray(pixels[start+1:start+1+stride])
        if method > 4: raise PrintError('PNG滤波格式不正确')
        for x in range(stride) if method else ():
            a, b, c = (row[x-channels] if x >= channels else 0), previous[x], (previous[x-channels] if x >= channels else 0)
            if method == 1: predictor = a
            elif method == 2: predictor = b
            elif method == 3: predictor = (a+b)//2
            elif method == 4:
                p = a+b-c; distances = [abs(p-a), abs(p-b), abs(p-c)]
                predictor = (a, b, c)[distances.index(min(distances))]
            else: predictor = 0
            row[x] = (row[x] + predictor) & 255
        if color in (4, 6):
            # Flatten transparency onto white paper, keeping print/preview identical.
            for x in range(0, stride, channels):
                alpha = row[x+channels-1]
                output.extend((v*alpha + 255*(255-alpha) + 127)//255 for v in row[x:x+channels-1])
        else: output.extend(row)
        previous = row
    return width, height, '/DeviceGray' if color in (0, 4) else '/DeviceRGB', '/FlateDecode', zlib.compress(output)


def image_pdf(data):
    width, height, space, encoding, payload = _png(data) if data.startswith(b'\x89PNG') else _jpeg(data)
    if not 0 < width * height <= 16_000_000:
        raise PrintError('图片像素超过1600万限制')
    scale = min(547/width, 794/height)
    w, h = width*scale, height*scale
    drawing = f'q {w:.4f} 0 0 {h:.4f} {(595-w)/2:.4f} {(842-h)/2:.4f} cm /Im0 Do Q'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>',
               f'<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace {space} /BitsPerComponent 8 /Filter {encoding} /Length {len(payload)} >>\nstream\n'.encode()+payload+b'\nendstream',
               f'<< /Length {len(drawing)} >>\nstream\n'.encode()+drawing+b'\nendstream']
    result, offsets = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n'), [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result)); result.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref = len(result)
    result.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    result.extend(b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets[1:]))
    result.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(result)


class PrintStore:
    def __init__(self, data, connect, *, pdfinfo=None, soffice=None):
        self.data, self.connect = Path(data).resolve(), connect
        self.directory = self.data / 'print'
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.is_symlink(): raise PrintError('打印存储目录不正确')
        self.pdfinfo = pdfinfo or os.environ.get('FAMILY_PRINT_PDFINFO') or shutil.which('pdfinfo')
        self.soffice = soffice or os.environ.get('FAMILY_PRINT_SOFFICE')
        with self._db(): pass

    @contextmanager
    def _db(self):
        c = self.connect(); c.row_factory = sqlite3.Row
        try:
            c.execute('CREATE TABLE IF NOT EXISTS print_preparations (id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, body TEXT NOT NULL)')
            c.execute("CREATE TABLE IF NOT EXISTS print_jobs (id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, preparation_id TEXT NOT NULL, status TEXT NOT NULL, body TEXT NOT NULL, bridge_id TEXT NOT NULL DEFAULT '', claim_key TEXT UNIQUE, claim_token TEXT NOT NULL DEFAULT '', cups_job_id TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', updated TEXT NOT NULL)")
            c.commit()
            with c: yield c
        finally: c.close()

    def _source(self, source):
        if not isinstance(source, dict): raise PrintError('请选择一个项目附件')
        if source.get('type') == 'upload' and set(source) == {'type', 'id'}:
            ident = _id(source['id'])
            with self._db() as c: row = c.execute('SELECT name FROM uploads WHERE id=?', (ident,)).fetchone()
            if not row: raise PrintError('附件不存在', 'not_found', 404)
            name, base, filename = row['name'], self.data/'uploads', ident
        elif source.get('type') == 'attachment' and set(source) == {'type', 'name'}:
            name = source['name']
            if not isinstance(name, str) or not name or len(name) > 200 or name in ('.', '..') or any(c in name for c in '/\\') or any(ord(c) < 32 or ord(c) == 127 for c in name):
                raise PrintError('附件名称不正确')
            base, filename = self.data/'attachments', name
        else: raise PrintError('只能选择已上传或已归档的附件')
        path = base / filename
        if base.is_symlink() or path.is_symlink() or path.resolve().parent != base.resolve() or not base.resolve().is_relative_to(self.data):
            raise PrintError('附件路径不正确')
        return name, _read_file(path, MAX_SOURCE)

    def _page_count(self, path):
        if not self.pdfinfo:
            raise PrintError('未配置PDF页数工具，请下载原件；暂不能确认打印', 'preview_unavailable', 503)
        try:
            p = subprocess.run([self.pdfinfo, str(path)], capture_output=True, timeout=20, env={**os.environ, 'LC_ALL':'C'})
        except (OSError, subprocess.TimeoutExpired):
            raise PrintError('PDF页数读取失败，请下载原件', 'preview_unavailable', 503) from None
        text = p.stdout.decode('utf-8', 'replace')
        match = re.search(r'^Pages:\s+(\d+)\s*$', text, re.M)
        if p.returncode or not match or re.search(r'^Encrypted:\s+yes', text, re.M):
            raise PrintError('PDF损坏、加密或暂不能预览，请下载原件')
        count = int(match[1])
        if not 1 <= count <= MAX_PAGES: raise PrintError('打印PDF须为1至200页')
        return count

    def _convert(self, data, name, directory):
        suffix = Path(name).suffix.lower()
        if suffix == '.pdf' and data.startswith(b'%PDF-'): return data
        if suffix in ('.jpg', '.jpeg') and data.startswith(b'\xff\xd8') or suffix == '.png' and data.startswith(b'\x89PNG'):
            return image_pdf(data)
        if suffix not in ('.docx', '.pptx'):
            raise PrintError('暂支持PDF、JPEG、PNG；其他文件请下载原件', 'preview_unavailable', 503)
        if not self.soffice:
            raise PrintError('Office转换尚未配置，请下载原件或上传PDF', 'preview_unavailable', 503)
        try:
            import io
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(x.file_size for x in entries) > 100*1024*1024:
                    raise PrintError('Office文件展开后过大')
                for entry in entries:
                    if 'vbaproject' in entry.filename.lower() or entry.filename.startswith(('/', '\\')) or '..' in entry.filename.split('/'):
                        raise PrintError('此Office文件暂不能转换，请下载原件')
                    if entry.filename.endswith('.rels'):
                        relationships = ET.fromstring(archive.read(entry))
                        if any(r.attrib.get('TargetMode','').lower()=='external' for r in relationships.iter()):
                            raise PrintError('含外部资源的Office文件暂不能转换，请下载原件')
        except (zipfile.BadZipFile, OSError, ET.ParseError): raise PrintError('Office内容无法读取') from None
        source = directory / ('source' + suffix); source.write_bytes(data)
        profile = directory/'profile'; profile.mkdir()
        (profile/'user').mkdir()
        (profile/'user'/'registrymodifications.xcu').write_text('<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item></oor:items>')
        try:
            p = subprocess.run([self.soffice, '-env:UserInstallation='+profile.as_uri(), '--headless', '--convert-to', 'pdf', '--outdir', str(directory), str(source)], capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            raise PrintError('Office转换失败，请下载原件或上传PDF', 'preview_unavailable', 503) from None
        if p.returncode or not (directory/'source.pdf').is_file():
            raise PrintError('Office转换未生成PDF，请下载原件', 'preview_unavailable', 503)
        return _read_file(directory/'source.pdf', MAX_PDF)

    def prepare(self, source, idempotency_key):
        key = _key(idempotency_key)
        name, data = self._source(source)
        fingerprint = _hash(_json([source, _hash(data)]).encode())
        with self._db() as c:
            old = c.execute('SELECT * FROM print_preparations WHERE idem=?', (key,)).fetchone()
        if old:
            if old['fingerprint'] != fingerprint: raise PrintError('同一请求的附件已变化，请重新预览', 'conflict', 409)
            self.preview(old['id'])
            return json.loads(old['body'])
        ident = secrets.token_hex(16); target = self.directory/(ident+'.pdf')
        try:
            with tempfile.TemporaryDirectory(prefix='.prepare-', dir=self.directory) as temporary:
                directory = Path(temporary)
                pdf = self._convert(data, name, directory)
                if not pdf.startswith(b'%PDF-') or len(pdf) > MAX_PDF: raise PrintError('预览PDF内容不正确或过大')
                stage = directory/'preview.pdf'; stage.write_bytes(pdf); stage.chmod(0o600)
                pages = self._page_count(stage)
                body = dict(id=ident, name=name, source=source, source_sha256=_hash(data), pdf_sha256=_hash(pdf), size=len(pdf), page_count=pages, status='ready', created=_now(), preview_url='/api/print/preview/'+ident)
                with self._db() as c:
                    c.execute('INSERT INTO print_preparations VALUES (?,?,?,?)', (ident, key, fingerprint, _json(body)))
                    os.replace(stage, target)
            return body
        except sqlite3.IntegrityError:
            target.unlink(missing_ok=True)
            return self.prepare(source, key)
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def preparation(self, ident):
        with self._db() as c: row = c.execute('SELECT body FROM print_preparations WHERE id=?', (_id(ident),)).fetchone()
        if not row: raise PrintError('打印预览不存在', 'not_found', 404)
        return json.loads(row['body'])

    def preview(self, ident):
        info = self.preparation(ident)
        data = _read_file(self.directory/(_id(ident)+'.pdf'), MAX_PDF)
        if _hash(data) != info['pdf_sha256']: raise PrintError('预览内容已变化，请重新准备', 'conflict', 409)
        return data, Path(info['name']).stem + '.pdf'

    def _job(self, row, private=False):
        if not row: raise PrintError('打印任务不存在', 'not_found', 404)
        body = json.loads(row['body'])
        body.update({k:row[k] for k in ['id', 'status', 'cups_job_id', 'note', 'updated']})
        if private: body.update(claim_token=row['claim_token'], bridge_id=row['bridge_id'], pdf_url='/api/print/bridge/pdf/'+row['id'])
        return body

    def enqueue(self, obj):
        if not isinstance(obj, dict) or obj.get('confirmed') is not True: raise PrintError('请先确认打印预览和设置')
        key = _key(obj.get('idempotency_key')); prep = self.preparation(obj.get('preparation_id'))
        if obj.get('pdf_sha256') != prep['pdf_sha256']: raise PrintError('确认的PDF与预览不一致', 'conflict', 409)
        self.preview(prep['id'])
        copies = obj.get('copies', 1)
        if type(copies) is not int or not 1 <= copies <= MAX_COPIES: raise PrintError('打印份数须为1至10')
        sides, color = obj.get('sides', 'one-sided'), obj.get('color', 'monochrome')
        if not isinstance(sides, str) or sides not in SIDES or not isinstance(color, str) or color not in COLORS: raise PrintError('单双面或颜色设置不正确')
        pages, selected = page_selection(obj.get('pages', 'all'), prep['page_count'])
        if selected * copies > 500: raise PrintError('一次打印最多500个页面副本')
        settings = dict(preparation_id=prep['id'], pdf_sha256=prep['pdf_sha256'], printer=printer_name(obj.get('printer')), pages=pages, copies=copies, sides=sides, color=color)
        fingerprint = _hash(_json(settings).encode())
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM print_jobs WHERE idem=?', (key,)).fetchone()
            if old:
                if old['fingerprint'] != fingerprint: raise PrintError('同一打印请求的设置不同', 'conflict', 409)
                return self._job(old)
            ident, now = secrets.token_hex(16), _now()
            body = dict(settings, name=prep['name'], source_sha256=prep['source_sha256'], page_count=prep['page_count'], selected_pages=selected, created=now)
            c.execute('INSERT INTO print_jobs (id,idem,fingerprint,preparation_id,status,body,updated) VALUES (?,?,?,?,?,?,?)', (ident,key,fingerprint,prep['id'],'queued',_json(body),now))
            return self._job(c.execute('SELECT * FROM print_jobs WHERE id=?',(ident,)).fetchone())

    def list_jobs(self):
        with self._db() as c: return [self._job(r) for r in c.execute('SELECT * FROM print_jobs ORDER BY rowid DESC LIMIT 100')]

    def claim(self, bridge_id, printer, request_key):
        _key(bridge_id); _key(request_key); printer_name(printer)
        claim_key = bridge_id+':'+request_key
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT * FROM print_jobs WHERE claim_key=?', (claim_key,)).fetchone()
            if old:
                if json.loads(old['body'])['printer'] != printer: raise PrintError('领取请求不一致', 'conflict', 409)
                return self._job(old, True)
            row = next((r for r in c.execute("SELECT * FROM print_jobs WHERE status='queued' ORDER BY rowid") if json.loads(r['body'])['printer']==printer), None)
            if not row: return None
            c.execute("UPDATE print_jobs SET status='claimed',bridge_id=?,claim_key=?,claim_token=?,updated=? WHERE id=?", (bridge_id,claim_key,secrets.token_urlsafe(32),_now(),row['id']))
            return self._job(c.execute('SELECT * FROM print_jobs WHERE id=?',(row['id'],)).fetchone(), True)

    def claimed_pdf(self, ident, token):
        with self._db() as c: row = c.execute('SELECT * FROM print_jobs WHERE id=?',(_id(ident),)).fetchone()
        if not row or not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(row['claim_token'], token) or row['status'] not in ('claimed','submitted'):
            raise PrintError('打印领取凭据无效', 'forbidden', 403)
        return self.preview(row['preparation_id'])

    def report(self, ident, token, status, cups_job_id='', note=''):
        allowed = {'claimed':{'submitted','failed','uncertain'}, 'submitted':{'spooler_completed','failed','uncertain'}}
        if not isinstance(status, str) or status not in {'submitted','spooler_completed','failed','uncertain'}: raise PrintError('打印状态不正确')
        if not isinstance(note, str) or len(note)>1000: raise PrintError('打印状态说明过长')
        if not isinstance(cups_job_id, str) or cups_job_id and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*-[1-9][0-9]*',cups_job_id): raise PrintError('CUPS作业标识不正确')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM print_jobs WHERE id=?',(_id(ident),)).fetchone()
            if not row or not isinstance(token, str) or not token.isascii() or not secrets.compare_digest(row['claim_token'],token) or not row['claim_token']:
                raise PrintError('打印领取凭据无效', 'forbidden', 403)
            # A lost HTTP acknowledgement may be retried after another observer
            # advanced the job. Acknowledge it without regressing durable state.
            if cups_job_id and cups_job_id == row['cups_job_id'] and (row['status']=='received' or status=='submitted' and row['status'] in ('spooler_completed','failed')):
                return self._job(row)
            if status == row['status']:
                if cups_job_id and cups_job_id != row['cups_job_id']: raise PrintError('CUPS作业标识不能更换', 'conflict', 409)
                return self._job(row)
            if status not in allowed.get(row['status'],set()): raise PrintError('打印状态不能这样更改', 'conflict', 409)
            if row['cups_job_id'] and cups_job_id and row['cups_job_id'] != cups_job_id: raise PrintError('CUPS作业标识不能更换', 'conflict', 409)
            cups = cups_job_id or row['cups_job_id']
            if status in ('submitted','spooler_completed') and not cups: raise PrintError('提交状态必须有CUPS作业标识')
            c.execute('UPDATE print_jobs SET status=?,cups_job_id=?,note=?,updated=? WHERE id=?',(status,cups,note,_now(),ident))
            return self._job(c.execute('SELECT * FROM print_jobs WHERE id=?',(ident,)).fetchone())

    def _parent_action(self, ident, status, note):
        if not isinstance(note, str) or not note.strip() or len(note)>1000: raise PrintError('请填写确认依据')
        with self._db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM print_jobs WHERE id=?',(_id(ident),)).fetchone()
            if not row: raise PrintError('打印任务不存在', 'not_found', 404)
            if row['status'] == status: return self._job(row)
            permitted = {'cancelled':{'queued'}, 'received':{'submitted','spooler_completed'}}
            if row['status'] not in permitted[status]: raise PrintError('此任务状态不能执行该操作', 'conflict', 409)
            c.execute('UPDATE print_jobs SET status=?,note=?,updated=? WHERE id=?',(status,note.strip(),_now(),ident))
            return self._job(c.execute('SELECT * FROM print_jobs WHERE id=?',(ident,)).fetchone())

    def cancel(self, ident):
        return self._parent_action(ident,'cancelled','家长取消尚未领取的任务')

    def confirm_received(self, ident, note):
        return self._parent_action(ident,'received',note)

"""Explicitly confirmed PDF print jobs. No printer I/O happens in this module."""
from contextlib import contextmanager
import datetime as dt
import hashlib
import io
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
import time
import zipfile
import zlib
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from family_wechat_media import MediaError, bounded_process

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


def question_sources(sources, limit=4):
    if not isinstance(sources,list) or not 1<=len(sources)<=limit or any(not isinstance(source,dict) for source in sources):
        raise PrintError('每次请选择1至%d张题目与作答原件'%limit)
    if len({_json(source) for source in sources})!=len(sources):
        raise PrintError('题目原件不能重复选择')
    return sources


def packet_sha(hashes):
    return hashes[0] if len(hashes)==1 else _hash(_json(hashes).encode())


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


def review_text(value, *, saved=False):
    """Saved parent text stays text; only the product's length frame is interpreted."""
    try: text=value.decode('utf-8-sig') if isinstance(value,bytes) else value
    except UnicodeError: raise PrintError('参考或先前检查文字无法安全完整读取') from None
    if not isinstance(text,str) or any(ord(ch)<32 and ch not in '\n\r\t' or ord(ch)==127 for ch in text):
        raise PrintError('参考或先前检查文字无法安全完整读取')
    archived=False
    if saved and text.startswith('作业检查保存格式 v1'):
        header=re.match(r'\A作业检查保存格式 v1\n最新检查字数：([1-9][0-9]{0,4})\n',text)
        if header is None: raise PrintError('保存检查的最新文字范围无法核对')
        size=int(header.group(1));content=text[header.end():]
        if size>12000 or len(content)<size+1 or content[size]!='\n':
            raise PrintError('保存检查的最新文字范围无法核对')
        text=content[:size];archived=bool(content[size+1:].strip())
    if not text.strip() or len(text)>12000:
        raise PrintError('参考或先前检查文字须清晰完整且最多12000字，请分批核对')
    return dict(text=text,has_archived=archived)


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


class OfficeError(ValueError):
    """Why a bounded Office->PDF conversion stopped; each caller maps the reason to its own error type."""
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


OFFICE_LIMITS = dict(entries=10000, total=100 * 1024 * 1024, member=100 * 1024 * 1024)  # The print path's existing bounds.
OFFICE_TIMEOUT = 60
_OFFICE_CHUNK = 64 * 1024  # Members stream through in bounded pieces; only what inspect asks for is kept.
_OFFICE_PROFILE = ('<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
                   '<item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse">'
                   '<value>3</value></prop></item></oor:items>')
_OFFICE_ERRORS = dict(too_large=('Office文件展开后过大',), unsupported=('此Office文件暂不能转换，请下载原件',),
                      external=('含外部资源的Office文件暂不能转换，请下载原件',), unreadable=('Office内容无法读取',),
                      failed=('Office转换失败，请下载原件或上传PDF', 'preview_unavailable', 503),
                      timeout=('Office转换失败，请下载原件或上传PDF', 'preview_unavailable', 503),
                      no_output=('Office转换未生成PDF，请下载原件', 'preview_unavailable', 503),
                      output_invalid=('预览PDF内容不正确或过大',))


def office_check(data, limits, inspect=None, *, deadline=None):
    """Validate one Office ZIP in memory; return (member names, {name: bytes} of the members inspect selects).

    Every member is streamed to its end in bounded chunks, so a bad CRC, a size that differs from the declared one or an
    expansion past the limits stops before any converter opens the file. inspect(name) -> True keeps a whole member;
    an int keeps that many leading bytes; anything else is verified and dropped. Relationship parts are always kept
    and refused when any relationship has TargetMode=External; macro projects, path traversal, duplicate, encrypted or
    oddly compressed entries stop too."""
    def check_time():
        if deadline is not None and time.monotonic() >= deadline: raise OfficeError('timeout')
    check_time()
    parts, names = {}, []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist(); low = [e.filename.lower() for e in entries]
            if len(entries) > limits['entries'] or sum(e.file_size for e in entries) > limits['total']:
                raise OfficeError('too_large')
            if len(set(low)) != len(low) or any(e.file_size > limits['member'] or e.flag_bits & 0x41
                                                 or e.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for e in entries):
                raise OfficeError('unreadable')
            total = 0
            for entry in entries:
                name = entry.filename; names.append(name)
                if 'vbaproject' in name.lower() or name.startswith(('/', '\\')) or '\\' in name or '..' in name.split('/'):
                    raise OfficeError('unsupported')
                want = name.lower().endswith('.rels') or (inspect(name) if inspect else False)
                kept, size = io.BytesIO(), 0
                with archive.open(entry) as f:  # Read to the end: zipfile verifies the CRC only once EOF is reached.
                    while True:
                        check_time()
                        chunk = f.read(min(_OFFICE_CHUNK, limits['member'] + 1 - size))
                        if not chunk: break
                        size += len(chunk); total += len(chunk)
                        if size > limits['member'] or total > limits['total']: raise OfficeError('too_large')
                        if want is True: kept.write(chunk)
                        elif want and kept.tell() < want: kept.write(chunk[:want - kept.tell()])
                if size != entry.file_size: raise OfficeError('unreadable')
                if want: parts[name] = kept.getvalue()
    except OfficeError:
        raise
    except Exception:  # Not a ZIP, truncated, bad CRC, password-protected or otherwise unreadable.
        raise OfficeError('unreadable') from None
    for name, part in parts.items():
        check_time()
        if name.lower().endswith('.rels'):
            if b'<!DOCTYPE' in part or b'<!ENTITY' in part: raise OfficeError('unreadable')
            try: relationships = ET.fromstring(part)
            except ET.ParseError: raise OfficeError('unreadable') from None
            if any(r.attrib.get('TargetMode', '').lower() == 'external' or
                   re.match(r'^(?:[A-Za-z][A-Za-z0-9+.-]*:|//|\\)', r.attrib.get('Target', '').strip())
                   for r in relationships.iter()):
                raise OfficeError('external')
    check_time()
    return names, parts


def office_convert(data, suffix, directory, soffice, *, timeout, limit, read):
    """Convert one checked Office body inside `directory` with a throwaway, macro-locked LibreOffice profile.

    argv only, no shell, stdin closed and the process group killed on timeout or failure; the PDF comes back
    through the caller's bounded read(path, limit) and must carry a PDF header. `timeout` is one budget shared by
    preparing the source and profile, the process and reading the output, never a fresh allowance per step."""
    started = time.monotonic()
    def left():
        remaining = float(timeout) - (time.monotonic() - started)
        if remaining <= 0: raise OfficeError('timeout')
        return remaining
    directory = Path(directory)
    source = directory / ('source' + suffix); source.write_bytes(data)
    profile = directory / 'profile'; (profile / 'user').mkdir(parents=True)
    (profile / 'user' / 'registrymodifications.xcu').write_text(_OFFICE_PROFILE)
    try:
        bounded_process([str(soffice), '-env:UserInstallation=' + profile.as_uri(), '--headless', '--convert-to', 'pdf',
                         '--outdir', str(directory), str(source)], dict(os.environ), left(), 64 * 1024)
    except MediaError as error:
        raise OfficeError({'process_timeout': 'timeout', 'process_unavailable': 'failed', 'invalid_process': 'failed'}
                          .get(error.code, 'no_output')) from None
    output = directory / 'source.pdf'
    if output.is_symlink() or not output.is_file(): raise OfficeError('no_output')
    left(); pdf = read(output, limit); left()
    if not pdf.startswith(b'%PDF-'): raise OfficeError('output_invalid')
    return pdf


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

    def image_for_draft(self, source):
        name, data = self._source(source)
        mime = 'image/jpeg' if name.lower().endswith(('.jpg','.jpeg')) and data.startswith(b'\xff\xd8') else 'image/png' if name.lower().endswith('.png') and data.startswith(b'\x89PNG') else ''
        if not mime: raise PrintError('参考草稿目前只支持一张JPG或PNG题目；PDF、Word可先打印并手动填写核对过的参考')
        (_jpeg if mime=='image/jpeg' else _png)(data)
        return dict(mime=mime,data=data,sha256=_hash(data))

    def images_for_draft(self, sources, *, limit=4):
        sources=question_sources(sources,limit)
        images=[self.image_for_draft(source) for source in sources]
        if sum(len(image['data']) for image in images)>MAX_SOURCE:
            raise PrintError('题目图片合计不能超过20MB')
        return images,packet_sha([image['sha256'] for image in images])

    @staticmethod
    def review_sources(data, questions, references, allowed, *, previous_sources=(), previous_text='', render=True):
        """Explicit same-task originals; PDF subsets are reported, never silently selected."""
        import family_pdf
        import family_media
        previous_sources=list(previous_sources) if isinstance(previous_sources,tuple) else previous_sources
        if (not isinstance(questions,list) or not questions or not isinstance(references,list)
                or len(questions)+len(references)>8 or not isinstance(previous_sources,list) or len(previous_sources)>2
                or len(questions)+len(references)+len(previous_sources)>10):
            raise PrintError('题目、作答及教师参考最多8份；上一轮检查最多2份，合计最多10份原件')
        if (not isinstance(previous_text,str) or len(previous_text)>12000
                or any(ord(ch)<32 and ch not in '\n\r\t' or ord(ch)==127 for ch in previous_text)):
            raise PrintError('上一轮检查文字须完整清晰且最多12000字')
        items=[];seen=set();raw_total=len(previous_text.encode('utf-8'))
        for role,sources in [('question',questions),('reference',references),('previous',previous_sources)]:
            for source in sources:
                if (not isinstance(source,dict) or set(source) not in ({'type','id'},{'type','id','pages'})
                        or source.get('type')!='upload'):
                    raise PrintError('批改只能使用这项作业已保存的原件')
                ident=_id(source['id'])
                if ident not in allowed: raise PrintError('原件不属于这份作答或原作业，请重新打开核对','review_source_not_allowed',403)
                if ident in seen: raise PrintError('同一原件不能重复选作题目、作答、教师参考或上一轮检查')
                seen.add(ident);row=allowed[ident]
                if role!='previous' and row.get('origin')=='review_result':
                    raise PrintError('已保存的检查意见只能作为上一轮待复核内容，不能作为作答或教师参考','review_source_not_allowed',403)
                if role=='previous' and not row['mime'].startswith('text/plain'):
                    raise PrintError('上一轮检查只接受同一作业已保存的纯文字TXT')
                base=Path(data).resolve()/'uploads';path=base/ident
                if base.is_symlink() or path.is_symlink() or path.resolve().parent!=base:
                    raise PrintError('原件路径不正确')
                name,body=row['name'],_read_file(path,MAX_SOURCE)
                if len(body)!=row['size']: raise PrintError('原件大小已变化，请重新上传','review_source_changed',409)
                raw_total+=len(body)
                if raw_total>MAX_SOURCE: raise PrintError('本次原件合计不能超过20MB，请分批核对')
                mime=row['mime'];pages=source.get('pages')
                if pages is not None and (mime!='application/pdf' or not isinstance(pages,list) or not pages
                        or len(pages)>8 or any(type(p) is not int or not 1<=p<=family_pdf.MAX_DOCUMENT_PAGES for p in pages)
                        or len(set(pages))!=len(pages)):
                    raise PrintError('PDF页码须为不重复的1至200整数，一次最多8页')
                canonical=dict(type='upload',id=ident)
                if pages is not None: canonical['pages']=list(pages)
                items.append(dict(role=role,source=canonical,name=name,mime=mime,body=body,sha256=_hash(body),binding=row.get('review_binding')))
        # All PDF probes and batches share the existing total deadline, even with multiple files.
        started=time.monotonic()
        def left():
            remaining=family_pdf.DEADLINE_SECONDS-(time.monotonic()-started)
            if remaining<=0: raise family_pdf.PDFError('render timed out')
            return remaining
        image_count=0;question_documents=[];documents=[];previous_documents=[];coverage=[]
        for item in items:
            mime=item['mime'];body=item['body'];pages=item['source'].get('pages')
            if mime=='application/pdf':
                if not body.startswith(b'%PDF-'): raise PrintError('PDF内容不正确')
                if render:
                    try: count=family_pdf.page_count(body,left())
                    except family_pdf.PDFError: raise PrintError('PDF无法安全读取，请核对原件或重新上传','review_pdf_unavailable',503) from None
                    pages=pages or list(range(1,count+1))
                    if any(page>count for page in pages): raise PrintError('所选页码超出PDF范围')
                    item['source']['pages']=pages;item['page_count']=count
                    omitted=[page for page in range(1,count+1) if page not in pages]
                    selected=page_selection(','.join(map(str,pages)),count)[0]
                    missing=page_selection(','.join(map(str,omitted)),count)[0] if omitted else '无'
                    coverage.append('%s《%s》：共%d页，本次第%s页；未读取页：%s。'%('教师参考' if item['role']=='reference' else '题目/孩子作答',item['name'],count,selected,missing))
                elif pages is None: raise PrintError('批改依据缺少已核对的PDF页码')
                image_count+=len(pages)
            elif mime in ('image/jpeg','image/png','image/webp'):
                if mime=='image/jpeg': _jpeg(body)
                elif mime=='image/png': _png(body)
                elif not (body[:4]==b'RIFF' and body[8:12]==b'WEBP'): raise PrintError('WebP内容不正确')
                image_count+=1
                coverage.append('%s《%s》：本次读取整张照片。'%('教师参考' if item['role']=='reference' else '题目/孩子作答',item['name']))
            elif mime.startswith('text/plain') or item['role']!='previous' and mime==family_media.DOCX_MIME:
                try: text=family_media.docx_text(body) if mime==family_media.DOCX_MIME else body
                except (UnicodeError,MediaError): raise PrintError('题目、作答、参考或先前检查文字无法安全完整读取') from None
                archived=False
                if text is not None:
                    parsed=review_text(text,saved=item['role']=='previous' and allowed[item['source']['id']].get('origin')=='review_result')
                    text=parsed['text'];archived=parsed['has_archived']
                    target=question_documents if item['role']=='question' else previous_documents if item['role']=='previous' else documents
                    target.append(dict(name=item['name'],text=text))
                coverage.append('%s《%s》：%s。'%('题目/孩子作答' if item['role']=='question' else '上一轮待复核意见' if item['role']=='previous' else '教师参考',item['name'],
                    '本次读取最新检查；较早草稿保留在原件，未作为本次复核输入' if archived else '本次读取完整文字'))
            else: raise PrintError('检查支持图片、PDF或安全纯文字TXT/Word；复杂Word请先保留原件并转换为完整PDF')
        if not 0<=image_count<=8 or not image_count and not question_documents: raise PrintError('题目、作答及参考合计最多8张照片/PDF页，或提供可完整读取的文字试卷；本次未调用模型')
        if sum(len(d['text']) for d in question_documents+documents)>12000: raise PrintError('题目、作答与教师参考文字合计最多12000字，请分批核对')
        if sum(len(d['text']) for d in previous_documents)+len(previous_text)>12000:
            raise PrintError('上一轮检查文件与文字合计最多12000字，请分批核对')
        images=[];reference_images=[];image_labels=[];reference_labels=[];total=0
        if render:
            for item in items:
                group=[]
                if item['mime']=='application/pdf':
                    pages=item['source']['pages']
                    for start in range(0,len(pages),family_pdf.MAX_REQUESTED_PAGES):
                        try: rendered=family_pdf.render_pages(item['body'],pages[start:start+family_pdf.MAX_REQUESTED_PAGES],left())
                        except family_pdf.PDFError: raise PrintError('PDF页暂时无法安全读取，已保存原件保留','review_pdf_unavailable',503) from None
                        if rendered['page_count']!=item['page_count']: raise PrintError('PDF页数已变化，请重新核对','review_source_changed',409)
                        group.extend((dict(mime=page['mime_type'],data=page['data']),item['name']+' 第%d页'%page['page']) for page in rendered['pages'])
                elif item['mime'].startswith('image/'):
                    group=[(dict(mime=item['mime'],data=item['body']),item['name'])]
                for image,label in group:
                    total+=len(image['data'])
                    if total+sum(len(d['text'].encode()) for d in question_documents+documents+previous_documents)+len(previous_text.encode('utf-8'))>MAX_SOURCE:
                        raise PrintError('本次图片/PDF页、参考及先前检查文字合计不能超过20MB，请分批核对')
                    if item['role']=='reference': reference_images.append(image);reference_labels.append(label)
                    else: images.append(image);image_labels.append(label)
        packet=[dict(role=i['role'],source=i['source'],name=i['name'],mime=i['mime'],sha256=i['sha256'],binding=i['binding']) for i in items]
        return dict(images=images,reference_images=reference_images,question_documents=question_documents,documents=documents,previous_documents=previous_documents,image_labels=image_labels,
                    reference_labels=reference_labels,coverage=coverage,fingerprint=_hash(_json(packet).encode()),
                    question_sources=[i['source'] for i in items if i['role']=='question'],
                    reference_sources=[i['source'] for i in items if i['role']=='reference'],
                    previous_sources=[i['source'] for i in items if i['role']=='previous'])

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
            office_check(data, OFFICE_LIMITS)
            return office_convert(data, suffix, directory, self.soffice, timeout=OFFICE_TIMEOUT, limit=MAX_PDF, read=_read_file)
        except OfficeError as error:
            raise PrintError(*_OFFICE_ERRORS[error.reason]) from None

    def prepare(self, source, idempotency_key, *, packet=None, revision=False):
        key = _key(idempotency_key)
        name, data = self._source(source)
        return self._prepare_bytes(name, data, source, key,packet=packet,revision=revision)

    def prepare_guide(self, title, text, idempotency_key, *, revision=False):
        """Prepare a separate parent-only answer sheet after the parent has checked its text."""
        key = _key(idempotency_key)
        def invalid_xml(value):
            return any(ord(ch) < 32 and ch not in '\n\t' or ord(ch) == 127 or 0xd800 <= ord(ch) <= 0xdfff or ord(ch) in (0xfffe,0xffff) for ch in value)
        if not isinstance(title, str) or not title.strip() or len(title) > 200 or invalid_xml(title):
            raise PrintError('作业标题不正确')
        if not isinstance(text, str) or not text.strip() or len(text) > 12000 or invalid_xml(text):
            raise PrintError('参考答案与指南须由家长核对，且不超过12000字')
        paragraphs = ['家长参考答案与辅导指南', title.strip(),
                      '仅供家长核对使用；答案与原题有冲突时以原题和老师要求为准。', *text.strip().splitlines()]
        keep=set();start=0
        for end in range(len(paragraphs)+1):
            if end==len(paragraphs) or not paragraphs[end].strip():
                if end-start<=10: keep.update(range(start,end-1))
                start=end+1
        document = ''.join('<w:p><w:pPr><w:keepLines/>'+('<w:keepNext/>' if n in keep else '')+'</w:pPr>'
                           +'<w:r><w:rPr><w:rFonts w:eastAsia="PingFang SC"/></w:rPr>'
                           '<w:t xml:space="preserve">'+escape(line or ' ')+'</w:t></w:r></w:p>'
                           for n,line in enumerate(paragraphs))
        docx = io.BytesIO()
        with zipfile.ZipFile(docx, 'w', zipfile.ZIP_DEFLATED) as archive:
            def write(name, content):
                # Generated text is identical across retries; ZIP timestamps must not change its hash.
                archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), content, compress_type=zipfile.ZIP_DEFLATED)
            write('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>')
            write('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                '</Relationships>')
            write('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                '<w:body>'+document+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
                '</w:body></w:document>')
        name='家长参考-'+re.sub(r'[\\/\x00-\x1f\x7f]', '_', title.strip())[:60]+'.docx'
        return self._prepare_bytes(name, docx.getvalue(),
                                   dict(type='parent_guide', title=title.strip()), key, revision=revision)

    def _prepare_bytes(self, name, data, source, key, *, packet=None, revision=False):
        fingerprint = _hash(_json([source, _hash(data)]+([packet] if packet is not None else [])).encode())
        with self._db() as c:
            old = c.execute('SELECT * FROM print_preparations WHERE idem=?', (key,)).fetchone()
            if revision and (old is None or old['fingerprint'] != fingerprint):
                # Keep every preparation immutable and reuse matching legacy IDs; enqueue keys stay unchanged.
                key = _hash((key+':'+fingerprint).encode())[:32]
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
            with self._db() as c:
                old = c.execute('SELECT * FROM print_preparations WHERE idem=?', (key,)).fetchone()
            if not old or old['fingerprint'] != fingerprint:
                raise PrintError('同一请求的附件已变化，请重新预览', 'conflict', 409)
            self.preview(old['id'])
            return json.loads(old['body'])
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def homework_pair(self, obj, task, *, before_queue=None):
        """One reviewed action queues two independent jobs; retries keep each original request key."""
        if not isinstance(obj, dict) or obj.get('question_confirmed') is not True or obj.get('guide_confirmed') is not True:
            raise PrintError('请分别核对作业题目和家长参考')
        if not isinstance(task, dict) or obj.get('task_id') != task.get('id'):
            raise PrintError('作业事项已变化，请刷新后核对', 'conflict', 409)
        key = _key(obj.get('request_key'))
        questions = question_sources(obj.get('question_sources') if 'question_sources' in obj else [obj.get('question_source')])
        guide = obj.get('guide_source')
        guide_text = obj.get('guide_text', '')
        if (guide is None) == (not bool(guide_text)):
            raise PrintError('请选择参考文件，或填写已核对的参考答案与指南')
        if guide is not None and guide in questions:
            raise PrintError('题目与家长参考须选两份不同的资料')
        settings = {k: obj.get(k, v) for k, v in dict(printer='', copies=1, sides='one-sided', color='monochrome').items()}
        subkey = lambda role: _hash((key+':'+role).encode())[:32]
        prepared=[self.prepare(source,subkey('question_prepare'+(str(n+1) if n else '')),
                               packet=questions if len(questions)>1 else None,revision=True)
                  for n,source in enumerate(questions)]
        expected = obj.get('expected_question_sha256', '')
        if expected and (not isinstance(expected,str) or not re.fullmatch(r'[a-f0-9]{64}',expected) or expected!=packet_sha([p['source_sha256'] for p in prepared])):
            raise PrintError('题目原件与参考草稿生成时不同，请重新核对答案','conflict',409)
        second = (self.prepare(guide, subkey('guide_prepare'),revision=True) if guide is not None else
                  self.prepare_guide(task['title'], guide_text, subkey('guide_prepare'),revision=True))
        def queue(prep, role):
            if before_queue is not None: before_queue()
            return self.enqueue(dict(settings, confirmed=True, preparation_id=prep['id'],
                                     pdf_sha256=prep['pdf_sha256'], idempotency_key=subkey(role+'_enqueue')))
        jobs=[queue(prep,'question'+(str(n+1) if n else '')) for n,prep in enumerate(prepared)]
        return dict(question=jobs[0],questions=jobs,guide=queue(second, 'guide'))

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

"""Local first-page previews of immutable uploads; no model, printer, network or new database."""
from pathlib import Path
import hashlib
import os
import re
import shutil
import tempfile
import threading
import time

import family_media
import family_pdf
import family_print

_LOCK = threading.Lock()
DEADLINE = 20


def read_upload(data, connection, ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):
        raise family_print.PrintError('原件编号不正确','preview_missing',404)
    row=connection.execute('SELECT * FROM uploads WHERE id=?',(ident,)).fetchone()
    directory=Path(data).resolve()/'uploads';path=directory/ident
    if row is None or type(row['size']) is not int or not 0<row['size']<=family_print.MAX_SOURCE or directory.is_symlink() or path.is_symlink() or path.resolve().parent!=directory or not path.is_file():
        raise family_print.PrintError('原件暂不可读取，已保存记录仍保留','preview_missing',404)
    body=family_print._read_file(path,family_print.MAX_SOURCE)
    if len(body)!=row['size']:
        raise family_print.PrintError('原件大小已变化，请核对原件','preview_changed',409)
    return dict(row),body


def first_page(data, connection, ident):
    row,body=read_upload(data,connection,ident)
    digest=hashlib.sha256(body).hexdigest()
    key=hashlib.sha256(('first-page-v1:'+row['mime']+':'+digest).encode()).hexdigest()
    directory=Path(data).resolve()/'original-previews';directory.mkdir(mode=0o700,exist_ok=True)
    target=directory/(key+'.png')
    if directory.is_symlink() or target.is_symlink():
        raise family_print.PrintError('预览缓存路径不正确','preview_unavailable',503)
    started=time.monotonic()
    # One bounded renderer avoids duplicate conversions when the same original appears twice.
    if not _LOCK.acquire(timeout=1):
        raise family_print.PrintError('另一份首页正在准备，请稍后重试','preview_busy',503)
    try:
        if target.is_file():
            try:
                cached=family_print._read_file(target,family_pdf.MAX_PAGE_BYTES);family_pdf._validate_png(cached)
            except (family_pdf.PDFError,family_print.PrintError): target.unlink()
            else: return cached,key
        mime=row['mime']
        if mime=='application/pdf': pdf=body
        elif mime in (family_media.DOCX_MIME,family_media.PPTX_MIME):
            if mime==family_media.DOCX_MIME: family_media.docx_pdf_preflight(body);suffix='.docx'
            else: family_media.pptx_pdf_preflight(body);suffix='.pptx'
            soffice=os.environ.get('FAMILY_PRINT_SOFFICE') or shutil.which('soffice')
            if not soffice: raise family_print.PrintError('本机尚未配置Office转换；可打开原件或另存PDF','preview_unavailable',503)
            with tempfile.TemporaryDirectory(prefix='.office-',dir=directory) as temporary:
                pdf=family_print.office_convert(body,suffix,Path(temporary),soffice,
                    timeout=max(.01,DEADLINE-(time.monotonic()-started)),limit=family_pdf.MAX_BODY_BYTES,read=family_print._read_file)
        else:
            raise family_print.PrintError('首页预览支持PDF及安全纯文字/版式Word、静态PPT；其他格式请打开原件','preview_unavailable',503)
        left=DEADLINE-(time.monotonic()-started)
        if left<=0: raise family_pdf.PDFError('render timed out')
        image=family_pdf.render_pages(bytes(pdf),[1],deadline=left)['pages'][0]['data']
        _,current=read_upload(data,connection,ident)
        if hashlib.sha256(current).hexdigest()!=digest:
            raise family_print.PrintError('生成期间原件已变化，请重新打开核对','preview_changed',409)
        with tempfile.NamedTemporaryFile(dir=directory,prefix='.page-',delete=False) as f:
            staged=Path(f.name);f.write(image);f.flush();os.fchmod(f.fileno(),0o600)
        try: os.replace(staged,target)
        finally: staged.unlink(missing_ok=True)
        return image,key
    except (family_pdf.PDFError,family_media.MediaError,family_print.OfficeError,OSError):
        raise family_print.PrintError('此原件未能安全生成首页；原件保留，可打开原件或重试','preview_unavailable',503) from None
    finally: _LOCK.release()

"""有界 PDF 逐页预览：仅渲染请求页为 PNG，不做 OCR / 模型 / 语音，不判断内容。

纯辅助函数，不落用户路径、不访问网络。调用方必须明确给出 1-based 页码；
返回结果显式标注总页数、未处理页码与是否覆盖全份，部分渲染不得被解读为
全份理解。
"""

import shutil
import struct
import subprocess
import time

MAX_BODY_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_PAGES = 200
MAX_REQUESTED_PAGES = 3
SCALE_LONG_EDGE = 1600
MAX_PAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
DEADLINE_SECONDS = 20.0

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PDFError(Exception):
    """PDF 预览失败。消息为通用类别，不携带 stderr 原文或 PDF 内容。"""


def _tool(path_name):
    found = shutil.which(path_name)
    if not found:
        raise PDFError("pdf tool unavailable: %s" % path_name)
    return found


def _run(argv, payload, timeout):
    if timeout is not None and timeout <= 0:
        raise PDFError("render timed out")
    try:
        result = subprocess.run(
            argv,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise PDFError("render timed out")
    except (OSError, ValueError):
        raise PDFError("pdf tool failed")
    if result.returncode != 0:
        raise PDFError("pdf tool rejected input")
    return result.stdout


def _read_page_count(pdfinfo, body, timeout):
    stdout = _run([pdfinfo, "-"], body, timeout)
    page_count = None
    for line in stdout.splitlines():
        if line.startswith(b"Pages:"):
            try:
                page_count = int(line.split(b":", 1)[1].strip())
            except ValueError:
                page_count = None
            break
    if page_count is None or not 1 <= page_count <= MAX_DOCUMENT_PAGES:
        raise PDFError("invalid pdfinfo result")
    return page_count


def _validate_png(data):
    if not data.startswith(_PNG_SIGNATURE) or len(data) < 24:
        raise PDFError("renderer returned invalid png")
    # IHDR 紧跟签名：长度(4) 'IHDR'(4) 宽(4) 高(4)
    chunk_length = struct.unpack(">I", data[8:12])[0]
    chunk_type = data[12:16]
    if chunk_length < 8 or chunk_type != b"IHDR":
        raise PDFError("renderer returned invalid png")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0 or max(width, height) > SCALE_LONG_EDGE:
        raise PDFError("renderer returned invalid png dimensions")
    return width, height


def _validate_page_numbers(page_numbers):
    if not isinstance(page_numbers, list) or not page_numbers:
        raise PDFError("page_numbers must be a non-empty list")
    normalized = []
    for number in page_numbers:
        # bool 是 int 的子类，明确拒绝
        if isinstance(number, bool) or not isinstance(number, int):
            raise PDFError("page numbers must be int")
        if number < 1:
            raise PDFError("page numbers must be 1-based positive ints")
        normalized.append(number)
    if len(normalized) > MAX_REQUESTED_PAGES:
        raise PDFError("at most %d pages per call" % MAX_REQUESTED_PAGES)
    if len(set(normalized)) != len(normalized):
        raise PDFError("page numbers must be unique")
    return normalized


def render_pages(body, page_numbers, deadline=DEADLINE_SECONDS):
    """渲染指定页为 PNG。

    返回 {"page_count": int, "pages": [...], "omitted_pages": [...],
    "complete": bool}。complete 仅当返回页覆盖整份文档。
    """
    if not isinstance(body, bytes) or not body:
        raise PDFError("body must be non-empty bytes")
    if len(body) > MAX_BODY_BYTES:
        raise PDFError("pdf body exceeds %d bytes" % MAX_BODY_BYTES)
    if (
        not isinstance(deadline, (int, float))
        or isinstance(deadline, bool)
        or deadline <= 0
    ):
        raise PDFError("invalid deadline")

    requested = _validate_page_numbers(page_numbers)

    pdfinfo = _tool("pdfinfo")
    pdftoppm = _tool("pdftoppm")

    start = time.monotonic()

    def remaining():
        left = deadline - (time.monotonic() - start)
        if left <= 0:
            raise PDFError("render timed out")
        return left

    page_count = _read_page_count(pdfinfo, body, remaining())

    for number in requested:
        if number > page_count:
            raise PDFError("page number out of range")

    pages = []
    total = 0
    for number in requested:
        argv = [
            pdftoppm,
            "-f", str(number),
            "-l", str(number),
            "-singlefile",
            "-scale-to", str(SCALE_LONG_EDGE),
            "-png",
            "-",
        ]
        data = _run(argv, body, remaining())
        if not data:
            raise PDFError("renderer produced empty output")
        if len(data) > MAX_PAGE_BYTES:
            raise PDFError("rendered page exceeds size limit")
        _validate_png(data)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise PDFError("rendered pages exceed total size limit")
        pages.append({"page": number, "mime_type": "image/png", "data": data})

    requested_set = set(requested)
    omitted = [p for p in range(1, page_count + 1) if p not in requested_set]
    return {
        "page_count": page_count,
        "pages": pages,
        "omitted_pages": omitted,
        "complete": not omitted,
    }

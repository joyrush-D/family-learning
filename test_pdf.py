"""合成 PDF 逐页预览测试：不使用真实家庭 PDF，最小 PDF 在测试内构造。"""

import shutil
import struct
import subprocess
import unittest
from unittest import mock

import family_pdf
from family_pdf import PDFError, render_pages


def build_pdf(page_count, width=2000, height=1000):
    """构造结构合法的最小多页 PDF（页面无内容流，poppler 可解析）。"""
    objects = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = b" ".join(("%d 0 R" % (3 + i)).encode() for i in range(page_count))
    objects.append(
        b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % page_count
    )
    for _ in range(page_count):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] >>"
            % (width, height)
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index
        out += obj
        out += b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_pos
    return bytes(out)


def png_rgba(width, height):
    """用 zlib 构造一张可通过签名/尺寸检查的最小 PNG。"""
    import zlib

    raw = b""
    row = b"\x00" + b"\xff\x00\x00" * width
    for _ in range(height):
        raw += row

    def chunk(tag, data):
        import zlib as _z

        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", _z.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        family_pdf._PNG_SIGNATURE
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


TOOLS_AVAILABLE = bool(shutil.which("pdfinfo") and shutil.which("pdftoppm"))


class RealRenderTests(unittest.TestCase):
    @unittest.skipUnless(TOOLS_AVAILABLE, "poppler 工具缺失，跳过真实渲染")
    def test_single_page_count_and_complete(self):
        result = render_pages(build_pdf(1), [1])
        self.assertEqual(result["page_count"], 1)
        self.assertEqual(len(result["pages"]), 1)
        self.assertEqual(result["pages"][0]["page"], 1)
        self.assertEqual(result["pages"][0]["mime_type"], "image/png")
        self.assertEqual(result["omitted_pages"], [])
        self.assertTrue(result["complete"])

    @unittest.skipUnless(TOOLS_AVAILABLE, "poppler 工具缺失，跳过真实渲染")
    def test_11_pages_three_requested_reports_8_omitted(self):
        result = render_pages(build_pdf(11), [11, 1, 5])
        self.assertEqual(result["page_count"], 11)
        self.assertEqual([p["page"] for p in result["pages"]], [11, 1, 5])
        self.assertEqual(
            result["omitted_pages"], [2, 3, 4, 6, 7, 8, 9, 10]
        )
        self.assertFalse(result["complete"])

    @unittest.skipUnless(TOOLS_AVAILABLE, "poppler 工具缺失，跳过真实渲染")
    def test_long_edge_scaled_to_1600(self):
        result = render_pages(build_pdf(1, width=2000, height=1000), [1])
        width, height = family_pdf._validate_png(result["pages"][0]["data"])
        self.assertEqual(max(width, height), 1600)


class ValidationTests(unittest.TestCase):
    def test_body_rejections(self):
        with self.assertRaises(PDFError):
            render_pages(b"", [1])
        with self.assertRaises(PDFError):
            render_pages("not bytes", [1])
        with self.assertRaises(PDFError):
            render_pages(b"x" * (family_pdf.MAX_BODY_BYTES + 1), [1])

    def test_page_number_rejections(self):
        for bad in ([], [True], [0], [-1], [1.0], [1, 1], [1, 2, 3, 4]):
            with self.subTest(bad=bad):
                with self.assertRaises(PDFError):
                    render_pages(b"%PDF-x", bad)


def fake_run_factory(page_count=11, pages=None, fail=None, oversized=False):
    """按 argv 分流 pdfinfo / pdftoppm 的合成 _run。"""
    pages = pages or {}

    def fake_run(argv, payload, timeout):
        tool = argv[0]
        if tool.endswith("pdfinfo"):
            if fail == "nonzero":
                return subprocess.CompletedProcess(argv, 1, b"", b"")
            if fail == "badcount":
                return b"Title: x\n"
            return ("Pages:          %d\n" % page_count).encode()
        if fail == "nonzero":
            return subprocess.CompletedProcess(argv, 1, b"", b"")
        if fail == "timeout":
            raise subprocess.TimeoutExpired(argv, timeout)
        if oversized:
            return png_rgba(10, 10) + b"\x00" * (
                family_pdf.MAX_PAGE_BYTES + 1
            )
        if fail == "badpng":
            return b"this is not a png file at all"
        if fail == "empty":
            return b""
        page = int(argv[argv.index("-f") + 1])
        return pages.get(page, png_rgba(1600, 800))

    return fake_run


class MockedToolTests(unittest.TestCase):
    def _patch(self, **kwargs):
        return mock.patch.object(
            family_pdf, "_run", fake_run_factory(**kwargs)
        )

    def test_missing_tool(self):
        with mock.patch.object(family_pdf.shutil, "which", return_value=None):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_timeout(self):
        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout"))
        with mock.patch.object(family_pdf.subprocess, "run", boom):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_nonzero_exit(self):
        def fail(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 1, b"", b"secret stderr")
        with mock.patch.object(family_pdf.subprocess, "run", fail):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_oversized_output(self):
        with self._patch(oversized=True):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_bad_png(self):
        with self._patch(fail="badpng"):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_empty_output(self):
        with self._patch(fail="empty"):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_page_out_of_range(self):
        with self._patch(page_count=2):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [3])

    def test_page_count_over_200_rejected(self):
        with self._patch(page_count=201):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_invalid_pdfinfo_output(self):
        with self._patch(fail="badcount"):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_11_page_coverage_declaration(self):
        with self._patch(page_count=11):
            result = render_pages(b"%PDF-x", [11, 1, 5])
        self.assertEqual(result["page_count"], 11)
        self.assertEqual(result["omitted_pages"], [2, 3, 4, 6, 7, 8, 9, 10])
        self.assertFalse(result["complete"])

    def test_png_dimensions_over_limit_rejected(self):
        big = png_rgba(1601, 10)
        with self._patch(pages={1: big}):
            with self.assertRaises(PDFError):
                render_pages(b"%PDF-x", [1])

    def test_error_messages_dont_leak_stderr(self):
        stderr = b"SECRET FAMILY PDF TEXT in stderr"

        def boom(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], 1.0, stderr=stderr)

        with mock.patch.object(family_pdf.subprocess, "run", boom):
            try:
                render_pages(b"%PDF-x", [1])
            except PDFError as exc:
                self.assertNotIn("SECRET", str(exc))
            else:
                self.fail("PDFError not raised")


if __name__ == "__main__":
    unittest.main(verbosity=2)

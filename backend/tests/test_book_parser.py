"""电子书解析 / 切片测试 — PDF、DOCX、TXT、Markdown、EPUB。"""
import zipfile

import pytest

from app.services.book_parser import BookParseError, chunk_blocks, parse_book


def _write_pdf(path, text="Hello CodeMentor PDF"):
    """生成一个最小的单页文字版 PDF，用于 pypdf 提取测试。"""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    content = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def test_parse_txt(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("第1章 树\n\n红黑树是一种平衡树。\n\n第2章 排序\n\n快速排序最坏 O(n²)。", encoding="utf-8")
    book = parse_book(p, ".txt", "笔记")
    assert book.title == "笔记"
    text = "\n".join(b.text for b in book.blocks)
    assert "红黑树" in text and "快速排序" in text


def test_parse_markdown_keeps_code_and_headings(tmp_path):
    p = tmp_path / "book.md"
    p.write_text(
        "# 数据结构笔记\n\n## 第1章 树\n\n红黑树很重要。\n\n"
        "```python\nprint('hello')\n```\n\n## 第2章 排序\n\n快排 O(n log n)。",
        encoding="utf-8",
    )
    book = parse_book(p, ".md", "笔记")
    assert book.title == "数据结构笔记"
    assert any(b.kind == "code" and "print" in b.text for b in book.blocks)
    assert any(b.kind == "heading" and "第1章" in b.text for b in book.blocks)


def test_parse_docx(tmp_path):
    from docx import Document

    p = tmp_path / "book.docx"
    doc = Document()
    doc.add_heading("第1章 树", level=1)
    doc.add_paragraph("红黑树是一种自平衡二叉搜索树。")
    doc.add_heading("1.1 AVL", level=2)
    doc.add_paragraph("AVL 的平衡因子不超过 1。")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "算法"
    table.cell(0, 1).text = "复杂度"
    table.cell(1, 0).text = "快排"
    table.cell(1, 1).text = "O(n log n)"
    doc.save(p)

    book = parse_book(p, ".docx", "算法笔记")
    text = "\n".join(b.text for b in book.blocks)
    assert "红黑树" in text and "平衡因子" in text
    assert "算法 | 复杂度" in text


def test_parse_pdf(tmp_path):
    p = tmp_path / "book.pdf"
    _write_pdf(p)
    book = parse_book(p, ".pdf", "PDF")
    text = "\n".join(b.text for b in book.blocks)
    assert "Hello CodeMentor PDF" in text


def test_parse_pdf_without_text_raises(tmp_path):
    p = tmp_path / "empty.pdf"
    _write_pdf(p, text="")
    with pytest.raises(BookParseError, match="扫描版"):
        parse_book(p, ".pdf", "空 PDF", ocr_mode="off")


def test_parse_scanned_pdf_uses_ocr(tmp_path, monkeypatch):
    from app.services import book_parser

    p = tmp_path / "scan.pdf"
    _write_pdf(p, text="")
    calls = {}

    def fake_ocr(path, page_numbers, dpi, progress_cb=None, cache_path=None):
        calls["pages"] = list(page_numbers)
        calls["dpi"] = dpi
        if progress_cb:
            progress_cb(1.0)
        return {1: "第1章 扫描页\n\nOCR 识别出的正文。"}

    monkeypatch.setattr(book_parser, "_ocr_pdf_pages", fake_ocr)
    book = parse_book(p, ".pdf", "扫描讲义", ocr_mode="auto", ocr_dpi=180)
    text = "\n".join(b.text for b in book.blocks)
    assert "OCR 识别出的正文" in text
    assert calls["pages"] == [1]
    assert calls["dpi"] == 180
    assert all(b.page == 1 for b in book.blocks)


def test_ocr_page_cache_reuses_recognized_pages(tmp_path, monkeypatch):
    from PIL import Image

    from app.services import book_parser

    p = tmp_path / "scan.pdf"
    Image.new("RGB", (400, 600), "white").save(p, "PDF")
    calls = {"n": 0}

    class FakeEngine:
        def __call__(self, _image):
            calls["n"] += 1
            box = [[0, 0], [20, 0], [20, 10], [0, 10]]
            return [[box, "缓存正文", 0.99]], None

    monkeypatch.setattr(book_parser, "_get_ocr_engine", lambda: FakeEngine())
    cache = tmp_path / "ocr_pages.json"
    first = book_parser._ocr_pdf_pages(p, [1], 150, cache_path=cache)
    second = book_parser._ocr_pdf_pages(p, [1], 150, cache_path=cache)
    assert first == second == {1: "缓存正文"}
    assert calls["n"] == 1

    # DPI 变化后缓存失效，需要重新识别
    third = book_parser._ocr_pdf_pages(p, [1], 120, cache_path=cache)
    assert third == {1: "缓存正文"}
    assert calls["n"] == 2


def test_parse_epub(tmp_path):
    p = tmp_path / "book.epub"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>EPUB 测试书</dc:title>'
            '</metadata><manifest><item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="c1"/></spine></package>',
        )
        z.writestr(
            "OEBPS/ch1.xhtml",
            "<html><body><h1>第1章 树</h1><p>红黑树是一种自平衡二叉搜索树。</p>"
            "<h2>1.1 AVL</h2><p>AVL 的平衡因子不超过 1。</p></body></html>",
        )
    book = parse_book(p, ".epub", "EPUB")
    assert book.title == "EPUB 测试书"
    text = "\n".join(b.text for b in book.blocks)
    assert "红黑树" in text and "平衡因子" in text


def test_chunk_blocks_keeps_page_boundaries():
    from app.services.book_parser import TextBlock

    blocks = [
        TextBlock("第一页内容。" * 10, page=1),
        TextBlock("第二页内容。" * 10, page=2),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, overlap=20)
    assert {c.page for c in chunks} == {1, 2}
    assert all(not ("第一页" in c.text and "第二页" in c.text) for c in chunks)


def test_chunk_blocks_preserves_chapter_and_overlap():
    from app.services.book_parser import TextBlock

    blocks = [
        TextBlock("第1章 树", chapter="第1章 树", kind="heading"),
        TextBlock("红黑树是一种自平衡二叉搜索树。" * 30, chapter="第1章 树"),
        TextBlock("第2章 排序", chapter="第2章 排序", kind="heading"),
        TextBlock("快速排序采用分治思想。" * 30, chapter="第2章 排序"),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, overlap=40)
    assert len(chunks) >= 2
    assert all(c.chapter for c in chunks)
    assert {c.chapter for c in chunks} == {"第1章 树", "第2章 排序"}
    assert all(len(c.text) <= 240 for c in chunks)

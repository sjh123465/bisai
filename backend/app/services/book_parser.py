"""电子书解析与切片 — PDF / DOCX / TXT / Markdown / EPUB。

解析统一产出 TextBlock（带章节/页码），再由 chunk_blocks 做结构感知切片：
- 目标 ~500 字，重叠 ~80 字；
- 尽量按段落/句子边界切分，不粗暴截断；
- 保留章节路径与页码，供回答时标注出处；
- 扫描版 PDF（无可提取文字）会给出明确错误，不做 OCR。
"""
from __future__ import annotations

import html.parser
import json
import os
import re
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from xml.etree import ElementTree as ET

SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".txt": "纯文本",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".epub": "EPUB",
}

_CHAPTER_RE = re.compile(
    r"^\s*(第[一二三四五六七八九十百千零〇0-9]+[章节部分篇卷]"
    r"|Chapter\s+\d+"
    r"|\d+(?:\.\d+){0,3}[、.\s]\s*\S)"
    , re.IGNORECASE
)


class BookParseError(Exception):
    """可展示给用户的解析错误。"""


@dataclass
class TextBlock:
    text: str
    chapter: str = ""
    page: int = 0
    kind: str = "text"  # text | heading | code | table


@dataclass
class BookChunk:
    text: str
    chapter: str
    page: int
    index: int
    kind: str = "text"


@dataclass
class ParsedBook:
    title: str
    blocks: list[TextBlock]
    format: str


def normalize_text(text: str) -> str:
    text = str(text or "").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _detect_chapter(text: str) -> str:
    for line in str(text or "").splitlines()[:20]:
        line = line.strip()
        if 0 < len(line) <= 80 and _CHAPTER_RE.match(line):
            return line
    return ""


def _split_paragraphs(text: str) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    parts = re.split(r"\n\s*\n", text)
    if len(parts) > 1:
        return [p.strip() for p in parts if p.strip()]
    # 没有空行时按单行分组，避免整页变成超长块
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out, buf, size = [], [], 0
    for line in lines:
        buf.append(line)
        size += len(line)
        if size >= 180:
            out.append(" ".join(buf))
            buf, size = [], 0
    if buf:
        out.append(" ".join(buf))
    return out


# 单页可提取文字少于该值时视为图片页，auto 模式会触发 OCR
OCR_PAGE_TEXT_THRESHOLD = 20
_OCR_ENGINE = None
_OCR_ENGINE_LOCK = threading.Lock()


def _get_ocr_engine():
    """懒加载 RapidOCR；首次调用会初始化本地 ONNX 模型。"""
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE
    with _OCR_ENGINE_LOCK:
        if _OCR_ENGINE is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except Exception as e:  # pragma: no cover - 依赖缺失时才触发
                raise BookParseError(
                    "扫描版 PDF 需要本地 OCR 组件，请先执行 pip install -r requirements.txt"
                ) from e
            # 限制检测长边 + 关闭方向分类，显著降低扫描书 OCR 耗时；
            # det/rec_model_path 传空是 rapidocr 1.2.x 覆盖参数时的必需占位。
            _OCR_ENGINE = RapidOCR(
                use_angle_cls=False,
                det_model_path="",
                det_limit_side_len=1280,
                det_limit_type="max",
                rec_model_path="",
            )
    return _OCR_ENGINE


def _ocr_result_text(result) -> str:
    """把 RapidOCR 输出按阅读顺序（先上后下、先左后右）拼成文本。"""
    rows = []
    for item in result or []:
        try:
            box, text, score = item[0], item[1], float(item[2])
        except (TypeError, ValueError, IndexError):
            continue
        if not text or score < 0.3:
            continue
        try:
            left = min(float(point[0]) for point in box)
            top = min(float(point[1]) for point in box)
        except (TypeError, ValueError, IndexError):
            continue
        rows.append((top, left, str(text)))
    rows.sort(key=lambda row: (row[0], row[1]))
    return "\n".join(text for _, _, text in rows)


OCR_CACHE_VERSION = 1


def _load_ocr_cache(path: Path, dpi: int) -> dict[int, str]:
    """读取页级 OCR 缓存；版本或 DPI 变化时自动失效。"""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(data.get("version", 0)) != OCR_CACHE_VERSION:
            return {}
        if int(data.get("dpi", 0)) != int(dpi):
            return {}
        pages = data.get("pages") or {}
        return {int(k): str(v) for k, v in pages.items() if str(v).strip()}
    except Exception:
        return {}


def _save_ocr_cache(path: Path, dpi: int, pages: dict[int, str]) -> None:
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": OCR_CACHE_VERSION,
            "dpi": int(dpi),
            "pages": {str(k): v for k, v in sorted(pages.items())},
        }
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass  # 缓存写失败不影响主流程


def _ocr_pdf_pages(
    path: Path,
    page_numbers: list[int],
    dpi: int,
    progress_cb: Callable[[float], None] | None = None,
    cache_path: Path | None = None,
) -> dict[int, str]:
    """渲染指定页并本地 OCR（可复用页级缓存），返回 {页码: 识别文本}。"""
    try:
        import numpy as np
        import pypdfium2 as pdfium
    except Exception as e:  # pragma: no cover - 依赖缺失时才触发
        raise BookParseError(
            "扫描版 PDF 需要本地渲染组件，请先执行 pip install -r requirements.txt"
        ) from e

    wanted = list(dict.fromkeys(int(n) for n in page_numbers))
    texts: dict[int, str] = {}
    if cache_path:
        cached = _load_ocr_cache(Path(cache_path), int(dpi))
        texts.update({n: cached[n] for n in wanted if n in cached})
    pending = [n for n in wanted if n not in texts]
    total = len(wanted)
    done = total - len(pending)

    def report():
        if progress_cb:
            try:
                progress_cb(min(1.0, done / max(total, 1)))
            except Exception:
                pass

    report()
    engine = _get_ocr_engine()
    scale = max(1.0, float(dpi) / 72.0)
    with pdfium.PdfDocument(str(path)) as doc:
        for idx, page_no in enumerate(pending):
            if page_no < 1 or page_no > len(doc):
                continue
            page = doc[page_no - 1]
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil().convert("RGB")
                with _OCR_ENGINE_LOCK:
                    result, _ = engine(np.asarray(image)[:, :, ::-1])
            finally:
                bitmap.close()
            text = normalize_text(_ocr_result_text(result))
            if text:
                texts[page_no] = text
            done += 1
            if cache_path and (idx + 1) % 5 == 0:
                _save_ocr_cache(Path(cache_path), int(dpi), texts)
            report()
    if cache_path:
        _save_ocr_cache(Path(cache_path), int(dpi), texts)
    return {n: texts[n] for n in wanted if n in texts}


def _parse_pdf(
    path: Path,
    fallback_title: str,
    *,
    ocr_mode: str = "auto",
    ocr_dpi: int = 150,
    ocr_max_pages: int = 1000,
    progress_cb: Callable[[float], None] | None = None,
    ocr_cache_path: str | Path | None = None,
) -> ParsedBook:
    try:
        from pypdf import PdfReader
    except Exception as e:  # pragma: no cover - 依赖缺失时才触发
        raise BookParseError(f"PDF 解析库未安装: {e}") from e

    mode = str(ocr_mode or "auto").lower()
    if mode not in ("auto", "off", "force"):
        mode = "auto"

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:
                raise BookParseError("PDF 已加密，无法读取，请移除密码后重试") from e
        title = fallback_title
        meta = reader.metadata or {}
        meta_title = str(meta.get("/Title") or "").strip()
        if meta_title:
            title = meta_title

        page_texts: dict[int, str] = {}
        for page_no, page in enumerate(reader.pages, 1):
            page_texts[page_no] = normalize_text(page.extract_text() or "")
        pages_n = len(page_texts)

        # 扫描版 / 图片页：auto 只补没有文字的页，force 全页重识别
        if mode != "off" and pages_n:
            if mode == "force":
                ocr_pages = list(range(1, pages_n + 1))
            else:
                ocr_pages = [n for n, text in page_texts.items() if len(text) < OCR_PAGE_TEXT_THRESHOLD]
            if ocr_pages:
                limit = max(0, int(ocr_max_pages))
                if limit and len(ocr_pages) > limit:
                    raise BookParseError(
                        f"需要 OCR 的页数（{len(ocr_pages)}）超过 {limit} 页上限，"
                        "请拆分 PDF 后上传，或调大 BOOK_OCR_MAX_PAGES"
                    )
                page_texts.update(_ocr_pdf_pages(
                    path,
                    ocr_pages,
                    int(ocr_dpi),
                    progress_cb,
                    cache_path=Path(ocr_cache_path) if ocr_cache_path else None,
                ))

        blocks: list[TextBlock] = []
        current_chapter = ""
        for page_no in range(1, pages_n + 1):
            text = page_texts.get(page_no, "")
            if not text:
                continue
            detected = _detect_chapter(text)
            if detected:
                current_chapter = detected
            for para in _split_paragraphs(text):
                blocks.append(TextBlock(para, chapter=current_chapter, page=page_no))
    except BookParseError:
        raise
    except Exception as e:
        raise BookParseError(f"PDF 解析失败: {e}") from e

    total = sum(len(b.text) for b in blocks)
    # 扫描版 PDF 常见情况：整本几乎没有文字，或每页只有页眉/页脚几个字
    if total < 10 or (pages_n > 3 and total / pages_n < 5):
        if mode == "off":
            raise BookParseError(
                "PDF 没有可提取的文字（可能是扫描版），可把 BOOK_OCR_MODE 设为 auto 开启本地 OCR"
            )
        raise BookParseError("PDF 没有可提取的文字，本地 OCR 也未能识别（扫描件可能过于模糊）")
    return ParsedBook(title=title, blocks=blocks, format="pdf")


def _iter_docx_blocks(doc):
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _parse_docx(path: Path, fallback_title: str) -> ParsedBook:
    try:
        from docx import Document
    except Exception as e:  # pragma: no cover
        raise BookParseError(f"Word 解析库未安装: {e}") from e

    try:
        doc = Document(str(path))
    except Exception as e:
        raise BookParseError(f"Word 解析失败（仅支持 .docx；旧版 .doc 请先另存为 .docx）: {e}") from e

    title = fallback_title
    try:
        core_title = str(doc.core_properties.title or "").strip()
        if core_title:
            title = core_title
    except Exception:
        pass

    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []

    def current_chapter() -> str:
        return " / ".join(t for _, t in heading_stack)

    for item in _iter_docx_blocks(doc):
        if hasattr(item, "style") and hasattr(item, "text"):
            text = normalize_text(item.text)
            style = str(getattr(item.style, "name", "") or "")
            m = re.match(r"^(Heading|标题)\s*(\d+)$", style, re.IGNORECASE)
            if m:
                level = int(m.group(2))
                heading_stack[:] = [(lv, t) for lv, t in heading_stack if lv < level]
                heading_stack.append((level, text))
                if text:
                    blocks.append(TextBlock(text, chapter=current_chapter(), kind="heading"))
                continue
            if text:
                blocks.append(TextBlock(text, chapter=current_chapter()))
        else:
            # 表格：按行拼接，保留可读结构
            try:
                rows = []
                for row in item.rows:
                    cells = [normalize_text(c.text).replace("\n", " ") for c in row.cells]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    blocks.append(TextBlock("\n".join(rows), chapter=current_chapter(), kind="table"))
            except Exception:
                continue

    if not blocks:
        raise BookParseError("Word 文档没有可提取的文字")
    return ParsedBook(title=title, blocks=blocks, format="docx")


def _read_text_file(path: Path) -> str:
    data = path.read_bytes()
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(data).best()
        if best is not None:
            return str(best)
    except Exception:
        pass
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_markdown(text: str) -> tuple[str, list[TextBlock]]:
    blocks: list[TextBlock] = []
    heading_stack: list[tuple[int, str]] = []
    title = ""
    in_code = False
    code_lines: list[str] = []
    buf: list[str] = []

    def chapter() -> str:
        return " / ".join(t for _, t in heading_stack)

    def flush_para():
        nonlocal buf
        para = normalize_text("\n".join(buf))
        buf = []
        if para:
            blocks.append(TextBlock(para, chapter=chapter()))

    for line in normalize_text(text).splitlines():
        if line.strip().startswith("```"):
            if in_code:
                code = "\n".join(code_lines).strip()
                if code:
                    blocks.append(TextBlock(code, chapter=chapter(), kind="code"))
                code_lines = []
                in_code = False
            else:
                flush_para()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            flush_para()
            level = len(m.group(1))
            heading = m.group(2).strip()
            heading_stack[:] = [(lv, t) for lv, t in heading_stack if lv < level]
            heading_stack.append((level, heading))
            if level == 1 and not title and not _CHAPTER_RE.match(heading):
                title = heading
            blocks.append(TextBlock(heading, chapter=chapter(), kind="heading"))
            continue
        if not line.strip():
            flush_para()
        else:
            buf.append(line)
    flush_para()
    if in_code and code_lines:
        blocks.append(TextBlock("\n".join(code_lines), chapter=chapter(), kind="code"))
    return title, blocks


def _parse_plain_text(text: str) -> tuple[str, list[TextBlock]]:
    blocks: list[TextBlock] = []
    title = ""
    current_chapter = ""
    for para in _split_paragraphs(text):
        detected = _detect_chapter(para)
        if detected:
            current_chapter = detected
        kind = "heading" if detected else "text"
        blocks.append(TextBlock(para, chapter=current_chapter, kind=kind))
    # TXT 的「第X章」通常只是首章标题，书名仍用文件名，避免书架里显示成章节名
    return title, blocks


def _parse_txt(path: Path, fallback_title: str, markdown: bool = False) -> ParsedBook:
    text = _read_text_file(path)
    title, blocks = _parse_markdown(text) if markdown else _parse_plain_text(text)
    if not blocks:
        raise BookParseError("文件没有可提取的文字")
    return ParsedBook(title=title or fallback_title, blocks=blocks, format="md" if markdown else "txt")


class _EPUBHTMLParser(html.parser.HTMLParser):
    """把 XHTML 拆成 (文本, 标题级别) 序列。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, int | None]] = []
        self._buf: list[str] = []
        self._heading: int | None = None
        self._skip = 0

    def _flush(self, heading: int | None = None):
        text = re.sub(r"[ \t]+", " ", "".join(self._buf)).strip()
        self._buf = []
        if text:
            self.blocks.append((text, heading))

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self._heading = int(tag[1])
        elif tag in ("p", "div", "br", "li", "tr", "section", "article"):
            self._flush()
        elif tag == "td":
            self._buf.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush(self._heading)
            self._heading = None
        elif tag in ("p", "div", "li", "tr", "section", "article"):
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush(self._heading)


def _parse_epub(path: Path, fallback_title: str) -> ParsedBook:
    try:
        zf = zipfile.ZipFile(path)
    except Exception as e:
        raise BookParseError(f"EPUB 文件损坏: {e}") from e

    with zf:
        total = sum(info.file_size for info in zf.infolist())
        if total > 200 * 1024 * 1024:
            raise BookParseError("EPUB 解压后体积过大，已拒绝处理")
        try:
            container = zf.read("META-INF/container.xml")
            root = ET.fromstring(container)
            rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            opf_path = rootfile.attrib.get("full-path") if rootfile is not None else None
            if not opf_path:
                raise BookParseError("EPUB 缺少 OPF 清单")
            opf = ET.fromstring(zf.read(opf_path))
        except BookParseError:
            raise
        except Exception as e:
            raise BookParseError(f"EPUB 结构解析失败: {e}") from e

        ns = {"opf": "http://www.idpf.org/2007/opf"}
        title = fallback_title
        try:
            title_el = opf.find(".//opf:metadata/{http://purl.org/dc/elements/1.1/}title", ns)
            if title_el is not None and title_el.text:
                title = title_el.text.strip() or title
        except Exception:
            pass

        manifest = {}
        try:
            for item in opf.findall(".//opf:manifest/opf:item", ns):
                manifest[item.attrib.get("id", "")] = (item.attrib.get("href", ""), item.attrib.get("media-type", ""))
            spine = [ref.attrib.get("idref", "") for ref in opf.findall(".//opf:spine/opf:itemref", ns)]
        except Exception as e:
            raise BookParseError(f"EPUB 清单解析失败: {e}") from e

        base = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
        blocks: list[TextBlock] = []
        current_chapter = ""
        for idref in spine:
            href, media_type = manifest.get(idref, ("", ""))
            if not href or ("html" not in media_type and not href.lower().endswith((".xhtml", ".html", ".htm"))):
                continue
            chapter_path = f"{base}/{href}" if base else href
            chapter_path = os.path.normpath(chapter_path).replace("\\", "/")
            try:
                raw = zf.read(chapter_path).decode("utf-8", errors="replace")
            except KeyError:
                continue
            parser = _EPUBHTMLParser()
            parser.feed(raw)
            parser.close()
            for text, heading in parser.blocks:
                text = normalize_text(text)
                if not text:
                    continue
                if heading:
                    current_chapter = text
                blocks.append(TextBlock(text, chapter=current_chapter, kind="heading" if heading else "text"))
        if not blocks:
            raise BookParseError("EPUB 没有可提取的文字（可能受 DRM 保护）")
        return ParsedBook(title=title, blocks=blocks, format="epub")


def parse_book(
    path: str | Path,
    ext: str,
    fallback_title: str = "",
    *,
    ocr_mode: str = "auto",
    ocr_dpi: int = 150,
    ocr_max_pages: int = 1000,
    progress_cb: Callable[[float], None] | None = None,
    ocr_cache_path: str | Path | None = None,
) -> ParsedBook:
    """按扩展名解析电子书；支持格式由 SUPPORTED_EXTENSIONS 定义。

    PDF 的 ocr_mode：auto 只识别缺少文字的页，off 关闭，force 全页 OCR。
    ocr_cache_path 指向页级 OCR 缓存，重建索引时可跳过已识别页。
    """
    path = Path(path)
    ext = ext.lower()
    if not ext.startswith("."):
        ext = "." + ext
    if ext not in SUPPORTED_EXTENSIONS:
        raise BookParseError(f"暂不支持 {ext} 格式，支持: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    fallback_title = fallback_title or path.stem
    if ext == ".pdf":
        return _parse_pdf(
            path,
            fallback_title,
            ocr_mode=ocr_mode,
            ocr_dpi=ocr_dpi,
            ocr_max_pages=ocr_max_pages,
            progress_cb=progress_cb,
            ocr_cache_path=ocr_cache_path,
        )
    if ext == ".docx":
        return _parse_docx(path, fallback_title)
    if ext == ".txt":
        return _parse_txt(path, fallback_title)
    if ext in (".md", ".markdown"):
        return _parse_txt(path, fallback_title, markdown=True)
    if ext == ".epub":
        return _parse_epub(path, fallback_title)
    raise BookParseError(f"暂不支持 {ext} 格式")  # pragma: no cover


def _split_long(text: str, max_len: int) -> Iterable[str]:
    """按句子边界把超长段落切成 <= max_len 的片段。"""
    text = text.strip()
    if len(text) <= max_len:
        yield text
        return
    sentences = re.split(r"(?<=[。！？；.!?;])\s*", text)
    buf = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(sentence) > max_len:
            if buf:
                yield buf
                buf = ""
            for i in range(0, len(sentence), max_len):
                yield sentence[i:i + max_len]
            continue
        if len(buf) + len(sentence) > max_len and buf:
            yield buf
            buf = ""
        buf += sentence
    if buf:
        yield buf


def chunk_blocks(
    blocks: list[TextBlock],
    chunk_size: int = 500,
    overlap: int = 80,
    max_chunks: int = 5000,
) -> list[BookChunk]:
    if chunk_size < 100:
        chunk_size = 100
    overlap = max(0, min(overlap, chunk_size // 2))

    chunks: list[BookChunk] = []
    buf: list[str] = []
    buf_len = 0
    meta = {"chapter": "", "page": 0, "kind": "text"}

    def flush():
        nonlocal buf, buf_len
        text = normalize_text("\n".join(buf))
        if text:
            chunks.append(BookChunk(
                text=text,
                chapter=meta["chapter"],
                page=meta["page"],
                index=len(chunks),
                kind=meta["kind"],
            ))
        buf, buf_len = [], 0

    for block in blocks:
        text = normalize_text(block.text)
        if not text:
            continue
        if block.kind == "heading":
            flush()
            buf = [text]
            buf_len = len(text)
            meta = {"chapter": block.chapter or text, "page": block.page, "kind": "text"}
            continue

        if block.page and meta["page"] and block.page != meta["page"]:
            flush()  # 不跨页合并，保证检索结果的页码准确
        if block.chapter and meta["chapter"] and block.chapter != meta["chapter"] and buf_len >= chunk_size // 2:
            flush()
        if not buf:
            meta = {"chapter": block.chapter or meta["chapter"], "page": block.page or meta["page"], "kind": block.kind}

        for piece in _split_long(text, chunk_size):
            if not piece:
                continue
            if buf_len + len(piece) + 1 > chunk_size and buf:
                flush()
                if overlap and chunks:
                    tail = chunks[-1].text[-overlap:]
                    m = re.search(r"[。！？；.!?;\n]", tail)
                    if m and m.end() < len(tail) - 10:
                        tail = tail[m.end():].lstrip()
                    if tail:
                        buf = [tail]
                        buf_len = len(tail)
                meta = {"chapter": block.chapter or meta["chapter"], "page": block.page or meta["page"], "kind": block.kind}
            if not buf:
                meta = {"chapter": block.chapter or meta["chapter"], "page": block.page or meta["page"], "kind": block.kind}
            buf.append(piece)
            buf_len += len(piece) + 1
        if len(chunks) >= max_chunks:
            raise BookParseError(f"书籍切片超过 {max_chunks} 片，请拆分后上传")

    flush()
    if len(chunks) > max_chunks:
        raise BookParseError(f"书籍切片超过 {max_chunks} 片，请拆分后上传")
    # 过滤过短的尾片/碎片（保留唯一内容）
    useful = [c for c in chunks if len(c.text) >= 20]
    if not useful and chunks:
        useful = chunks
    for i, c in enumerate(useful):
        c.index = i
    return useful

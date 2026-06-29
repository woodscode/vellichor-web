"""Turn an input (uploaded file or pasted text) into a list of chapters.

Each chapter is a dict: {"title": str, "text": str}.
Supported: .txt, .md, .epub, .pdf, .docx, and raw text from the editor.
"""
import os
import re


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # collapse runs of blank lines, strip trailing spaces
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_markdown(text: str, default_title: str):
    """Split on markdown H1/H2 headings into chapters; otherwise one chapter."""
    lines = text.split("\n")
    chapters = []
    cur_title, cur_lines = None, []

    def flush():
        body = _clean("\n".join(cur_lines))
        if body:
            chapters.append({"title": cur_title or default_title, "text": body})

    for ln in lines:
        m = re.match(r"^#{1,2}\s+(.*)$", ln.strip())
        if m:
            flush()
            cur_title, cur_lines = m.group(1).strip(), []
        else:
            cur_lines.append(ln)
    flush()
    if not chapters:
        chapters = [{"title": default_title, "text": _clean(text)}]
    return chapters


def from_text(text: str, title: str = "Story"):
    return _split_markdown(text, title)


def from_txt(path: str):
    title = os.path.splitext(os.path.basename(path))[0]
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return _split_markdown(f.read(), title)


def from_pdf(path: str):
    from pypdf import PdfReader
    reader = PdfReader(path)
    title = (reader.metadata.title if reader.metadata else None) or \
        os.path.splitext(os.path.basename(path))[0]
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    text = _clean("\n\n".join(parts))
    return [{"title": title, "text": text}] if text else []


def from_docx(path: str):
    import docx
    doc = docx.Document(path)
    title = os.path.splitext(os.path.basename(path))[0]
    chapters = []
    cur_title, cur_lines = None, []

    def flush():
        body = _clean("\n".join(cur_lines))
        if body:
            chapters.append({"title": cur_title or title, "text": body})

    for p in doc.paragraphs:
        style = (p.style.name or "").lower() if p.style else ""
        if style.startswith("heading 1") or style.startswith("title"):
            flush()
            cur_title, cur_lines = p.text.strip(), []
        else:
            cur_lines.append(p.text)
    flush()
    return chapters or [{"title": title, "text": _clean("\n".join(p.text for p in doc.paragraphs))}]


def from_epub(path: str):
    from ebooklib import epub, ITEM_DOCUMENT
    from bs4 import BeautifulSoup
    book = epub.read_epub(path)
    title = (book.get_metadata("DC", "title") or [["Audiobook"]])[0][0]
    chapters = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        # chapter title from first heading, else the doc file name
        heading = soup.find(["h1", "h2", "h3"])
        ch_title = heading.get_text(strip=True) if heading else None
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = _clean(soup.get_text("\n"))
        if len(text) < 20:  # skip covers, nav, empty pages
            continue
        if not ch_title:
            ch_title = f"Chapter {len(chapters) + 1}"
        chapters.append({"title": ch_title, "text": text})
    return chapters, title


EXT_HANDLERS = {
    ".txt": from_txt, ".md": from_txt, ".markdown": from_txt,
    ".pdf": from_pdf, ".docx": from_docx,
}
SUPPORTED_EXTS = set(EXT_HANDLERS) | {".epub"}


def extract(path: str):
    """Returns (chapters, book_title)."""
    ext = os.path.splitext(path)[1].lower()
    base = os.path.splitext(os.path.basename(path))[0]
    if ext == ".epub":
        return from_epub(path)
    handler = EXT_HANDLERS.get(ext)
    if not handler:
        raise ValueError(f"Unsupported file type: {ext}")
    return handler(path), base

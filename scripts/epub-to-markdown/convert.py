#!/usr/bin/env python3
"""
EPUB to Markdown Converter

Converts EPUB files to a folder of Markdown files organized by chapters.

Usage:
    python convert.py <input.epub> [output_dir]

Output structure:
    output_dir/
    ├── SUMMARY.md
    ├── images/
    │   ├── img_001.png
    │   └── img_002.jpg
    ├── 01_封面.md
    ├── 02_前言.md
    ├── 03_第一章.md
    └── ...
"""

import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

import warnings
from bs4 import XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Tag
import markdownify


def slugify(text, max_length=60):
    text = unicodedata.normalize("NFKC", str(text))
    text = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", text)
    text = re.sub(r"[\s]+", "_", text)
    text = re.sub(r"_+", "_", text)
    text = text.strip("._ ")
    return text[:max_length] if len(text) > max_length else text


def format_filename(index, title):
    num = f"{index:02d}"
    safe = slugify(title)
    return f"{num}_{safe}.md" if safe else f"{num}.md"


class EpubConverter:
    def __init__(self, epub_path, output_dir=None):
        self.epub_path = Path(epub_path).resolve()
        if not self.epub_path.exists():
            raise FileNotFoundError(f"EPUB not found: {epub_path}")

        print(f"Reading: {self.epub_path.name}")
        self.book = epub.read_epub(str(self.epub_path), options={"ignore_ncx": False})

        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            self.output_dir = Path.cwd() / "epub-output" / self.epub_path.stem

        self.image_dir = self.output_dir / "images"
        self.image_map = {}
        self.chapters = []

    def convert(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)

        self._extract_images()
        self._build_chapters()
        self._write_chapters()
        self._generate_summary()

        print(f"\nDone! {len(self.chapters)} chapters, {len(self.image_map)} images")
        print(f"Output: {self.output_dir}")

    # ── Images ──────────────────────────────────────────────

    def _extract_images(self):
        count = 0
        for item in self.book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                href = item.get_name()
                content = item.get_content()
                ext = self._image_ext(item.media_type, href)
                count += 1
                local_name = f"img_{count:03d}{ext}"

                (self.image_dir / local_name).write_bytes(content)

                rel = f"images/{local_name}"
                self.image_map[href] = rel
                bare = Path(href).name
                if bare not in self.image_map:
                    self.image_map[bare] = rel
                decoded = unquote(bare)
                if decoded not in self.image_map:
                    self.image_map[decoded] = rel

        print(f"  Images: {count}")

    @staticmethod
    def _image_ext(media_type, href):
        ext_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/svg+xml": ".svg",
            "image/webp": ".webp",
        }
        if media_type in ext_map:
            return ext_map[media_type]
        ext = Path(href).suffix.lower()
        return (
            ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp") else ".png"
        )

    # ── TOC Parsing ─────────────────────────────────────────

    def _flatten_toc(self):
        result = []

        def _walk(entries, depth=0):
            for entry in entries:
                title, href = None, None

                if isinstance(entry, (tuple, list)):
                    if len(entry) >= 2:
                        t, h = entry[0], entry[1]
                        title = t if isinstance(t, str) else getattr(t, "title", None)
                        href = h if isinstance(h, str) else getattr(h, "href", None)
                    if len(entry) >= 3 and isinstance(entry[2], (list, tuple)):
                        _walk(entry[2], depth + 1)
                else:
                    title = getattr(entry, "title", None)
                    href = getattr(entry, "href", None)
                    children = getattr(entry, "children", [])
                    if children:
                        _walk(children, depth + 1)

                if title and href:
                    result.append((title, href, depth))

        try:
            _walk(self.book.toc)
        except Exception as e:
            print(f"  Warning: TOC parse error: {e}")

        return result

    def _build_toc_map(self):
        toc_map = {}
        for title, href, depth in self._flatten_toc():
            base = href.split("#")[0]
            toc_map.setdefault(base, title)
            toc_map[href] = title
        return toc_map

    # ── Chapter Building ────────────────────────────────────

    def _build_chapters(self):
        toc_map = self._build_toc_map()
        toc_flat = self._flatten_toc()

        spine_items = []
        for item in self.book.spine:
            if isinstance(item, tuple):
                spine_items.append(item[0])
            else:
                spine_items.append(item)

        # Resolve spine idrefs to EpubHtml objects
        resolved = []
        for ref in spine_items:
            if isinstance(ref, epub.EpubHtml):
                resolved.append(ref)
            elif isinstance(ref, str):
                obj = self.book.get_item_with_id(ref)
                if obj and isinstance(obj, epub.EpubHtml):
                    resolved.append(obj)

        html_items = (
            resolved
            if resolved
            else list(self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
        )
        if not html_items:
            html_items = list(self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

        if not html_items:
            print("  Error: No HTML items found in EPUB")
            return

        # Group TOC entries by file to detect multi-chapter files
        file_toc = {}
        for title, href, depth in toc_flat:
            base = href.split("#")[0]
            anchor = href.split("#")[1] if "#" in href else None
            file_toc.setdefault(base, []).append((title, anchor, depth))

        idx = 0
        seen = set()
        last_title = None  # Track last heading for continuation pages

        for item in html_items:
            href = item.get_name()
            if href in seen:
                continue
            seen.add(href)

            try:
                raw = item.get_content().decode("utf-8", errors="replace")
            except Exception:
                continue

            if not raw.strip():
                continue

            entries = file_toc.get(href, [])

            if entries and len(entries) > 1:
                idx = self._split_chapter(idx, raw, entries, toc_map.get(href, None))
            elif entries and len(entries) == 1:
                last_title = entries[0][0]
                idx = self._add_chapter(idx, entries[0][0], raw)
            else:
                toc_title = toc_map.get(href)
                html_title = self._html_title(raw)
                if html_title:
                    last_title = html_title
                title = toc_title or html_title or last_title
                if not title:
                    title = f"章节 {idx + 1}"
                idx = self._add_chapter(idx, title, raw)

        if not self.chapters:
            self._fallback_split()

    def _add_chapter(self, idx, title, html):
        md = self._to_markdown(html)
        if not md.strip():
            return idx
        text_only = re.sub(r"!\[.*?\]\(.*?\)", "", md)
        text_only = re.sub(r"#+\s*", "", text_only)
        text_only = re.sub(r"[\s#\-_*\n\r]", "", text_only)
        if len(text_only) < 50:
            return idx
        self.chapters.append((title, md))
        return idx + 1

    def _split_chapter(self, idx, html, entries, default_title):
        soup = BeautifulSoup(html, "lxml")
        body = soup.body if soup.body else soup

        anchor_map = {}
        for title, anchor, depth in entries:
            if anchor:
                elem = body.find(id=anchor) or body.find(attrs={"name": anchor})
                if elem:
                    anchor_map[id(elem)] = (title, anchor)

        if not anchor_map:
            title = default_title or entries[0][0] or f"章节 {idx + 1}"
            return self._add_chapter(idx, title, html)

        sections = []
        current_title = entries[0][0] if entries else default_title
        current_parts = []

        def flush():
            if current_parts:
                html_str = "".join(str(p) for p in current_parts)
                if html_str.strip():
                    sections.append((current_title, html_str))

        for child in list(body.children):
            if isinstance(child, Tag) and id(child) in anchor_map:
                flush()
                current_title = anchor_map[id(child)][0]
                current_parts = [child]
            else:
                current_parts.append(child)

        flush()

        for title, section_html in sections:
            idx = self._add_chapter(
                idx, title, f"<html><body>{section_html}</body></html>"
            )

        return idx

    def _fallback_split(self):
        print("  Warning: Fallback heading-based split")
        all_html = []
        for item in self.book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            try:
                all_html.append(item.get_content().decode("utf-8", errors="replace"))
            except Exception:
                pass

        if not all_html:
            return

        soup = BeautifulSoup("\n".join(all_html), "lxml")
        body = soup.body if soup.body else soup

        idx = len(self.chapters)
        title = "开始"
        parts = []

        def flush():
            nonlocal idx
            if parts:
                md = self._to_markdown(
                    "<html><body>" + "".join(str(p) for p in parts) + "</body></html>"
                )
                if md.strip():
                    self.chapters.append((title, md))
                    idx += 1

        for child in list(body.children):
            if isinstance(child, Tag) and child.name in ("h1", "h2"):
                flush()
                title = child.get_text(strip=True) or f"章节 {idx + 1}"
                parts = [child]
            else:
                parts.append(child)

        flush()

    # ── HTML → Markdown ─────────────────────────────────────

    def _to_markdown(self, html):
        soup = BeautifulSoup(html, "lxml")

        for tag in soup.find_all(["script", "style", "link", "meta"]):
            tag.decompose()

        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                local = self._resolve_image(src)
                if local:
                    img["src"] = local
                    alt = img.get("alt", "").strip()
                    if not alt:
                        img["alt"] = Path(src).stem

        md = markdownify.markdownify(
            str(soup),
            heading_style="ATX",
            bullets="-",
            strong_em_symbol="**",
            autolinks=True,
            default_title=True,
            escape_asterisks=False,
            escape_misc=False,
            convert=[
                "p",
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "ul",
                "ol",
                "li",
                "table",
                "thead",
                "tbody",
                "tfoot",
                "tr",
                "td",
                "th",
                "img",
                "a",
                "blockquote",
                "pre",
                "code",
                "em",
                "strong",
                "b",
                "i",
                "br",
                "hr",
                "dl",
                "dt",
                "dd",
                "sup",
                "sub",
                "figure",
                "figcaption",
                "span",
                "div",
                "abbr",
                "cite",
                "mark",
                "del",
                "ins",
            ],
        )

        return self._clean_md(md)

    def _resolve_image(self, src):
        decoded = unquote(src)
        candidates = [decoded, src, Path(decoded).name, Path(src).name]
        for c in list(candidates):
            parts = c.split("/")
            if len(parts) > 1:
                candidates.append(parts[-1])
        for c in candidates:
            if c in self.image_map:
                return self.image_map[c]
        return None

    @staticmethod
    def _clean_md(md):
        md = re.sub(r"\n{4,}", "\n\n\n", md)
        lines = md.split("\n")
        lines = [l.rstrip() for l in lines]
        md = "\n".join(lines)
        md = md.strip() + "\n"
        return md

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _html_title(html):
        soup = BeautifulSoup(html, "lxml")
        # Priority: h1/h2/h3 content > h1/h2/h3 title attribute > <title> tag
        for lvl in range(1, 4):
            for h in soup.find_all(f"h{lvl}"):
                text = h.get_text(strip=True)
                if text:
                    return text
                # Hidden headings may have title attribute
                title_attr = h.get("title", "").strip()
                if title_attr:
                    return title_attr
        t = soup.find("title")
        if t and t.string and t.string.strip():
            return t.string.strip()
        return None

    # ── Output ───────────────────────────────────────────────

    def _write_chapters(self):
        for i, (title, md) in enumerate(self.chapters, 1):
            path = self.output_dir / format_filename(i, title)
            path.write_text(md, encoding="utf-8")
        print(f"  Chapters: {len(self.chapters)}")

    def _generate_summary(self):
        lines = []

        titles = self.book.get_metadata("DC", "title")
        book_title = titles[0][0] if titles else self.epub_path.stem
        lines.append(f"# {book_title}\n")

        authors = self.book.get_metadata("DC", "author")
        if authors:
            lines.append(f"\n**作者：** {authors[0][0]}\n")

        lines.append("\n---\n\n")
        lines.append("## 目录\n\n")

        for i, (title, _) in enumerate(self.chapters, 1):
            fname = format_filename(i, title)
            lines.append(f"{i}. [{title}]({fname})\n")

        (self.output_dir / "SUMMARY.md").write_text("".join(lines), encoding="utf-8")
        print("  Summary: SUMMARY.md")


def main():
    if len(sys.argv) < 2:
        print("Usage: python convert.py <input.epub> [output_dir]")
        sys.exit(1)

    epub_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    converter = EpubConverter(epub_path, output_dir)
    converter.convert()


if __name__ == "__main__":
    main()

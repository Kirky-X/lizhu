#!/usr/bin/env python3
"""
markitdown-convert — markitdown 包装脚本（lizhu 主转换引擎）

基于 Microsoft markitdown，统一把多种文档格式转为 Markdown。
可选接 md-normalizer/semantic_normalize.py 做语义格式优化。

支持输入：PDF / Word / PowerPoint / Excel / HTML / CSV / JSON / XML /
YAML / ZIP / EPUB / 图片 / 音频 / YouTube URL 等（视已安装的可选依赖而定）。

统一管线：
    input → markitdown.convert() → [optional] semantic_normalize → output

Usage:
    python3 main.py <input> [--output OUT.md] [--normalize]
                            [--llm-model MODEL] [--llm-base-url URL]
                            [--llm-prompt PROMPT]
    python3 main.py --list-formats
    python3 main.py --help

Exit codes:
    0 = success
    1 = input file not found / is directory
    2 = conversion error (unsupported ext, deps missing, markitdown raise, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ----------------------------------------------------------------------------
# Path setup: make sibling md-normalizer importable for optional normalize step
# ----------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_LIZHU_SCRIPTS_DIR = _THIS_DIR.parent
_MD_NORMALIZER_DIR = _LIZHU_SCRIPTS_DIR / "md-normalizer"
if str(_MD_NORMALIZER_DIR) not in sys.path:
    sys.path.insert(0, str(_MD_NORMALIZER_DIR))

# ----------------------------------------------------------------------------
# Imports with explicit failure (Rule 12: 显性化错误)
# ----------------------------------------------------------------------------

try:
    from markitdown import MarkItDown
except ImportError as _e:  # pragma: no cover - env guard
    print(
        f"[Error] markitdown not installed. Run: pip install 'markitdown[all]'\n"
        f"  detail: {_e}",
        file=sys.stderr,
    )
    sys.exit(2)

try:
    from openai import OpenAI
    _HAS_OPENAI = True
except ImportError:
    OpenAI = None  # type: ignore[assignment]
    _HAS_OPENAI = False

try:
    from semantic_normalize import Stats as _NormStats
    from semantic_normalize import semantic_normalize as _semantic_normalize
    _HAS_NORMALIZER = True
except ImportError:  # pragma: no cover - md-normalizer missing
    _HAS_NORMALIZER = False

# ----------------------------------------------------------------------------
# Configuration (no hardcoded magic in logic; thresholds centralized here)
# ----------------------------------------------------------------------------

DEFAULT_OUTPUT_ENCODING = "utf-8"

# Built-in formats (no extra deps) + optional-deps formats (need pip extras).
# Kept as a set for O(1) lookup; URLs handled separately via URL_RE.
SUPPORTED_INPUT_EXTS: frozenset[str] = frozenset({
    # Built-in
    ".md", ".markdown", ".txt",
    ".html", ".htm",
    ".csv", ".json", ".jsonl", ".xml", ".yaml", ".yml",
    ".zip",
    ".epub",
    # Image (basic EXIF; LLM description optional)
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg",
    # Audio (basic metadata; transcription optional via [audio-transcription])
    ".mp3", ".wav", ".m4a",
    # Optional-deps formats
    ".pdf",       # [pdf]
    ".docx",      # [docx]
    ".pptx",      # [pptx]
    ".xlsx",      # [xlsx]
    ".xls",       # [xls]
    ".msg",       # [outlook]
})

MAX_FILE_SIZE_MB = 500  # match epub threshold in SKILL.md

URL_RE = re.compile(r"^https?://", re.IGNORECASE)


# ----------------------------------------------------------------------------
# Exceptions
# ----------------------------------------------------------------------------


class ConvertError(Exception):
    """Raised when markitdown conversion fails (deps, unsupported, etc.)."""


# ----------------------------------------------------------------------------
# Result dataclass
# ----------------------------------------------------------------------------


@dataclass
class ConvertResult:
    """Structured result of a single conversion call."""

    input_path: str
    output_path: Optional[str]
    markdown: str
    title: Optional[str]
    source_format: str
    normalize_stats: Optional[dict] = None
    warnings: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def detect_source_format(path: Path) -> str:
    ext = path.suffix.lower()
    return ext.lstrip(".") or "unknown"


def is_url_input(source: str) -> bool:
    return bool(URL_RE.match(source.strip()))


def build_llm_client(
    llm_model: Optional[str],
    llm_base_url: Optional[str],
) -> tuple[Optional[Any], Optional[str]]:
    """Build an OpenAI-compatible LLM client for image descriptions.

    Returns (client_or_None, model_or_None). Raises ConvertError on misconfig.
    """
    model = llm_model or os.environ.get("MARKITDOWN_LLM_MODEL")
    if not model:
        return None, None
    if not _HAS_OPENAI:
        raise ConvertError(
            "--llm-model given but openai package not installed. Run: pip install openai"
        )
    api_key = (
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("MARKITDOWN_LLM_API_KEY")
    )
    if not api_key:
        raise ConvertError(
            "--llm-model given but OPENAI_API_KEY (or MARKITDOWN_LLM_API_KEY) not set"
        )
    base_url = llm_base_url or os.environ.get("MARKITDOWN_LLM_BASE_URL")
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    return client, model


# ----------------------------------------------------------------------------
# Core API
# ----------------------------------------------------------------------------


def convert_to_markdown(
    input_source: str | Path,
    output_path: Optional[str | Path] = None,
    normalize: bool = False,
    llm_client: Optional[Any] = None,
    llm_model: Optional[str] = None,
    llm_prompt: Optional[str] = None,
) -> ConvertResult:
    """Convert any supported source (file path or URL) to Markdown.

    Pipeline: input → MarkItDown.convert() → [optional] semantic_normalize → output.

    Raises:
        FileNotFoundError: input file does not exist.
        ConvertError: unsupported ext, file too large, markitdown failure.
    """
    source_str = str(input_source).strip()

    # URL path -------------------------------------------------------------
    if is_url_input(source_str):
        source_path: Optional[Path] = None
        source_format = "url"
    else:
        path = Path(source_str).resolve()
        if not path.exists():
            raise FileNotFoundError(f"input file not found: {path}")
        if path.is_dir():
            raise ConvertError(f"input is a directory, expected a file: {path}")
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise ConvertError(
                f"file too large: {size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB threshold"
            )
        ext = path.suffix.lower()
        if ext not in SUPPORTED_INPUT_EXTS:
            raise ConvertError(
                f"unsupported extension: {ext}. supported: {sorted(SUPPORTED_INPUT_EXTS)}"
            )
        source_path = path
        source_format = detect_source_format(path)
        source_str = str(path)

    # Build MarkItDown instance -------------------------------------------
    kwargs: dict[str, Any] = {"enable_plugins": False}
    if llm_client is not None and llm_model:
        kwargs["llm_client"] = llm_client
        kwargs["llm_model"] = llm_model
        if llm_prompt:
            kwargs["llm_prompt"] = llm_prompt

    try:
        md = MarkItDown(**kwargs)
        result = md.convert(source_str)
    except Exception as e:  # noqa: BLE001 - re-wrap with context
        raise ConvertError(
            f"markitdown.convert() failed for {source_str}: {type(e).__name__}: {e}"
        ) from e

    markdown_text = result.text_content or ""
    title = getattr(result, "title", None)

    warnings: list[str] = []
    normalize_stats: Optional[dict] = None

    if normalize:
        if not _HAS_NORMALIZER:
            warnings.append(
                "normalize=True but semantic_normalize module not found; "
                "skipping normalize step"
            )
        else:
            stats = _NormStats()
            markdown_text = _semantic_normalize(markdown_text, stats)
            normalize_stats = {
                "paragraph_joins": stats.joins,
                "fence_repairs": stats.fence_repairs,
                "table_repairs": stats.table_repairs,
            }

    out_path: Optional[str] = None
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown_text, encoding=DEFAULT_OUTPUT_ENCODING)
        out_path = str(out)

    return ConvertResult(
        input_path=source_str if source_path is None else str(source_path),
        output_path=out_path,
        markdown=markdown_text,
        title=title,
        source_format=source_format,
        normalize_stats=normalize_stats,
        warnings=warnings,
    )


# ----------------------------------------------------------------------------
# CLI helpers
# ----------------------------------------------------------------------------


def list_formats() -> None:
    """Print supported input formats grouped by dependency availability."""
    print("markitdown 支持的输入格式（按依赖可用性分组）:")
    print()
    print("【内置格式（无需额外依赖）】")
    print("  Markdown: .md .markdown .txt")
    print("  HTML:     .html .htm")
    print("  数据:     .csv .json .jsonl .xml .yaml .yml")
    print("  归档:     .zip（递归转换内部文件）")
    print("  EPUB:     .epub")
    print("  图片:     .jpg .jpeg .png .gif .bmp .tiff .webp .svg")
    print("           （EXIF + 可选 LLM 描述，需 --llm-model）")
    print("  音频:     .mp3 .wav .m4a")
    print("           （元数据；转写需 pip install 'markitdown[audio-transcription]'）")
    print()
    print("【可选依赖格式】")
    print("  PDF:     .pdf            [pdf]")
    print("  Word:    .docx           [docx]")
    print("  PPT:     .pptx           [pptx]")
    print("  Excel:   .xlsx .xls      [xlsx] [xls]")
    print("  Outlook: .msg            [outlook]")
    print()
    print("【远程来源】")
    print("  YouTube: https://www.youtube.com/watch?v=...   [youtube-transcription]")
    print("  HTTP URL: 任意 http(s):// 链接（markitdown 自行抓取）")
    print()
    print("【当前环境检测】")
    print(f"  markitdown:         installed")
    print(f"  openai (LLM 描述):  {'installed' if _HAS_OPENAI else 'not installed'}")
    print(
        f"  semantic_normalize: "
        f"{'available' if _HAS_NORMALIZER else 'NOT available (md-normalizer 缺失)'}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="markitdown-convert",
        description="markitdown 包装脚本——lizhu 主转换引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="输入文件路径或 URL")
    parser.add_argument(
        "-o", "--output",
        help="输出 Markdown 路径（不指定则输出到 stdout）",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="调用 md-normalizer 做语义格式优化（段落合并/fence/表格）",
    )
    parser.add_argument(
        "--llm-model",
        help="LLM 模型名（用于图片描述，如 gpt-4o / DeepSeek-OCR-2 等 OpenAI 兼容模型）",
    )
    parser.add_argument(
        "--llm-base-url",
        help="LLM API base URL（OpenAI 兼容端点）",
    )
    parser.add_argument(
        "--llm-prompt",
        help="自定义 LLM 图片描述 prompt",
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="列出支持的输入格式并退出",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果元信息（markdown 不打印到 stdout）",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_formats:
        list_formats()
        return 0

    if not args.input:
        parser.error("input is required (or use --list-formats)")

    # Build LLM client if requested --------------------------------------
    llm_client: Optional[Any] = None
    llm_model: Optional[str] = None
    if args.llm_model:
        try:
            llm_client, llm_model = build_llm_client(args.llm_model, args.llm_base_url)
        except ConvertError as e:
            print(f"[Error] {e}", file=sys.stderr)
            return 2

    # Convert -------------------------------------------------------------
    try:
        result = convert_to_markdown(
            args.input,
            output_path=args.output,
            normalize=args.normalize,
            llm_client=llm_client,
            llm_model=llm_model,
            llm_prompt=args.llm_prompt,
        )
    except FileNotFoundError as e:
        print(f"[Error] {e}", file=sys.stderr)
        return 1
    except ConvertError as e:
        print(f"[Error] {e}", file=sys.stderr)
        return 2

    # Warnings (stderr) ---------------------------------------------------
    for w in result.warnings:
        print(f"[Warn] {w}", file=sys.stderr)

    if args.json:
        meta = {
            "input_path": result.input_path,
            "output_path": result.output_path,
            "title": result.title,
            "source_format": result.source_format,
            "normalize_stats": result.normalize_stats,
            "warnings": result.warnings,
            "markdown_length": len(result.markdown),
        }
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        if not args.output:
            sys.stdout.write(result.markdown)
            if not result.markdown.endswith("\n"):
                sys.stdout.write("\n")
        # Stats to stderr so stdout stays clean for markdown
        print(
            f"[Info] source_format={result.source_format} "
            f"title={result.title or 'N/A'} chars={len(result.markdown)}",
            file=sys.stderr,
        )
        if result.normalize_stats:
            s = result.normalize_stats
            print(
                f"[Info] normalize: paragraph_joins={s['paragraph_joins']} "
                f"fence_repairs={s['fence_repairs']} "
                f"table_repairs={s['table_repairs']}",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

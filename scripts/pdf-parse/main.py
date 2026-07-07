#!/usr/bin/env python3
"""
PDF Parse Skill - 智能PDF解析脚本

根据文档复杂度自动选择最优解析方案：
- 轻量模式：PyMuPDF 快速提取（文本+图片+超链接）
- MinerU轻量API：表格识别，无公式
- MinerU精准API：公式+表格+OCR，论文级解析
"""

import argparse
import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Optional, Dict, Any, List

# PyMuPDF for lightweight extraction (fitz)
try:
    import fitz  # PyMuPDF
except ImportError:
    print("[Error] PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

# requests for API calls
try:
    import requests
except ImportError:
    print("[Error] requests not installed. Run: pip install requests")
    sys.exit(1)


# ============================================================================
# Configuration
# ============================================================================

MINERU_API_URL = os.environ.get("MINERU_API_URL", "https://mineru.net/api/v4")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
DEFAULT_LANGUAGE = os.environ.get("MINERU_LANGUAGE", "zh")

# File limits
MAX_FILE_SIZE_MB = 200
MAX_PAGES = 600

# Formula detection patterns
FORMULA_PATTERNS = [
    r"\\frac",
    r"\\sum",
    r"\\int",
    r"\\sqrt",
    r"\\partial",
    r"\\alpha",
    r"\\beta",
    r"\\gamma",
    r"\\delta",
    r"\\begin{equation",
    r"\\begin{align",
]


# ============================================================================
# Utility Functions
# ============================================================================


def get_file_size_mb(filepath: str) -> float:
    """Get file size in MB."""
    return os.path.getsize(filepath) / (1024 * 1024)


def get_pdf_page_count(filepath: str) -> int:
    """Get PDF page count using PyMuPDF."""
    doc = fitz.open(filepath)
    count = len(doc)
    doc.close()
    return count


def validate_file(filepath: str) -> Dict[str, Any]:
    """Validate input file."""
    result = {"valid": True, "errors": [], "warnings": []}

    # Check file exists
    if not os.path.exists(filepath):
        result["valid"] = False
        result["errors"].append(f"File not found: {filepath}")
        return result

    # Check file extension
    ext = Path(filepath).suffix.lower()
    supported = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".pptx", ".xlsx"]
    if ext not in supported:
        result["valid"] = False
        result["errors"].append(f"Unsupported format: {ext}. Supported: {supported}")
        return result

    # Check file size
    size_mb = get_file_size_mb(filepath)
    if size_mb > MAX_FILE_SIZE_MB:
        result["warnings"].append(
            f"File size {size_mb:.1f}MB exceeds limit {MAX_FILE_SIZE_MB}MB"
        )

    # Check PDF page count
    if ext == ".pdf":
        try:
            pages = get_pdf_page_count(filepath)
            if pages > MAX_PAGES:
                result["warnings"].append(
                    f"Page count {pages} exceeds limit {MAX_PAGES}"
                )
        except Exception as e:
            result["warnings"].append(f"Could not read page count: {e}")

    return result


def detect_formula_features(text: str) -> bool:
    """Detect if text contains formula-like patterns."""
    for pattern in FORMULA_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def detect_document_type(filepath: str) -> Dict[str, Any]:
    """
    Detect document type by quick scan.

    Returns:
        {
            "type": "simple" | "paper" | "chart" | "scanned",
            "has_images": bool,
            "has_tables": bool,
            "has_formulas": bool,
            "text_quality": "good" | "poor" | "none",
            "recommended_mode": str
        }
    """
    result = {
        "type": "simple",
        "has_images": False,
        "has_tables": False,
        "has_formulas": False,
        "text_quality": "good",
        "recommended_mode": "light",
    }

    ext = Path(filepath).suffix.lower()

    # Non-PDF files: recommend MinerU
    if ext != ".pdf":
        result["type"] = "other"
        result["recommended_mode"] = "mineru-precision"
        return result

    # Quick scan with PyMuPDF
    try:
        doc = fitz.open(filepath)
        # Scan first 3 pages
        sample_pages = doc[: min(3, len(doc))]

        total_images = 0
        total_links = 0
        total_text = ""
        text_extracted = False

        for page in sample_pages:
            # Check images
            images = page.get_images()
            total_images += len(images)

            # Check hyperlinks
            links = page.get_links()
            total_links += len(links)

            # Extract text
            text = page.get_text()
            total_text += text
            if text.strip():
                text_extracted = True

        result["has_images"] = total_images > 0
        result["has_links"] = total_links > 0  # Add links detection
        result["has_formulas"] = detect_formula_features(total_text)

        # Determine text quality
        if not text_extracted:
            result["text_quality"] = "none"
        elif len(total_text) < 100:
            result["text_quality"] = "poor"
        else:
            result["text_quality"] = "good"

        # Determine document type and recommended mode
        if result["text_quality"] == "none" or result["text_quality"] == "poor":
            result["type"] = "scanned"
            result["recommended_mode"] = "mineru-precision"
        elif result["has_formulas"]:
            result["type"] = "paper"
            result["recommended_mode"] = "mineru-precision"
        elif result["has_images"] and len(total_text) > 500:
            # Document with images and substantial text
            result["type"] = "mixed"
            result["recommended_mode"] = "light"
        else:
            result["type"] = "simple"
            result["recommended_mode"] = "light"

        doc.close()

    except Exception as e:
        print(f"[Warning] Quick scan failed: {e}")
        result["type"] = "unknown"
        result["recommended_mode"] = "mineru-light"

    return result


# ============================================================================
# Lightweight Parser (PyMuPDF)
# ============================================================================


def parse_with_pymupdf(
    filepath: str,
    output_path: Optional[str] = None,
    extract_images: bool = True,
    image_output_dir: Optional[str] = None,
) -> str:
    """
    Parse PDF with PyMuPDF (lightweight mode).

    Features:
    - Extract text content
    - Extract and save images
    - Extract hyperlinks
    - Convert to Markdown format

    Args:
        filepath: Input PDF file path
        output_path: Output markdown file path (optional)
        extract_images: Whether to extract images (default: True)
        image_output_dir: Directory to save extracted images (default: same as output)

    Returns markdown-formatted text.
    """
    print("[Info] Using PyMuPDF lightweight mode...")

    markdown_lines = []

    # Prepare image output directory
    if extract_images:
        if image_output_dir:
            img_dir = Path(image_output_dir)
        elif output_path:
            img_dir = Path(output_path).parent / "images"
        else:
            img_dir = Path(filepath).parent / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(filepath)
        total_pages = len(doc)

        for page_num in range(total_pages):
            page = doc[page_num]
            print(f"[Info] Processing page {page_num + 1}/{total_pages}...")

            # Page header
            markdown_lines.append(f"\n## Page {page_num + 1}\n\n")

            # Extract text
            text = page.get_text()
            if text.strip():
                markdown_lines.append(text.strip())
                markdown_lines.append("\n")

            # Extract hyperlinks
            links = page.get_links()
            if links:
                markdown_lines.append("\n### Hyperlinks\n\n")
                for link in links:
                    uri = link.get("uri", "")
                    if uri:
                        # Try to get the link text by position
                        rect = link.get("rect")
                        if rect:
                            link_text = page.get_text("text", clip=fitz.Rect(rect))
                            if link_text.strip():
                                markdown_lines.append(f"- [{link_text.strip()}]({uri})")
                            else:
                                markdown_lines.append(f"- [{uri}]({uri})")
                        else:
                            markdown_lines.append(f"- [{uri}]({uri})")
                markdown_lines.append("\n")

            # Extract images
            if extract_images:
                images = page.get_images(full=True)
                if images:
                    markdown_lines.append("\n### Images\n\n")
                    for img_index, img in enumerate(images):
                        try:
                            xref = img[0]  # Image reference number
                            base_image = doc.extract_image(xref)

                            if base_image:
                                image_bytes = base_image["image"]
                                image_ext = base_image["ext"]

                                # Save image
                                img_filename = (
                                    f"page{page_num + 1}_img{img_index + 1}.{image_ext}"
                                )
                                img_path = img_dir / img_filename

                                with open(img_path, "wb") as f:
                                    f.write(image_bytes)

                                # Add to markdown
                                markdown_lines.append(
                                    f"![Image {img_index + 1}](images/{img_filename})"
                                )
                                markdown_lines.append("\n")
                        except Exception as img_e:
                            # Skip this image, continue with others
                            print(
                                f"[Warning] Failed to extract image {img_index + 1} on page {page_num + 1}: {img_e}"
                            )
                            markdown_lines.append(
                                f"[Image {img_index + 1} - extraction failed]\n"
                            )

        doc.close()

    except Exception as e:
        print(f"[Error] PyMuPDF extraction failed: {e}")
        return ""

    result = "\n".join(markdown_lines)

    # Write to output file if specified
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"[Success] Output saved to: {output_path}")

    return result


# ============================================================================
# MinerU API Parser
# ============================================================================


def parse_with_mineru(
    filepath: str,
    mode: str = "light",  # "light" or "precision"
    language: str = DEFAULT_LANGUAGE,
    output_path: Optional[str] = None,
) -> str:
    """
    Parse PDF with MinerU batch API (async workflow).

    Workflow:
    1. Get presigned upload URL from /file-urls/batch
    2. PUT upload file to OSS
    3. Poll /extract-results/batch/{batch_id} until done
    4. Download and extract result zip

    Args:
        filepath: Input file path
        mode: "light" (formula=False, table=True) or "precision" (formula=True, table=True, ocr=True)
        language: Document language (zh, en, ja, ko, etc.)
        output_path: Output file path (optional)

    Returns markdown-formatted text.
    """
    if not MINERU_API_KEY:
        print("[Error] MINERU_API_KEY environment variable not set")
        print("[Hint] Run: export MINERU_API_KEY='your-api-key'")
        return ""

    print(f"[Info] Using MinerU batch API ({mode} mode)...")

    # Build parameters based on mode
    if mode == "precision":
        model_version = "vlm"  # VLM for precision
    else:  # light
        model_version = "pipeline"  # Pipeline for light

    filename = Path(filepath).name
    data_id = f"parse-{int(time.time())}"

    # Step 1: Get presigned upload URL
    print("[Info] Step 1: Getting presigned upload URL...")
    request_payload = {
        "files": [{"name": filename, "data_id": data_id}],
        "model_version": model_version,
    }

    headers = {
        "Authorization": f"Bearer {MINERU_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            f"{MINERU_API_URL}/file-urls/batch",
            json=request_payload,
            headers=headers,
            timeout=30,
        )

        if response.status_code != 200:
            print(f"[Error] Failed to get upload URL: {response.status_code}")
            print(f"[Error] Response: {response.text[:500]}")
            return ""

        result = response.json()
        if result.get("code") != 0:
            print(f"[Error] API error: {result.get('msg')}")
            return ""

        batch_id = result["data"]["batch_id"]
        file_urls = result["data"]["file_urls"]
        upload_url = file_urls[0]

        print(f"[Info] batch_id: {batch_id}")
        print(f"[Info] upload_url obtained")

    except Exception as e:
        print(f"[Error] Failed to get upload URL: {e}")
        return ""

    # Step 2: Upload file to OSS (PUT without Content-Type header)
    print("[Info] Step 2: Uploading file to OSS...")
    try:
        with open(filepath, "rb") as f:
            upload_response = requests.put(upload_url, data=f, timeout=120)

        if upload_response.status_code != 200:
            print(f"[Error] Upload failed: {upload_response.status_code}")
            print(f"[Error] Response: {upload_response.text[:500]}")
            return ""

        print("[Info] Upload successful")

    except Exception as e:
        print(f"[Error] Upload failed: {e}")
        return ""

    # Step 3: Poll batch results until done
    print("[Info] Step 3: Polling for results...")
    max_retries = 60  # 60 * 5 = 300 seconds max wait
    retry_interval = 5

    for retry in range(max_retries):
        try:
            poll_response = requests.get(
                f"{MINERU_API_URL}/extract-results/batch/{batch_id}",
                headers=headers,
                timeout=30,
            )

            if poll_response.status_code != 200:
                print(f"[Warning] Poll failed: {poll_response.status_code}")
                time.sleep(retry_interval)
                continue

            poll_result = poll_response.json()
            if poll_result.get("code") != 0:
                print(f"[Warning] Poll error: {poll_result.get('msg')}")
                time.sleep(retry_interval)
                continue

            extract_results = poll_result["data"]["extract_result"]
            if not extract_results:
                print("[Warning] No results yet, waiting...")
                time.sleep(retry_interval)
                continue

            file_result = extract_results[0]
            state = file_result.get("state", "pending")

            if state == "done":
                zip_url = file_result.get("full_zip_url")
                print(f"[Info] Extraction complete!")
                print(f"[Info] Download URL: {zip_url}")
                break
            elif state == "failed":
                err_msg = file_result.get("err_msg", "unknown error")
                print(f"[Error] Extraction failed: {err_msg}")
                return ""
            elif state == "running":
                progress = file_result.get("extract_progress", {})
                extracted = progress.get("extracted_pages", 0)
                total = progress.get("total_pages", "?")
                print(f"[Info] Progress: {extracted}/{total} pages")
                time.sleep(retry_interval)
            else:
                print(f"[Info] State: {state}, waiting...")
                time.sleep(retry_interval)

        except Exception as e:
            print(f"[Warning] Poll error: {e}")
            time.sleep(retry_interval)

    else:
        print("[Error] Timeout waiting for extraction")
        return ""

    # Step 4: Download and extract result
    print("[Info] Step 4: Downloading result...")
    if not zip_url:
        print("[Error] No download URL found")
        return ""

    try:
        # Download zip
        zip_response = requests.get(zip_url, timeout=120)
        if zip_response.status_code != 200:
            print(f"[Error] Download failed: {zip_response.status_code}")
            return ""

        # Save to temp file and extract (use tempfile, never hardcode /tmp)
        import zipfile
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_zip_path = Path(temp_dir) / f"mineru_{batch_id}.zip"
            with open(temp_zip_path, "wb") as f:
                f.write(zip_response.content)

            with zipfile.ZipFile(temp_zip_path, "r") as zf:
                # ZIP Slip 防护：逐成员校验路径不逃逸 temp_dir
                td_resolved = Path(temp_dir).resolve()
                for member in zf.namelist():
                    member_target = (td_resolved / member).resolve()
                    try:
                        member_target.relative_to(td_resolved)
                    except ValueError:
                        print(f"  [Warn] 跳过逃逸成员: {member}")
                        continue
                    zf.extract(member, temp_dir)

            # Find full.md
            full_md_path = Path(temp_dir) / "full.md"
            if full_md_path.exists():
                markdown_content = full_md_path.read_text(encoding="utf-8")
            else:
                # Try content_list.json fallback
                content_json_candidates = list(
                    Path(temp_dir).glob("*_content_list.json")
                )
                if not content_json_candidates:
                    print("[Error] No full.md and no *_content_list.json in zip")
                    return ""
                content_data = json.loads(content_json_candidates[0].read_text())
                markdown_content = extract_mineru_markdown(content_data)

    except Exception as e:
        print(f"[Error] Failed to download/extract: {e}")
        return ""

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"[Success] Output saved to: {output_path}")

    return markdown_content


def extract_mineru_markdown(api_response: Dict[str, Any]) -> str:
    """
    Extract markdown content from MinerU API response.

    Response structure (from documentation):
    {
        "pdf_info": {
            "para_blocks": [
                {"type": "text", "content": "..."},
                {"type": "table", "html": "..."},
                {"type": "formula", "latex": "..."}
            ]
        },
        "_parse_type": "txt" | "ocr"
    }
    """
    markdown_lines = []

    # Try to get markdown directly if available
    if "markdown" in api_response:
        return api_response["markdown"]

    # Parse structured response
    pdf_info = api_response.get("pdf_info", {})
    para_blocks = pdf_info.get("para_blocks", [])

    if not para_blocks:
        # Fallback: try to get raw content
        return api_response.get("content", str(api_response))

    for block in para_blocks:
        block_type = block.get("type", "text")

        if block_type == "text":
            content = block.get("content", "")
            if content:
                markdown_lines.append(content)

        elif block_type == "title":
            content = block.get("content", "")
            level = block.get("level", 1)
            if content:
                markdown_lines.append(f"\n{'#' * level} {content}\n")

        elif block_type == "formula":
            latex = block.get("latex", "")
            if latex:
                markdown_lines.append(f"\n$$\n{latex}\n$$\n")

        elif block_type == "table":
            html = block.get("html", "")
            if html:
                # Simple HTML to markdown conversion
                # (MinerU returns HTML tables)
                markdown_lines.append(f"\n{html}\n")

        elif block_type == "image":
            # Image reference
            image_path = block.get("path", "")
            caption = block.get("caption", "")
            if image_path:
                markdown_lines.append(f"\n![{caption}]({image_path})\n")

    return "\n".join(markdown_lines)


# ============================================================================
# Main Parser with Auto Mode
# ============================================================================


def parse_pdf(
    filepath: str,
    mode: str = "auto",
    language: str = DEFAULT_LANGUAGE,
    output_path: Optional[str] = None,
    extract_images: bool = True,
) -> str:
    """
    Parse PDF with automatic mode selection.

    Args:
        filepath: Input file path
        mode: "auto", "light", "mineru-light", "mineru-precision"
        language: Document language
        output_path: Output file path (optional)
        extract_images: Whether to extract images in light mode (default: True)

    Returns markdown-formatted content.
    """
    # Validate file
    validation = validate_file(filepath)
    if not validation["valid"]:
        for error in validation["errors"]:
            print(f"[Error] {error}")
        return ""

    for warning in validation["warnings"]:
        print(f"[Warning] {warning}")

    # Auto mode: detect document type
    if mode == "auto":
        print("[Info] Auto mode: detecting document type...")
        doc_type = detect_document_type(filepath)
        print(f"[Info] Document type: {doc_type['type']}")
        print(
            f"[Info] Features: images={doc_type['has_images']}, formulas={doc_type['has_formulas']}"
        )
        print(f"[Info] Text quality: {doc_type['text_quality']}")

        selected_mode = doc_type["recommended_mode"]
        print(f"[Info] Selected mode: {selected_mode}")
    else:
        selected_mode = mode

    # Execute parsing based on selected mode
    if selected_mode == "light":
        return parse_with_pymupdf(filepath, output_path, extract_images)
    elif selected_mode == "mineru-light":
        return parse_with_mineru(filepath, "light", language, output_path)
    elif selected_mode == "mineru-precision":
        return parse_with_mineru(filepath, "precision", language, output_path)
    else:
        print(f"[Error] Unknown mode: {selected_mode}")
        return ""


# ============================================================================
# CLI Entry Point
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="PDF Parse Skill - Intelligent PDF parsing with automatic mode selection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto detect and parse
  python3 main.py "paper.pdf" --mode auto

  # Lightweight extraction (PyMuPDF - text + images + links)
  python3 main.py "document.pdf" --mode light

  # MinerU precision mode (papers with formulas)
  python3 main.py "paper.pdf" --mode mineru-precision --language en

  # Save output to file
  python3 main.py "paper.pdf" --output "output.md"

  # Skip image extraction in light mode
  python3 main.py "document.pdf" --mode light --no-images
""",
    )

    parser.add_argument("filepath", help="Input file path (PDF, image, DOCX, etc.)")
    parser.add_argument(
        "--mode",
        choices=["auto", "light", "mineru-light", "mineru-precision"],
        default="auto",
        help="Parsing mode (default: auto)",
    )
    parser.add_argument(
        "--language", default=DEFAULT_LANGUAGE, help="Document language (default: zh)"
    )
    parser.add_argument("--output", help="Output file path (optional)")
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction in light mode",
    )

    args = parser.parse_args()

    # Execute parsing
    result = parse_pdf(
        filepath=args.filepath,
        mode=args.mode,
        language=args.language,
        output_path=args.output,
        extract_images=not args.no_images,
    )

    if result:
        # Print to stdout if no output file specified
        if not args.output:
            print("\n" + "=" * 60)
            print("PARSED CONTENT")
            print("=" * 60)
            print(result)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

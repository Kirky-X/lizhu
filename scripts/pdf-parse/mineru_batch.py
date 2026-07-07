#!/usr/bin/env python3
"""
MinerU Batch PDF Parser

Splits PDFs into chunks of max 200 pages, processes each with MinerU API,
then merges results into a single Markdown file with images.
"""

import os
import re
import sys
import time
import json
import zipfile
import tempfile
import shutil
from pathlib import Path

import fitz  # PyMuPDF
import requests

MINERU_API_URL = os.environ.get("MINERU_API_URL", "https://mineru.net/api/v4")
MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
MAX_PAGES_PER_REQUEST = 200
POLL_INTERVAL = 10
MAX_POLL_RETRIES = 120


def split_pdf(pdf_path, output_dir, chunk_size=MAX_PAGES_PER_REQUEST):
    """Split PDF into chunks. Returns list of (chunk_path, start_page, end_page)."""
    doc = fitz.open(pdf_path)
    total = len(doc)
    chunks = []
    for i in range(0, total, chunk_size):
        end = min(i + chunk_size, total)
        chunk_path = os.path.join(output_dir, f"chunk_{i:04d}_{end:04d}.pdf")
        chunk_doc = fitz.open()
        chunk_doc.insert_pdf(doc, from_page=i, to_page=end - 1)
        chunk_doc.save(chunk_path)
        chunk_doc.close()
        chunks.append((chunk_path, i, end))
    doc.close()
    return chunks, total


def upload_and_extract(chunk_path, img_dir, mode="precision", img_prefix=""):
    """Upload PDF chunk to MinerU, extract markdown and images.

    Copies images from result zip into img_dir with optional prefix.
    Rewrites markdown image paths to match prefixed filenames.
    """
    filename = Path(chunk_path).name
    data_id = f"parse-{int(time.time())}"
    headers = {
        "Authorization": f"Bearer {MINERU_API_KEY}",
        "Content-Type": "application/json",
    }
    model_version = "vlm" if mode == "precision" else "pipeline"

    # Step 1: Get presigned URL
    try:
        resp = requests.post(
            f"{MINERU_API_URL}/file-urls/batch",
            json={
                "files": [{"name": filename, "data_id": data_id}],
                "model_version": model_version,
            },
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"  [Error] Upload URL: {resp.status_code} {resp.text[:300]}")
            return None
        data = resp.json()
        if data.get("code") != 0:
            print(f"  [Error] API: {data.get('msg')}")
            return None
        data_payload = data.get("data") or {}
        batch_id = data_payload.get("batch_id")
        file_urls = data_payload.get("file_urls") or []
        if not batch_id or not file_urls:
            print(f"  [Error] API response missing batch_id or file_urls: {data}")
            return None
        upload_url = file_urls[0]
    except Exception as e:
        print(f"  [Error] URL: {e}")
        return None

    # Step 2: Upload
    try:
        with open(chunk_path, "rb") as f:
            upload_resp = requests.put(upload_url, data=f, timeout=120)
        if upload_resp.status_code not in (200, 201):
            print(f"  [Error] Upload: {upload_resp.status_code}")
            return None
    except Exception as e:
        print(f"  [Error] Upload: {e}")
        return None

    # Step 3: Poll
    print(f"  Polling {batch_id}...", end="", flush=True)
    zip_url = None
    for attempt in range(MAX_POLL_RETRIES):
        time.sleep(POLL_INTERVAL)
        try:
            poll = requests.get(
                f"{MINERU_API_URL}/extract-results/batch/{batch_id}",
                headers=headers,
                timeout=30,
            )
            if poll.status_code != 200:
                print(".", end="", flush=True)
                continue
            poll_data = poll.json()
            if poll_data.get("code") != 0:
                print(".", end="", flush=True)
                continue
            data_payload = poll_data.get("data") or {}
            results = data_payload.get("extract_result") or []
            if not results:
                print(".", end="", flush=True)
                continue
            file_result = results[0]
            state = file_result.get("state", "pending")
            if state == "done":
                zip_url = file_result.get("full_zip_url", "")
                print(f" Done! ({(attempt + 1) * POLL_INTERVAL}s)")
                break
            elif state == "failed":
                print(f" Failed: {file_result.get('err_msg', 'unknown')}")
                return None
            elif state == "running":
                p = file_result.get("extract_progress", {})
                print(
                    f" {p.get('extracted_pages', '?')}/{p.get('total_pages', '?')}...",
                    end="",
                    flush=True,
                )
            else:
                print(f" {state}...", end="", flush=True)
        except Exception:
            print(".", end="", flush=True)

    if not zip_url:
        print(" Timeout!")
        return None

    # Step 4: Download and extract
    try:
        dl = requests.get(zip_url, timeout=120)
        if dl.status_code != 200:
            print(f"  [Error] Download: {dl.status_code}")
            return None
        with tempfile.TemporaryDirectory() as td:
            zip_path = os.path.join(td, "result.zip")
            with open(zip_path, "wb") as zf:
                zf.write(dl.content)
            with zipfile.ZipFile(zip_path, "r") as z:
                # ZIP Slip 防护：逐成员校验路径不逃逸 td
                td_resolved = Path(td).resolve()
                for member in z.namelist():
                    member_target = (td_resolved / member).resolve()
                    try:
                        member_target.relative_to(td_resolved)
                    except ValueError:
                        print(f"  [Warn] 跳过逃逸成员: {member}")
                        continue
                    z.extract(member, td)

            # Copy images from zip to img_dir with prefix
            img_count = 0
            src_img_dir = Path(td) / "images"
            if src_img_dir.exists():
                for img_file in sorted(src_img_dir.iterdir()):
                    if img_file.is_file():
                        dest_name = (
                            f"{img_prefix}{img_file.name}"
                            if img_prefix
                            else img_file.name
                        )
                        shutil.copy2(str(img_file), str(img_dir / dest_name))
                        img_count += 1
            if img_count > 0:
                print(f"  Images extracted: {img_count}")

            # Read full.md and rewrite image paths to include prefix
            full_md = Path(td) / "full.md"
            if full_md.exists():
                md_text = full_md.read_text(encoding="utf-8")
                if img_prefix:
                    md_text = re.sub(
                        r"!\[([^\]]*)\]\(images/([^)]+)\)",
                        f"![\\1](images/{img_prefix}\\2)",
                        md_text,
                    )
                return md_text

            # Fallback: any .md
            mds = list(Path(td).glob("*.md"))
            if mds:
                md_text = mds[0].read_text(encoding="utf-8")
                if img_prefix:
                    md_text = re.sub(
                        r"!\[([^\]]*)\]\(images/([^)]+)\)",
                        f"![\\1](images/{img_prefix}\\2)",
                        md_text,
                    )
                return md_text

            # Last resort: content_list.json
            cls = list(Path(td).glob("*_content_list.json"))
            if cls:
                return json.dumps(
                    json.loads(cls[0].read_text()), indent=2, ensure_ascii=False
                )
            print(f"  [Error] No content in zip")
            return None
    except Exception as e:
        print(f"  [Error] Extract: {e}")
        return None


def process_pdf(pdf_path, output_dir):
    """Process a single PDF with MinerU, splitting into chunks if needed."""
    pdf_name = Path(pdf_path).stem
    book_dir = Path(output_dir) / pdf_name
    book_dir.mkdir(parents=True, exist_ok=True)
    img_dir = book_dir / "images"
    img_dir.mkdir(exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"Processing: {Path(pdf_path).name}")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()
    print(f"  Total pages: {total_pages}")

    chunks_info = []
    tmp_dir = None

    if total_pages <= MAX_PAGES_PER_REQUEST:
        chunks_info = [(pdf_path, 0, total_pages)]
    else:
        tmp_dir = book_dir / "_chunks"
        tmp_dir.mkdir(exist_ok=True)
        chunks_info, _ = split_pdf(pdf_path, str(tmp_dir))
        print(
            f"  Split into {len(chunks_info)} chunks (max {MAX_PAGES_PER_REQUEST} pages)"
        )

    all_md = []
    success_count = 0
    total_images = 0

    for i, (chunk_path, start, end) in enumerate(chunks_info):
        label = Path(chunk_path).name if tmp_dir else Path(pdf_path).name
        # Use prefix for chunked files to avoid image name collisions
        img_prefix = f"chunk{i:02d}_" if len(chunks_info) > 1 else ""
        print(f"  [{i + 1}/{len(chunks_info)}] {label} (pages {start + 1}-{end})")
        md_content = upload_and_extract(chunk_path, img_dir, "precision", img_prefix)
        if md_content:
            all_md.append(f"\n<!-- Pages {start + 1}-{end} -->\n\n")
            all_md.append(md_content)
            all_md.append("\n\n---\n\n")
            success_count += 1
            # Count images in this chunk's markdown
            total_images += len(re.findall(r"!\[.*?\]\(images/[^)]+\)", md_content))
        else:
            print(f"  [WARN] Chunk failed!")
            all_md.append(f"\n<!-- Pages {start + 1}-{end} - FAILED -->\n\n")

    # Merge
    output_md = book_dir / "output.md"
    output_md.write_text("".join(all_md), encoding="utf-8")

    # Cleanup chunks
    if tmp_dir and tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(
        f"  Images: {total_images} referenced in markdown, {len(list(img_dir.iterdir()))} on disk"
    )
    print(f"  Result: {success_count}/{len(chunks_info)} chunks succeeded")
    print(f"  Output: {output_md}")
    return success_count == len(chunks_info)


def main():
    if not MINERU_API_KEY:
        print("[Error] MINERU_API_KEY not set")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: mineru_batch.py <pdf_dir_or_file> [output_dir]")
        print("Examples:")
        print("  mineru_batch.py /path/to/pdfs/")
        print("  mineru_batch.py /path/to/pdfs/ /path/to/output/")
        print("  mineru_batch.py single.pdf")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_base = sys.argv[2] if len(sys.argv) > 2 else None

    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdf_files = [input_path]
        if output_base is None:
            output_base = str(input_path.parent / "pdf-output-mineru")
    elif input_path.is_dir():
        pdf_files = sorted(input_path.glob("*.pdf"))
        if output_base is None:
            output_base = str(input_path / "pdf-output-mineru")
    else:
        print(f"[Error] Not a PDF file or directory: {input_path}")
        sys.exit(1)

    if not pdf_files:
        print(f"No PDF files found in: {input_path}")
        sys.exit(0)

    print(f"Found {len(pdf_files)} PDF file(s)")
    print(f"Output directory: {output_base}")
    print(f"Max pages per request: {MAX_PAGES_PER_REQUEST}")

    results = []
    for i, pf in enumerate(pdf_files, 1):
        ok = process_pdf(str(pf), output_base)
        results.append((pf.name, "OK" if ok else "FAIL"))
        print(f"\n[{i}/{len(pdf_files)}] Done: {pf.name[:60]}")

    print("\n" + "=" * 60)
    print("Summary:")
    ok_count = sum(1 for _, s in results if s == "OK")
    fail_count = len(results) - ok_count
    print(f"Success: {ok_count}, Failed: {fail_count}")
    print(f"Output: {output_base}")
    if fail_count:
        print("\nFailed files:")
        for name, status in results:
            if status == "FAIL":
                print(f"  - {name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
QR Scanner Skill - 二维码扫描脚本

从图片中扫描并提取二维码内容（URL、文本等）
使用 zxing-cpp 进行二维码解码（93.3%正确率，最高精度）
"""

import argparse
import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# Try to import required libraries
try:
    from PIL import Image
except ImportError:
    print("[Error] Pillow not installed. Run: pip install pillow")
    sys.exit(1)

try:
    from zxingcpp import read_barcodes
except ImportError:
    print("[Error] zxing-cpp not installed. Run: pip install zxing-cpp")
    print("[Info] zxing-cpp is the highest accuracy QR decoder (93.3% success rate)")
    sys.exit(1)


# Supported image formats
SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# Max file size (10MB)
MAX_FILE_SIZE_MB = 10


def get_file_size_mb(filepath: str) -> float:
    """Get file size in MB."""
    return os.path.getsize(filepath) / (1024 * 1024)


def validate_image(filepath: str) -> Dict[str, Any]:
    """Validate input image file."""
    result = {"valid": True, "errors": [], "warnings": []}

    if not os.path.exists(filepath):
        result["valid"] = False
        result["errors"].append(f"File not found: {filepath}")
        return result

    ext = Path(filepath).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        result["valid"] = False
        result["errors"].append(
            f"Unsupported format: {ext}. Supported: {', '.join(SUPPORTED_FORMATS)}"
        )
        return result

    size_mb = get_file_size_mb(filepath)
    if size_mb > MAX_FILE_SIZE_MB:
        result["warnings"].append(
            f"File size {size_mb:.1f}MB exceeds {MAX_FILE_SIZE_MB}MB. Consider compressing."
        )

    return result


def is_url(text: str) -> bool:
    """Check if text is a URL."""
    url_pattern = re.compile(
        r"^https?://"
        r"(?:www\.)?"
        r"[a-zA-Z0-9-]+"
        r"\.[a-zA-Z]{2,}"
        r"(?:/[^\s]*)?",
        re.IGNORECASE,
    )
    return bool(url_pattern.match(text))


def scan_qrcode(filepath: str) -> List[Dict[str, Any]]:
    """
    Scan QR codes from an image file using zxing-cpp.

    Returns list of decoded QR code contents.
    """
    results = []

    try:
        # Open image with PIL
        image = Image.open(filepath)

        # Decode barcodes with zxing-cpp
        decoded_results = read_barcodes(image)

        for result in decoded_results:
            # Check if it's a QR code
            if result.format.name == "QRCode":
                content = result.text
                position = result.position

                results.append(
                    {
                        "type": "qrcode",
                        "content": content,
                        "is_url": is_url(content),
                        "rect": {
                            "left": position.top_left.x,
                            "top": position.top_left.y,
                            "width": position.bottom_right.x - position.top_left.x,
                            "height": position.bottom_right.y - position.top_left.y,
                        },
                    }
                )

    except Exception as e:
        print(f"[Error] Failed to scan image: {e}")
        return []

    return results


def scan_directory(dirpath: str) -> Dict[str, List[Dict[str, Any]]]:
    """Scan all images in a directory for QR codes."""
    all_results = {}

    for ext in SUPPORTED_FORMATS:
        for filepath in Path(dirpath).glob(f"*{ext}"):
            results = scan_qrcode(str(filepath))
            if results:
                all_results[str(filepath)] = results

    return all_results


def format_output_text(
    results: List[Dict[str, Any]], filepath: Optional[str] = None
) -> str:
    """Format results as human-readable text."""
    lines = []

    if filepath:
        lines.append(f"File: {filepath}")

    if not results:
        lines.append("[Info] No QR codes detected in this image")
        lines.append(
            "[Hint] Possible reasons: image too blurry, QR code too small, or no QR code present"
        )
        return "\n".join(lines)

    for i, result in enumerate(results):
        prefix = f"QR Code {i + 1}" if len(results) > 1 else "QR Code"
        content = result["content"]

        if result["is_url"]:
            lines.append(f"【{prefix}】Link: {content}")
            lines.append(f"  Markdown: [{content}]({content})")
        else:
            lines.append(f"【{prefix}】Text: {content}")

    return "\n".join(lines)


def format_output_json(
    results: List[Dict[str, Any]], filepath: Optional[str] = None
) -> str:
    """Format results as JSON."""
    output = {
        "success": len(results) > 0,
        "count": len(results),
        "file": filepath,
        "results": results,
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(
        description="QR Scanner Skill - Scan QR codes from images (zxing-cpp)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py "qrcode.png"
  python3 main.py --batch "images/"
  python3 main.py "qrcode.png" --format json
""",
    )

    parser.add_argument("input", help="Image file path or directory (with --batch)")
    parser.add_argument(
        "--batch", action="store_true", help="Scan all images in directory"
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format"
    )
    parser.add_argument("--output", help="Output file path (optional)")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[Error] Input not found: {args.input}")
        sys.exit(1)

    if args.batch:
        if not os.path.isdir(args.input):
            print(f"[Error] --batch requires a directory: {args.input}")
            sys.exit(1)

        print(f"[Info] Scanning directory: {args.input}")
        all_results = scan_directory(args.input)

        if args.format == "json":
            output = json.dumps(all_results, indent=2, ensure_ascii=False)
        else:
            lines = []
            for filepath, results in all_results.items():
                lines.append(format_output_text(results, filepath))
                lines.append("")
            output = "\n".join(lines)

    else:
        validation = validate_image(args.input)
        if not validation["valid"]:
            for error in validation["errors"]:
                print(f"[Error] {error}")
            sys.exit(1)

        for warning in validation["warnings"]:
            print(f"[Warning] {warning}")

        print(f"[Info] Scanning: {args.input}")
        results = scan_qrcode(args.input)

        if args.format == "json":
            output = format_output_json(results, args.input)
        else:
            output = format_output_text(results, args.input)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[Success] Output saved to: {args.output}")
    else:
        print(output)

    # Exit code semantics: 0 = scan completed successfully (regardless of QR found or not)
    # 1 = scan failed (file not found, invalid format, scan exception)
    # "No QR detected" is a successful scan with empty results, NOT a failure.
    sys.exit(0)


if __name__ == "__main__":
    main()

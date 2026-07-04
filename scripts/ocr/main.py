#!/usr/bin/env python3
"""
DeepSeek OCR Skill - 主脚本
使用 DeepSeek-OCR-2 API 进行图像 OCR 识别
"""

import os
import sys
import base64
from pathlib import Path
from openai import OpenAI


API_BASE_URL = os.environ.get("DEEPSEEK_OCR_API_URL", "https://www.aiping.cn/api/v1")
API_KEY = os.environ.get("DEEPSEEK_OCR_API_KEY", "")
MODEL = os.environ.get("DEEPSEEK_OCR_MODEL", "DeepSeek-OCR-2")


def _ensure_api_key():
    """API key 必须显式提供，禁止硬编码。"""
    if not API_KEY:
        print("[Error] DEEPSEEK_OCR_API_KEY 环境变量未设置")
        print("[Hint] Run: export DEEPSEEK_OCR_API_KEY='your-api-key'")
        sys.exit(1)


def is_url(path: str) -> bool:
    return path.startswith("http://") or path.startswith("https://")


def encode_image_to_base64(image_path: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"图像文件不存在: {image_path}")

    suffix = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    mime_type = mime_map.get(suffix, "image/png")

    image_data = path.read_bytes()
    base64_data = base64.b64encode(image_data).decode("utf-8")
    return f"data:{mime_type};base64,{base64_data}"


def ocr_image(image_input: str, question: str) -> None:
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    image_url = (
        image_input if is_url(image_input) else encode_image_to_base64(image_input)
    )

    response = client.chat.completions.create(
        model=MODEL,
        stream=True,
        extra_body={
            "provider": {
                "only": [],
                "order": [],
                "sort": "latency",
                "input_price_range": [0, 0],
                "output_price_range": [0, 0],
                "input_length_range": [],
                "output_length_range": [],
                "throughput_range": [],
                "latency_range": [],
            }
        },
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": question},
                ],
            }
        ],
    )

    for chunk in response:
        if not getattr(chunk, "choices", None):
            continue

        reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
        if reasoning:
            print(reasoning, end="", flush=True)

        content = getattr(chunk.choices[0].delta, "content", None)
        if content:
            print(content, end="", flush=True)

    print()


def main():
    if len(sys.argv) < 2:
        print("用法: python3 main.py <image_path_or_url> [question]")
        print("示例: python3 main.py screenshot.png '识别图像中的文字'")
        sys.exit(1)

    _ensure_api_key()

    image_input = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else "识别图像中的所有文字内容"

    try:
        ocr_image(image_input, question)
    except FileNotFoundError as e:
        print(f"错误: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"API 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

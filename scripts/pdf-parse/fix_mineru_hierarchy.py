#!/usr/bin/env python3
"""
MinerU Markdown 层级修复（v9）

策略：
1. 从文件名提取书名提示
2. 在所有 heading 中搜索与书名提示最匹配的
3. 根据内容模式分配 H1-H4
"""

import re
import sys
from collections import Counter
from pathlib import Path

# ── 前置页/版权 ───────────────────────────────────
FRONT_MATTER_PREFIXES = [
    "图书在版编目",
    "CIP数据",
    "版权所有",
    "ISBN",
    "定价",
    "出品人",
    "责任编辑",
    "出版",
    "印刷",
    "经销",
    "字数",
    "印张",
    "版次",
    "次印刷",
    "Psychologie des Foules",
    "所长林超著",
    "窑",
    "北京联合出版公司",
    "嘉业印刷",
    "新华书店经销",
    "第1版",
    "第1次印刷",
]

# ── H2: 部分/卷/序/目录 ─────────────────────────
H2_PREFIXES = [
    "第一部分",
    "第二部分",
    "第三部分",
    "第四部分",
    "第五部分",
    "第六部分",
    "第七部分",
    "第八部分",
    "第一卷",
    "第二卷",
    "第三卷",
    "第四卷",
    "第五卷",
    "上篇",
    "中篇",
    "下篇",
    "前言",
    "自序",
    "序言",
    "推荐序",
    "引言",
    "目录",
    "目 录",
    "目  录",
    "致谢",
    "后记",
    "结语",
    "结论",
    "附录",
    "本章小结",
]


def normalize_for_match(text):
    """合并连续空白/全角空格，用于前缀匹配。"""
    return re.sub(r"[\s　]+", "", text)


def strip_chapter_prefix(text):
    """去掉章节编号前缀，如 '10..达克效应' → '达克效应'。"""
    # 数字 + 标点/点 + 内容
    t = re.sub(r"^\d+[\.\.\s\-—]+", "", text)
    # 第X章/节 + 内容
    t = re.sub(r"^第[一二三四五六七八九十\d]+[章节篇回讲][\s\-—]*", "", t)
    # 中文序号 + 标点
    t = re.sub(r"^[一二三四五六七八九十]+[、，\s]", "", t)
    return t


def classify(text):
    """分类标题类型。"""
    t = text.strip()
    if not t:
        return "front"

    norm = normalize_for_match(t)
    for fm in FRONT_MATTER_PREFIXES:
        fm_norm = normalize_for_match(fm)
        if norm.startswith(fm_norm):
            return "front"

    for pt in H2_PREFIXES:
        pt_norm = normalize_for_match(pt)
        if norm.startswith(pt_norm):
            return "part"

    # 第X章/节/篇/回/讲
    if re.match(r"^第[一二三四五六七八九十\d]+[章节篇回讲]", t):
        return "chapter"

    # 原则N / Chapter N
    if re.match(r"^(原则|Chapter)\s*\d+", t):
        return "chapter"

    # NN 编号小节: 01 xxx / 1 xxx
    if re.match(r"^\d{1,2}[\s　]", t):
        return "subsection"

    # 中文序号 + 标点/空格
    if re.match(r"^[一二三四五六七八九十]+[、，\s]", t):
        return "sub_sub"

    # 第X步
    if re.match(r"^第[一二三四五六七八九十\d]+步", t):
        return "sub_sub"

    # 小作业/总结/小结
    if re.match(r"^(小作业|总结|小结)", t):
        return "subsection"

    # 短标题（≤15字）→ 章名
    if len(t) <= 15:
        return "chapter"

    return "content"


def is_mdformat_artifact(text):
    """检测 mdformat 换行产生的伪标题。"""
    t = text.strip()
    if len(t) <= 1:
        return True
    if re.match(r"^[一-龥]{1,3}[。！？\.\!，]$", t):
        return True
    # 英文单词 ≤4 字母可能是伪标题，但排除明显有意义的词
    if re.match(r"^[a-zA-Z]+$", t) and len(t) <= 3:
        return True
    return False


def find_book_title(all_texts, book_hint):
    """
    找书名。

    book_hint: 从文件名提取的书名，如 "开窍"、"达克效应"

    匹配策略：
    1. 精确匹配（去掉章节前缀后）
    2. 子串匹配（hint 在 heading 中，或 heading 在 hint 中）
    3. 频率分析回退
    """
    if not book_hint:
        return None

    # 清理 hint：去掉版本号、副标题
    hint_clean = book_hint.strip()
    hint_clean = re.sub(r"（第\d+版）", "", hint_clean).strip()

    # 排除模式（不可能是书名的内容）
    exclude_re = re.compile(
        r"^(第[一二三四五六七八九十\d]+[章节篇回讲])"
        r"|(原则)"
        r"^(^\d+$)"
    )

    # ── Pass 1: 精确匹配（去前缀后） ──
    # 要求：strip 后的文本完全等于 hint_clean，且原始文本不含章节编号
    for t in all_texts:
        stripped = strip_chapter_prefix(t.strip())
        if stripped == hint_clean:
            # 确保原始文本本身没有章节编号前缀（避免 "10..达克效应" 匹配）
            if stripped == t.strip():
                return t.strip()

    # ── Pass 2: 双向子串匹配 ──
    best_match = None
    best_score = 0

    for t in all_texts:
        ct = t.strip()
        if not ct or len(ct) > 50:
            continue
        if exclude_re.search(ct):
            continue

        stripped = strip_chapter_prefix(ct)
        # 跳过带章节编号前缀的 heading（如 "10..达克效应"）
        if stripped != ct:
            continue

        # hint 在 heading 中（要求完全匹配，因为已过滤带前缀的）
        if ct == hint_clean:
            return ct
        # heading 在 hint 中
        elif ct in hint_clean:
            score = len(ct) / max(len(hint_clean), 1)
            if score > best_score:
                best_score = score
                best_match = ct

    if best_match:
        return best_match

    # ── Pass 3: 如果 heading 中完全找不到 hint，直接用 hint 作为书名 ──
    # 这适用于文件名是可靠来源但 heading 中没有纯文本匹配的情况
    # 如 "达克效应" 在 heading 中只有 "10..达克效应"
    return hint_clean


def process_file(input_path, output_path, book_hint=None):
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 收集所有标题文本
    all_texts = []
    for line in lines:
        s = line.strip()
        m = re.match(r"^(#+)\s*(.*)", s)
        if m:
            all_texts.append(m.group(2))

    book_title = find_book_title(all_texts, book_hint)

    # 一次性分配层级
    book_title_seen = False
    output_lines = []

    for i, line in enumerate(lines):
        s = line.strip()
        m = re.match(r"^(#+)\s*(.*)", s)
        if not m:
            output_lines.append(line)
            continue

        text = m.group(2)
        t = text.strip()
        htype = classify(text)

        if is_mdformat_artifact(t) and htype != "front":
            level = 4
        # 匹配书名：精确匹配 或 strip_chapter_prefix 后匹配
        text_stripped = strip_chapter_prefix(t)
        if book_title and (t == book_title or text_stripped == book_title):
            if not book_title_seen:
                level = 1
                book_title_seen = True
            else:
                level = 2
        elif htype == "front":
            level = 2
        elif htype == "part":
            level = 2
        elif htype in ("chapter", "subsection"):
            level = 3
        elif htype == "sub_sub":
            level = 4
        else:
            level = 4

        output_lines.append("#" * level + " " + t + "\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

    # 统计
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for line in output_lines:
        s = line.strip()
        if s.startswith("#### "):
            counts[4] += 1
        elif s.startswith("### "):
            counts[3] += 1
        elif s.startswith("## ") and not s.startswith("### "):
            counts[2] += 1
        elif s.startswith("# ") and not s.startswith("## "):
            counts[1] += 1
    print(f"  书名: {book_title}")
    print(f"  H1: {counts[1]}, H2: {counts[2]}, H3: {counts[3]}, H4: {counts[4]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fix_mineru_hierarchy.py <input.md>")
        sys.exit(1)
    inp = sys.argv[1]
    # 从父目录名自动提取书名提示
    parent = Path(inp).parent
    default_hint = parent.name if parent.name != "." else Path(inp).stem
    default_hint = re.sub(r"（第\d+版）", "", default_hint)
    default_hint = re.sub(r"：.*", "", default_hint)
    process_file(inp, inp, default_hint)

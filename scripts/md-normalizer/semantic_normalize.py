#!/usr/bin/env python3
"""
Semantic normalization pass for Markdown files.

Handles:
- Soft-wrap joining within paragraphs and list item bodies
- Fenced code block repair (unclosed fences)
- Table structural repair (missing separator, ragged columns, missing outer pipes)

Usage:
    python3 semantic_normalize.py <input.md> <output.md>

Output to stdout:
    paragraph_joins=N
    fence_repairs=N
    table_repairs=N
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Stats:
    joins: int = 0
    fence_repairs: int = 0
    table_repairs: int = 0


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

HEADING_RE     = re.compile(r"^#{1,6}\s")
LIST_MARKER_RE = re.compile(r"^(\s*)(?:[-*+]|\d+\.)\s")
BLOCKQUOTE_RE  = re.compile(r"^>")
HR_RE          = re.compile(r"^(?:\*{3,}|-{3,}|_{3,})\s*$")
HTML_BLOCK_RE  = re.compile(r"^<[a-zA-Z/!]")
FENCE_OPEN_RE  = re.compile(r"^(`{3,}|~{3,})(.*)")
LINK_DEF_RE    = re.compile(r"^\[.*?\]:")
FOOTNOTE_RE    = re.compile(r"^\[\^.*?\]:")
FRONT_SEP_RE   = re.compile(r"^(---|`{3}|\.\.\.)\s*$")
EXPLICIT_BR_RE = re.compile(r"  $|\\$")

# A line is "table-like" if it has >= 2 pipe characters OR starts/ends with pipe
TABLE_LIKE_RE  = re.compile(r"^\|.*\||(.*\|){2,}")


def is_block_starter(line: str) -> bool:
    """Return True if line opens a new block (heading, list, fence, table row, etc.)."""
    s = line.strip()
    if not s:
        return True
    return bool(
        HEADING_RE.match(line)
        or LIST_MARKER_RE.match(line)
        or BLOCKQUOTE_RE.match(line)
        or HR_RE.match(s)
        or HTML_BLOCK_RE.match(line)
        or FENCE_OPEN_RE.match(line)
        or LINK_DEF_RE.match(line)
        or FOOTNOTE_RE.match(line)
        or s.startswith("|")   # table row — never join across table boundary
    )


def normalize_fence_opener(line: str) -> str:
    m = FENCE_OPEN_RE.match(line)
    if not m:
        return line
    lang = m.group(2).strip()
    return f"```{lang}" if lang else "```"


def is_table_like(line: str) -> bool:
    return bool(TABLE_LIKE_RE.match(line.strip()))


# ---------------------------------------------------------------------------
# Table repair
# ---------------------------------------------------------------------------

def fix_table_block(rows: list[str], stats: Stats) -> list[str]:
    """Add outer pipes, insert missing separator row, pad ragged columns."""
    repaired = False

    # Add outer pipes
    fixed = []
    for row in rows:
        r = row.rstrip()
        if not r.startswith("|"):
            r = "| " + r
            repaired = True
        if not r.endswith("|"):
            r = r + " |"
            repaired = True
        fixed.append(r)
    rows = fixed

    # Determine max column count
    def split_cells(row):
        return [c.strip() for c in row.strip().strip("|").split("|")]

    col_count = max(len(split_cells(r)) for r in rows)

    # Pad ragged rows
    padded = []
    for row in rows:
        cells = split_cells(row)
        while len(cells) < col_count:
            cells.append("")
            repaired = True
        padded.append("| " + " | ".join(cells) + " |")
    rows = padded

    # Check for separator row in position 1
    SEP_CELL = re.compile(r"^\s*:?-+:?\s*$")
    def is_sep_row(row):
        cells = split_cells(row)
        return cells and all(SEP_CELL.match(c) for c in cells if c.strip())

    has_sep = len(rows) > 1 and is_sep_row(rows[1])
    if not has_sep:
        sep = "| " + " | ".join("---" for _ in range(col_count)) + " |"
        rows.insert(1, sep)
        repaired = True

    if repaired:
        stats.table_repairs += 1

    return rows


# ---------------------------------------------------------------------------
# List continuation detection
# ---------------------------------------------------------------------------

def list_continuation_indent(list_line: str) -> int:
    """
    For a line starting a list item, return the minimum indent for a
    continuation line (marker indent + marker width + 1).
    Returns -1 if the line is not a list item.
    """
    m = LIST_MARKER_RE.match(list_line)
    if not m:
        return -1
    indent = len(m.group(0))   # full matched prefix length
    return indent


def is_list_continuation(prev_line: str, curr_line: str) -> bool:
    """
    True if curr_line is an indented continuation of prev_line's list item,
    or a continuation of an already-continued list body line.
    """
    # curr must start with spaces (indented)
    if not curr_line or not curr_line[0] == " ":
        return False
    # curr must not itself be a new block starter
    if is_block_starter(curr_line):
        return False

    # Case 1: prev is a list marker line
    cont_indent = list_continuation_indent(prev_line)
    if cont_indent > 0:
        curr_indent = len(curr_line) - len(curr_line.lstrip())
        return curr_indent >= cont_indent

    # Case 2: prev is itself an indented continuation (already joined)
    # Detect by: prev starts with spaces, curr starts with spaces, roughly same indent
    prev_stripped = prev_line.lstrip()
    prev_indent = len(prev_line) - len(prev_stripped)
    curr_indent = len(curr_line) - len(curr_line.lstrip())
    if prev_indent > 0 and curr_indent >= prev_indent and not is_block_starter(prev_line):
        return True

    return False


# ---------------------------------------------------------------------------
# Main normalizer
# ---------------------------------------------------------------------------

def semantic_normalize(text: str, stats: Stats) -> str:
    lines = text.splitlines()
    result: list[str] = []

    in_fence = False
    fence_char = ""
    in_front_matter = False
    front_matter_done = False

    # Table buffer: indices into result[] that form the current table block
    table_buf: list[int] = []

    def flush_table():
        nonlocal table_buf
        if not table_buf:
            return
        raw = [result[i] for i in table_buf]
        fixed = fix_table_block(raw, stats)
        for idx, new_line in zip(table_buf, fixed):
            result[idx] = new_line
        table_buf = []

    for i, raw in enumerate(lines):
        line = raw

        # ---- Front matter -------------------------------------------------
        if not front_matter_done and i == 0 and FRONT_SEP_RE.match(line):
            in_front_matter = True
            front_matter_done = True
            result.append(line)
            continue

        if in_front_matter:
            result.append(line)
            if i > 0 and FRONT_SEP_RE.match(line):
                in_front_matter = False
            continue

        # ---- Fence tracking -----------------------------------------------
        fence_match = FENCE_OPEN_RE.match(line)

        if not in_fence and fence_match:
            flush_table()
            char = fence_match.group(1)[0]
            normalized = normalize_fence_opener(line)
            if normalized != line:
                stats.fence_repairs += 1
            in_fence = True
            fence_char = char
            result.append(normalized)
            continue

        if in_fence:
            closing = re.match(rf"^{re.escape(fence_char)}{{3,}}\s*$", line)
            if closing:
                in_fence = False
                fence_char = ""
                result.append(line)
                continue
            # Auto-close at clear block boundaries (headings)
            if HEADING_RE.match(line):
                result.append(fence_char * 3)
                stats.fence_repairs += 1
                in_fence = False
                fence_char = ""
                # fall through to process this line normally
            else:
                result.append(line)
                continue

        # ---- Blank line ---------------------------------------------------
        if not line.strip():
            flush_table()
            result.append(line)
            continue

        # ---- Table detection ----------------------------------------------
        if is_table_like(line):
            result.append(line)
            table_buf.append(len(result) - 1)
            continue
        else:
            flush_table()

        # ---- Soft-wrap and list-continuation joining ---------------------
        can_join = False

        if result and result[-1].strip():
            prev = result[-1]

            if not is_block_starter(line) and not EXPLICIT_BR_RE.search(prev):
                if not is_block_starter(prev):
                    # Normal paragraph join
                    can_join = True
                elif is_list_continuation(prev, line):
                    # List item body continuation
                    can_join = True

        if can_join:
            result[-1] = result[-1].rstrip() + " " + line.lstrip()
            stats.joins += 1
        else:
            result.append(line)

    flush_table()

    # Repair unclosed fence
    if in_fence:
        result.append("```")
        stats.fence_repairs += 1

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: semantic_normalize.py <input.md> <output.md>", file=sys.stderr)
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    stats = Stats()
    normalized = semantic_normalize(text, stats)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(normalized, encoding="utf-8")

    print(f"paragraph_joins={stats.joins}")
    print(f"fence_repairs={stats.fence_repairs}")
    print(f"table_repairs={stats.table_repairs}")


if __name__ == "__main__":
    main()

# markitdown 子命令 —— 统一文档数字化主转换引擎

基于 [Microsoft markitdown](https://github.com/microsoft/markitdown) 的统一转换管线，把多种文档格式转为 Markdown。lizhu 的**主转换引擎**，覆盖原 pdf/epub 子命令的能力并扩展到 Word/PPT/Excel/HTML/CSV/JSON/XML/ZIP/YouTube 等。

## TL;DR

```
任意文档输入？
├─ 主路径：markitdown 单步转换 → 输出 .md
├─ 高质量路径：markitdown 转换 → normalize 语义修复 → 输出 .md
├─ 失败/需要精细公式 OCR → 回退 pdf(MinerU) / ocr(DeepSeek-OCR-2)
└─ 图片二维码 → qr 子命令（不归 markitdown）
```

## 功能

- **统一格式入口** — PDF / Word / PowerPoint / Excel / HTML / CSV / JSON / XML / YAML / ZIP / EPUB / 图片 / 音频 / YouTube URL 一次接入
- **结构保留** — 标题、列表、表格、链接、代码块等结构尽量保留为 Markdown
- **可选 LLM 图片描述** — 通过 OpenAI 兼容接口（含 DeepSeek-OCR-2）对图片生成文字描述
- **可选语义 normalize** — 一键接入 `md-normalizer/semantic_normalize.py`，修复段落断行、未闭合 fence、表格结构
- **URL/YouTube 支持** — 远程 URL 直接转换（视已安装的 `[youtube-transcription]` 等可选依赖）
- **显性错误** — 不支持的扩展名、文件过大、依赖缺失、API key 缺失均显式报错并终止

## 何时使用

| 触发场景                                              | 是否首选 markitdown        |
| ----------------------------------------------------- | -------------------------- |
| `.docx` / `.pptx` / `.xlsx` / `.xls` / `.msg` 文档    | **必须**（无其他子命令）   |
| `.html` / `.htm` / `.csv` / `.json` / `.xml` / `.yaml` | **首选**                   |
| `.zip`（递归转换内部文件）                            | **必须**                   |
| `.epub`（无需章节拆分）                               | **首选**（epub 子命令备选，需 TOC 拆分时用 epub） |
| `.pdf`（普通文本/简单布局）                           | **首选**（PyMuPDF 同等可用） |
| `.pdf`（论文/公式/复杂表格/扫描版）                   | **回退** pdf(MinerU 精准模式) |
| 图片（仅 EXIF 元数据）                                | markitdown                 |
| 图片（OCR 文字识别）                                  | **回退** ocr(DeepSeek-OCR-2) |
| 图片（二维码扫描）                                    | **回退** qr(zxing-cpp)      |
| YouTube URL                                           | **必须** markitdown + `[youtube-transcription]` |
| `.md`（已是 Markdown）                                | markitdown（透传/可加 normalize） |

> 🔴 **CHECKPOINT**：图片输入仍需遵守 SKILL.md 的"禁止假设图片意图"原则。同一图片既可能含二维码也可能需要 OCR，markitdown 不替代用户意图确认。

## 执行流程

### Phase 1: 输入验证

**Step 1.0** — 依赖检查(⚠️ 检查点)

```bash
python3 -c "from markitdown import MarkItDown; print('markitdown OK')" 2>/dev/null || \
  pip install --quiet --break-system-packages 'markitdown[all]'
```

- markitdown 缺失 → 提示 `pip install 'markitdown[all]'`，终止
- 仅缺可选依赖（如 `[pdf]`） → 提示具体 extras 命令，终止对应格式

**Step 1.1** — 检查输入类型

- 本地文件路径 → 验证文件存在、扩展名在 `SUPPORTED_INPUT_EXTS` 内
- URL（`http(s)://`） → 直接交给 markitdown 抓取
- 目录 → 报错终止（markitdown 处理单文件/URL，不递归目录）

**Step 1.2** — 文件大小检查(⚠️ 检查点)

- 文件 > 500MB → 报 `ConvertError`，提示分割或缩减
- URL 输入跳过此检查（由 markitdown 内部处理）

### Phase 2: 执行转换(⚠️ 检查点)

```bash
# 基础转换（输出到 stdout）
python3 scripts/markitdown-convert/main.py "<input>"

# 指定输出文件
python3 scripts/markitdown-convert/main.py "<input>" -o "<output.md>"

# 带 normalize 后处理
python3 scripts/markitdown-convert/main.py "<input>" -o "<output.md>" --normalize

# 图片走 LLM 描述（OpenAI 兼容，含 DeepSeek-OCR-2）
OPENAI_API_KEY=$DEEPSEEK_OCR_API_KEY \
  python3 scripts/markitdown-convert/main.py "<image.jpg>" \
    --llm-model deepseek-ai/deepseek-vl2 \
    --llm-base-url https://api.deepseek.com/v1 -o out.md
```

**退出码**：

| 退出码 | 含义                                  |
| ------ | ------------------------------------- |
| 0      | 成功                                  |
| 1      | 输入文件不存在 / 是目录               |
| 2      | 转换错误（不支持扩展名/依赖缺失/转换异常） |

### Phase 3: 可选 normalize 后处理(⚠️ 检查点)

`--normalize` 标志会自动调用 `scripts/md-normalizer/semantic_normalize.py`：

- 段落软换行合并
- 代码块 fence 修复
- 表格结构补齐（外侧 `|`、分隔行、列数）

输出到 stderr 的统计：

```
[Info] source_format=docx title=报告标题 chars=12345
[Info] normalize: paragraph_joins=42 fence_repairs=3 table_repairs=5
```

不指定 `--normalize` 时跳过此步，交付原始 markitdown 输出。

### Phase 4: 交付与汇报

汇报内容：

- 输入路径、源格式（扩展名）、文档标题（如能识别）
- 输出路径（或 stdout）
- 字符数
- normalize 统计（若启用）
- 警告列表（如 normalize 模块缺失但仍要求 normalize）

## 管线设计

```
input (file path | URL)
  │
  ▼
[guard] 文件存在 / 大小 / 扩展名 / 目录检查
  │
  ▼
[optional] LLM client 构建（仅 --llm-model 时）
  │
  ▼
MarkItDown.convert() → DocumentConverterResult { markdown, title }
  │
  ▼
[optional] semantic_normalize(markdown) → cleaned markdown + Stats
  │
  ▼
output (file | stdout) + 元信息到 stderr
```

## Python API

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("scripts/markitdown-convert").resolve()))
from main import convert_to_markdown, ConvertResult, ConvertError

# 基础用法
result = convert_to_markdown("input.docx", output_path="out.md")
print(result.title, result.source_format, len(result.markdown))

# 带 normalize
result = convert_to_markdown("input.html", output_path="out.md", normalize=True)
print(result.normalize_stats)  # {paragraph_joins, fence_repairs, table_repairs}

# 带 LLM 图片描述
from openai import OpenAI
client = OpenAI(api_key="...", base_url="https://api.deepseek.com/v1")
result = convert_to_markdown(
    "scan.jpg",
    llm_client=client,
    llm_model="deepseek-ai/deepseek-vl2",
)

# 错误处理
try:
    convert_to_markdown("missing.pdf")
except FileNotFoundError as e:
    print(f"输入不存在: {e}")
except ConvertError as e:
    print(f"转换失败: {e}")
```

## 异常处理

| 异常                       | 处理                                       | Fallback                  |
| -------------------------- | ------------------------------------------ | ------------------------- |
| markitdown 未安装          | 提示 `pip install 'markitdown[all]'`，退出码 2 | 无                        |
| 输入文件不存在             | 报 `FileNotFoundError`，退出码 1           | 无                        |
| 输入是目录                 | 报 `ConvertError`，退出码 2                | 无                        |
| 不支持的扩展名             | 报 `ConvertError` 列出支持的扩展名，退出码 2 | 无                        |
| 文件 > 500MB               | 报 `ConvertError`，提示分割                | 无                        |
| 可选依赖缺失（如 `[pdf]`） | markitdown 内部抛异常 → 包裹为 `ConvertError` | 安装对应 extras           |
| `OPENAI_API_KEY` 未设置    | `--llm-model` 路径下报 `ConvertError`，退出码 2 | 不使用 LLM 描述           |
| `semantic_normalize` 缺失  | 添加 warning，跳过 normalize 步骤，不报错   | md-normalizer 修复        |
| markitdown.convert() 异常  | 捕获并包裹为 `ConvertError`，含原始异常类型与消息 | 无                        |
| URL 抓取失败               | markitdown 内部异常 → `ConvertError`       | 检查网络/URL 可达性       |
| 输出目录无写权限           | 抛 `PermissionError`（来自 `Path.write_text`） | 提示用户指定其他输出目录  |

## 环境变量

| 变量                       | 默认值 | 说明                                                 |
| -------------------------- | ------ | ---------------------------------------------------- |
| `OPENAI_API_KEY`           | (无)   | LLM 图片描述用，OpenAI 兼容                          |
| `MARKITDOWN_LLM_API_KEY`   | (无)   | 同上，专用别名（优先级低于 `OPENAI_API_KEY`）        |
| `MARKITDOWN_LLM_MODEL`     | (无)   | 默认 LLM 模型名（可被 `--llm-model` 覆盖）           |
| `MARKITDOWN_LLM_BASE_URL`  | (无)   | 默认 LLM base URL（可被 `--llm-base-url` 覆盖）      |

> 🔴 **禁止硬编码 API KEY** —— 必须通过环境变量传入，缺失时显式报错（同 SKILL.md 反例黑名单 #1）。

## 命令参数

| 参数             | 说明                                                       |
| ---------------- | ---------------------------------------------------------- |
| `input`          | 输入文件路径或 URL（必需，除非用 `--list-formats`）        |
| `-o, --output`   | 输出 Markdown 路径（不指定则输出到 stdout）                |
| `--normalize`    | 调用 md-normalizer 做语义格式优化                          |
| `--llm-model`    | LLM 模型名（用于图片描述，如 `gpt-4o`、`deepseek-vl2`）   |
| `--llm-base-url` | LLM API base URL（OpenAI 兼容端点）                        |
| `--llm-prompt`   | 自定义 LLM 图片描述 prompt                                 |
| `--list-formats` | 列出支持的输入格式并退出                                   |
| `--json`         | 以 JSON 输出结果元信息（markdown 不打印到 stdout）         |

## 使用示例

```bash
# 列出支持的格式
python3 scripts/markitdown-convert/main.py --list-formats

# Word 转 Markdown
python3 scripts/markitdown-convert/main.py "report.docx" -o "report.md"

# PPT 转 Markdown + normalize
python3 scripts/markitdown-convert/main.py "slides.pptx" -o "slides.md" --normalize

# Excel 转 Markdown
python3 scripts/markitdown-convert/main.py "data.xlsx" -o "data.md"

# HTML 转 Markdown（stdout）
python3 scripts/markitdown-convert/main.py "page.html" > page.md

# JSON 转 Markdown（输出元信息 JSON）
python3 scripts/markitdown-convert/main.py "config.json" --json

# EPUB 单文件转换（不拆章节）
python3 scripts/markitdown-convert/main.py "book.epub" -o "book.md"

# PDF 简单转换（PyMuPDF 失败时 fallback 用此命令）
python3 scripts/markitdown-convert/main.py "paper.pdf" -o "paper.md"

# 图片走 LLM 描述（DeepSeek-OCR-2）
OPENAI_API_KEY=$DEEPSEEK_OCR_API_KEY \
  python3 scripts/markitdown-convert/main.py "diagram.jpg" \
    --llm-model deepseek-ai/deepseek-vl2 \
    --llm-base-url https://api.deepseek.com/v1 \
    -o "diagram.md"

# YouTube 字幕（需 pip install 'markitdown[youtube-transcription]'）
python3 scripts/markitdown-convert/main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -o "video.md"
```

## 与其他子命令的关系

| 子命令     | markitdown 关系                                                  |
| ---------- | ---------------------------------------------------------------- |
| `pdf`      | markitdown 主路径用于简单 PDF；MinerU 精准模式仍处理论文/公式/扫描版 |
| `epub`     | markitdown 单文件输出；epub 子命令用于按 TOC 拆分章节             |
| `ocr`      | markitdown 不做 OCR 文字识别；图片文字识别仍走 ocr(DeepSeek-OCR-2) |
| `qr`       | markitdown 不识别二维码；二维码仍走 qr(zxing-cpp)                |
| `normalize`| markitdown `--normalize` 标志内嵌调用；也可独立对任意 .md 调用    |

## 反例黑名单

- **禁止**在 markitdown 转换失败后吞掉异常继续输出空 Markdown —— 必须报 `ConvertError` 并退出码 2
- **禁止**硬编码 API KEY —— `OPENAI_API_KEY` / `MARKITDOWN_LLM_API_KEY` 必须从环境变量读
- **禁止**对图片输入跳过用户意图确认 —— 同 SKILL.md 反例 #2，markitdown 不替代 qr/ocr 的意图路由
- **禁止**对扫描版 PDF 强行用 markitdown —— 公式/复杂表格场景应回退 pdf(MinerU 精准模式)
- **禁止**用 markitdown 处理目录 —— 仅文件/URL，目录递归请用其他工具
- **禁止**把 markitdown `--normalize` 与 normalize 子命令同时叠加使用 —— 二选一，避免重复语义修复

## Sources

- [microsoft/markitdown](https://github.com/microsoft/markitdown) — Microsoft 开源文档转 Markdown 工具
- [markitdown PyPI](https://pypi.org/project/markitdown/) — 包页面与可选依赖说明

# Lizhu (离朱) —— 统一文档数字化技能

[![GitHub Release](https://img.shields.io/github/v/release/Kirky-X/lizhu?style=flat-square)](https://github.com/Kirky-X/lizhu/releases)
[![GitHub License](https://img.shields.io/github/license/Kirky-X/lizhu?style=flat-square)](LICENSE)

lizhu 是一个面向 AI agent 的统一文档数字化 skill，以 [Microsoft markitdown](https://github.com/microsoft/markitdown) 为主转换引擎，覆盖 PDF/Word/PPT/Excel/HTML/CSV/JSON/XML/ZIP/EPUB/图片/音频/URL 等格式，输出格式化 Markdown。六类子命令构成完整管线：`markitdown`(主引擎) → `qr`/`ocr`/`pdf`/`epub`(专用路径) → `normalize`(后处理)。

核心原则：**主路径优先**——能走 markitdown 的格式一律走 markitdown；论文/公式/扫描版 PDF、二维码、OCR 文字识别、章节拆分 EPUB 才走各自的专用子命令。完整路由表与流程文档见 [SKILL.md](SKILL.md)。

## 安装

### 方式一：通过 `skills` 包安装（推荐）

需 [Node.js](https://nodejs.org/) 18+ 和 `skills` npm 包(v1.5.12+)。`skills` 是 open agent skills 生态的 CLI，支持 68+ agents(Claude Code / Trae / Cursor / Codex / OpenCode 等)。

```bash
# 安装到 Claude Code
npx skills add Kirky-X/lizhu --agent claude-code -y

# 安装到 Trae
npx skills add Kirky-X/lizhu --agent trae -y

# 列出仓库中可被发现的所有 skills（不安装）
npx skills add https://github.com/Kirky-X/lizhu.git --list
```

### 方式二：传统 git clone

```bash
git clone https://github.com/Kirky-X/lizhu.git
# 将 SKILL.md + references/ + scripts/ 复制到 agent skills 目录
#   Claude Code:  ~/.claude/skills/lizhu/
#   Trae:         ~/.trae-cn/skills/lizhu/
```

## 子命令

| 子命令     | 一句话功能                                         | 输入格式                |
| ---------- | -------------------------------------------------- | ----------------------- |
| markitdown | 主转换引擎，多格式转 Markdown                      | PDF/Word/PPT/Excel/HTML/CSV/JSON/XML/ZIP/EPUB/图片/音频/URL |
| qr         | 从图片提取二维码内容（zxing-cpp，93.3% 正确率）   | 图片                    |
| ocr        | 多模态 OCR 识别图像文字/数学题/表格（DeepSeek-OCR-2） | 图片                    |
| pdf        | PDF 智能解析（PyMuPDF 轻量 / MinerU 精准）         | PDF（论文/公式/扫描版） |
| epub       | EPUB 按 TOC 拆章节转 Markdown                      | EPUB                    |
| normalize  | Markdown 语义修复 + 格式规范化（mdformat）         | .md 文件                |

## 依赖矩阵

| 子命令     | Python 库                                           | 环境变量                                 |
| ---------- | --------------------------------------------------- | ---------------------------------------- |
| markitdown | `markitdown[all]` / `openai`(LLM 描述)             | `OPENAI_API_KEY`（仅 --llm-model 时必需）|
| qr         | `pillow`, `zxing-cpp`                               | 无                                       |
| ocr        | `openai`                                            | `DEEPSEEK_OCR_API_KEY`（必需）           |
| pdf        | `PyMuPDF`, `requests`                               | `MINERU_API_KEY`（仅 MinerU 模式必需）   |
| epub       | `ebooklib`, `beautifulsoup4`, `markdownify`, `lxml` | 无                                       |
| normalize  | `mdformat`, `mdformat-gfm`, `mdformat-frontmatter`  | 无                                       |

统一安装：

```bash
pip install 'markitdown[all]' openai pillow zxing-cpp pymupdf requests ebooklib beautifulsoup4 markdownify lxml mdformat mdformat-gfm mdformat-frontmatter
```

## 文件结构

```
lizhu/
├── SKILL.md                              # 入口路由
├── references/commands/
│   ├── markitdown.md                     # 主转换引擎子命令
│   ├── qr.md                             # 二维码扫描子命令
│   ├── ocr.md                            # OCR 子命令
│   ├── pdf.md                            # PDF 解析子命令
│   ├── epub.md                           # EPUB 转 Markdown 子命令
│   └── normalize.md                      # Markdown 格式标准化子命令
└── scripts/
    ├── markitdown-convert/main.py        # markitdown 包装脚本
    ├── qr-scanner/main.py                # zxing-cpp 扫码脚本
    ├── ocr/main.py                       # DeepSeek-OCR-2 调用脚本
    ├── pdf-parse/
    │   ├── main.py                       # 智能模式选择
    │   ├── mineru_batch.py               # 大 PDF 分块批处理
    │   └── fix_mineru_hierarchy.py       # MinerU 输出层级修复
    ├── epub-to-markdown/convert.py       # EPUB → Markdown 转换
    └── md-normalizer/semantic_normalize.py  # 语义修复
```

## 完整流程链路

```
用户请求
  ├─ 输入识别（文件扩展名 / URL / 图片+意图）
  ├─ 主路径优先 → markitdown（多格式）
  ├─ 专用路径 → qr / ocr / pdf / epub
  ├─ 执行子命令
  └─ 可选后处理 → normalize
```

## Sources

- [microsoft/markitdown](https://github.com/microsoft/markitdown) — 主转换引擎
- [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) — 二维码解码库
- [DeepSeek-OCR-2](https://www.aiping.cn/) — 多模态 OCR API
- [MinerU](https://github.com/opendatalab/MinerU) — PDF 精准解析
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF 轻量解析
- [mdformat](https://mdformat.readthedocs.io/) — Markdown 格式规范化

## 许可证

MIT

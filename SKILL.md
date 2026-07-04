---
name: lizhu
description: "统一文档数字化工具。输入图片(OCR)/PDF/EPUB/二维码，输出格式化 Markdown。触发词：数字化文档、图片转文字、PDF转Markdown、EPUB转换、扫描二维码、OCR、识别二维码、parse PDF、convert epub、提取文字"
license: MIT
---

# lizhu (栗子) —— 统一文档数字化技能

四个子命令覆盖四种输入到 Markdown 的转换：`qr`(图片→二维码文本)、`ocr`(图片→文字/问答)、`pdf`(PDF→Markdown+图片)、`epub`(EPUB→章节化 Markdown 文件夹)。

- **qr**(图片输入)— 用 `zxing-cpp`(93.3% 正确率)从图片提取二维码内容(URL/文本)，支持批量扫描。解决"**图片里的二维码是什么**"。
- **ocr**(图片输入)— 用 `DeepSeek-OCR-2` 多模态模型识别图像文字、解答数学题、提取表格。解决"**图片里的文字/内容是什么**"。
- **pdf**(PDF 输入)— 智能选择 PyMuPDF 轻量模式(文本+图片+超链接)或 MinerU API 精准模式(公式+表格+OCR)。解决"**PDF 怎么转成 Markdown**"。
- **epub**(EPUB 输入)— 按 TOC 拆分章节、提取图片、生成 SUMMARY.md 目录。解决"**EPUB 怎么转成 Markdown**"。

## 子命令路由

> 🔴 **CHECKPOINT**:同一张图片既可能含二维码也可能需要 OCR —— 必须先确认用户意图(扫码 vs 识文字)，不得擅自选择子命令。若用户意图模糊，先提问澄清。

| 用户输入                              | 子命令 | 完整流程                                                       |
| ------------------------------------- | ------ | -------------------------------------------------------------- |
| 图片 + "扫描二维码/QR/扫码" 意图      | qr     | [`references/commands/qr.md`](references/commands/qr.md)       |
| 图片 + "识别文字/OCR/提取文字" 意图   | ocr    | [`references/commands/ocr.md`](references/commands/ocr.md)     |
| `.pdf` 文件                           | pdf    | [`references/commands/pdf.md`](references/commands/pdf.md)     |
| `.epub` 文件                          | epub   | [`references/commands/epub.md`](references/commands/epub.md)   |
| 图片 + 意图不明                       | 提问   | 询问"扫码还是识文字"，不得擅自选择                              |
| 不支持的扩展名(.docx/.pptx 等除外)    | 报错   | 列出支持的输入：图片/PDF/EPUB                                   |

> 🔴 标记的行需用户显式确认意图；图片输入时禁止假设用户想要 qr 或 ocr 中的某一个。

进入子命令后，按其流程文档执行。检查点、依赖安装、错误处理均在各子命令文档内 —— **本路由器不含流程主体**。

## 通用工作流

```
用户请求
  ├─ Phase 1: 输入识别
  │   ├─ 文件扩展名 → 直接路由(.pdf → pdf, .epub → epub)
  │   └─ 图片 + 用户意图 → 路由(qr 或 ocr)
  ├─ Phase 2: 依赖检查(⚠️ 检查点)
  │   ├─ Python 库缺失 → 提示安装命令，终止
  │   └─ API KEY 缺失(ocr/pdf mineru 模式) → 提示环境变量，终止
  ├─ Phase 3: 执行子命令(⚠️ 检查点)
  │   └─ 调用 scripts/<子模块>/main.py
  └─ Phase 4: 输出 Markdown
      ├─ qr   → 文本/URL + Markdown 链接
      ├─ ocr  → 流式输出 reasoning + content
      ├─ pdf  → output.md + images/
      └─ epub → SUMMARY.md + NN_章节.md + images/
```

## 依赖矩阵

| 子命令 | Python 库                                  | 环境变量                              | 系统依赖 |
| ------ | ------------------------------------------ | ------------------------------------- | -------- |
| qr     | `pillow`, `zxing-cpp`                      | 无                                    | 无       |
| ocr    | `openai`                                   | `DEEPSEEK_OCR_API_KEY` (必需)         | 无       |
| pdf    | `PyMuPDF`, `requests`                      | `MINERU_API_KEY` (仅 MinerU 模式必需) | 无       |
| epub   | `ebooklib`, `beautifulsoup4`, `markdownify`, `lxml` | 无                                    | 无       |

**统一安装**：

```bash
pip install pillow zxing-cpp openai pymupdf requests ebooklib beautifulsoup4 markdownify lxml
```

## 失败模式与 fallback

| 触发条件                          | 一线修复                                      | 仍失败兜底                                |
| --------------------------------- | --------------------------------------------- | ----------------------------------------- |
| 图片输入但意图不明(qr vs ocr)     | 询问用户"扫码还是识文字"                       | 用户拒绝澄清 → 终止，不得擅自选择          |
| Python 库缺失                     | 提示 `pip install <package>`，终止             | 无                                        |
| `DEEPSEEK_OCR_API_KEY` 未设置     | 提示 `export DEEPSEEK_OCR_API_KEY=...`，终止   | 无(禁止硬编码回退到默认 key)              |
| `MINERU_API_KEY` 未设置           | 提示 `export MINERU_API_KEY=...`，降级到 PyMuPDF 轻量模式 | 用户确认无 key → 仅用 `--mode light`      |
| MinerU API 超时(>60s)             | 建议分批处理或减小文件                         | 降级到 PyMuPDF 轻量模式                   |
| PyMuPDF 提取失败(扫描版 PDF)      | 自动切换 MinerU OCR 模式                       | 报错并展示具体异常                        |
| EPUB 无 TOC                       | 回退到 h1/h2 标题拆分                          | 章节命名为 `章节 N`，提示用户手动重命名    |
| 二维码未检测到                    | 提示可能原因(模糊/太小/无二维码)               | 建议 OCR fallback 识文字                  |
| 文件 > 子命令阈值(qr 10MB / ocr 5MB / pdf 200MB / epub 500MB) | 提示大文件，等待用户确认继续或压缩 | 用户拒绝 → 终止                           |

## 禁止事项(反例黑名单)

1. **禁止硬编码 API KEY** — 所有密钥必须通过环境变量传入(`DEEPSEEK_OCR_API_KEY`、`MINERU_API_KEY`)，严禁在脚本或文档中写入具体 key 字符串；缺失时显式报错并终止。
2. **禁止假设图片意图** — 同一图片可能含二维码也可能需要 OCR；用户未明确表态时必须提问，不得擅自选择 qr 或 ocr。
3. **禁止跳过依赖检查** — Python 库缺失时不得"尝试运行看看"，必须先检查并提示安装命令。
4. **禁止吞掉错误** — 子命令失败时必须显式展示异常类型与消息；批量处理(qr --batch、mineru_batch)跳过的文件必须在最终输出中列出文件名与跳过原因，不得仅在日志中埋没。
5. **禁止在路由器内写流程主体** — 本文件是路由器，子命令的执行流程、检查点、参数说明必须放在 `references/commands/*.md`。
6. **禁止硬编码绝对路径** — 脚本中的输入/输出路径必须来自 CLI 参数或环境变量，严禁写入 `/home/xxx` 等具体路径。

## 文件结构

```
lizhu/
├── SKILL.md                              # 本文件(路由器)
├── references/commands/
│   ├── qr.md                             # 二维码扫描子命令
│   ├── ocr.md                            # OCR 子命令
│   ├── pdf.md                            # PDF 解析子命令
│   └── epub.md                           # EPUB 转 Markdown 子命令
└── scripts/
    ├── qr-scanner/main.py                # zxing-cpp 扫码脚本
    ├── ocr/main.py                       # DeepSeek-OCR-2 调用脚本
    ├── pdf-parse/
    │   ├── main.py                       # 智能模式选择(auto/light/mineru-*)
    │   ├── mineru_batch.py               # 大 PDF 分块批处理
    │   └── fix_mineru_hierarchy.py       # MinerU 输出层级修复
    └── epub-to-markdown/convert.py       # EPUB → Markdown 转换
```

## Sources

- [zxing-cpp](https://github.com/zxing-cpp/zxing-cpp) — 二维码解码库
- [DeepSeek-OCR-2](https://www.aiping.cn/) — 多模态 OCR API
- [MinerU](https://github.com/opendatalab/MinerU) — PDF 精准解析
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF 轻量解析
- [ebooklib](https://docs.sourcefabric.org/projects/ebooklib/) — EPUB 解析
- [markdownify](https://pypi.org/project/markdownify/) — HTML→Markdown

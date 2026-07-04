# pdf 子命令 —— PDF 智能解析

根据文档复杂度自动选择 PyMuPDF 轻量模式或 MinerU API 精准模式。

## TL;DR

```
PDF文件？
├─ 简单文本PDF → PyMuPDF 快速提取(文本+图片+超链接)
├─ 论文/图表/公式 → MinerU API 精准解析
│   ├─ 轻量模式 → enable_formula=False, enable_table=True
│   └─ 精准模式 → enable_formula=True, enable_table=True, is_ocr=True
└─ 扫描版PDF → MinerU OCR 模式
```

## 功能

- **轻量文本提取** — PyMuPDF 快速解析纯文本 PDF
- **图片提取** — 提取并保存图片(PNG/JPG)
- **超链接保留** — 提取超链接并保留为 Markdown 格式
- **精准结构解析** — MinerU API 处理论文/图表/公式
- **公式识别** — LaTeX 格式输出
- **表格识别** — HTML/Markdown 格式输出
- **OCR 支持** — 扫描版 PDF、109 语言识别
- **大文件批处理** — `mineru_batch.py` 自动分块(>200 页)

## 执行流程

### Phase 1: 输入验证

**Step 1.0** — 依赖检查(⚠️ 检查点)

```bash
python3 -c "import fitz; print('PyMuPDF OK')" 2>/dev/null || echo "pip install pymupdf"
python3 -c "import requests; print('requests OK')" 2>/dev/null || echo "pip install requests"
```

**Step 1.1** — 检查文件类型

支持格式：PDF、图片(PNG/JPG/JPEG/WEBP)、DOCX、PPTX、XLSX

**Step 1.2** — 文件大小检查(⚠️ 检查点)

- 文件 > 200MB → **暂停并提示**「文件过大，建议分批处理」
- 用户确认「继续」→ 执行(可能超时)
- 用户确认「分割」→ 建议使用 `pdftk` 或 `qpdf` 分割
- 用户拒绝 → 终止

**Step 1.3** — 页数检查(仅 PDF)

- 页数 > 600 → 提示「超出 API 限制，建议分批处理」

### Phase 2: 文档类型检测(auto 模式)

**Step 2.1** — 快速预扫描(PyMuPDF 前 3 页)

统计图片数量、超链接数量、文本长度，检测公式特征(`\frac`、`\sum`、`\int` 等 LaTeX 残留)。

**Step 2.2** — 类型判断

| 检测条件             | 文档类型      | 解析方案        |
| -------------------- | ------------- | --------------- |
| 有图片 + 有公式特征  | 论文/学术文档 | MinerU 精准模式 |
| 有表格 + 复杂布局    | 图表文档      | MinerU 精准模式 |
| 无图片/表格 + 纯文本 | 简单 PDF      | PyMuPDF 轻量模式 |
| PyMuPDF 提取失败     | 扫描版 PDF    | MinerU OCR 模式 |
| 手写/低质量扫描      | 特殊文档      | MinerU OCR 模式 |

### Phase 3: 执行解析(⚠️ 检查点)

#### 轻量模式(PyMuPDF)

```bash
python3 scripts/pdf-parse/main.py <pdf_path> --mode light
```

适用：纯文本 PDF、简单布局、包含图片和超链接、无复杂公式。

⚠️ **图片提取目录确认**：
- 默认图片目录：`<输出目录>/images/`
- 若输出目录不存在 → 自动创建
- 若用户无写入权限 → 提示指定其他目录
- 用户可用 `--no-images` 跳过图片提取

#### MinerU 轻量 API

```bash
python3 scripts/pdf-parse/main.py <pdf_path> --mode mineru-light
```

参数：`enable_formula=False`、`enable_table=True`、`is_ocr=False`、`model_version=pipeline`

适用：有表格但无复杂公式、正常印刷质量。

#### MinerU 精准 API

```bash
python3 scripts/pdf-parse/main.py <pdf_path> --mode mineru-precision
```

参数：`enable_formula=True`、`enable_table=True`、`is_ocr=True`、`model_version=vlm`

适用：学术论文、数学公式密集、复杂图表、扫描文档。

#### 自动模式(推荐)

```bash
python3 scripts/pdf-parse/main.py <pdf_path> --mode auto
```

⚠️ **检测结果确认**：显示检测到的文档类型与推荐模式，用户可手动指定其他模式。

#### 大 PDF 批处理(>200 页)

```bash
python3 scripts/pdf-parse/mineru_batch.py <pdf_path_or_dir> [output_dir]
```

自动分块(每块 ≤200 页)上传 MinerU，下载结果合并为单一 Markdown，图片重命名加 `chunkNN_` 前缀避免冲突。

### Phase 4: 结果输出

| 场景     | 输出格式            | 附加输出                  |
| -------- | ------------------- | ------------------------- |
| 纯文本   | Markdown            | 无                        |
| 有图片   | Markdown + 图片引用 | `images/` 目录(PNG/JPG)   |
| 有超链接 | Markdown + 链接列表 | 无                        |
| 有公式   | Markdown + LaTeX    | 无                        |
| 有表格   | Markdown + HTML 表格 | 无                        |
| 多页     | 分页 Markdown       | 无                        |

**图片输出说明**(轻量模式)：
- 文件命名：`page{页码}_img{序号}.{扩展名}`
- Markdown 引用：`![Image N](images/page1_img1.png)`

**输出目录结构**：

```
<输出目录>/
├── output.md          # Markdown 主文档
└── images/            # 图片目录(轻量模式)
    ├── page1_img1.png
    └── page1_img2.jpg
```

**Step 4.2** — 结果确认(⚠️ 检查点)

- 输出是否符合预期？
- 公式是否正确转换为 LaTeX？
- 表格结构是否完整？

### Phase 5: 可选 normalize 后处理(⚠️ 检查点)

MinerU 模式输出的 Markdown 常见格式问题：段落软换行、表格列不齐、fence 未闭合。转换完成后**询问用户**：

> 转换完成。是否需要整理 Markdown 格式(normalize)？可修复段落断行、表格、代码块。

- 用户同意 → 调用 [`normalize.md`](normalize.md) 流程：`scripts/md-normalizer/semantic_normalize.py` + `mdformat`
- 用户拒绝 → 交付原始 Markdown

PyMuPDF 轻量模式输出一般较干净，normalize 为可选；MinerU 模式推荐询问。

## 异常处理

| 异常                  | 处理                               | Fallback         |
| --------------------- | ---------------------------------- | ---------------- |
| `MINERU_API_KEY` 未设置 | 提示配置环境变量，仅用轻量模式     | PyMuPDF 轻量模式 |
| 文件格式不支持        | 列出支持格式，终止                 | 无               |
| 文件损坏              | 提示文件可能损坏                   | 无               |
| 文件过大(>200MB)      | 建议分割后重试                     | 无               |
| API 连接失败          | 检查网络，重试或降级轻量模式       | PyMuPDF 轻量模式 |
| API 超时(>60s)        | 建议使用更小文件或分页处理         | 无               |
| PyMuPDF 提取失败      | 自动切换 MinerU OCR 模式           | MinerU OCR 模式  |
| 图片提取失败          | 跳过该图片，继续提取其他内容       | 继续解析         |
| 图片目录创建失败      | 提示权限问题，建议指定其他输出目录 | 用户确认后重试   |
| 超链接提取失败        | 跳过超链接，仅输出文本             | 继续解析         |
| 权限不足(读取)        | 提示文件权限或运行权限问题         | 无               |
| 权限不足(写入)        | 提示输出目录权限问题               | 用户指定其他目录 |

## 环境变量

| 变量               | 默认值                      | 说明                  |
| ------------------ | --------------------------- | --------------------- |
| `MINERU_API_KEY`   | (无)                        | MinerU API 密钥(必需) |
| `MINERU_API_URL`   | `https://mineru.net/api/v4` | API 端点              |
| `MINERU_LANGUAGE`  | `zh`                        | 主要语言              |

## 命令参数

### `main.py` 参数

| 参数          | 说明                                               | 适用模式   |
| ------------- | -------------------------------------------------- | ---------- |
| `filepath`    | 输入文件路径                                       | 全部       |
| `--mode`      | 解析模式：auto/light/mineru-light/mineru-precision | 全部       |
| `--language`  | 文档语言：zh/en/ja/ko/fr/de(默认 zh)              | MinerU API |
| `--output`    | 输出文件路径(默认 stdout)                          | 全部       |
| `--no-images` | 跳过图片提取，仅文本+超链接                        | light      |

### `mineru_batch.py` 参数

| 参数         | 说明                                |
| ------------ | ----------------------------------- |
| `input`      | PDF 文件或目录(必需)                |
| `output_dir` | 输出目录(可选，默认 `<input>/pdf-output-mineru`) |

### 辅助脚本

- `fix_mineru_hierarchy.py <input.md>` — 修复 MinerU 输出的 Markdown 标题层级(H1-H4)，从文件名提取书名提示自动归类。

## 使用示例

```bash
# 自动检测模式(推荐)
python3 scripts/pdf-parse/main.py "paper.pdf" --mode auto

# 强制轻量模式(提取文本+图片+超链接)
python3 scripts/pdf-parse/main.py "document.pdf" --mode light

# 轻量模式跳过图片
python3 scripts/pdf-parse/main.py "document.pdf" --mode light --no-images

# 强制精准模式(论文)
python3 scripts/pdf-parse/main.py "paper.pdf" --mode mineru-precision --language en

# 输出到指定文件
python3 scripts/pdf-parse/main.py "paper.pdf" --output "output.md"

# 大 PDF 批处理
python3 scripts/pdf-parse/mineru_batch.py "big_book.pdf"
python3 scripts/pdf-parse/mineru_batch.py "/path/to/pdfs/" "/path/to/output/"

# 修复标题层级
python3 scripts/pdf-parse/fix_mineru_hierarchy.py "output.md"
```

## MinerU Batch API 工作流

1. **获取预签名上传 URL** — `POST /api/v4/file-urls/batch`，返回 `batch_id` + upload URL
2. **上传文件到 OSS** — `PUT <presigned-url>`，不设置 Content-Type，直接上传二进制
3. **轮询结果** — `GET /api/v4/extract-results/batch/{batch_id}`，state: pending/running/done/failed
4. **下载结果** — zip 包含 `full.md`(主文档)、`images/`(图片)、`*.json`(结构数据)

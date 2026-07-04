# epub 子命令 —— EPUB 转 Markdown

将 EPUB 电子书转换为按章节组织的 Markdown 文件夹。

## TL;DR

```
EPUB文件？
├─ 是 → 运行转换脚本
│   ├─ 解析 EPUB 结构(TOC + Spine)
│   ├─ 提取图片到 images/
│   ├─ 按章节转换为独立 Markdown 文件(NN_章节名.md)
│   └─ 生成 SUMMARY.md 目录
└─ 否 → 报错退出
```

## 功能

- **章节拆分** — 按 TOC(NCX/NAV) 拆分
- **图片提取** — 提取到 `images/img_NNN.ext`
- **表格/层级保留** — Markdown 表格与标题层级
- **SUMMARY.md 目录** — 书名 + 作者 + 章节链接
- **完整中文支持** — 中文路径、中文章节名

## 执行流程

### Phase A: 前置检查

**Step A.0** — 依赖检查(⚠️ 检查点)

```bash
python3 -c "import ebooklib, markdownify, bs4, lxml; print('OK')" 2>/dev/null || \
  echo "pip install ebooklib beautifulsoup4 markdownify lxml"
```

**Step A.1** — 文件确认

```bash
ls -la "<epub_path>"
```

- 文件不存在 → 向用户确认路径(可能是相对路径，尝试 resolve 到绝对路径)

**Step A.2** — 路径处理

用户提供的路径可能是相对路径。需解析为绝对路径：

```bash
EPUB_PATH="$(realpath "input.epub")"
# 含中文/空格的路径示例
EPUB_PATH="$(realpath "epub/黑天鹅：如何应对不可预知的未来（升级版）.epub")"
```

bash 命令中始终使用双引号包裹路径变量：`"$EPUB_PATH"`。

**Step A.3** — 前置校验

- 文件扩展名非 `.epub` → 提醒用户确认是否为有效 EPUB
- 文件大小 > 500MB → 警告大文件，预估转换时间
- 输出目录所在磁盘空间 < EPUB 大小 × 3 → 警告可能空间不足

### 检查点：确认后执行(🔴)

向用户展示即将执行的操作，**等待确认再继续**：

```
即将转换：
- 源文件：<epub_path>(XX MB)
- 输出到：<output_dir>
- [如输出目录已存在] ⚠ 目录已存在，文件将被覆盖

请确认：继续 / 更改输出路径 / 取消
```

用户回复"继续"才进入 Phase B。用户可随时回复"取消"终止。

### Phase B: 执行转换(⚠️ 检查点)

```bash
python3 scripts/epub-to-markdown/convert.py "<epub_path>" "<output_dir>"
```

**观察输出**：脚本打印 `Images: N`、`Chapters: M`、`Summary: SUMMARY.md`、`Done!`。

**退出码**：0=成功，1=参数错误，2=EPUB 解析失败。

### Phase C: 验证输出

```bash
# 1. 确认目录结构存在
ls "<output_dir>/SUMMARY.md" "<output_dir>/images/" 2>&1

# 2. 统计产出
echo "章节数: $(ls "<output_dir>"/[0-9]*.md 2>/dev/null | wc -l)"
echo "图片数: $(ls "<output_dir>"/images/ 2>/dev/null | wc -l)"

# 3. 抽检内容质量(跳过封面/版权等前置页，取第一个正文章节)
head -20 "$(ls "<output_dir>"/[0-9]*.md 2>/dev/null | grep -v '扉页\|版权\|目录' | head -1)"

# 4. 检查无名章节数量
echo "无名章节: $(ls "<output_dir>"/[0-9]*.md 2>/dev/null | grep -c '章节_[0-9]' || echo 0)"
```

### Phase D: 报告结果

```
转换完成！
- 书名：《XXX》
- 章节数：N
- 图片数：M
- 输出路径：<output_dir>

请检查 SUMMARY.md 确认章节完整性。
```

如果发现异常(章节数为 0、大量"章节 N"无名文件、图片全部缺失)，主动告知用户并建议排查方向。

转换完成后，**询问用户是否满意**：
- 满意 → 结束
- 不满意 → 根据具体问题进入排查(见下方"常见问题")

## 输出结构

```
output_dir/
├── SUMMARY.md              # 目录文件(书名 + 作者 + 章节链接)
├── images/                 # 提取的图片
│   ├── img_001.png
│   ├── img_002.jpg
│   └── ...
├── 01_封面.md
├── 02_前言.md
├── 03_第一章_黑天鹅的不可预见性.md
└── ...
```

## 章节检测策略(优先级从高到低)

1. **EPUB TOC(NCX/NAV)** — 从目录获取章节名称和位置
2. **Spine 阅读顺序** — 按 EPUB 定义的阅读顺序组织
3. **锚点拆分** — 多章节在同一 HTML 文件时按锚点 ID 拆分
4. **标题回退** — 无 TOC 时按 h1/h2 标题拆分

**文件命名**：`NN_章节名.md`(NN=01-99 序号，章节名从 TOC/标题提取，特殊字符→下划线，≤60 字符)。

**图片处理**：提取到 `images/img_NNN.ext`，Markdown 用相对路径 `![alt](images/img_001.png)`，支持 PNG/JPG/GIF/SVG/WebP。

## 错误处理

| 场景             | 行为                                 |
| ---------------- | ------------------------------------ |
| EPUB 文件不存在  | 报 FileNotFoundError 退出            |
| 非 .epub 文件    | 提醒用户确认，非强制阻止             |
| 无 TOC           | 回退到 h1/h2 标题拆分                |
| 图片引用无法解析 | 保留原始路径                         |
| 编码错误         | 自动替换字符(errors='replace')       |
| 空 HTML 项       | 跳过不生成文件                       |
| TOC 解析异常     | 警告后继续                           |
| 磁盘空间不足     | 转换中途报错，已输出文件保留         |
| EPUB 加密/DRM    | ebooklib 抛出异常，报告用户无法转换  |
| 输出目录无写权限 | 报 PermissionError，提示检查目录权限 |

## 常见问题排查

### 章节名显示为"章节 N"

**原因**：该 HTML 文件在 EPUB 的 TOC 中没有对应条目，且文件内无 h1-h3 标题，脚本回退到序号命名。

**排查步骤**：
1. 检查原始 EPUB 是否有完整目录(用电子书阅读器打开看目录页)
2. 查看输出中 `SUMMARY.md`，确认哪些章节是无名的
3. 如需修正，直接重命名输出目录中的 `.md` 文件，并同步更新 `SUMMARY.md` 中的链接

**不建议修改脚本** —— 无名章节通常是封面、版权页、空白分隔页等非正文内容，保留为序号是合理的。

### 图片显示为断链

**排查**：
1. 检查 `images/` 目录是否有对应的 `img_NNN.ext` 文件
2. 若有图片文件但 Markdown 引用不对 → EPUB 内部路径映射异常
3. 若 `images/` 为空 → EPUB 图片项的 media_type 未被识别为图片

### 表格格式错乱

**原因**：EPUB 内的 HTML 表格结构复杂(合并单元格、嵌套表格)，markdownify 无法完美转换。

**建议**：手动修复该章节的 Markdown 文件，或将原始 HTML 表格直接保留在 Markdown 中。

### 默认输出目录

用户未指定输出目录时，脚本默认输出到 `当前工作目录/epub-output/<EPUB文件名>/`。如需指定，传入第二个参数。

## 使用示例

```bash
# 基本用法(输出到 epub-output/<书名>/)
python3 scripts/epub-to-markdown/convert.py input.epub

# 指定输出目录
python3 scripts/epub-to-markdown/convert.py input.epub /path/to/output

# 中文路径
python3 scripts/epub-to-markdown/convert.py "/home/user/黑天鹅：如何应对不可预知的未来（升级版）.epub" "/home/user/output/"
```

## 命令参数

| 参数         | 说明                                |
| ------------ | ----------------------------------- |
| `input.epub` | EPUB 文件路径(必需)                 |
| `output_dir` | 输出目录(可选，默认 `./epub-output/<书名>/`) |

## 反例黑名单

- **禁止**在用户未确认前直接覆盖已存在的输出目录
- **禁止**修改脚本以"修复"无名章节 —— 这是 EPUB 数据质量问题，非脚本缺陷
- **禁止**忽略 EPUB 加密/DRM 异常 —— 必须显式告知用户无法转换

# normalize 子命令 —— Markdown 格式标准化(可选后处理)

对 qr/ocr/pdf/epub 产出的 Markdown 做语义修复 + 格式规范化，输出干净规范的 Markdown 文件。

## TL;DR

```
任意子命令产出 Markdown？
├─ 用户要求"整理格式/规范化/clean up" → 运行 normalize
├─ pdf/epub 转换后默认询问是否 normalize
└─ 不需要 → 跳过
```

## 功能

- **段落软换行合并** — 把 MinerU/markdownify 产生的断行段落重新拼回
- **列表续行合并** — list item 的多行内容合并为一行
- **代码块修复** — 自动关闭未闭合 fence，统一 opener 反引号数量为 3
- **表格修复** — 补外侧 `|`、补分隔行、补齐列数
- **格式规范化** — mdformat 统一 ATX heading、list 缩进、空行、代码块、表格列对齐

## 何时使用

| 触发场景                                       | 是否默认调用 |
| ---------------------------------------------- | ------------ |
| pdf(MinerU 模式)输出 markdown                  | 推荐(询问)   |
| epub 输出章节 markdown                         | 推荐(询问)   |
| pdf(PyMuPDF 轻量模式)输出                      | 可选         |
| 用户主动要求"整理/规范化/clean/normalize"      | 必须         |
| qr/ocr 输出                                    | 一般不需要(输出非文件) |

## 执行流程

### Phase 1: 输入验证

**Step 1.0** — 依赖检查(⚠️ 检查点)

```bash
python3 -c "import mdformat" 2>/dev/null || \
  pip install mdformat mdformat-gfm mdformat-frontmatter --quiet --break-system-packages
```

- mdformat 缺失 → 提示安装命令；用户拒绝 → 仅执行语义修复，跳过格式规范化

**Step 1.1** — 确认输入文件

- 输入为子命令产出的 `.md` 文件路径
- 文件不存在 → 报错终止

**Step 1.2** — 确认输出路径(⚠️ 检查点)

- 默认覆盖原文件 → 询问用户确认
- 或保存为 `<stem>_normalized.md`

### Phase 2: 语义修复(⚠️ 检查点)

```bash
python3 scripts/md-normalizer/semantic_normalize.py "<input.md>" "<output.md>"
```

脚本输出到 stdout：

```
paragraph_joins=N
fence_repairs=N
table_repairs=N
```

记录这三个数字，Phase 4 汇报用。

### Phase 3: 格式规范化(mdformat)

```bash
mdformat --wrap keep "<output.md>"
```

- mdformat 失败 → 跳过本步骤，交付语义修复结果并说明
- 成功 → 进入 Phase 4

### Phase 4: 交付与汇报

汇报内容：

- 合并了 N 处段落断行
- 修复了 N 个代码块
- 修复了 N 个表格
- mdformat 格式规范化：成功/跳过(原因)

## 语义脚本行为说明

### 软换行合并规则

满足以下**全部**条件时合并两行：

- 两行之间无空行
- 当前行不以块元素起始(`#` 标题、`- / * / 1.` 列表、`>` 引用、`---` 分割线、HTML 标签、fence)
- 不在 fence 或表格内部
- 上一行末尾无 `  `(显式换行)或 `\`

**list item 续行**：缩进超过 marker 的行被认为是 item 内容续行，也参与合并。

### fence 修复

- 未关闭的 fence → 遇到下一个 heading 时自动插入关闭标记；到达 EOF 仍未关闭则在末尾插入
- opener 反引号数量不一致 → 统一为 3 个，保留语言标签

### 表格修复

- 行缺少外侧 `|` → 自动添加
- 无分隔行 → 在第 0 行后插入 `| --- | --- | ...`
- 列数不齐 → 用空单元格补齐

## 特殊情况

| 情况                          | 处理                                        |
| ----------------------------- | ------------------------------------------- |
| Front matter(`---` / `+++`)   | 完整跳过，不修改                            |
| HTML 块(`<tag>` 行)           | 透传，不处理                                |
| 脚注 / 链接定义               | 视为块级，不合并                            |
| Blockquote(`>` 行)            | 视为块边界，不跨 `>` 合并                   |
| 非 UTF-8 文件                 | 捕获 `UnicodeDecodeError`，提示用户指定编码 |
| mdformat 安装失败             | 只交付语义修复结果，说明 mdformat 跳过      |

## 异常处理

| 异常               | 处理                                          |
| ------------------ | --------------------------------------------- |
| 输入文件不存在     | 报错终止                                      |
| 输入非 .md 文件    | 提醒用户确认                                  |
| 脚本执行失败       | 显示异常类型与消息，不修改原文件              |
| mdformat 执行失败  | 保留语义修复结果，跳过格式规范化并说明        |
| 输出目录无写权限   | 报 PermissionError，提示检查目录权限          |

## 命令参数

| 参数     | 说明                           |
| -------- | ------------------------------ |
| `input`  | 输入 .md 文件路径(必需)        |
| `output` | 输出 .md 文件路径(必需)        |

## 使用示例

```bash
# 整理 MinerU 输出的 markdown
python3 scripts/md-normalizer/semantic_normalize.py "output.md" "output_normalized.md"

# 整理后用 mdformat 规范化
mdformat --wrap keep "output_normalized.md"

# 整理 epub 某章节
python3 scripts/md-normalizer/semantic_normalize.py "03_第一章.md" "03_第一章.md"
```

## 反例黑名单

- **禁止**在用户未确认前覆盖原文件 —— 默认输出到 `<stem>_normalized.md`，用户明确同意才覆盖
- **禁止**对 qr/ocr 的 stdout 流式输出做 normalize —— 它们不是文件，normalize 仅适用于文件
- **禁止**吞掉 mdformat 失败 —— 必须显式告知用户"格式规范化跳过，仅完成语义修复"

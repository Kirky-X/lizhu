# ocr 子命令 —— 图像 OCR 识别

使用 `DeepSeek-OCR-2` 多模态模型进行图像文字识别与问答。

## TL;DR

```
图片输入 + 识文字意图
├─ 本地文件 → python3 scripts/ocr/main.py <路径> "<提问>"
└─ URL → python3 scripts/ocr/main.py <URL> "<提问>"
```

**提问示例**：

- `识别所有文字`
- `这道数学题怎么解？请给出详细步骤`
- `提取表格数据，输出 CSV 格式`
- `识别图中英文并翻译成中文`

## 功能

- **图像文字识别** — 提取图像中的文本内容
- **图像问答** — 对图像内容进行分析和解答
- **数学题解析** — 数学题目识别和解答过程
- **表格识别** — 表格结构提取

## 执行流程

### Phase 1: 输入验证

**Step 1.0** — 依赖检查(⚠️ 检查点)

```bash
python3 -c "from openai import OpenAI; print('openai OK')" 2>/dev/null || echo "pip install openai"
```

**Step 1.1** — API KEY 检查(⚠️ 检查点，🔴 强制)

```bash
test -n "$DEEPSEEK_OCR_API_KEY" && echo "KEY OK" || echo "export DEEPSEEK_OCR_API_KEY='your-key'"
```

- `DEEPSEEK_OCR_API_KEY` 未设置 → 提示 export 命令，**终止**(禁止硬编码回退)
- 用户拒绝设置 → 终止，建议改用 qr 子命令(若图片是二维码)

**Step 1.2** — 检查输入类型

- 输入为 URL → 直接使用
- 输入为本地路径 → 验证文件存在

**Step 1.3** — 大文件检查(⚠️ 检查点)

- 文件 > 5MB → 提示「大图像建议先压缩」
- 等待用户确认继续或压缩后再执行

**Step 1.4** — 格式验证

支持格式：PNG、JPG、JPEG、WEBP、GIF

### Phase 2: 执行识别(⚠️ 检查点 — 调用外部 API)

```bash
python3 scripts/ocr/main.py <image_path_or_url> "<question>"
```

流式输出：`reasoning_content`(思考过程) → `content`(最终结果)

### Phase 3: 结果输出

**Step 3.1** — 流式接收

- `reasoning_content` → 模型思考过程(可选显示)
- `content` → 最终识别结果

**Step 3.2** — 格式化输出(按用户需求)

| 场景   | 输出格式                 |
| ------ | ------------------------ |
| 纯文本 | 【识别结果】文本内容     |
| 数学题 | 【题目】【解答】【答案】 |
| 表格   | Markdown 表格 + CSV      |

**Step 3.3** — 结果确认(⚠️ 检查点)

- 输出是否符合预期？
- 不符 → 调整 prompt 重新执行

## 异常处理

| 异常             | 处理                                  |
| ---------------- | ------------------------------------- |
| 文件不存在       | 提示路径错误，终止                    |
| 文件格式不支持   | 列出支持格式，终止                    |
| 图像损坏         | 提示文件可能损坏                      |
| 文件过大(>5MB)   | 建议压缩后重试                        |
| API KEY 未设置   | 提示 export 命令，终止(禁止硬编码)    |
| API 连接失败     | 提示网络问题，重试                    |
| API 超时(>30s)   | 检查网络或换小图                      |
| API 返回错误     | 显示错误码与消息，分析原因            |
| 输出格式不符预期 | 调整 prompt 或指定输出模板            |

## 环境变量

| 变量                       | 默认值                          | 说明          |
| -------------------------- | ------------------------------- | ------------- |
| `DEEPSEEK_OCR_API_KEY`     | (无，必需)                      | API 认证密钥  |
| `DEEPSEEK_OCR_API_URL`     | `https://www.aiping.cn/api/v1`  | API 端点      |
| `DEEPSEEK_OCR_MODEL`       | `DeepSeek-OCR-2`                | 模型名称      |

## 使用示例

```bash
# 识别图片中所有文字
python3 scripts/ocr/main.py "screenshot.png" "识别所有文字"

# 解数学题
python3 scripts/ocr/main.py "math.png" "这道题怎么解？给出步骤"

# 提取表格为 CSV
python3 scripts/ocr/main.py "table.png" "提取表格数据，输出 CSV"

# 识别 URL 图片
python3 scripts/ocr/main.py "https://example.com/image.png" "识别文字"

# 翻译英文图片
python3 scripts/ocr/main.py "english.png" "识别英文并翻译成中文"
```

## 反例黑名单

- **禁止**在脚本或文档中写入具体 API KEY 字符串
- **禁止**在 KEY 缺失时使用默认 KEY 继续运行
- **禁止**将图片 base64 内容打印到日志(可能泄露内容)

# qr 子命令 —— 二维码扫描

从图片中提取二维码内容(URL/文本)，支持批量扫描。

## TL;DR

```
图片输入 + 扫码意图
├─ 单图 → python3 scripts/qr-scanner/main.py <图片>
├─ 目录 → python3 scripts/qr-scanner/main.py --batch <目录>
└─ 无二维码 → 提示「未检测到二维码」
```

## 功能

- **二维码识别** — `zxing-cpp` 解码 QRCode(93.3% 正确率)
- **多码支持** — 同一图片中的多个二维码全部提取
- **URL 识别** — 自动检测 URL 并生成 Markdown 链接
- **批量扫描** — 扫描目录下所有图片

## 执行流程

### Phase 1: 输入验证

**Step 1.0** — 依赖检查(⚠️ 检查点)

```bash
python3 -c "import PIL; print('Pillow OK')" 2>/dev/null || echo "pip install pillow"
python3 -c "from zxingcpp import read_barcodes; print('zxing-cpp OK')" 2>/dev/null || echo "pip install zxing-cpp"
```

- Pillow 缺失 → 提示安装命令，终止
- zxing-cpp 缺失 → 提示安装命令，终止

**Step 1.1** — 检查输入类型

- 本地图片路径 → 验证文件存在
- 图片目录(配合 `--batch`) → 扫描目录下所有支持格式

**Step 1.2** — 格式验证

支持格式：PNG、JPG、JPEG、WEBP、GIF、BMP

**Step 1.3** — 大文件检查(⚠️ 检查点)

- 文件 > 10MB → 提示「大图像建议先压缩」
- 等待用户确认：「继续」/「压缩后重试」
- 用户拒绝 → 终止流程

### Phase 2: 执行扫描(⚠️ 检查点)

```bash
python3 scripts/qr-scanner/main.py <image_path>
```

### Phase 3: 结果输出

| 场景       | 输出格式                    |
| ---------- | --------------------------- |
| 单个二维码 | 【QR Code】Link/Text + 内容 |
| 多个二维码 | 【QR Code 1】【QR Code 2】  |
| URL 内容   | URL + Markdown 链接         |
| 纯文本     | 【QR Code】Text: 内容       |
| 无二维码   | 「未检测到二维码」+ 可能原因 |

**输出示例**：

```
[Info] Scanning: qrcode.png
【QR Code】Link: https://example.com/path
  Markdown: [https://example.com/path](https://example.com/path)
```

**JSON 输出**：`--format json` 返回 `{success, count, file, results: [{type, content, is_url, rect}]}`

## 异常处理

| 异常             | 处理                            |
| ---------------- | ------------------------------- |
| 文件不存在       | 提示路径错误，终止              |
| 文件格式不支持   | 列出支持格式，终止              |
| 未检测到二维码   | 提示可能原因(模糊、太小)        |
| 图像损坏         | 提示文件可能损坏                |
| zxing-cpp 未安装 | 提示安装命令                    |
| 解码失败         | 提示尝试清晰图片或 OCR fallback |

## 命令参数

| 参数       | 说明                         |
| ---------- | ---------------------------- |
| `input`    | 图片路径或目录(配合 --batch) |
| `--batch`  | 批量扫描目录下所有图片       |
| `--format` | 输出格式：text(默认)/ json   |
| `--output` | 输出文件路径(可选)           |

## 使用示例

```bash
# 扫描单个图片
python3 scripts/qr-scanner/main.py "qrcode.png"

# 批量扫描目录
python3 scripts/qr-scanner/main.py --batch "images/"

# JSON 输出
python3 scripts/qr-scanner/main.py "qrcode.png" --format json

# 输出到文件
python3 scripts/qr-scanner/main.py "qrcode.png" --output result.txt
```

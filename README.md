# PasteReader

截图 OCR 识别与翻译工具。后台监听剪贴板，截图后自动弹出悬浮窗展示识别文字，支持多语言翻译。

## 功能

- 剪贴板监听，截图后自动触发 OCR 识别
- 离线 OCR 引擎（[RapidOCR](https://github.com/RapidAI/RapidOCR) + ONNX Runtime），无需联网
- 基于坐标的排版还原，保留原文的行结构、缩进和段落间距
- 手动触发翻译，支持 15 种目标语言，自动检测源语言
- 全局快捷键 Ctrl+Shift+Q 随时开关 OCR 功能，程序保持后台运行
- 暗色悬浮窗，跟随鼠标弹出，失焦自动隐藏
- 一键复制原文或翻译结果

## 安装

```bash
git clone https://github.com/moabgin/PasteReader.git
cd PasteReader
pip install -r requirements.txt
```

## 使用

```bash
python pastereader.py
```

启动后程序在后台运行，OCR 功能默认开启。使用任意截图工具截图后，悬浮窗会自动出现在鼠标旁边。

### 工作流程

1. 截图（Snipaste、微信、QQ、系统截图等），图片自动复制到剪贴板
2. 悬浮窗弹出，显示排版还原后的 OCR 原文
3. 在下拉框中选择目标语言（默认简体中文），点击「翻译」
4. 点击「复制原文」或「复制翻译」将内容复制到剪贴板
5. 点击窗口外部或右上角关闭按钮隐藏悬浮窗

### 快捷键

| 快捷键 | 功能 |
| --- | --- |
| Ctrl+Shift+Q | 开启 / 关闭 OCR 识别（屏幕底部显示状态提示） |

### 推荐截图工具

| 工具 | 截图快捷键 |
| --- | --- |
| Snipaste | F1 |
| 微信 | Alt+A |
| QQ | Ctrl+Alt+A |
| Windows 系统截图 | Win+Shift+S |

## 依赖

| 包 | 用途 |
| --- | --- |
| PyQt6 | GUI 界面与悬浮窗 |
| Pillow | 剪贴板图像读取 |
| rapidocr-onnxruntime | 离线 OCR 识别 |
| requests | Google 翻译 API |
| keyboard | 全局热键监听 |

## 项目结构

```
PasteReader/
├── pastereader.py      # 主程序
├── requirements.txt    # Python 依赖
└── README.md
```

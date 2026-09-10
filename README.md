# PasteReader

截图 OCR 识别与翻译工具。后台监听剪贴板，截图后自动弹出悬浮窗展示识别文字，支持多语言翻译。

## 功能

- 剪贴板事件驱动监听（无轮询、低占用），截图后自动触发 OCR 识别
- 离线 OCR 引擎（[RapidOCR](https://github.com/RapidAI/RapidOCR) + ONNX Runtime），识别过程无需联网
- OCR 与翻译均在后台线程执行，界面不卡顿
- 基于坐标的排版还原，保留原文的行结构、缩进和段落间距
- 手动 / 自动翻译，支持 15 种目标语言，自动检测源语言
- 全局快捷键 Ctrl+Shift+Q 随时开关 OCR 功能（Windows 原生热键，无需管理员权限），程序保持后台运行
- 托盘图标：切换 OCR、显示窗口、退出程序
- 语言选择与自动翻译设置自动保存
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

启动后程序在后台运行（系统托盘出现蓝色 "P" 图标），OCR 功能默认开启。使用任意截图工具截图后，悬浮窗会自动出现在鼠标旁边。

### 工作流程

1. 截图（Snipaste、微信、QQ、系统截图等），图片自动复制到剪贴板
2. 悬浮窗弹出，显示排版还原后的 OCR 原文
3. 勾选「自动翻译」可在识别完成后自动翻译；或在下拉框中选择目标语言（默认简体中文）后点击「翻译」
4. 点击「复制原文」或「复制翻译」将内容复制到剪贴板
5. 点击窗口外部或右上角关闭按钮隐藏悬浮窗（程序继续后台运行）
6. 右键托盘图标可切换 OCR、显示窗口或退出程序

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
| numpy | OCR 图像数组 |
| requests | Google 翻译 API |

> 翻译使用 Google 非官方接口（translate.googleapis.com），需要联网，且请求内容会发送到 Google 服务器。

## 项目结构

```
PasteReader/
├── pastereader.py      # 主程序
├── requirements.txt    # Python 依赖
└── README.md
```

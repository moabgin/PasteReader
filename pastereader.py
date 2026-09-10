import sys
import ctypes

import numpy as np
import requests
from PIL import Image, ImageGrab
from rapidocr_onnxruntime import RapidOCR

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer, QSettings
from PyQt6.QtGui import (
    QCursor, QTextCursor, QIcon, QPixmap, QPainter, QColor, QFont,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QGraphicsDropShadowEffect, QFrame, QComboBox,
    QCheckBox, QSystemTrayIcon, QMenu,
)

# 初始化离线 OCR 引擎
engine = RapidOCR()

# 翻译目标语言选项
LANGUAGES = {
    "中文 (简体)": "zh-CN",
    "中文 (繁体)": "zh-TW",
    "English": "en",
    "日本語": "ja",
    "한국어": "ko",
    "Français": "fr",
    "Deutsch": "de",
    "Español": "es",
    "Русский": "ru",
    "Italiano": "it",
    "Português": "pt",
    "العربية": "ar",
    "हिन्दी": "hi",
    "ไทย": "th",
    "Tiếng Việt": "vi",
}

# 全局热键参数：Ctrl + Shift + Q
HOTKEY_ID = 1
HOTKEY_MODS = 0x0002 | 0x0004  # MOD_CONTROL | MOD_SHIFT
HOTKEY_VK = 0x51              # 虚拟键码 'Q'
WM_HOTKEY = 0x0312


def _settings():
    return QSettings("PasteReader", "PasteReader")


class TranslateWorker(QThread):
    """后台执行网络翻译，避免阻塞 UI 线程"""
    done = pyqtSignal(bool, str)

    def __init__(self, text, target_lang, parent=None):
        super().__init__(parent)
        self._text = text
        self._target_lang = target_lang

    def run(self):
        try:
            response = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={
                    "client": "gtx",
                    "sl": "auto",
                    "tl": self._target_lang,
                    "dt": "t",
                    "q": self._text,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            translated = "".join(item[0] for item in data[0] if item[0])
            self.done.emit(True, translated)
        except Exception as e:
            self.done.emit(False, str(e))


class OcrWorker(QThread):
    """后台执行 OCR 识别，避免阻塞 UI 线程"""
    done = pyqtSignal(bool, str)

    def __init__(self, image, parent=None):
        super().__init__(parent)
        self._image = image

    def run(self):
        try:
            result, _ = engine(np.array(self._image.convert("RGB")))
            text = format_ocr_layout(result) if result else ""
            self.done.emit(True, text)
        except Exception as e:
            self.done.emit(False, str(e))


def format_ocr_layout(ocr_result):
    """
    根据 OCR 结果的坐标信息排版，尽量还原原截图的文字布局

    RapidOCR 每项格式: [box, text, score]
    box: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]  四个角点
    """
    if not ocr_result:
        return ""

    # 1. 解析每个文本块的位置信息
    blocks = []
    for item in ocr_result:
        box = item[0]
        text = item[1]
        # 取左上角和右下角
        x1, y1 = box[0]
        x2, y2 = box[2]
        y_center = (y1 + y2) / 2
        height = y2 - y1
        blocks.append({
            "text": text,
            "x": x1,
            "y_center": y_center,
            "height": height,
            "width": x2 - x1,
        })

    if not blocks:
        return ""

    # 2. 计算中位行高作为同行判定的阈值
    heights = sorted(b["height"] for b in blocks)
    median_height = heights[len(heights) // 2]
    line_threshold = median_height * 0.6  # Y 坐标差小于 60% 行高视为同一行

    # 3. 按 Y 坐标分组为行
    blocks.sort(key=lambda b: (b["y_center"], b["x"]))
    lines = []
    current_line = [blocks[0]]
    current_y = blocks[0]["y_center"]

    for block in blocks[1:]:
        if abs(block["y_center"] - current_y) < line_threshold:
            current_line.append(block)
            # 更新当前行的 Y 中心（加权平均）
            current_y = sum(b["y_center"] for b in current_line) / len(current_line)
        else:
            lines.append(current_line)
            current_line = [block]
            current_y = block["y_center"]
    lines.append(current_line)

    # 4. 格式化输出
    output_lines = []
    prev_y_end = None
    char_width = median_height * 0.55  # 估算字符宽度

    for line_blocks in lines:
        # 同行内按 X 排序
        line_blocks.sort(key=lambda b: b["x"])

        # 同行内拼接，根据 X 间距决定空格数量
        parts = []
        prev_x_end = None
        for block in line_blocks:
            if prev_x_end is not None:
                gap = block["x"] - prev_x_end
                # 间距大于 2 个字符宽加 tab，大于 1 个字符宽加 2 空格
                if gap > char_width * 3:
                    parts.append("\t")
                elif gap > char_width * 1.5:
                    parts.append("  ")
                elif gap > char_width * 0.3:
                    parts.append(" ")
            parts.append(block["text"])
            prev_x_end = block["x"] + block["width"]

        line_text = "".join(parts)
        # 行首缩进
        indent = ""
        first_x = line_blocks[0]["x"]
        if first_x > char_width * 2:
            indent = "\t" if first_x > char_width * 4 else "  "

        # 段落间距检测：与前一行 Y 间距超过 1.5 倍行高则插入空行
        line_y_center = sum(b["y_center"] for b in line_blocks) / len(line_blocks)
        if prev_y_end is not None:
            gap = line_y_center - prev_y_end
            if gap > median_height * 1.8:
                output_lines.append("")  # 空行分隔段落

        output_lines.append(indent + line_text)
        prev_y_end = max(b["y_center"] + b["height"] / 2 for b in line_blocks)

    return "\n".join(output_lines)


class HotkeyBridge(QWidget):
    """隐藏窗口：接收 RegisterHotKey 发来的 WM_HOTKEY 消息（无需管理员权限）"""
    hotkey_pressed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.winId()  # 强制创建原生窗口以接收系统消息

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            try:
                # Windows MSG 结构体：hwnd(指针大小) + message(4 字节)
                offset = ctypes.sizeof(ctypes.c_void_p)
                msg_type = int.from_bytes(
                    ctypes.string_at(message, offset), 2, "little")
                if msg_type == WM_HOTKEY:
                    self.hotkey_pressed.emit()
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)


class FloatingWindow(QWidget):
    """PyQt6 无边框跟随鼠标悬浮窗"""
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        # 1. 窗口属性设置：无边框 + 保持置顶 + 不在任务栏显示图标
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 背景透明（配合圆角阴影）
        self.setFixedSize(400, 300)

        # 2. 外层主容器与阴影样式
        # 边距需大于阴影 blur 半径，否则阴影会被窗口边界裁切
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 12px;
            }
            QLabel {
                color: #cdd6f4;
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
            QTextEdit {
                background-color: #181825;
                color: #a6adc8;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                border-radius: 6px;
                padding: 5px 12px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton:pressed {
                background-color: #74c7ec;
            }
        """)

        # 增加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setOffset(0, 4)
        shadow.setColor(Qt.GlobalColor.black)
        self.container.setGraphicsEffect(shadow)

        # 3. 内部布局构成
        c_layout = QVBoxLayout(self.container)
        c_layout.setSpacing(6)

        # 标题栏/头部
        header_layout = QHBoxLayout()
        header_title = QLabel("Snipaste OCR & 翻译")
        header_layout.addWidget(header_title)
        header_layout.addStretch()

        # 关闭按钮（隐藏窗口，程序继续后台运行；退出请用托盘菜单）
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setToolTip("隐藏窗口（程序继续后台运行，可从托盘图标退出）")
        close_btn.setStyleSheet("QPushButton { background: transparent; color: #a6adc8; border-radius: 10px; font-size: 10px; } QPushButton:hover { background: #f38ba8; color: #11111b; }")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        c_layout.addLayout(header_layout)

        # 识别原文（只读，防止误编辑）
        c_layout.addWidget(QLabel("原文识别:"))
        self.ocr_box = QTextEdit()
        self.ocr_box.setReadOnly(True)
        c_layout.addWidget(self.ocr_box)

        # 翻译结果
        trans_header_layout = QHBoxLayout()
        trans_header_layout.addWidget(QLabel("翻译结果:"))

        # 自动翻译开关（状态持久化）
        self.auto_translate = QCheckBox("自动翻译")
        self.auto_translate.setChecked(bool(_settings().value("auto_translate", False)))
        self.auto_translate.setToolTip("OCR 完成后自动翻译")
        self.auto_translate.toggled.connect(
            lambda on: _settings().setValue("auto_translate", on)
        )
        trans_header_layout.addWidget(self.auto_translate)

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
        saved_lang = _settings().value("language")
        if saved_lang in LANGUAGES:
            self.lang_combo.setCurrentText(saved_lang)
        else:
            self.lang_combo.setCurrentText("中文 (简体)")
        self.lang_combo.setFixedWidth(100)
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 2px 4px;
                font-size: 10px;
            }
            QComboBox:hover {
                background-color: #45475a;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e2e;
                color: #cdd6f4;
                selection-background-color: #89b4fa;
                selection-color: #11111b;
                border: 1px solid #45475a;
                font-size: 10px;
            }
        """)
        self.lang_combo.currentTextChanged.connect(
            lambda text: _settings().setValue("language", text)
        )
        trans_header_layout.addWidget(self.lang_combo)
        trans_header_layout.addStretch()

        self.trans_btn = QPushButton("翻译")
        self.trans_btn.setFixedWidth(50)
        self.trans_btn.clicked.connect(self.do_translate)
        trans_header_layout.addWidget(self.trans_btn)

        c_layout.addLayout(trans_header_layout)
        self.trans_box = QTextEdit()
        self.trans_box.setReadOnly(True)
        c_layout.addWidget(self.trans_box)

        # 底部操作按钮
        btn_layout = QHBoxLayout()
        btn_copy_ocr = QPushButton("复制原文")
        btn_copy_trans = QPushButton("复制翻译")

        btn_copy_ocr.clicked.connect(self.copy_ocr)
        btn_copy_trans.clicked.connect(self.copy_trans)

        btn_layout.addWidget(btn_copy_ocr)
        btn_layout.addWidget(btn_copy_trans)
        btn_layout.addStretch()

        c_layout.addLayout(btn_layout)
        layout.addWidget(self.container)

        # 失焦隐藏守卫：延迟 200ms 再隐藏，避免下拉框打开时抢焦点导致误隐藏
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._lang_popup_open = False
        self.lang_combo.showPopup.connect(self._on_lang_popup_show)
        self.lang_combo.hidePopup.connect(self._on_lang_popup_hide)

    def changeEvent(self, event):
        """窗口失去焦点时延迟自动隐藏；语言下拉框打开期间不隐藏"""
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._hide_timer.stop()
            elif not self._lang_popup_open:
                self._hide_timer.start(200)
        super().changeEvent(event)

    def _on_lang_popup_show(self):
        """下拉框打开：暂停失焦隐藏"""
        self._lang_popup_open = True
        self._hide_timer.stop()

    def _on_lang_popup_hide(self):
        """下拉框关闭后若窗口仍未获得焦点，则走延迟隐藏流程"""
        self._lang_popup_open = False
        if not self.isActiveWindow():
            self._hide_timer.start(200)

    def update_and_show(self, ocr_text, trans_text=""):
        """更新文本，定位到鼠标旁边并显示"""
        self.ocr_box.setPlainText(ocr_text)
        self.ocr_box.moveCursor(QTextCursor.MoveOperation.Start)
        self.trans_box.setPlainText(trans_text)
        self.trans_btn.setEnabled(True)  # 新 OCR 结果，重新启用翻译按钮

        # 获取鼠标所在屏幕（支持多显示器），防止弹窗超出屏幕边界
        cursor_pos = QCursor.pos()
        screen = QApplication.screenAt(cursor_pos) or QApplication.primaryScreen()
        geom = screen.geometry()
        x = cursor_pos.x() + 15  # 默认在鼠标右下方偏移 15px
        y = cursor_pos.y() + 15

        if x + self.width() > geom.right():
            x = cursor_pos.x() - self.width() - 5
        if y + self.height() > geom.bottom():
            y = cursor_pos.y() - self.height() - 5
        x = max(geom.left(), x)
        y = max(geom.top(), y)

        self.move(x, y)
        self.show()
        self.activateWindow()

        # 勾选了自动翻译则立即翻译
        if self.auto_translate.isChecked():
            self.do_translate()

    def copy_ocr(self):
        QApplication.clipboard().setText(self.ocr_box.toPlainText())

    def copy_trans(self):
        QApplication.clipboard().setText(self.trans_box.toPlainText())

    def do_translate(self):
        """触发翻译（后台线程执行，不卡 UI，防重入）"""
        ocr_text = self.ocr_box.toPlainText()
        if not ocr_text.strip() or not self.trans_btn.isEnabled():
            return
        target_lang = LANGUAGES.get(self.lang_combo.currentText(), "zh-CN")
        self.trans_btn.setEnabled(False)
        self.trans_box.clear()

        worker = TranslateWorker(ocr_text, target_lang, self)
        worker.done.connect(self._on_translate_done)
        worker.done.connect(worker.deleteLater)
        worker.start()

    def _on_translate_done(self, ok, text):
        self.trans_btn.setEnabled(True)
        if ok:
            self.trans_box.setPlainText(text)
            self.trans_box.moveCursor(QTextCursor.MoveOperation.Start)
        else:
            self.trans_box.clear()
            self.show_toast(f"翻译失败: {text}", 2500)

    def show_toast(self, message, duration=1500):
        """在屏幕中央底部显示短暂提示（非阻塞）"""
        toast = QLabel(message, parent=None)
        toast.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        toast.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        toast.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 30, 46, 220);
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 8px;
                padding: 8px 20px;
                font-size: 14px;
                font-weight: bold;
            }
        """)
        toast.adjustSize()
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - toast.width()) // 2
        y = screen.height() - toast.height() - 60
        toast.move(x, y)
        toast.show()
        QTimer.singleShot(duration, toast.close)


class MainApp(QApplication):
    def __init__(self, sys_argv):
        super().__init__(sys_argv)
        self.ocr_enabled = True
        self.window = FloatingWindow()

        # 注册全局快捷键 Ctrl+Shift+Q（Windows RegisterHotKey，无需管理员权限）
        self._hotkey_ok = False
        if sys.platform == "win32":
            self.bridge = HotkeyBridge()
            hwnd = int(self.bridge.winId())
            self._hotkey_ok = bool(ctypes.windll.user32.RegisterHotKey(
                hwnd, HOTKEY_ID, HOTKEY_MODS, HOTKEY_VK))
            if self._hotkey_ok:
                self.bridge.hotkey_pressed.connect(self._toggle_ocr)
            else:
                self.window.show_toast("全局热键注册失败，可用托盘菜单切换 OCR", 3000)

        self._setup_tray()

        # 事件驱动的剪贴板监听（替代 500ms 轮询 + 全像素 hash）
        self._last_clip_hash = None
        self._ocr_busy = False
        self.clipboard().dataChanged.connect(self._on_clipboard_changed)

    def _setup_tray(self):
        """系统托盘图标：切换 OCR / 显示窗口 / 退出程序"""
        self.tray = QSystemTrayIcon(self.make_tray_icon(), self)
        self.tray.setToolTip("PasteReader - 截图 OCR & 翻译")
        menu = QMenu()
        self._tray_toggle_action = menu.addAction(
            "关闭 OCR 识别" if self.ocr_enabled else "开启 OCR 识别")
        self._tray_toggle_action.triggered.connect(self._toggle_ocr)
        menu.addSeparator()
        menu.addAction("显示窗口", self._show_window)
        menu.addAction("退出 PasteReader", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.show()

    @staticmethod
    def make_tray_icon():
        """程序化生成托盘图标（蓝色圆角方块 + P），避免依赖外部图片资源"""
        pm = QPixmap(64, 64)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#89b4fa"))
        p.drawRoundedRect(4, 4, 56, 56, 12, 12)
        p.setPen(QColor("#11111b"))
        font = QFont("Segoe UI")
        font.setPointSize(26)
        font.setBold(True)
        p.setFont(font)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "P")
        p.end()
        return QIcon(pm)

    def _show_window(self):
        self.window.show()
        self.window.activateWindow()

    def _toggle_ocr(self):
        """切换 OCR 识别开关"""
        self.ocr_enabled = not self.ocr_enabled
        status = "OCR 已开启" if self.ocr_enabled else "OCR 已关闭"
        self.window.show_toast(status)
        self._tray_toggle_action.setText(
            "关闭 OCR 识别" if self.ocr_enabled else "开启 OCR 识别")

    def _on_clipboard_changed(self):
        """剪贴板变化时检查是否为新图片，是则交给后台线程识别"""
        if not self.ocr_enabled or self._ocr_busy:
            return
        img = ImageGrab.grabclipboard()
        if not isinstance(img, Image.Image):
            return
        # 像素数据 hash 去重，避免同一张图重复触发
        img_hash = hash(img.tobytes())
        if img_hash == self._last_clip_hash:
            return
        self._last_clip_hash = img_hash

        self._ocr_busy = True
        worker = OcrWorker(img, self)
        worker.done.connect(self._on_ocr_done)
        worker.done.connect(worker.deleteLater)
        worker.start()

    def _on_ocr_done(self, ok, text):
        self._ocr_busy = False
        if not ok:
            self.window.show_toast(f"OCR 失败: {text}", 2500)
            return
        if text:
            self.window.update_and_show(text)
        else:
            self.window.show_toast("未识别到文字")

    def cleanup(self):
        if self._hotkey_ok and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(
                int(self.bridge.winId()), HOTKEY_ID)


if __name__ == "__main__":
    app = MainApp(sys.argv)
    app.aboutToQuit.connect(app.cleanup)
    sys.exit(app.exec())

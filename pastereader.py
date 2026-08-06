import sys
import numpy as np
import requests
import keyboard
from PIL import Image, ImageGrab
from rapidocr_onnxruntime import RapidOCR

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QGraphicsDropShadowEffect, QFrame, QComboBox
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

def translate_text(text, target_lang="zh"):
    if not text.strip():
        return ""
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={text}"
        response = requests.get(url, timeout=5)
        result = response.json()
        return "".join([item[0] for item in result[0] if item[0]])
    except Exception as e:
        return f"翻译失败: {str(e)}"


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


class ClipboardListener(QThread):
    """后台剪贴板监听线程"""
    image_detected = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.running = True
        self.last_hash = None

    def run(self):
        while self.running:
            try:
                img = ImageGrab.grabclipboard()
                if isinstance(img, Image.Image):
                    # 通过像素数据计算简易 hash 避免重复触发
                    img_hash = hash(img.tobytes())
                    if img_hash != self.last_hash:
                        self.last_hash = img_hash
                        self.image_detected.emit(img)
            except Exception:
                pass
            self.msleep(500)

    def stop(self):
        self.running = False


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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) # 背景透明（配合圆角阴影）
        self.setFixedSize(380, 280)

        # 2. 外层主容器与阴影样式
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

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
        shadow.setBlurRadius(15)
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
        
        # 关闭按钮
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("QPushButton { background: transparent; color: #a6adc8; border-radius: 10px; font-size: 10px; } QPushButton:hover { background: #f38ba8; color: #11111b; }")
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        
        c_layout.addLayout(header_layout)

        # 识别原文
        c_layout.addWidget(QLabel("原文识别:"))
        self.ocr_box = QTextEdit()
        c_layout.addWidget(self.ocr_box)

        # 翻译结果
        trans_header_layout = QHBoxLayout()
        trans_header_layout.addWidget(QLabel("翻译结果:"))

        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES.keys())
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
        trans_header_layout.addWidget(self.lang_combo)
        trans_header_layout.addStretch()

        self.trans_btn = QPushButton("翻译")
        self.trans_btn.setFixedWidth(50)
        self.trans_btn.clicked.connect(self.do_translate)
        trans_header_layout.addWidget(self.trans_btn)

        c_layout.addLayout(trans_header_layout)
        self.trans_box = QTextEdit()
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

    def changeEvent(self, event):
        """窗口失去焦点时自动隐藏"""
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self.hide()
        super().changeEvent(event)

    def update_and_show(self, ocr_text, trans_text=""):
        """更新文本，定位到鼠标旁边并显示"""
        self.ocr_box.setText(ocr_text)
        self.trans_box.setText(trans_text)
        self.trans_btn.setEnabled(True)  # 新 OCR 结果，重新启用翻译按钮

        # 获取当前鼠标在屏幕上的全局坐标
        cursor_pos = QCursor.pos()

        # 获取当前屏幕分辨率，防止弹窗超出屏幕边界
        screen = QApplication.primaryScreen().geometry()
        x = cursor_pos.x() + 15  # 默认在鼠标右下方偏移 15px
        y = cursor_pos.y() + 15

        if x + self.width() > screen.width():
            x = cursor_pos.x() - self.width() - 5
        if y + self.height() > screen.height():
            y = cursor_pos.y() - self.height() - 5

        self.move(x, y)
        self.show()
        self.activateWindow()

    def copy_ocr(self):
        QApplication.clipboard().setText(self.ocr_box.toPlainText())

    def copy_trans(self):
        QApplication.clipboard().setText(self.trans_box.toPlainText())

    def do_translate(self):
        """手动触发翻译"""
        ocr_text = self.ocr_box.toPlainText()
        if not ocr_text.strip():
            return
        target_lang = LANGUAGES[self.lang_combo.currentText()]
        trans_text = translate_text(ocr_text, target_lang)
        self.trans_box.setText(trans_text)
        self.trans_btn.setEnabled(False)

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
    toggle_signal = pyqtSignal()

    def __init__(self, sys_argv):
        super().__init__(sys_argv)
        self.ocr_enabled = True
        self.window = FloatingWindow()

        # 连接切换信号（由键盘钩子线程触发，主线程执行）
        self.toggle_signal.connect(self._toggle_ocr)

        # 注册全局快捷键 Ctrl+Shift+Q 切换 OCR 功能
        keyboard.add_hotkey('ctrl+shift+q', self.toggle_signal.emit)

        # 开启剪贴板后台监听线程
        self.listener = ClipboardListener()
        self.listener.image_detected.connect(self.handle_image)
        self.listener.start()

    def _toggle_ocr(self):
        """切换 OCR 识别开关"""
        self.ocr_enabled = not self.ocr_enabled
        status = "OCR 已开启" if self.ocr_enabled else "OCR 已关闭"
        self.window.show_toast(status)

    def handle_image(self, img):
        if not self.ocr_enabled:
            return

        # 直接传入 numpy 数组，省去 PNG 编解码开销
        result, _ = engine(np.array(img))
        if result:
            ocr_text = format_ocr_layout(result)
            self.window.update_and_show(ocr_text)

    def cleanup(self):
        self.listener.stop()
        self.listener.wait()


if __name__ == "__main__":
    app = MainApp(sys.argv)
    app.aboutToQuit.connect(app.cleanup)
    sys.exit(app.exec())
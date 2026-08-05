import time
import io
import tkinter as tk
from PIL import ImageGrab, Image
from rapidocr_onnxruntime import RapidOCR
import requests

# 初始化离线 OCR 引擎
engine = RapidOCR()

def translate_text(text, target_lang="zh"):
    """使用免费的谷歌翻译接口 (不需要 API Key)"""
    if not text.strip():
        return ""
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={text}"
        response = requests.get(url, timeout=5)
        result = response.json()
        translated = "".join([item[0] for item in result[0] if item[0]])
        return translated
    except Exception as e:
        return f"翻译失败: {str(e)}"

def show_popup(ocr_text, trans_text):
    """显示简洁的悬浮弹窗"""
    root = tk.Tk()
    root.title("Snipaste OCR & 翻译")
    root.attributes('-topmost', True)  # 窗口最顶层显示
    root.geometry("450x300")

    # 原文区域
    tk.Label(root, text="识别原文:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
    text_box = tk.Text(root, height=5, font=("Microsoft YaHei", 9))
    text_box.insert("1.0", ocr_text)
    text_box.pack(fill="x", padx=10)

    # 翻译区域
    tk.Label(root, text="翻译结果:", font=("Microsoft YaHei", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
    trans_box = tk.Text(root, height=5, font=("Microsoft YaHei", 9))
    trans_box.insert("1.0", trans_text)
    trans_box.pack(fill="x", padx=10)

    # 复制按钮
    def copy_ocr():
        root.clipboard_clear()
        root.clipboard_append(ocr_text)

    def copy_trans():
        root.clipboard_clear()
        root.clipboard_append(trans_text)

    btn_frame = tk.Frame(root)
    btn_frame.pack(fill="x", padx=10, pady=10)
    tk.Button(btn_frame, text="复制原文", command=copy_ocr).pack(side="left", padx=5)
    tk.Button(btn_frame, text="复制翻译", command=copy_trans).pack(side="left", padx=5)

    root.mainloop()

def process_image(img):
    # 将 PIL Image 转为 bytes 给 RapidOCR 使用
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()

    # 运行 OCR
    result, _ = engine(img_bytes)
    if result:
        ocr_text = "\n".join([line[1] for line in result])
        trans_text = translate_text(ocr_text)
        show_popup(ocr_text, trans_text)

def listen_clipboard():
    print("开始监听剪贴板...（使用 Snipaste 截图并按 Ctrl+C 即可触发）")
    last_img_hash = None

    while True:
        try:
            # 获取剪贴板图片
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                # 简单计算 hash 避免重复触发
                img_hash = hash(img.tobytes())
                if img_hash != last_img_hash:
                    last_img_hash = img_hash
                    process_image(img)
        except Exception as e:
            pass
        time.sleep(0.5)

if __name__ == "__main__":
    listen_clipboard()
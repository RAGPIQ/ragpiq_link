import os
import sys
import time
import shutil
import requests
import threading
import json

from brother_ql.raster import BrotherQLRaster
from brother_ql.conversion import convert
from brother_ql.backends.helpers import send
from PIL import Image, ImageDraw, ImageFont
import qrcode
import pdf417gen

# Compatibility patch for Pillow >=10.0.0
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# ----------------- Label Image Setup -----------------
LABEL_WIDTH = 306
LABEL_HEIGHT = 991
TOP_MARGIN = 35
SPACING = 35
BOTTOM_MARGIN = 10
PDF417_OFFSET = 80
TOP_GROUP_WIDTH = int(LABEL_WIDTH * 0.85)
PDF417_WIDTH = int(LABEL_WIDTH * 1)
PDF417_HEIGHT = 300

def get_resized_font(text, max_width, font_path="arialbd.ttf"):
    size = 10
    while True:
        try:
            font = ImageFont.truetype(font_path, size)
        except:
            font = ImageFont.load_default()
        bbox = ImageDraw.Draw(Image.new("1", (1, 1))).textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] >= max_width and size > 1:
            return ImageFont.truetype(font_path, size - 1)
        elif bbox[2] - bbox[0] >= max_width:
            return font
        size += 1

def create_label_image(text1, qr_data, text2, pdf_data, width=LABEL_WIDTH, height=LABEL_HEIGHT):
    img = Image.new('1', (width, height), 1)
    draw = ImageDraw.Draw(img)

    header_font = get_resized_font(text1, TOP_GROUP_WIDTH)
    date_font = get_resized_font(text2, TOP_GROUP_WIDTH)
    header_h = draw.textbbox((0, 0), text1, font=header_font)[3]

    qr = qrcode.QRCode(border=0)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
    qr_img = qr_img.resize((TOP_GROUP_WIDTH, TOP_GROUP_WIDTH), Image.NEAREST)

    y_cursor = TOP_MARGIN
    draw.text(((width - TOP_GROUP_WIDTH) // 2, y_cursor), text1, font=header_font, fill=0)
    y_cursor += header_h + SPACING

    img.paste(qr_img, ((width - TOP_GROUP_WIDTH) // 2, y_cursor))
    y_cursor += qr_img.height + SPACING

    draw.text(((width - TOP_GROUP_WIDTH) // 2, y_cursor), text2, font=date_font, fill=0)

    codes = pdf417gen.encode(pdf_data)
    pdf_img = pdf417gen.render_image(codes, scale=2).convert("1")
    pdf_img = pdf_img.resize((PDF417_WIDTH, PDF417_HEIGHT))
    pdf_x = (width - PDF417_WIDTH) // 2
    pdf_y = height - PDF417_HEIGHT - BOTTOM_MARGIN + PDF417_OFFSET

    img.paste(pdf_img, (pdf_x, pdf_y))
    return img

def print_label(img, printer_identifier="usb://0x04f9:0x2042", model="QL-700"):
    qlr = BrotherQLRaster(model)
    qlr.exception_on_warning = True
    qlr.cut = False
    qlr.auto_cut = False
    qlr.cut_at_end = False

    instructions = convert(
        qlr,
        label='29x90',
        images=[img],
        threshold=70.0,
        dither=True,
        compress=True,
        red=False,
        cut=False
    )

    send(
        instructions=instructions,
        printer_identifier=printer_identifier,
        backend_identifier='pyusb'
    )

# ----------------- File and Polling Logic -----------------
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
    BASE_DIR = os.path.abspath(os.path.join(exe_dir, ".."))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WATCH_DIRECTORY = os.path.join(BASE_DIR, "PROCESSING")
DESTINATION_DIRECTORY = os.path.join(BASE_DIR, "COMPLETE")

os.makedirs(WATCH_DIRECTORY, exist_ok=True)
os.makedirs(DESTINATION_DIRECTORY, exist_ok=True)

IMAGE_POST_URL = "https://n8n2.ragpiq.com/webhook/6a101ea2-23e3-47ba-a180-9ac16edd35c3"
LABEL_POLL_URL = "https://ragpiq.bubbleapps.io/api/1.1/wf/camera_polling"
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
processed_images = set()

def watch_folder_for_images(camera_id):
    while True:
        try:
            for filename in os.listdir(WATCH_DIRECTORY):
                if filename in processed_images:
                    continue

                full_path = os.path.join(WATCH_DIRECTORY, filename)
                if not os.path.isfile(full_path):
                    continue

                ext = os.path.splitext(filename)[1].lower()
                if ext in VALID_EXTENSIONS:
                    send_image_to_webhook(full_path, camera_id)
                    new_path = os.path.join(DESTINATION_DIRECTORY, filename)
                    shutil.move(full_path, new_path)
                    processed_images.add(filename)

        except Exception as e:
            print(f"⚠ Error while processing images: {e}", flush=True)
        time.sleep(5)

def send_image_to_webhook(image_path, camera_id):
    try:
        filename = os.path.basename(image_path)
        with open(image_path, "rb") as image_file:
            files = {"data": (filename, image_file, "image/jpeg")}
            data = {"camera": camera_id}
            response = requests.post(IMAGE_POST_URL, files=files, data=data)
            response.raise_for_status()
            print(f"✅ Image sent: {filename}", flush=True)
            return filename
    except requests.RequestException as e:
        print(f"❌ Error sending {filename}: {e}", flush=True)
        return None

def poll_for_label_data(camera_id):
    while True:
        try:
            payload = {"camera": camera_id}
            headers = {
                "Authorization": "Bearer fd6db05318d92ca4d50e4532bc82e23c",
                "Content-Type": "application/json"
            }
            response = requests.post(LABEL_POLL_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and data.get("status") == "success":
                raw_string = data["response"]["response"]
                label_items = json.loads(raw_string)

                if isinstance(label_items, list):
                    for item in label_items:
                        qrcode = item.get("qrcode", "Unknown")
                        barcode = item.get("barcode", "Unknown")
                        created = item.get("created", "Unknown")
                        print(f"★ New label => QR: {qrcode}, Barcode: {barcode}, Created: {created}", flush=True)
                        send_to_printer(qrcode, barcode, created)
                else:
                    print("⚠ Unexpected data structure for 'label_items' (expected a list).", flush=True)
            else:
                print("⚠ No valid data returned or empty array.", flush=True)

        except Exception as e:
            print(f"❌ Error polling label data: {e}", flush=True)
        time.sleep(10)

def send_to_printer(qrcode, barcode, created):
    try:
        img = create_label_image(
            text1="RAGPIQ",
            qr_data=qrcode,
            text2=created,
            pdf_data=barcode
        )
        print_label(img)
        print("★ Printed label successfully.", flush=True)
    except Exception as e:
        print(f"❌ Error during printing: {e}", flush=True)

def main(camera_id):
    watcher_thread = threading.Thread(target=watch_folder_for_images, args=(camera_id,), daemon=True)
    watcher_thread.start()
    poll_for_label_data(camera_id)

if __name__ == "__main__":
    cam_id = sys.argv[1] if len(sys.argv) > 1 else "MISSING_ID"
    main(cam_id)

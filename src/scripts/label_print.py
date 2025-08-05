import sys
import os
from brother_ql.raster import BrotherQLRaster
from brother_ql.conversion import convert
from brother_ql.backends.helpers import send
from PIL import Image, ImageDraw, ImageFont
import qrcode
import pdf417gen

os.environ["DYLD_LIBRARY_PATH"] = os.path.abspath("./portable-python/mac/libusb")

# Compatibility patch for Pillow >=10.0.0
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

# Label layout constants
LABEL_WIDTH = 306
LABEL_HEIGHT = 991
TOP_MARGIN = 35
SPACING = 35
BOTTOM_MARGIN = 10
PDF417_OFFSET = 80
TOP_GROUP_WIDTH = int(LABEL_WIDTH * 0.85)
PDF417_WIDTH = int(LABEL_WIDTH * 1.10)
PDF417_HEIGHT = 230

def get_resized_font(text, max_width, font_path=None):
    if font_path is None:
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'arialbd.ttf')

    size = 10
    while True:
        try:
            font = ImageFont.truetype(font_path, size)
            bbox = font.getbbox(text)
            text_width = bbox[2] - bbox[0]
        except Exception:
            font = ImageFont.load_default()
            try:
                bbox = font.getbbox(text)
                text_width = bbox[2] - bbox[0]
            except Exception:
                text_width = 9999  # fallback in worst case

        if text_width > max_width:
            break
        size += 1

    return font

def create_label_image(text1, qr_data, text2, pdf_data, width=LABEL_WIDTH, height=LABEL_HEIGHT):
    img = Image.new('1', (width, height), 1)
    draw = ImageDraw.Draw(img)

    # Fonts
    header_font = get_resized_font(text1, TOP_GROUP_WIDTH)
    date_font = get_resized_font(text2, TOP_GROUP_WIDTH)
    bbox = draw.textbbox((0, 0), text1, font=header_font)
    header_h = bbox[3] - bbox[1]


    # QR Code
    qr = qrcode.QRCode(border=0)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
    qr_img = qr_img.resize((TOP_GROUP_WIDTH, TOP_GROUP_WIDTH), Image.NEAREST)

    # Compose top section
    y_cursor = TOP_MARGIN
    draw.text(((width - TOP_GROUP_WIDTH) // 2, y_cursor), text1, font=header_font, fill=0)
    y_cursor += header_h + SPACING
    img.paste(qr_img, ((width - TOP_GROUP_WIDTH) // 2, y_cursor))
    y_cursor += qr_img.height + SPACING
    draw.text(((width - TOP_GROUP_WIDTH) // 2, y_cursor), text2, font=date_font, fill=0)

    # PDF417
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

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python label_print.py <qrcode> <barcode> <created>")
        sys.exit(1)

    try:
        qrcode_val = sys.argv[1]
        barcode_val = sys.argv[2]
        created_val = sys.argv[3]

        label_img = create_label_image(
            text1="RAGPIQ",
            qr_data=qrcode_val,
            text2=created_val,
            pdf_data=barcode_val
        )

        print_label(label_img)
        print("Printed label successfully.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error during label generation/printing: {e}", file=sys.stderr)
        sys.exit(2)

import sys
import os
from pathlib import Path

DEBUG = os.getenv("RAGPIQ_DEBUG", "").lower() in ("1", "true", "yes")

def dprint(*a, **k):
    if DEBUG:
        print("[label_print]", *a, **k, flush=True)

if sys.platform == "darwin" and "DYLD_LIBRARY_PATH" not in os.environ:
    exe = Path(sys.executable).resolve()
    # Try to find ".../Contents/Resources" in the path (packaged app)
    resources = None
    for p in exe.parents:
        if p.name == "Resources" and p.parent.name == "Contents":
            resources = p
            break

    if resources is not None:
        # Packaged layout:
        # Resources/lib/libusb-1.0.dylib (you will copy the whole libusb dir here)
        lib_dir = resources / "lib"
        py_lib  = resources / "python" / "mac" / "Library" / "Frameworks" / "3.13" / "lib"
        dyld = f"{lib_dir}:{resources}:{py_lib}"
        libusb_hint = lib_dir / "libusb-1.0.dylib"
    else:
        # Dev layout:
        # <repo>/portable-python/mac/libusb/libusb-1.0.dylib
        # <repo>/portable-python/mac/Library/Frameworks/3.13/lib
        # Walk up until we see portable-python
        pp_root = None
        for p in exe.parents:
            cand = p / "portable-python" / "mac"
            if cand.exists():
                pp_root = p
                break
        if pp_root is None:
            # fallback: assume current working directory is repo root
            pp_root = Path.cwd()
        lib_dir = pp_root / "portable-python" / "mac" / "libusb"
        py_lib  = pp_root / "portable-python" / "mac" / "Library" / "Frameworks" / "3.13" / "lib"
        dyld = f"{lib_dir}:{py_lib}"
        libusb_hint = lib_dir / "libusb-1.0.dylib"

    os.environ["DYLD_LIBRARY_PATH"] = dyld
    os.environ.setdefault("LIBUSB_PATH", str(libusb_hint))
    dprint("DYLD_LIBRARY_PATH:", os.environ["DYLD_LIBRARY_PATH"])
    dprint("LIBUSB_PATH:", os.environ.get("LIBUSB_PATH"))

# preload libusb for clearer errors (optional but helpful)
if sys.platform == "darwin":
    try:
        import ctypes
        ctypes.CDLL(os.environ.get("LIBUSB_PATH", "libusb-1.0.dylib"))
        dprint("libusb preloaded OK")
    except Exception as e:
        dprint("libusb preload FAILED:", repr(e))

        
from brother_ql.raster import BrotherQLRaster
from brother_ql.conversion import convert
from brother_ql.backends.helpers import send
from PIL import Image, ImageDraw, ImageFont
import qrcode
import pdf417gen

# Optional: probe libusb loadability on macOS for clearer errors
if sys.platform == "darwin" and DEBUG:
    try:
        import ctypes
        ctypes.CDLL("libusb-1.0.dylib")
        dprint("libusb-1.0.dylib loaded OK")
    except Exception as e:
        dprint("libusb load FAILED:", repr(e))

# ===== Label constants =====
LABEL_WIDTH = 306
LABEL_HEIGHT = 991
TOP_MARGIN = 35
SPACING = 35
BOTTOM_MARGIN = 10
PDF417_OFFSET = 80
TOP_GROUP_WIDTH = int(LABEL_WIDTH * 0.85)
PDF417_WIDTH = int(LABEL_WIDTH * 1.10)
PDF417_HEIGHT = 230

# Pillow >=10 fallback
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

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
                text_width = 9999
        if text_width > max_width:
            break
        size += 1
    return font

def create_label_image(text1, qr_data, text2, pdf_data, width=LABEL_WIDTH, height=LABEL_HEIGHT):
    img = Image.new('1', (width, height), 1)
    draw = ImageDraw.Draw(img)

    header_font = get_resized_font(text1, TOP_GROUP_WIDTH)
    date_font = get_resized_font(text2, TOP_GROUP_WIDTH)
    bbox = draw.textbbox((0, 0), text1, font=header_font)
    header_h = bbox[3] - bbox[1]

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

# ----- USB auto-discovery (pyusb) -----
def autodetect_printer_identifier(vendor_hex="0x04f9"):
    """
    Returns a 'usb://0xVVVV:0xPPPP' for the first Brother device found, or None.
    """
    try:
        import usb.core  # pyusb
        vid = int(vendor_hex, 16)
        dev = usb.core.find(idVendor=vid)
        if dev is None:
            dprint("pyusb found NO Brother devices")
            return None
        pid = dev.idProduct
        ident = f"usb://0x{vid:04x}:0x{pid:04x}"
        dprint("pyusb found device:", ident)
        return ident
    except Exception as e:
        dprint("pyusb discovery failed:", repr(e))
        return None

def print_label(img, printer_identifier=None, model="QL-700"):
    """
    printer_identifier:
      - if None: try autodetect via pyusb
      - or explicit like 'usb://0x04f9:0x2042'
    """
    if not printer_identifier:
        printer_identifier = autodetect_printer_identifier() or "usb://0x04f9:0x2042"

    dprint("Using printer_identifier:", printer_identifier, "model:", model)

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

    try:
        send(
            instructions=instructions,
            printer_identifier=printer_identifier,
            backend_identifier='pyusb'
        )
    except Exception as e:
        # Make the error explicit so you see it in Electron's stderr
        dprint("send() FAILED:", repr(e))
        raise

def _self_test():
    print("=== label_print.py self-test ===")
    print("sys.platform:", sys.platform)
    print("sys.executable:", sys.executable)
    print("DYLD_LIBRARY_PATH:", os.environ.get("DYLD_LIBRARY_PATH"))
    try:
        ident = autodetect_printer_identifier()
        print("Autodetect printer:", ident)
    except Exception as e:
        print("Autodetect failed:", repr(e))

if __name__ == "__main__":
    # quick self-test mode: `python label_print.py --self-test`
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        _self_test()
        sys.exit(0)

    if len(sys.argv) != 4:
        print("Usage: python label_print.py <qrcode> <barcode> <created>", file=sys.stderr)
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

        print_label(label_img, printer_identifier=None)  # let it auto-detect
        print("Printed label successfully.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error during label generation/printing: {e}", file=sys.stderr)
        sys.exit(2)
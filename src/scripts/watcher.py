import os
import sys
import time
import shutil
import requests
import threading

# UTF-8 output for real-time logs
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

# Directories
if getattr(sys, 'frozen', False):
    exe_dir = os.path.dirname(sys.executable)
    BASE_DIR = os.path.abspath(os.path.join(exe_dir, ".."))
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

WATCH_DIRECTORY = os.path.join(BASE_DIR, "PROCESSING")
DESTINATION_DIRECTORY = os.path.join(BASE_DIR, "COMPLETE")

os.makedirs(WATCH_DIRECTORY, exist_ok=True)
os.makedirs(DESTINATION_DIRECTORY, exist_ok=True)

# Config
IMAGE_POST_URL = "https://n8n2.ragpiq.com/webhook/6a101ea2-23e3-47ba-a180-9ac16edd35c3"
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
            print(f"[WATCHER_SUCCESS] Uploaded image: {filename}", flush=True)
            return filename
    except requests.RequestException as e:
        print(f"[WATCHER_ERROR] Failed to upload {filename}: {e}", flush=True)
        return None

def main(camera_id):
    watcher_thread = threading.Thread(target=watch_folder_for_images, args=(camera_id,), daemon=True)
    watcher_thread.start()
    watcher_thread.join()

if __name__ == "__main__":
    cam_id = sys.argv[1] if len(sys.argv) > 1 else "MISSING_ID"
    main(cam_id)
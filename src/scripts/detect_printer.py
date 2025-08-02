import subprocess
import platform
import json
import re
import time
import signal
import sys

def handle_sigterm(sig, frame):
    print("Watcher received SIGTERM, exiting.", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)

def check_driver_type_windows(device_name):
    try:
        powershell_cmd = f"""
        Get-PnpDevice -FriendlyName "*{device_name}*" |
        Select-Object -Property FriendlyName, Class, Status, DriverProviderName, DriverVersion |
        ConvertTo-Json
        """
        output = subprocess.check_output(["powershell", "-Command", powershell_cmd], text=True)
        return json.loads(output)
    except Exception as e:
        return {"error": f"Driver check failed: {e}"}

def scan_usb_devices_windows():
    try:
        output = subprocess.check_output([
            "powershell",
            "-Command",
            "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '^USB' }"
        ], text=True)
        return output
    except subprocess.CalledProcessError:
        return ""

def scan_usb_devices_unix():
    try:
        output = subprocess.check_output(["lsusb"], text=True)
        return output
    except Exception:
        return ""

def detect_ql_printers(output, system):
    ql_keywords = ["QL", "Brother"]
    ql_lines = [line.strip() for line in output.splitlines() if any(k in line for k in ql_keywords)]
    printers = []

    for line in ql_lines:
        match = re.search(r'Brother.*QL-\d+\w*', line)
        printer_name = match.group(0) if match else "Brother QL Printer"

        driver_info = None
        setup_required = True

        if system == "Windows":
            driver_info = check_driver_type_windows("QL")
            if isinstance(driver_info, list):
                for d in driver_info:
                    if d.get("Class", "").lower() == "libusbk devices" and d.get("Status", "").lower() == "ok":
                        setup_required = False
                        break
        else:
            setup_required = True  # default for Unix-like systems

        printers.append({
            "platform": system.lower(),
            "printer_name": printer_name,
            "driver": driver_info,
            "setup_required": setup_required
        })

    return printers

def watch_printers(poll_interval=3):
    system = platform.system()
    previous_state = None

    while True:
        if system == "Windows":
            usb_output = scan_usb_devices_windows()
        else:
            usb_output = scan_usb_devices_unix()

        printers = detect_ql_printers(usb_output, system)
        new_state = json.dumps({
            "printer_name": printers[0]["printer_name"] if printers else "",
            "setup_required": printers[0]["setup_required"] if printers else True
        })

        if new_state != previous_state:
            print(new_state, flush=True)
            previous_state = new_state

        time.sleep(poll_interval)

if __name__ == "__main__":
    watch_printers(poll_interval=3)
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
        # Use system_profiler to list USB devices, which is more reliable on macOS
        output = subprocess.check_output(["system_profiler", "SPUSBDataType"], stderr=subprocess.PIPE, text=True)
        return output
    except subprocess.CalledProcessError as e:
        # Ignore specific error message related to IOCreatePlugInInterfaceForService failure
        if 'SPUSBDevice: IOCreatePlugInInterfaceForService failed' in e.stderr:
            # Print nothing or return an empty string to suppress the error
            return ""
        else:
            # Log other errors
            return f"Error: {e.stderr}"
    except Exception as e:
        # Catch all other exceptions that may arise
        return f"Unexpected error: {str(e)}"

def detect_ql_printers(output, system):
    ql_keywords = ["QL", "Brother"]
    printers = []

    if system == "Darwin":  # macOS-specific
        # Look for Brother QL printer in the system_profiler output
        for line in output.splitlines():
            if any(keyword in line for keyword in ql_keywords):
                printer_name = line.strip()  # Capture printer name
                printers.append({
                    "platform": system.lower(),
                    "printer_name": printer_name,
                    "driver": None,  # No specific driver info for now
                    "setup_required": False  # Assuming setup is not required if the printer is detected
                })

    else:
        # Use existing code for non-macOS systems
        ql_lines = [line.strip() for line in output.splitlines() if any(k in line for k in ql_keywords)]
        for line in ql_lines:
            match = re.search(r'Brother.*QL-\d+\w*', line)
            printer_name = match.group(0) if match else "Brother QL Printer"
            printers.append({
                "platform": system.lower(),
                "printer_name": printer_name,
                "driver": None,
                "setup_required": True
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
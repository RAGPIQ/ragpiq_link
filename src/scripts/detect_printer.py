#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
from typing import Any, Dict, List, Tuple, Union

DEBUG = os.getenv("RAGPIQ_DEBUG", "").lower() in ("1", "true", "yes")

QL_VENDOR_IDS = {"04F9"}  # Brother
QL_NAME_HINTS = ("Brother", "QL")  # quick filter for names

def dprint(*args, **kwargs):
    if DEBUG:
        print("[detect_printer]", *args, **kwargs, flush=True)

def handle_sigterm(sig, frame):
    print("Watcher received SIGTERM, exiting.", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)


# ----------------------------
# Platform helpers
# ----------------------------

def run_powershell(ps_script: str) -> str:
    """Run a PowerShell script and return stdout (text)."""
    return subprocess.check_output(
        ["powershell", "-NoProfile", "-Command", ps_script],
        text=True,
        stderr=subprocess.STDOUT,
    )

def safe_json_loads(s: str) -> Union[dict, list, None]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


# ----------------------------
# Windows: enumerate USB PnP + driver provider
# ----------------------------

def get_windows_ql_devices() -> List[Dict[str, Any]]:
    """
    Return list of dicts with keys:
      FriendlyName, Class, Status, InstanceId, DriverProviderName
    Only includes devices that look like Brother QL (by name or VID_04F9).
    """
    # Filter by USB bus + Brother/QL hints OR VID_04F9
    ps = r"""
$devs = Get-PnpDevice -PresentOnly |
    Where-Object {
        $_.InstanceId -like 'USB*' -and (
            $_.FriendlyName -like '*Brother*' -or
            $_.FriendlyName -like '*QL*' -or
            $_.InstanceId -match 'VID_04F9'
        )
    }

$result = foreach ($d in $devs) {
    $prov = $null
    try { $prov = (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_DriverProvider').Data } catch { }

    [pscustomobject]@{
        FriendlyName       = $d.FriendlyName
        Class              = $d.Class
        Status             = $d.Status
        InstanceId         = $d.InstanceId
        DriverProviderName = $prov
    }
}

$result | ConvertTo-Json -Depth 4
""".strip()

    try:
        out = run_powershell(ps)
    except subprocess.CalledProcessError as e:
        dprint("PowerShell error:", e.output)
        return []

    data = safe_json_loads(out)
    if data is None:
        return []

    # Normalize to list
    return data if isinstance(data, list) else [data]


def windows_setup_required(devs: List[Dict[str, Any]]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Decide if setup is required:
      - OK if DriverProviderName looks like libusbK or WinUSB (some stacks report this way).
      - Otherwise setup_required = True.
    Returns (setup_required, chosen_printer_name, raw_device_dict)
    """
    if not devs:
        return True, "", {}

    # Pick the "most QL-looking" device (prefer names that actually contain QL)
    def score(d: Dict[str, Any]) -> int:
        name = (d.get("FriendlyName") or "").lower()
        inst = (d.get("InstanceId") or "").lower()
        s = 0
        if "ql" in name:
            s += 5
        if "brother" in name:
            s += 3
        if "vid_04f9" in inst:
            s += 2
        return s

    devs_sorted = sorted(devs, key=score, reverse=True)
    chosen = devs_sorted[0]
    printer_name = (chosen.get("FriendlyName") or "").strip() or "Brother QL Printer"

    # Determine driver provider
    prov = (chosen.get("DriverProviderName") or "").lower()
    friendly = (chosen.get("FriendlyName") or "").lower()

    # Acceptable providers/markers
    ok_markers = ("libusbk", "winusb", "libusb-win32")  # be generous
    is_ok = any(m in prov for m in ok_markers) or any(m in friendly for m in ok_markers)

    dprint("Chosen device:", json.dumps(chosen, indent=2))
    dprint("Driver OK?", is_ok, "Provider:", prov)

    return (not is_ok), printer_name, chosen


# ----------------------------
# macOS: system_profiler parsing
# ----------------------------

def scan_usb_devices_macos() -> str:
    try:
        return subprocess.check_output(
            ["system_profiler", "SPUSBDataType"],
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        # Suppress noisy plugin errors common on CI
        if "IOCreatePlugInInterfaceForService failed" in (e.stderr or ""):
            return ""
        return ""

def parse_macos_system_profiler(text: str) -> List[Dict[str, str]]:
    """
    Parse system_profiler output into blocks; pick ones that look like Brother/QL.
    Returns list of dicts with "name", "vendor_id", "product_id".
    """
    blocks = re.split(r"\n(?=\s{2,}\S)", text or "")
    results = []
    for b in blocks:
        name_match = re.search(r"^\s*(.+):\s*$", b, re.MULTILINE)
        if not name_match:
            continue
        name = name_match.group(1).strip()
        vendor_match = re.search(r"Vendor ID:\s*0x([0-9a-fA-F]+)", b)
        product_match = re.search(r"Product ID:\s*0x([0-9a-fA-F]+)", b)
        if any(h in name for h in QL_NAME_HINTS) or (vendor_match and vendor_match.group(1).upper() in QL_VENDOR_IDS):
            results.append({
                "name": name,
                "vendor_id": vendor_match.group(1).upper() if vendor_match else "",
                "product_id": product_match.group(1).upper() if product_match else "",
            })
    return results


# ----------------------------
# Linux: lsusb parsing (best-effort)
# ----------------------------

def scan_usb_devices_linux() -> str:
    try:
        return subprocess.check_output(["lsusb"], text=True)
    except Exception:
        return ""

def parse_linux_lsusb(text: str) -> List[Dict[str, str]]:
    matches = []
    for line in (text or "").splitlines():
        if any(h.lower() in line.lower() for h in QL_NAME_HINTS) or "04f9:" in line.lower():
            matches.append({"line": line})
    return matches


# ----------------------------
# Main detection per platform
# ----------------------------

def detect_printers() -> List[Dict[str, Any]]:
    system = platform.system()
    printers: List[Dict[str, Any]] = []

    if system == "Windows":
        devs = get_windows_ql_devices()
        setup_required, printer_name, chosen = windows_setup_required(devs)
        if devs:
            printers.append({
                "platform": "windows",
                "printer_name": printer_name,
                "driver": {
                    "provider": chosen.get("DriverProviderName"),
                    "instanceId": chosen.get("InstanceId"),
                    "status": chosen.get("Status"),
                },
                "setup_required": setup_required,
            })

    elif system == "Darwin":
        sp_text = scan_usb_devices_macos()
        hits = parse_macos_system_profiler(sp_text)
        for h in hits:
            # No libusbK concept on macOS; if we see it, assume OK
            printers.append({
                "platform": "darwin",
                "printer_name": h["name"],
                "driver": {"vendor_id": h["vendor_id"], "product_id": h["product_id"]},
                "setup_required": False,
            })

    else:
        # Linux / others: best-effort via lsusb
        ls = scan_usb_devices_linux()
        hits = parse_linux_lsusb(ls)
        for h in hits:
            printers.append({
                "platform": system.lower(),
                "printer_name": "Brother QL Printer",
                "driver": {"raw": h.get("line")},
                # Most distros with pyusb/libusb are fine; mark as not required.
                "setup_required": False,
            })

    return printers


# ----------------------------
# Watch loop (prints JSON on change)
# ----------------------------

def watch_printers(poll_interval: float = 3.0):
    previous_state = None

    while True:
        printers = detect_printers()

        payload = {
            "printer_name": printers[0]["printer_name"] if printers else "",
            "setup_required": printers[0]["setup_required"] if printers else True,
            # Bonus debug fields (safe to remove if you want the old shape)
            "platform": printers[0]["platform"] if printers else platform.system().lower(),
            "driver": printers[0].get("driver") if printers else None,
        }

        state = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        if state != previous_state:
            print(state, flush=True)
            previous_state = state

        time.sleep(poll_interval)


if __name__ == "__main__":
    try:
        poll = float(os.getenv("RAGPIQ_POLL_SEC", "3"))
    except Exception:
        poll = 3.0
    watch_printers(poll_interval=poll)
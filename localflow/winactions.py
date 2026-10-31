"""The Windows side of Commands: list installed apps, launch them, find their windows.

The Commands module calls these through its `actions` object; nothing here decides
what a Command means.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
from pathlib import Path

from commands import Target, normalise

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
NO_WINDOW = 0x08000000           # CREATE_NO_WINDOW: no console flashes up
SW_RESTORE, SW_SHOW = 9, 5
VK_MENU, KEYUP = 0x12, 0x2


def load_catalog():
    """Every app in the Start menu (Store apps included), as Targets keyed by launch ID."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
        capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    rows = json.loads(out.stdout or "[]")
    rows = [rows] if isinstance(rows, dict) else rows
    return [Target(r["AppID"], r["Name"]) for r in rows if r.get("Name") and r.get("AppID")]


def _exe_of(hwnd):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf, size = ctypes.create_unicode_buffer(512), wt.DWORD(512)
        kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return buf.value
    finally:
        kernel32.CloseHandle(h)


def _class_of(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _title_of(hwnd):
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def app_windows():
    """Visible top-level windows with a title, as (hwnd, exe path, class, title)."""
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.GetWindow(hwnd, 4):  # GW_OWNER: skip popups
            title = _title_of(hwnd)
            if title:
                found.append((hwnd, _exe_of(hwnd), _class_of(hwnd), title))
        return True

    user32.EnumWindows(each, 0)
    return found


def _belongs_to(target, exe, cls, title):
    """Does this window belong to the app? Matched by exe name, or by the app name
    ending the window title ("Inbox - Google Chrome")."""
    stem = normalise(Path(exe).stem).replace(" ", "")
    if stem == "explorer":
        return cls == "CabinetWClass" and normalise(target.name) == "file explorer"
    name = normalise(target.name)
    words = name.split()
    return (stem and (stem == name.replace(" ", "") or stem == words[-1] or stem in target.id.lower())) \
        or normalise(title).endswith(name)


def windows_of(target):
    return [w for w in app_windows() if _belongs_to(target, *w[1:])]


def bring_forward(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    else:
        user32.ShowWindow(hwnd, SW_SHOW)
    # Windows only lets the app that last got input take focus; a tap of Alt counts.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYUP, 0)
    user32.SetForegroundWindow(hwnd)


class Actions:
    def switch_to(self, target):
        wins = windows_of(target)
        if not wins:
            return False
        bring_forward(wins[0][0])
        return True

    def launch(self, target):
        os.startfile("shell:AppsFolder\\" + target.id)

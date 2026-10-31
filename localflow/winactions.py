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


# ------------------------------------------------------------------ icons
# The same icon the Start menu or Explorer shows, asked from the Windows shell
# (IShellItemImageFactory), so every installed app, folder and drive looks native.

class _GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("type", ctypes.c_long), ("w", ctypes.c_long), ("h", ctypes.c_long), ("wb", ctypes.c_long),
                ("planes", ctypes.c_ushort), ("bpp", ctypes.c_ushort), ("bits", ctypes.c_void_p)]


class _BIH(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("w", ctypes.c_long), ("h", ctypes.c_long), ("planes", ctypes.c_ushort),
                ("bpp", ctypes.c_ushort), ("comp", ctypes.c_uint32), ("img", ctypes.c_uint32), ("xp", ctypes.c_long),
                ("yp", ctypes.c_long), ("used", ctypes.c_uint32), ("imp", ctypes.c_uint32)]


ole32, shell32, gdi32 = ctypes.windll.ole32, ctypes.windll.shell32, ctypes.windll.gdi32
shell32.SHCreateItemFromParsingName.argtypes = [wt.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
user32.GetDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_IID_IMAGE_FACTORY = _GUID()
ole32.CLSIDFromString("{bcc18b79-ba16-442f-80c4-8a59c30c463b}", ctypes.byref(_IID_IMAGE_FACTORY))
_GetImage = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, _SIZE, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)


def shell_path(target_or_path):
    """What the shell parses: an installed app's AppsFolder entry, or a file/folder path."""
    if isinstance(target_or_path, Target):
        return "shell:AppsFolder\\" + target_or_path.id
    return str(target_or_path)


def icon_image(target_or_path, size):
    """The shell's icon as a PIL RGBA image (straight alpha), or None."""
    from PIL import Image
    import numpy as np
    ole32.CoInitialize(None)
    obj = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(shell_path(target_or_path), None, ctypes.byref(_IID_IMAGE_FACTORY),
                                          ctypes.byref(obj)) != 0 or not obj:
        return None
    vtbl = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    hbmp = ctypes.c_void_p()
    try:
        # SIIGBF_BIGGERSIZEOK | SIIGBF_ICONONLY: the icon, never a thumbnail of the content
        if _GetImage(vtbl[3])(obj, _SIZE(size, size), 0x1 | 0x4, ctypes.byref(hbmp)) != 0:
            return None
    except OSError:
        return None
    finally:
        _Release(vtbl[2])(obj)
    try:
        bm = _BITMAP()
        gdi32.GetObjectW(hbmp, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.w, abs(bm.h)
        bih = _BIH(ctypes.sizeof(_BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)  # top-down BGRA
        buf = ctypes.create_string_buffer(w * h * 4)
        dc = user32.GetDC(None)
        gdi32.GetDIBits(dc, hbmp, 0, h, buf, ctypes.byref(bih), 0)
        user32.ReleaseDC(None, dc)
    finally:
        gdi32.DeleteObject(hbmp)
    a = np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0, 3]].astype(np.float32)
    alpha = a[:, :, 3:4]
    a[:, :, :3] = np.where(alpha > 0, np.minimum(255, a[:, :, :3] * 255 / np.maximum(alpha, 1)), 0)  # un-premultiply
    im = Image.fromarray(a.astype(np.uint8), "RGBA")
    return im if im.size == (size, size) else im.resize((size, size), Image.LANCZOS)


class Actions:
    def switch_to(self, target):
        wins = windows_of(target)
        if not wins:
            return False
        bring_forward(wins[0][0])
        return True

    def launch(self, target):
        os.startfile("shell:AppsFolder\\" + target.id)

"""The Windows side of Commands: list installed apps, launch them, find their windows.

The Commands module calls these through its `actions` object; nothing here decides
what a Command means.
"""
import ctypes
import ctypes.wintypes as wt
import codecs
import hashlib
import json
import os
import subprocess
import winreg
from pathlib import Path

from commands import Target, normalise

user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
NO_WINDOW = 0x08000000           # CREATE_NO_WINDOW: no console flashes up
SW_RESTORE, SW_SHOW = 9, 5
VK_MENU, KEYUP = 0x12, 0x2


SETTINGS_PAGES = {"Bluetooth": "bluetooth", "Display": "display", "Sound": "sound", "Wi-Fi": "network-wifi",
                  "Network": "network", "Apps": "appsfeatures", "Windows Update": "windowsupdate",
                  "Notifications": "notifications", "Personalization": "personalization",
                  "Power": "powersleep", "Mouse": "mousetouchpad", "Privacy": "privacy",
                  "Storage": "storagesense", "Default apps": "defaultapps"}
WEBSITES = {
    "YouTube": "https://www.youtube.com", "Gmail": "https://mail.google.com",
    "Google": "https://www.google.com", "LinkedIn": "https://www.linkedin.com/feed/",
    "GitHub": "https://github.com", "Reddit": "https://www.reddit.com",
    "Instagram": "https://www.instagram.com", "Facebook": "https://www.facebook.com",
    "X": "https://x.com", "WhatsApp": "https://web.whatsapp.com",
    "Google Drive": "https://drive.google.com", "Google Calendar": "https://calendar.google.com",
    "Notion": "https://www.notion.so",
}


def builtin_places():
    """Places every PC has: the main user folders, This PC, each drive, common
    Settings pages and a few websites."""
    places = [Target(f"folder:{n.lower()}", n, "folder", f"shell:{shell}") for n, shell in
              (("Downloads", "Downloads"), ("Documents", "Personal"), ("Desktop", "Desktop"),
               ("Pictures", "My Pictures"), ("Music", "My Music"), ("Videos", "My Video"))]
    places.append(Target("folder:thispc", "This PC", "folder", "shell:MyComputerFolder"))
    for letter in "CDEFGH":
        if os.path.exists(f"{letter}:\\"):
            places.append(Target(f"drive:{letter.lower()}", f"{letter} drive", "folder", f"{letter}:\\"))
    places += [Target(f"settings:{page}", f"{name} settings", "settings", f"ms-settings:{page}")
               for name, page in SETTINGS_PAGES.items()]
    places += [Target(f"site:{name.lower()}", name, "website", url) for name, url in WEBSITES.items()]
    return places


def user_targets(user_apps=()):
    """Path-based apps the user added in Commands settings."""
    out = []
    for item in user_apps:
        path = os.path.abspath(os.path.expandvars(item.get("path", "")))
        name = item.get("name", "").strip() or Path(path).stem
        if path and Path(path).suffix.lower() in (".exe", ".bat", ".lnk") and os.path.exists(path):
            key = hashlib.sha1(os.path.normcase(path).encode("utf-8")).hexdigest()[:16]
            out.append(Target(f"user:{key}", name, "app", path))
    return out


def custom_places(user_places=()):
    """Folders and websites the user explicitly added in Commands settings."""
    out = []
    for item in user_places:
        kind, path = item.get("kind"), item.get("path", "").strip()
        name = item.get("name", "").strip()
        if kind == "folder":
            path = os.path.abspath(os.path.expandvars(path))
            valid = os.path.isdir(path)
        else:
            valid = kind == "website" and path.lower().startswith(("http://", "https://"))
        if name and valid:
            key = hashlib.sha1(f"{kind}:{os.path.normcase(path)}".encode("utf-8")).hexdigest()[:16]
            out.append(Target(f"user-place:{key}", name, kind, path))
    return out


def load_catalog(user_apps=(), user_places=()):
    """Every app in the Start menu (Store apps included), as Targets keyed by launch ID,
    then the built-in Places."""
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
        capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
    rows = json.loads(out.stdout or "[]")
    rows = [rows] if isinstance(rows, dict) else rows
    return ([Target(r["AppID"], r["Name"]) for r in rows if r.get("Name") and r.get("AppID")]
            + user_targets(user_apps) + custom_places(user_places) + builtin_places())


def windows_usage(catalog):
    """Best-effort ranking from Explorer's per-user UserAssist run counts.

    UserAssist is optional and its entries are opaque, so failure simply means no
    Windows-use tie-breaker. Voice-use counts remain authoritative.
    """
    seen = []
    root = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, root) as parent:
            for i in range(winreg.QueryInfoKey(parent)[0]):
                guid = winreg.EnumKey(parent, i)
                try:
                    with winreg.OpenKey(parent, guid + r"\Count") as count:
                        for j in range(winreg.QueryInfoKey(count)[1]):
                            name, data, _ = winreg.EnumValue(count, j)
                            decoded = codecs.decode(name, "rot_13").lower()
                            runs = int.from_bytes(data[4:8], "little") if isinstance(data, bytes) and len(data) >= 8 else 1
                            seen.append((decoded, runs))
                except OSError:
                    continue
    except OSError:
        return {}
    scores = {}
    for target in catalog:
        if target.kind != "app":
            continue
        needles = {target.id.lower(), normalise(target.name).replace(" ", "")}
        if target.path:
            needles.add(Path(target.path).stem.lower())
        score = sum(runs for name, runs in seen if any(n and n in name.replace(" ", "") for n in needles))
        if score:
            scores[target.id] = score
    return scores


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
    path_stem = normalise(Path(target.path).stem).replace(" ", "") if target.path else ""
    return (stem and (stem == path_stem or stem == name.replace(" ", "") or stem == words[-1] or stem in target.id.lower())) \
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


NOT_TYPEABLE = {"ButtonControl", "HyperlinkControl", "ListControl", "ListItemControl", "MenuItemControl",
                "MenuControl", "TabItemControl", "TreeItemControl", "TreeControl", "WindowControl", "ImageControl",
                "TextControl", "CheckBoxControl", "RadioButtonControl", "SliderControl", "ToolBarControl"}


def classify_focus(control_type, editable=None, caret=False):
    """Can you type where the focus is? True, False, or None when it's unclear
    (a pane or group): unclear stays Dictation, so no words are lost."""
    if caret or control_type in ("EditControl", "ComboBoxControl"):
        return True
    if control_type == "DocumentControl":
        return editable          # an editor (True), a web page or player (False)
    if control_type in NOT_TYPEABLE:
        return False             # a link, button, list, the desktop: nowhere to type
    return None


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("flags", wt.DWORD), ("active", wt.HWND), ("focus", wt.HWND), ("capture", wt.HWND),
                ("menu", wt.HWND), ("move", wt.HWND), ("caret", wt.HWND), ("rc", wt.RECT)]


def focus_is_text_field():
    """Is the keyboard focus somewhere you can type? See classify_focus."""
    try:
        info = _GUITHREADINFO(cb=ctypes.sizeof(_GUITHREADINFO))
        caret = bool(user32.GetGUIThreadInfo(0, ctypes.byref(info)) and info.caret)
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            ctrl = auto.GetFocusedControl()
            if ctrl is None:
                return classify_focus("", caret=caret)
            editable = None
            if ctrl.ControlTypeName == "DocumentControl":
                try:
                    editable = not ctrl.GetValuePattern().IsReadOnly
                except Exception:
                    editable = None
            return classify_focus(ctrl.ControlTypeName, editable, caret)
    except Exception:
        return None


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


SETTINGS_APP = "windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel"


def shell_path(target_or_path):
    """What the shell parses for an icon: an app's AppsFolder entry, a folder, or None."""
    if isinstance(target_or_path, Target):
        t = target_or_path
        if t.kind == "app":
            return t.path or "shell:AppsFolder\\" + t.id
        if t.kind == "settings":
            return "shell:AppsFolder\\" + SETTINGS_APP
        return t.path if t.kind == "folder" else None
    return str(target_or_path)


def icon_image(target_or_path, size):
    """The shell's icon as a PIL RGBA image (straight alpha), or None."""
    from PIL import Image
    import numpy as np
    path = shell_path(target_or_path)
    if not path:
        return None
    ole32.CoInitialize(None)
    obj = ctypes.c_void_p()
    if shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(_IID_IMAGE_FACTORY),
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


# ------------------------------------------------------------- media and volume

def _media_sessions():
    """(current session, all sessions) from the Windows media pop-up. Works with any
    player that shows there (Spotify Free included), offline."""
    import asyncio
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager

    async def get():
        m = await Manager.request_async()
        return m.get_current_session(), list(m.get_sessions())
    return asyncio.run(get())


def _run_media(session, action):
    import asyncio
    call = {"pause": session.try_pause_async, "play": session.try_play_async,
            "next": session.try_skip_next_async, "previous": session.try_skip_previous_async}[action]

    async def go():
        return await call()
    return asyncio.run(go())


def _speakers():
    import comtypes
    from pycaw.pycaw import AudioUtilities
    comtypes.CoInitialize()
    return AudioUtilities.GetSpeakers().EndpointVolume


class Actions:
    def __init__(self, catalog=lambda: []):
        self.catalog = catalog   # the current Targets, to name media players

    def media(self, action, target=None):
        """Play/pause/next/previous on the named player, else whatever the media pop-up
        shows. Returns the player's name, or None when nothing is playing."""
        current, sessions = _media_sessions()
        if target:
            session = next((s for s in sessions if s.source_app_user_model_id == target.id), None)
        else:
            session = current
        if not session:
            return None
        _run_media(session, action)
        aumid = session.source_app_user_model_id
        app = next((t for t in self.catalog() if t.id == aumid), None)
        return app.name if app else Path(aumid.split("!")[0]).stem.split("_")[0]

    def set_volume(self, level):
        _speakers().SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100, None)

    def change_volume(self, step):
        ep = _speakers()
        level = round(ep.GetMasterVolumeLevelScalar() * 100) + step
        level = max(0, min(100, level))
        ep.SetMasterVolumeLevelScalar(level / 100, None)
        return level

    def volume(self):
        return round(_speakers().GetMasterVolumeLevelScalar() * 100)

    def mute(self, on):
        _speakers().SetMute(1 if on else 0, None)

    def switch_to(self, target):
        wins = windows_of(target)
        if not wins:
            return False
        bring_forward(wins[0][0])
        return True

    def launch(self, target):
        os.startfile(target.path or "shell:AppsFolder\\" + target.id)

    def running_apps(self, catalog):
        """[(Target, [window titles])] for apps with windows open. Each window belongs to
        the first app that claims it, so a duplicate Start entry doesn't count twice."""
        wins, found = app_windows(), {}
        for t in catalog:
            mine = [w for w in wins if w[0] not in found and _belongs_to(t, *w[1:])]
            for w in mine:
                found[w[0]] = t
        out = {}
        for hwnd, exe, cls, title in wins:
            if hwnd in found:
                out.setdefault(found[hwnd], []).append(title)
        return list(out.items())

    def close(self, target):
        """Politely, like clicking X: apps with unsaved work still ask."""
        for hwnd, *_ in windows_of(target):
            user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def minimise(self, target):
        for hwnd, *_ in windows_of(target):
            user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE

    def minimise_all(self):
        user32.keybd_event(0x5B, 0, 0, 0)        # Win+M
        user32.keybd_event(0x4D, 0, 0, 0)
        user32.keybd_event(0x4D, 0, KEYUP, 0)
        user32.keybd_event(0x5B, 0, KEYUP, 0)

    def open_place(self, target):
        os.startfile(target.path)

    def open_url(self, url):
        os.startfile(url)   # default browser for web links, the Spotify app for spotify:

"""Real operating-system input for the Humanize mode (Windows): the actual mouse cursor and the actual keyboard.

The browser is not told to "dispatch" anything: the cursor really travels over the screen, buttons are pressed with
SendInput, text is typed key by key (Unicode key events) or pasted with a real Ctrl+V. Everything here uses only
ctypes, no extra packages. On other systems `available()` is False and Humanize falls back to normal page actions.

`page_to_screen` / `screen_to_page` convert between page (viewport) coordinates and physical screen pixels from the
window metrics the page reports (window.screenX, outerWidth, devicePixelRatio ...). They assume a browser zoom of 100%.
"""
import sys
import time
from typing import Dict, Iterable, Optional, Tuple

IS_WINDOWS = sys.platform == "win32"

VK_BACK, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU = 0x08, 0x0D, 0x10, 0x11, 0x12
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
CF_UNICODETEXT = 13
SW_RESTORE = 9


def available() -> bool:
    return IS_WINDOWS


def _origin(m: Dict) -> Tuple[float, float]:
    """Screen position (CSS px) of the top-left corner of the page area."""
    border = max(0.0, (m["ow"] - m["iw"]) / 2.0)
    return m["sx"] + border, m["sy"] + max(0.0, m["oh"] - m["ih"] - border)


def page_to_screen(m: Dict, x: float, y: float) -> Tuple[float, float]:
    ox, oy = _origin(m)
    d = m.get("dpr") or 1.0
    return (ox + x) * d, (oy + y) * d


def screen_to_page(m: Dict, sx: float, sy: float) -> Tuple[float, float]:
    ox, oy = _origin(m)
    d = m.get("dpr") or 1.0
    return sx / d - ox, sy / d - oy


class OsInput:
    """Thin wrapper over user32 (Windows only)."""

    def __init__(self):
        if not IS_WINDOWS:
            raise RuntimeError("OS input is available on Windows only")
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        self.u32 = ctypes.windll.user32
        self.k32 = ctypes.windll.kernel32
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixels
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                pass
        ULONG_PTR = ctypes.c_size_t

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("u", _U)]

        self._MI, self._KI, self._INPUT = MOUSEINPUT, KEYBDINPUT, INPUT
        self.u32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]

    # ---- low level
    def _send(self, inp) -> None:
        self.u32.SendInput(1, self.ct.byref(inp), self.ct.sizeof(self._INPUT))

    def _key(self, vk: int = 0, scan: int = 0, flags: int = 0) -> None:
        inp = self._INPUT(type=1)
        inp.u.ki = self._KI(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
        self._send(inp)

    # ---- mouse
    def cursor(self) -> Tuple[float, float]:
        from ctypes import wintypes
        pt = wintypes.POINT()
        self.u32.GetCursorPos(self.ct.byref(pt))
        return float(pt.x), float(pt.y)

    def move(self, x: float, y: float) -> None:
        self.u32.SetCursorPos(int(round(x)), int(round(y)))

    def button(self, down: bool) -> None:
        inp = self._INPUT(type=0)
        inp.u.mi = self._MI(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=0)
        self._send(inp)

    # ---- keyboard
    def type_char(self, ch: str) -> None:
        """One character as a Unicode key press (works for any language)."""
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):
            code = data[i] | (data[i + 1] << 8)
            self._key(0, code, KEYEVENTF_UNICODE)
            time.sleep(0.004)
            self._key(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)

    def chord(self, mod_vk: int, vk: int) -> None:
        self.hotkey(mod_vk, vk)

    def hotkey(self, *vks: int) -> None:
        """Press a sequence of virtual keys together and release in reverse order."""
        for vk in vks:
            self._key(vk)
            time.sleep(0.025)
        for vk in reversed(vks):
            self._key(vk, 0, KEYEVENTF_KEYUP)
            time.sleep(0.02)

    def press(self, vk: int) -> None:
        self.hotkey(vk)

    def shift_enter(self) -> None:
        self.chord(VK_SHIFT, VK_RETURN)

    def select_all_delete(self) -> None:
        self.chord(VK_CONTROL, 0x41)
        time.sleep(0.08)
        self._key(VK_BACK)
        time.sleep(0.03)
        self._key(VK_BACK, 0, KEYEVENTF_KEYUP)

    def paste(self, text: str) -> None:
        self.set_clipboard(text)
        time.sleep(0.05)
        self.chord(VK_CONTROL, 0x56)

    def set_clipboard(self, text: str) -> None:
        ct, u32, k32 = self.ct, self.u32, self.k32
        k32.GlobalAlloc.restype = ct.c_void_p
        k32.GlobalAlloc.argtypes = [ct.c_uint, ct.c_size_t]
        k32.GlobalLock.restype = ct.c_void_p
        k32.GlobalLock.argtypes = [ct.c_void_p]
        k32.GlobalUnlock.argtypes = [ct.c_void_p]
        u32.OpenClipboard.argtypes = [ct.c_void_p]
        u32.SetClipboardData.argtypes = [ct.c_uint, ct.c_void_p]
        u32.SetClipboardData.restype = ct.c_void_p
        data = (text.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")
        for _ in range(20):
            if u32.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("clipboard is busy")
        try:
            u32.EmptyClipboard()
            h = k32.GlobalAlloc(0x0002, len(data))
            p = k32.GlobalLock(h)
            ct.memmove(p, data, len(data))
            k32.GlobalUnlock(h)
            u32.SetClipboardData(CF_UNICODETEXT, h)
        finally:
            u32.CloseClipboard()

    def get_clipboard(self) -> str:
        """Read Unicode text from the Windows clipboard (returns '' if empty or unavailable)."""
        ct, u32, k32 = self.ct, self.u32, self.k32
        k32.GlobalLock.restype = ct.c_void_p
        k32.GlobalLock.argtypes = [ct.c_void_p]
        k32.GlobalUnlock.argtypes = [ct.c_void_p]
        u32.OpenClipboard.argtypes = [ct.c_void_p]
        u32.GetClipboardData.argtypes = [ct.c_uint]
        u32.GetClipboardData.restype = ct.c_void_p
        for _ in range(20):
            if u32.OpenClipboard(None):
                break
            time.sleep(0.05)
        else:
            return ""
        try:
            h = u32.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            p = k32.GlobalLock(h)
            if not p:
                return ""
            try:
                text = ct.wstring_at(p)
                return text.replace("\r\n", "\n")
            finally:
                k32.GlobalUnlock(h)
        finally:
            u32.CloseClipboard()

    # ---- windows
    def find_window(self, title_hints: Iterable[str]) -> Optional[int]:
        """Find a visible Chrome window whose title matches one of title_hints (or any Chrome window as fallback)."""
        ct, u32 = self.ct, self.u32
        from ctypes import wintypes

        hints = [h.lower() for h in title_hints if h]
        matched: list[int] = []
        any_chrome: list[int] = []

        WNDENUMPROC = ct.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def cb(hwnd, _lp):
            if not u32.IsWindowVisible(hwnd):
                return True
            cls_buf = ct.create_unicode_buffer(64)
            u32.GetClassNameW(hwnd, cls_buf, 64)
            if cls_buf.value != "Chrome_WidgetWin_1":
                return True
            length = u32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buf = ct.create_unicode_buffer(length + 1)
            u32.GetWindowTextW(hwnd, title_buf, length + 1)
            title = title_buf.value.lower()
            if "chrome" not in title and not any(h in title for h in hints):
                return True
            if any(h in title for h in hints):
                matched.append(int(hwnd))
            else:
                any_chrome.append(int(hwnd))
            return True

        u32.EnumWindows(WNDENUMPROC(cb), 0)
        if matched:
            return matched[0]
        return any_chrome[0] if any_chrome else None

    def activate(self, hwnd: int) -> bool:
        """Restore and bring `hwnd` to the foreground."""
        u32 = self.u32
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.15)
        for _ in range(3):
            if int(u32.GetForegroundWindow() or 0) == int(hwnd):
                return True
            # Pressing Alt lets Windows allow SetForegroundWindow from a background process
            self._key(VK_MENU)
            self._key(VK_MENU, 0, KEYEVENTF_KEYUP)
            u32.SetForegroundWindow(hwnd)
            u32.BringWindowToTop(hwnd)
            time.sleep(0.12)
        return int(u32.GetForegroundWindow() or 0) == int(hwnd)

    def window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """Return (left, top, right, bottom) of `hwnd` in physical screen pixels."""
        from ctypes import wintypes

        rect = wintypes.RECT()
        self.u32.GetWindowRect(hwnd, self.ct.byref(rect))
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


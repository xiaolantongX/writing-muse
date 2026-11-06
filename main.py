# -*- coding: utf-8 -*-
"""写作灵感 Muse —— 桌面悬浮写作助手（DeepSeek 云端版）。

触发方式：
1. 悬浮球：单击开/收完整面板，双击立即生成；
2. 全局快捷键：Ctrl+Space 连按两下，读取光标上下文立即生成；
3. 鼠标中键：选中文字后按中键生成（没选中则原样放行）；
4. 托盘图标：从剪贴板生成，或打开完整面板。

V2 相比 MVP：悬浮球、灵感弹层、B 方案快捷键、X 文章文风、设置面板、
6 种写作模式、候选角度标签、个人文风样本、历史记录、粘贴目标校验等。
"""
from __future__ import annotations

import copy
import ctypes
import math
import re
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QMimeData,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QGraphicsDropShadowEffect,
)

from config import (
    DEFAULT_CONFIG,
    load_config,
    load_history,
    normalize_config,
    push_history,
    save_config,
    save_history,
)
from muse_core import (
    MODES,
    STYLES,
    estimate_cost,
    friendly_error,
    generate,
    prepare_context,
)
from pynput import mouse

# ---------------------------------------------------------------------------
# Windows 输入钩子 / 窗口信息
# ---------------------------------------------------------------------------
IS_WINDOWS = sys.platform == "win32"

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_GETTEXT, WM_GETTEXTLENGTH = 0x000D, 0x000E
EM_GETSEL = 0x00B0
SMTO_ABORTIFHUNG = 0x0002
LLMHF_INJECTED = 0x01
LLMHF_LOWER_IL_INJECTED = 0x02
LLKHF_INJECTED = 0x10
LLKHF_LOWER_IL_INJECTED = 0x02
ERROR_ALREADY_EXISTS = 183

TERMINAL_CLASSES = {
    "consolewindowclass",
    "cascadia_hosting_window_class",
    "mintty",
    "putty",
    "kitty",
    "alacritty",
    "org.wezfurlong.wezterm",
}


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


if IS_WINDOWS:
    user32 = ctypes.windll.user32
    imm32 = ctypes.windll.imm32
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetGUIThreadInfo.argtypes = [
        wintypes.DWORD,
        ctypes.POINTER(GUITHREADINFO),
    ]
    user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
    user32.GetKeyboardLayout.restype = ctypes.c_void_p
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL

    imm32.ImmGetContext.argtypes = [wintypes.HWND]
    imm32.ImmGetContext.restype = wintypes.HANDLE
    imm32.ImmReleaseContext.argtypes = [wintypes.HWND, wintypes.HANDLE]
    imm32.ImmGetOpenStatus.argtypes = [wintypes.HANDLE]
    imm32.ImmGetOpenStatus.restype = wintypes.BOOL
    imm32.ImmGetConversionStatus.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    imm32.ImmGetConversionStatus.restype = wintypes.BOOL
    imm32.ImmIsIME.argtypes = [ctypes.c_void_p]
    imm32.ImmIsIME.restype = wintypes.BOOL

    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t

    kernel32.CreateMutexW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
else:  # pragma: no cover - 仅 Windows 支持
    user32 = None
    imm32 = None
    kernel32 = None

CFG = load_config()


def get_foreground_hwnd() -> int:
    if not IS_WINDOWS:
        return 0
    try:
        return int(user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def get_foreground_title() -> str:
    if not IS_WINDOWS:
        return ""
    try:
        hwnd = get_foreground_hwnd()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


def get_window_class(hwnd: int) -> str:
    if not IS_WINDOWS or not hwnd:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def get_foreground_class() -> str:
    return get_window_class(get_foreground_hwnd())


def get_focus_hwnd() -> int:
    """前台窗口里真正接收键盘焦点的子控件（编辑框常常是子窗口）。"""
    if not IS_WINDOWS:
        return 0
    try:
        hwnd = get_foreground_hwnd()
        if not hwnd:
            return 0
        tid = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
        if tid:
            info = GUITHREADINFO()
            info.cbSize = ctypes.sizeof(GUITHREADINFO)
            if user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndFocus:
                return int(info.hwndFocus)
        return hwnd
    except Exception:
        return 0


def _send_message_timeout(hwnd: int, msg: int, wparam: int, lparam: int, timeout: int = 180) -> int:
    """带超时地向另一个进程的控件发消息，避免对方卡死拖住 Muse。"""
    if not IS_WINDOWS or not hwnd:
        return 0
    try:
        result = ctypes.c_size_t(0)
        ok = user32.SendMessageTimeoutW(
            hwnd,
            msg,
            wparam,
            lparam,
            SMTO_ABORTIFHUNG,
            timeout,
            ctypes.byref(result),
        )
        return int(result.value) if ok else 0
    except Exception:
        return 0


def _read_edit_text_and_selection() -> tuple[str, int, int]:
    """读取标准 Edit/RichEdit 的全文和选区，读不到返回空。"""
    if not IS_WINDOWS:
        return "", 0, 0
    hwnd = get_focus_hwnd()
    if not hwnd or "edit" not in get_window_class(hwnd).lower():
        return "", 0, 0
    length = _send_message_timeout(hwnd, WM_GETTEXTLENGTH, 0, 0)
    if length <= 0 or length > 200_000:
        return "", 0, 0
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = _send_message_timeout(
        hwnd,
        WM_GETTEXT,
        length + 1,
        ctypes.cast(buffer, ctypes.c_void_p).value or 0,
    )
    if copied <= 0:
        return "", 0, 0
    text = buffer.value
    start = wintypes.DWORD(0)
    end = wintypes.DWORD(0)
    result = ctypes.c_size_t(0)
    ok = user32.SendMessageTimeoutW(
        hwnd,
        EM_GETSEL,
        ctypes.addressof(start),
        ctypes.addressof(end),
        SMTO_ABORTIFHUNG,
        180,
        ctypes.byref(result),
    )
    if not ok:
        return text, len(text), len(text)
    start_value = max(0, min(int(start.value), len(text)))
    end_value = max(0, min(int(end.value), len(text)))
    return text, start_value, end_value


def read_edit_context(max_chars: int = 3000) -> str:
    """取选区优先；没有选区就取光标前的文字。中文可用。"""
    text, start, end = _read_edit_text_and_selection()
    if not text:
        return ""
    if end > start:
        return text[start:end][-max_chars:].strip()
    return text[:start][-max_chars:].strip()


def read_edit_selection(max_chars: int = 3000) -> str:
    text, start, end = _read_edit_text_and_selection()
    if not text or end <= start:
        return ""
    return text[start:end][-max_chars:].strip()


def read_edit_text_before_caret(max_chars: int = 1200) -> str:
    """读取标准 Edit/RichEdit 控件里光标前的文字（兼容旧调用）。"""
    text, start, _end = _read_edit_text_and_selection()
    if not text:
        return ""
    return text[:start][-max_chars:].strip()


def get_caret_screen_pos() -> QPoint | None:
    """取当前光标在屏幕上的位置，取不到返回 None。"""
    if not IS_WINDOWS:
        return None
    try:
        hwnd = get_foreground_hwnd()
        if not hwnd:
            return None
        tid = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not tid or not user32.GetGUIThreadInfo(tid, ctypes.byref(info)):
            return None
        if not info.hwndCaret:
            return None
        point = wintypes.POINT(info.rcCaret.left, info.rcCaret.bottom)
        if user32.ClientToScreen(info.hwndCaret, ctypes.byref(point)):
            return QPoint(int(point.x), int(point.y))
    except Exception:
        return None
    return None


def is_terminal_window() -> bool:
    return get_foreground_class().lower() in TERMINAL_CLASSES


def ime_is_open() -> bool:
    """判断前台输入框是否开着中文输入法。

    取不到输入法上下文时，如果当前键盘布局是 IME，也按“开着”处理，
    避免把拼音字母当成正文写进自动引导的缓冲区。
    """
    if not IS_WINDOWS:
        return False
    try:
        hwnd = get_foreground_hwnd()
        if not hwnd:
            return False
        tid = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
        focus = hwnd
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if tid and user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndFocus:
            focus = info.hwndFocus
        himc = imm32.ImmGetContext(focus)
        if himc:
            try:
                if not imm32.ImmGetOpenStatus(himc):
                    return False
                # 中文输入法切到英文模式时，不应该误伤自动引导
                conversion = wintypes.DWORD()
                if imm32.ImmGetConversionStatus(
                    himc, ctypes.byref(conversion), None
                ):
                    return bool(conversion.value & 0x0001)  # IME_CMODE_NATIVE
                return True
            finally:
                imm32.ImmReleaseContext(focus, himc)
        hkl = user32.GetKeyboardLayout(tid)
        return bool(imm32.ImmIsIME(hkl))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 快捷键
# ---------------------------------------------------------------------------
_VK_MODS = {
    0x10: "shift",
    0xA0: "shift",
    0xA1: "shift",
    0x11: "ctrl",
    0xA2: "ctrl",
    0xA3: "ctrl",
    0x12: "alt",
    0xA4: "alt",
    0xA5: "alt",
    0x5B: "win",
    0x5C: "win",
}

_NAMED_VK = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "right": 0x27,
    "up": 0x26,
    "down": 0x28,
}


def parse_hotkey(combo: str) -> tuple[set[str], int | None]:
    """把 "ctrl+alt+m" 解析成 (修饰键集合, 虚拟键码)。"""
    parts = [p.strip().lower() for p in (combo or "").split("+") if p.strip()]
    if not parts:
        return set(), None
    key = parts[-1]
    mods = {p for p in parts[:-1] if p in ("ctrl", "alt", "shift", "win")}
    if len(mods) != len(parts) - 1:
        return set(), None
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key in _NAMED_VK:
        vk = _NAMED_VK[key]
    else:
        match = re.fullmatch(r"f([1-9]|1[0-2])", key)
        if not match:
            return set(), None
        vk = 0x70 + int(match.group(1)) - 1
    if not mods and not key.startswith("f"):
        return set(), None
    return mods, vk


def hotkey_label(combo: str) -> str:
    display = {
        "ctrl": "Ctrl",
        "alt": "Alt",
        "shift": "Shift",
        "win": "Win",
        "space": "Space",
        "enter": "Enter",
        "return": "Enter",
        "tab": "Tab",
        "esc": "Esc",
        "escape": "Esc",
        "backspace": "Backspace",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "pageup": "PageUp",
        "pagedown": "PageDown",
        "left": "Left",
        "right": "Right",
        "up": "Up",
        "down": "Down",
    }
    parts = [display.get(p, p.upper()) for p in (combo or "").split("+") if p]
    return "+".join(parts)


def parse_sequence(sequence: str) -> list[tuple[set[str], int]] | None:
    """把 "ctrl+space,ctrl+space" 解析成步骤列表；任一步无效就返回 None。"""
    parts = [p.strip() for p in (sequence or "").split(",") if p.strip()]
    if not parts or len(parts) > 4:
        return None
    steps: list[tuple[set[str], int]] = []
    for part in parts:
        mods, vk = parse_hotkey(part)
        if vk is None:
            return None
        steps.append((mods, vk))
    return steps


def sequence_label(sequence: str) -> str:
    parts = [hotkey_label(p.strip()) for p in (sequence or "").split(",") if p.strip()]
    if len(parts) == 2 and parts[0] == parts[1]:
        return parts[0] + " ×2"
    return " → ".join(parts)


class HotkeySequence:
    """B 方案：只观察按键序列，不拦截、不延迟。"""

    def __init__(self, steps: list[tuple[set[str], int]], judge_ms: int = 450):
        self.steps = steps
        self.window = max(0.05, judge_ms / 1000.0)
        self.index = 0
        self.last_at = 0.0

    def reset(self):
        self.index = 0
        self.last_at = 0.0

    def feed(self, mods: set[str], vk: int, now: float | None = None) -> bool:
        if not self.steps:
            return False
        now = time.monotonic() if now is None else now
        if self.index and now - self.last_at > self.window:
            self.index = 0
        expected = self.steps[self.index] if self.index < len(self.steps) else None
        if expected and mods == expected[0] and vk == expected[1]:
            self.index += 1
            self.last_at = now
            if self.index >= len(self.steps):
                self.index = 0
                return True
            return False
        first = self.steps[0]
        if mods == first[0] and vk == first[1]:
            self.index = 1
            self.last_at = now
        else:
            self.index = 0
        return False


def combo_to_qt(combo: str) -> str:
    display = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Meta"}
    parts = [display.get(p, p.upper()) for p in (combo or "").split("+") if p]
    return "+".join(parts)


def qt_to_combo(sequence: QKeySequence) -> str:
    if sequence.isEmpty():
        return ""
    text = sequence.toString(QKeySequence.PortableText)
    parts = [p for p in text.split("+") if p]
    if not parts:
        return ""
    mods: list[str] = []
    for part in parts[:-1]:
        low = part.lower()
        if low == "ctrl":
            mods.append("ctrl")
        elif low in ("alt", "option"):
            mods.append("alt")
        elif low == "shift":
            mods.append("shift")
        elif low in ("meta", "win"):
            mods.append("win")
        else:
            return ""
    key = parts[-1].lower()
    if len(key) != 1 and key not in _NAMED_VK and not re.fullmatch(
        r"f([1-9]|1[0-2])", key
    ):
        return ""
    return "+".join(mods + [key])


# ---------------------------------------------------------------------------
# 剪贴板
# ---------------------------------------------------------------------------
def snapshot_clipboard() -> QMimeData | None:
    clipboard = QApplication.clipboard()
    if clipboard is None:
        return None
    source = clipboard.mimeData()
    if source is None:
        return None
    clone = QMimeData()
    for fmt in source.formats():
        clone.setData(fmt, source.data(fmt))
    return clone


def restore_clipboard(snapshot: QMimeData | None) -> None:
    if snapshot is None:
        return
    clipboard = QApplication.clipboard()
    if clipboard is None:
        return
    if snapshot.formats():
        clipboard.setMimeData(snapshot)


def _send_ctrl_c() -> None:
    try:
        from pynput.keyboard import Controller, Key

        keyboard = Controller()
        keyboard.press(Key.ctrl)
        keyboard.press("c")
        keyboard.release("c")
        keyboard.release(Key.ctrl)
    except Exception:
        pass


def _send_ctrl_v() -> None:
    try:
        from pynput.keyboard import Controller, Key

        keyboard = Controller()
        keyboard.press(Key.ctrl)
        keyboard.press("v")
        keyboard.release("v")
        keyboard.release(Key.ctrl)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 输入监听
# ---------------------------------------------------------------------------
class MuseSignals(QObject):
    middle_down = Signal()
    middle_up = Signal()
    left_down = Signal(int, int)
    typing = Signal(str)
    hotkey = Signal()


class GlobalInput:
    """全局输入监听：鼠标中键、键盘打字、全局快捷键，自带注入过滤。"""

    def __init__(self, signals: MuseSignals):
        self.signals = signals
        self.mouse_listener = None
        self.kb_listener = None
        self._kb_injected = False
        self._mods: set[str] = set()
        self._sequence: HotkeySequence | None = None

    # ---------- 鼠标 ----------
    def _mouse_filter(self, msg, data):
        if data.flags & (LLMHF_INJECTED | LLMHF_LOWER_IL_INJECTED):
            return True
        if msg == WM_LBUTTONDOWN:
            self.signals.left_down.emit(data.pt.x, data.pt.y)
        elif msg == WM_MBUTTONDOWN:
            self.signals.middle_down.emit()
            if self.mouse_listener:
                self.mouse_listener.suppress_event()
        elif msg == WM_MBUTTONUP:
            self.signals.middle_up.emit()
            if self.mouse_listener:
                self.mouse_listener.suppress_event()
        return True

    # ---------- 键盘 ----------
    def _kb_filter(self, msg, data):
        injected = bool(data.flags & (LLKHF_INJECTED | LLKHF_LOWER_IL_INJECTED))
        self._kb_injected = injected
        if injected:
            return True

        vk = int(data.vkCode)
        if vk in _VK_MODS:
            if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                self._mods.add(_VK_MODS[vk])
            elif msg in (WM_KEYUP, WM_SYSKEYUP):
                self._mods.discard(_VK_MODS[vk])
            return True

        # B 方案：只观察序列，不 suppress、不延迟
        if (
            self._sequence is not None
            and msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
            and self._sequence.feed(self._mods, vk)
        ):
            self.signals.hotkey.emit()
        return True

    def _on_press(self, key):
        if self._kb_injected:
            return
        # 带 Ctrl/Alt/Win 的多半是快捷键，不写入打字缓冲区
        if self._mods & {"ctrl", "alt", "win"}:
            return
        from pynput.keyboard import Key, KeyCode

        if key == Key.backspace:
            self.signals.typing.emit("\x08")
        elif key == Key.enter:
            self.signals.typing.emit("\n")
        elif isinstance(key, KeyCode):
            if key.char and key.char.isprintable():
                self.signals.typing.emit(key.char)
            else:
                self.signals.typing.emit("\x00")

    def set_hotkey(self, enabled: bool, sequence: str, judge_ms: int = 450) -> None:
        self._mods.clear()
        steps = parse_sequence(sequence) if enabled else None
        self._sequence = HotkeySequence(steps, judge_ms) if steps else None

    def start(self):
        from pynput import keyboard, mouse

        self.mouse_listener = mouse.Listener(
            win32_event_filter=self._mouse_filter,
            on_click=lambda *a, **k: None,
        )
        self.kb_listener = keyboard.Listener(
            win32_event_filter=self._kb_filter,
            on_press=self._on_press,
        )
        try:
            self.mouse_listener.start()
            self.kb_listener.start()
        except Exception:
            self.stop()
            raise

    def stop(self):
        for listener in (self.mouse_listener, self.kb_listener):
            try:
                if listener:
                    listener.stop()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 后台线程
# ---------------------------------------------------------------------------
class GenerateWorker(QThread):
    ok = Signal(int, list, dict)
    err = Signal(int, str)

    def __init__(self, req_id: int, params: dict):
        super().__init__()
        self.req_id = req_id
        self.params = params

    def run(self):
        try:
            result = generate(**self.params)
            usage = {
                "prompt_tokens": result.get("prompt_tokens", 0),
                "completion_tokens": result.get("completion_tokens", 0),
                "model": result.get("model", ""),
            }
            self.ok.emit(self.req_id, result["candidates"], usage)
        except Exception as error:
            self.err.emit(self.req_id, friendly_error(error))


class PingWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, api_key: str, base_url: str, model: str):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def run(self):
        from muse_core import test_connection

        try:
            self.done.emit(True, test_connection(self.api_key, self.base_url, self.model))
        except Exception as error:
            self.done.emit(False, friendly_error(error))


# ---------------------------------------------------------------------------
# 候选卡片
# ---------------------------------------------------------------------------
class CandidateCard(QFrame):
    copy_requested = Signal(dict)
    paste_requested = Signal(dict)

    def __init__(self, index: int, candidate: dict):
        super().__init__()
        self.candidate = candidate
        self.setObjectName("card")
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 10)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        number = QLabel(f"{index:02d}")
        number.setObjectName("num")
        number.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        badge = QLabel(candidate.get("label") or "候选")
        badge.setObjectName("badge")
        badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        head.addWidget(number)
        head.addWidget(badge)
        head.addStretch(1)

        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("mini")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(lambda: self.copy_requested.emit(self.candidate))
        paste_btn = QPushButton("粘贴")
        paste_btn.setObjectName("mini")
        paste_btn.setCursor(Qt.PointingHandCursor)
        paste_btn.clicked.connect(lambda: self.paste_requested.emit(self.candidate))
        head.addWidget(copy_btn)
        head.addWidget(paste_btn)
        layout.addLayout(head)

        body = QLabel(candidate.get("text", ""))
        body.setObjectName("body")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.NoTextInteraction)
        body.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(body)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.copy_requested.emit(self.candidate)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.paste_requested.emit(self.candidate)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("复制", lambda: self.copy_requested.emit(self.candidate))
        menu.addAction(
            "粘贴回原文", lambda: self.paste_requested.emit(self.candidate)
        )
        menu.exec(event.globalPos())


# ---------------------------------------------------------------------------
# 设置
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, parent, cfg: dict, focus_key: bool = False):
        super().__init__(parent)
        self.setWindowTitle("写作灵感 Muse · 设置")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.resize(580, 540)
        self.cfg = normalize_config(cfg)
        self.result_cfg: dict | None = None
        self.ping: PingWorker | None = None
        self._build()
        if focus_key:
            self.tabs.setCurrentIndex(0)
            self.key_edit.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(10)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._build_model_tab()
        self._build_trigger_tab()
        self._build_style_tab()

        bottom = QHBoxLayout()
        self.test_btn = QPushButton("测试连接")
        self.test_btn.setObjectName("ghost")
        self.test_btn.clicked.connect(self._test_connection)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("ghost")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        bottom.addWidget(self.test_btn)
        bottom.addStretch(1)
        bottom.addWidget(cancel_btn)
        bottom.addWidget(save_btn)
        outer.addLayout(bottom)

    def _build_model_tab(self):
        page = QWidget()
        page.setObjectName("page")
        form = QFormLayout(page)
        form.setContentsMargins(14, 18, 14, 14)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        key_row = QHBoxLayout()
        self.key_edit = QLineEdit(self.cfg.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…（只保存在本机 config.json）")
        self.show_key = QCheckBox("显示")
        self.show_key.toggled.connect(
            lambda checked: self.key_edit.setEchoMode(
                QLineEdit.Normal if checked else QLineEdit.Password
            )
        )
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.show_key)
        form.addRow("API Key", key_row)

        self.base_edit = QLineEdit(self.cfg.get("base_url", DEFAULT_CONFIG["base_url"]))
        form.addRow("Base URL", self.base_edit)

        self.model_box = QComboBox()
        self.model_box.setEditable(True)
        models = ["deepseek-chat", "deepseek-reasoner", "deepseek-flash", "deepseek-v4-pro"]
        current_model = self.cfg.get("model", "deepseek-chat")
        if current_model and current_model not in models:
            models.append(current_model)
        self.model_box.addItems(models)
        self.model_box.setCurrentText(current_model)
        form.addRow("模型", self.model_box)

        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(float(self.cfg.get("temperature", 1.1)))
        form.addRow("温度", self.temp_spin)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 300)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(int(self.cfg.get("timeout_seconds", 60)))
        form.addRow("请求超时", self.timeout_spin)

        self.ctx_spin = QSpinBox()
        self.ctx_spin.setRange(200, 20000)
        self.ctx_spin.setSingleStep(100)
        self.ctx_spin.setSuffix(" 字")
        self.ctx_spin.setValue(int(self.cfg.get("max_context_chars", 3000)))
        form.addRow("上下文上限", self.ctx_spin)

        hint = QLabel(
            "Key 只保存在本机 config.json；如果担心泄漏，可以改用环境变量 "
            "DEEPSEEK_API_KEY。温度越高越发散，1.0~1.2 适合写作。"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.tabs.addTab(page, "连接")

    def _build_trigger_tab(self):
        page = QWidget()
        page.setObjectName("page")
        form = QFormLayout(page)
        form.setContentsMargins(14, 18, 14, 14)
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight)

        self.hk_enabled = QCheckBox("启用全局快捷键")
        self.hk_enabled.setChecked(bool(self.cfg["hotkey"].get("enabled", True)))
        self.hotkey_edit = QLineEdit(
            self.cfg["hotkey"].get("sequence", "ctrl+space,ctrl+space")
        )
        self.hotkey_edit.setPlaceholderText("ctrl+space,ctrl+space")
        self.judge_spin = QSpinBox()
        self.judge_spin.setRange(150, 1500)
        self.judge_spin.setSingleStep(50)
        self.judge_spin.setSuffix(" ms")
        self.judge_spin.setValue(int(self.cfg["hotkey"].get("judge_ms", 450)))
        hk_row = QHBoxLayout()
        hk_row.addWidget(self.hk_enabled)
        hk_row.addWidget(self.hotkey_edit, 1)
        form.addRow("快捷键", hk_row)
        form.addRow("判定窗口", self.judge_spin)

        self.history_enabled = QCheckBox("在本机保存生成历史（方便回看，不上传）")
        self.history_enabled.setChecked(bool(self.cfg["history"].get("enabled", True)))
        form.addRow("历史记录", self.history_enabled)

        hint = QLabel(
            "默认 ctrl+space,ctrl+space：单按 Ctrl+Space 照常切输入法/触发建议，"
            "450ms 内连按两下才触发 Muse。B 方案不拦截、不延迟，"
            "所以两次 Ctrl+Space 都会交给系统。"
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.tabs.addTab(page, "触发")

    def _build_style_tab(self):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(8)
        label = QLabel(
            "粘贴 3~5 句你过去写过的文字。生成时会作为语感参考，"
            "只学节奏和用词，不照抄。最多 1200 字。"
        )
        label.setObjectName("hint")
        label.setWordWrap(True)
        layout.addWidget(label)
        self.sample_edit = QPlainTextEdit()
        self.sample_edit.setPlaceholderText(
            "例如：\n写代码和写文章其实是同一件事：先把问题拆小，再决定哪一块值得展开。\n我见过太多“正确的废话”，它们读起来像会议纪要，唯独不像人话。"
        )
        self.sample_edit.setPlainText(self.cfg.get("style_sample", ""))
        layout.addWidget(self.sample_edit, 1)
        self.tabs.addTab(page, "我的文风")

    # ---------- 收集 / 校验 ----------
    def _collect(self) -> dict | None:
        base_url = self.base_edit.text().strip() or DEFAULT_CONFIG["base_url"]
        if not base_url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Base URL 无效", "请填写 http:// 或 https:// 开头的地址。")
            return None
        sequence = self.hotkey_edit.text().strip()
        if self.hk_enabled.isChecked() and parse_sequence(sequence) is None:
            QMessageBox.warning(
                self,
                "快捷键无效",
                "请填写用逗号分隔的组合键，例如 ctrl+space,ctrl+space。",
            )
            return None
        cfg = copy.deepcopy(self.cfg)
        cfg["api_key"] = self.key_edit.text().strip()
        cfg["base_url"] = base_url
        cfg["model"] = self.model_box.currentText().strip() or "deepseek-chat"
        cfg["temperature"] = float(self.temp_spin.value())
        cfg["timeout_seconds"] = int(self.timeout_spin.value())
        cfg["max_context_chars"] = int(self.ctx_spin.value())
        cfg["hotkey"] = {
            "enabled": bool(self.hk_enabled.isChecked()),
            "sequence": sequence or "ctrl+space,ctrl+space",
            "judge_ms": int(self.judge_spin.value()),
        }
        cfg["auto_guide"]["enabled"] = False
        cfg["history"] = {"enabled": bool(self.history_enabled.isChecked())}
        cfg["style_sample"] = self.sample_edit.toPlainText().strip()[:1200]
        return normalize_config(cfg)

    def accept(self):
        if self.ping is not None and self.ping.isRunning():
            QMessageBox.information(self, "稍等", "正在测试连接，请等测试结束再保存。")
            return
        cfg = self._collect()
        if cfg is None:
            return
        try:
            save_config(cfg)
        except OSError as error:
            QMessageBox.warning(self, "保存失败", f"配置写入失败：\n{error}")
            return
        self.result_cfg = cfg
        super().accept()

    def reject(self):
        if self.ping is not None and self.ping.isRunning():
            return
        super().reject()

    def closeEvent(self, event):
        if self.ping is not None and self.ping.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    # ---------- 测试连接 ----------
    def _test_connection(self):
        if self.ping is not None and self.ping.isRunning():
            return
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "缺少 Key", "请先填写 API Key。")
            return
        base_url = self.base_edit.text().strip() or DEFAULT_CONFIG["base_url"]
        model = self.model_box.currentText().strip() or "deepseek-chat"
        self.test_btn.setEnabled(False)
        self.test_btn.setText("测试中…")
        self.ping = PingWorker(key, base_url, model)
        self.ping.done.connect(self._on_ping_done)
        self.ping.start()

    def _on_ping_done(self, ok: bool, message: str):
        self.test_btn.setEnabled(True)
        self.test_btn.setText("测试连接")
        if ok:
            QMessageBox.information(self, "连接正常", message)
        else:
            QMessageBox.warning(self, "连接失败", message)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------
class MuseWindow(QWidget):
    settings_changed = Signal()
    notice = Signal(str)
    ball_menu_requested = Signal(QPoint)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("写作灵感 Muse")
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setMinimumSize(460, 500)
        self.resize(540, 660)
        self.setWindowIcon(make_icon())

        self._target_hwnd = 0
        self._req_id = 0
        self._requests: dict[int, dict] = {}
        self._workers: set[GenerateWorker] = set()
        self._busy = False
        self._paste_attempts = 0
        self.mouse_ctl = mouse.Controller()
        self._quick = False
        self._quick_anchor = QPoint()
        self._quick_target = 0

        # 中键取词状态
        self._state = "idle"
        self._up_early = False
        self._cap_cb = None
        self._cap_deadline = 0.0
        self._clip_backup: QMimeData | None = None
        self._old_clip_text = ""
        self._cap_timer = QTimer(self)
        self._cap_timer.setInterval(30)
        self._cap_timer.timeout.connect(self._poll_selection)
        self._terminal_notified = False

        # 快速生成的兜底输入缓冲区（不做后台感知）
        self._typed: list[str] = []

        # 窗口位置
        self._geom_timer = QTimer(self)
        self._geom_timer.setSingleShot(True)
        self._geom_timer.timeout.connect(self._save_geometry)

        self.history = load_history()

        ball_cfg = CFG.get("ball", {})
        self.ball = BallWindow(
            size=int(ball_cfg.get("size", 64)),
            opacity=float(ball_cfg.get("opacity", 0.82)),
            x=ball_cfg.get("x"),
            y=ball_cfg.get("y"),
        )
        self.ball.clicked.connect(self.toggle_show)
        self.ball.double_clicked.connect(self.trigger_quick)
        self.ball.menu_requested.connect(self.ball_menu_requested)
        self.ball.position_changed.connect(self._save_ball_position)
        self.ball.mode_cycled.connect(self.cycle_mode)

        self.popup = ResultPopup()
        self.popup.paste_requested.connect(self._paste_from_popup)
        self.popup.regenerate_requested.connect(self._regenerate_quick)
        self.popup.expand_requested.connect(self._expand_popup)
        self.popup.stop_requested.connect(self._stop_quick)

        self._build_ui()
        self.setStyleSheet(STYLE)
        self._apply_config()
        self._restore_geometry()

    # ---------- 界面 ----------
    def _build_ui(self):
        self.setObjectName("root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        header = QHBoxLayout()
        title = QLabel("写作灵感 Muse")
        title.setObjectName("title")
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setObjectName("ghost")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.clicked.connect(self.open_settings)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.settings_btn)
        outer.addLayout(header)

        self.tip_label = QLabel()
        self.tip_label.setObjectName("hint")
        self.tip_label.setWordWrap(True)
        outer.addWidget(self.tip_label)

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self._build_inspire_tab()
        self._build_history_tab()

    def _build_inspire_tab(self):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self.input = QPlainTextEdit()
        self.input.setObjectName("input")
        self.input.setPlaceholderText(
            "粘贴一段草稿、一个标题、半句话… 也可以按 Ctrl+Space ×2 读取光标上下文"
        )
        self.input.setFixedHeight(92)
        layout.addWidget(self.input)

        meta = QHBoxLayout()
        self.count_label = QLabel("0 字")
        self.count_label.setObjectName("count")
        meta_hint = QLabel("Ctrl+Enter 生成 · Ctrl+Space ×2 快捷生成")
        meta_hint.setObjectName("count")
        meta.addWidget(self.count_label)
        meta.addStretch(1)
        meta.addWidget(meta_hint)
        layout.addLayout(meta)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.mode_box = QComboBox()
        self.mode_box.addItems(MODES)
        self.mode_box.setToolTip("选择这次要什么：续写、润色、标题、提纲…")
        self.style_box = QComboBox()
        self.style_box.addItems(list(STYLES.keys()))
        self.gen_btn = QPushButton("生成灵感")
        self.gen_btn.setCursor(Qt.PointingHandCursor)
        self.gen_btn.clicked.connect(self.on_generate)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("ghost")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self.cancel_generation)
        controls.addWidget(self.mode_box, 2)
        controls.addWidget(self.style_box, 2)
        controls.addWidget(self.gen_btn, 2)
        controls.addWidget(self.stop_btn)
        layout.addLayout(controls)

        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText(
            "补充要求（可选）：写给谁看 / 再短一点 / 保留术语 / 语气更硬…"
        )
        self.extra_edit.returnPressed.connect(self.on_generate)
        layout.addWidget(self.extra_edit)

        candidate_header = QHBoxLayout()
        section = QLabel("灵感候选")
        section.setObjectName("section")
        self.again_btn = QPushButton("换一批")
        self.again_btn.setObjectName("mini")
        self.again_btn.setCursor(Qt.PointingHandCursor)
        self.again_btn.clicked.connect(self.on_generate)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("mini")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_all)
        candidate_header.addWidget(section)
        candidate_header.addStretch(1)
        candidate_header.addWidget(self.again_btn)
        candidate_header.addWidget(self.clear_btn)
        layout.addLayout(candidate_header)

        self.cards_host = QWidget()
        self.cards_host.setObjectName("cards")
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 3, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignTop)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.cards_host)
        layout.addWidget(self.scroll, 1)

        self.status = QLabel("待命")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        bottom = QHBoxLayout()
        hint = QLabel("单击候选复制 · 双击粘贴 ｜ 悬浮球可拖动、双击直接生成")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        bottom.addWidget(hint)
        bottom.addStretch(1)
        layout.addLayout(bottom)

        self.input.textChanged.connect(self._on_input_changed)
        self.tabs.addTab(page, "灵感")

        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.on_generate)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.on_generate)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)
        QShortcut(QKeySequence("Esc"), self, activated=self.hide)

    def _build_history_tab(self):
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self.history_list = QListWidget()
        self.history_list.setWordWrap(True)
        self.history_list.itemDoubleClicked.connect(
            lambda _item: self.load_history_item()
        )
        layout.addWidget(self.history_list, 1)

        buttons = QHBoxLayout()
        load_btn = QPushButton("载入到灵感页")
        load_btn.setObjectName("ghost")
        load_btn.clicked.connect(self.load_history_item)
        delete_btn = QPushButton("删除")
        delete_btn.setObjectName("ghost")
        delete_btn.clicked.connect(self.delete_history_item)
        clear_btn = QPushButton("清空历史")
        clear_btn.setObjectName("ghost")
        clear_btn.clicked.connect(self.clear_history)
        buttons.addWidget(load_btn)
        buttons.addStretch(1)
        buttons.addWidget(delete_btn)
        buttons.addWidget(clear_btn)
        layout.addLayout(buttons)

        note = QLabel("历史只存本机 history.json；可在「设置 → 触发」里关闭。")
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.tabs.addTab(page, "历史")
        self._refresh_history()

    # ---------- 配置应用 ----------
    def _apply_config(self):
        mode = CFG.get("last", {}).get("mode", MODES[0])
        style = CFG.get("last", {}).get("style", "平实")
        if mode in MODES:
            self.mode_box.setCurrentText(mode)
        if style in STYLES:
            self.style_box.setCurrentText(style)

        sequence = CFG["hotkey"].get("sequence", "ctrl+space,ctrl+space")
        enabled = CFG["hotkey"].get("enabled", True)
        hotkey_text = sequence_label(sequence) if enabled else "快捷键已关闭"
        self.tip_label.setText(
            f"悬浮球 ｜ {hotkey_text} ｜ 鼠标中键 ｜ 托盘图标"
        )
        if not CFG.get("api_key"):
            self.status.setText("首次使用：点右上角「设置」填入 DeepSeek API Key")
        self._on_input_changed()

    def _restore_geometry(self):
        geometry = CFG.get("window", {})
        width = int(geometry.get("w") or 540)
        height = int(geometry.get("h") or 660)
        x, y = geometry.get("x"), geometry.get("y")
        self.resize(width, height)
        if isinstance(x, int) and isinstance(y, int):
            screen = QApplication.screenAt(QPoint(x, y))
            if screen is not None:
                self.move(x, y)
                return
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(
                area.center().x() - self.width() // 2,
                area.center().y() - self.height() // 2,
            )

    def _save_cfg(self):
        try:
            save_config(CFG)
        except OSError as error:
            self.status.setText(f"配置写入失败：{error}")

    def _save_geometry(self):
        if self.isMaximized() or self.isMinimized():
            return
        CFG.setdefault("window", {})
        geometry = {"x": self.x(), "y": self.y(), "w": self.width(), "h": self.height()}
        if all(CFG["window"].get(key) == value for key, value in geometry.items()):
            return
        CFG["window"].update(geometry)
        self._save_cfg()

    def moveEvent(self, event):
        super().moveEvent(event)
        timer = getattr(self, "_geom_timer", None)
        if timer is not None:
            timer.start(700)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        timer = getattr(self, "_geom_timer", None)
        if timer is not None:
            timer.start(700)

    def hideEvent(self, event):
        self._save_geometry()
        super().hideEvent(event)

    # ---------- 输入变化 ----------
    def _on_input_changed(self):
        text = self.input.toPlainText()
        self.count_label.setText(f"{len(text)} 字")
        self.again_btn.setEnabled(not self._busy and bool(text.strip()))

    # ---------- 窗口显示 ----------
    def _activate_show(self, preserve_target: bool = False):
        if not preserve_target:
            self._target_hwnd = get_foreground_hwnd()
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def toggle_show(self):
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            if not self.isVisible():
                self._position_panel_near_ball()
            self._activate_show()

    def _position_panel_near_ball(self):
        if not self.ball.isVisible():
            return
        center = self.ball.center_global()
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        gap = 18
        if center.x() > area.center().x():
            x = center.x() - self.width() - gap
        else:
            x = center.x() + self.ball.width() + gap
        y = center.y() - self.height() // 2
        x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))
        self.move(x, y)

    def generate_from_text(self, text: str):
        text = (text or "").strip()
        if not text:
            self._activate_show()
            self.status.setText("剪贴板里没有文字")
            return
        self._target_hwnd = get_foreground_hwnd()
        self._load_and_generate(text)

    def _load_and_generate(self, text: str, mode: str | None = None):
        text = (text or "").strip()
        if not text:
            return
        self.input.setPlainText(text)
        if mode is None:
            mode = self._guess_mode(text)
        if mode in MODES:
            self.mode_box.setCurrentText(mode)
        self.tabs.setCurrentIndex(0)
        self._activate_show(preserve_target=True)
        self._run_generate()

    @staticmethod
    def _guess_mode(text: str) -> str:
        stripped = (text or "").rstrip()
        if stripped and stripped[-1] in "。！？!?…；;":
            return "换词润色"
        return "续写下文"

    # ---------- 中键取词 ----------
    def on_middle_down(self):
        if self._state != "idle":
            return
        self._target_hwnd = get_foreground_hwnd()
        self._state = "checking"
        self._up_early = False
        self._begin_capture(self._on_middle_captured, 220, "middle")

    def _on_middle_captured(self, text: str):
        self._state = "idle"
        if text.strip():
            self._load_and_generate(text)
            return
        if self._up_early:
            self.mouse_ctl.click(mouse.Button.middle)
        else:
            self._state = "drag"
            self.mouse_ctl.press(mouse.Button.middle)

    def on_middle_up(self):
        if self._state == "checking":
            self._up_early = True
        elif self._state == "drag":
            self.mouse_ctl.release(mouse.Button.middle)
            self._state = "idle"

    def _begin_capture(self, callback, timeout_ms: int, kind: str):
        if not IS_WINDOWS or is_terminal_window():
            if is_terminal_window() and not self._terminal_notified:
                self._terminal_notified = True
                self.notice.emit("终端里不自动取词：先复制文字，再按快捷键或点托盘")
            QTimer.singleShot(0, lambda: callback(""))
            return
        self._cap_cb = callback
        self._cap_deadline = time.monotonic() + timeout_ms / 1000
        self._clip_backup = snapshot_clipboard()
        self._old_clip_text = QApplication.clipboard().text()
        _send_ctrl_c()
        self._cap_timer.start()

    def _poll_selection(self):
        if self._cap_cb is None:
            self._cap_timer.stop()
            return
        text = QApplication.clipboard().text()
        if text and text.strip() and text != self._old_clip_text:
            self._finish_capture(text)
        elif time.monotonic() >= self._cap_deadline:
            self._finish_capture("")

    def _finish_capture(self, text: str):
        self._cap_timer.stop()
        callback = self._cap_cb
        self._cap_cb = None
        restore_clipboard(self._clip_backup)
        self._clip_backup = None
        if callback:
            callback(text)

    # ---------- 快速生成 / 悬浮球 ----------
    @staticmethod
    def _title_matches(title: str) -> bool:
        if not title:
            return False
        exts = CFG["auto_guide"].get("exts", [])
        if any(
            re.search(r"\." + re.escape(ext.lstrip(".")) + r"($|\s)", title, re.I)
            for ext in exts
        ):
            return True
        if re.search(r"\.[A-Za-z0-9]{1,8}(\s|$)", title):
            return False
        lower = title.lower()
        return "记事本" in title or "notepad" in lower

    def on_typing(self, char: str):
        """只为快捷键兜底维护一个短缓冲区；不做感知、不自动生成。"""
        if self.isActiveWindow():
            return
        if not self._title_matches(get_foreground_title()):
            if self._typed:
                self._typed.clear()
            return
        if ime_is_open():
            self._typed.clear()
            return
        if char == "\x00":
            return
        if char == "\x08":
            if self._typed:
                self._typed.pop()
        elif char == "\n":
            self._typed.append("\n")
        else:
            self._typed.append(char)
        if len(self._typed) > 1200:
            del self._typed[: len(self._typed) - 1200]

    def _capture_quick_context(self) -> tuple[str, int, QPoint, bool]:
        """立即取上下文，返回 (文本, 原窗口 hwnd, 锚点, 是否选区)。"""
        hwnd = get_foreground_hwnd()
        anchor = get_caret_screen_pos() or self.ball.center_global()
        if self.isActiveWindow():
            return self.input.toPlainText().strip(), 0, anchor, False
        selection = read_edit_selection(3000)
        if selection:
            return selection, hwnd, anchor, True
        text = read_edit_context(3000)
        if not text:
            text = "".join(self._typed[-1200:]).strip()
        return text, hwnd, anchor, False

    def trigger_quick(self):
        if self._busy:
            QToolTip.showText(
                self.ball.center_global(),
                "正在生成中…",
                self.ball,
                QRect(),
                1400,
            )
            return
        text, hwnd, anchor, has_selection = self._capture_quick_context()
        if len(text.strip()) < 2:
            self.ball.shake()
            QToolTip.showText(
                self.ball.center_global(),
                "没读到光标前的文字，先点一下输入框再按 Ctrl+Space ×2",
                self.ball,
                QRect(),
                2600,
            )
            return
        self._quick = True
        self._quick_target = hwnd
        self._quick_anchor = anchor
        self.popup.hide()
        self.input.setPlainText(text)
        mode = "换词润色" if has_selection else self._guess_mode(text)
        if mode in MODES:
            self.mode_box.setCurrentText(mode)
        self.tabs.setCurrentIndex(0)
        self._run_generate(quick=True)

    def cycle_mode(self, delta: int):
        current = self.mode_box.currentText()
        index = MODES.index(current) if current in MODES else 0
        mode = MODES[(index + int(delta)) % len(MODES)]
        self.mode_box.setCurrentText(mode)
        QToolTip.showText(
            self.ball.center_global(),
            f"模式：{mode}",
            self.ball,
            QRect(),
            1400,
        )

    def set_mode(self, mode: str):
        if mode in MODES:
            self.mode_box.setCurrentText(mode)

    def _save_ball_position(self, position: QPoint):
        CFG.setdefault("ball", {})
        CFG["ball"]["x"] = int(position.x())
        CFG["ball"]["y"] = int(position.y())
        self._save_cfg()

    def show_ball(self):
        self.ball.restore_or_default()
        self.ball.show()
        self.ball.raise_()

    def hide_ball(self):
        self.ball.hide()

    # ---------- 生成 ----------
    def on_generate(self):
        if not CFG.get("api_key"):
            self.open_settings(focus_key=True)
            if CFG.get("api_key") and self.input.toPlainText().strip():
                self._run_generate()
            return
        self._run_generate()

    def _run_generate(self, quick: bool = False):
        if self._busy:
            return
        if not CFG.get("api_key"):
            self.ball.set_state("error")
            self.status.setText("请先在「设置」里填写 DeepSeek API Key")
            QToolTip.showText(
                self.ball.center_global(),
                "请先点右上角「设置」填写 DeepSeek API Key",
                self.ball,
                QRect(),
                2600,
            )
            return
        context = self.input.toPlainText().strip()
        if not context:
            self.status.setText("先把草稿/标题粘进来，或用 Ctrl+Space ×2 读取光标上下文")
            return
        mode = self.mode_box.currentText()
        style = self.style_box.currentText()
        context, truncated = prepare_context(
            context, mode, int(CFG.get("max_context_chars", 3000))
        )
        extra = self.extra_edit.text().strip()
        params = {
            "api_key": CFG.get("api_key", ""),
            "base_url": CFG.get("base_url", DEFAULT_CONFIG["base_url"]),
            "model": CFG.get("model", "deepseek-chat"),
            "mode": mode,
            "style": style,
            "context": context,
            "temperature": float(CFG.get("temperature", 1.1)),
            "extra": extra,
            "style_sample": CFG.get("style_sample", ""),
            "timeout": float(CFG.get("timeout_seconds", 60)),
        }

        self._req_id += 1
        request_id = self._req_id
        self._requests[request_id] = {
            "context": context,
            "mode": mode,
            "style": style,
            "extra": extra,
            "truncated": truncated,
            "quick": quick,
            "anchor": QPoint(self._quick_anchor) if quick else self.ball.center_global(),
            "target": self._quick_target if quick else self._target_hwnd,
        }
        CFG["last"] = {"mode": mode, "style": style}
        self._set_busy(True)
        self._clear_cards()
        self.status.setText(
            "生成中…" + ("（原文过长，已截断）" if truncated else "")
        )
        self.ball.set_state("thinking")
        self.ball.set_badge(0)

        worker = GenerateWorker(request_id, params)
        worker.ok.connect(self.on_result)
        worker.err.connect(self.on_error)
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self._workers.add(worker)
        worker.start()

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.gen_btn.setEnabled(not busy)
        self.stop_btn.setVisible(busy)
        self.again_btn.setEnabled(not busy and bool(self.input.toPlainText().strip()))
        if busy:
            self.ball.set_state("thinking")

    def cancel_generation(self):
        self._req_id += 1
        self._set_busy(False)
        self.ball.set_state("idle")
        self.ball.set_badge(0)
        self.popup.hide()
        self.status.setText("已停止等待（旧请求的结果会被丢弃）")

    def _cleanup_worker(self, worker: GenerateWorker):
        self._workers.discard(worker)
        worker.deleteLater()

    def on_result(self, req_id: int, candidates: list, usage: dict):
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        cost = self._record_usage(prompt_tokens, completion_tokens)
        info = self._requests.pop(req_id, None)
        if req_id != self._req_id:
            return

        self._set_busy(False)
        self._render_candidates(candidates)
        self.tabs.setCurrentIndex(0)
        total = prompt_tokens + completion_tokens
        self.status.setText(
            f"本次 {total:,} tokens ≈ ¥{cost:.3f} ｜ "
            f"累计 ¥{CFG['stats'].get('cost', 0):.3f}"
        )
        self.ball.set_state("result")
        self.ball.set_badge(len(candidates))
        if info and info.get("quick"):
            self.popup.show_results(
                candidates,
                {
                    "mode": info["mode"],
                    "style": info["style"],
                    "context": info["context"],
                },
                info.get("anchor") or self.ball.center_global(),
                int(info.get("target") or 0),
            )
        if info and CFG["history"].get("enabled", True):
            entry = {
                "ts": time.strftime("%m-%d %H:%M"),
                "mode": info["mode"],
                "style": info["style"],
                "extra": info["extra"],
                "context": info["context"],
                "candidates": candidates,
                "tokens": total,
                "cost": round(cost, 6),
            }
            self.history = push_history(entry)
            self._refresh_history()
        self._on_input_changed()

    def on_error(self, req_id: int, message: str):
        info = self._requests.pop(req_id, None)
        if req_id != self._req_id:
            return
        self._set_busy(False)
        self.ball.set_state("error")
        self.ball.set_badge(1)
        self.status.setText(f"出错：{message}")
        if info and info.get("quick"):
            self.popup.show_error(
                message,
                info.get("anchor") or self.ball.center_global(),
                int(info.get("target") or 0),
            )
        self._on_input_changed()

    def _record_usage(self, prompt_tokens: int, completion_tokens: int) -> float:
        prices = CFG.get("prices_cny_per_1m", DEFAULT_CONFIG["prices_cny_per_1m"])
        cost = estimate_cost(prompt_tokens, completion_tokens, prices)
        stats = CFG.setdefault("stats", {"tokens": 0, "cost": 0.0, "calls": 0})
        stats["tokens"] = int(stats.get("tokens", 0)) + prompt_tokens + completion_tokens
        stats["cost"] = round(float(stats.get("cost", 0.0)) + cost, 4)
        stats["calls"] = int(stats.get("calls", 0)) + 1
        self._save_cfg()
        return cost

    # ---------- 候选 ----------
    def _render_candidates(self, candidates: list):
        self._clear_cards()
        if not isinstance(candidates, list):
            return
        for index, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                candidate = {"label": "", "text": str(candidate)}
            card = CandidateCard(index, candidate)
            card.copy_requested.connect(self.copy_candidate)
            card.paste_requested.connect(self.paste_candidate)
            self.cards_layout.addWidget(card)

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def copy_candidate(self, candidate: dict):
        text = candidate.get("text", "")
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status.setText("已复制到剪贴板；点「粘贴」或双击候选可写回原文")

    def paste_candidate(self, candidate: dict):
        text = candidate.get("text", "")
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status.setText("正在写回原文…")
        self.hide()
        self._paste_attempts = 0
        QTimer.singleShot(100, self._try_paste)

    def _try_paste(self):
        if not IS_WINDOWS:
            return
        target = self._target_hwnd
        if target and not user32.IsWindow(target):
            self.notice.emit("原窗口已关闭，候选已复制到剪贴板")
            return
        foreground = get_foreground_hwnd()
        if not target or foreground == target:
            _send_ctrl_v()
            return
        self._paste_attempts += 1
        if self._paste_attempts < 6:
            QTimer.singleShot(80, self._try_paste)
        else:
            self.notice.emit("没有检测到原窗口，候选已复制，请手动粘贴")

    def _paste_from_popup(self, text: str):
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.popup.hide()
        self._target_hwnd = self.popup.target_hwnd or self._quick_target
        self._paste_attempts = 0
        QTimer.singleShot(80, self._try_paste)

    def _regenerate_quick(self):
        self.popup.hide()
        if not self.input.toPlainText().strip():
            return
        self._quick = True
        self._quick_anchor = self._quick_anchor or self.ball.center_global()
        self._quick_target = self.popup.target_hwnd or self._quick_target
        self._run_generate(quick=True)

    def _expand_popup(self):
        self.popup.hide()
        self._quick = False
        self._activate_show(preserve_target=True)
        self.tabs.setCurrentIndex(0)
        self.status.setText("已展开完整面板")

    def _stop_quick(self):
        self.popup.hide()
        self.cancel_generation()

    def clear_all(self):
        self.input.clear()
        self.extra_edit.clear()
        self._clear_cards()
        self.status.setText("已清空")
        self._on_input_changed()

    # ---------- 历史 ----------
    def _refresh_history(self):
        self.history_list.clear()
        for entry in self.history:
            context = (entry.get("context") or "").replace("\n", " ").strip()
            preview = context[:40] + ("…" if len(context) > 40 else "")
            text = (
                f"{entry.get('ts', '')}   {entry.get('mode', '')} · "
                f"{entry.get('style', '')}\n{preview}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)
            item.setSizeHint(QSize(0, 50))
            item.setToolTip(context[:300])
            self.history_list.addItem(item)

    def load_history_item(self):
        item = self.history_list.currentItem()
        if item is None:
            return
        entry = item.data(Qt.UserRole)
        if not isinstance(entry, dict):
            return
        self.input.setPlainText(entry.get("context", ""))
        self.extra_edit.setText(entry.get("extra", ""))
        mode = entry.get("mode", "")
        style = entry.get("style", "")
        if mode in MODES:
            self.mode_box.setCurrentText(mode)
        if style in STYLES:
            self.style_box.setCurrentText(style)
        candidates = entry.get("candidates", [])
        if not isinstance(candidates, list):
            candidates = []
        self._render_candidates(candidates)
        self.tabs.setCurrentIndex(0)
        self._activate_show(preserve_target=True)
        self._target_hwnd = 0
        self.status.setText(f"已载入 {entry.get('ts', '')} 的记录")

    def delete_history_item(self):
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.history):
            return
        del self.history[row]
        save_history(self.history)
        self._refresh_history()

    def clear_history(self):
        if not self.history:
            return
        answer = QMessageBox.question(
            self,
            "清空历史",
            "确定删除本机保存的全部生成历史？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.history = []
        save_history([])
        self._refresh_history()

    # ---------- 设置 ----------
    def open_settings(self, focus_key: bool = False):
        dialog = SettingsDialog(self, CFG, focus_key=focus_key)
        if dialog.exec() != QDialog.Accepted:
            return
        new_cfg = dialog.result_cfg
        if not new_cfg:
            return
        CFG.clear()
        CFG.update(new_cfg)
        self._apply_config()
        self.settings_changed.emit()
        self.status.setText("设置已保存")

    # ---------- 退出 ----------
    def shutdown(self):
        self._cap_timer.stop()
        self._geom_timer.stop()
        self._save_geometry()
        if self.ball.isVisible():
            CFG.setdefault("ball", {})
            CFG["ball"]["x"] = int(self.ball.x())
            CFG["ball"]["y"] = int(self.ball.y())
        self._save_cfg()
        self._req_id += 1
        for worker in list(self._workers):
            if worker.isRunning():
                worker.terminate()
                worker.wait(600)
        self._workers.clear()
        self.ball.hide()
        self.popup.hide()
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


# ---------------------------------------------------------------------------
# 悬浮球 / 灵感弹层
# ---------------------------------------------------------------------------
class BallWindow(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    menu_requested = Signal(QPoint)
    position_changed = Signal(QPoint)
    mode_cycled = Signal(int)

    def __init__(self, size: int = 64, opacity: float = 0.82, x=None, y=None):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_Hover, True)
        self._orb = max(40, int(size))
        self._pad = 12
        self.setFixedSize(self._orb + self._pad * 2, self._orb + self._pad * 2)
        self._opacity = max(0.3, min(1.0, float(opacity)))
        self._saved_x = x if isinstance(x, int) else None
        self._saved_y = y if isinstance(y, int) else None
        self._placed = False
        self._state = "idle"
        self._badge = 0
        self._angle = 0.0
        self._phase = 0.0
        self._hover = False
        self._dragging = False
        self._double_fired = False
        self._press_global = QPoint()
        self._press_pos = QPoint()
        self._shake_anim = None
        self._icon = QPixmap(
            str(Path(__file__).resolve().parent / "assets" / "muse-icon-256.png")
        )
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(100)
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(280)
        self._click_timer.timeout.connect(self.clicked.emit)
        self.setToolTip("Muse · 单击打开 · 双击生成\nCtrl+Space ×2")

    # ---------- 绘制 ----------
    def _tick(self):
        self._phase += 0.08
        if self._state == "thinking":
            self._angle = (self._angle + 7.0) % 360.0
        self.update()

    def set_state(self, state: str):
        self._state = state
        self._timer.setInterval(33 if state == "thinking" else 100)
        self.update()

    def set_badge(self, count: int):
        self._badge = max(0, int(count))
        self.update()

    def _conic(self):
        center = QPointF(self.width() / 2, self.height() / 2)
        gradient = QConicalGradient(center, self._angle)
        for pos, color in (
            (0.0, "#22d3ee"),
            (0.2, "#818cf8"),
            (0.4, "#f472b6"),
            (0.6, "#fbbf24"),
            (0.8, "#34d399"),
            (1.0, "#22d3ee"),
        ):
            gradient.setColorAt(pos, QColor(color))
        return gradient

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        center = QPointF(self.width() / 2, self.height() / 2)
        scale = 1.0 + (0.02 * math.sin(self._phase) if self._state != "thinking" else 0.0)
        if self._hover:
            scale *= 1.05
        radius = (self._orb / 2) * scale

        # 外发光
        glow_color = {
            "idle": QColor(255, 255, 255, 16),
            "thinking": QColor(120, 170, 255, 40),
            "result": QColor(255, 184, 0, 34),
            "error": QColor(255, 95, 87, 34),
        }.get(self._state, QColor(255, 255, 255, 16))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow_color)
        painter.drawEllipse(center, radius + 9, radius + 9)

        # 半透明玻璃球本体：直接复用图标资产
        painter.setOpacity(self._opacity + (0.04 if self._hover else 0.0))
        if not self._icon.isNull():
            painter.drawPixmap(
                QRectF(
                    center.x() - radius,
                    center.y() - radius,
                    radius * 2,
                    radius * 2,
                ),
                self._icon,
                QRectF(self._icon.rect()),
            )
        else:
            painter.setBrush(QColor(28, 32, 44, 210))
            painter.drawEllipse(center, radius, radius)
        painter.setOpacity(1.0)

        if self._state == "thinking":
            conic = self._conic()
            painter.save()
            clip = QPainterPath()
            clip.addEllipse(center, radius, radius)
            painter.setClipPath(clip)
            painter.setOpacity(0.52)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(conic))
            painter.drawEllipse(center, radius, radius)
            painter.setOpacity(1.0)
            painter.restore()

            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QBrush(conic), 3.6))
            painter.drawEllipse(center, radius - 1, radius - 1)
            painter.setPen(QPen(QColor(255, 255, 255, 210), 2.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(
                QRectF(
                    center.x() - radius + 1,
                    center.y() - radius + 1,
                    (radius - 1) * 2,
                    (radius - 1) * 2,
                ),
                int(self._angle * 16) + 210 * 16,
                60 * 16,
            )
            for i, color in enumerate(("#22d3ee", "#f472b6", "#fbbf24")):
                angle = math.radians(self._angle + i * 120)
                dot = center + QPointF(
                    math.cos(angle) * (radius + 3),
                    math.sin(angle) * (radius + 3),
                )
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(color))
                painter.drawEllipse(dot, 2.4, 2.4)
        else:
            ring = {
                "idle": QColor(255, 255, 255, 70),
                "result": QColor(255, 184, 0, 220),
                "error": QColor(255, 95, 87, 230),
            }.get(self._state, QColor(255, 255, 255, 70))
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(ring, 2.0))
            painter.drawEllipse(center, radius - 1, radius - 1)

        if self._badge:
            badge_text = "!" if self._state == "error" else str(self._badge)
            badge_color = "#ff5f57" if self._state == "error" else "#ffb800"
            badge_center = center + QPointF(radius * 0.78, -radius * 0.78)
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.setBrush(QColor(badge_color))
            painter.drawEllipse(badge_center, 10, 10)
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(badge_center.x() - 10, badge_center.y() - 10, 20, 20),
                Qt.AlignCenter,
                badge_text,
            )
        painter.end()

    # ---------- 位置 ----------
    def center_global(self) -> QPoint:
        return self.mapToGlobal(QPoint(self.width() // 2, self.height() // 2))

    def restore_or_default(self):
        if self._placed:
            return
        if self._saved_x is not None and self._saved_y is not None:
            screen = QApplication.screenAt(QPoint(self._saved_x, self._saved_y))
            if screen is not None:
                self.move(self._saved_x, self._saved_y)
                self._placed = True
                return
        self._place_default()

    def _place_default(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(100, 100)
            return
        area = screen.availableGeometry()
        self.move(
            area.right() - self.width() - 12,
            area.center().y() - self.height() // 2,
        )
        self._placed = True

    def snap_to_edge(self):
        screen = QApplication.screenAt(self.center_global()) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        margin = 8
        center = self.center_global()
        if center.x() < area.center().x():
            x = area.left() + margin
        else:
            x = area.right() - self.width() - margin
        y = max(area.top() + margin, min(self.y(), area.bottom() - self.height() - margin))
        self.move(x, y)

    def showEvent(self, event):
        if not self._placed:
            self.restore_or_default()
        super().showEvent(event)

    def shake(self):
        if self._shake_anim is not None:
            self._shake_anim.stop()
        start = self.pos()
        animation = QPropertyAnimation(self, b"pos", self)
        animation.setDuration(360)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        for pos, dx in (
            (0.0, 0),
            (0.15, 8),
            (0.3, -8),
            (0.45, 6),
            (0.6, -6),
            (0.8, 2),
            (1.0, 0),
        ):
            animation.setKeyValueAt(pos, start + QPoint(dx, 0))
        animation.start()
        self._shake_anim = animation

    # ---------- 鼠标 ----------
    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._double_fired = False
            self._press_global = event.globalPosition().toPoint()
            self._press_pos = self.pos()
            self._dragging = False
            self._click_timer.stop()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._press_global
            if not self._dragging and delta.manhattanLength() > 4:
                self._dragging = True
                self.setCursor(Qt.SizeAllCursor)
            if self._dragging:
                self.move(self._press_pos + delta)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._double_fired:
                self._double_fired = False
                event.accept()
                return
            if self._dragging:
                self._dragging = False
                self.unsetCursor()
                self.snap_to_edge()
                self.position_changed.emit(self.pos())
            else:
                self._click_timer.start()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._double_fired = True
            self._click_timer.stop()
            self.double_clicked.emit()
            event.accept()

    def wheelEvent(self, event):
        self.mode_cycled.emit(1 if event.angleDelta().y() > 0 else -1)
        event.accept()

    def contextMenuEvent(self, event):
        self.menu_requested.emit(event.globalPos())
        event.accept()

    def closeEvent(self, event):
        self.hide()
        event.ignore()


class ResultPopup(QWidget):
    paste_requested = Signal(str)
    regenerate_requested = Signal()
    expand_requested = Signal()
    stop_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(440)
        self.target_hwnd = 0
        self._meta = ""
        self._anchor = QPoint()
        self._build()
        self.setStyleSheet(STYLE + POPUP_STYLE)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        card = QFrame()
        card.setObjectName("popupCard")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(20, 30, 60, 55))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        self.title = QLabel("灵感")
        self.title.setObjectName("popupTitle")
        close_btn = QPushButton("×")
        close_btn.setObjectName("popupX")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self.meta = QLabel("")
        self.meta.setObjectName("hint")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)

        self.cards_host = QWidget()
        self.cards_host.setObjectName("popupCards")
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignTop)
        layout.addWidget(self.cards_host)

        self.error_label = QLabel("")
        self.error_label.setObjectName("popupError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        self.status = QLabel("")
        self.status.setObjectName("hint")
        layout.addWidget(self.status)

        footer = QHBoxLayout()
        self.again_btn = QPushButton("换一批")
        self.again_btn.setObjectName("mini")
        self.again_btn.clicked.connect(self._regenerate)
        self.retry_btn = QPushButton("重试")
        self.retry_btn.setObjectName("mini")
        self.retry_btn.clicked.connect(self._regenerate)
        self.retry_btn.hide()
        self.expand_btn = QPushButton("展开完整面板")
        self.expand_btn.setObjectName("ghost")
        self.expand_btn.clicked.connect(self._expand)
        footer.addWidget(self.again_btn)
        footer.addWidget(self.retry_btn)
        footer.addStretch(1)
        footer.addWidget(self.expand_btn)
        layout.addLayout(footer)

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _copy(self, candidate: dict):
        text = candidate.get("text", "")
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.status.setText("已复制到剪贴板")
        QTimer.singleShot(1400, lambda: self.status.setText(""))

    def _paste(self, candidate: dict):
        text = candidate.get("text", "")
        if not text:
            return
        self.paste_requested.emit(text)
        self.hide()

    def _regenerate(self):
        self.hide()
        self.regenerate_requested.emit()

    def _expand(self):
        self.hide()
        self.expand_requested.emit()

    def show_results(self, candidates: list, meta: dict, anchor: QPoint, target_hwnd: int):
        self.target_hwnd = int(target_hwnd or 0)
        self._anchor = QPoint(anchor)
        self._meta = meta
        self._clear_cards()
        self.error_label.hide()
        self.status.setText("")
        self.again_btn.show()
        self.retry_btn.hide()
        self.expand_btn.show()
        self.title.setText(f"{len(candidates)} 个灵感 · {meta.get('mode', '续写')}")
        self.meta.setText(
            f"{meta.get('style', '平实')} · 光标上下文 "
            f"{len(meta.get('context', ''))} 字"
        )
        for index, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                candidate = {"label": "", "text": str(candidate)}
            card = CandidateCard(index, candidate)
            card.copy_requested.connect(self._copy)
            card.paste_requested.connect(self._paste)
            self.cards_layout.addWidget(card)
        self.adjustSize()
        self._place(anchor)
        self.show()
        self.raise_()

    def show_error(self, message: str, anchor: QPoint, target_hwnd: int):
        self.target_hwnd = int(target_hwnd or 0)
        self._anchor = QPoint(anchor)
        self._clear_cards()
        self.title.setText("生成失败")
        self.meta.setText("可以重试，或先在完整面板里检查设置。")
        self.error_label.setText(message)
        self.error_label.show()
        self.status.setText("")
        self.again_btn.hide()
        self.retry_btn.show()
        self.expand_btn.show()
        self.adjustSize()
        self._place(anchor)
        self.show()
        self.raise_()

    def _place(self, anchor: QPoint):
        self.adjustSize()
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        width = self.width()
        height = self.height()
        x = anchor.x() + 20
        if x + width > area.right() - 8:
            x = anchor.x() - width - 20
        x = max(area.left() + 8, min(x, area.right() - width - 8))
        y = anchor.y() - height // 2
        y = max(area.top() + 8, min(y, area.bottom() - height - 8))
        self.move(x, y)

    def hide_if_outside(self, x: int, y: int):
        if self.isVisible() and not self.frameGeometry().contains(QPoint(x, y)):
            self.hide()

    def closeEvent(self, event):
        self.hide()
        event.ignore()


# ---------------------------------------------------------------------------
# 托盘 / 应用
# ---------------------------------------------------------------------------
class TrayApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setWindowIcon(make_icon())

        self.win = MuseWindow()
        self.win.settings_changed.connect(self._apply_hotkey)
        self.win.notice.connect(self._notify)

        self.tray = QSystemTrayIcon(make_icon(), self.app)
        self.tray.setToolTip("写作灵感 Muse — 悬浮球 / Ctrl+Space ×2 / 中键")
        self.tray_menu = QMenu()
        menu = self.tray_menu
        menu.addAction("显示 / 隐藏 Muse", self.win.toggle_show)
        menu.addAction("立即生成", self.win.trigger_quick)
        menu.addAction("显示 / 隐藏悬浮球", self._toggle_ball)
        menu.addAction("从剪贴板生成", self._from_clipboard)
        menu.addSeparator()
        menu.addAction("设置…", self._open_settings)
        menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self.signals = MuseSignals()
        self.signals.middle_down.connect(self.win.on_middle_down)
        self.signals.middle_up.connect(self.win.on_middle_up)
        self.signals.left_down.connect(
            lambda x, y: self.win.popup.hide_if_outside(x, y)
        )
        self.signals.typing.connect(self.win.on_typing)
        self.signals.hotkey.connect(self.win.trigger_quick)
        self.win.ball_menu_requested.connect(self._show_ball_menu)
        self.input_watcher = GlobalInput(self.signals)
        self.input_watcher.start()
        self._apply_hotkey()
        self.win.show_ball()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.win.show()

    def _apply_hotkey(self):
        hotkey = CFG.get("hotkey", {})
        self.input_watcher.set_hotkey(
            bool(hotkey.get("enabled", True)),
            hotkey.get("sequence", "ctrl+space,ctrl+space"),
            int(hotkey.get("judge_ms", 450)),
        )

    def _show_ball_menu(self, position: QPoint):
        menu = QMenu()
        menu.addAction("打开 Muse", self.win.toggle_show)
        menu.addAction("立即生成", self.win.trigger_quick)
        mode_menu = menu.addMenu("本次模式")
        for mode in MODES:
            action = mode_menu.addAction(mode)
            action.triggered.connect(
                lambda _checked=False, chosen=mode: self.win.set_mode(chosen)
            )
        menu.addSeparator()
        menu.addAction("设置…", self.win.open_settings)
        menu.addAction("隐藏悬浮球", self.win.hide_ball)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        menu.exec(position)

    def _toggle_ball(self):
        if self.win.ball.isVisible():
            self.win.hide_ball()
        else:
            self.win.show_ball()

    def _notify(self, message: str):
        if self.tray.isVisible():
            self.tray.showMessage(
                "写作灵感 Muse", message, QSystemTrayIcon.Information, 3000
            )

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.win.toggle_show()

    def _from_clipboard(self):
        text = QApplication.clipboard().text().strip()
        if text:
            self.win.generate_from_text(text)
        else:
            self.win.toggle_show()
            self.win.status.setText("剪贴板里没有文字")

    def _open_settings(self):
        if not self.win.isVisible():
            self.win._activate_show()
        self.win.open_settings()

    def quit(self):
        self.input_watcher.stop()
        self.win.shutdown()
        self.tray.hide()
        self.app.quit()


# ---------------------------------------------------------------------------
# 样式
# ---------------------------------------------------------------------------
STYLE = """
QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"; font-size: 10pt; color: #2b2f36; }
QWidget#root, QDialog { background: #f6f7fa; }
QWidget#page, QWidget#cards { background: transparent; }
QLabel#title { font-size: 15pt; font-weight: 700; color: #1f2430; }
QLabel#hint, QLabel#status { color: #8a919c; font-size: 8.5pt; }
QLabel#count { color: #a3aab5; font-size: 8pt; }
QLabel#section { color: #5d6573; font-size: 9pt; font-weight: 600; }
QLabel#num { color: #c3c9d4; font-size: 8.5pt; }
QLabel#badge { color: #4c6fff; font-size: 8.5pt; font-weight: 600; }
QLabel#body { color: #2b2f36; font-size: 10pt; }
QPlainTextEdit#input { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 8px; padding: 8px; selection-background-color: #dfe6ff; }
QPlainTextEdit { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 8px; padding: 8px; }
QLineEdit { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 6px; padding: 6px 8px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: #4c6fff; }
QComboBox { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 6px; padding: 5px 8px; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #e3e6ec; selection-background-color: #eef2ff; selection-color: #2b2f36; }
QSpinBox, QDoubleSpinBox, QKeySequenceEdit { background: #ffffff; border: 1px solid #e3e6ec; border-radius: 6px; padding: 5px 8px; }
QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus { border-color: #4c6fff; }
QPushButton { background: #4c6fff; color: #ffffff; border: none; border-radius: 6px; padding: 7px 14px; }
QPushButton:hover { background: #3a5ae0; }
QPushButton:pressed { background: #304cc4; }
QPushButton:disabled { background: #c7d0f7; }
QPushButton#ghost { background: #eef1f7; color: #4b5563; }
QPushButton#ghost:hover { background: #e4e9f2; }
QPushButton#mini { background: transparent; color: #4c6fff; border: 1px solid #dbe2ff; border-radius: 5px; padding: 2px 8px; font-size: 8.5pt; }
QPushButton#mini:hover { background: #eef2ff; }
QPushButton#mini:disabled { color: #b6c0d6; border-color: #e8ecf5; }
QFrame#card { background: #ffffff; border: 1px solid #e6e9f0; border-radius: 9px; }
QFrame#card:hover { border-color: #b9c6ff; background: #fbfcff; }
QCheckBox { color: #5b6472; font-size: 9pt; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: transparent; color: #8a919c; padding: 7px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #2b2f36; border-bottom-color: #4c6fff; font-weight: 600; }
QTabBar::tab:hover { color: #4c6fff; }
QListWidget { background: #ffffff; border: 1px solid #e6e9f0; border-radius: 8px; }
QListWidget::item { padding: 7px 8px; border-bottom: 1px solid #f1f3f7; color: #4b5563; }
QListWidget::item:selected { background: #eef2ff; color: #2b2f36; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #d7dce6; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #c3cad8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #2b2f36; color: #ffffff; border: none; padding: 4px 6px; }
"""

POPUP_STYLE = """
QFrame#popupCard { background: #ffffff; border: 1px solid #e3e7f0; border-radius: 16px; }
QLabel#popupTitle { font-size: 12pt; font-weight: 700; color: #1f2430; }
QPushButton#popupX { background: transparent; color: #9aa3b2; border: none; padding: 0 7px; font-size: 15pt; }
QPushButton#popupX:hover { background: #eef2ff; color: #4c6fff; border-radius: 6px; }
QWidget#popupCards { background: transparent; }
QLabel#popupError { color: #d64545; font-size: 9pt; background: #fff5f5; border: 1px solid #ffdada; border-radius: 8px; padding: 8px; }
"""


def make_icon() -> QIcon:
    """优先加载 assets 里的多尺寸图标，失败时退回旧灯泡。"""
    asset_dir = Path(__file__).resolve().parent / "assets"
    icon = QIcon()
    for size, name in (
        (16, "muse-tray-16.png"),
        (20, "muse-tray-20.png"),
        (24, "muse-tray-24.png"),
        (32, "muse-tray-32.png"),
        (48, "muse-icon-48.png"),
        (64, "muse-icon-64.png"),
        (128, "muse-icon-128.png"),
        (256, "muse-icon-256.png"),
    ):
        path = asset_dir / name
        if path.exists():
            icon.addFile(str(path), QSize(size, size))
    if not icon.isNull():
        return icon

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#ffb800"))
    painter.drawEllipse(22, 10, 20, 20)
    painter.setBrush(QColor("#4c6fff"))
    painter.drawRoundedRect(27, 30, 10, 14, 2, 2)
    painter.drawRoundedRect(24, 46, 16, 4, 2, 2)
    pen = QPen(QColor("#ffb800"), 3, Qt.SolidLine, Qt.RoundCap)
    painter.setPen(pen)
    for dx, dy in ((0, -8), (12, -4), (12, 10), (0, 14)):
        painter.drawLine(32, 20, 32 + dx, 20 + dy)
    painter.end()
    return QIcon(pixmap)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def _acquire_single_instance():
    if not IS_WINDOWS:
        return 1
    handle = kernel32.CreateMutexW(None, False, "Local\\WritingMuse_v2")
    if not handle:
        return 1
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def main() -> int:
    if not IS_WINDOWS:
        print("写作灵感 Muse 目前只支持 Windows。")
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("写作灵感 Muse")
    app.setQuitOnLastWindowClosed(False)

    _mutex = _acquire_single_instance()
    if _mutex is None:
        QMessageBox.information(
            None, "写作灵感 Muse", "Muse 已经在运行了，请点系统托盘里的灯泡。"
        )
        return 0

    try:
        tray = TrayApp(app)
    except Exception as error:
        QMessageBox.critical(
            None, "启动失败", f"写作灵感 Muse 启动失败：\n{error}"
        )
        return 1
    # 保持引用，避免被垃圾回收
    app._muse_tray = tray  # type: ignore[attr-defined]
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

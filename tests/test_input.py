# -*- coding: utf-8 -*-
from types import SimpleNamespace

from pynput.keyboard import Key, KeyCode

from main import GlobalInput, WM_KEYDOWN


class FakeSignal:
    def __init__(self):
        self.values = []

    def emit(self, value=None):
        self.values.append(value)


class FakeSignals:
    def __init__(self):
        self.typing = FakeSignal()
        self.hotkey = FakeSignal()
        self.middle_down = FakeSignal()
        self.middle_up = FakeSignal()
        self.left_down = FakeSignal()
        self.left_up_drag = FakeSignal()


def make_input():
    signals = FakeSignals()
    listener = GlobalInput(signals)
    listener._kb_injected = False
    listener._mods = set()
    return listener, signals


def test_ime_key_emits_tick():
    listener, signals = make_input()
    listener._on_press(KeyCode(vk=229))  # 中文输入法下常见的 VK_PROCESSKEY
    assert signals.typing.values == ["\x00"]


def test_printable_key_emits_char():
    listener, signals = make_input()
    listener._on_press(KeyCode.from_char("a"))
    assert signals.typing.values == ["a"]


def test_backspace_and_enter():
    listener, signals = make_input()
    listener._on_press(Key.backspace)
    listener._on_press(Key.enter)
    assert signals.typing.values == ["\x08", "\n"]


def test_shortcut_keys_are_ignored():
    listener, signals = make_input()
    listener._mods = {"ctrl"}
    listener._on_press(KeyCode.from_char("c"))
    assert signals.typing.values == []


def test_hotkey_b_double_ctrl_space_emits():
    listener, signals = make_input()
    listener.set_hotkey(True, "ctrl+space,ctrl+space", 450)
    ctrl = SimpleNamespace(vkCode=0xA2, flags=0)
    space = SimpleNamespace(vkCode=0x20, flags=0)
    assert listener._kb_filter(WM_KEYDOWN, ctrl) is True
    assert listener._kb_filter(WM_KEYDOWN, space) is True
    assert signals.hotkey.values == []
    assert listener._kb_filter(WM_KEYDOWN, space) is True
    assert signals.hotkey.values == [None]


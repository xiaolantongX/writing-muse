# -*- coding: utf-8 -*-
import pytest
from PySide6.QtGui import QKeySequence

from main import (
    HotkeySequence,
    hotkey_label,
    parse_hotkey,
    parse_sequence,
    qt_to_combo,
    sequence_label,
)


def test_parse_hotkey():
    mods, vk = parse_hotkey("ctrl+alt+m")
    assert mods == {"ctrl", "alt"}
    assert vk == ord("M")


def test_parse_hotkey_named_keys():
    assert parse_hotkey("ctrl+shift+space")[1] == 0x20
    assert parse_hotkey("ctrl+f8")[1] == 0x77


@pytest.mark.parametrize("combo", ["", "m", "ctrl+", "ctrl+alt", "ctrl+alt+?"])
def test_parse_bad_hotkey(combo):
    assert parse_hotkey(combo)[1] is None


def test_qt_roundtrip():
    combo = qt_to_combo(QKeySequence("Ctrl+Alt+M"))
    assert combo == "ctrl+alt+m"
    assert hotkey_label(combo) == "Ctrl+Alt+M"


def test_qt_to_combo_special_key():
    assert qt_to_combo(QKeySequence("Ctrl+Shift+Space")) == "ctrl+shift+space"


def test_parse_sequence():
    steps = parse_sequence("ctrl+space,ctrl+space")
    assert steps == [({"ctrl"}, 0x20), ({"ctrl"}, 0x20)]
    assert parse_sequence("ctrl+space") == [({"ctrl"}, 0x20)]
    assert parse_sequence("ctrl+space,,bad") is None
    assert parse_sequence("") is None


def test_sequence_label():
    assert sequence_label("ctrl+space,ctrl+space") == "Ctrl+Space ×2"
    assert sequence_label("ctrl+alt+m") == "Ctrl+Alt+M"


def test_hotkey_sequence_b_double_press():
    matcher = HotkeySequence(parse_sequence("ctrl+space,ctrl+space"), 450)
    assert matcher.feed({"ctrl"}, 0x20, 0.0) is False
    assert matcher.feed({"ctrl"}, 0x20, 0.2) is True


def test_hotkey_sequence_timeout_and_reset():
    matcher = HotkeySequence(parse_sequence("ctrl+space,ctrl+space"), 450)
    assert matcher.feed({"ctrl"}, 0x20, 0.0) is False
    assert matcher.feed({"ctrl"}, 0x20, 1.0) is False  # 超时，重新算第一次
    assert matcher.feed({"ctrl"}, 0x20, 1.2) is True


def test_hotkey_sequence_wrong_key_resets():
    matcher = HotkeySequence(parse_sequence("ctrl+space,ctrl+space"), 450)
    assert matcher.feed({"ctrl"}, 0x20, 0.0) is False
    assert matcher.feed({"ctrl"}, ord("A"), 0.1) is False
    assert matcher.feed({"ctrl"}, 0x20, 0.2) is False
    assert matcher.feed({"ctrl"}, 0x20, 0.3) is True

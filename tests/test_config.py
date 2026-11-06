# -*- coding: utf-8 -*-
import json
import shutil
import uuid
from pathlib import Path

import pytest

from config import (
    DEFAULT_CONFIG,
    deep_merge,
    load_config,
    load_history,
    mask_key,
    normalize_config,
    normalize_exts,
    push_history,
    save_config,
    save_history,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def tmp_dir():
    path = ROOT / ".pytest_tmp" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_deep_merge_keeps_defaults_and_unknown_keys():
    base = {"a": 1, "nested": {"x": 1, "y": 2}}
    merged = deep_merge(base, {"nested": {"y": 9}, "extra": "kept"})
    assert merged == {"a": 1, "nested": {"x": 1, "y": 9}, "extra": "kept"}
    assert base["nested"]["y"] == 2


def test_normalize_exts():
    assert normalize_exts("md, txt .MD") == [".md", ".txt"]
    assert normalize_exts([".markdown", "txt"]) == [".markdown", ".txt"]
    assert normalize_exts([]) == DEFAULT_CONFIG["auto_guide"]["exts"]


def test_normalize_clamps_and_fills():
    cfg = normalize_config(
        {
            "temperature": 99,
            "max_context_chars": -1,
            "timeout_seconds": "abc",
            "auto_guide": {"pause_seconds": 0.1, "exts": "md txt"},
        }
    )
    assert cfg["temperature"] == 2.0
    assert cfg["max_context_chars"] == 200
    assert cfg["timeout_seconds"] == 60
    assert cfg["auto_guide"]["pause_seconds"] == 0.5
    assert cfg["auto_guide"]["exts"] == [".md", ".txt"]
    assert cfg["version"] == 2


def test_ball_and_hotkey_defaults():
    cfg = normalize_config({})
    assert cfg["hotkey"]["sequence"] == "ctrl+space,ctrl+space"
    assert cfg["hotkey"]["judge_ms"] == 450
    assert cfg["ball"]["size"] == 64
    assert cfg["ball"]["opacity"] == 0.82
    assert cfg["auto_guide"]["enabled"] is False
    assert cfg["last"]["style"] == "X文章"


def test_save_and_load_roundtrip(tmp_dir):
    path = tmp_dir / "config.json"
    cfg = load_config(path, env={})
    cfg["api_key"] = "sk-test-123456"
    cfg["hotkey"]["sequence"] = "ctrl+alt+j,ctrl+alt+j"
    cfg["hotkey"]["judge_ms"] = 300
    cfg["ball"]["x"] = 1200
    cfg["ball"]["y"] = 400
    cfg["auto_guide"]["exts"] = ["md"]
    saved = save_config(cfg, path)
    assert saved["hotkey"]["sequence"] == "ctrl+alt+j,ctrl+alt+j"
    assert saved["hotkey"]["judge_ms"] == 300

    loaded = load_config(path, env={})
    assert loaded["api_key"] == "sk-test-123456"
    assert loaded["auto_guide"]["exts"] == [".md"]
    assert loaded["ball"]["x"] == 1200
    assert not (tmp_dir / "config.json.tmp").exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 2
    assert "combo" not in raw["hotkey"]


def test_env_key_fallback(tmp_dir):
    path = tmp_dir / "missing.json"
    cfg = load_config(path, env={"DEEPSEEK_API_KEY": "sk-env"})
    assert cfg["api_key"] == "sk-env"


def test_broken_config_falls_back(tmp_dir):
    path = tmp_dir / "config.json"
    path.write_text("{not json", encoding="utf-8")
    cfg = load_config(path, env={})
    assert cfg["model"] == DEFAULT_CONFIG["model"]


def test_history_push_and_limit(tmp_dir):
    path = tmp_dir / "history.json"
    for index in range(5):
        items = push_history({"ts": str(index)}, path, limit=3)
    assert [item["ts"] for item in items] == ["4", "3", "2"]
    assert len(load_history(path)) == 3
    save_history([], path)
    assert load_history(path) == []


def test_mask_key():
    assert mask_key("") == "未设置"
    assert mask_key("short") == "*****"
    assert mask_key("sk-1234567890abcdef").startswith("sk-")
    assert "1234567890" not in mask_key("sk-1234567890abcdef")

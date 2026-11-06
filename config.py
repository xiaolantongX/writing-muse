# -*- coding: utf-8 -*-
"""配置与本地历史：默认值、深层合并、原子写入。

这个模块不依赖 PySide6，方便单独测试。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_PATH = BASE_DIR / "history.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-chat",
    "max_context_chars": 3000,
    "temperature": 1.1,
    "timeout_seconds": 60,
    "trigger": "mouse_middle",
    "hotkey": {
        "enabled": True,
        "sequence": "ctrl+space,ctrl+space",
        "judge_ms": 450,
    },
    "ball": {
        "enabled": True,
        "x": None,
        "y": None,
        "size": 64,
        "opacity": 0.82,
    },
    "auto_guide": {
        "enabled": False,
        "pause_seconds": 2.5,
        "min_chars": 8,
        "exts": [".md", ".txt", ".markdown"],
    },
    "history": {"enabled": True},
    "style_sample": "",
    "prices_cny_per_1m": {"input": 2.0, "output": 8.0},
    "window": {"x": None, "y": None, "w": 540, "h": 660},
    "stats": {"tokens": 0, "cost": 0.0, "calls": 0},
    "last": {"mode": "续写下文", "style": "X文章"},
}


def deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典；override 里的未知键保留，默认值只用来补缺。"""
    out = copy.deepcopy(base)
    if not isinstance(override, dict):
        return out
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _clamp_float(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_exts(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace("，", ",").replace(" ", ",").split(",")
    if not isinstance(value, (list, tuple)):
        return list(DEFAULT_CONFIG["auto_guide"]["exts"])
    out: list[str] = []
    for item in value:
        text = str(item).strip().lower()
        if not text:
            continue
        if not text.startswith("."):
            text = "." + text
        if text not in out:
            out.append(text)
    return out or list(DEFAULT_CONFIG["auto_guide"]["exts"])


def normalize_config(cfg: dict) -> dict:
    """把任意来源的配置整理成当前版本可用的形状（不修改传入对象）。"""
    cfg = copy.deepcopy(cfg) if isinstance(cfg, dict) else {}
    cfg["version"] = 2
    cfg["api_key"] = str(cfg.get("api_key") or "").strip()
    cfg["base_url"] = str(
        cfg.get("base_url") or DEFAULT_CONFIG["base_url"]
    ).strip().rstrip("/")
    cfg["model"] = str(cfg.get("model") or DEFAULT_CONFIG["model"]).strip()
    cfg["max_context_chars"] = _clamp_int(
        cfg.get("max_context_chars"), 3000, 200, 20000
    )
    cfg["temperature"] = _clamp_float(cfg.get("temperature"), 1.1, 0.0, 2.0)
    cfg["timeout_seconds"] = _clamp_int(cfg.get("timeout_seconds"), 60, 5, 300)

    hotkey = cfg.get("hotkey")
    if not isinstance(hotkey, dict):
        hotkey = {}
    hotkey["enabled"] = bool(hotkey.get("enabled", True))
    hotkey["sequence"] = str(
        hotkey.get("sequence") or "ctrl+space,ctrl+space"
    ).strip().lower()
    hotkey["judge_ms"] = _clamp_int(hotkey.get("judge_ms"), 450, 150, 1500)
    hotkey.pop("combo", None)
    cfg["hotkey"] = hotkey

    ball = cfg.get("ball")
    if not isinstance(ball, dict):
        ball = {}
    ball["enabled"] = bool(ball.get("enabled", True))
    for axis in ("x", "y"):
        value = ball.get(axis)
        ball[axis] = int(value) if isinstance(value, (int, float)) else None
    ball["size"] = _clamp_int(ball.get("size"), 64, 40, 96)
    ball["opacity"] = round(_clamp_float(ball.get("opacity"), 0.82, 0.3, 1.0), 2)
    cfg["ball"] = ball

    auto = cfg.get("auto_guide")
    if not isinstance(auto, dict):
        auto = {}
    # 感知流程已下线：保留字段做旧配置兼容，但不再生效
    auto["enabled"] = False
    auto["pause_seconds"] = _clamp_float(auto.get("pause_seconds"), 2.5, 0.5, 30.0)
    auto["min_chars"] = _clamp_int(auto.get("min_chars"), 8, 1, 200)
    auto["exts"] = normalize_exts(auto.get("exts"))
    cfg["auto_guide"] = auto

    history = cfg.get("history")
    if not isinstance(history, dict):
        history = {}
    history["enabled"] = bool(history.get("enabled", True))
    cfg["history"] = history

    cfg["style_sample"] = str(cfg.get("style_sample") or "").strip()

    prices = cfg.get("prices_cny_per_1m")
    if not isinstance(prices, dict):
        prices = {}
    prices["input"] = _clamp_float(prices.get("input"), 2.0, 0.0, 1000.0)
    prices["output"] = _clamp_float(prices.get("output"), 8.0, 0.0, 1000.0)
    cfg["prices_cny_per_1m"] = prices

    window = cfg.get("window")
    if not isinstance(window, dict):
        window = {}
    for axis in ("x", "y"):
        value = window.get(axis)
        window[axis] = int(value) if isinstance(value, (int, float)) else None
    window["w"] = _clamp_int(window.get("w"), 540, 420, 1600)
    window["h"] = _clamp_int(window.get("h"), 660, 420, 1400)
    cfg["window"] = window

    stats = cfg.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    stats["tokens"] = _clamp_int(stats.get("tokens"), 0, 0, 10**12)
    stats["cost"] = round(_clamp_float(stats.get("cost"), 0.0, 0.0, 10**9), 4)
    stats["calls"] = _clamp_int(stats.get("calls"), 0, 0, 10**9)
    cfg["stats"] = stats

    last = cfg.get("last")
    if not isinstance(last, dict):
        last = {}
    last["mode"] = str(last.get("mode") or "续写下文")
    last["style"] = str(last.get("style") or "X文章")
    cfg["last"] = last
    return cfg


def load_config(path: str | Path = CONFIG_PATH, env: dict | None = None) -> dict:
    """读取配置：默认值 <- config.json <- 环境变量里缺失的 API Key。"""
    env = os.environ if env is None else env
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    file_path = Path(path)
    if file_path.exists():
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cfg = deep_merge(cfg, data)
        except (OSError, ValueError):
            pass
    if not cfg.get("api_key"):
        cfg["api_key"] = env.get("DEEPSEEK_API_KEY", "")
    return normalize_config(cfg)


def _atomic_write(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def save_config(cfg: dict, path: str | Path = CONFIG_PATH) -> dict:
    """规范化并原子写入；返回真正落盘的内容。"""
    data = normalize_config(cfg)
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return data


def load_history(path: str | Path = HISTORY_PATH, limit: int = 50) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)][: max(0, limit)]


def save_history(
    items: list[dict], path: str | Path = HISTORY_PATH, limit: int = 50
) -> list[dict]:
    kept = [item for item in items if isinstance(item, dict)][: max(0, limit)]
    _atomic_write(
        path,
        json.dumps({"items": kept}, ensure_ascii=False, indent=2) + "\n",
    )
    return kept


def push_history(
    entry: dict, path: str | Path = HISTORY_PATH, limit: int = 50
) -> list[dict]:
    items = load_history(path, limit=limit)
    items.insert(0, entry)
    return save_history(items, path=path, limit=limit)


def mask_key(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return "未设置"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:3]}{'*' * 6}{key[-4:]}"

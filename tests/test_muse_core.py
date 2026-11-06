# -*- coding: utf-8 -*-
import json

import pytest

from muse_core import (
    MODES,
    STYLES,
    build_messages,
    estimate_cost,
    friendly_error,
    parse_candidates,
    prepare_context,
)


def test_parse_objects_with_labels():
    content = json.dumps(
        {
            "candidates": [
                {"label": "直给", "text": "A"},
                {"label": "换视角", "text": "B"},
                {"label": "打比方", "text": "C"},
            ]
        },
        ensure_ascii=False,
    )
    result = parse_candidates(content)
    assert [item["label"] for item in result] == ["直给", "换视角", "打比方"]
    assert [item["text"] for item in result] == ["A", "B", "C"]


def test_parse_strings_and_fence():
    content = '```json\n{"candidates": ["第一句。", "第二句。", "第三句。"]}\n```'
    result = parse_candidates(content)
    assert len(result) == 3
    assert result[0] == {"label": "", "text": "第一句。"}


def test_parse_trailing_prose():
    content = (
        '好的，这里是候选：\n{"candidates": ['
        '{"label": "一", "text": "甲"},'
        '{"label": "二", "text": "乙"},'
        '{"label": "三", "text": "丙"}]}\n希望有帮助。'
    )
    result = parse_candidates(content)
    assert [item["text"] for item in result] == ["甲", "乙", "丙"]


def test_parse_line_fallback():
    content = "1. 【直给】第一句\n2. 【换视角】第二句\n3. 【反常识】第三句"
    result = parse_candidates(content)
    assert result[0] == {"label": "直给", "text": "第一句"}
    assert result[2]["label"] == "反常识"


def test_parse_limits_to_three_and_dedupes():
    content = json.dumps(
        {"candidates": ["A", "A", "B", "C", "D"]}, ensure_ascii=False
    )
    result = parse_candidates(content)
    assert [item["text"] for item in result] == ["A", "B", "C"]


def test_parse_empty_raises():
    with pytest.raises(ValueError):
        parse_candidates("")
    with pytest.raises(ValueError):
        parse_candidates("模型什么都没说")


def test_build_messages_includes_style_sample_and_extra():
    messages = build_messages(
        "续写下文",
        "生动",
        "大模型幻觉的本质是",
        extra="写给产品经理看",
        style_sample="我写东西喜欢先给结论。",
    )
    assert messages[0]["role"] == "system"
    assert "比喻" in messages[0]["content"]
    assert "我写东西喜欢先给结论。" in messages[0]["content"]
    assert "写给产品经理看" in messages[1]["content"]
    assert "大模型幻觉的本质是" in messages[1]["content"]


def test_build_messages_caps_style_sample():
    messages = build_messages("灵感发散", "平实", "主题", style_sample="字" * 3000)
    assert len(messages[0]["content"]) < 3000


def test_prepare_context_direction():
    text = "开头" + "中间" * 100 + "结尾"
    tail, truncated = prepare_context(text, "续写下文", 20)
    assert truncated
    assert tail.endswith("结尾")
    head, _ = prepare_context(text, "换词润色", 20)
    assert head.startswith("开头")


def test_estimate_cost():
    cost = estimate_cost(1_000_000, 1_000_000, {"input": 2, "output": 8})
    assert cost == pytest.approx(10.0)
    assert estimate_cost(0, 0) == 0


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_has_spec(mode):
    messages = build_messages(mode, "平实", "一段原文")
    assert mode in messages[1]["content"]


def test_styles_are_non_empty():
    assert len(STYLES) >= 4
    assert all(value.strip() for value in STYLES.values())


def test_x_style_prompt_has_key_rules():
    desc = STYLES["X文章"]
    for token in ("前 2~3 行", "钩子", "书签", "点赞", "段落", "结尾"):
        assert token in desc
    assert "公众号" in desc


def test_friendly_error_maps_common_cases():
    assert "API Key" in friendly_error(Exception("Error code: 401 - invalid api key"))
    assert "余额" in friendly_error(Exception("402 Insufficient Balance"))
    assert "限流" in friendly_error(Exception("429 too many requests"))
    assert "超时" in friendly_error(Exception("Request timed out"))
    assert "网络" in friendly_error(Exception("APIConnectionError"))

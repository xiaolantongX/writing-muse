# -*- coding: utf-8 -*-
"""CLI 冒烟测试：验证 DeepSeek 连通性与提示词效果。

用法：
    python test_api.py
    python test_api.py --mode 灵感发散 --style 生动 --context "为什么 RAG 正在过时"
    python test_api.py --key sk-xxx --extra "写给产品经理看"
"""
import argparse
import os
import sys

from config import load_config
from muse_core import MODES, STYLES, estimate_cost, friendly_error, generate

BASE_CFG = load_config()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default="", help="DeepSeek API Key（也可写在 config.json 或环境变量 DEEPSEEK_API_KEY）")
    parser.add_argument("--mode", default="续写下文", choices=MODES)
    parser.add_argument("--style", default="X文章", choices=list(STYLES.keys()))
    parser.add_argument("--context", default="大模型幻觉的本质是")
    parser.add_argument("--extra", default="", help="补充要求，例如：写给产品经理看")
    args = parser.parse_args()

    key = args.key or BASE_CFG.get("api_key") or os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("请先提供 key：python test_api.py --key sk-xxx", file=sys.stderr)
        return 2

    try:
        result = generate(
            api_key=key,
            base_url=BASE_CFG.get("base_url", "https://api.deepseek.com"),
            model=BASE_CFG.get("model", "deepseek-chat"),
            mode=args.mode,
            style=args.style,
            context=args.context,
            temperature=float(BASE_CFG.get("temperature", 1.1)),
            extra=args.extra,
            style_sample=BASE_CFG.get("style_sample", ""),
            timeout=float(BASE_CFG.get("timeout_seconds", 60)),
        )
    except Exception as error:
        print(f"失败：{friendly_error(error)}", file=sys.stderr)
        return 1

    print(f"模式：{args.mode} ｜ 文风：{args.style} ｜ 原文：{args.context}")
    for index, candidate in enumerate(result["candidates"], 1):
        label = candidate.get("label") or "候选"
        print(f"\n{index}. [{label}] {candidate['text']}")

    prompt_tokens = result["prompt_tokens"]
    completion_tokens = result["completion_tokens"]
    cost = estimate_cost(
        prompt_tokens,
        completion_tokens,
        BASE_CFG.get("prices_cny_per_1m"),
    )
    print(
        f"\n本次 {prompt_tokens + completion_tokens:,} tokens ≈ ¥{cost:.4f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

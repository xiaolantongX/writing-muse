# -*- coding: utf-8 -*-
"""用本地假 OpenAI 服务验证 generate 的完整 HTTP 路径，不消耗真实额度。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from muse_core import generate
from muse_core import test_connection as check_connection

CANDIDATES = [
    {"label": "直给", "text": "概率采样的副产品。"},
    {"label": "打比方", "text": "像在填空，而不是在查资料。"},
    {"label": "换视角", "text": "这是接口错位，不是能力问题。"},
]


class FakeHandler(BaseHTTPRequestHandler):
    def _send(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._send(
                {
                    "object": "list",
                    "data": [
                        {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"}
                    ],
                }
            )
        else:
            self._send({"error": {"message": "not found"}}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        self.rfile.read(length)
        content = json.dumps({"candidates": CANDIDATES}, ensure_ascii=False)
        self._send(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "deepseek-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            }
        )

    def log_message(self, *args):
        pass


@pytest.fixture()
def base_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_generate_roundtrip(base_url):
    result = generate(
        api_key="sk-test",
        base_url=base_url,
        model="deepseek-chat",
        mode="续写下文",
        style="平实",
        context="大模型幻觉的本质是",
        timeout=5,
    )
    assert [item["label"] for item in result["candidates"]] == ["直给", "打比方", "换视角"]
    assert result["prompt_tokens"] == 10
    assert result["completion_tokens"] == 20


def test_generate_requires_key():
    with pytest.raises(RuntimeError, match="API Key"):
        generate(
            api_key="",
            base_url="http://127.0.0.1:1",
            model="deepseek-chat",
            mode="续写下文",
            style="平实",
            context="x",
        )


def test_test_connection_uses_models_endpoint(base_url):
    message = check_connection("sk-test", base_url, "deepseek-chat")
    assert "连接正常" in message
    assert "deepseek-chat" in message

"""Tests for the Ollama HTTP client.

We patch `requests.post` with `unittest.mock` so we don't need any extra
deps beyond `requests` itself.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest

from oracle_db_agent.llm import (
    ChatMessage,
    LlmResponse,
    OllamaClient,
    OllamaError,
    ToolCall,
    ToolSpec,
)


CHAT_URL = "http://localhost:11434/api/chat"


def _ok_response(content: str, tool_calls: list[dict] | None = None) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return {"message": msg}


def _mock_response(status: int, json_body=None, text_body: str = ""):
    """Build a mock object that looks like a `requests.Response`."""
    m = mock.Mock()
    m.status_code = status
    if json_body is not None:
        m.json.return_value = json_body
    else:
        m.json.side_effect = json.JSONDecodeError("no json", text_body, 0)
    m.text = text_body
    return m


# ----------------------------------------------------------------- tests


def test_plain_text_response() -> None:
    body = _ok_response("hello back")
    with mock.patch("oracle_db_agent.llm.ollama.requests.post", return_value=_mock_response(200, body)) as p:
        client = OllamaClient()
        out = client.chat([ChatMessage(role="user", content="hi")])
    assert isinstance(out, LlmResponse)
    assert out.text == "hello back"
    assert out.is_final_answer
    assert out.tool_calls == ()
    # And the URL was right
    assert p.call_args.args[0] == CHAT_URL


def test_tool_call_response() -> None:
    body = _ok_response(
        "",
        tool_calls=[
            {"function": {"name": "echo", "arguments": {"message": "hi"}}}
        ],
    )
    with mock.patch("oracle_db_agent.llm.ollama.requests.post", return_value=_mock_response(200, body)):
        client = OllamaClient()
        out = client.chat(
            [ChatMessage(role="user", content="do it")],
            tools=[ToolSpec(name="echo", description="echo", parameters={})],
        )
    assert not out.is_final_answer
    assert out.tool_calls == (ToolCall(name="echo", arguments={"message": "hi"}),)


def test_tool_call_with_stringified_arguments() -> None:
    """Some models return a JSON string in `arguments`. We parse it."""
    body = _ok_response(
        "",
        tool_calls=[
            {
                "function": {
                    "name": "show_user",
                    "arguments": json.dumps({"username": "SCOTT"}),
                }
            }
        ],
    )
    with mock.patch("oracle_db_agent.llm.ollama.requests.post", return_value=_mock_response(200, body)):
        client = OllamaClient()
        out = client.chat([ChatMessage(role="user", content="x")])
    assert out.tool_calls == (ToolCall(name="show_user", arguments={"username": "SCOTT"}),)


def test_request_body_shape() -> None:
    body = _ok_response("ok")
    captured: dict = {}

    def fake_post(*args, **kwargs):
        # requests.post(json=payload) — `payload` is a real dict, not a
        # string. Capture it as-is.
        captured["json"] = kwargs["json"]
        return _mock_response(200, body)

    with mock.patch("oracle_db_agent.llm.ollama.requests.post", side_effect=fake_post):
        client = OllamaClient(model="qwen2.5:7b")
        client.chat(
            [
                ChatMessage(role="system", content="sys"),
                ChatMessage(role="user", content="u1"),
                ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=(ToolCall(name="t", arguments={"a": 1}),),
                ),
                ChatMessage(role="tool", content="obs", tool_call_id="t"),
            ],
            tools=[ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})],
        )
    sent = captured["json"]
    assert sent["model"] == "qwen2.5:7b"
    assert sent["stream"] is False
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][1]["content"] == "u1"
    assert sent["messages"][2]["tool_calls"][0]["function"]["name"] == "t"
    assert sent["messages"][2]["tool_calls"][0]["function"]["arguments"] == {"a": 1}
    assert sent["messages"][3]["tool_call_id"] == "t"
    assert sent["tools"][0]["function"]["name"] == "t"


def test_5xx_raises() -> None:
    with mock.patch(
        "oracle_db_agent.llm.ollama.requests.post",
        return_value=_mock_response(500, text_body="internal"),
    ):
        client = OllamaClient()
        with pytest.raises(OllamaError) as exc:
            client.chat([ChatMessage(role="user", content="x")])
    assert "500" in str(exc.value)


def test_4xx_raises() -> None:
    with mock.patch(
        "oracle_db_agent.llm.ollama.requests.post",
        return_value=_mock_response(404, text_body="model not found"),
    ):
        client = OllamaClient()
        with pytest.raises(OllamaError) as exc:
            client.chat([ChatMessage(role="user", content="x")])
    assert "rejected" in str(exc.value)
    assert "404" in str(exc.value)


def test_connection_error_raises() -> None:
    import requests

    with mock.patch(
        "oracle_db_agent.llm.ollama.requests.post",
        side_effect=requests.ConnectionError("refused"),
    ):
        client = OllamaClient()
        with pytest.raises(OllamaError) as exc:
            client.chat([ChatMessage(role="user", content="x")])
    assert "not reachable" in str(exc.value)


def test_non_json_body_raises() -> None:
    with mock.patch(
        "oracle_db_agent.llm.ollama.requests.post",
        return_value=_mock_response(200, text_body="not json"),
    ):
        client = OllamaClient()
        with pytest.raises(OllamaError) as exc:
            client.chat([ChatMessage(role="user", content="x")])
    assert "non-JSON" in str(exc.value)

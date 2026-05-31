"""Tests for the AI agent loop and tool registry."""

from __future__ import annotations

import pytest

from sifty.ai import agent as ai_agent, tools as ai_tools
from sifty.ai.agent import (
    FallbackEvent,
    FinalAnswerEvent,
    ToolCallEvent,
    ToolResultEvent,
    _needs_confirm,
    run,
)
from sifty.ai.client import OllamaClient, OllamaUnavailable
from sifty.ai.tools import Tool


# ---------------------------------------------------------------------------
# Autonomy gating
# ---------------------------------------------------------------------------

def test_read_never_needs_confirm():
    for autonomy in ("ask", "low_risk_auto", "full_auto"):
        assert _needs_confirm("read", autonomy) is False


def test_low_risk_ask_needs_confirm():
    assert _needs_confirm("low", "ask") is True


def test_low_risk_auto_skips_confirm():
    assert _needs_confirm("low", "low_risk_auto") is False


def test_high_always_asks_unless_full_auto():
    assert _needs_confirm("high", "ask") is True
    assert _needs_confirm("high", "low_risk_auto") is True
    assert _needs_confirm("high", "full_auto") is False


# ---------------------------------------------------------------------------
# Fake tools
# ---------------------------------------------------------------------------

def _make_tool(name="do_thing", risk="read", result="done") -> Tool:
    return Tool(
        name=name,
        description="Test tool",
        parameters={"type": "object", "properties": {}, "required": []},
        risk=risk,
        handler=lambda args: result,
    )


def _fake_client_plain(monkeypatch, answer="Hello!"):
    """Client that always returns a plain text reply (no tool_calls)."""
    client = OllamaClient(host="http://localhost:11434", model="test", timeout=5.0)

    def fake_chat_once(messages, tools=None):
        return {"role": "assistant", "content": answer}

    monkeypatch.setattr(client, "chat_once", fake_chat_once)
    return client


def _fake_client_tool_then_answer(monkeypatch, tool_name, args, answer):
    """Client that calls a tool on the first turn, then gives a plain answer."""
    client = OllamaClient(host="http://localhost:11434", model="test", timeout=5.0)
    calls = [0]

    def fake_chat_once(messages, tools=None):
        if calls[0] == 0:
            calls[0] += 1
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": tool_name, "arguments": args}}],
            }
        return {"role": "assistant", "content": answer}

    monkeypatch.setattr(client, "chat_once", fake_chat_once)
    return client


# ---------------------------------------------------------------------------
# Agent loop — fallback (model ignores tools)
# ---------------------------------------------------------------------------

def test_plain_reply_is_fallback(monkeypatch):
    client = _fake_client_plain(monkeypatch, "I can help!")
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    events = list(run(client, msgs, autonomy="ask", tools=[]))
    assert len(events) == 1
    assert isinstance(events[0], FallbackEvent)
    assert events[0].text == "I can help!"


# ---------------------------------------------------------------------------
# Agent loop — single tool call auto-run (read risk)
# ---------------------------------------------------------------------------

def test_read_tool_runs_without_confirm(monkeypatch):
    tool = _make_tool("scan", risk="read", result="scan result")
    client = _fake_client_tool_then_answer(monkeypatch, "scan", {}, "Done, here's the summary.")

    confirmed = []
    events = list(run(client, [{"role": "user", "content": "scan"}],
                      autonomy="ask",
                      confirm=lambda p: confirmed.append(p) or True,
                      tools=[tool]))

    assert confirmed == []  # read tools never confirm
    call_ev = next(e for e in events if isinstance(e, ToolCallEvent))
    result_ev = next(e for e in events if isinstance(e, ToolResultEvent))
    final_ev = next(e for e in events if isinstance(e, FinalAnswerEvent))
    assert call_ev.tool_name == "scan"
    assert result_ev.result == "scan result"
    assert not result_ev.skipped
    assert final_ev.text == "Done, here's the summary."


# ---------------------------------------------------------------------------
# Agent loop — high-risk tool with autonomy=ask, confirm=deny
# ---------------------------------------------------------------------------

def test_high_tool_skipped_when_denied(monkeypatch):
    tool = _make_tool("delete", risk="high", result="deleted!")
    client = _fake_client_tool_then_answer(monkeypatch, "delete", {}, "OK, I skipped it.")

    events = list(run(client, [{"role": "user", "content": "clean"}],
                      autonomy="ask",
                      confirm=lambda p: False,   # always deny
                      tools=[tool]))

    result_ev = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result_ev.skipped is True
    assert "declined" in result_ev.result


# ---------------------------------------------------------------------------
# Agent loop — high-risk tool with autonomy=full_auto runs without confirm
# ---------------------------------------------------------------------------

def test_high_tool_runs_in_full_auto(monkeypatch):
    tool = _make_tool("delete", risk="high", result="deleted!")
    client = _fake_client_tool_then_answer(monkeypatch, "delete", {}, "Done.")

    confirmed = []
    events = list(run(client, [{"role": "user", "content": "clean"}],
                      autonomy="full_auto",
                      confirm=lambda p: confirmed.append(p) or True,
                      tools=[tool]))

    assert confirmed == []
    result_ev = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result_ev.result == "deleted!"
    assert not result_ev.skipped


# ---------------------------------------------------------------------------
# Agent loop — Ollama unavailable
# ---------------------------------------------------------------------------

def test_ollama_unavailable_yields_final(monkeypatch):
    client = OllamaClient(host="http://localhost:11434", model="test", timeout=5.0)
    monkeypatch.setattr(client, "chat_once", lambda *a, **kw: (_ for _ in ()).throw(OllamaUnavailable("down")))

    events = list(run(client, [{"role": "user", "content": "hi"}], tools=[]))
    assert len(events) == 1
    assert isinstance(events[0], FinalAnswerEvent)
    assert "unavailable" in events[0].text.lower()


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def test_all_tools_have_valid_risk():
    for t in ai_tools.TOOLS:
        assert t.risk in ("read", "low", "high"), f"{t.name} has invalid risk"


def test_tool_to_ollama_schema():
    t = _make_tool("mytool", risk="read")
    schema = t.to_ollama()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "mytool"


def test_get_tool_by_name():
    t = ai_tools.get("scan_junk")
    assert t is not None
    assert t.risk == "read"


def test_get_unknown_tool():
    assert ai_tools.get("no_such_tool") is None


def test_ollama_schemas_count():
    schemas = ai_tools.ollama_schemas()
    assert len(schemas) == len(ai_tools.TOOLS)

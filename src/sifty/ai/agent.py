"""AI agent loop with autonomy levels.

The agent sends the user's request to Ollama with a tool registry. Ollama may
respond with one or more tool calls; the agent dispatches them (subject to the
autonomy level and a confirm callback), appends the results, and re-submits
until the model produces a plain text answer.

Autonomy levels (set in config as ``ai.autonomy``):
  ``ask``           — confirm every ``low`` or ``high`` risk tool before running.
  ``low_risk_auto`` — auto-run ``low`` risk tools; confirm ``high`` ones.
  ``full_auto``     — run all tools automatically (still routes through safety.trash).

Models that don't emit ``tool_calls`` (not tool-capable) produce a plain reply
on the first iteration; the agent yields that as a :class:`FallbackEvent` so
callers can detect the downgrade.

Events are yielded as the agent progresses so callers (TUI, CLI) can display
each step live instead of waiting for the whole chain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Iterator

from ..infra.config import load_config
from .client import OllamaClient, OllamaUnavailable
from .tools import Tool, get as get_tool, ollama_schemas

logger = logging.getLogger("sifty.ai")

_MAX_ITERATIONS = 10


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

@dataclass
class ToolCallEvent:
    """The model is requesting a tool call."""
    tool_name: str
    args: dict
    risk: str           # from the Tool definition


@dataclass
class ToolResultEvent:
    """A tool has been executed (or skipped due to a denied confirm)."""
    tool_name: str
    result: str
    skipped: bool = False   # True when the user declined to run it


@dataclass
class FinalAnswerEvent:
    """The model produced a plain text reply — the agent is done."""
    text: str


@dataclass
class FallbackEvent:
    """The model doesn't support tools; plain advisory answer returned."""
    text: str


AgentEvent = ToolCallEvent | ToolResultEvent | FinalAnswerEvent | FallbackEvent


# ---------------------------------------------------------------------------
# Autonomy gating
# ---------------------------------------------------------------------------

def _needs_confirm(risk: str, autonomy: str) -> bool:
    """Return True if this risk level requires a confirm under the given autonomy."""
    if risk == "read":
        return False
    if autonomy == "full_auto":
        return False
    if autonomy == "low_risk_auto" and risk == "low":
        return False
    return True  # "ask" always confirms low+high; "low_risk_auto" confirms high


def autonomy_from_config(config=None) -> str:
    config = config or load_config()
    return config.section("ai").get("autonomy", "ask")


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run(
    client: OllamaClient,
    messages: list[dict],
    *,
    autonomy: str = "ask",
    confirm: Callable[[str], bool] | None = None,
    tools: list[Tool] | None = None,
) -> Iterator[AgentEvent]:
    """Drive an agentic conversation and yield :data:`AgentEvent` instances.

    ``messages`` is the full Ollama-format conversation history (including the
    system message). The caller appends any :class:`FinalAnswerEvent` text to
    its own history.

    ``confirm`` is called with a human-readable prompt when a tool requires
    confirmation; return ``True`` to proceed, ``False`` to skip.  Defaults to
    always-refuse (safe) when not provided.
    """
    if confirm is None:
        confirm = lambda _: False  # noqa: E731 — safe default, not interactive

    active_tools = tools if tools is not None else [
        t for t in __import__("sifty.ai.tools", fromlist=["TOOLS"]).TOOLS
    ]
    schemas = [t.to_ollama() for t in active_tools]
    tool_map = {t.name: t for t in active_tools}

    current_messages = list(messages)

    for _ in range(_MAX_ITERATIONS):
        try:
            msg = client.chat_once(current_messages, tools=schemas)
        except OllamaUnavailable as exc:
            logger.warning("agent: Ollama unavailable: %s", exc)
            yield FinalAnswerEvent(text=f"(AI unavailable: {exc})")
            return

        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # Plain text reply: either the final answer or a fallback.
            text = (msg.get("content") or "").strip()
            if not text:
                text = "(no response)"
            # Distinguish a first-turn plain reply (fallback) from a final answer.
            is_fallback = len(current_messages) == len(messages)  # no tools dispatched yet
            if is_fallback:
                yield FallbackEvent(text=text)
            else:
                yield FinalAnswerEvent(text=text)
            return

        # Append the assistant message with tool calls to history.
        current_messages.append(msg)

        # Dispatch each tool call.
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            args = raw_args if isinstance(raw_args, dict) else {}

            tool = tool_map.get(name) or get_tool(name)
            if tool is None:
                result_text = f"Unknown tool: {name}"
                yield ToolResultEvent(tool_name=name, result=result_text)
                current_messages.append({"role": "tool", "content": result_text})
                continue

            yield ToolCallEvent(tool_name=name, args=args, risk=tool.risk)

            if _needs_confirm(tool.risk, autonomy):
                prompt = _confirm_prompt(tool, args)
                if not confirm(prompt):
                    result_text = f"(user declined to run {name})"
                    yield ToolResultEvent(tool_name=name, result=result_text, skipped=True)
                    current_messages.append({"role": "tool", "content": result_text})
                    continue

            try:
                result_text = tool.handler(args)
            except Exception as exc:
                logger.exception("tool %s failed", name)
                result_text = f"Error running {name}: {exc}"

            yield ToolResultEvent(tool_name=name, result=result_text)
            current_messages.append({"role": "tool", "content": result_text})

    # Exhausted iterations without a plain reply.
    yield FinalAnswerEvent(text="(agent reached the iteration limit without a final answer)")


def _confirm_prompt(tool: Tool, args: dict) -> str:
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if args else ""
    return f"Run {tool.name}({args_str}) — risk: {tool.risk}"

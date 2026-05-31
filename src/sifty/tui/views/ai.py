"""AI screen: a chat panel backed by the local Ollama agent/advisor.

The transcript is a scrollable column of message widgets so both streaming
replies and tool-call events can be rendered in place as they arrive.

Conversation memory: the full message history is kept in ``_messages`` and sent
each turn so the model can refer back to earlier exchanges.  The system prompt
is built once on mount with a live machine-context snapshot so answers are
grounded in *this* machine's state.

Agentic mode: when Ollama supports tools the view drives :mod:`ai.agent`, which
yields :class:`ToolCallEvent`, :class:`ToolResultEvent`, and
:class:`FinalAnswerEvent`.  Models that ignore the tools field produce a
:class:`FallbackEvent` and the view transparently degrades to plain streaming.
"""

from __future__ import annotations

import logging

from rich.markdown import Markdown
from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from ...ai import context as ai_context
from ...ai.advisor import SYSTEM_PROMPT
from ...ai.agent import (
    FallbackEvent,
    FinalAnswerEvent,
    ToolCallEvent,
    ToolResultEvent,
    autonomy_from_config,
    run as agent_run,
)
from ...ai.client import OllamaClient, OllamaUnavailable
from ...ai.tools import TOOLS as ALL_TOOLS
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class AIView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Ask Sifty", classes="title")
        yield Static("Checking Ollama…", id="ai-status", classes="subtle")
        yield VerticalScroll(id="chat-log")
        yield Input(
            placeholder="Ask about cleanup, disk usage, safety…  (Enter to send)",
            id="ask",
        )

    def on_mount(self) -> None:
        self._client = OllamaClient.from_config()
        self._live: Static | None = None     # in-progress streaming widget
        self._messages: list[dict] = []      # full Ollama-format conversation history
        self._system = self._build_system()
        self._autonomy = autonomy_from_config()
        if self.workers_enabled():
            self.check_status()

    def _build_system(self) -> str:
        ctx = ai_context.build()
        if ctx:
            return f"{SYSTEM_PROMPT}\n\n{ctx}"
        return SYSTEM_PROMPT

    @work(thread=True, exclusive=True, group="ai-status")
    def check_status(self) -> None:
        ok = self._client.is_available()
        self.app.call_from_thread(self._set_status, ok)

    def _set_status(self, ok: bool) -> None:
        status = self.query_one("#ai-status", Static)
        if ok:
            status.update(
                f"[green]●[/green] Ollama connected · model [b]{self._client.model}[/b] · "
                f"autonomy: [b]{self._autonomy}[/b]"
            )
        else:
            status.update(
                f"[yellow]●[/yellow] Ollama not reachable at {self._client.host} — "
                f"start it and run `ollama pull {self._client.model}`"
            )

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if not question:
            return
        log = self.query_one("#chat-log", VerticalScroll)
        self.query_one("#ask", Input).value = ""
        await log.mount(Static(f"[b cyan]You[/b cyan]  {escape(question)}", classes="msg"))
        self._messages.append({"role": "user", "content": question})
        self.ask(list(self._messages))

    @work(thread=True, exclusive=True, group="ai-chat")
    def ask(self, messages: list[dict]) -> None:
        if not self._client.is_available():
            self.app.call_from_thread(self._show_error, "AI unavailable — is Ollama running?")
            return

        full_messages = [{"role": "system", "content": self._system}] + messages

        # Confirm callback: in the TUI we default-deny for safety; future work
        # can wire a ConfirmModal here.
        def confirm(prompt: str) -> bool:
            return False

        try:
            for event in agent_run(
                self._client,
                full_messages,
                autonomy=self._autonomy,
                confirm=confirm,
                tools=ALL_TOOLS,
            ):
                if isinstance(event, ToolCallEvent):
                    self.app.call_from_thread(self._show_tool_call, event)
                elif isinstance(event, ToolResultEvent):
                    self.app.call_from_thread(self._show_tool_result, event)
                elif isinstance(event, (FinalAnswerEvent, FallbackEvent)):
                    # For fallback we try streaming instead for a better UX.
                    if isinstance(event, FallbackEvent):
                        self.app.call_from_thread(self._start_streaming_reply)
                        parts: list[str] = []
                        try:
                            for chunk in self._client.chat_stream("", "", messages=full_messages):
                                parts.append(chunk)
                                self.app.call_from_thread(self._stream, "".join(parts))
                        except OllamaUnavailable as exc:
                            self.app.call_from_thread(self._show_error, str(exc))
                            return
                        answer = "".join(parts).strip()
                    else:
                        answer = event.text
                    self.app.call_from_thread(self._finish_reply, answer)
                    if answer and not isinstance(event, FallbackEvent):
                        self._messages.append({"role": "assistant", "content": answer})
        except Exception as exc:
            logger.exception("AI agent failed")
            self.app.call_from_thread(self._show_error, str(exc))

    # ------------------------------------------------------------------
    # Thread-safe UI helpers (called via call_from_thread)
    # ------------------------------------------------------------------

    def _show_tool_call(self, event: ToolCallEvent) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        args_str = ", ".join(f"{k}={v!r}" for k, v in event.args.items()) if event.args else ""
        label = f"[dim]⚙ {event.tool_name}({args_str}) [{event.risk}][/dim]"
        self.app.call_later(log.mount, Static(label, classes="msg-tool"))
        log.scroll_end(animate=False)

    def _show_tool_result(self, event: ToolResultEvent) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        prefix = "[dim]✗ skipped[/dim]" if event.skipped else "[dim]✓[/dim]"
        self.app.call_later(log.mount, Static(
            f"{prefix} [dim]{escape(event.result[:120])}[/dim]", classes="msg-tool"
        ))
        log.scroll_end(animate=False)

    def _start_streaming_reply(self) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        self.app.call_later(log.mount, Static("[b green]Sifty[/b green]", classes="msg-label"))
        self._live = Static("[dim]thinking…[/dim]", classes="msg")
        self.app.call_later(log.mount, self._live)
        log.scroll_end(animate=False)

    def _stream(self, text: str) -> None:
        if self._live is None:
            return
        self._live.update(Markdown(text))
        self.query_one("#chat-log", VerticalScroll).scroll_end(animate=False)

    def _finish_reply(self, answer: str) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        if self._live is not None:
            self._live.update(Markdown(answer))
            self._live = None
        else:
            self.app.call_later(log.mount, Static("[b green]Sifty[/b green]", classes="msg-label"))
            self.app.call_later(log.mount, Static(Markdown(answer), classes="msg"))
        log.scroll_end(animate=False)

    def _show_error(self, err: str) -> None:
        log = self.query_one("#chat-log", VerticalScroll)
        self.app.call_later(log.mount, Static(
            f"[yellow](error: {escape(err)})[/yellow]", classes="msg"
        ))
        log.scroll_end(animate=False)
        if self._live is not None:
            self._live.update(f"[yellow](error: {escape(err)})[/yellow]")
            self._live = None

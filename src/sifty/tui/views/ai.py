"""AI screen: a chat panel backed by the local Ollama advisor.

The transcript is a scrollable column of message widgets (not a RichLog), so
the *streaming* reply can be rendered into a message that lives inside the chat
box and updated in place as tokens arrive — instead of spilling into a separate
area outside the box until it completes.

The model answers in Markdown, so replies are rendered through Rich's
:class:`~rich.markdown.Markdown` — headings, bold/italic, code fences and
tables show up formatted instead of as literal ``**asterisks**`` and backticks.
"""

from __future__ import annotations

import logging

from rich.markdown import Markdown
from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from ...ai.advisor import SYSTEM_PROMPT
from ...ai.client import OllamaClient, OllamaUnavailable
from .base import BaseView

logger = logging.getLogger("sifty.tui")

_SYSTEM = SYSTEM_PROMPT


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
        self._live: Static | None = None  # the in-progress Sifty reply widget
        if self.workers_enabled():
            self.check_status()

    @work(thread=True, exclusive=True, group="ai-status")
    def check_status(self) -> None:
        ok = self._client.is_available()
        self.app.call_from_thread(self._set_status, ok)

    def _set_status(self, ok: bool) -> None:
        status = self.query_one("#ai-status", Static)
        if ok:
            status.update(f"[green]●[/green] Ollama connected · model [b]{self._client.model}[/b]")
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
        await log.mount(Static("[b green]Sifty[/b green]", classes="msg-label"))
        self._live = Static("[dim]thinking…[/dim]", classes="msg")
        await log.mount(self._live)
        log.scroll_end(animate=False)
        self.ask(question)

    @work(thread=True, exclusive=True, group="ai-chat")
    def ask(self, question: str) -> None:
        if not self._client.is_available():
            self.app.call_from_thread(self._finish, None, None)
            return
        parts: list[str] = []
        try:
            for chunk in self._client.chat_stream(_SYSTEM, question):
                parts.append(chunk)
                self.app.call_from_thread(self._stream, "".join(parts))
        except OllamaUnavailable as exc:
            self.app.call_from_thread(self._finish, None, str(exc))
            return
        except Exception as exc:  # never let a worker die silently
            logger.exception("AI chat failed")
            self.app.call_from_thread(self._finish, None, str(exc))
            return
        self.app.call_from_thread(self._finish, "".join(parts).strip(), None)

    def _stream(self, text: str) -> None:
        """Render the in-progress answer (as Markdown) while tokens arrive."""
        if self._live is None:
            return
        self._live.update(Markdown(text))
        self.query_one("#chat-log", VerticalScroll).scroll_end(animate=False)

    def _finish(self, answer: str | None, err: str | None) -> None:
        """Replace the in-progress reply with the completed answer or an error."""
        if self._live is None:
            return
        if err is not None:
            self._live.update(f"[yellow](error talking to Ollama: {escape(err)})[/yellow]")
        elif not answer:
            self._live.update("[yellow]AI unavailable — is Ollama running?[/yellow]")
        else:
            self._live.update(Markdown(answer))
        self._live = None
        self.query_one("#chat-log", VerticalScroll).scroll_end(animate=False)

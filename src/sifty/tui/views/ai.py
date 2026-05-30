"""AI screen: a chat panel backed by the local Ollama advisor."""

from __future__ import annotations

import logging

from textual import work
from textual.app import ComposeResult
from textual.widgets import Input, RichLog, Static

from ...ai.client import OllamaClient
from .base import BaseView

logger = logging.getLogger("sifty.tui")

_SYSTEM = "You are a careful Windows maintenance assistant. Be concise and cautious."


class AIView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Ask Sifty", classes="title")
        yield Static("Checking Ollama…", id="ai-status", classes="subtle")
        yield RichLog(id="chat-log", wrap=True, markup=True)
        yield Input(
            placeholder="Ask about cleanup, disk usage, safety…  (Enter to send)",
            id="ask",
        )

    def on_mount(self) -> None:
        self._client = OllamaClient.from_config()
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
        log = self.query_one("#chat-log", RichLog)
        log.write(f"[b cyan]You[/b cyan]  {question}")
        self.query_one("#ask", Input).value = ""
        log.write("[dim]Sifty is thinking…[/dim]")
        self.ask(question)

    @work(thread=True, exclusive=True, group="ai-chat")
    def ask(self, question: str) -> None:
        if not self._client.is_available():
            self.app.call_from_thread(self._reply, None)
            return
        try:
            answer = self._client.chat(_SYSTEM, question)
        except Exception as exc:
            logger.exception("AI chat failed")
            answer = f"(error talking to Ollama: {exc})"
        self.app.call_from_thread(self._reply, answer)

    def _reply(self, answer: str | None) -> None:
        log = self.query_one("#chat-log", RichLog)
        if answer is None:
            log.write("[yellow]AI unavailable — is Ollama running?[/yellow]\n")
        else:
            log.write(f"[b green]Sifty[/b green]  {answer}\n")

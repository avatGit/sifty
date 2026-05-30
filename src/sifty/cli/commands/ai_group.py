"""`sifty ai` — ask the local AI for maintenance advice (Ollama)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.markdown import Markdown

from ...ai.advisor import SYSTEM_PROMPT, summarize_disk
from ...ai.client import OllamaClient
from ...console import console, error, human_size, success, warn
from ...core import disk

app = typer.Typer(help="Ask the local AI for maintenance advice (Ollama).")


@app.command("status")
def status_cmd() -> None:
    """Check whether the local Ollama model is reachable."""
    client = OllamaClient.from_config()
    if client.is_available():
        success(f"Ollama is running at {client.host} (model: {client.model}).")
    else:
        error(f"Ollama not reachable at {client.host}.")
        console.print("[dim]Install from https://ollama.com, then run "
                      f"`ollama pull {client.model}`.[/dim]")


@app.command("ask")
def ask_cmd(
    question: str = typer.Argument(..., help="Your maintenance question."),
    path: Path = typer.Option(None, "--path", "-p", help="Ground the answer in this folder's biggest items."),
) -> None:
    """Ask a question, optionally grounded in a folder's largest items."""
    client = OllamaClient.from_config()
    if not client.is_available():
        error(f"Ollama not reachable at {client.host}. Run `sifty ai status` for help.")
        raise typer.Exit(1)

    if path:
        path = path.expanduser()
        if not path.exists():
            warn(f"Path does not exist: {path}")
            raise typer.Exit(1)
        with console.status(f"Scanning {path}…"):
            items = [
                (entry.name, human_size(size))
                for entry, size in disk.biggest(path, 20)
            ]
        with console.status("Thinking…"):
            answer = summarize_disk(client, items, question)
    else:
        with console.status("Thinking…"):
            answer = client.chat(SYSTEM_PROMPT, question)

    if answer:
        # The model replies in Markdown; render it so headings, code fences
        # and tables show up formatted instead of as literal syntax.
        console.print(Markdown(answer))
    else:
        console.print("[yellow]No answer (AI unavailable).[/yellow]")

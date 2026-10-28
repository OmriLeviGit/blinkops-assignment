"""Terminal rendering: rich tables, panels and colors."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import CustomField, WorkItem

console = Console()
err_console = Console(stderr=True)

STAGE_STYLES = {
    "open": "cyan",
    "in_progress": "yellow",
    "review": "magenta",
    "closed": "green",
}


def stage_badge(stage: str) -> Text:
    return Text(stage.replace("_", " "), style=f"bold {STAGE_STYLES.get(stage, 'white')}")


def _when(value: datetime | None) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M") if value else "-"


def _excerpt(text: str | None, width: int = 50) -> str:
    if not text:
        return ""
    line = " ".join(text.split())
    return line if len(line) <= width else line[: width - 1] + "…"


def ticket_table(items: list[WorkItem], title: str | None = None) -> Table:
    table = Table(title=title, header_style="bold", title_justify="left")
    table.add_column("Ref", style="bold blue", no_wrap=True)
    table.add_column("Stage", no_wrap=True)
    table.add_column("Title", overflow="fold")
    table.add_column("Description", style="dim", overflow="ellipsis")
    table.add_column("Updated", style="dim", no_wrap=True)
    for item in items:
        table.add_row(
            Text(item.ref),
            stage_badge(item.stage),
            Text(item.title),
            Text(_excerpt(item.description)),
            _when(item.updated),
        )
    return table


def ticket_detail(item: WorkItem, labels: dict[str, str] | None = None) -> Panel:
    labels = labels or {}
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold", no_wrap=True)
    grid.add_column()
    grid.add_row("Stage", stage_badge(item.stage))
    grid.add_row(
        "Description",
        Text(item.description) if item.description else Text("No description", style="dim italic"),
    )
    grid.add_row(
        "Depends on",
        Text(", ".join(item.depends_on), style="blue")
        if item.depends_on
        else Text("-", style="dim"),
    )
    for name, value in item.custom_fields.items():
        grid.add_row(Text(labels.get(name, name)), Text(value))
    if item.owner:
        grid.add_row("Owner", Text(item.owner))
    grid.add_row("Created", _when(item.created))
    grid.add_row("Updated", _when(item.updated))
    return Panel(
        grid,
        title=f"[bold blue]{escape(item.ref)}[/] {escape(item.title)}",
        title_align="left",
        expand=False,
    )


def fields_table(fields: list[CustomField]) -> Table:
    table = Table(header_style="bold")
    table.add_column("Name", style="bold")
    table.add_column("Label")
    table.add_column("Type", style="dim")
    table.add_column("ID", style="dim")
    for f in fields:
        table.add_row(Text(f.name), Text(f.label), Text(f.type), Text(f.id))
    return table


def print_json(data: Any) -> None:
    def default(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(type(obj).__name__)

    data = [_jsonable(d) for d in data] if isinstance(data, list) else _jsonable(data)
    print(json.dumps(data, indent=2, default=default))


def _jsonable(obj: Any) -> Any:
    raw = getattr(obj, "raw", None)
    if raw:
        return raw
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: v for k, v in asdict(obj).items() if k != "raw"}
    return obj


def success(message: str) -> None:
    console.print(f"[green]✓[/] {message}")


def info(message: str) -> None:
    err_console.print(f"[dim]{escape(message)}[/]")


def error(message: str, hint: str | None = None) -> None:
    err_console.print(f"[bold red]Error:[/] {escape(message)}")
    if hint:
        err_console.print(f"[dim]{escape(hint)}[/]")

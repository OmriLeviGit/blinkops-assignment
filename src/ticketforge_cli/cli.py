"""`tforge` command line interface."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from typing import Annotated, Any, TypeVar

import typer

from . import views
from .client import TicketForgeClient
from .config import DEFAULT_BASE_URL, Config, config_path, load_config, save_config
from .errors import AuthError, ConfigError, TicketForgeError
from .services import TicketService, parse_field_assignments

app = typer.Typer(
    help="Manage TicketForge tickets from the terminal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
fields_app = typer.Typer(help="Manage custom field definitions.", no_args_is_help=True)
app.add_typer(fields_app, name="fields")

F = TypeVar("F", bound=Callable[..., Any])

JsonOpt = Annotated[bool, typer.Option("--json", help="Print raw JSON instead of tables.")]


def handle_errors(func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except AuthError as exc:
            views.error(exc.message, "Check your credentials with `tforge setup`.")
            raise typer.Exit(2) from None
        except ConfigError as exc:
            views.error(exc.message, "Run `tforge setup` first.")
            raise typer.Exit(2) from None
        except TicketForgeError as exc:
            views.error(exc.message)
            raise typer.Exit(1) from None

    return wrapper  # type: ignore[return-value]


def _on_wait(seconds: float, reason: str) -> None:
    views.info(f"{reason}; waiting {seconds:.1f}s…")


def make_client(cfg: Config, *, auth: bool = True) -> TicketForgeClient:
    if auth:
        return TicketForgeClient(cfg.base_url, cfg.username, cfg.password, on_wait=_on_wait)
    return TicketForgeClient(cfg.base_url, on_wait=_on_wait)


def get_service() -> TicketService:
    cfg = load_config()
    if not cfg.is_complete:
        raise ConfigError("TicketForge is not configured")
    return TicketService(make_client(cfg))


# ------------------------------------------------------------------ setup


@app.command()
@handle_errors
def setup(
    username: Annotated[str | None, typer.Option("--username", "-u")] = None,
    password: Annotated[str | None, typer.Option("--password", "-p", help="Prompted if omitted.")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="TicketForge app URL.")] = None,
) -> None:
    """Configure and verify the connection to TicketForge."""
    current = load_config()
    base_url = base_url or typer.prompt("TicketForge URL", default=current.base_url or DEFAULT_BASE_URL)
    username = username or typer.prompt("Username", default=current.username or None)
    password = password or typer.prompt("Password", hide_input=True)

    cfg = Config(base_url=base_url.rstrip("/"), username=username, password=password)
    with make_client(cfg) as client:
        client.verify_credentials()
    path = save_config(cfg)
    views.success(f"Connected as [bold]{username}[/]. Config saved to {path}")


@app.command()
@handle_errors
def register(
    username: Annotated[str | None, typer.Option("--username", "-u")] = None,
    password: Annotated[str | None, typer.Option("--password", "-p")] = None,
    base_url: Annotated[str | None, typer.Option("--base-url")] = None,
    save: Annotated[bool, typer.Option(help="Save the new credentials as the active config.")] = True,
) -> None:
    """Create a new TicketForge account."""
    base_url = (base_url or load_config().base_url).rstrip("/")
    username = username or typer.prompt("Username")
    password = password or typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    with make_client(Config(base_url=base_url), auth=False) as client:
        client.register(username, password)
    views.success(f"Account [bold]{username}[/] created")
    if save:
        path = save_config(Config(base_url=base_url, username=username, password=password))
        views.success(f"Config saved to {path}")


@app.command()
@handle_errors
def status() -> None:
    """Show the active configuration and check the connection."""
    cfg = load_config()
    views.console.print(f"Config file: {config_path()}")
    views.console.print(f"URL:         {cfg.base_url}")
    views.console.print(f"Username:    {cfg.username or '[dim]not set[/]'}")
    if not cfg.is_complete:
        raise ConfigError("TicketForge is not configured")
    with make_client(cfg) as client:
        client.verify_credentials()
        rate = (
            f"{client.rate_remaining}/{client.rate_limit} requests left in this window"
            if client.rate_remaining is not None
            else "unknown"
        )
    views.success("Credentials OK")
    views.console.print(f"Rate limit:  {rate}")


# ------------------------------------------------------------------ tickets


@app.command("list")
@handle_errors
def list_tickets(
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, help="Tickets per page.")] = 10,
    all_: Annotated[bool, typer.Option("--all", "-a", help="Fetch every ticket.")] = False,
    stage: Annotated[str | None, typer.Option("--stage", "-s", help="Filter by stage.")] = None,
    cursor: Annotated[str | None, typer.Option(help="Resume from a cursor printed by a previous run.")] = None,
    no_pager: Annotated[bool, typer.Option("--no-pager", help="Don't prompt for more pages.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """List your tickets, newest first."""
    svc = get_service()
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not (as_json or all_ or no_pager)
    page_no = 1
    while True:
        result = svc.list_tickets(limit=None if all_ else limit, stage=stage, cursor=cursor)
        if as_json:
            views.print_json(
                {
                    "workitems": [w.raw for w in result.items],
                    "pagination": {"hasMore": result.has_more, "nextCursor": result.next_cursor},
                }
            )
            return
        if not result.items and page_no == 1:
            views.console.print("No tickets found.")
            return
        views.console.print(views.ticket_table(result.items, title=f"Page {page_no}" if interactive else None))
        if not result.has_more:
            return
        if not interactive:
            views.info(f"More tickets available. Next page: tforge list --cursor '{result.next_cursor}'")
            return
        if not typer.confirm("Show more?", default=True):
            return
        cursor, page_no = result.next_cursor, page_no + 1


@app.command()
@handle_errors
def show(ref: Annotated[str, typer.Argument(help="Ticket ref, e.g. TF-12 or 12.")], as_json: JsonOpt = False) -> None:
    """Show a single ticket in full."""
    svc = get_service()
    ticket = svc.get_ticket(ref)
    if as_json:
        views.print_json(ticket)
        return
    labels = {f.name: f.label for f in svc.list_fields()} if ticket.custom_fields else {}
    views.console.print(views.ticket_detail(ticket, labels))


@app.command()
@handle_errors
def create(
    title: Annotated[str | None, typer.Argument(help="Ticket title (prompted if omitted).")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d")] = None,
    stage: Annotated[str | None, typer.Option("--stage", "-s", help="Initial stage (default: open).")] = None,
    depends_on: Annotated[list[str] | None, typer.Option("--depends-on", "--dep", help="Repeatable.")] = None,
    field: Annotated[list[str] | None, typer.Option("--field", "-f", help="Custom field name=value. Repeatable.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Create a ticket."""
    svc = get_service()
    title = title or typer.prompt("Title")
    ticket = svc.create_ticket(
        title,
        description=description,
        depends_on=depends_on or [],
        fields=parse_field_assignments(field or []),
    )
    if stage and stage.strip().lower() != "open":
        # The create endpoint has no stage; new tickets always start as "open".
        ticket = svc.update_ticket(ticket.ref, stage=stage)
    if as_json:
        views.print_json(ticket)
        return
    views.success(f"Created [bold blue]{ticket.ref}[/]")
    labels = {f.name: f.label for f in svc.list_fields()} if ticket.custom_fields else {}
    views.console.print(views.ticket_detail(ticket, labels))


@app.command()
@handle_errors
def update(
    ref: Annotated[str, typer.Argument(help="Ticket ref, e.g. TF-12 or 12.")],
    title: Annotated[str | None, typer.Option("--title", "-t")] = None,
    description: Annotated[str | None, typer.Option("--description", "-d", help="Pass '' to clear.")] = None,
    stage: Annotated[str | None, typer.Option("--stage", "-s", help="open | in_progress | review | closed")] = None,
    depends_on: Annotated[list[str] | None, typer.Option("--depends-on", help="Replace all dependencies. Repeatable.")] = None,
    add_dep: Annotated[list[str] | None, typer.Option("--add-dep", help="Add a dependency. Repeatable.")] = None,
    remove_dep: Annotated[list[str] | None, typer.Option("--remove-dep", help="Remove a dependency. Repeatable.")] = None,
    clear_deps: Annotated[bool, typer.Option("--clear-deps", help="Remove all dependencies.")] = False,
    field: Annotated[list[str] | None, typer.Option("--field", "-f", help="name=value to set, name= to unset. Repeatable.")] = None,
    as_json: JsonOpt = False,
) -> None:
    """Update a ticket. Only the options you pass are changed."""
    svc = get_service()
    ticket = svc.update_ticket(
        ref,
        title=title,
        description=description,
        stage=stage,
        depends_on=[] if clear_deps else depends_on,
        add_deps=add_dep or [],
        remove_deps=remove_dep or [],
        fields=parse_field_assignments(field) if field else None,
    )
    if as_json:
        views.print_json(ticket)
        return
    views.success(f"Updated [bold blue]{ticket.ref}[/]")
    labels = {f.name: f.label for f in svc.list_fields()} if ticket.custom_fields else {}
    views.console.print(views.ticket_detail(ticket, labels))


@app.command()
@handle_errors
def delete(
    ref: Annotated[str, typer.Argument(help="Ticket ref, e.g. TF-12 or 12.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a ticket. Other tickets' dependencies on it are removed too."""
    svc = get_service()
    ticket = svc.get_ticket(ref)
    if not yes:
        typer.confirm(f"Delete {ticket.ref} \"{ticket.title}\"?", abort=True)
    svc.delete_ticket(ticket.ref)
    views.success(f"Deleted {ticket.ref}")


# ------------------------------------------------------------ custom fields


@fields_app.command("list")
@handle_errors
def fields_list(as_json: JsonOpt = False) -> None:
    """List custom field definitions."""
    fields = get_service().list_fields()
    if as_json:
        views.print_json(fields)
    elif not fields:
        views.console.print("No custom fields defined. Add one with `tforge fields add NAME`.")
    else:
        views.console.print(views.fields_table(fields))


@fields_app.command("add")
@handle_errors
def fields_add(
    name: Annotated[str, typer.Argument(help="Letters, digits and underscores.")],
    label: Annotated[str | None, typer.Option("--label", "-l", help="Display label (defaults from name).")] = None,
) -> None:
    """Define a new custom field."""
    created = get_service().add_field(name, label)
    views.success(f"Added field [bold]{created.name}[/] ({created.label})")


@fields_app.command("relabel")
@handle_errors
def fields_relabel(
    name: Annotated[str, typer.Argument(help="Field name or id.")],
    label: Annotated[str, typer.Argument(help="New display label.")],
) -> None:
    """Change a custom field's display label (the API does not allow renaming)."""
    updated = get_service().relabel_field(name, label)
    views.success(f"Field [bold]{updated.name}[/] is now labelled \"{updated.label}\"")


@fields_app.command("delete")
@handle_errors
def fields_delete(
    name: Annotated[str, typer.Argument(help="Field name or id.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a custom field. Its values are removed from all tickets."""
    if not yes:
        typer.confirm(f"Delete field '{name}' and its values on all tickets?", abort=True)
    removed = get_service().delete_field(name)
    views.success(f"Deleted field {removed.name}")


if __name__ == "__main__":
    app()

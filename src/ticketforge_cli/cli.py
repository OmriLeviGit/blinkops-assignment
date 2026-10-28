"""`tforge` command line interface."""

from __future__ import annotations

import functools
import shlex
import sys
from collections.abc import Callable
from typing import Annotated, Any, TypeVar

import typer

from . import __version__, views
from .client import TicketForgeClient
from .config import DEFAULT_BASE_URL, Config, config_path, load_config, save_config
from .errors import AuthError, ConfigError, TicketForgeError, ValidationError
from .services import TicketPager, TicketService, normalize_stage, parse_field_assignments

app = typer.Typer(
    help="Manage TicketForge tickets from the terminal.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
fields_app = typer.Typer(help="Manage custom field definitions.", no_args_is_help=True)
app.add_typer(fields_app, name="fields")

F = TypeVar("F", bound=Callable[..., Any])

SETUP_HINT = (
    "Run `tforge setup`, or set TFORGE_USERNAME and TFORGE_PASSWORD in a .env file"
    " (see .env.example)."
)

JsonOpt = Annotated[bool, typer.Option("--json", help="Print raw JSON instead of tables.")]


def examples(*lines: str) -> str:
    """Build an --help epilog. `#` starts a dimmed comment."""
    rendered = []
    for line in lines:
        cmd, _, note = line.partition("#")
        rendered.append(f"{cmd.rstrip()}  [dim]# {note.strip()}[/]" if note else cmd.rstrip())
    return "[bold]Examples[/]\n\n" + "\n".join(rendered)


def _print_version(value: bool) -> None:
    if value:
        print(f"tforge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=_print_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    """Manage TicketForge tickets from the terminal."""


def handle_errors(func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except AuthError as exc:
            views.error(exc.message, "Check your credentials with `tforge setup`.")
            raise typer.Exit(2) from None
        except ConfigError as exc:
            views.error(exc.message, SETUP_HINT)
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


@app.command(
    epilog=examples(
        "tforge setup  # prompts for URL, username and password",
        "tforge setup -u alice -p 's3cret'",
        "TFORGE_USERNAME=alice TFORGE_PASSWORD=s3cret tforge status  # env vars, no config file",
    )
)
@handle_errors
def setup(
    username: Annotated[
        str | None, typer.Option("--username", "-u", help="Prompted if omitted.")
    ] = None,
    password: Annotated[
        str | None, typer.Option("--password", "-p", help="Prompted (hidden) if omitted.")
    ] = None,
    base_url: Annotated[str | None, typer.Option("--base-url", help="TicketForge app URL.")] = None,
) -> None:
    """Configure and verify the connection to TicketForge."""
    current = load_config()
    base_url = base_url or typer.prompt(
        "TicketForge URL", default=current.base_url or DEFAULT_BASE_URL
    )
    username = username or typer.prompt("Username", default=current.username or None)
    password = password or typer.prompt("Password", hide_input=True)

    cfg = Config(base_url=base_url.rstrip("/"), username=username, password=password)
    with make_client(cfg) as client:
        client.verify_credentials()
    path = save_config(cfg)
    views.success(f"Connected as [bold]{username}[/]. Config saved to {path}")


@app.command(
    epilog=examples(
        "tforge register  # prompts, then saves the new credentials",
        "tforge register -u alice --no-save",
    )
)
@handle_errors
def register(
    username: Annotated[
        str | None, typer.Option("--username", "-u", help="Prompted if omitted.")
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", "-p", help="Prompted (hidden, confirmed) if omitted."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="TicketForge app URL (default: configured URL)."),
    ] = None,
    save: Annotated[
        bool, typer.Option(help="Save the new credentials as the active config.")
    ] = True,
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


def _source(cfg: Config, attr: str) -> str:
    source = cfg.sources.get(attr)
    return f" [dim](from {source})[/]" if source else ""


@app.command(
    epilog=examples(
        "tforge status",
        "cp .env.example .env && tforge status  # credentials from ./.env",
    )
)
@handle_errors
def status() -> None:
    """Show the active configuration and check the connection."""
    cfg = load_config()
    views.console.print(f"Config file: {config_path()}")
    views.console.print(f"URL:         {cfg.base_url}{_source(cfg, 'base_url')}")
    views.console.print(
        f"Username:    {cfg.username or '[dim]not set[/]'}{_source(cfg, 'username')}"
    )
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


@app.command(
    "list",
    epilog=examples(
        "tforge list  # page 1, 10 per page",
        "tforge list -p 2 -n 5  # page 2, 5 per page",
        "tforge list -a  # every ticket",
        "tforge list -s in_progress  # filter by stage",
        "tforge list -i  # browse with n/p/q",
        "tforge list --json",
    ),
)
@handle_errors
def list_tickets(
    page: Annotated[int, typer.Option("--page", "-p", min=1, help="Page number.")] = 1,
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, help="Tickets per page.")] = 10,
    all_: Annotated[
        bool, typer.Option("--all", "-a", help="Show every ticket, no paging.")
    ] = False,
    interactive: Annotated[
        bool, typer.Option("--interactive", "-i", help="Browse pages with n/p/q.")
    ] = False,
    stage: Annotated[
        str | None,
        typer.Option(
            "--stage", "-s", help="Filter by stage: open | in_progress | review | closed."
        ),
    ] = None,
    as_json: JsonOpt = False,
) -> None:
    """List your tickets, newest first."""
    if interactive and (all_ or as_json):
        raise typer.BadParameter("--interactive can't be combined with --all or --json")
    svc = get_service()

    if interactive:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise ValidationError("--interactive needs a terminal")
        browse(svc.pager(stage), limit, page)
        return

    result = svc.list_tickets(page=page, limit=None if all_ else limit, stage=stage)
    if as_json:
        pagination = {
            "page": None if all_ else page,
            "limit": None if all_ else limit,
            "hasMore": result.has_more,
        }
        views.print_json({"workitems": [w.raw for w in result.items], "pagination": pagination})
        return
    if not result.items:
        views.console.print(
            "No tickets found." if page == 1 or all_ else f"No tickets on page {page}."
        )
        return

    views.console.print(views.ticket_table(result.items))
    if all_:
        views.info(f"{len(result.items)} tickets")
        return
    start = (page - 1) * limit + 1
    end = start + len(result.items) - 1
    footer = f"Page {page} · " + (f"ticket {start}" if start == end else f"tickets {start}–{end}")
    if result.has_more:
        args = [f"--page {page + 1}"]
        if limit != 10:
            args.append(f"--limit {limit}")
        if stage:
            args.append(f"--stage {shlex.quote(stage)}")
        footer += f" · next: tforge list {' '.join(args)}"
    views.info(footer)


QUIT_KEYS = {"q", "\x1b", "\x03"}
NEXT_KEYS = {"n", " ", "\r", "\n", "\x1b[C", "\x1b[B"}
PREV_KEYS = {"p", "\x1b[D", "\x1b[A"}


def browse(
    pager: TicketPager,
    limit: int,
    page: int = 1,
    read_key: Callable[[], str] = typer.getchar,
) -> None:
    """Page through tickets with single keypresses, fetching only when moving onto new pages."""
    while True:
        if pager.is_cached(page, limit):
            result = pager.page(page, limit)
        else:
            with views.console.status("Loading…"):
                result = pager.page(page, limit)
        if not result.items:
            if page == 1:
                views.console.print("No tickets found.")
                return
            page = pager.total_pages(limit) or 1  # --page past the end
            continue

        views.console.clear()
        views.console.print(views.ticket_table(result.items))
        total = pager.total_pages(limit)
        position = (
            f"Page {page}/{total} · {len(pager.loaded)} tickets"
            if total
            else f"Page {page} · {len(pager.loaded)} loaded"
        )
        actions = []
        if result.has_more:
            actions.append("[bold]\\[n][/]ext")
        if page > 1:
            actions.append("[bold]\\[p][/]rev")
        actions.append("[bold]\\[q][/]uit")
        views.console.print(f"{position} · {'  '.join(actions)} > ", end="")

        try:
            key = read_key()
        except (KeyboardInterrupt, typer.Abort):
            key = "q"
        if len(key) == 1:
            key = key.lower()  # arrow keys arrive as case-sensitive escape sequences
        if key in QUIT_KEYS:
            views.console.print()
            return
        if key in NEXT_KEYS and result.has_more:
            page += 1
        elif key in PREV_KEYS and page > 1:
            page -= 1


@app.command(
    epilog=examples("tforge show TF-12", "tforge show 12 --json  # bare numbers mean TF-<n>")
)
@handle_errors
def show(
    ref: Annotated[str, typer.Argument(help="Ticket ref, e.g. TF-12 or 12.")],
    as_json: JsonOpt = False,
) -> None:
    """Show a single ticket in full."""
    svc = get_service()
    ticket = svc.get_ticket(ref)
    if as_json:
        views.print_json(ticket)
        return
    labels = {f.name: f.label for f in svc.list_fields()} if ticket.custom_fields else {}
    views.console.print(views.ticket_detail(ticket, labels))


@app.command(
    epilog=examples(
        'tforge create "Fix login redirect"',
        'tforge create "Write release notes" -d "Cover the new CLI" -s in_progress',
        'tforge create "Ship v2" --dep TF-12 --dep TF-13 -f priority=high',
    )
)
@handle_errors
def create(
    title: Annotated[str | None, typer.Argument(help="Ticket title (prompted if omitted).")] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="Ticket description.")
    ] = None,
    stage: Annotated[
        str | None, typer.Option("--stage", "-s", help="Initial stage (default: open).")
    ] = None,
    depends_on: Annotated[
        list[str] | None,
        typer.Option("--depends-on", "--dep", help="Ref this ticket depends on. Repeatable."),
    ] = None,
    field: Annotated[
        list[str] | None, typer.Option("--field", "-f", help="Custom field name=value. Repeatable.")
    ] = None,
    as_json: JsonOpt = False,
) -> None:
    """Create a ticket."""
    # Validate up front: the stage is applied by a second request, after the ticket exists.
    stage = normalize_stage(stage) if stage else None
    svc = get_service()
    title = title or typer.prompt("Title")
    ticket = svc.create_ticket(
        title,
        description=description,
        depends_on=depends_on or [],
        fields=parse_field_assignments(field or []),
    )
    if stage and stage != "open":
        # The create endpoint has no stage; new tickets always start as "open".
        ticket = svc.update_ticket(ticket.ref, stage=stage)
    if as_json:
        views.print_json(ticket)
        return
    views.success(f"Created [bold blue]{ticket.ref}[/]")
    labels = {f.name: f.label for f in svc.list_fields()} if ticket.custom_fields else {}
    views.console.print(views.ticket_detail(ticket, labels))


@app.command(
    epilog=examples(
        "tforge update TF-12 -s review",
        "tforge update TF-12 -t 'New title' -d ''  # '' clears the description",
        "tforge update TF-12 --add-dep TF-3 --remove-dep TF-4",
        "tforge update TF-12 --clear-deps",
        "tforge update TF-12 -f priority=low -f team=  # set one field, unset another",
    )
)
@handle_errors
def update(
    ref: Annotated[str, typer.Argument(help="Ticket ref, e.g. TF-12 or 12.")],
    title: Annotated[str | None, typer.Option("--title", "-t", help="New title.")] = None,
    description: Annotated[
        str | None, typer.Option("--description", "-d", help="Pass '' to clear.")
    ] = None,
    stage: Annotated[
        str | None, typer.Option("--stage", "-s", help="open | in_progress | review | closed")
    ] = None,
    depends_on: Annotated[
        list[str] | None, typer.Option("--depends-on", help="Replace all dependencies. Repeatable.")
    ] = None,
    add_dep: Annotated[
        list[str] | None, typer.Option("--add-dep", help="Add a dependency. Repeatable.")
    ] = None,
    remove_dep: Annotated[
        list[str] | None, typer.Option("--remove-dep", help="Remove a dependency. Repeatable.")
    ] = None,
    clear_deps: Annotated[
        bool, typer.Option("--clear-deps", help="Remove all dependencies.")
    ] = False,
    field: Annotated[
        list[str] | None,
        typer.Option("--field", "-f", help="name=value to set, name= to unset. Repeatable."),
    ] = None,
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


@app.command(epilog=examples("tforge delete TF-12", "tforge delete TF-12 -y  # no confirmation"))
@handle_errors
def delete(
    ref: Annotated[str, typer.Argument(help="Ticket ref, e.g. TF-12 or 12.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation.")] = False,
) -> None:
    """Delete a ticket. Other tickets' dependencies on it are removed too."""
    svc = get_service()
    ticket = svc.get_ticket(ref)
    if not yes:
        typer.confirm(f'Delete {ticket.ref} "{ticket.title}"?', abort=True)
    svc.delete_ticket(ticket.ref)
    views.success(f"Deleted {ticket.ref}")


# ------------------------------------------------------------ custom fields


@fields_app.command("list", epilog=examples("tforge fields list", "tforge fields list --json"))
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


@fields_app.command(
    "add",
    epilog=examples(
        "tforge fields add priority  # label defaults to 'Priority'",
        'tforge fields add due_date -l "Due date"',
    ),
)
@handle_errors
def fields_add(
    name: Annotated[str, typer.Argument(help="Letters, digits and underscores.")],
    label: Annotated[
        str | None, typer.Option("--label", "-l", help="Display label (defaults from name).")
    ] = None,
) -> None:
    """Define a new custom field."""
    created = get_service().add_field(name, label)
    views.success(f"Added field [bold]{created.name}[/] ({created.label})")


@fields_app.command("relabel", epilog=examples("tforge fields relabel priority Urgency"))
@handle_errors
def fields_relabel(
    name: Annotated[str, typer.Argument(help="Field name or id.")],
    label: Annotated[str, typer.Argument(help="New display label.")],
) -> None:
    """Change a custom field's display label (the API does not allow renaming)."""
    updated = get_service().relabel_field(name, label)
    views.success(f'Field [bold]{updated.name}[/] is now labelled "{updated.label}"')


@fields_app.command(
    "delete",
    epilog=examples(
        "tforge fields delete priority", "tforge fields delete priority -y  # no confirmation"
    ),
)
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

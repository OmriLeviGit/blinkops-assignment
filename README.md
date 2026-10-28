# tforge — TicketForge CLI

A command line client for [TicketForge](https://integrations-assignment-ticketforge.vercel.app),
a lightweight ticketing tool with no public API. The API was reverse-engineered
from the web app; the findings are documented in [docs/API.md](docs/API.md).

```
$ tforge list -n 3
┏━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage  ┃ Title             ┃ Description          ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-594 │ closed │ Smoke test ticket │ created from the CLI │ 2026-10-28 14:14 │
│ TF-593 │ open   │ test1             │ test2                │ 2026-10-28 14:08 │
│ TF-592 │ open   │ Ticket 5          │                      │ 2026-10-28 14:06 │
└────────┴────────┴───────────────────┴──────────────────────┴──────────────────┘
Page 1 · tickets 1–3 · next: tforge list --page 2 --limit 3
```

## Features

- **Setup** step that verifies credentials before saving them
- **Create, list, update** tickets, plus **show** and **delete**
- **Safe partial updates**: only the options you pass are changed (the raw API
  silently wipes fields you leave out of an update)
- **Pagination**: `--page`/`--limit`, `--all`, or an interactive browser (`-i`) with next/prev keys
- **Stage filter** (`--stage`), dependencies (`--add-dep`, `--remove-dep`, ...) and
  **custom fields** (`--field priority=high`, `tforge fields ...`)
- **Rate-limit handling**: waits for the window to reset when the quota is used
  up, and retries with backoff on 429 and transient errors
- Colored tables, a `--json` flag on every read/write command for scripting, and
  meaningful exit codes
- 59 tests with mocked HTTP

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/OmriLeviGit/blinkops-assignment.git
cd blinkops-assignment
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # or: pip install -e '.[dev]' to run the tests
tforge --help
```

### Tested on

- Windows 11 Pro (build 26300) with WSL2 2.5.9, Ubuntu 24.04.2 LTS, kernel 6.6.87.2
- Python 3.12.3 in a venv, bash
- Starting from a fresh `git clone` and following the steps above: 54/54 tests passed, and every
  command in this README was run against the live API (2026-10-28). The recorded output and
  screenshots are in [docs/evidence/](docs/evidence/README.md).

It's plain Python with no native dependencies, so it should also work on Linux and macOS
(not tested). The interactive browser (`list -i`) needs a real terminal (TTY). In the WSL2
terminal, single-key navigation works without pressing Enter.

## Setup

Use an existing TicketForge account, or create one with `tforge register`.

```bash
tforge setup
# TicketForge URL [https://integrations-assignment-ticketforge.vercel.app]:
# Username: alice
# Password:
# ✓ Connected as alice. Config saved to ~/.config/ticketforge/config.json
```

`setup` checks the credentials against the API before saving them. You can also
pass everything non-interactively:

```bash
tforge setup -u alice -p 's3cret' --base-url https://integrations-assignment-ticketforge.vercel.app
```

Configuration is resolved in this order: **environment variables → config file → defaults**.

| Variable | Purpose |
|---|---|
| `TFORGE_USERNAME`, `TFORGE_PASSWORD` | Credentials (handy for CI; no config file needed) |
| `TFORGE_BASE_URL` | TicketForge app URL |
| `TFORGE_CONFIG` | Alternative config file path |

`tforge status` shows the active config, checks the credentials, and reports the remaining rate-limit quota.

## Usage

### Create

```bash
tforge create "Fix login redirect"
tforge create "Write release notes" -d "Cover the new CLI" --stage in_progress
tforge create "Ship v2" --dep TF-12 --dep TF-13 --field priority=high
```

If you leave out the title, you'll be prompted for it.

### List

```bash
tforge list                        # page 1, 10 tickets per page
tforge list --page 2 --limit 5     # any page, any page size
tforge list --all                  # every ticket, no paging
tforge list --stage in_progress    # filter by stage (paging applies to the filtered list)
tforge list --json                 # machine-readable
```

The footer shows where you are and the command for the next page:

```
Page 2 · tickets 6–10 · next: tforge list --page 3 --limit 5
```

#### Interactive browsing

```bash
tforge list --interactive          # or -i; combine with --limit and --stage
```

```
Page 1 · 10 loaded · [n]ext  [q]uit >
Page 2 · 25 loaded · [n]ext  [p]rev  [q]uit >
Page 3/3 · 27 tickets · [p]rev  [q]uit >
```

Single keypresses: `n`/space/→ for next, `p`/← for previous, `q`/Esc to quit.

Tickets are **loaded lazily**: the browser fetches from the API only when you
move onto a page it hasn't seen, and keeps everything loaded so going back is
instant and free. The API has no count endpoint, so the page total (`3/3`)
appears once the end of the list is reached. Opening the browser costs one or
two requests no matter how many tickets you have.

### Show

```bash
tforge show TF-12
tforge show 12          # bare numbers are treated as TF-<n>
```

### Update

Only the options you pass are changed:

```bash
tforge update TF-12 --stage review
tforge update TF-12 --title "New title" -d "New description"
tforge update TF-12 -d ''                     # clear the description
tforge update TF-12 --add-dep TF-3 --remove-dep TF-4
tforge update TF-12 --depends-on TF-5         # replace all dependencies
tforge update TF-12 --clear-deps
tforge update TF-12 -f priority=low -f team=  # set one field, unset another
```

Stages: `open`, `in_progress`, `review`, `closed` (`in-progress` and `"In Progress"` work too).

### Delete

```bash
tforge delete TF-12        # asks for confirmation
tforge delete TF-12 --yes
```

### Custom fields

Custom fields are per-user, text-valued attributes such as priority or team.

```bash
tforge fields list
tforge fields add priority --label Priority
tforge fields relabel priority "Urgency"
tforge fields delete priority          # asks first (--yes to skip); also removes its values from all tickets
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | API or validation error (e.g. ticket not found, invalid stage) |
| 2 | Not configured / bad credentials |

## Project layout

```
src/ticketforge_cli/
├── cli.py        # Typer commands (thin: parse args, call services, render)
├── views.py      # rich tables/panels, colors, JSON output
├── services.py   # ticket logic: merge-before-update, filtering, field validation
├── client.py     # HTTP: auth, retries, rate limits, error mapping, cursor walking
├── models.py     # lenient dataclasses (tolerate missing/extra fields)
├── errors.py     # exception hierarchy, mapped from the API's `err` codes
└── config.py     # config file + env overrides
docs/API.md       # reverse-engineered API reference
docs/demo.md      # recorded run against the live API
docs/evidence/    # fresh-clone walkthrough: outputs + screenshots
tests/            # pytest + respx (mocked HTTP)
```

## Running the tests

```bash
pip install -e '.[dev]'
pytest
```

The tests cover error mapping, retries and 429/`Retry-After` handling, waiting
for the quota to reset, page-number paging over the cursor API, merge-before-update, client-side
filtering, config precedence, and the main CLI flows.

## Design notes

- **Updates are GET → merge → PUT.** TicketForge's `PUT` is a full replace with
  inconsistent rules: an omitted `description` or `customFields` is wiped, while an
  omitted `dependsOn` is kept. The service layer always fetches the ticket and
  sends a complete body, so `tforge update TF-1 --stage review` never loses data.
- **Errors are mapped by the `err` code, not the HTTP status**, because the API
  returns 400 for not-found, forbidden and validation errors alike.
- **Retries are method-aware.** A 429 is retried for any method, since the request
  was rejected before it was processed. Other transient errors are retried only
  for idempotent methods, so a flaky `create` can't produce duplicate tickets.
- **Rate limits.** The client tracks `x-ratelimit-remaining`/`x-ratelimit-reset`
  and sleeps until the reset when the quota hits 0. On a 429 it honors `Retry-After`,
  then falls back to the reset header, then to exponential backoff with jitter (at
  most 3 retries, with any single wait capped at 60s).
- **Custom fields are validated locally** before sending, so a typo produces a
  helpful message listing the available fields.

## Assumptions and limitations

- **Credentials are stored in plaintext** in `~/.config/ticketforge/config.json`
  (file mode `0600`). The API only supports Basic auth, so there is no token to store
  instead. Use the environment variables if you'd rather not write a file.
- **The API only supports cursor paging, at most 5 tickets per request.**
  There is no offset or page parameter (`page`, `offset` and `skip` are ignored),
  and cursors must point at a real ticket, so `--page N` walks the cursor from
  the start: page N of size L costs about `N×L/5` requests against the 50/min
  rate limit. That's fine for personal ticket lists, but would need server
  support to scale to very large ones. The interactive browser avoids paying
  this up front by loading pages only as you move forward.
- **Stage filtering is client-side**, since the server ignores filter parameters.
  The filter is applied before paging, which means scanning tickets until enough
  matches are found.
- **The list endpoint omits dependencies and custom fields**, so they appear
  in `show` but not in the `list` table. Fetching each ticket would cost one request per row.
- **A 429 was never observed live.** The rate limiter appears to be per serverless
  instance (see [docs/API.md](docs/API.md#rate-limiting)), so 429 handling is built
  on the headers the API sends and on standard conventions, and verified with mocked tests.
- **Ticket refs can be reused** after a delete (the server assigns `max + 1`).
- **No comments, assignees or search**: these endpoints don't exist in the API.
- `create --stage` makes two requests (create, then update), because the create
  endpoint always starts tickets as `open`.
- Custom fields can be relabelled but not renamed, because the API ignores name changes.

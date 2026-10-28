# tforge — TicketForge CLI

A command line client for [TicketForge](https://integrations-assignment-ticketforge.vercel.app),
built for the Blink Ops Integration Developer take-home. TicketForge has no public API, so it
was reverse-engineered from the web app.

## For the reviewer

This part is for whoever is reviewing the assignment. The [user guide](#user-guide) is below the line.

### AI disclosure

I used an AI coding assistant (Claude Code) throughout: for reverse-engineering the API and for
development, testing and documentation. I directed the work (architecture, UX decisions, scope),
reviewed the output, and verified the results against the live API. Details in
[AI_DISCLOSURE.md](AI_DISCLOSURE.md).

### Documentation and evidence

| | |
|---|---|
| [docs/API.md](docs/API.md) | The reverse-engineered API: how it was discovered, endpoints, payloads, errors, rate limits, quirks |
| [docs/CLI.md](docs/CLI.md) | Every command and flag with examples, generated from the code |
| [docs/demo.md](docs/demo.md) | **Evidence 1:** a scripted run against the live API on a freshly registered account, covering every command and the error cases. The output is captured verbatim and reproducible |
| [docs/evidence/](docs/evidence/README.md) | **Evidence 2:** a manual walkthrough from a fresh `git clone`, following this README exactly. Each step has a text transcript and a colored screenshot, plus the findings (one bug, since fixed) |

The test suite (`pytest`, mocked HTTP, 95% coverage floor) covers the client, the services and every command.

### Requirements

| Requirement | Where |
|---|---|
| Setup step | `tforge setup`, which verifies the credentials before saving them |
| Create, list, update | `tforge create`, `list`, `update` |
| README, evidence | This file; [docs/demo.md](docs/demo.md), [docs/evidence/](docs/evidence/README.md) |
| Bonus | Pagination (`--page`/`--limit`, `--all`, interactive `-i`), rate-limit handling, extra commands (`show`, `delete`, `fields`, `register`, `status`), colored output, tests |

### Key decisions

- **Reverse engineering:** the endpoints came from the web app's JavaScript bundles. Two response
  headers then exposed more: `x-matched-path` shows which routes exist, and `OPTIONS` lists the
  methods each one accepts. That revealed a `DELETE` endpoint the UI never uses. Every behavior
  was confirmed live.
- **Stack:** Python with Typer (commands and generated `--help`/docs), httpx (HTTP, easy to mock)
  and rich (tables, colors, the pager). The layers are `cli` → `services` → `client`, so the
  API's quirks are handled below the commands.
- **Safe updates:** the API's `PUT` replaces the whole ticket and wipes fields you leave out.
  The CLI fetches the ticket, merges your changes, and sends it all back.
- **Errors:** the API returns 400 for almost everything, so errors are mapped by its `err` code.
  Inputs that can be checked locally are validated before anything is sent.
- **Rate limits:** the client waits when the quota runs out. It retries 429s (using
  `Retry-After`, then the reset header, then backoff), but retries other failures only for
  requests that are safe to repeat, so `create` never makes duplicates.
- **Pagination:** the API gives 5 tickets per request with no offset. Page numbers are built
  on its cursor, and the interactive browser loads lazily and caches what it has seen.

---

## User guide

- [Installation](#installation)
- [Setup](#setup)
- [Usage](#usage): [commands](#commands) · [list](#list) · [create and update](#create-and-update) · [other commands](#other-commands) · [exit codes](#exit-codes)
- [Development](#development)
- [Assumptions and limitations](#assumptions-and-limitations)

```
$ tforge list -n 3
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                   ┃ Description               ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-611 │ open        │ Release v1.0            │ Blocked on CI and         │ 2026-10-28 14:24 │
│        │             │                         │ security work             │                  │
│ TF-610 │ in progress │ Add login rate limiting │                           │ 2026-10-28 14:24 │
│ TF-609 │ review      │ Set up CI pipeline      │ GitHub Actions running    │ 2026-10-28 14:24 │
│        │             │                         │ lint and tests            │                  │
└────────┴─────────────┴─────────────────────────┴───────────────────────────┴──────────────────┘
Page 1 · tickets 1–3 · next: tforge list --page 2 --limit 3
```

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/OmriLeviGit/blinkops-assignment.git
cd blinkops-assignment
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # or '.[dev]' to run the tests
```

Tested on Ubuntu 24.04 under WSL2 (Windows 11) with Python 3.12, starting from a fresh clone. It
has no native dependencies, so Linux and macOS should work too (not tested).

## Setup

```bash
tforge setup                 # prompts for URL, username and password, verifies them, saves the config
tforge register              # or create a new account first
tforge status                # show the config, check the credentials, show the rate-limit quota
```

The config is saved to `~/.config/ticketforge/config.json` (mode `0600`). Environment variables
override it: `TFORGE_USERNAME`, `TFORGE_PASSWORD`, `TFORGE_BASE_URL`, `TFORGE_CONFIG` (config path).

## Usage

### Commands

| Command | Purpose | Main flags |
|---|---|---|
| `list` | List tickets, newest first | `-p/--page`, `-n/--limit`, `-a/--all`, `-i/--interactive`, `-s/--stage` |
| `show REF` | Show one ticket in full | |
| `create [TITLE]` | Create a ticket | `-d/--description`, `-s/--stage`, `--dep`, `-f/--field` |
| `update REF` | Change only the given fields | `-t`, `-d`, `-s`, `--add-dep`, `--remove-dep`, `--depends-on`, `--clear-deps`, `-f` |
| `delete REF` | Delete a ticket | `-y/--yes` |
| `fields list\|add\|relabel\|delete` | Manage custom fields | `-l/--label`, `-y` |
| `setup`, `register`, `status` | Configuration (see [Setup](#setup)) | |

Most commands accept `--json`. Refs can be written as `TF-12` or just `12`. For every flag, see
`tforge <command> --help` or [docs/CLI.md](docs/CLI.md).

### List

```bash
tforge list                        # page 1, 10 per page
tforge list -p 2 -n 5              # page 2, 5 per page
tforge list -a                     # everything
tforge list -s in_progress         # filter by stage (open, in_progress, review, closed)
tforge list -i                     # interactive: n/→ next, p/← previous, q quit
```

The interactive browser loads lazily: it fetches only when you move onto a new page, and going
back is free. The page total (`Page 3/3`) appears once the end of the list is reached, because
the API has no count endpoint.

### Create and update

```bash
tforge create "Ship v2" -d "Release" -s in_progress --dep TF-12 -f priority=high
tforge update TF-12 -s review                  # only the stage changes
tforge update TF-12 -t "New title" -d ''       # '' clears the description
tforge update TF-12 --add-dep TF-3 --remove-dep TF-4
tforge update TF-12 -f priority=low -f team=   # set one field, unset another
```

### Other commands

```bash
tforge show TF-12
tforge delete TF-12                            # asks for confirmation (-y to skip)
tforge fields add priority -l Priority         # custom fields are per-user text values
tforge fields relabel priority Urgency
```

### Exit codes

`0` success · `1` API or validation error · `2` not configured or bad credentials

## Development

```bash
pip install -e '.[dev]'
pytest --cov                       # fails below 95% coverage
python scripts/gen_cli_docs.py     # regenerate docs/CLI.md after changing commands
```

A test fails if [docs/CLI.md](docs/CLI.md) falls out of sync with the code.

```
src/ticketforge_cli/
├── cli.py        # commands: parse args, call services, render
├── views.py      # tables, panels, colors, JSON
├── services.py   # ticket logic: safe updates, paging, filtering, validation
├── client.py     # HTTP: auth, retries, rate limits, error mapping
├── models.py     # lenient dataclasses
├── errors.py     # exceptions, mapped from the API's error codes
└── config.py     # config file + env overrides
```

## Assumptions and limitations

- **The password is stored in plaintext** (in a `0600` file), because the API only supports Basic
  auth. Use the environment variables to avoid writing it to disk.
- **Deep pages cost requests.** The API returns 5 tickets per request with no offset, so
  `--page N` steps through every earlier page (about N×limit/5 requests, against 50 per minute).
- **Filtering is client-side**, because the server ignores filter parameters.
- **`list` doesn't show dependencies or custom fields**, because the list endpoint doesn't return
  them. `show` does.
- **429 handling is tested with mocks only.** The live rate limiter appears to count per server
  instance, and it never rejected a request (see [docs/API.md](docs/API.md#rate-limiting)).
- **Refs can be reused** after a delete (the server assigns `max + 1`).
- **No comments, assignees or search**, because the API doesn't have them. Custom fields can be
  relabelled but not renamed.

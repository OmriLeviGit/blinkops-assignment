# `tforge`

Manage TicketForge tickets from the terminal.

**Usage**:

```console
$ tforge [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `-V, --version`: Show the version and exit.
* `--install-completion`: Install completion for the current shell.
* `--show-completion`: Show completion for the current shell, to copy it or customize the installation.
* `--help`: Show this message and exit.

**Commands**:

* `setup`: Configure and verify the connection to...
* `register`: Create a new TicketForge account and...
* `status`: Show the active configuration and check...
* `list`: List your tickets, newest first.
* `show`: Show a single ticket in full.
* `create`: Create a ticket.
* `update`: Update a ticket.
* `delete`: Delete a ticket.
* `fields`: Manage custom field definitions.

## `tforge setup`

Configure and verify the connection to TicketForge.

If the login fails, offers to create the account.

**Usage**:

```console
$ tforge setup [OPTIONS]
```

**Options**:

* `-u, --username <str>`: Prompted if omitted.
* `-p, --password <str>`: Prompted (hidden) if omitted.
* `--base-url <str>`: TicketForge app URL.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge setup  # prompts for URL, username and password
$ tforge setup -u alice -p 's3cret'
$ TFORGE_USERNAME=alice TFORGE_PASSWORD=s3cret tforge status  # env vars, no config file
```

## `tforge register`

Create a new TicketForge account and switch to it.

**Usage**:

```console
$ tforge register [OPTIONS]
```

**Options**:

* `-u, --username <str>`: Prompted if omitted.
* `-p, --password <str>`: Prompted (hidden, confirmed) if omitted.
* `--base-url <str>`: TicketForge app URL (default: configured URL).
* `--save / --no-save`: Save the new credentials as the active config.  [default: save]
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge register  # prompts, then saves the new credentials
$ tforge register -u alice --no-save
```

## `tforge status`

Show the active configuration and check the connection.

**Usage**:

```console
$ tforge status [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge status
$ cp .env.example .env && tforge status  # credentials from ./.env
```

## `tforge list`

List your tickets, newest first.

**Usage**:

```console
$ tforge list [OPTIONS]
```

**Options**:

* `-p, --page <int range>`: Page number.  [default: 1; x>=1]
* `-n, --limit <int range>`: Tickets per page.  [default: 10; x>=1]
* `-a, --all`: Show every ticket, no paging.
* `-i, --interactive`: Browse pages with n/p/q.
* `-s, --stage <str>`: Filter by stage: open | in_progress | review | closed.
* `--json`: Print raw JSON instead of tables.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge list  # page 1, 10 per page
$ tforge list -p 2 -n 5  # page 2, 5 per page
$ tforge list -a  # every ticket
$ tforge list -s in_progress  # filter by stage
$ tforge list -i  # browse with n/p/q
$ tforge list --json
```

## `tforge show`

Show a single ticket in full.

**Usage**:

```console
$ tforge show [OPTIONS] {ref}
```

**Arguments**:

* `ref`: Ticket ref, e.g. TF-12 or 12.  [required]

**Options**:

* `--json`: Print raw JSON instead of tables.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge show TF-12
$ tforge show 12 --json  # bare numbers mean TF-<n>
```

## `tforge create`

Create a ticket.

**Usage**:

```console
$ tforge create [OPTIONS] [title]
```

**Arguments**:

* `title`: Ticket title (prompted if omitted).

**Options**:

* `-d, --description <str>`: Ticket description.
* `-s, --stage <str>`: Initial stage (default: open).
* `--depends-on, --dep <str>`: Ref this ticket depends on. Repeatable.
* `-f, --field <str>`: Custom field name=value. Repeatable.
* `--json`: Print raw JSON instead of tables.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge create "Fix login redirect"
$ tforge create "Write release notes" -d "Cover the new CLI" -s in_progress
$ tforge create "Ship v2" --dep TF-12 --dep TF-13 -f priority=high
```

## `tforge update`

Update a ticket. Only the options you pass are changed.

**Usage**:

```console
$ tforge update [OPTIONS] {ref}
```

**Arguments**:

* `ref`: Ticket ref, e.g. TF-12 or 12.  [required]

**Options**:

* `-t, --title <str>`: New title.
* `-d, --description <str>`: Pass '' to clear.
* `-s, --stage <str>`: open | in_progress | review | closed
* `--depends-on <str>`: Replace all dependencies. Repeatable.
* `--add-dep <str>`: Add a dependency. Repeatable.
* `--remove-dep <str>`: Remove a dependency. Repeatable.
* `--clear-deps`: Remove all dependencies.
* `-f, --field <str>`: name=value to set, name= to unset. Repeatable.
* `--json`: Print raw JSON instead of tables.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge update TF-12 -s review
$ tforge update TF-12 -t 'New title' -d ''  # '' clears the description
$ tforge update TF-12 --add-dep TF-3 --remove-dep TF-4
$ tforge update TF-12 --clear-deps
$ tforge update TF-12 -f priority=low -f team=  # set one field, unset another
```

## `tforge delete`

Delete a ticket. Other tickets' dependencies on it are removed too.

**Usage**:

```console
$ tforge delete [OPTIONS] {ref}
```

**Arguments**:

* `ref`: Ticket ref, e.g. TF-12 or 12.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge delete TF-12
$ tforge delete TF-12 -y  # no confirmation
```

## `tforge fields`

Manage custom field definitions.

**Usage**:

```console
$ tforge fields [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `list`: List custom field definitions.
* `add`: Define a new custom field.
* `relabel`: Change a custom field's display label (the...
* `delete`: Delete a custom field.

### `tforge fields list`

List custom field definitions.

**Usage**:

```console
$ tforge fields list [OPTIONS]
```

**Options**:

* `--json`: Print raw JSON instead of tables.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge fields list
$ tforge fields list --json
```

### `tforge fields add`

Define a new custom field.

**Usage**:

```console
$ tforge fields add [OPTIONS] {name}
```

**Arguments**:

* `name`: Letters, digits and underscores.  [required]

**Options**:

* `-l, --label <str>`: Display label (defaults from name).
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge fields add priority  # label defaults to 'Priority'
$ tforge fields add due_date -l "Due date"
```

### `tforge fields relabel`

Change a custom field's display label (the API does not allow renaming).

**Usage**:

```console
$ tforge fields relabel [OPTIONS] {name} {label}
```

**Arguments**:

* `name`: Field name or id.  [required]
* `label`: New display label.  [required]

**Options**:

* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge fields relabel priority Urgency
```

### `tforge fields delete`

Delete a custom field. Its values are removed from all tickets.

**Usage**:

```console
$ tforge fields delete [OPTIONS] {name}
```

**Arguments**:

* `name`: Field name or id.  [required]

**Options**:

* `-y, --yes`: Skip confirmation.
* `--help`: Show this message and exit.

**Examples**:

```console
$ tforge fields delete priority
$ tforge fields delete priority -y  # no confirmation
```

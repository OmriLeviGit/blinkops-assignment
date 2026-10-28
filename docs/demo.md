# Demo: a recorded run against the live API

This output comes from running `tforge` against
https://integrations-assignment-ticketforge.vercel.app on 2026-10-28 12:25 UTC.
A fresh account was registered for the demo. Colors are disabled so the output renders as plain text.

## Register and set up

```console
$ tforge register -u tforge-demo-1793190305 -p demo-pass-123
✓ Account tforge-demo-1793190305 created
✓ Config saved to /tmp/tmp.km5iY73En5/config.json
```

```console
$ tforge setup -u tforge-demo-1793190305 -p wrong-password --base-url https://integrations-assignment-ticketforge.vercel.app
Error: valid basic auth required
Check your credentials with `tforge setup`.
[exit code 2]
```

```console
$ tforge setup -u tforge-demo-1793190305 -p demo-pass-123 --base-url https://integrations-assignment-ticketforge.vercel.app
✓ Connected as tforge-demo-1793190305. Config saved to /tmp/tmp.km5iY73En5/config.json
```

```console
$ tforge status
Config file: /tmp/tmp.km5iY73En5/config.json
URL:         https://integrations-assignment-ticketforge.vercel.app
Username:    tforge-demo-1793190305
✓ Credentials OK
Rate limit:  48/50 requests left in this window
```

## Custom fields

```console
$ tforge fields add priority --label Priority
✓ Added field priority (Priority)
```

```console
$ tforge fields add team
✓ Added field team (Team)
```

```console
$ tforge fields list
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name     ┃ Label    ┃ Type ┃ ID                        ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ priority │ Priority │ text │ cmvs37lh20014m47h1t6ockkp │
│ team     │ Team     │ text │ cmvs37m0u0016m47hz98vt71e │
└──────────┴──────────┴──────┴───────────────────────────┘
```

## Create

```console
$ tforge create "Set up CI pipeline" -d "GitHub Actions running lint and tests" -f priority=high -f team=platform
✓ Created TF-616
╭─ TF-616 Set up CI pipeline ────────────────────────╮
│ Stage        open                                  │
│ Description  GitHub Actions running lint and tests │
│ Depends on   -                                     │
│ Priority     high                                  │
│ Team         platform                              │
│ Created      2026-10-28 14:25                      │
│ Updated      2026-10-28 14:25                      │
╰────────────────────────────────────────────────────╯
```

```console
$ tforge create "Add login rate limiting" --stage in_progress -f priority=medium
✓ Created TF-617
╭─ TF-617 Add login rate limiting ────╮
│ Stage        in progress            │
│ Description  No description         │
│ Depends on   -                      │
│ Priority     medium                 │
│ Owner        tforge-demo-1793190305 │
│ Created      2026-10-28 14:25       │
│ Updated      2026-10-28 14:25       │
╰─────────────────────────────────────╯
```

```console
$ tforge create "Release v1.0" -d "Blocked on CI and security work" --dep TF-616 --dep TF-617
✓ Created TF-618
╭─ TF-618 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   TF-616, TF-617                  │
│ Created      2026-10-28 14:25                │
│ Updated      2026-10-28 14:25                │
╰──────────────────────────────────────────────╯
```

Four more tickets were created quietly, so the list below spans several server pages (the server returns at most 5 per page).

## List and pagination

```console
$ tforge list --all
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                      ┃ Description               ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-622 │ open        │ Triage bug backlog         │                           │ 2026-10-28 14:25 │
│ TF-621 │ open        │ Rotate API keys            │                           │ 2026-10-28 14:25 │
│ TF-620 │ open        │ Fix flaky integration test │                           │ 2026-10-28 14:25 │
│ TF-619 │ open        │ Update onboarding docs     │                           │ 2026-10-28 14:25 │
│ TF-618 │ open        │ Release v1.0               │ Blocked on CI and         │ 2026-10-28 14:25 │
│        │             │                            │ security work             │                  │
│ TF-617 │ in progress │ Add login rate limiting    │                           │ 2026-10-28 14:25 │
│ TF-616 │ open        │ Set up CI pipeline         │ GitHub Actions running    │ 2026-10-28 14:25 │
│        │             │                            │ lint and tests            │                  │
└────────┴─────────────┴────────────────────────────┴───────────────────────────┴──────────────────┘
7 tickets
```

```console
$ tforge list --limit 3
┏━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage ┃ Title                      ┃ Description ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-622 │ open  │ Triage bug backlog         │             │ 2026-10-28 14:25 │
│ TF-621 │ open  │ Rotate API keys            │             │ 2026-10-28 14:25 │
│ TF-620 │ open  │ Fix flaky integration test │             │ 2026-10-28 14:25 │
└────────┴───────┴────────────────────────────┴─────────────┴──────────────────┘
Page 1 · tickets 1–3 · next: tforge list --page 2 --limit 3
```

```console
$ tforge list --page 2 --limit 3
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                   ┃ Description                  ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-619 │ open        │ Update onboarding docs  │                              │ 2026-10-28 14:25 │
│ TF-618 │ open        │ Release v1.0            │ Blocked on CI and security   │ 2026-10-28 14:25 │
│        │             │                         │ work                         │                  │
│ TF-617 │ in progress │ Add login rate limiting │                              │ 2026-10-28 14:25 │
└────────┴─────────────┴─────────────────────────┴──────────────────────────────┴──────────────────┘
Page 2 · tickets 4–6 · next: tforge list --page 3 --limit 3
```

```console
$ tforge list --page 3 --limit 3
┏━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage ┃ Title              ┃ Description                           ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-616 │ open  │ Set up CI pipeline │ GitHub Actions running lint and tests │ 2026-10-28 14:25 │
└────────┴───────┴────────────────────┴───────────────────────────────────────┴──────────────────┘
Page 3 · ticket 7
```

```console
$ tforge list --stage in_progress
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                   ┃ Description ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-617 │ in progress │ Add login rate limiting │             │ 2026-10-28 14:25 │
└────────┴─────────────┴─────────────────────────┴─────────────┴──────────────────┘
Page 1 · ticket 1
```

Interactive browsing (`tforge list -i`) uses single keypresses, so it isn't captured in this text recording.

## Update

Only the options passed are changed. The description and custom fields survive a stage change, even though the raw API would wipe them:

```console
$ tforge update TF-616 --stage review
✓ Updated TF-616
╭─ TF-616 Set up CI pipeline ────────────────────────╮
│ Stage        review                                │
│ Description  GitHub Actions running lint and tests │
│ Depends on   -                                     │
│ Priority     high                                  │
│ Team         platform                              │
│ Owner        tforge-demo-1793190305                │
│ Created      2026-10-28 14:25                      │
│ Updated      2026-10-28 14:25                      │
╰────────────────────────────────────────────────────╯
```

```console
$ tforge update TF-618 --remove-dep TF-617 -f priority=high
✓ Updated TF-618
╭─ TF-618 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   TF-616                          │
│ Priority     high                            │
│ Owner        tforge-demo-1793190305          │
│ Created      2026-10-28 14:25                │
│ Updated      2026-10-28 14:25                │
╰──────────────────────────────────────────────╯
```

```console
$ tforge update TF-617 --title 'Add login rate limiting (per IP)' --stage closed
✓ Updated TF-617
╭─ TF-617 Add login rate limiting (per IP) ─╮
│ Stage        closed                       │
│ Description  No description               │
│ Depends on   -                            │
│ Priority     medium                       │
│ Owner        tforge-demo-1793190305       │
│ Created      2026-10-28 14:25             │
│ Updated      2026-10-28 14:25             │
╰───────────────────────────────────────────╯
```

## Show and JSON output

```console
$ tforge show TF-618
╭─ TF-618 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   TF-616                          │
│ Priority     high                            │
│ Owner        tforge-demo-1793190305          │
│ Created      2026-10-28 14:25                │
│ Updated      2026-10-28 14:25                │
╰──────────────────────────────────────────────╯
```

```console
$ tforge show TF-618 --json
{
  "ref": "TF-618",
  "title": "Release v1.0",
  "description": "Blocked on CI and security work",
  "stage": "open",
  "created": "2026-10-28T12:25:19.306Z",
  "updated": "2026-10-28T12:25:38.133Z",
  "dependsOn": [
    "TF-616"
  ],
  "customFields": {
    "priority": "high"
  },
  "owner": {
    "id": "cmvs37jcr0012m47hgc1vea1w",
    "username": "tforge-demo-1793190305"
  }
}
```

## Errors

```console
$ tforge update TF-616 --stage done
Error: invalid stage 'done'. Choose one of: open, in_progress, review, closed
[exit code 1]
```

```console
$ tforge update TF-616 -f severity=critical
Error: unknown custom field(s): severity (available: priority, team). Create one with `tforge fields
add NAME`.
[exit code 1]
```

```console
$ tforge show TF-1
Error: you can only view your own workitems
[exit code 1]
```

```console
$ tforge update TF-616
Error: nothing to update; pass at least one option
[exit code 1]
```

## Delete

Deleting a ticket that others depend on also removes it from their dependencies (server-side):

```console
$ tforge delete TF-616 --yes
✓ Deleted TF-616
```

```console
$ tforge show TF-618
╭─ TF-618 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   -                               │
│ Priority     high                            │
│ Owner        tforge-demo-1793190305          │
│ Created      2026-10-28 14:25                │
│ Updated      2026-10-28 14:25                │
╰──────────────────────────────────────────────╯
```


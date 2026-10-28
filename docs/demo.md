# Demo: a recorded run against the live API

This output comes from running `tforge` against
https://integrations-assignment-ticketforge.vercel.app on 2026-10-28 12:17 UTC.
A fresh account was registered for the demo. Colors are disabled so the output renders as plain text.

## Register and set up

```console
$ tforge register -u tforge-demo-1793189838 -p demo-pass-123
✓ Account tforge-demo-1793189838 created
✓ Config saved to /tmp/tmp.JHPVONSuyi/config.json
```

```console
$ tforge setup -u tforge-demo-1793189838 -p wrong-password --base-url https://integrations-assignment-ticketforge.vercel.app
Error: valid basic auth required
Check your credentials with `tforge setup`.
[exit code 2]
```

```console
$ tforge setup -u tforge-demo-1793189838 -p demo-pass-123 --base-url https://integrations-assignment-ticketforge.vercel.app
✓ Connected as tforge-demo-1793189838. Config saved to /tmp/tmp.JHPVONSuyi/config.json
```

```console
$ tforge status
Config file: /tmp/tmp.JHPVONSuyi/config.json
URL:         https://integrations-assignment-ticketforge.vercel.app
Username:    tforge-demo-1793189838
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
│ priority │ Priority │ text │ cmvs2xlfg001ljxzxiouov1v3 │
│ team     │ Team     │ text │ cmvs2xlyq001njxzxnlfovoq8 │
└──────────┴──────────┴──────┴───────────────────────────┘
```

## Create

```console
$ tforge create "Set up CI pipeline" -d "GitHub Actions running lint and tests" -f priority=high -f team=platform
✓ Created TF-602
╭─ TF-602 Set up CI pipeline ────────────────────────╮
│ Stage        open                                  │
│ Description  GitHub Actions running lint and tests │
│ Depends on   -                                     │
│ Priority     high                                  │
│ Team         platform                              │
│ Created      2026-10-28 14:17                      │
│ Updated      2026-10-28 14:17                      │
╰────────────────────────────────────────────────────╯
```

```console
$ tforge create "Add login rate limiting" --stage in_progress -f priority=medium
✓ Created TF-603
╭─ TF-603 Add login rate limiting ────╮
│ Stage        in progress            │
│ Description  No description         │
│ Depends on   -                      │
│ Priority     medium                 │
│ Owner        tforge-demo-1793189838 │
│ Created      2026-10-28 14:17       │
│ Updated      2026-10-28 14:17       │
╰─────────────────────────────────────╯
```

```console
$ tforge create "Release v1.0" -d "Blocked on CI and security work" --dep TF-602 --dep TF-603
✓ Created TF-604
╭─ TF-604 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   TF-602, TF-603                  │
│ Created      2026-10-28 14:17                │
│ Updated      2026-10-28 14:17                │
╰──────────────────────────────────────────────╯
```

Four more tickets were created quietly, so the list below spans several server pages (the server returns at most 5 per page).

## List and pagination

```console
$ tforge list --all
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                      ┃ Description               ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-608 │ open        │ Triage bug backlog         │                           │ 2026-10-28 14:17 │
│ TF-607 │ open        │ Rotate API keys            │                           │ 2026-10-28 14:17 │
│ TF-606 │ open        │ Fix flaky integration test │                           │ 2026-10-28 14:17 │
│ TF-605 │ open        │ Update onboarding docs     │                           │ 2026-10-28 14:17 │
│ TF-604 │ open        │ Release v1.0               │ Blocked on CI and         │ 2026-10-28 14:17 │
│        │             │                            │ security work             │                  │
│ TF-603 │ in progress │ Add login rate limiting    │                           │ 2026-10-28 14:17 │
│ TF-602 │ open        │ Set up CI pipeline         │ GitHub Actions running    │ 2026-10-28 14:17 │
│        │             │                            │ lint and tests            │                  │
└────────┴─────────────┴────────────────────────────┴───────────────────────────┴──────────────────┘
```

```console
$ tforge list -n 3
┏━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage ┃ Title                      ┃ Description ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-608 │ open  │ Triage bug backlog         │             │ 2026-10-28 14:17 │
│ TF-607 │ open  │ Rotate API keys            │             │ 2026-10-28 14:17 │
│ TF-606 │ open  │ Fix flaky integration test │             │ 2026-10-28 14:17 │
└────────┴───────┴────────────────────────────┴─────────────┴──────────────────┘
More tickets available. Next page: tforge list --cursor 
'2026-10-28T12:17:36.706Z:cmvs2xwoy0027jxzxq6kie75q'
```

The cursor printed above resumes exactly where the first page ended:

```console
$ tforge list -n 3 --cursor '2026-10-28T12:17:36.706Z:cmvs2xwoy0027jxzxq6kie75q'
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                   ┃ Description                  ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-605 │ open        │ Update onboarding docs  │                              │ 2026-10-28 14:17 │
│ TF-604 │ open        │ Release v1.0            │ Blocked on CI and security   │ 2026-10-28 14:17 │
│        │             │                         │ work                         │                  │
│ TF-603 │ in progress │ Add login rate limiting │                              │ 2026-10-28 14:17 │
└────────┴─────────────┴─────────────────────────┴──────────────────────────────┴──────────────────┘
More tickets available. Next page: tforge list --cursor 
'2026-10-28T12:17:27.652Z:cmvs2xppf001ujxzx0s5j2p9r'
```

```console
$ tforge list --stage in_progress
┏━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Ref    ┃ Stage       ┃ Title                   ┃ Description ┃ Updated          ┃
┡━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ TF-603 │ in progress │ Add login rate limiting │             │ 2026-10-28 14:17 │
└────────┴─────────────┴─────────────────────────┴─────────────┴──────────────────┘
```

## Update

Only the options passed are changed. The description and custom fields survive a stage change, even though the raw API would wipe them:

```console
$ tforge update TF-602 --stage review
✓ Updated TF-602
╭─ TF-602 Set up CI pipeline ────────────────────────╮
│ Stage        review                                │
│ Description  GitHub Actions running lint and tests │
│ Depends on   -                                     │
│ Priority     high                                  │
│ Team         platform                              │
│ Owner        tforge-demo-1793189838                │
│ Created      2026-10-28 14:17                      │
│ Updated      2026-10-28 14:17                      │
╰────────────────────────────────────────────────────╯
```

```console
$ tforge update TF-604 --remove-dep TF-603 -f priority=high
✓ Updated TF-604
╭─ TF-604 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   TF-602                          │
│ Priority     high                            │
│ Owner        tforge-demo-1793189838          │
│ Created      2026-10-28 14:17                │
│ Updated      2026-10-28 14:17                │
╰──────────────────────────────────────────────╯
```

```console
$ tforge update TF-603 --title 'Add login rate limiting (per IP)' --stage closed
✓ Updated TF-603
╭─ TF-603 Add login rate limiting (per IP) ─╮
│ Stage        closed                       │
│ Description  No description               │
│ Depends on   -                            │
│ Priority     medium                       │
│ Owner        tforge-demo-1793189838       │
│ Created      2026-10-28 14:17             │
│ Updated      2026-10-28 14:17             │
╰───────────────────────────────────────────╯
```

## Show and JSON output

```console
$ tforge show TF-604
╭─ TF-604 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   TF-602                          │
│ Priority     high                            │
│ Owner        tforge-demo-1793189838          │
│ Created      2026-10-28 14:17                │
│ Updated      2026-10-28 14:17                │
╰──────────────────────────────────────────────╯
```

```console
$ tforge show TF-604 --json
{
  "ref": "TF-604",
  "title": "Release v1.0",
  "description": "Blocked on CI and security work",
  "stage": "open",
  "created": "2026-10-28T12:17:32.792Z",
  "updated": "2026-10-28T12:17:50.691Z",
  "dependsOn": [
    "TF-602"
  ],
  "customFields": {
    "priority": "high"
  },
  "owner": {
    "id": "cmvs2xjar001jjxzxtav6b8fi",
    "username": "tforge-demo-1793189838"
  }
}
```

## Errors

```console
$ tforge update TF-602 --stage done
Error: invalid stage 'done'. Choose one of: open, in_progress, review, closed
[exit code 1]
```

```console
$ tforge update TF-602 -f severity=critical
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
$ tforge update TF-602
Error: nothing to update; pass at least one option
[exit code 1]
```

## Delete

Deleting a ticket that others depend on also removes it from their dependencies (server-side):

```console
$ tforge delete TF-602 --yes
✓ Deleted TF-602
```

```console
$ tforge show TF-604
╭─ TF-604 Release v1.0 ────────────────────────╮
│ Stage        open                            │
│ Description  Blocked on CI and security work │
│ Depends on   -                               │
│ Priority     high                            │
│ Owner        tforge-demo-1793189838          │
│ Created      2026-10-28 14:17                │
│ Updated      2026-10-28 14:17                │
╰──────────────────────────────────────────────╯
```


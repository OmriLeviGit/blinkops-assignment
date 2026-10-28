# Evidence: fresh-clone walkthrough

A from-scratch verification of `tforge`, run on 2026-10-28 against the live API
(https://integrations-assignment-ticketforge.vercel.app).

**Environment:** Windows 11 Pro (build 26300) + WSL2 2.5.9, Ubuntu 24.04.2 LTS (kernel 6.6.87.2-microsoft-standard-WSL2),
Python 3.12.3, bash.

**Procedure:** the repo was cloned from GitHub into a new directory (commit `8b75b10`), and
the README's Installation and Setup steps were followed exactly. Then every command in the
README's Usage section was run with a throwaway account, plus the error paths and exit codes.

Each step has two files:

- `.txt`: the plain-text output, easy to read and diff
- `.svg`: a "screenshot" with colors, rendered by `rich` from the same terminal output (open it in a browser)

Commands were run non-interactively (`FORCE_COLOR=1`, 110 columns). Where a command prompts,
the input was piped in, so the prompt and the response appear on the same line. Interactive
paging (`list -i`) was driven through a real pseudo-terminal by sending the keys `n n p q`.

| Step | What it shows | Result |
|---|---|---|
| [01 install](01-install.txt) ([svg](01-install.svg)) | clone, venv, `pip install -e '.[dev]'`, `pytest` (54 passed), `tforge --help` | ✅ |
| [02 setup](02-setup.txt) ([svg](02-setup.svg)) | wrong password → exit 2; correct → config saved with mode `0600`; `status`; env-var-only auth; unconfigured → exit 2 | ✅ |
| [03 fields](03-fields.txt) ([svg](03-fields.svg)) | list, relabel (label shows up in `show`), delete (values removed from tickets), add, duplicate/unknown errors | ✅ |
| [04 create](04-create.txt) ([svg](04-create.svg)) | plain, `-d` + `--stage`, prompted title, unknown field, invalid stage, missing dependency, someone else's ticket as a dependency | ⚠️ see finding 1 |
| [05 show](05-show.txt) ([svg](05-show.svg)) | `TF-n` and bare number; other user's ticket; not found | ✅ |
| [06 list](06-list.txt) ([svg](06-list.svg)) | default, `--page/--limit` with a "next" hint, `--all`, `--stage`, `--json`, page past the end | ✅ |
| [07 update](07-update.txt) ([svg](07-update.svg)) | each option on its own (other fields untouched), stage aliases, dependency add/remove/replace/clear, field set/unset, error cases | ✅ |
| [08 delete](08-delete.txt) ([svg](08-delete.svg)) | confirmation (n → aborted, y → deleted), dependents cleaned up, `--yes`, delete twice → not found | ✅ |
| [09 interactive](09-interactive.txt) ([svg](09-interactive.svg)) | `list -i -n 2`: page 1/3 → 2/3 → 3/3 → 2/3 → quit | ✅ |

## Findings

1. **`create --stage <invalid>` creates the ticket and then fails.** Because the create
   endpoint has no stage, the stage is set by a second request, and it was only validated at
   that point. `tforge create "Bad stage" --stage done` printed "invalid stage" and exited 1,
   but TF-628 had already been created as `open` (it shows up in 06-list).
2. **Two tests fail when `FORCE_COLOR` is set.** The CLI tests check plain-text output, so they
   fail if the environment forces ANSI colors (as some CI runners do). Plain `pytest` passes.
3. Minor: an invalid ref such as `tforge show abc` goes to the server and comes back as
   "workitem ABC does not exist", rather than being rejected locally as a malformed ref.
4. Minor: in error messages, rich highlights things automatically, so `custom field(s)` and
   the numbers in refs come out colored.
5. Minor: the panel shown after `create` has no **Owner** row, while `update` and `show` do,
   because the create response doesn't include the owner.

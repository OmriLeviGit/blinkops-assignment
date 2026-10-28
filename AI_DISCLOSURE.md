# AI disclosure

**Tool:** Claude Code (Anthropic), used from the terminal and VS Code.

## What AI was used for

- **Reverse-engineering the API:** reading the web app's JavaScript bundles, finding extra
  routes through the `x-matched-path` header and `OPTIONS` requests, and probing edge cases
  with live requests. The findings are in [docs/API.md](docs/API.md).
- **Implementation:** the HTTP client, the service layer, the CLI commands and the output.
- **Tests and documentation:** the test suite, README drafts, the generated CLI reference and
  the demo script.

## How I worked

- **Plan first.** Larger changes started with a written plan that I reviewed and adjusted before
  any code was written.
- **I made the design calls:** the layered architecture (cli → services → client),
  page-number pagination with an opt-in interactive mode, lazy loading, and the README structure.
- **Parallel work in git worktrees.** Development, code review and test coverage ran in parallel
  on separate worktrees, and were merged back into `main`.
- **Verification:** every claim about the API was checked with live requests, and I ran the
  evidence walkthrough myself from a fresh clone.

## Tooling choices

For a ~3-hour, single-repo task, I didn't set up custom skills or hooks. The setup cost wouldn't
pay off at this size. On a longer-lived project I would add a `CLAUDE.md` with the project's
conventions, a hook that runs the tests and linter on every change, and skills for repeated
workflows such as regenerating the docs or re-recording the demo.

If agentic capabilities are of interest, a natural follow-up would be an MCP server for
TicketForge built on the same client layer, so that AI agents can create, update and triage
tickets directly.

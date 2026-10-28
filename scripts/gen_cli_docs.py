"""Generate docs/CLI.md from the Typer app.

Wraps `typer ... utils docs` and post-processes its output: the rich markup in
the `--help` examples is rendered as plain text inside console code blocks, so
the same examples read well both in the terminal and on GitHub.

    python scripts/gen_cli_docs.py           # write docs/CLI.md
    python scripts/gen_cli_docs.py --check   # exit 1 if docs/CLI.md is stale
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

from rich.text import Text

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "CLI.md"
TYPER = Path(sys.executable).with_name("typer")

EXAMPLES_BLOCK = re.compile(r"^\[bold\]Examples\[/\]\n\n((?:.+\n?)+)", re.MULTILINE)


def _examples_to_markdown(match: re.Match[str]) -> str:
    lines = [Text.from_markup(line).plain for line in match.group(1).strip().splitlines()]
    body = "\n".join(f"$ {line}" for line in lines)
    return f"**Examples**:\n\n```console\n{body}\n```\n"


def render() -> str:
    raw = subprocess.run(
        [str(TYPER), "ticketforge_cli.cli", "utils", "docs", "--name", "tforge"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return EXAMPLES_BLOCK.sub(_examples_to_markdown, html.unescape(raw)).rstrip() + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        if OUTPUT.read_text() != content:
            print(f"{OUTPUT.relative_to(ROOT)} is out of date; run: python scripts/gen_cli_docs.py")
            return 1
        return 0
    OUTPUT.write_text(content)
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

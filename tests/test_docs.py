import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_cli_docs", ROOT / "scripts" / "gen_cli_docs.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_reference_is_up_to_date():
    gen = load_generator()
    assert gen.OUTPUT.read_text() == gen.render(), (
        "docs/CLI.md is out of date; run: python scripts/gen_cli_docs.py"
    )


def test_every_command_has_examples():
    content = (ROOT / "docs" / "CLI.md").read_text()
    commands = content.count("\n## `tforge ") + content.count("\n### `tforge fields ")
    assert content.count("**Examples**:") >= commands - 1  # the `fields` group itself has none

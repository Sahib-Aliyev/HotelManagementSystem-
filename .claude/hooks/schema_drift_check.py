"""PostToolUse: after an edit under `app/models/`, ask Alembic whether the
migrations still describe the models. Rule: `.claude/rules/migrations.md`."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
WATCHED = PROJECT / "app" / "models"
ALEMBIC = PROJECT / ".venv" / "Scripts" / "alembic.exe"


def edited_path(payload):
    tool_input = payload.get("tool_input") or {}
    for key in ("file_path", "notebook_path"):
        value = tool_input.get(key)
        if value:
            return Path(value)
    return None


def watches(path):
    if path is None:
        return None
    try:
        resolved = (path if path.is_absolute() else PROJECT / path).resolve()
    except OSError:
        return None
    if resolved.suffix != ".py" or not resolved.is_relative_to(WATCHED):
        return None
    return resolved


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    target = watches(edited_path(payload))
    if target is None:
        return 0

    command = [str(ALEMBIC), "check"] if ALEMBIC.exists() else ["alembic", "check"]
    try:
        result = subprocess.run(
            command, cwd=PROJECT, capture_output=True, text=True, timeout=90
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"could not run `alembic check`: {exc}", file=sys.stderr)
        return 2
    if result.returncode == 0:
        return 0

    output = (result.stdout + result.stderr).strip()
    print(
        f"Schema drift after editing {target.relative_to(PROJECT)}: "
        "`alembic check` failed. Write the migration now - "
        "see `.claude/rules/migrations.md`.\n\n" + output,
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

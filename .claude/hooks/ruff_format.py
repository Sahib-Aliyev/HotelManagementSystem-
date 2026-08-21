"""PostToolUse: format a Python file the moment it is written, so the CI
formatting gate listed in `.claude/rules/tests.md` never sees an unformatted
file."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PYTHON = PROJECT / ".venv" / "Scripts" / "python.exe"


def target(raw):
    if not raw:
        return None
    try:
        path = Path(raw)
        resolved = (path if path.is_absolute() else PROJECT / path).resolve()
    except OSError:
        return None
    if resolved.suffix != ".py" or not resolved.is_relative_to(PROJECT):
        return None
    return resolved if resolved.is_file() else None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    path = target((payload.get("tool_input") or {}).get("file_path"))
    if path is None:
        return 0

    executable = str(PYTHON) if PYTHON.exists() else sys.executable
    try:
        result = subprocess.run(
            [executable, "-m", "ruff", "format", str(path)],
            cwd=PROJECT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"could not run `ruff format`: {exc}", file=sys.stderr)
        return 0
    if result.returncode != 0:
        print(
            f"`ruff format` could not parse {path.relative_to(PROJECT)}:\n"
            + (result.stderr or result.stdout).strip(),
            file=sys.stderr,
        )
        return 2
    print((result.stdout or "").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())

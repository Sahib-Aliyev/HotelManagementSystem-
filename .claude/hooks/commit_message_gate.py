"""PreToolUse on a shell tool: refuse a commit that the Git / commit rule in
CLAUDE.md would not accept, and refuse `--no-verify` with it."""

import json
import re
import shlex
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
POINTER = "See the Git / commit rule in `CLAUDE.md`."

# Forms that reuse an existing message, which this hook cannot read.
REUSES_A_MESSAGE = (
    "--no-edit",
    "--reuse-message",
    "--reedit-message",
    "--squash",
    "--fixup",
    "-C",
    "-c",
)
TRAILER = re.compile(r"^[A-Za-z][A-Za-z-]*(-[Bb]y)?:\s", re.ASCII)


def commits(command):
    """True only when a segment of the command line *is* a commit, so that a
    command merely quoting one (an echo, a grep) is left alone."""
    start = re.compile(r"(?:\w+=\S+\s+)*git\s+(?:-\S+\s+)*commit\b")
    return any(
        start.match(segment.strip().lstrip("({ "))
        for segment in re.split(r"[\n;|&]+", command)
    )


def heredoc_bodies(command):
    """Bodies of `<<EOF` / `<<'EOF'` heredocs — how a long -m is passed here."""
    bodies = []
    for match in re.finditer(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", command):
        tag = match.group(2)
        rest = command[match.end() :]
        newline = rest.find("\n")
        if newline == -1:
            continue
        body = rest[newline + 1 :]
        end = re.search(rf"^\s*{re.escape(tag)}\s*$", body, re.MULTILINE)
        bodies.append(body[: end.start()] if end else body)
    return bodies


def herestring_bodies(command):
    """PowerShell `@'` … `'@`, the other multi-line form used in this repo."""
    return [
        match.group(2)
        for match in re.finditer(r"@(['\"])\r?\n(.*?)\r?\n\1@", command, re.DOTALL)
    ]


def flag_values(tokens, short, long):
    values = []
    for index, token in enumerate(tokens):
        if token in (short, long):
            if index + 1 < len(tokens):
                values.append(tokens[index + 1])
        elif token.startswith(f"{long}="):
            values.append(token.split("=", 1)[1])
        elif token.startswith(short) and len(token) > len(short) and short != "-":
            values.append(token[len(short) :])
    return values


def candidate_messages(command):
    messages = heredoc_bodies(command) + herestring_bodies(command)
    try:
        tokens = shlex.split(command, comments=False)
    except ValueError:
        tokens = command.split()
    messages += flag_values(tokens, "-m", "--message")
    for name in flag_values(tokens, "-F", "--file"):
        path = Path(name)
        candidate = path if path.is_absolute() else PROJECT / path
        try:
            messages.append(candidate.read_text(encoding="utf-8"))
        except OSError:
            continue
    return [message for message in messages if message.strip()], tokens


def too_thin(message):
    lines = message.strip("\r\n").splitlines()
    if not lines or not lines[0].strip():
        return "the summary line is empty"
    if len(lines) == 1:
        return "the message is a single line"
    if lines[1].strip():
        return "the line after the summary is not blank"
    body = [
        line for line in lines[2:] if line.strip() and not TRAILER.match(line.strip())
    ]
    if len(body) < 2:
        return f"the body is {len(body)} line(s) long"
    return None


def verdict(command):
    """The hook's exit code for one command line: 2 refuses it, 0 lets it by."""
    if not commits(command):
        return 0

    messages, tokens = candidate_messages(command)
    if "--no-verify" in tokens or "-n" in tokens:
        print(f"Commit refused: `--no-verify`. {POINTER}", file=sys.stderr)
        return 2
    if not messages:
        if any(flag in tokens for flag in REUSES_A_MESSAGE):
            return 0
        print(
            "Commit refused: no message found on the command line. "
            f"Pass it with -m, -F or a heredoc. {POINTER}",
            file=sys.stderr,
        )
        return 2

    reasons = [too_thin(message) for message in messages]
    if any(reason is None for reason in reasons):
        return 0
    print(f"Commit refused: {reasons[0]}. {POINTER}", file=sys.stderr)
    return 2


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    return verdict((payload.get("tool_input") or {}).get("command") or "")


if __name__ == "__main__":
    sys.exit(main())

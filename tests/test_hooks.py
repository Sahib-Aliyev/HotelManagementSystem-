"""The hooks in `.claude/hooks/` decide, mechanically, whether work may
proceed - one of them stands in front of every commit. A wrong answer there is
expensive in both directions: too lax and the convention it guards stops being
enforced, too strict and no commit can be made at all until someone edits a
hook. Both hooks are pure functions over a command line or a path, so they are
checked here rather than by running a session.

What each hook enforces is written down elsewhere and not repeated here: the
**Git / commit rule** in `CLAUDE.md`, and `.claude/rules/migrations.md`.
"""

import importlib.util
import pathlib

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1] / ".claude" / "hooks"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("commit_message_gate")
formatter = load("ruff_format")
drift = load("schema_drift_check")

GOOD = "summary line\n\n- what changed, and why\n- which files it touched"


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "fix"',
        'git commit -m "summary\nbody straight after it\nsecond line"',
        'git commit -m "summary\n\nonly one body line"',
        f'git commit -m "{GOOD}" --no-verify',
        "git commit -m @'\nfix\n'@",
        "git commit -F - <<'EOF'\nfix\nEOF",
        "git commit",
    ],
)
def test_a_commit_message_thinner_than_the_rule_is_refused(command):
    assert gate.verdict(command) == 2


@pytest.mark.parametrize(
    "command",
    [
        f'git commit -m "{GOOD}"',
        f'git add -A && git commit -m "{GOOD}" && git push',
        f"git commit -m @'\n{GOOD}\n'@",
        f"git commit -F - <<'EOF'\n{GOOD}\nEOF",
        f'git commit -m "{GOOD}\n\nCo-Authored-By: Claude Opus 5 <noreply@a.com>"',
        "git commit --amend --no-edit",
        "git commit -C HEAD@{1}",
    ],
)
def test_a_commit_message_the_rule_accepts_goes_through(command):
    assert gate.verdict(command) == 0


@pytest.mark.parametrize(
    "command",
    [
        "git log --oneline -5",
        'echo "git commit -m fix"',
        'grep -rn "git commit" docs/',
        "python .claude/hooks/commit_message_gate.py",
    ],
)
def test_a_command_that_only_mentions_a_commit_is_left_alone(command):
    assert gate.verdict(command) == 0


def test_only_a_python_file_inside_the_project_is_formatted():
    assert formatter.target("app/services/pricing.py") is not None
    assert formatter.target("README.md") is None
    assert formatter.target("app/services/does_not_exist.py") is None
    assert formatter.target("../outside_the_project.py") is None
    assert formatter.target(None) is None


def test_only_a_model_edit_asks_alembic_about_drift():
    assert drift.watches(pathlib.Path("app/models/room.py")) is not None
    assert drift.watches(pathlib.Path("app/services/pricing.py")) is None
    assert drift.watches(pathlib.Path("app/models/room.pyc")) is None
    assert drift.watches(None) is None

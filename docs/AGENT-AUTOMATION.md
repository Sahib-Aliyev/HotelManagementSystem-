# Automating the workflow: hooks and skills

The conventions in this repository are *context*. Claude reads them and usually
follows them, but context cannot make a violation impossible, and it cannot
carry a repeated procedure from one session to the next except by being retyped.
Two mechanisms close that gap, and both were added on **2026-08-21**:

- **A hook** is a command the harness runs at a fixed moment, whatever the model
  decides. Three of them live in `.claude/settings.json`, which is committed, so
  the whole project gets them.
- **A skill** is a procedure written once and loaded only when invoked.
  `/finding` is the first, in `.claude/skills/finding/SKILL.md`.

## The rule that keeps this from becoming duplication

**A hook or a skill never restates a rule. It runs it, or it links to it.**

| | What it may contain | What it must not contain |
| --- | --- | --- |
| Hook | a command, a matcher, an exit code, a one-line message naming the rule file | any explanation of *why* the rule exists |
| Skill | the order of steps, and where to look up each step's rule | the rules themselves, or the history behind them |

Concretely: the migration hook runs `alembic check` — the command CLAUDE.md's
**Commands** section already gives — and on failure its message names
`.claude/rules/migrations.md`. It does not explain batch mode on SQLite. The
`/finding` skill says "naming and placement: `.claude/rules/tests.md`". It does
not repeat the naming rule.

Test for it when touching either: pick a distinctive phrase from any rule and
grep the repository. It must appear in exactly one file. If a hook or a skill
made a second copy, delete the copy and link instead.

---

## The three hooks

All three run `python <script>` — a bare `python` on `PATH`, deliberately. Hook
commands go through the platform shell, and on this machine `cmd.exe` refuses a
program path written with forward slashes (`.venv/Scripts/python.exe …` fails
with *'.venv' is not recognized*) while a POSIX shell refuses one written with
backslashes. A program name with no separator in it works in both. The scripts
themselves then locate `.venv\Scripts\alembic.exe` and `.venv\Scripts\python.exe`
internally, with a fallback for CI, where there is no `.venv`.

Each script's own module docstring names what it enforces. What is worth
recording is why each one exists at all.

### `schema_drift_check.py` — `alembic check` after a model edit

`PostToolUse` on `Edit`/`Write` under `app/models/**`. The 2026-08-19 audit found
the models and the migrations had silently diverged and nothing noticed for
weeks; what that cost is in `docs/history/audit-2026-08-19-architecture.md`. CI
catches it now, but only after a push. This hook catches it in the minute the
model changes, which is when the migration is still cheap to write.

### `commit_message_gate.py` — refuse a commit whose message is one line

`PreToolUse` on `Bash`/`PowerShell`. The **Git / commit rule** in `CLAUDE.md` is
the convention this project leans on hardest, and it held only because whoever
was working chose to comply. A one-line commit is exactly what slips through at
the end of a long session.

The gate reads the message from every form used here (`-m`, repeated `-m`, `-F`,
`-F -` with a heredoc, and a PowerShell `@'…'@` here-string), refuses
`--no-verify` alongside it, and lets through the forms that reuse an existing
message (`--amend --no-edit`, `-C`) because it cannot read those. It fires only
when a *segment* of the command line starts a commit, so `echo "git commit -m
fix"` is not a commit — an early version matched the substring and blocked a
command that merely quoted one. Both hooks are pinned by `tests/test_hooks.py`;
a gate that is wrong in the strict direction blocks every commit in the project
until someone edits it, which is the failure mode that test exists for.

### `ruff_format.py` — format Python after writing it

`PostToolUse` on `Edit`/`Write` matching `**/*.py`. Formatting is one of the CI
gates in `.claude/rules/tests.md`, so a badly formatted file is otherwise found
after the push instead of before it. Formatting only — no `--fix` on lint rules, because
silently rewriting logic behind the model's back is a different and worse class
of surprise. A file `ruff` cannot parse is reported instead, which makes the hook
a syntax check as well.

### Known gaps

- The `PostToolUse` matcher covers `Edit`/`Write`. A file written through the
  shell instead — `sed -i`, a heredoc — is neither formatted nor drift-checked.
- Hook commands assume the working directory is the project root, which is how
  the harness runs them. If it ever is not, `python .claude/hooks/…` exits 2 on
  a missing file, and for the `PreToolUse` gate that reads as a refusal.

### Where hooks are the wrong tool

A hook runs a command; it cannot reason. Anything that needs judgement — "is this
the right layer for this rule", "does this figure name its basis" — stays in
`CLAUDE.md` and `.claude/rules/`. Do not try to encode an invariant as a hook
unless a command can decide it exactly.

---

## Skills

### `/finding` — close an open item

The most repeated procedure in the project's history: reproduce and measure, fix
in the layer that owns the rule, write the regression test, move the entry from
the TODO file into `docs/history/fixed-bugs.md`, commit and push. Each step names
its owner rather than repeating it.

### Still worth writing

- **`/endpoint`** — the chain dictated by hand every time: schema → repository →
  service (with the role check on the state change) → router → register it in
  `app/routers/api/__init__.py` → test. Each step links to
  `.claude/rules/api-and-schemas.md`, CLAUDE.md's **Architecture rule** and
  `.claude/rules/tests.md`. The registration step exists because it is the one
  that gets forgotten — CLAUDE.md already says so.
- **`/audit`** — the methodology that produced eighteen findings in a day: ask
  what *states* the application can be driven into rather than walking code
  paths. It is written down as "the lesson worth keeping" at the end of
  `docs/history/audit-2026-08-19-architecture.md`; a skill would link to that
  section rather than restate it.

### Where skills are the wrong tool

A skill is optional — it applies when invoked. Anything that must hold on every
change belongs in a rule file (always available, path-scoped) or a hook
(enforced). Do not put an invariant in a skill.

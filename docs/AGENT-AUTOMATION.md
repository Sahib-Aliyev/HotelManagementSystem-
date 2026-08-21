# Automating the workflow: hooks and skills

Brief for a future session. Two gaps, both about the same thing: the conventions
in this repository are *context*, not configuration. Claude reads them and
usually follows them — but nothing makes a violation impossible, and nothing
carries the repeated procedures from one session to the next except retyping
them.

- **Gap 1 — nothing enforces a rule.** CLAUDE.md says `alembic check` must pass
  and that a commit needs a broad message. Both survive only because whoever is
  working chooses to comply. A hook is a command the harness runs at a fixed
  moment, whatever the model decides.
- **Gap 2 — the same procedure is re-explained every time.** Closing a finding
  has been the same five steps roughly thirty times. A skill is that procedure
  written once, loaded only when invoked.

## The rule that keeps this from becoming duplication

**A hook or a skill never restates a rule. It runs it, or it links to it.**

| | What it may contain | What it must not contain |
| --- | --- | --- |
| Hook | a command, a matcher, an exit code, a one-line message naming the rule file | any explanation of *why* the rule exists |
| Skill | the order of steps, and where to look up each step's rule | the rules themselves, or the history behind them |

Concretely: the migration hook runs `alembic check` — the command CLAUDE.md's
**Commands** section already gives — and on failure its message is
"schema drift: see `.claude/rules/migrations.md`". It does not explain batch mode
on SQLite. The `/finding` skill says "write the regression test — naming rule in
`.claude/rules/tests.md`". It does not repeat the naming rule.

Test for it afterwards: pick a distinctive phrase from any rule and grep the
repository. It must appear in exactly one file. If a hook or skill made a second
copy, delete the copy and link instead.

---

## Gap 1 — hooks

Hooks live in `.claude/settings.json`, which does not exist yet (`.claude/` holds
only `launch.json`). It is committed, so the whole project gets them.

### 1a. `alembic check` after a model edit — the highest-value one

**Where it fires:** `PostToolUse`, on `Edit`/`Write` touching `app/models/**`.

**What it runs:** `.venv\Scripts\alembic.exe check`, and on failure feeds the
output back so the same session sees it.

**Why here:** the 2026-08-19 audit found that the models and the migrations had
silently diverged — development builds its schema with `create_all()` and
production migrates, so the two had structurally different databases and nothing
noticed for weeks. CI catches it now, but only after a push. This hook catches it
in the minute the model changes, which is when the migration is cheap to write.

**Rule it enforces, and does not restate:** `.claude/rules/migrations.md`
(bullet 1) and the `alembic check` line in CLAUDE.md's Commands.

### 1b. Refuse a commit whose message is one line

**Where it fires:** `PreToolUse`, on `Bash` when the command contains
`git commit`.

**What it checks:** a summary line, a blank line, then at least two body lines.
Refuse `--no-verify` in the same check. It has to read the message from all the
forms actually used here: `-m`, `-F <file>`, and a heredoc.

**Why here:** "write a broad and detailed description on every commit" is the
convention this project leans on hardest — the git log is treated as
documentation, and the last twelve commits obey it only because the agent chose
to. A one-line commit is exactly the kind of thing that slips through at the end
of a long session.

**Rule it enforces:** the **Git / commit rule** in CLAUDE.md.

### 1c. Format Python after writing it

**Where it fires:** `PostToolUse`, on `Edit`/`Write` matching `**/*.py`.

**What it runs:** `.venv\Scripts\python.exe -m ruff format <file>`.

**Why here:** CI runs `ruff format --check`, so a badly formatted file is found
after the push instead of before it. Formatting only — no `--fix` on lint rules,
because silently rewriting logic behind the model's back is a different and worse
class of surprise.

**Rule it enforces:** the lint/format line in CLAUDE.md's Commands, and the CI
gate listed in `.claude/rules/tests.md`.

### Where hooks are the wrong tool

A hook runs a command; it cannot reason. Anything that needs judgement — "is this
the right layer for this rule", "does this figure name its basis" — stays in
`CLAUDE.md` and `.claude/rules/`. Do not try to encode an invariant as a hook
unless a command can decide it exactly.

### Implementation risk to check first

Hook commands run through the shell, and this is a Windows machine where the
interpreter differs from the POSIX examples in the documentation. Verify one
trivial hook end to end (something that just echoes) before writing the three
real ones, and use the `.venv\Scripts\...` paths that CLAUDE.md's Commands
already use rather than a bare `alembic` or `ruff`.

---

## Gap 2 — skills

Skills live in `.claude/skills/<name>/SKILL.md`, load only when invoked, and cost
no context until then. Two are worth writing; a third is optional.

### 2a. `/finding` — close an open item (write this one first)

The most repeated procedure in the project's history. Steps, each pointing at its
owner:

1. Reproduce it and measure — the entries in `docs/history/` show the standard:
   symptom, exact request, observed figure.
2. Fix it in the layer that owns the rule — layer order in CLAUDE.md's
   **Architecture rule**; the invariant index names the rule file.
3. Write the regression test — naming and placement in `.claude/rules/tests.md`.
4. Delete the entry from `SECURITY-TODO.md` or `BUGS-TODO.md` and record it in
   `docs/history/fixed-bugs.md` — the contract is in CLAUDE.md's **Open work and
   history**.
5. Commit with a message that explains what broke and why, then push — CLAUDE.md's
   **Git / commit rule**. (Hook 1b will refuse it otherwise.)

### 2b. `/endpoint` — add an endpoint

The chain that has been dictated by hand every time: schema → repository →
service (with the role check on the state change) → router → register it in
`app/routers/api/__init__.py` → test. Each step links to
`.claude/rules/api-and-schemas.md`, the **Architecture rule**, and
`.claude/rules/tests.md`. The registration step exists because it is the one that
gets forgotten — CLAUDE.md already says so.

### 2c. `/audit` — optional

The methodology that produced eighteen findings in a day: ask what *states* the
application can be driven into rather than walking code paths. It is written down
as "the lesson worth keeping" at the end of
`docs/history/audit-2026-08-19-architecture.md`. A skill would make it repeatable;
link to that section rather than restating it.

### Where skills are the wrong tool

A skill is optional — it applies when invoked. Anything that must hold on every
change belongs in a rule file (always available, path-scoped) or a hook
(enforced). Do not put an invariant in a skill.

---

## Done when

- Editing a file under `app/models/**` without writing a migration produces a
  visible schema-drift warning in the same session.
- `git commit -m "fix"` is refused; a commit with a real body is accepted.
- Writing a Python file leaves it already formatted (`ruff format --check .`
  passes without a separate step).
- `/finding` has been run end to end on one real item from `SECURITY-TODO.md`.
- Grepping a distinctive phrase from any rule finds it in exactly one file — no
  hook or skill has copied prose that a rule file already owns.

## Task frame for that session

```
Goal:        add the three hooks in §1 and the /finding skill in §2a
Don't touch: app/** application code; no new rules in CLAUDE.md
Done when:   the five checks above pass, and the phrase-grep finds no duplication
```

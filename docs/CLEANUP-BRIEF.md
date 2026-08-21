# Consistency cleanup — brief for the session of 2026-08-24

Twenty findings from the consistency audit of **2026-08-21**. None is a
security hole and none breaks a test; they are contradictions between what the
documentation says and what the repository does, prose that now has two owners,
figures that are simply wrong, one piece of dead code, and seven defects in
the hooks and the skill added the same day.

**This file has an expiry.** It is a work order, not an inventory: nothing in it
is a rule, and it must not become another place where open work lives. Anything
still open when the session ends becomes an item in `docs/todo/`, and this file
is deleted along with the line pointing at it in CLAUDE.md's **Open work and
history**.

The three functional items in commit 3 were deliberately *not* filed in
`docs/todo/` on 2026-08-21, so that they have one home for the three days until
this session. If the session slips, file them and delete them here.

How every figure below was measured is in **Verification** at the end. Re-run
those commands before fixing anything: the numbers are three days old.

---

## Decisions needed before the work starts

Four of the findings need Sahib to choose; the rest are mechanical. Ask at the
start rather than guessing, because each answer changes what gets deleted.

| # | Question | Why it cannot be guessed |
| --- | --- | --- |
| C2 | The walk-in flow needs two committing service calls. Leave it recorded as tolerable, or give the request one transaction? | The documentation half is already fixed (see A1 below); what is left is a real change — a unit-of-work boundary — against a partial result nobody has complained about. |
| E1 | Do CLAUDE.md's ten **Security rules** move into the rule files as detail with one-line index entries, or stay where they are with the exemption written down? | Both are defensible. Staying costs context on every session; moving means a security rule is no longer in the always-loaded file. |
| E3 | `start.bat`: delete it, or make it call `run.py` and mention it in `README.md`? | It is nobody's documented entry point, but it may be how Sahib actually starts the app. |

---

## Commit 1 — one owner for each open item

### A1. The same item is filed in four files — **closed on 2026-08-21**

| Item | Where it appears | The contradiction |
| --- | --- | --- |
| Audit log | `docs/LIMITATIONS.md:23`, `SECURITY-TODO.md:122`, `BUGS-TODO.md:74`, `docs/ROADMAP.md:46` | `LIMITATIONS` calls it a deliberately accepted limitation; the other three call it the highest-value missing piece, and `ROADMAP` gives it a *done when* |
| Two-factor authentication | `docs/LIMITATIONS.md:29`, `SECURITY-TODO.md:130` | accepted in one, open in the other |
| CSP `unsafe-inline` / `unsafe-eval` | `docs/LIMITATIONS.md:9`, `SECURITY-TODO.md:72`, `docs/ROADMAP.md:77`, `BUGS-TODO.md:54` | accepted in one, staged work in three |
| Redis for the two counters | `docs/LIMITATIONS.md:14`, `SECURITY-TODO.md` §3, `docs/ROADMAP.md:88` | accepted in one, staged work in two |
| `passlib`, `ACCESS_TOKEN_EXPIRE_MINUTES`, a lock file with hashes | `SECURITY-TODO.md:132-142`, `docs/ROADMAP.md:101-105` | one list restated as another |

The file names in that table are the state **before** the move described below;
`SECURITY-TODO.md` and `BUGS-TODO.md` no longer exist, so the path check under
**Verification** will report those cells and nothing else.

**Measured.** A nine-word shingle scan over every tracked `*.md` finds 28 shared
runs between `BUGS-TODO.md` and `docs/ROADMAP.md`, 9 between `BUGS-TODO.md` and
`docs/LIMITATIONS.md`, and 5 between `SECURITY-TODO.md` and `docs/ROADMAP.md`.

**What it violates.** CLAUDE.md's one-owner-per-area principle, and
`docs/ROADMAP.md`'s own second paragraph, which says the file is only the
sequence.

**What was done instead of waiting for the session.** `SECURITY-TODO.md` and
`BUGS-TODO.md` were replaced by `docs/todo/`, one file per item, nineteen items;
`docs/ROADMAP.md` was rewritten as the sequence and the reasoning only, naming
item numbers; `docs/LIMITATIONS.md` now carries only what is not going to be
done, plus the three decisions-with-triggers. The classification question was
settled by a test rather than a judgement — *does it have a fix and a done when?*
— which is written down at the top of `docs/todo/README.md`.

Two things that came out of doing it: five items that were open work all along
(backups, TLS, request IDs, error tracking, the load test) existed only as
roadmap prose and are now items 015–019; and `BUGS-TODO.md`'s claim that no flow
composes two service calls was false, so the entry moved to
`docs/LIMITATIONS.md` stating what walk-in actually does — which is the
documentation half of C2.

**Still to check in this session:** that no pair of files shares prose again
(the scan under **Verification**), and that nothing outside `docs/todo/`
describes an item rather than naming it.

### A3. The TODO contract sentence existed three times — **closed on 2026-08-21**

It was in `CLAUDE.md`, `SECURITY-TODO.md` and `BUGS-TODO.md`. The two TODO files
are gone; CLAUDE.md's **Open work and history** owns the sentence and
`docs/todo/README.md` points at it. Verify it did not come back.

### A4. The language rule is restated in `README.md`

`README.md:53` repeats CLAUDE.md's **Language rule** almost verbatim. README is
the outward-facing document, so a one-line statement is right — shorten it to
the fact and drop the reasoning, which CLAUDE.md owns.

### A2. Rule prose was copied into `docs/history/`

| Rule file | History file | Shared nine-word runs |
| --- | --- | --- |
| `.claude/rules/api-and-schemas.md` (the optional-not-nullable paragraph) | `docs/history/review-2026-08-17.md` | 10 |
| `.claude/rules/services-runtime.md` (threadpool, `anonymise()`) | `docs/history/audit-2026-08-19-architecture.md` | 9 |
| `.claude/rules/money-and-billing.md` | `docs/history/review-2026-08-17.md` | 2 |
| `.claude/rules/migrations.md` | `docs/history/audit-2026-08-19-architecture.md` | 2 |
| `.claude/rules/reservations-and-rooms.md` | `docs/history/audit-2026-08-19-architecture.md` | 2 |

The rule file should carry the imperative and the arrow to the history file —
which it already does — but not the history file's explanation as well. Trim the
duplicated sentences from the **rule** side, since the history is the record of
how it was learned and must stay readable on its own.

**Not a finding, do not "fix" it:** the overlap between CLAUDE.md's
**Invariants** index and the rule files is deliberate and documented in that
section. The scan reports it as three-word-run overlap; leave it alone.

---

## Commit 2 — the figures

### B1. The test count is stated three times and is wrong in all three

- `README.md:151` says 98.
- `README.md:223` says 134.
- Commit `0c99ce7`'s message says 94 — my own error on 2026-08-21, from
  miscounting pytest's progress dots. The commit is pushed, so the message
  stands; state the correction in the next commit's body rather than rewriting
  history.

Actual on 2026-08-21: **166 collected, 163 passed, 3 skipped** on SQLite (the
skips are the PostgreSQL-only race tests).

**Fix.** State it in one place or nowhere. Recommended: nowhere — replace both
README figures with what the suite covers and the command that counts it, so the
number cannot rot again. `docs/ROADMAP.md`'s hygiene bullet that flags this
inconsistency then goes too.

### B2. `README.md:146` says the templates are "base + 8 pages + partials"

There are nine page templates — `dashboard`, `frontdesk`, `guests`, `login`,
`new_reservation`, `reports`, `reservations`, `rooms`, `settings` — plus
`base.html` and two partials.

**Verified correct on the same pass, do not re-check:** the seed figures (28
rooms, 15 guests, 175 reservations, 45 days of history — reproduced by running
`seed.py` against a scratch database), the role table against the router
dependencies, the configuration table against `.env.example` and
`app/core/config.py`, the CI gates against `.github/workflows/ci.yml`, and every
file path referenced from a `*.md`.

---

## Commit 3 — the code

### C1. `occupant_of_room()` is dead code that re-offers a forbidden shape

**Where.** `app/repositories/reservation_repo.py:178`.

**Measured.** Referenced nowhere: a whole-tree grep over `app/`, `tests/`,
`app/templates/`, `seed.py` and `run.py` finds only the definition.

**Why it matters more than an unused function normally would.** Its body is
`occupants[0] if occupants else None` — the single-row answer that
`.claude/rules/reservations-and-rooms.md` explains `active_for_room()` returns a
list to avoid. The audit of 2026-08-19 deleted six functions for exactly this
reason (`BaseRepository.update/list/count`, `PageParams`,
`RoomService.occupancy_snapshot/board`; recorded in
`docs/history/audit-2026-08-19-architecture.md`). This one survived that sweep.

**Fix.** Delete it. No test names it, so nothing else changes.

### C2. The walk-in flow composes two committing service calls

**Where.** `app/routers/api/reservations.py:74` calls
`GuestService.get_or_create()`, which commits at
`app/services/guest_service.py:64`, and then `ReservationService.create()`.

**Behaviour.** A walk-in that loses the room — `_commit_booking()` turning the
constraint violation into a 409 — leaves the newly registered guest committed
with no booking. Harmless in practice (`get_or_create` finds them next time),
but it is a partially applied operation.

**Why it is in this list.** The old `BUGS-TODO.md` entry claimed no flow needed
two service calls. That claim is gone — `docs/LIMITATIONS.md` now records what
walk-in actually does and names the trigger that would force a unit of work. What
is left is the decision in the table: leave it, or give the request one
transaction.

**Reproduce it before fixing:** register a walk-in against a room that is
already booked for those dates, then search the guest by document number — the
guest exists, the booking does not.

### C3. Nothing asserts that the password-change rate limit fires

**Where.** `app/routers/api/auth.py:68` carries
`@limiter.limit(settings.PASSWORD_CHANGE_RATE_LIMIT)`. The tests that touch
`/auth/change-password` (`tests/test_security.py:99-137`) all test the
functional behaviour; only login's limiter has a test that exhausts it
(`test_repeated_failed_logins_are_rate_limited`).

**Why it is worth a test.** CLAUDE.md's own security rule names the silent
failure: without a `request: Request` parameter the decorator does nothing at
all. That is invisible except to a test that hits the endpoint until it 429s.

**Fix.** One test in `tests/test_security.py`, named after the state it pins;
naming rule in `.claude/rules/tests.md`.

---

## Commit 4 — the automation's own gaps

All six are in what was added on 2026-08-21. The rule they must respect is the
one in `docs/AGENT-AUTOMATION.md`: a hook or a skill links to a rule, it does
not restate it.

### D1. `docs/AGENT-AUTOMATION.md:69` says "Both hooks are pinned by `tests/test_hooks.py`"

Three hooks are pinned there. Fix the sentence.

### D2. The two `PostToolUse` hooks are blind in the mode the project is worked in

They match `Edit|Write`. In a bypass-permissions session the harness asks for
file changes to go through the shell (`sed`, a heredoc), and a file changed that
way triggers neither `ruff format` nor `alembic check`. The gap is already
written down under **Known gaps**; what is missing is the mitigation.

**Fix (the only one of the six with real value).** Add a `PostToolUse` hook on
`Bash`/`PowerShell` that, after the command runs, formats any tracked `*.py`
file that `git status --porcelain` reports as modified, and runs `alembic check`
if any of them is under `app/models/`. Keep it a single command with no
reasoning in its message, same as the other three, and extend
`tests/test_hooks.py` with its predicate.

### D3. The commit gate's two failure modes are asymmetric

- No `python` on `PATH`: the shell exits 127 (or 9009 on `cmd.exe`), which is
  not 2, so the call is allowed — enforcement is silently off.
- Working directory not the project root: `python .claude/hooks/…` cannot find
  the script and exits **2**, which blocks every `Bash` call in the session.

**Fix.** Decide the failure direction deliberately and guard it: resolve the
script path from `CLAUDE_PROJECT_DIR` when it is set, and treat "cannot start"
as a warning rather than a refusal.

### D4. The `/audit` methodology sentence now exists three times

*"what states the application can be driven into rather than walking code
paths"* was in `SECURITY-TODO.md`, `docs/AGENT-AUTOMATION.md` (added 2026-08-21)
and `docs/history/audit-2026-08-19-architecture.md`, which owns it. The first
copy went with the file; cut `docs/AGENT-AUTOMATION.md`'s down to a pointer.

### D7. The gate cannot read a message it cannot see, and then refuses

Two forms defeat it, both hit while writing this brief:

- `git commit -F "$MSG"` — the hook cannot expand a shell variable, finds no
  readable message, and refuses.
- A command that carries an unrelated heredoc *and* a commit (a `python - <<'PY'`
  block followed by `git commit -F <file>`) — `shlex` fails on the mixed
  quoting, the `-F` value is never resolved, and the heredoc body is validated
  as though it were the message. Python source is not a commit message, so the
  commit is refused.

Neither is a false negative, which is the safe direction, but both stop work for
a reason that has nothing to do with the message. Resolve `-F` against the
environment the hook is given, and prefer the `-F` file over a heredoc body when
both are present.

### D5. `.claude/settings.json` matches a tool that does not exist

The `PostToolUse` matcher lists `MultiEdit`. Dead configuration; remove it.

### D6. Two files list what the three hooks do

CLAUDE.md's **Automation** section and `docs/AGENT-AUTOMATION.md` both enumerate
them. This is the same index/detail split as **Invariants** and is acceptable —
recorded here only so that adding a fourth hook does not surprise anyone into
updating one file and not the other.

---

## Commit 5 — structure

### E1. CLAUDE.md's **Security rules** is detail in the always-loaded file

Ten bullets, roughly 45 lines, each with its reasoning — in the file that was
cut from 753 lines to 176 precisely to move detail into path-scoped rule files.
Each bullet has an obvious owner: create-versus-PATCH and "a GET must not write"
→ `.claude/rules/api-and-schemas.md`; the status-independent ceiling →
`.claude/rules/money-and-billing.md`; the `pwf` and `tv` claims and rate
limiting → `.claude/rules/services-runtime.md`; the production-boot guard has no
rule file today. See the decision table.

### E2. The sentence introducing those rules is inaccurate

CLAUDE.md says breaking one breaks a test in `tests/test_security.py`. For three
of the ten the test is elsewhere: the production configuration guard in
`tests/test_config.py`, the status-independent overpayment ceiling in
`tests/test_payments.py:212`, and the read-only PDF route in
`tests/test_reservations.py:531`. Either widen the sentence to `tests/` or move
the tests.

### E3. `start.bat` is a third, undocumented way to start the server

It runs `uvicorn` on a hardcoded `127.0.0.1:8000` with `--reload`, ignoring
`HOST`, `PORT` and `APP_ENV` from `.env`, while the documented `run.py` reads all
three and `.claude/launch.json` invokes `run.py`. No `*.md` mentions it. See the
decision table.

### E4. The nested `CLAUDE.md` files are not mentioned anywhere

`app/templates/CLAUDE.md`, `tests/CLAUDE.md` and `alembic/CLAUDE.md` are pure
pointers — exactly right — but CLAUDE.md's **Rule files** section describes only
`.claude/rules/*.md`, so nothing tells a new session they exist. One line in
that section.

---

## Verification

Re-run these first; the findings are dated 2026-08-21.

Duplicated prose across every tracked `*.md` (the nine-word shingle scan that
produced the figures in A1 and A2):

```bash
python - <<'PY'
import pathlib, re, subprocess, collections
files = [f for f in subprocess.run(["git","ls-files"],capture_output=True,text=True).stdout.split() if f.endswith(".md")]
def norm(t):
    t = re.sub(r"`+", "", t); t = re.sub(r"[*_>#|]", " ", t)
    return re.sub(r"[^a-zA-Z0-9()./:_-]+", " ", t).lower().split()
seen = collections.defaultdict(set)
for f in files:
    w = norm(pathlib.Path(f).read_text(encoding="utf-8"))
    for i in range(len(w) - 8):
        seen[" ".join(w[i:i+9])].add(f)
pairs = collections.Counter(frozenset(v) for v in seen.values() if len(v) > 1)
for pair, n in pairs.most_common():
    print(n, " + ".join(sorted(pair)))
PY
```

Functions defined and never referenced (produced C1; route handlers and
decorated callbacks show up as false positives):

```bash
python - <<'PY'
import pathlib, re
src = [p for p in pathlib.Path("app").rglob("*.py")]
whole = "\n".join(p.read_text(encoding="utf-8") for p in src)
whole += "\n".join(p.read_text(encoding="utf-8") for p in list(pathlib.Path("tests").rglob("*.py")) + list(pathlib.Path("app/templates").rglob("*.html")) + [pathlib.Path("seed.py"), pathlib.Path("run.py")])
for p in src:
    for m in re.finditer(r"^\s*(?:async )?def ([a-zA-Z_]\w*)", p.read_text(encoding="utf-8"), re.M):
        if not m.group(1).startswith("__") and len(re.findall(rf"\b{m.group(1)}\b", whole)) <= 1:
            print(p, m.group(1))
PY
```

The rest:

```bash
.venv\Scripts\python.exe -m pytest --collect-only -q
```

- Every path named in a `*.md` exists: glob each `app|docs|tests|alembic|.claude|.github` reference and check it. Four are deliberately absent (`app/static/vendor/`, `app/static/js/pages/*.js`, `docs/runbook.md`) because they are targets, not links.
- The language rule: search tracked files for `[əıĞğŞşƏ]`. Do **not** use a
  case-insensitive match — Python and PCRE fold dotless `ı` onto `I`, which
  matches every ASCII file in the repository and reports the whole tree. This
  brief is the only tracked file the scan hits, because it names the letters.

---

## Done when

- Each of the five items in A1 is described in exactly one file, and no file
  classifies it differently from another.
- The shingle scan reports no pair of files sharing prose except the
  CLAUDE.md-Invariants-to-rule-file overlaps, which are deliberate.
- `README.md` states the test count in one place or not at all, and the template
  count matches `app/templates/`.
- `occupant_of_room()` is gone; the walk-in decision is taken either way; the
  password-change limiter has a test.
- A file changed through the shell is formatted and drift-checked, and
  `tests/test_hooks.py` covers the new hook's predicate.
- CLAUDE.md's security-rule sentence names where the tests actually are.
- Every item closed here is recorded in `docs/history/fixed-bugs.md` per
  CLAUDE.md's **Open work and history**, this file is deleted, and the line
  pointing at it in that section goes with it.

## Task frame for that session

```
Goal:        the five commits above, in order; ask the four decision questions first
Don't touch: app/** beyond C1, C2 and C3; no new rules anywhere
Done when:   the checks above pass and this file is deleted
```

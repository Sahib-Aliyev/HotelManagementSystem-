---
name: finding
description: Close one open item from SECURITY-TODO.md or BUGS-TODO.md end to end - reproduce, fix in the owning layer, pin with a regression test, move the entry into docs/history, commit. Use when asked to fix, close or work off a listed finding, bug or security item.
---

# Close an open finding

The order below is the procedure; each step names the file that owns its rule.
Do not re-derive a rule here - open the file named and follow it.

## 1. Reproduce it and measure it

Read the entry in `SECURITY-TODO.md` or `BUGS-TODO.md`, then reproduce the
behaviour before changing anything: exact request, observed result, and the
figure if there is one. The entries in `docs/history/` set the standard for what
"measured" means - `docs/history/README.md` is the index.

State the reproduction back before moving on. If it cannot be reproduced, that
is the finding: say so and stop.

## 2. Fix it in the layer that owns the rule

The layer order and the one-owner-per-area principle are the **Architecture
rule** in `CLAUDE.md`; its **Invariants** index maps the rule to the file that
owns it, and that rule file loads as soon as you open a file it governs.

Fix it in that one place. If the same check already exists somewhere else, the
fix is to remove the copy, not to add a third.

## 3. Pin it with a regression test

Write the test that fails before the fix and passes after it. Naming and
placement: `.claude/rules/tests.md`, and `tests/CLAUDE.md` for the fixtures.

Run the suite, not only the new test - the command is under **Commands** in
`CLAUDE.md`.

## 4. Move the entry out of the TODO file

Delete it from `SECURITY-TODO.md` / `BUGS-TODO.md` and record it in
`docs/history/fixed-bugs.md`, naming the test from step 3 - the contract is
**Open work and history** in `CLAUDE.md`.

If the item was one of several under a heading, check whether the heading itself
is now empty and should go too.

## 5. Commit, then push

One commit for the finding, with the message the **Git / commit rule** in
`CLAUDE.md` asks for; `.claude/hooks/commit_message_gate.py` refuses anything
thinner. Push to `origin` once the tests pass.

## Where this skill stops

It closes one listed item. Finding new ones is a different job - the method that
found eighteen in a day is at the end of
`docs/history/audit-2026-08-19-architecture.md`.

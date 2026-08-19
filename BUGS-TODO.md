# Open bugs

Functional defects that are not security issues — those live in
`SECURITY-TODO.md`.

Both entries this file carried (the overdue guest who disappeared from the front
desk, and the housekeeping menu clipped by its room card) were fixed on
**2026-08-19**; the details are in the "Review of 2026-08-17" section of
CLAUDE.md.

**Nothing is open right now.** When something is found, describe it here the way
those two were: symptom, where in the code, what was measured or reproduced, and
what the fix should be — then move it into CLAUDE.md with its regression test
once it is closed.

---

## Waiting on a human check

- [ ] **The room-card `⋮` menu at three widths.** The clipping fix is verified
      in the running app for the three things it depends on: the card computes
      `overflow: visible`, the status stripe carries its own 16px top radius,
      and the menu opens upward (`bottom-full`). What is *not* verified is the
      hit test that originally proved the bug —
      `document.elementFromPoint()` over each item — because the preview
      browser used to check it reports a 0×0 viewport, so no geometry it
      returns means anything. Open `/rooms`, click `⋮` on a card in the **last**
      grid row, and confirm all three items are visible and clickable at
      desktop, tablet and mobile widths.

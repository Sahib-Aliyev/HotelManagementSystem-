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

## Closed since, for the record

The room-card `⋮` menu needed a second pass. Removing the card's
`overflow-hidden` and opening the menu upward stopped it being clipped
*vertically*, but the menu is 176px wide and a card is about 155px wide in the
two-column layout, so it still overflowed the grid sideways — on a narrow
window it rendered as a blank white sliver half outside the visible area.

There is no position that fits, so the popover was removed. The three actions
are inline icon buttons in the card's button row. Hit-tested at 375, 768 and
1280px, on the first and the last card in the grid: every control sits inside
its card and `document.elementFromPoint()` at its centre returns the control
itself. The round trip was exercised in the running app too — Available → Flag
for cleaning → Cleaning → Mark clean → Available — and "Take out of service"
still goes through the confirmation dialog.

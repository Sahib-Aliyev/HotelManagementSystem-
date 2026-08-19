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

No position inside the card fits, so the menu now leaves the card: it is
teleported to `<body>` and positioned against its button, clamped to the
viewport (`cardMenu()` in `app.js`). Inline icon buttons were tried in between
and reverted — they worked, but they made a 155px card busy and pushed the
actions onto a second row.

Fixing the position surfaced the defect behind the blank white panel in the
screenshot: the `:style` binding carrying those coordinates was overwriting the
`display: none` that `x-show` sets, so all 28 menus stayed rendered as invisible
boxes wherever they had last been positioned. Coordinates are written
imperatively now and `x-show` owns visibility.

Verified at 375, 768 and 1280px on the first and last card: nothing rendered
while closed, the menu opens inside the viewport aligned to its button, every
item is returned by `document.elementFromPoint()`, it follows the button on
scroll and closes when the button leaves the screen, and Escape / an outside
click / a second click all dismiss it. The round trip was exercised in the app
too — Available → Flag for cleaning → Cleaning → Mark clean → Available — and
"Take out of service" still goes through the confirmation dialog.

Two things about the environment, so the next reader does not repeat the
detour: the preview browser runs the page as a **hidden tab**, where CSS
transitions never complete and programmatic scrolls fire no scroll events, so
anything whose visibility depends on a transition cannot be measured there. And
a full-screen screenshot with another window of the same app behind it looks
exactly like a duplicated sidebar — the app renders one `<aside>`, which is
worth checking before hunting for a CSS bug.

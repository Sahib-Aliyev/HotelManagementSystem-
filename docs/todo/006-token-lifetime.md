# 006 — Shorten the access-token lifetime

**Kind** security · **Size** hours · **Depends on** nothing

## What is wrong

`ACCESS_TOKEN_EXPIRE_MINUTES` is 720 — twelve hours. Signing out now revokes
tokens through the `tv` claim, so the window only matters for a token stolen from
a session nobody signs out of. But a front-desk shift is not twelve hours long,
and a shared reception machine is exactly where a forgotten session sits.

## Fix

Two decisions, and the second is why this is not a one-line change:

1. **The number.** A shift length is the natural anchor; the value belongs in
   `.env.example` and `app/core/config.py` together, and README's configuration
   table states it, so all three move at once.
2. **Whether the session renews.** Cutting the lifetime without a renewal path
   signs a receptionist out mid-shift, which trades a security window for people
   working around it. Either accept the sign-in, or issue a fresh token on
   activity — in which case the renewal has to keep both the `pwf` and `tv`
   claims, or it hands back exactly the session that signing out revoked.

The claims and what they are for are a **Security rule** in `CLAUDE.md`; do not
restate them in the code.

## Done when

The default lifetime is the agreed number in `config.py`, `.env.example` and
README; a test pins that a token older than the window is refused; and if
renewal was chosen, a renewed token still fails after a password change and
after a sign-out.

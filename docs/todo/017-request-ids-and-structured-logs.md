# 017 — Request IDs and structured logs

**Kind** operations · **Size** hours · **Depends on** nothing

## What is wrong

A 500 in production leaves a stack trace with nothing tying it to a user, a
reservation or a request. A receptionist saying "it failed when I checked her
out" cannot be connected to any line in the log.

## Fix

Middleware that stamps an id on every request, logs one JSON line per request
(method, path, status, duration, user id, request id), and returns the id in the
error body so it can be read off the screen and quoted.

The error body format is already uniform and rendered by the frontend without
special cases — add the id to it rather than inventing a second shape.

## Done when

A deliberately broken request is findable in the logs by the id shown on screen.

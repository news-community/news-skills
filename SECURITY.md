# Security

## What this repo is, in security terms

A single-file Python CLI that reads the alaskanews.com API. It runs on your machine, has no server
and no database, stores nothing, and handles exactly one secret: **your own API key**.

That narrows the realistic problems to three, and they are all listed below rather than left for you
to work out.

## If your API key leaks

Revoke it yourself, immediately, at `alaskanews.com/profile/settings`. You do not need us and you
should not wait for us. Then create a replacement with **Read-only** ticked: a read-only key is
rejected by the server on every write method before a handler runs, so a leaked one cannot be used
to damage the newsroom.

Do not paste a key into an issue. `alaska_desk.py check` is safe to paste; it prints reachability
statuses and never the key.

## Two behaviours worth knowing before you run it

Neither is a vulnerability. Both are the kind of thing you should be told rather than discover.

**`PLATFORM_API_BASE` redirects where your key is sent.** The client reads that environment variable
to choose the API host, which exists so the tool can be pointed at a local platform for development.
Anything that can set it in your environment can make the client send your `Authorization: Bearer`
header to a host of its choosing. If you did not set it, do not let anything else set it, and be
wary of a shell profile or `.env` you did not write.

**It reads `.env` and `.env.local` from the current directory**, not only from beside the script, so
that the key is found whether you run from the project root or the script's folder. Values are
loaded without overriding anything already in your environment, and only `ALASKA_DESK_API_KEY` is
ever sent anywhere. Still: running it inside an unrelated project loads that project's `.env` into
the process. If that matters to you, export the key instead and keep no `.env` nearby.

## Reporting a vulnerability

**In this code:** use GitHub's private vulnerability reporting on this repository (the Security tab,
"Report a vulnerability"). Please do not open a public issue for something exploitable. A first
response should take a few days; if it does not, open a public issue saying only that you are
waiting on a private report, with no detail.

**In alaskanews.com itself:** that is the platform, not this client, and it is a separate codebase.
Report it through the site rather than here. If you are unsure which side a problem is on, report it
privately here and it will be routed.

## Out of scope

- Reach limits. A 401 or 403 on an endpoint is authorization working. `check` will tell you what
  your key reaches, and cookie-session endpoints (`GET /clips`, `GET /transcripts/search`) reject
  every API key by design, whatever your role.
- Rate limiting (300 reads/min). A 429 is a back-off, not a flaw.
- Content of the reporting retrieved through the API. Corrections belong with the newsroom.

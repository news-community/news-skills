# Security

## What this repo is, in security terms

A single-file Python CLI that reads a Communities News newsroom API, alaskanews.com by default. It
runs on your machine, has no server and no database, stores nothing, and handles exactly one secret:
**your own API key**.

That narrows the realistic problems to three, and they are all listed below rather than left for you
to work out.

## If your API key leaks

Revoke it yourself, immediately, at your newsroom's `…/profile/settings` (for the default
newsroom, `alaskanews.com/profile/settings`). You do not need us and you should not wait for us. Then create a replacement with **Read-only** ticked: a read-only key is
rejected by the server on every write method before a handler runs, so a leaked one cannot be used
to damage the newsroom.

Do not paste a key into an issue. `news_desk.py check` is safe to paste; it prints reachability
statuses and never the key.

## Three behaviours worth knowing before you run it

None is a vulnerability. All three are the kind of thing you should be told rather than discover.

**Two environment variables decide where your key is sent.** `NEWS_SITE` chooses the newsroom, and
the API base is derived from it; `PLATFORM_API_BASE` overrides that base outright, which exists so
the tool can be pointed at a platform running locally. Anything that can set either in your
environment can make the client send your `Authorization: Bearer` header to a host of its choosing.
If you did not set them, do not let anything else set them, and be wary of a shell profile or a
`.env` you did not write. `check` prints the newsroom it is actually pointed at, on the first line,
for exactly this reason.

**It reads `.env` and `.env.local` from the current directory**, not only from beside the script, so
that the key is found whether you run from the project root or the script's folder. Values are
loaded without overriding anything already in your environment, and the only secret it ever
transmits is `NEWS_DESK_API_KEY` (or the legacy `ALASKA_DESK_API_KEY`). Still: running it inside an
unrelated project loads that project's `.env` into the process. If that matters to you, export the
key instead and keep no `.env` nearby.

**It fetches each newsroom's usage terms over the network.** Before printing the terms line, the
client reads `<newsroom>/robots.txt` and, failing that, `<newsroom>/llms.txt`. That is one extra
unauthenticated GET per run, to the same host you are already querying, carrying no key.

## What the client does to protect the key

**It refuses to follow a redirect to another origin.** `urllib` follows 3xx by default and rebuilds
the request with the headers it was given, `Authorization` included, without caring that the target
is a different host or that `https` has just become `http`. So anything able to answer for the
configured newsroom, or to sit in front of it, could collect a reader's key with a single redirect.
Reproduced on 2026-09-10 with two local servers: the second origin received the bearer token intact.
The authenticated path now refuses instead, names both origins, and sends nothing. Same-origin
redirects still work.

It refuses rather than quietly stripping the header, because a newsroom API that redirects a JSON
GET to another origin is not something to paper over, and the 401 that stripping would produce reads
as a key problem, which is the wrong place to send the reader.

**It will not read a permission out of a comment.** Usage terms are parsed only from an active
`Content-Signal` line in `robots.txt`, or from a declaration-shaped list item in `llms.txt`, which is
labelled as the softer source when used. A commented-out directive used to be read as a granted
permission, and the dangerous direction is that one: reading `ai-train=no` as `yes` invites a reader
to breach terms they were never given.

## Reporting a vulnerability

**In this code:** use GitHub's private vulnerability reporting on this repository (the Security tab,
"Report a vulnerability"). Please do not open a public issue for something exploitable. A first
response should take a few days; if it does not, open a public issue saying only that you are
waiting on a private report, with no detail.

**In alaskanews.com itself:** that is the platform, not this client, and it is a separate codebase.
Report it through the site rather than here. If you are unsure which side a problem is on, report it
privately here and it will be routed.

## Out of scope

- Reach limits. A 401 or 403 on an endpoint is authorization working. Some endpoints authenticate
  by browser session only and reject every API key by design, whatever its role; they answer 403
  with `error: session_auth_only` and a remedy. The platform publishes that list itself and `check`
  renders it, so this file deliberately does not repeat it: on 2026-09-09 the server listed twelve
  such paths while this repo's prose named two, which is why the client stopped carrying a
  hand-written copy in the first place.
- Rate limiting (300 reads/min). A 429 is a back-off, not a flaw.
- Content of the reporting retrieved through the API. Corrections belong with the newsroom.

# Changelog

The skill declares a `version` under `metadata` in
[`SKILL.md`](skills/local-news-api/SKILL.md). This file is what that number refers to.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are the day the work
landed on `main`.

## 1.6.1 - 2026-10-02

### Changed

- **The one local write is declared.** "Read-only" was always about the newsroom: the client never
  writes to the platform. But `brief --out FILE` writes a Markdown file on your machine, replacing one
  already at that path, and the skill never said so beside the read-only claim. One of ClawHub's
  three scanners (SkillSpector) rated 1.6.0 "do not install" partly on that mismatch. `SKILL.md` now
  says it in the description, in a **Local files** row, and where `brief` is explained; the README
  and `--out`'s own help say it too. Behaviour is unchanged.
- **A test keeps it true.** It reads the client's source for every call that writes to disk, finds
  exactly one (in `brief`), and first proves it can find a planted write. Two more check that the
  row is there and that `--out` replaces an existing file, as documented.

## 1.6.0 - 2026-09-30

### Changed

- **`digest --date` asks for the day directly.** The platform fixed the public feed on 2026-09-30:
  it now filters by `community`, takes `published_after` and `published_before`, pages exactly (an
  `as_of` cursor, a true `has_more`, and a `next_page` link), and reports the newsroom's time zone.
  So a day is one window query instead of a scan: the same 34 stories for 2026-09-29 in one request
  where the scan read 300, and a June date the scan could not finish now completes in a second.
- **Days are counted in the time zone the newsroom reports**, read from the feed without a key,
  instead of a zone compiled into the client for the default newsroom. `--tz` still overrides it,
  and a newsroom that reports none is counted in UTC, said aloud.
- Gone with the platform's bugs: the week-long scan and its cap, filtering rows by community,
  paging until empty, and de-duplicating across pages. What stays is a check that the rows are the
  ones asked for (the right day, the right newsroom, no repeats), so a server that ignored a filter
  stops the command instead of printing a wrong day; and the hand-written timestamp parser, since
  the API still trims trailing zeros from fractional seconds, which Python 3.9 cannot read.

## 1.5.0 - 2026-09-30

Two features carried over from the newsroom's own internal tools, adapted to what an outside reader
can reach.

### Added

- **`digest --date <today | yesterday | YYYY-MM-DD>`: one day's stories**, newest first, each with
  its time, place, one-line summary and link. A daily briefing, and **no key**: it reads the public
  `/feed`. `--tz <Area/City>` sets the time zone a day is counted in; the default newsroom's own zone
  (America/Anchorage) is the default, and another newsroom gets UTC with a note saying so, since the
  API reports no time zone. `--json` gives the stories as data.
- **`brief "<topic>"`: a research brief before writing.** One `/search` across every corpus the key
  reaches, arranged in a writer's order (prior coverage, meeting and hearing transcripts, people on
  the record, events, beats), then four blanks to fill before drafting: why it matters, whose voice
  is missing, what you will cite, and a premise check. No model call. `--out FILE` also saves it,
  with the newsroom's terms. It says which corpora it could not search for your key.

### Measured, and built around

The public feed was measured on 2026-09-29 before anything was built on it, and five facts shaped
`digest --date` (all fixed on the platform the next day; see 1.6.0): it answers without a key while `/articles` does not; it **ignores its documented
`community` parameter**, so rows are filtered by their own community; its **paging metadata is
wrong** (`has_more` is always false while the next offset answers), so it is paged until a stop rule
instead; it is **ranked, not chronological** (a story can arrive up to about a week behind older
ones, and resurface up to a year after publication), so the scan runs to a week past the day; and
**pages overlap**, so rows are de-duplicated. Its timestamps carry 5-digit fractional seconds that
Python 3.9's `fromisoformat` rejects, so the client parses them itself.

### Changed

- `/feed` is read by this client now, in one place and as a public read. It was deliberately left
  alone on 2026-09-09 because, for a keyed reader, it duplicated `/articles`; that reasoning did not
  cover a reader with no key.
- Next-step hints no longer say `digest` is the only keyless mode; `topics` and `tags` have been
  keyless since 1.3.0.
- `SKILL.md`'s explanation of next steps and `next_steps` moved to `references/output.md`, to keep
  the body an agent loads inside its budget.

### From an outside review of the skills page

- **Relevance is no longer called corroboration.** Two matching dimensions (topic and actor) make a
  piece relevant; several pieces can repeat one source, so they do not confirm a claim. `SKILL.md`,
  `angles`' output and its next steps now say to verify against an independent source, ideally the
  primary record. A test pins the wording.
- **The read-only key's guarantee is stated exactly.** It was "cannot damage the newsroom if it
  leaks". The server rejects every write such a key attempts, so it cannot change anything; it is
  still a credential that can read what it reaches and spend its rate limit, so a leaked one gets
  revoked. The same fix is in the README.
- **The `rag` cost of a read-only key comes first**, beside the advice to create one, and the `rag`
  line in the Modes block says it will not run with one.
- **The `angles` table matches the code.** It said `rag` ran underneath two intents; each run is one
  `/search`, and `rag` is only ever a suggested next step. The table now has separate "runs now" and
  "suggested next" columns, per intent.
- Historical explanations of old bugs left `SKILL.md` for this changelog, and the account settings
  address is a link.

## 1.4.1 - 2026-09-30

Housekeeping before the repository goes public; no behaviour changes.

- A code comment in `local_news_api.py` pointed at a planning document that lives outside this
  repository. It now points at the newsroom's public API spec instead
  (`<newsroom>/api/v1/openapi.json`; for Alaska News, `alaskanews.com/api/v1/openapi.json`).
- `.env.example` gives a generic `localhost:<port>` for the local-platform override rather than a
  specific development port.

## 1.4.0 - 2026-09-30

### Changed

- **Renamed to `local-news-api` ("Local News API")**, from `news-desk`. It is a read-only client
  for a newsroom's public API, and "desk" described neither that nor anything it does. The skill
  folder is `skills/local-news-api/` and the client is `scripts/local_news_api.py`. On ClawHub the
  old slug `news-desk` stays as a redirect, so an existing install keeps resolving.
- **The key is `COMMUNITIES_NEWS_API_KEY`**, named for what it is: a Communities News platform key,
  whose prefix `cn_` already said so. `NEWS_DESK_API_KEY` and `ALASKA_DESK_API_KEY` are still read,
  in that order after the new name, so no existing setup breaks. Deliberately not `NEWS_API_KEY`,
  which newsapi.org users commonly have set: reading it would send a stranger's key to the newsroom.
- **`SKILL.md` introduces the platform and uses Alaska News as its worked example**, naming the site
  (`https://alaskanews.com`), the API (`https://alaskanews.com/api/v1`) and the spec
  (`https://alaskanews.com/api/v1/openapi.json`), where it used to read as an Alaska-only tool.
- The User-Agent is `local-news-api/1.4.0`, and a test now derives it from the frontmatter `name`
  as well as the version.

## 1.3.1 - 2026-09-30

### Security

- **A project folder's `.env` can no longer choose where your key is sent.** The client reads
  `.env` files from the directory it runs in, which is whatever project the skill is used inside.
  Such a file could set `NEWS_SITE` or `PLATFORM_API_BASE`, so an agent working in an untrusted
  repository would send an exported `NEWS_DESK_API_KEY` to that repository's host. Reproduced
  against 1.3.0: a local collector received the bearer token. A current-directory `.env` may now
  set only the key and `NEWS_COMMUNITY`; destination settings in it are ignored and named on
  stderr, and a `.env` next to `news_desk.py` or your real environment still sets them. Found by
  ClawHub's security scan of 1.3.0, which rated the skill suspicious for exactly this.

## 1.3.0 - 2026-09-29

Readiness for skill registries, and one mode moved off an endpoint the platform has retired.

### Changed

- **License is now MIT-0** (MIT No Attribution), from MIT. Use, modify and redistribute with no
  attribution required. Skill registries such as ClawHub publish every skill under MIT-0 and accept
  no other terms, so the repository matches what a registry would state. The newsroom's content
  terms are unaffected and are still read from the newsroom on every run.
- **`topics` reads topic tags instead of the retired `/topics` endpoint.** The platform's OpenAPI
  spec marks `/topics` deprecated ("Use `GET /api/v1/tags` instead"), and every beat it listed
  reported 0 articles. `topics` now lists the topic-category tags ranked by articles published
  (Government 556, Infrastructure 345, Commercial Fisheries 299 on alaskanews.com today), names
  each one's parent, and pages the ranked list. Every slug it prints works with `browse --tag`.
- **`topics` and `tags` need no key.** `/tags` answers without one, and a public request now sends
  no credential even when a key is set: it buys nothing there, and it is one more place the key
  would go.
- The User-Agent carries the skill's real version (`news-desk/1.3.0`); it said `1.1` through 1.2.0.

### Fixed

- `tags --category` is taken on trust no longer. The server ignores a category it does not filter
  on and answers the whole vocabulary: `election` exists on 67 tags but `category=election`
  returned all 600. `tags` now says when the rows do not match the filter it asked for, and offers
  only the three categories the server filters (`organization`, `topic`, `location`).

### Added

- `metadata.openclaw` in `SKILL.md` declares every environment variable the client reads, all
  optional, with `NEWS_DESK_API_KEY` as the primary. A test holds the declaration and the code
  equal in both directions.
- `agents/openai.yaml` carries the name and short summary a skill catalog shows, kept separate from
  `SKILL.md`'s `description`, which is written for the agent.
- `.clawhubignore` keeps the test file and any `.env` out of a registry bundle. `SKILL.md` no longer
  links outside its own folder or points an agent at the tests; the Development notes it carried
  are in `CONTRIBUTING.md`.

## 1.2.0 - 2026-09-10

Findings from two external code reviews. Every one was reproduced before it was fixed.

### Security

- **The API key no longer follows redirects to another origin.** `urllib` rebuilds a redirected
  request with the headers it was given, `Authorization` included, regardless of host or scheme.
  Reproduced with two local servers: the second origin received the bearer token intact. The
  authenticated path refuses now, names both origins, and sends nothing.

### Fixed

- A **commented-out** `Content-Signal` directive was read as granted permission, so
  `# Content-Signal: ai-train=yes` printed as a licence to train. Comments are stripped before
  parsing, and `llms.txt` now yields policy only from declaration-shaped list items, labelled as the
  softer source.
- `article <url>` printed the **configured** newsroom's terms over content fetched from a different
  one. Terms follow the origin the content actually came from.
- A **bare slug** took the keyed endpoint and demanded a key, though it is documented as public. A
  UUID now distinguishes an id from a slug.
- `events "<query>"` filtered one page and reported "nothing in the window" when the match sat
  further down. For a tool people use to find hearings and comment deadlines, that does not look
  like a limitation, it looks like an answer. It pages the window now, and says so when a scan cap
  stops it.
- `check --json` printed prose, so the one mode a script would parse was the one that could not be.
- A key rejected by **every** endpoint was labelled "no access (role)" on each, sending readers after
  a role upgrade when the credential was simply bad.
- The `check` footer said "your key reached the search surface" after every request had failed.
- An inline comment in `.env` became part of the value, so `KEY=cn_x  # mine` failed on a credential
  that looked correct in the file. `.env` files are also read as utf-8 explicitly rather than in the
  platform's preferred encoding.
- One test needed the network, so the suite advertised as offline in three places failed with
  networking disabled. It is now 0 failures offline.

## 1.1.0 - 2026-09-10

The release that stopped this being an Alaska-only tool, and stopped it asserting things it had not
checked.

### Added

- Five read modes: `browse` (published articles, with `--tag`), `people` and `person` (the Who axis,
  with the quote where one exists), `topics` and `tags` (the two vocabularies, which are not the
  same thing).
- `communities`, so `--community` has a way to discover valid slugs.
- `--since` / `--until` on `search` and `angles`, mapping to the API's `date_from` / `date_to`. The
  When axis is the only one of the five Ws the server can filter, and it is the axis the `angles`
  intents are about.
- `--offset` on every list mode, so `has_more` is a fact you can act on.
- Newsroom targeting via `NEWS_SITE` and `NEWS_COMMUNITY`. Alaska is the default, not a limit.
- CI (GitHub Actions) across Python 3.9, 3.11 and 3.13. There were tests before this and nothing
  ran them.
- `CONTRIBUTING.md`, `SECURITY.md`, issue and PR templates, `.env.example`.
- Conformance to the [Agent Skills specification](https://agentskills.io/specification), with tests
  asserting its constraints, and `references/verification.md` for provenance the agent does not
  need on every run.

### Changed

- The usage terms printed under every output are now **fetched** from the newsroom's `robots.txt`
  `Content-Signal` (falling back to `llms.txt`) rather than compiled in. Pointed at a second
  newsroom, a constant would have published one newsroom's terms over another's reporting. If the
  terms cannot be read, the output says so and invents nothing.
- `check` reads the platform's own `GET /api/v1/me` reachability block instead of a hand-maintained
  list of unreachable endpoints, and reports whether your key is read-only. It also dropped `rag`
  from its probes, taking a run from about ninety seconds to five.
- `rag` renders its answer and citations instead of dumping raw JSON, and gets a 180s budget against
  its measured 84s latency.
- The env var is `NEWS_DESK_API_KEY`. The old `ALASKA_DESK_API_KEY` still works.
- The skill is `news-desk` and the module is `news_desk.py`, both renamed from `alaska-*`.

### Fixed

- `events` returned only past meetings under a heading saying "upcoming", because it ranked by
  relevance. It reads the date-ranged `GET /calendar` now.
- `clip` could not work at all: the endpoint 302s to an MP4 and the client decoded every response as
  JSON, so the mode died with an uncaught `UnicodeDecodeError`.
- `check --community X` probed Alaska while saying it had checked X.
- A mistyped `--corpus` returned an empty result set, which reads as "nothing has been published
  about this". Corpus names are validated before the request goes out.
- Documented claims that had stopped being true: the rate limit understated by three times, clip
  browsing described as a role gate when no API key of any role reaches it, and a corpus-access
  claim the platform had contradicted months earlier.

## 1.0.0 - 2026-07-25

- Initial extraction of the read-only API client from an internal repository into this one, as the
  `alaska-desk` skill.

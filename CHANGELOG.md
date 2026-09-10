# Changelog

The skill declares a `version` under `metadata` in
[`SKILL.md`](skills/news-desk/SKILL.md). This file is what that number refers to.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Dates are the day the work
landed on `main`.

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

- Initial extraction of the read-only API client from `studio` into its own repository, as the
  `alaska-desk` skill.

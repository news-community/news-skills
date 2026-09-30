---
name: news-desk
description: >-
  Use when someone asks what a local newsroom has published, is about to cover, or has
  reported before: what happened at a public meeting, when the next hearing or comment
  deadline falls, who said something on the record, or what prior coverage exists to cite.
  Reads published articles, meeting transcripts with speakers and timestamps, upcoming civic
  events, a people directory, beats and traceable prior-coverage citations from a Communities
  News newsroom API, alaskanews.com by default. Read-only: it never writes back. Reach for it
  even when the request never says "API" or names the newsroom, as in "has anyone reported on
  this", "when does the assembly next meet", "what did the mayor say about the port", "find
  me what was written before", or "is there a public comment deadline coming up".
license: MIT-0
compatibility: >-
  Python 3.9+, standard library only, no third-party packages. Needs network access to a
  Communities News newsroom (alaskanews.com unless NEWS_SITE says otherwise) and, for most
  modes, that newsroom's own cn_ API key in NEWS_DESK_API_KEY.
allowed-tools: Bash
metadata:
  version: "1.3.0"
  author: Communities News LLC
  homepage: https://communities.news
  repository: news-community/news-skills
  openclaw: {"primaryEnv": "NEWS_DESK_API_KEY", "requires": {"bins": ["python3"]},
    "homepage": "https://communities.news",
    "envVars": [
      {"name": "NEWS_DESK_API_KEY", "required": false, "description": "The newsroom's cn_ API key. digest, topics and tags run without it."},
      {"name": "ALASKA_DESK_API_KEY", "required": false, "description": "Legacy name for NEWS_DESK_API_KEY, still honoured."},
      {"name": "NEWS_SITE", "required": false, "description": "Newsroom origin; defaults to https://alaskanews.com."},
      {"name": "NEWS_COMMUNITY", "required": false, "description": "Community slug; defaults to alaska-news."},
      {"name": "PLATFORM_API_BASE", "required": false, "description": "Overrides the API base derived from NEWS_SITE."}]}
---

# news-desk

> **A read-only research client for the alaskanews.com public API**, for external Alaska
> creators, community journalists, bloggers, and civic writers, to pull published articles,
> meeting transcripts, public events, and prior coverage into **their own** work, under the
> site's stated terms.

**This skill only consumes.** It never submits, edits, or writes back to the platform.
Submitting content into the newsroom is a separate, editor-authenticated workflow that is not
part of this tool. news-desk is for people building on Alaska News reporting from the outside.

---

## What it is, and what it is not

| | |
|---|---|
| **Audience** | external Alaska creators, one per key |
| **Direction** | READ ONLY. No `PATCH` / `PUT` / `DELETE`; its only `POST` is the read-only RAG query. A test enforces this. |
| **Auth** | **your own** `cn_` API key (`NEWS_DESK_API_KEY`), ideally created **read-only**. `digest`, `topics` and `tags` need none. |
| **Output** | rendered markdown by default (paste into your draft), `--json` for raw. Every response carries the site's usage terms. |
| **Newsroom** | alaskanews.com by default, and that is a DEFAULT not a limit: `NEWS_SITE` + `NEWS_COMMUNITY` point it elsewhere. |
| **Runs on** | [`scripts/news_desk.py`](scripts/news_desk.py), Python 3, standard library only, no dependencies. |

**It is not** a content generator. It produces *source material* that you turn into your own
article, script, or post.

---

## Terms (read this before you publish anything from it)

**The terms are read from the newsroom on every run, not compiled in.** The client fetches
`robots.txt`'s `Content-Signal` (the machine-readable location defined by contentsignals.org),
falling back to `llms.txt`. alaskanews.com currently declares:

- **`ai-train=no`** you may not train models on the content.
- **`search=yes`** it may surface in AI-powered search.
- **`ai-input=yes`** you may quote it **with attribution and a backlink**.

That used to be a constant in the source. It is fetched now for two reasons. A newsroom can change
its stance and a constant would keep reciting the old one. And pointed at a **different** newsroom, a
constant would have printed Alaska's terms over somebody else's reporting, which for a tool whose
whole ethic is "the attribution is the consideration" is the worst thing in the file. **If the terms
cannot be read, the output says so and invents nothing.**

Every mode prints that reminder under its output. It is not decoration: the person running this
is republishing someone else's reporting, and the attribution + backlink is the consideration
for using it. If you generate content from an article, name Alaska News and link the source.

---

## Auth: your own key, and only what it reaches

Create a key at `alaskanews.com/profile/settings`. **Tick "Read-only" when you create it.**

That checkbox is the single most useful thing on this page for you. This client never writes, but
that is a promise made by code you would have to read; a read-only key is enforced by the server,
which rejects every `POST`/`PUT`/`PATCH`/`DELETE` before a handler runs. Same reach for everything
here, and a key that cannot damage the newsroom even if you leak it, paste it into the wrong
terminal, or hand it to an agent that turns out to be more creative than you wanted. The one
exception is `rag`, whose read-only query is an HTTP `POST`, so tick read-only only if you can live
without that mode.

Then either export the key (works from anywhere):

```bash
export NEWS_DESK_API_KEY=cn_...
```

or drop it in a gitignored `.env.local` next to the script (or in your project root):

```bash
echo 'NEWS_DESK_API_KEY=cn_...' >> scripts/.env.local
```

Access is tiered on the platform side, and your key may not reach everything.

| Mode | Reach | Note |
|---|---|---|
| `digest` | **public** | recent-stories markdown, no key. Re-verified 2026-09-09 |
| `search` | **any valid key** | six corpora; `external_documents` and `social_post` are editor/admin only |
| `angles` | **any valid key** | discovery scaffold; runs on the `/search` surface |
| `article` | **public by URL/slug**, keyed by id | the id form returns the richer record |
| `transcript` | **any valid key** | full meeting transcript with speakers + timestamps |
| `events` | **any valid key** | `GET /calendar`, date-ranged. Re-verified 2026-09-09 |
| `communities` | **any valid key** | the slugs `--community` accepts |
| `browse` | **any valid key** | the published article list; `--tag` for one beat |
| `people` / `person` | **any valid key** | speaker directory, and one actor's coverage |
| `topics` / `tags` | **public** | beats ranked by coverage, and the subject vocabulary. Verified 2026-09-29 |
| `rag` | **role-gated** | an external consumer key saw 403 on 2026-07-23; slow (~1-2 min) where allowed |
| `clip` | **id only** | resolves a known id to its public MP4 URL. You cannot BROWSE clips: see below |

**Some endpoints are not role gates, and no upgrade reaches them.** A set of routes authenticate by
**cookie session only**: they read the browser's Supabase session rather than the API-key path, so
they refuse *every* `cn_` key, including an admin's. `GET /clips` (browse) and
`GET /transcripts/search` are the two you are most likely to want; `GET /transcript/<id>/speakers`
is a third, which is why you can read every word of a meeting and not learn who said it.

**You no longer have to take that list from this file.** As of 2026-09-09 the platform answers it:
`GET /api/v1/me` returns a `reachability` block derived from its own router, and `check` renders it.
It separates `session_auth_only` (nothing to request) from `requires_role` (a membership you could
be granted), and those endpoints now return **403** with `error: session_auth_only` and a remedy,
rather than a bare 401 indistinguishable from a bad key. This client used to carry that list by
hand; it does not any more, which is the point.

Use `search --corpus transcripts` instead of `transcripts/search`, and get clip ids from `search` or
an article.

**How much weight these rows carry.** They come from two passes with two different keys, and only
one of them tells you about external reach. Read
[`references/verification.md`](references/verification.md) before changing any claim here about what
a key reaches. Run `check` for the only answer that is about *your* key.

**Run `check` first.** It asks the server what your key reaches, and probes a handful of endpoints
directly on top of that. It reports whether your key is **read-only**, your role per community, the
endpoints no key reaches and the ones a membership would unlock. It takes about five seconds:

```bash
python3 scripts/news_desk.py check
```

---

## Modes

```bash
python3 scripts/news_desk.py check                               # what does MY key reach? (run first)
python3 scripts/news_desk.py digest                              # recent stories (no key)
python3 scripts/news_desk.py browse --sort new                   # what has been PUBLISHED (no query)
python3 scripts/news_desk.py search "port of alaska settlement"  # --corpus, --since, --until
python3 scripts/news_desk.py angles "port of alaska" --intent track  # discovery: fix 2 Ws, expand the rest
python3 scripts/news_desk.py article <id | slug | url>           # full article
python3 scripts/news_desk.py transcript <source-id>              # meeting transcript
python3 scripts/news_desk.py events                              # what is coming UP (next 30 days)
python3 scripts/news_desk.py rag "public comment deadlines"      # answer + traceable citations
python3 scripts/news_desk.py clip <clip-id>                      # resolve a known clip id to its MP4 URL
python3 scripts/news_desk.py communities                         # slugs valid for --community
python3 scripts/news_desk.py people "dunleavy"                   # the Who axis: named speakers
python3 scripts/news_desk.py person <person-id>                  # one actor + the coverage they appear in
python3 scripts/news_desk.py topics                              # the beats, ranked by coverage
python3 scripts/news_desk.py tags "port" --category organization # the subject vocabulary
```

**`topics` is the beats; `tags` is the whole vocabulary.** `topics` lists the topic-category tags
(Government, Infrastructure, Health...) ranked by articles published, each naming its parent; counts
do not roll up into the parent. `tags` searches every tag: `organization`, `topic` or `location`. A
slug from either is what `browse --tag` takes. Both are public. (`topics` read the retired `/topics`
endpoint until 1.3.0, whose counts were all zero.)

**`browse` vs `search`.** `search` answers "what do you have about X". `browse` answers "what has
been published", which is the question you ask before you know what X is. `--sort` takes
`new`/`hot`/`top`/`popular`/`timeline`/`alphabetical`, and `--tag <slug>` lists a single beat.

## Pointing it at another newsroom

The platform behind alaskanews.com is multi-community by design: it maps a host to a community, and
this client already took `--community` and a base-URL override. What kept it Alaska-only was four
hard-coded constants, not its structure. They are settings now:

```bash
export NEWS_SITE=https://<host>        # the newsroom; the API base is derived from it
export NEWS_COMMUNITY=<slug>           # default for --community
export NEWS_DESK_API_KEY=cn_...        # your key (the old ALASKA_DESK_API_KEY still works)
```

**alaskanews.com remains the default**, and today it is the only newsroom live on this platform, so
that default is also the whole of production. Nothing about a market is compiled in: the terms, the
`See also` links, the reachability report and every request path follow whatever `NEWS_SITE` and
`--community` say. `check` prints which newsroom and community it is reporting on, because a
reachability report that does not name its subject is the kind of thing you read wrongly once.

**Paging.** Every list mode takes `--limit` and `--offset`, and prints `showing 1-20 of 340` with the
next `--offset` when there is more. A page that quietly drops the rest is how you conclude there are
three of something when there are ninety.

Add `--json` for raw responses, `--community <slug>` to target a community other than `alaska-news`
(run `communities` to see which slugs exist).

**The When axis: `--since` / `--until`.** `search` and `angles` both take `--since YYYY-MM-DD` and
`--until YYYY-MM-DD`, which map to the API's `date_from` / `date_to` on the articles corpus. This is
the only one of the five Ws the server can filter on, and it is the axis the `angles` intents talk
about holding or expanding, so `--intent precedent --until 2020-01-01` is how you actually ask the
question that intent describes. Result lines carry the date for the same reason: you cannot check
the two-axis corroboration rule below against results whose dates are hidden.

**`events` is forward-looking.** It reads `GET /calendar`, whose window starts now and runs 30 days
(`--days` to change it, `--type meeting|public_notice|community_event|class` to narrow). It used to
run `search --corpus events`, which ranks by relevance rather than date: on 2026-09-09 that returned
15 of 15 meetings **already past** under a heading saying "upcoming", which is the one thing a
hearing listing must never do. To search events by relevance across all time, including past ones,
use `search "<q>" --corpus events`. `/calendar` has no full-text parameter, so a query argument to
`events` filters the window client-side on title and location.

---

## HATEOAS: every output points onward

The API and this client both follow a HATEOAS discipline (every response tells you where to go
next), so you never hit a dead end or need an external map:

- **It consumes the server's.** API responses carry a `next_steps` array; rendered output surfaces
  it ("The API points onward to..."), and `--json` passes it through in the payload for machine
  consumers.
- **It emits its own.** Every mode ends with **Next steps** (prioritized, each with the *why*,
  capped at five), the **Related modes**, and a **See also**. The suggestions are *state-driven*:
  with no key, the top suggestion is to get one; after a `search`, they point at opening a result
  or pulling its quotes.
- **Errors carry recovery**, not just a status: a 403 explains *why* (clips/some corpora need an
  editor role) and *what to do* (run `check`, stay on articles/transcripts).

`--json` is the machine surface and stays valid JSON: the prose next-steps and the license reminder
are omitted there, because a machine reads `next_steps` from the payload itself.

---

## Working the story: the five Ws (the `angles` mode)

Treat Who, What, When, Where, Why as five independent axes. The investigative method has two modes,
and they land on opposite sides of this tool's read-only line:

- **Matching** (ranking which stories are genuinely related) is axis-weighted similarity. That is
  the **server's** job; it happens inside `/search` and `/rag/query`. This client does not re-do it.
- **Discovery** (fix two Ws, expand the rest) is a workflow of chained searches, and that is exactly
  what a sourcing tool can scaffold. It is what `angles` runs.

`angles --intent` names which two Ws you fix:

| Intent (the two Ws it fixes) | `--intent` | What runs underneath |
|---|---|---|
| similar stories / historical precedent (What + Why) | `similar`, `precedent` | search articles, then `rag` holds What+Why and varies When |
| track a company or agency (Who + What) | `track` | search articles + transcripts for the actor; expand When |
| local coverage (Where + What) | `local` | `--community <slug>` **is** the Where axis |
| same narrative angle (Why + What) | `angle` | `rag` people/quotes: who is deploying the framing |

`angles "<seed>" --intent <intent>` runs **one** framed level (a single `/search` across the corpora
that intent implies) and hands back the nested-expansion plan as Next steps, so you drive the depth,
not the key's rate limit.

**The one rule to carry:** a match must agree on **two** axes before you trust it. A hit that shares
only the topic is one-axis agreement (an anecdote); a hit that shares the topic **and** the actor is
corroboration. That is why "cite a specific article, never a generic phrase" below is not fussiness:
a single-keyword match is not yet a citation.

---

## Method: internal before external

Before you reach for a general web search, ask whether Alaska News has already covered this. Run
`search` first. If the answer is in the corpus, you save an external lookup and you can cite specific
prior reporting; if it isn't, you now know it's a genuine gap. The reorder is the value.

When you cite "previously reported," cite a **specific** article (its id or URL), never a generic
phrase with no matching published story behind it.

---

## Honest limits (as of 2026-09-09)

- **What was verified, and with which key.** Two passes, 2026-07-23 with a real external key and
  2026-09-09 with an elevated one, which prove different things. The detail is in
  [`references/verification.md`](references/verification.md); `check` is the only answer about
  *your* key.
- **`rag` is role-gated and slow.** An external key saw 403. Where it is allowed, it synthesizes an
  answer over retrieved passages and measured **84 seconds** on 2026-09-09, so the client gives it a
  180s budget; a timeout is now reported as a timeout, not as "unreachable". Quote its **citations**
  (each carries a verbatim excerpt and a url), never its synthesized paragraph: the paragraph is a
  summary of someone else's reporting and is not itself attributable.
- **You cannot browse clips or use `/transcripts/search` with any key.** Both are cookie-session
  endpoints, not role gates. See the auth section above.
- **`angles`** rides the `/search` surface (one framed GET per run), so any valid key that reaches
  `search` reaches it. Its suggested `rag` follow-ups inherit rag's role limit.
- **Rate limits.** 300 reads/min per user (and 180 writes/min, which nothing here uses). A 429 is a
  back-off, not a permission problem.
- **`--json` is the stable machine surface.** Renderers fall back to raw JSON if a payload shape ever
  changes, and `--json` always gives you the untouched payload.
- **This is not a submission tool.** If you want your work published *on* Alaska News, that is a
  newsroom workflow, not this.

### Not covered here, deliberately

**`GET /feed` is not wrapped.** It returns byte-identical results to `browse --sort new` (compared
directly on 2026-09-09) and accepts no `community` parameter, so for a consumer targeting a community
it is the same mode with strictly less reach. A test pins its absence, so anyone adding it later has
to delete that test and read this first.

**`person` reports "appears in", not "quoted in", and the distinction is load-bearing.**
`/persons/<id>/articles` returns a UNION: articles where an attribution matched the person's name,
and articles structurally linked to them. Only the first kind carries a verbatim excerpt. Rows with a
quote are marked `quoted (Nx)`; when a whole page has none, the client says so, because "Dunleavy
appears in this piece" and "Dunleavy said this in this piece" are different claims and only one of
them is quotable. Open the article and confirm before you attribute words to anyone.

Everything else on the read surface that a consumer key reaches is now wrapped. What remains
unwrapped is write-side or editor-only, and out of scope by design.

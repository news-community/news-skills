---
name: alaska-desk
description: >-
  Read-only research client for the alaskanews.com public API. Pull published Alaska News
  articles, meeting transcripts, public events, and prior coverage into your own work, under
  the site's stated terms. For external Alaska creators: community journalists, bloggers, and
  civic writers. Use when you want to build on Alaska News reporting, cite prior coverage, or
  work a story across the five Ws.
---

# alaska-desk

> **A read-only research client for the alaskanews.com public API**, for external Alaska
> creators, community journalists, bloggers, and civic writers, to pull published articles,
> meeting transcripts, public events, and prior coverage into **their own** work, under the
> site's stated terms.

**This skill only consumes.** It never submits, edits, or writes back to the platform.
Submitting content into the newsroom is a separate, editor-authenticated workflow that is not
part of this tool. alaska-desk is for people building on Alaska News reporting from the outside.

---

## What it is, and what it is not

| | |
|---|---|
| **Audience** | external Alaska creators, one per key |
| **Direction** | READ ONLY. No `PATCH` / `PUT` / `DELETE`; its only `POST` is the read-only RAG query. A test enforces this. |
| **Auth** | **your own** `cn_` API key (`ALASKA_DESK_API_KEY`). `digest` needs none. |
| **Output** | rendered markdown by default (paste into your draft), `--json` for raw. Every response carries the site's usage terms. |
| **Runs on** | [`scripts/alaska_desk.py`](scripts/alaska_desk.py), Python 3, standard library only, no dependencies. |

**It is not** a content generator. It produces *source material* that you turn into your own
article, script, or post.

---

## Terms (read this before you publish anything from it)

alaskanews.com declares its own machine-usage terms at `alaskanews.com/llms.txt`:

- **`ai-train=no`** you may not train models on the content.
- **`search=yes`** it may surface in AI-powered search.
- **`ai-input=yes`** you may quote it **with attribution and a backlink**.

Every mode prints that reminder under its output. It is not decoration: the person running this
is republishing someone else's reporting, and the attribution + backlink is the consideration
for using it. If you generate content from an article, name Alaska News and link the source.

---

## Auth: your own key, and only what it reaches

Create a key at `alaskanews.com/profile/settings`, then either export it (works from anywhere):

```bash
export ALASKA_DESK_API_KEY=cn_...
```

or drop it in a gitignored `.env.local` next to the script (or in your project root):

```bash
echo 'ALASKA_DESK_API_KEY=cn_...' >> scripts/.env.local
```

Access is tiered on the platform side, and your key may not reach everything. The table below is
**live-verified against a real external `cn_` key (2026-07-23)**, so it reflects what an external
consumer actually gets, not what the docs imply:

| Mode | This external key got | Note |
|---|---|---|
| `digest` | **OK** | public recent-stories markdown, no key |
| `search` | **OK** | multi-corpus; a plain external key even saw external-documents + social-post here |
| `angles` | **OK (via search)** | discovery scaffold; runs on the verified `/search` surface |
| `article` | **OK** | URL/slug needs no key; `id` is keyed |
| `transcript` | **OK** | full meeting transcript with speakers + timestamps |
| `events` | **OK** | via the events search corpus |
| `rag` | **403 forbidden** | prior-coverage RAG needs a higher role than an external consumer key; expect this to be unavailable to you |
| `clip` | **no access** | browsing the clip library needs an editor role external keys lack; only a KNOWN clip id streams (public) |

So the reliable external surface is **digest, search, angles, article, transcript, events**. `rag`
and `clip` are role-gated and most external keys will not reach them.

**Run `check` first.** It probes each surface and tells you what your key actually reaches, before
you build a workflow on something it can't touch:

```bash
python3 scripts/alaska_desk.py check
```

---

## Modes

```bash
python3 scripts/alaska_desk.py digest                              # recent stories (no key)
python3 scripts/alaska_desk.py search "port of alaska settlement"  # --corpus articles,transcripts,events
python3 scripts/alaska_desk.py angles "port of alaska" --intent track  # discovery: fix 2 Ws, expand the rest
python3 scripts/alaska_desk.py article <id | slug | url>           # full article
python3 scripts/alaska_desk.py transcript <source-id>              # meeting transcript
python3 scripts/alaska_desk.py events "assembly"                   # upcoming hearings/meetings
python3 scripts/alaska_desk.py rag "public comment deadlines"      # quotes + people + prior coverage
python3 scripts/alaska_desk.py clip <clip-id>                      # stream a known clip
```

Add `--json` for raw responses, `--community <slug>` to target a community other than
`alaska-news`.

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

## Honest limits (as of 2026-07-23)

- **Live-verified (2026-07-23).** Run against a real external `cn_` key: `digest`, `search`, `article`,
  `transcript`, and `events` all return and render correctly. `rag` returned 403 and `clip` browse is
  role-gated, so both are unavailable to a plain external key. The renders fall back to raw JSON if a
  shape ever changes; `--json` always gives you the raw payload.
- **`rag` and `clip` need a higher role.** An external consumer key reaches the read surface
  (articles/transcripts/events/search) but not the RAG endpoint or the clip library. Run `check` to
  confirm your own key's reach.
- **`angles`** rides the already-verified `/search` surface (one framed GET per run), so any valid key
  that reaches `search` reaches it. Its suggested `rag` follow-ups inherit rag's role limit above.
- **This is not a submission tool.** If you want your work published *on* Alaska News, that is a
  newsroom workflow, not this.

---

## Development

```bash
pip install pytest
python3 -m pytest scripts/test_alaska_desk.py -q   # offline; no key, no network
```

The tests cover arg parsing, the read-only contract (no write verbs; the only POST is the read-only
RAG query), the HATEOAS footer, and the five-Ws intent grid. Only the single live API call per mode is
untestable without a key, which is why it is kept as thin as possible.

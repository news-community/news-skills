# Alaska News: public API toolkit

Open tools for building on [Alaska News](https://alaskanews.com) reporting.

This repo is for **external Alaska creators** (community journalists, bloggers, civic writers) who
want to pull published articles, meeting transcripts, public events, and prior coverage from the
alaskanews.com public API into their own work, under the site's stated terms.

Everything here is **read-only**. It consumes the public API; it does not submit, edit, or write
back to the platform.

## What's inside

| Skill | What it does |
|-------|--------------|
| [`skills/alaska-desk`](skills/alaska-desk/SKILL.md) | A read-only research client over the alaskanews.com public API. 15 modes: `digest` and `browse` (what's published), `search` and `angles` (five-Ws discovery), `article`, `transcript`, `events` (upcoming meetings, hearings and comment deadlines), `people` and `person` (the Who axis), `topics` and `tags` (beats and subjects), `rag` (answer plus traceable citations), `clip`, `communities`, and a `check` that reports what your key can reach. |

## Quickstart

```bash
# 1. Recent stories, no key needed:
python3 skills/alaska-desk/scripts/alaska_desk.py digest

# 2. Get a key at alaskanews.com/profile/settings -- TICK "READ-ONLY" -- then:
export NEWS_DESK_API_KEY=cn_...

# 3. See what your key reaches:
python3 skills/alaska-desk/scripts/alaska_desk.py check

# 4. Search, then work a story across the five Ws:
python3 skills/alaska-desk/scripts/alaska_desk.py search "port of alaska settlement" --since 2026-01-01
python3 skills/alaska-desk/scripts/alaska_desk.py angles "port of alaska" --intent track

# 5. What can you still show up to, or still file comment on?
python3 skills/alaska-desk/scripts/alaska_desk.py events --days 14

# 6. Work an actor, or a beat:
python3 skills/alaska-desk/scripts/alaska_desk.py people "dunleavy"
python3 skills/alaska-desk/scripts/alaska_desk.py browse --tag transportation
```

**Tick "Read-only" when you create the key.** Nothing here writes, but a read-only key is enforced
by the server rather than promised by code you would have to read: it reaches everything in this
toolkit and cannot damage the newsroom if it leaks. (The one exception is `rag`, whose read-only
query is an HTTP `POST`.)

Python 3, standard library only. No dependencies to install for the tool itself. Verified on 3.11,
3.13 and 3.14; CI also runs 3.9, the intended floor. See
[`skills/alaska-desk/SKILL.md`](skills/alaska-desk/SKILL.md) for the full guide.

## Other newsrooms

alaskanews.com is the **default**, not a limit. The platform is multi-community by design, so
`NEWS_SITE` and `NEWS_COMMUNITY` point the same tool at another newsroom on it, and the usage terms
are read from whichever newsroom you point at rather than baked in. Today Alaska is the only one
live, so this is a door rather than a road.

## Tests

```bash
pip install pytest
python3 -m pytest skills/alaska-desk/scripts/test_alaska_desk.py -q
```

Offline: no key and no network required. CI runs them on every push, across Python 3.9-3.13.

## Using it as an agent skill

`skills/alaska-desk/` is a self-contained [agent skill](skills/alaska-desk/SKILL.md): a `SKILL.md`
describing when and how to use it, plus the script it runs. Point your agent at the skill directory,
or run the CLI directly as above.

## Terms

Content from alaskanews.com is governed by the site's own machine-usage terms at
`alaskanews.com/llms.txt`: **you may not train models on it (`ai-train=no`)**, and **you may quote it
with attribution and a backlink (`ai-input=yes`)**. Every command prints that reminder. If you
publish anything sourced here, name Alaska News and link the source. Those content terms are separate
from this repository's code license below.

## License

The code in this repository is released under the [MIT License](LICENSE). This covers the tool, not
the reporting it retrieves (see Terms above).

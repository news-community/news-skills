# News Skills

Open, read-only tools for building on community newsroom reporting. Alaska News is the
newsroom they point at today, and not the only one they can.

## The problem

A community journalist who wants to build on local reporting that already exists has to
re-find it by hand: scroll the site, guess at search terms, and hope they remember which
meeting a quote came from. Upcoming hearings live on a different page from the coverage of
the last one. And the terms under which any of it can be quoted sit in a `robots.txt` that
nobody reads.

## What this does about it

One read-only client over a newsroom's public API, with fifteen modes covering what is
published, what is coming up, who said it, and what was reported before. Every output ends
with where to go next, and carries the newsroom's **own** machine-readable usage terms,
fetched at run time rather than compiled in, so the tool cannot print one newsroom's terms
over another's reporting.

Everything here is **read-only**. It consumes the public API; it does not submit, edit, or
write back to the platform.

| Skill | What it does |
|-------|--------------|
| [`skills/news-desk`](skills/news-desk/SKILL.md) | A read-only research client. 15 modes: `check` (what your key reaches), `digest` and `browse` (what's published), `search` and `angles` (five-Ws discovery), `article`, `transcript`, `events` (upcoming meetings, hearings and comment deadlines), `people` and `person` (the Who axis), `topics` and `tags` (beats and subjects), `rag` (answer plus traceable citations), `clip`, and `communities`. |

## Install

This is an [Agent Skills](https://agentskills.io) skill, so installing it means putting the
skill directory where your agent looks for skills.

**Claude Code**, all skills in this repo:

```bash
git clone https://github.com/news-community/news-skills.git ~/.claude/skills/news-skills
```

**Claude Code**, just this one skill, symlinked so `git pull` keeps it current:

```bash
git clone https://github.com/news-community/news-skills.git ~/src/news-skills
ln -s ~/src/news-skills/skills/news-desk ~/.claude/skills/news-desk
```

**Other agents**: point yours at `skills/news-desk/`, or skip the agent entirely and run the
CLI directly as below. It is a plain Python program and does not need an agent to be useful.

If you already have a skill named `news-desk`, install this one under a different directory
name. The frontmatter `name` is what most clients key on, so two skills sharing it is the
thing to avoid, not two directories.

Then set a key:

```bash
cp .env.example .env.local     # then edit it
# or, from anywhere:
export NEWS_DESK_API_KEY=cn_...
```

## Quickstart

```bash
# 1. Recent stories, no key needed:
python3 skills/news-desk/scripts/news_desk.py digest

# 2. Get a key at alaskanews.com/profile/settings -- TICK "READ-ONLY" -- then:
export NEWS_DESK_API_KEY=cn_...

# 3. See what your key reaches:
python3 skills/news-desk/scripts/news_desk.py check

# 4. Search, then work a story across the five Ws:
python3 skills/news-desk/scripts/news_desk.py search "port of alaska settlement" --since 2026-01-01
python3 skills/news-desk/scripts/news_desk.py angles "port of alaska" --intent track

# 5. What can you still show up to, or still file comment on?
python3 skills/news-desk/scripts/news_desk.py events --days 14

# 6. Work an actor, or a beat:
python3 skills/news-desk/scripts/news_desk.py people "dunleavy"
python3 skills/news-desk/scripts/news_desk.py browse --tag transportation
```

**Tick "Read-only" when you create the key.** Nothing here writes, but a read-only key is
enforced by the server rather than promised by code you would have to read: it reaches
everything in this toolkit and cannot damage the newsroom if it leaks. (The one exception is
`rag`, whose read-only query is an HTTP `POST`.) `check` reports which kind you hold.

Python 3, standard library only. No dependencies to install for the tool itself. Verified on
3.11, 3.13 and 3.14; CI also runs 3.9, the intended floor. See
[`skills/news-desk/SKILL.md`](skills/news-desk/SKILL.md) for the full guide.

## Built on the Agent Skills standard

`skills/news-desk/` follows the [Agent Skills specification](https://agentskills.io/specification):
a directory containing a `SKILL.md` of YAML frontmatter plus Markdown instructions, with an
optional `scripts/` beside it.

```
skills/news-desk/
  SKILL.md           # required: frontmatter + instructions
  scripts/           # optional: the client and its tests
```

The format was originally developed by Anthropic and released as an open standard, and has
been adopted by a growing number of agentic clients; the site's Client Showcase lists them.
Writing to the standard rather than to one client is the point: the same directory works
wherever the standard is read.

The frontmatter here uses the spec's own fields, including `license`, `compatibility` and
`allowed-tools`, and puts version, author, homepage and repository under `metadata`, which is
where the spec puts arbitrary extras. Tests assert the spec's constraints (name shape and
length, description length, metadata being a flat string map) so the file cannot drift out of
conformance quietly.

## Standalone

**This repository is fully standalone.** It has no dependency on any private repository, no
build step, no package to install, and no shared library. The client is a single Python file
using only the standard library, and its tests run with `pytest` and nothing else.

It is developed inside a private monorepo, which is an implementation detail of how it is
maintained and not a requirement for using it. If you cloned this and it works, it works.

## Other newsrooms

alaskanews.com is the **default**, not a limit. The platform is multi-community by design, so
`NEWS_SITE` and `NEWS_COMMUNITY` point the same tool at another newsroom on it, and the usage
terms are read from whichever newsroom you point at rather than baked in. Today Alaska is the
only one live, so this is a door rather than a road.

## Tests

```bash
pip install pytest
python3 -m pytest skills/news-desk/scripts/test_news_desk.py -q
```

Offline: no key and no network required. CI runs them on every push, across Python 3.9-3.13.
They cover the client, and also `SKILL.md` itself: its conformance to the Agent Skills spec,
and that every mode the CLI registers is documented and every mode documented exists.

## Terms

Content from a newsroom is governed by that newsroom's own machine-usage terms, which this
tool reads from its `robots.txt` `Content-Signal` (falling back to `llms.txt`) on every run
rather than assuming them. alaskanews.com currently declares **`ai-train=no`** (you may not
train models on it) and **`ai-input=yes`** (you may quote it with attribution and a backlink).
Every command prints whatever the newsroom actually declares, and says so plainly if it cannot
read them. If you publish anything sourced here, name the newsroom and link the source. Those
content terms are separate from this repository's code license below.

## License

The code in this repository is released under the [MIT License](LICENSE). This covers the
tool, not the reporting it retrieves (see Terms above).

# Alaska News — public API toolkit

Open tools for building on [Alaska News](https://alaskanews.com) reporting.

This repo is for **external Alaska creators** (community journalists, bloggers, civic writers) who
want to pull published articles, meeting transcripts, public events, and prior coverage from the
alaskanews.com public API into their own work, under the site's stated terms.

Everything here is **read-only**. It consumes the public API; it does not submit, edit, or write
back to the platform.

## What's inside

| Skill | What it does |
|-------|--------------|
| [`skills/alaska-desk`](skills/alaska-desk/SKILL.md) | A read-only research client over the alaskanews.com public API: `digest`, `search`, `angles` (five-Ws discovery), `article`, `transcript`, `events`, `rag`, `clip`, and a `check` that reports what your key can reach. |

## Quickstart

```bash
# 1. Recent stories, no key needed:
python3 skills/alaska-desk/scripts/alaska_desk.py digest

# 2. Get a key at alaskanews.com/profile/settings, then:
export ALASKA_DESK_API_KEY=cn_...

# 3. See what your key reaches:
python3 skills/alaska-desk/scripts/alaska_desk.py check

# 4. Search, then work a story across the five Ws:
python3 skills/alaska-desk/scripts/alaska_desk.py search "port of alaska settlement"
python3 skills/alaska-desk/scripts/alaska_desk.py angles "port of alaska" --intent track
```

Python 3, standard library only. No dependencies to install for the tool itself. See
[`skills/alaska-desk/SKILL.md`](skills/alaska-desk/SKILL.md) for the full guide.

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

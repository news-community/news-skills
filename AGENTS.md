# AGENTS.md: News Skills

> Onboarding for AI coding agents. If you are a human, welcome: the same applies to you, and
> [CONTRIBUTING.md](CONTRIBUTING.md) has the longer version.

This repository holds one agent skill, **Local News API** (`skills/local-news-api/`): a read-only
client for a local newsroom's public API on the Communities News platform. The worked example
everywhere is **Alaska News**: site `https://alaskanews.com`, API `https://alaskanews.com/api/v1`,
spec `https://alaskanews.com/api/v1/openapi.json`. It is published on ClawHub as
[`local-news-api`](https://clawhub.ai/alaskanews/skills/local-news-api).

## Layout

```
skills/local-news-api/
  SKILL.md                    the skill: YAML frontmatter + instructions an agent loads every run
  agents/openai.yaml          the name and summary a skill catalog shows (not the agent's trigger)
  references/verification.md  loaded on demand, not on every run
  scripts/local_news_api.py   the client: one file, Python 3.9+, standard library only
  scripts/test_local_news_api.py   the offline suite (kept out of the registry bundle)
  .clawhubignore              what a registry does not receive
```

## Setup, run, test

There is nothing to install for the client. Tests need pytest only.

```bash
python3 skills/local-news-api/scripts/local_news_api.py digest    # recent stories, no key
python3 skills/local-news-api/scripts/local_news_api.py topics    # beats ranked by coverage, no key
pip install pytest
python3 -m pytest skills/local-news-api/scripts/test_local_news_api.py -q
```

The suite is **offline**: no key and no network. One test needs a real key and skips without it.
CI runs the suite on Python 3.9, 3.11 and 3.13 and must pass before a pull request merges. Read
the count from pytest's own output; do not copy a number from a document.

## Rules that the tests enforce

Break one of these and the suite fails, deliberately.

- **Read-only.** No `PATCH`, `PUT` or `DELETE`, and the only `POST` is `/rag/query`, which reads.
  A test reads the source, and CI greps for it separately.
- **Standard library only.** The install story for a community journalist is copy a folder and
  run it. A dependency needs a very strong argument.
- **`SKILL.md` is a spec document** ([agentskills.io](https://agentskills.io/specification)):
  `name` lowercase-and-hyphens matching the folder, `description` under 1,024 characters,
  `metadata` a flat string map except the one `openclaw` object, under 500 lines and about 5,000
  tokens, and every relative link staying inside the skill folder (an installed copy has nothing
  else). Trim into `references/` rather than raising the budget.
- **Mode parity, both directions.** A mode added to the CLI must appear in `SKILL.md`'s Modes
  block and in `README.md`, and a mode documented there must exist.
- **Declare every environment variable the client reads** under `metadata.openclaw.envVars` in
  `SKILL.md`. Registries flag an undeclared read; a test flags it first, in both directions.
- **The key goes only where it buys something.** Public endpoints send no `Authorization`
  header. A `.env` in the current directory may supply the key but never `NEWS_SITE` or
  `PLATFORM_API_BASE`, because that directory belongs to whatever project the skill runs in.
- **Usage terms are read from the newsroom on every run**, never compiled in, and when they
  cannot be read the output says so.
- **The User-Agent is `<name>/<version>`** from the frontmatter, checked by a test.

## Rules that no test can enforce

- **Verify against the live API**, and say when and with which kind of key. An elevated key
  proves an endpoint exists; only an ordinary key proves reach.
- **Do not print a number the data does not support.** A zero that means "not populated" reads as
  "nothing exists".
- **A fix lands with the test that would have caught it**, and that test is shown failing without
  the fix before it is trusted.
- **No em dashes** in prose, comments or commit messages. Use commas, colons, parentheses or two
  sentences.

## Releases

A release bumps `metadata.version` in `SKILL.md` (the User-Agent follows it) and adds a
`CHANGELOG.md` entry. **Publishing to ClawHub is done by the maintainers. Do not publish, rename
or delete anything on a registry**, even when you have the credentials to.

## Security

Never commit a key; `.env` and `.env.local` are git-ignored. Report a vulnerability privately
through the Security tab ("Report a vulnerability"), as [SECURITY.md](SECURITY.md) describes, not in
a public issue.

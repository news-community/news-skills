# Contributing

Thanks for looking. This repo shares tools that external creators can point at a Communities News
newsroom API, alaskanews.com by default. Contributions are welcome, with one hard rule and one
habit.

## The hard rule: this stays read-only

`skills/local-news-api` is a **consumer** client. It must never `PATCH`, `PUT` or `DELETE`, and its
only `POST` is the read-only `/rag/query`. Two things enforce that, and a change that trips either
will not be merged:

- `TestReadOnlyContract` in the test suite, which reads the source and fails on a write verb.
- A grep in CI, which runs even if the module fails to import (a test that cannot load is a test
  that cannot fail).

Publishing *into* the newsroom is a separate, editor-authenticated workflow. It does not belong
here, however convenient it would be.

## The habit: verify against the live API, and date it

This client consumes a platform that changes without telling us. Most of the defects found in the
2026-09-09 audit were not logic errors: they were claims that had quietly stopped being true.

So if you add or change a mode, or write anything about what an endpoint returns:

1. **Run it against the live API** and say so in the PR, with the date.
2. **Say which key you used.** "Works with my key" and "works with an external consumer key" are
   different claims, and only the second one describes this repo's audience. An elevated key can
   confirm that an endpoint exists and returns a given shape; it cannot confirm reach.
3. **Prefer a renderer that degrades.** Every mode falls back to raw JSON if a payload shape
   changes, and `--json` always returns the untouched payload. Keep it that way.
4. **Do not print a number the data does not support.** The retired `/topics` endpoint returned
   `article_count: 0` for every beat; rendering that as "0 articles" would have read as "no coverage
   exists", which was false. It was suppressed with the reason, and `topics` now reads topic tags,
   whose counts are real. The same goes for a filter the server silently ignores: `tags` says so
   rather than print the unfiltered list under a filtered heading. The same reasoning applies to an empty result set from a mistyped
   corpus, which is why corpus names are validated before the request goes out.

## Running the tests

```bash
pip install pytest
python3 -m pytest skills/local-news-api/scripts/test_local_news_api.py -q
```

Offline: no key, no network. CI runs them on Python 3.9, 3.11 and 3.13.

A new mode needs, at minimum:

- a test that it is a GET (`TestReadSurfaceCoverage`),
- a next-steps entry so it is not a dead end (`TestHateoasEmitted` will fail otherwise),
- a rendering test,
- **a line in `SKILL.md`'s Modes block and a mention in the README.** Parity is enforced in both
  directions, so a mode you add without documenting fails the suite, and so does a mode you
  document without adding. That check exists because `check` had already gone missing from the
  Modes block and nothing noticed.

If you fix a defect, add the test that would have caught it, and check that the test actually fails
without your fix.

## A test that was wrong first, kept as a warning

One SKILL.md check scanned for write verbs and called any line containing one a contradiction of the
read-only contract. It fired immediately on a sentence describing the *server* rejecting writes,
which is the promise being kept, not broken. An extractor that cannot tell an explanation from an
advertisement reports the fix as the defect.

It asserts the positive claim now, and the code-side contract is enforced separately by reading the
source rather than the prose. Worth knowing before you write the next prose-scanning check, because
this repo is mostly prose about a program and the temptation recurs.

## SKILL.md is a spec document, and the tests treat it as one

`skills/local-news-api/SKILL.md` follows the [Agent Skills
specification](https://agentskills.io/specification), and `TestSkillMdMeetsTheSpec` asserts its
constraints: `name` lowercase-and-hyphens under 64 characters, `description` non-empty and under
1024, `compatibility` under 500, `metadata` a flat map of strings to strings, and a declared
`license` that matches the bundled `LICENSE` file.

**One metadata key is an object, deliberately.** `metadata.openclaw` declares the environment
variables the client reads, for skill registries such as ClawHub, whose security analysis flags a
skill that reads a variable it does not declare. Registries read that key only as an object, so it
is the single exception to the flat map, and `TestRegistryMetadata` holds it in both directions:
**if you make the client read a new environment variable, declare it there**, or the suite fails.
The listing a registry shows (display name and short summary) lives in
`skills/local-news-api/agents/openai.yaml`, not in `SKILL.md`: the `description` field is what an agent
reads to decide when to use the skill, and it stays written for that job.

**What a registry installs is the skill folder minus `.clawhubignore`**, which leaves out the test
file. So nothing in `SKILL.md` may link outside `skills/local-news-api/` or tell an agent to run the
tests; `TestRegistryBundle` checks both.

Two things follow for anyone editing it:

- **Extras belong under `metadata`.** The spec defines `name`, `description`, `license`,
  `compatibility`, `metadata` and `allowed-tools` and nothing else. Fields like `homepage` or
  `version` are not spec fields; they live inside `metadata`, which is where the spec puts
  arbitrary extras. Other public skill repos put them at the top level. That is a registry
  convention, not the standard.
- **Keep it under 500 lines and 5,000 tokens**, which is what the specification recommends for the
  body an agent loads on every run. Detailed reference material belongs in a `references/`
  directory, loaded on demand, and the guidance is explicit that you must tell the agent *when* to
  read it rather than gesturing at a folder.

## Style

- The tool is Python 3, **standard library only**. A dependency needs a strong argument; "it would
  be tidier" is not one, because the install story for a community journalist is `git clone` and
  run.
- Every mode ends with next steps, related modes and a see-also. No dead ends, and errors carry a
  recovery path rather than just a status.
- Every output carries the newsroom's usage terms, **fetched from that newsroom at run time**, never
  hardcoded. That is not decoration: the person running this is republishing someone else's
  reporting, and a constant would print one newsroom's terms over another's work. If the terms
  cannot be read, say so; do not fall back to a remembered stance.
- No em dashes in prose or comments. Use commas, colons, parentheses, or two sentences.

## Reporting rather than fixing

If you would rather just tell us something is wrong, that is genuinely useful, especially
**"my key cannot reach X"**. Reach varies by role and we cannot see your key. Open an issue with the
output of `local_news_api.py check`, which is safe to paste: it prints statuses, never your key.
